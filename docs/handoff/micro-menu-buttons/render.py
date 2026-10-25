import sys, math
sys.path.insert(0,'/home/nebula/wow/bestiary-forever/tools/wowmock')
import wowmock as W
from PIL import Image

BUILD='1.60.1.70532'
ui = W.Ui(scale=2, build=BUILD)

BTN_W, BTN_H, STEP = 32, 41, 27
NATIVE = ['Professions','SpecTalents','Achievements','Questlog','Groupfinder','GuildCommunities','Collections','AdventureGuide']

def glyph(u, icon, size):
    """An icon drawn on its own canvas at the target canvas's scale (micro glyphs carry no bezel)."""
    c = u.canvas(size, size)
    c.draw(u.texture(icon), 0, 0, size, size)
    return c

def micro_button(canvas, x, y, name, hover=False, alert=False):
    # MainMenuBarMicroButton: ButtonBG plate in BACKGROUND, the glyph atlas as the button's normal texture.
    u = canvas.ui
    canvas.draw(u.atlas('UI-HUD-MicroMenu-ButtonBG-Down' if hover else 'UI-HUD-MicroMenu-ButtonBG-Up'), x, y, BTN_W, BTN_H)
    suffix = 'Mouseover' if hover else 'Up'
    canvas.draw(u.atlas(f'UI-HUD-MicroMenu-{name}-{suffix}'), x, y, BTN_W, BTN_H)
    if alert:
        canvas.draw(u.atlas('UI-HUD-MicroMenu-Highlightalert'), x, y, BTN_W, BTN_H)

ICON = 22

def custom_button(canvas, x, y, icon, hover=False, alert=False):
    u = canvas.ui
    canvas.draw(u.atlas('UI-HUD-MicroMenu-ButtonBG-Down' if hover else 'UI-HUD-MicroMenu-ButtonBG-Up'), x, y, BTN_W, BTN_H)
    gx, gy = x + (BTN_W-ICON)/2, y + (BTN_H-ICON)/2 + 0.5
    # A soft contact shadow from the icon's own alpha, the way the painted glyphs sit on the plate.
    shadow = g_shadow(u, icon, ICON)
    canvas.paste(shadow, gx + 1, gy + 2)
    g = glyph(u, icon, ICON)
    if hover:
        g.image = W.tint(g.image, (1.15,1.15,1.15,1))
    canvas.paste(g, gx, gy)
    if alert:
        canvas.draw(ui.atlas('UI-HUD-MicroMenu-Highlightalert'), x, y, BTN_W, BTN_H)

def row(ui, w, h, buttons, hover_index=None, tooltip_lines=None, tooltip_side='left'):
    """buttons: list of ('native', name) or ('custom', icon). Right-aligned bottom-right of the crop."""
    canvas = ui.canvas(w, h)
    right = w - 6
    bottom = h - 6
    xs = [right - BTN_W - (len(buttons)-1-i)*STEP for i in range(len(buttons))]
    for i, b in enumerate(buttons):
        hov = (i == hover_index)
        if b[0] == 'native':
            micro_button(canvas, xs[i], bottom-BTN_H, b[1], hover=hov)
        else:
            custom_button(canvas, xs[i], bottom-BTN_H, b[1], hover=hov)
    if tooltip_lines:
        tip = W.tooltip(ui, tooltip_lines)
        i = hover_index
        tx = xs[i] + BTN_W/2 - tip.width/2
        ty = bottom - BTN_H - 8 - tip.height
        canvas.paste(tip, min(max(4, tx), w-4-tip.width), max(4, ty))
    return canvas

def g_shadow(u, icon, size):
    c = u.canvas(size+2, size+2)
    c.draw(u.texture(icon), 1, 1, size, size)
    alpha = c.image.getchannel('A').point(lambda a: int(a*0.55))
    black = Image.new('RGBA', c.image.size, (0,0,0,255))
    black.putalpha(alpha)
    out = u.canvas(size+2, size+2); out.image = black
    return out

FG_ICON = 'interface/icons/inv_misc_book_09.blp'
AG_ICON = 'interface/icons/inv_misc_map_01.blp'

def compose(name, canvas, w, h):
    base = W.backdrop(ui, w, h)
    base.paste(canvas, 0, 0)
    base.save(name)
    print('wrote', name, base.image.size)

# ---- 1. Field Guide button beside the game menu
btns = [('native', n) for n in NATIVE] + [('custom', FG_ICON), ('native','GameMenu')]
hover = len(btns)-2
lines = [W.TooltipLine('Field Guide'),
         W.TooltipLine('(Shift-F)', W.NORMAL),
         W.TooltipLine('Click to browse the field compendium', W.rgb('808080'))]
compose('micro-menu-field-guide.png', row(ui, 620, 150, btns, hover, lines), 620, 150)

# ---- 2. Adventure Guide Forever replaces the client's own adventure guide button
btns2 = [('native', n) for n in NATIVE if n != 'AdventureGuide'] + [('custom', AG_ICON), ('native','GameMenu')]
hover2 = len(btns2)-2
lines2 = [W.TooltipLine('Adventure Guide'),
          W.TooltipLine('(Alt-G)', W.NORMAL),
          W.TooltipLine('Click to open the levelling guide', W.rgb('808080'))]
compose('micro-menu-adventure-guide.png', row(ui, 620, 150, btns2, hover2, lines2), 620, 150)

def dropdown(canvas, right, top, text, h=18):
    """WowStyle1FilterDropdownTemplate placed by its TOPRIGHT, text vertically centred in the 18-high button."""
    u = canvas.ui
    font = W.FONTS['GameFontNormal']
    w = canvas.text_width(text, font) + 56
    x = right - w
    canvas.draw(u.atlas('common-dropdown-b-button'), x-4, top-4, w+8, h+8)
    canvas.text(x, top, text, font, justify='CENTER', width=w, box_height=h)
    return x, top, w, h

# ---- 3. Options panel with the toggles
PW, PH = 420, 250
panel, px, py = W.basic_panel(ui, 'Micro Menu Buttons', PW, PH)
ix, iy = px + 20, py + 34
panel.text(ix, iy, 'Micro menu', W.FONTS['GameFontNormalLarge'], W.NORMAL)
W.edit_mode_checkbox(panel, ix, iy+26, 'Show Field Guide button', checked=True)
W.edit_mode_checkbox(panel, ix, iy+64, 'Show Adventure Guide button', checked=True)
W.edit_mode_checkbox(panel, ix, iy+102, "Replace Blizzard's Adventure Guide button", checked=True)
panel.text(ix, iy+152, 'Position', W.FONTS['GameFontNormal'])
dropdown(panel, ix+250, iy+148, 'Left of Game Menu')
panel.text(ix, iy+186, 'Both buttons can also be bound in Key Bindings > AddOns.', W.FONTS['GameFontDisableSmall'])
base = W.backdrop(ui, panel.width, panel.height)
base.paste(panel, 0, 0)
base.save('micro-menu-options.png')
print('wrote micro-menu-options.png', base.image.size)

# ---- 4. zoomed detail strip at 4x
ui4 = W.Ui(scale=6, build=BUILD)
def zoomed(path):
    c = ui4.canvas(BTN_W*4*2+30, BTN_H+8)
    for i,b in enumerate([('native','AdventureGuide'),('custom',FG_ICON)]):
        x = i*(BTN_W+10)
        if b[0]=='native': micro_button(c,x,4,b[1])
        else: custom_button(c,x,4,b[1])
    base=W.backdrop(ui4, c.width, c.height); base.paste(c,0,0); base.save(path); print('wrote',path, base.image.size)
zoomed('micro-button-detail.png')
