import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools/wowmock"))
import wowmock as W

BUILD = "1.60.1.70124"
ui = W.Ui(scale=2, build=BUILD)

BTN = 20
ICON = 13
MINIMAP = 198
RIM_OFFSET = 5
# Core/MinimapButton.lua's first two default angles: bottom-left, then a little further round the rim.
FIELD_GUIDE_ANGLE = 225
ADVENTURE_GUIDE_ANGLE = 195
FIELD_GUIDE_ICON = "interface/icons/inv_misc_book_09.blp"
ADVENTURE_GUIDE_ICON = "interface/icons/inv_misc_map_01.blp"


def round_icon(ui, icon):
    """The icon as Core/MinimapButton.lua draws it: cropped to texcoords 0.08-0.92 and masked by CircleMaskScalable."""
    art = ui.texture(icon)
    w, h = art.size
    art = art.crop((round(w * 0.08), round(h * 0.08), round(w * 0.92), round(h * 0.92)))
    out = ui.canvas(ICON, ICON)
    out.draw(art, 0, 0, ICON, ICON)
    out.mask(ui.atlas("CircleMaskScalable").image, 0, 0, ICON, ICON)
    return out


def button(canvas, cx, cy, angle, icon, hover=False):
    """A register's button: the client's minimap plate, the addon icon, and the native round hover glow."""
    radius = MINIMAP / 2 + RIM_OFFSET
    x = cx + math.cos(math.radians(angle)) * radius
    y = cy - math.sin(math.radians(angle)) * radius
    state = "UI-HUD-Minimap-Button-Down" if hover else "UI-HUD-Minimap-Button"
    canvas.draw(canvas.ui.atlas(state), x - BTN / 2, y - BTN / 2, BTN, BTN)
    canvas.paste(round_icon(canvas.ui, icon), x - ICON / 2, y - ICON / 2)
    if hover:
        # The client's own round hover glow (bags-roundhighlight), the one its bag and container slots use.
        canvas.draw(
            canvas.ui.atlas("bags-roundhighlight"),
            x - BTN / 2,
            y - BTN / 2,
            BTN,
            BTN,
            color=(1, 1, 1, 0.55),
            blend="ADD",
        )


def minimap(canvas, cx, cy, hovered):
    """The client's Minimap at Auberdine: masked face, native frame, then the addon buttons on the rim."""
    terrain = W.minimap_art(canvas.ui, 1, 6464.8, 662.9, 233 + 1 / 3)
    face = canvas.ui.canvas(MINIMAP, MINIMAP)
    face.image = terrain.resize(face.image.size)
    face.mask(canvas.ui.atlas("ui-hud-minimap-frame-generic-mask").image, 0, 0, MINIMAP, MINIMAP)
    canvas.paste(face, cx - MINIMAP / 2, cy - MINIMAP / 2)
    frame = canvas.ui.atlas("UI-HUD-Minimap-Frame")
    canvas.draw(frame, cx - frame.width / 2, cy - frame.height / 2)
    cycle = canvas.ui.atlas("UI-HUD-Minimap-Frame-Cycle")
    canvas.draw(cycle, cx + 63 - cycle.width / 2, cy - 72 - cycle.height / 2)
    button(canvas, cx, cy, FIELD_GUIDE_ANGLE, FIELD_GUIDE_ICON, hovered == "field-guide")
    button(canvas, cx, cy, ADVENTURE_GUIDE_ANGLE, ADVENTURE_GUIDE_ICON, hovered == "adventure-guide")


def scene(path, hovered, tooltip_lines):
    width, height = 540, 340
    canvas = ui.canvas(width, height)
    minimap(canvas, 350, 175, hovered)
    if tooltip_lines:
        tip = W.tooltip(ui, tooltip_lines)
        canvas.paste(tip, 20, 120)
    base = W.backdrop(ui, width, height)
    base.paste(canvas, 0, 0)
    base.save(path)
    print("wrote", path, base.image.size)


def options(path):
    panel, px, py = W.basic_panel(ui, "Minimap Buttons", 420, 220)
    x, y = px + 20, py + 34
    panel.text(x, y, "Minimap", W.FONTS["GameFontNormalLarge"], W.NORMAL)
    W.edit_mode_checkbox(panel, x, y + 28, "Show the Field Guide button", checked=True)
    W.edit_mode_checkbox(panel, x, y + 66, "Show the Adventure Guide button", checked=True)
    panel.text(
        x,
        y + 120,
        "Drag a button around the rim to move it; the angle is saved.",
        W.FONTS["GameFontDisableSmall"],
    )
    base = W.backdrop(ui, panel.width, panel.height)
    base.paste(panel, 0, 0)
    base.save(path)
    print("wrote", path, base.image.size)


def detail(path):
    big = W.Ui(scale=6, build=BUILD)
    canvas = big.canvas(BTN * 2 + 40, BTN + 34)
    for index, (icon, hover) in enumerate([(FIELD_GUIDE_ICON, False), (FIELD_GUIDE_ICON, True)]):
        x = 10 + index * (BTN + 20)
        y = 24
        state = "UI-HUD-Minimap-Button-Down" if hover else "UI-HUD-Minimap-Button"
        canvas.draw(big.atlas(state), x, y, BTN, BTN)
        canvas.paste(round_icon(big, icon), x + (BTN - ICON) / 2, y + (BTN - ICON) / 2)
        if hover:
            canvas.draw(
                big.atlas("bags-roundhighlight"),
                x,
                y,
                BTN,
                BTN,
                color=(1, 1, 1, 0.55),
                blend="ADD",
            )
        canvas.text(
            x, 4, "hover" if hover else "normal", W.FONTS["GameFontNormalSmall"], W.NORMAL, width=BTN, justify="CENTER"
        )
    base = W.backdrop(big, canvas.width, canvas.height)
    base.paste(canvas, 0, 0)
    base.save(path)
    print("wrote", path, base.image.size)


scene(
    "minimap-field-guide.png",
    "field-guide",
    [
        W.TooltipLine("Field Guide"),
        W.TooltipLine("(Shift-F)", W.NORMAL),
        W.TooltipLine("Click to browse the field compendium", W.rgb("808080")),
    ],
)
scene(
    "minimap-adventure-guide.png",
    "adventure-guide",
    [
        W.TooltipLine("Adventure Guide"),
        W.TooltipLine("(Alt-G)", W.NORMAL),
        W.TooltipLine("Click to open the levelling guide", W.rgb("808080")),
    ],
)
options("minimap-options.png")
detail("minimap-button-detail.png")
