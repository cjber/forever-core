import math
import sys
from pathlib import Path

from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools/wowmock"))
import wowmock as W

BUILD = "1.60.1.70124"
ui = W.Ui(scale=2, build=BUILD)

# LibDBIcon's construction, the art every LibDBIcon addon button on the rim uses.
BTN = 31
OVERLAY = 50
BACKGROUND = 24
ICON = 18
MINIMAP = 198
RIM_OFFSET = 5
HIGHLIGHT = 136477  # interface/minimap/ui-minimap-zoombutton-highlight.blp
TRACKING_BORDER = 136430  # interface/minimap/minimap-trackingborder.blp
MINIMAP_BACKGROUND = 136467  # interface/minimap/ui-minimap-background.blp
# Core/MinimapButton.lua's first two default angles: bottom-left, then a little further round the rim.
FIELD_GUIDE_ANGLE = 225
ADVENTURE_GUIDE_ANGLE = 195
FIELD_GUIDE_ICON = "interface/icons/inv_misc_book_09.blp"
ADVENTURE_GUIDE_ICON = "interface/icons/inv_misc_map_01.blp"


def icon_art(ui, icon):
    """The icon as Core/MinimapButton.lua draws it: cropped to texcoords 0.05-0.95, unmasked."""
    art = ui.texture(icon)
    w, h = art.size
    art = art.crop((round(w * 0.05), round(h * 0.05), round(w * 0.95), round(h * 0.95)))
    out = ui.canvas(ICON, ICON)
    out.draw(art, 0, 0, ICON, ICON)
    return out


def add_glow(canvas, texture, left, top, size):
    """Additive like the client's highlight: the texture's black backing adds nothing and stays transparent."""
    box = (canvas.px(left), canvas.px(top), canvas.px(left + size), canvas.px(top + size))
    region = canvas.image.crop(box)
    piece = texture.resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
    added = ImageChops.add(region.convert("RGB"), piece.convert("RGB"))
    alpha = ImageChops.lighter(region.getchannel("A"), piece.convert("L"))
    out = added.convert("RGBA")
    out.putalpha(alpha)
    canvas.image.paste(out, box[:2])


def button_art(canvas, left, top, icon, hover=False, pressed=False):
    """LibDBIcon's pieces at its sizes: background under the icon, tracking border over it, highlight on top."""
    cx, cy = left + BTN / 2, top + BTN / 2
    canvas.draw(canvas.ui.texture(MINIMAP_BACKGROUND), cx - BACKGROUND / 2, cy - BACKGROUND / 2, BACKGROUND, BACKGROUND)
    # LibDBIcon nudges the icon one unit down-right while the mouse button is held.
    nudge = 1 if pressed else 0
    canvas.paste(icon_art(canvas.ui, icon), cx - ICON / 2 + nudge, cy - ICON / 2 + nudge)
    canvas.draw(canvas.ui.texture(TRACKING_BORDER), left, top, OVERLAY, OVERLAY)
    if hover:
        add_glow(canvas, canvas.ui.texture(HIGHLIGHT), left, top, BTN)


def button(canvas, cx, cy, angle, icon, hover=False):
    """A register's button on the Minimap rim, centred on its angle."""
    radius = MINIMAP / 2 + RIM_OFFSET
    x = cx + math.cos(math.radians(angle)) * radius
    y = cy - math.sin(math.radians(angle)) * radius
    button_art(canvas, x - BTN / 2, y - BTN / 2, icon, hover)


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
    canvas = big.canvas(BTN * 3 + 60, BTN + 34)
    states = [("normal", False, False), ("hover", True, False), ("pressed", False, True)]
    for index, (label, hover, pressed) in enumerate(states):
        x = 10 + index * (BTN + 20)
        y = 24
        button_art(canvas, x, y, FIELD_GUIDE_ICON, hover=hover, pressed=pressed)
        canvas.text(x, 4, label, W.FONTS["GameFontNormalSmall"], W.NORMAL, width=BTN, justify="CENTER")
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
