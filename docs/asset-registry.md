# WoW asset registry and blacklist

What art, fonts, and widgets the suite can reach, which of them fit the client's own
current look, and which are banned. Read with `.agents/skills/wow-retail-ui-style/SKILL.md`
(the rules); this file is the inventory those rules point at.

Pinned client: **1.60.1.70124** (`_classic_beta_`, Interface 16001). Every name and count
below is from that build's own DB2 tables and listfile, not from retail 12.x.

## The five layers of art the suite can reach

| Layer | What it is | Size / reach | Where |
|---|---|---|---|
| 1. Client atlases | Every `SetAtlas` element the client ships, resolved to its sheet, crop box and slice margins | 2,802 atlases, 20,722 atlas elements, 20,522 members; 217 atlases in art set 1 (the `c60` Forever set); 1,167 elements have a set-1 member | `~/.cache/wowmock/1.60.1.70124/UiTextureAtlas*.csv` |
| 2. Client textures and fonts | Loose files by path/FDID (frame chrome, portraits, icons, FRIZQT/ARIALN) | 80 resolved paths, 131 files, 38 MB cached for the pinned build | `~/.cache/wowmock/1.60.1.70124/files`, `paths.json` |
| 3. Repo-owned art | The only art the addons themselves ship | `Icon.tga` in 8 repos; `legacy-forever/media/Shade.tga`; `shortest-path-forever/media/Dot.tga`, `zeppelin.tga`; `tweaks-forever/media/TooltipBorderModern.tga`, `TooltipBorderRetail.tga` | `<addon>/media/` |
| 4. Mock/render tooling | `wowmock` widgets, NineSlice layouts, font-object table | ~35 widgets (panel, tabs, side tab, dialog, scrollbar, slider, checkbox, edit-mode, tooltip, bags, context menu, world map, tracker); 11 font objects | `bestiary-forever/tools/wowmock/wowmock.py` |
| 5. Loose mock art | Web mockups and renders left in the trees | 13 species JPGs, 14 icon JPGs, window/mockup PNGs, and **Cinzel / EB Garamond / Marcellus** webfonts | `bestiary-mockup/`, `rarity-mockup/`, `rarity-recolour/` |

Cached builds on disk: `1.60.1.70124` (pinned, use this), `1.60.1.70450`, `1.60.1.70532`,
and `1.15.9.70003` — a Classic-era client whose UI art predates the Forever redesign.
Only `1.60.1.70124` is a legitimate art source.

## Tier 1 — use these (native, template-first)

1. **Templates before any texture**: `PortraitFrameTemplate`, `ButtonFrameTemplate(NoPortrait)`,
   `InsetFrameTemplate`, `BasicFrameTemplateWithInset`, `Dialog`/`StaticPopupDialogs`,
   `UIPanelButtonTemplate`, `PanelTabButtonTemplate`, `LargeSideTabButtonTemplate`, `InputBoxTemplate`,
   `MinimalScrollBar`/`WowScrollBarWithLabel`, `TooltipDefaultLayout`.
2. **NineSlice layouts** from `Blizzard_SharedXML/Mainline/NineSliceLayouts.lua`, applied with
   `NineSliceUtil.ApplyLayout`, plus Camelot's overrides where the frame is a Camelot frame.
3. **Art set 1 (`c60`) atlases** — the client's own Forever art. Coverage by family, elements
   that have a set-1 member: common widgets 108, minimal (scrollbar/input) 47, professions 57,
   128/red buttons 33, tooltip 13, unit frames 8, HUD/action bars 125.
4. **Font objects only**: `GameFontNormal(12)`, `GameFontHighlight`, `GameFontNormalSmall(10)`,
   `GameFontDisableSmall(10)`, `GameFontHighlightMedium(14)`, `GameFontHighlightLarge(16)`,
   `GameTooltipHeaderText(14)`, `GameTooltipText(12)`, `NumberFontNormal` (ARIALN 14, outlined).
   Family is FRIZQT everywhere else.
5. **Semantic colours**: `NORMAL_FONT_COLOR`, `HIGHLIGHT_FONT_COLOR`, `GRAY_FONT_COLOR`,
   `RED_FONT_COLOR`, `GREEN_FONT_COLOR`, `ITEM_QUALITY_COLORS`, `BAG_ITEM_QUALITY_COLORS`,
   `TOOLTIP_DEFAULT_BACKGROUND_COLOR`, `PANEL_BACKGROUND_COLOR`, `OBJECTIVE_TRACKER_*`.
6. **Item and spell icons** by their own `IconFileDataID` / correct subject name, wearing
   `interface/common/whiteiconframe.blp`, portrait masked by `TempPortraitAlphaMask`.

## Tier 2 — conditional

Use only where the client itself shows that art in the same context, and never as window chrome:

- `hud-*` / `UI-HUD-*` (678 elements, 125 with a set-1 member): legitimate **inside** a HUD system
  being skinned (action bars, cast bar, cooldown manager). Never as a border, divider, or panel edge.
- `talents-*`, `artifacts*`, `runecarving*` (423 elements, only 13 with a set-1 member): only those 13.
- `questlog-*` (67 elements, none in set 1) — the icon-level ones (`QuestLog-icon-setting`) are fine;
  the parchment column art is not.
- Expansion-flavoured icons for content that is genuinely that expansion (a Draenei portrait, a
  Pandaren map pin). Icons carry meaning; frames and chrome must stay neutral.

## Tier 3 — blacklist: never use

| Banned | Scale in build 1.60.1.70124 | Why |
|---|---|---|
| Garrison / class-hall art: `Garr*`, `GarrMission_*`, `GarrBuilding_*`, `ClassHall_*`, `orderhall*` | 718 elements, **0** with a set-1 member | WoD/Legion mission-table parchment, heavy bronze filigree. Reads as a decade-old expansion next to clean client chrome. |
| Covenant / soulbind art: `covenant*`, `covenantsanctum*`, `soulbinds*` | 318 elements, 0 in set 1 | Shadowlands styling, off-theme and never redesigned for Forever. |
| Warfront art: `warfront*` | 168 elements, 0 in set 1 | BfA tabletop art. |
| Housing art: `housing*` | 172 elements, 0 in set 1 | Retail 11.x system that has no Forever equivalent. |
| `shop-*` / store chrome | 516 elements, 0 in set 1 | Cash-shop storefront art, not client UI. |
| `dragonriding*`, `plunderstorm*`, `eyeofthejailer*` | 280 elements, 0 in set 1 | Event/expansion art with no set-1 counterpart. |
| PvP queue / PvP talents: `pvpqueue*`, `pvptalents*` | 60 elements, 0 in set 1 | Old PvP-frame art. |
| `gamepad*`, `cursor*`, `crosshair*` atlases | 3,302 elements | Input-device and cursor art; never window chrome or decoration. |
| Any `-c60`-named member that resolves into a **set-0** atlas | 352 `-c60` element names exist | The documented trap: the tooltip centre has a c60 member in a set-0 atlas that is brown, while the real Forever tooltip is blue-grey. Resolve to a set-1 atlas or take the plain member. |
| Loose legacy Backdrop textures: `interface/tooltips/ui-tooltip-border.blp` (137057/137056) | 1 file | The pre-NineSlice tooltip border. Use `Tooltip-NineSlice-*` / the template. |
| Hand-made frame chrome shipped in `media/` | — | A border, fill, gradient, gem, glow or crest drawn by us always reads as addon art. Style a missing element with a template instead of new art. |
| Non-client fonts: Cinzel, EB Garamond, Marcellus (and any other webfont in `*-mockup/`) | 3 families | Only FRIZQT and ARIALN are client fonts. Using anything else in a window, tooltip, or screenshot is instantly visible. |
| Hand-picked hex colours described as "gold" | — | Gold is the font object's colour and `NORMAL_FONT_COLOR`. A hex that is "gold-ish" is the single most common review flag. |
| `1.15.9.70003` cached art | 1 build | Classic-era client; its UI art predates the Forever redesign. |
| `legacy-forever/media/Shade.tga`, `shortest-path-forever/media/zeppelin.tga` | 2 files, 65,580 B and 16,428 B | Shipped art referenced by no code. Dead weight; delete rather than reuse. |

## Sanctioned exception, needs the owner's call

`tweaks-forever/media/TooltipBorder{Modern,Retail}.tga` (4,114 B each, drawn by
`tools/tooltip_border.py`, applied in `UI/Tooltips.lua`) is hand-made chrome and is therefore in
tension with the blacklist above. It exists because the client resolves `Tooltip-NineSlice-*` to its
own beige art, and the tweak's whole purpose is to offer the modern charcoal tooltip instead. It is
the one place where drawing our own art *is* the feature. Keep it, but it is the exception the rule
must name, not a precedent.

`shortest-path-forever/media/Dot.tga` (4,140 B, `UI/Route.lua` `DOT_TEXTURE`) is a 1px stroke
primitive, not chrome — allowed.

## What the addons actually reference today

Ten atlas names and three loose assets in total: `common-dropdown-bg`, `CircleMaskScalable`,
`questlog-icon-setting`, `common-icon-checkmark`, `common-dropdown-c-button-hover-arrow`,
`checkmark-minimal`, `Waypoint-MapPin-Tracked`, `Navigation-Tracked-Arrow`,
`UI-HUD-CoolDownManager-Bar`, `UI-HUD-CoolDownManager-Bar-BG`; `map-icon-suramardoor.tga`,
`media/Dot.tga`, `media/TooltipBorder*.tga`. Every one is Tier 1 or a named exception, so the
blacklist is prophylactic: it stops the next new feature reaching for garrison or covenant art.

## Checking an element before you use it

```python
# set 1 is the Forever c60 art; a set-0-only element is client art from another era
import csv, collections
base = '/.cache/wowmock/1.60.1.70124/'          # under $HOME
atel = {a['ID']: a for a in csv.DictReader(open(base+'UiTextureAtlas.csv', encoding='utf-8-sig'))}
elem = {e['ID']: e['Name'] for e in csv.DictReader(open(base+'UiTextureAtlasElement.csv', encoding='utf-8-sig'))}
sets = collections.defaultdict(set)
for m in csv.DictReader(open(base+'UiTextureAtlasMember.csv', encoding='utf-8-sig')):
    a = atel.get(m['UiTextureAtlasID'])
    if a: sets[elem.get(m['UiTextureAtlasElementID'], '?')].add(a['UiTextureAtlasSetID'])
sets['common-dropdown-bg']                    # {'0', '1'} -> has Forever art, use it
sets['GarrMission_EncounterAbilityBorder']    # {'0'}     -> blacklisted era
```
