# WoW asset registry and blacklist

What art, fonts, and widgets the suite can reach, which of them fit the client's own
current look, and which are banned. Read with `.agents/skills/wow-retail-ui-style/SKILL.md`
(the rules); this file is the inventory those rules point at.

Pinned client: **1.60.1.70124** (Interface 16001; live client `_forever_`). Every name and count
below is from that build's own DB2 tables and listfile, not from retail 12.x.

## The five layers of art the suite can reach

Buttons use `SharedButtonTemplate`, `SharedButtonSmallTemplate`,
`SharedButtonLargeTemplate` or `SharedButtonExtraSmallTemplate`. These select the
gold-bordered set-1 `128-RedButton` family, including its pressed and disabled states.
The native `128-RedButton-Highlight` overlay is an approved set-0 exception.
The similarly named `128-GoldRedButton` shop family is outside this set.

The shared `forever_tools.assets` checker rejects legacy loose button, dialog,
tooltip and border chrome, plus the templates that select it. This includes
`UI-Panel-Button-*`, `UI-DialogBox-*`, `UI-Tooltip-Border/Background`,
`UI-Border-*`, `UI-Character-Border-*` and the `UIPanelButton*` template family.
It also rejects the profession crafting progress bar atlases
(`Profession-ProgressBar-BG` and `Profession-ProgressBar-frame`), which read as
the crafting cast bar wherever they are reused. A progress bar uses
`common-stat-bar-white` over `common-stat-bar-BG`, the `ColoredProgressBarTemplate` art.
It also rejects **any** loose `interface/` texture whose FileDataID is below
1,000,000, which catches old art that no name list knew about. The blacklist
applies to runtime Lua/XML and Python screenshot renderers, including art helpers
and references carrying an `art-ok` comment. Content icons and native host
backgrounds are separate from these chrome families, and the age rule leaves atlases alone.

## Pre-Legion chrome by FileDataID age

FileDataIDs were assigned roughly in the order art was added. About 130,000-140,000
is the 2004 UI, and 200,000-1,000,000 is Cataclysm and Mists of Pandaria (trainer
textures, marble and rock backgrounds, the Cataclysm Encounter Journal, help-frame
sheets). A loose texture referenced by path under `interface/` whose FileDataID is
below **1,000,000** is pre-Legion chrome and fails with
`pre-Legion UI chrome (FileDataID < 1000000); use an atlas`.

The age rule covers Lua, XML and the Python screenshot renderers. A value looks
like a client path when it starts `Interface\...` or `interface/...` (either slash,
any case) and may carry `.blp` or `.tga`. Exempt categories are content
(`interface/icons/`), maps (`interface/worldmap/`, including dungeon and zone
tiles), minimap map content (quest and objective blobs, tiles, pings including
`ui-minimap-ping-*`, arrows and unit markers), the empty equipment-slot art the client hands out through
`C_PaperDollInfo.GetInventorySlotInfo` (`interface/paperdoll/ui-paperdoll-slot-*`), portraits, `interface/cursor/` and fonts. Loose minimap chrome is
not blanket-exempt (the three LibDBIcon button pieces are allowlisted by name),
and neither are the 2004 tracking icons under `interface/minimap/tracking/`:
each fails the age rule and points at the atlas of the same name (`Repair`,
`Banker`, `Innkeeper`, and the rest).
`Interface\AddOns\<addon>\...` is the addon's own media, not a client file, so
the package check owns it.

A path under `interface/` that is not in the pinned build's listfile fails as
`unverifiable client path`, which catches a typo or art from another build. The
short allowlist in `forever_tools/legacy_chrome.py` names the few old pieces with
no modern replacement and gives a one-line reason for each (the raid target
markers, `WhiteIconFrame`, the native menu and item-button pieces `wowmock`
reproduces). Everything else old is fixed to an atlas or template.

The data is generated offline from the pinned build and committed, so the gate needs
no network:

- `forever_tools/legacy_chrome.txt` — sorted lowercase extensionless paths of
  banned chrome (6,772 paths, 317 KB).
- `forever_tools/interface_paths.txt` — every `interface/` path in the build, as a
  sorted zlib-compressed base64 set used for the fallback (144,998 paths, 731 KB).

Regenerate both after a client art pin change:

```sh
python3 tools/gen_legacy_chrome.py            # cached listfile under tools/.cache/legacy-chrome/
python3 tools/gen_legacy_chrome.py --refresh  # download the pinned build's listfile again
```

The generator reads the pinned build's listfile from wago.tools with both `version=`
and `build=1.60.1.70124`; its unpaged CSV export times out, so it asks for the
listfile's `interface/` slice through the search API. The generated files live in
`forever_tools/`, so `tools/forever_tools/sync.py` vendors them into every consumer
with the checker.

| Layer | What it is | Size / reach | Where |
|---|---|---|---|
| 1. Client atlases | Every `SetAtlas` element the client ships, resolved to its sheet, crop box and slice margins | 2,802 atlases, 20,722 atlas elements, 20,522 members; 217 atlases in art set 1 (the `c60` Forever set); 1,167 elements have a set-1 member | `~/.cache/wowmock/1.60.1.70124/UiTextureAtlas*.csv` |
| 2. Client textures and fonts | Loose files by path/FDID (frame chrome, portraits, icons, FRIZQT/ARIALN) | 80 resolved paths, 131 files, 38 MB cached for the pinned build | `~/.cache/wowmock/1.60.1.70124/files`, `paths.json` |
| 3. Repo-owned art | The only art the addons themselves ship | `Icon.tga` in 8 repos; `shortest-path-forever/media/Dot.tga`; `tweaks-forever/media/TooltipBorderModern.tga`, `TooltipBorderRetail.tga` | `<addon>/media/` |
| 4. Mock/render tooling | `wowmock` widgets, NineSlice layouts, font-object table | ~35 widgets (panel, tabs, side tab, dialog, scrollbar, slider, checkbox, edit-mode, tooltip, bags, context menu, world map, tracker); 11 font objects | `forever-core/tools/wowmock/wowmock.py` |
| 5. Loose mock art | Web mockups and renders left in the trees | 13 species JPGs, 14 icon JPGs, window/mockup PNGs, and **Cinzel / EB Garamond / Marcellus** webfonts | `bestiary-mockup/`, `rarity-mockup/`, `rarity-recolour/` |

Cached builds on disk: `1.60.1.70124` (pinned, use this), `1.60.1.70450`, `1.60.1.70532`,
and `1.15.9.70003` — a Classic-era client whose UI art predates the Forever redesign.
Only `1.60.1.70124` is a legitimate art source.

The visual sheets in `docs/asset-audit/` are prefix-search results, not approval lists.
`native-retail.png` includes blacklisted expansion scenes despite its name. The tiers below and
native host usage decide suitability. Clean Retail assets used by Forever are the target;
Retail origin alone, a matching prefix or a `c60` suffix does not establish approval.

## Tier 1 — use these (native, template-first)

1. **Templates before any texture**: `PortraitFrameTemplate`, `ButtonFrameTemplate(NoPortrait)`,
   `InsetFrameTemplate`, `BasicFrameTemplateWithInset`, `Dialog`/`StaticPopupDialogs`,
   `SharedButtonSmallTemplate`, `PanelTabButtonTemplate`, `PanelTopTabButtonTemplate`,
   `TabSystemTopButtonTemplate`, `LargeSideTabButtonTemplate`, `InputBoxTemplate`,
   `MinimalScrollBar`/`WowScrollBarWithLabel`, `TooltipDefaultLayout`.
2. **NineSlice layouts** from `Blizzard_SharedXML/Mainline/NineSliceLayouts.lua`, applied with
   `NineSliceUtil.ApplyLayout`, plus Camelot's overrides where the frame is a Camelot frame.
3. **Art set 1 (`c60`) atlases**, subject to the context restrictions in Tier 2 and bans in Tier 3.
   Set membership is a selection preference, not blanket approval. Coverage by family, elements
   that have a set-1 member: common widgets 108, minimal (scrollbar/input) 47, professions 57,
   128/red buttons 33, tooltip 13, unit frames 8, HUD/action bars 125.
4. **Font objects only**: `GameFontNormal(12)`, `GameFontHighlight`, `GameFontNormalSmall(10)`,
   `GameFontDisableSmall(10)`, `GameFontHighlightMedium(14)`, `GameFontHighlightLarge(16)`,
   `GameTooltipHeaderText(14)`, `GameTooltipText(12)`, `NumberFontNormal` (ARIALN 14, outlined).
   Family is FRIZQT everywhere else.
5. **Semantic colours**: `NORMAL_FONT_COLOR`, `HIGHLIGHT_FONT_COLOR`, `GRAY_FONT_COLOR`,
   `RED_FONT_COLOR`, `GREEN_FONT_COLOR`, `ITEM_QUALITY_COLORS`, `BAG_ITEM_QUALITY_COLORS`,
   `TOOLTIP_DEFAULT_BACKGROUND_COLOR`, `PANEL_BACKGROUND_COLOR`, `OBJECTIVE_TRACKER_*`.
6. **Item and spell icons** by their own `IconFileDataID` / correct subject name. Inspect the
   source before framing: preserve a baked bevel, or apply `interface/common/whiteiconframe.blp`
   once when the host uses it for an otherwise unframed icon. Never stack WhiteIconFrame over a
   source that already owns its bevel. Portraits use `TempPortraitAlphaMask` and the host portrait
   frame. See [ui-composition.md](ui-composition.md) for the one-owner and crop rules.

### Composition limits

The registry approves assets in their native host context, not as isolated pieces. A side tab,
top tab, bottom tab, portrait frame, map frame and content inset each have an edge owner. A
`PanelTabButtonTemplate` is not valid on a top edge or outer rail merely because the window is
standalone. Artwork must remain clipped inside its frame, and every icon must have exactly one
border owner. The UI art pin is `1.60.1.70124`, independent of any newer data pin.

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
| Profession crafting progress bar art: `Profession-ProgressBar-BG`, `Profession-ProgressBar-frame` | 4 elements, 2 in set 1 | Set membership does not approve a casting-bar context: the bar reads as the profession craft cast bar wherever it is reused. Use a plain `StatusBar` filled with `common-stat-bar-white` over `common-stat-bar-BG` instead. |
| Any `-c60`-named member that resolves into a **set-0** atlas | 352 `-c60` element names exist | The documented trap: the tooltip centre has a c60 member in a set-0 atlas that is brown, while the real Forever tooltip is blue-grey. Resolve to a set-1 atlas or use a plain member only with evidence that the intended native host uses it; the other blacklist rules still apply. |
| Loose legacy Backdrop textures: `interface/tooltips/ui-tooltip-border.blp` (137057/137056) | 1 file | The pre-NineSlice tooltip border. Use `Tooltip-NineSlice-*` / the template. |
| Hand-made frame chrome shipped in `media/` | — | A border, fill, gradient, gem, glow or crest drawn by us always reads as addon art. Style a missing element with a template instead of new art. |
| Non-client fonts: Cinzel, EB Garamond, Marcellus (and any other webfont in `*-mockup/`) | 3 families | Only FRIZQT and ARIALN are client fonts. Using anything else in a window, tooltip, or screenshot is instantly visible. |
| Hand-picked hex colours described as "gold" | — | Gold is the font object's colour and `NORMAL_FONT_COLOR`. A hex that is "gold-ish" is the single most common review flag. |
| `1.15.9.70003` cached art | 1 build | Classic-era client; its UI art predates the Forever redesign. |
| `legacy-forever/media/Shade.tga` | Removed | Legacy's completion bar draws the client's `Legacy-Progressbar-BG`, `-Fill` and `-Frame` atlases instead. |

## Named exceptions

The owner approved each of these by name. A new use of the same art in another context is not covered.

| Asset | Where | Why it stays |
|---|---|---|
| `islands-queue-prop-compass` | Adventure Guide, Legacy | The client shows it as a standalone prop on the Islands queue screen (`Blizzard_IslandsQueueUI.xml`): an illustrated object with no expansion branding, at high resolution. Allowed only as a standalone navigation icon, never as framing. |
| `shortest-path-forever/media/Zeppelin.tga` | Shortest Path | The client has no zeppelin icon. |
| `adventureguide-ring` | Shortest Path route stop ring | The only replacement on offer is a loose pre-Legion file. |
| `loottoast-sheen` | Field Guide, on shiny creatures | The owner asked for it. |
| The native target-frame rarity art | Field Guide | The owner asked for it; it is the client's own frame, recoloured. |


`tweaks-forever/media/TooltipBorder{Modern,Retail}.tga` (4,114 B each, drawn by
`tools/tooltip_border.py`, applied in `UI/Tooltips.lua`) is hand-made chrome and is therefore in
tension with the blacklist above. It exists because the client resolves `Tooltip-NineSlice-*` to its
own beige art, and the tweak's whole purpose is to offer the modern charcoal tooltip instead. It is
the one place where drawing our own art *is* the feature. Keep it, but it is the exception the rule
must name, not a precedent.

`shortest-path-forever/media/Dot.tga` (4,140 B, `UI/Route.lua` `DOT_TEXTURE`) is a 1px stroke
primitive, not chrome — allowed.

## What the addons actually reference today

Eleven atlas names and a few loose assets in total: `common-dropdown-bg`, `CircleMaskScalable`,
`questlog-icon-setting`, `common-icon-checkmark`, `common-dropdown-c-button-hover-arrow`,
`checkmark-minimal`, `Waypoint-MapPin-Tracked`, `Navigation-Tracked-Arrow`,
`UI-HUD-CoolDownManager-Bar`, `UI-HUD-CoolDownManager-Bar-BG`, `bags-roundhighlight`; `map-icon-suramardoor.tga`,
`media/Dot.tga`, `media/TooltipBorder*.tga`, plus the allowlisted native widget pieces `WhiteIconFrame`,
`ButtonHilight-Square` and `UI-QuestTitleHighlight`. The shared minimap button uses LibDBIcon's three loose
pieces by FileDataID, the same construction Questie's, RXP's and AtlasLoot's buttons already wear on the
player's rim: `136477` (`interface/minimap/ui-minimap-zoombutton-highlight`) as the button's highlight,
`136430` (`interface/minimap/minimap-trackingborder`) as the 50-unit overlay, and `136467`
(`interface/minimap/ui-minimap-background`) as the 24-unit background. They are the three minimap paths the
age rule's allowlist names, and each is drawn square to square at LibDBIcon's sizes. Every other
asset above is Tier 1, a named exception or an allowlisted native widget, so the blacklist is prophylactic:
it stops the next new feature reaching for garrison or covenant art.

## Checking an element before you use it

```python
# Set 1 is preferred; a set-0-only element needs native host evidence and a blacklist check.
import csv, collections
base = '/.cache/wowmock/1.60.1.70124/'          # under $HOME
atel = {a['ID']: a for a in csv.DictReader(open(base+'UiTextureAtlas.csv', encoding='utf-8-sig'))}
elem = {e['ID']: e['Name'] for e in csv.DictReader(open(base+'UiTextureAtlasElement.csv', encoding='utf-8-sig'))}
sets = collections.defaultdict(set)
for m in csv.DictReader(open(base+'UiTextureAtlasMember.csv', encoding='utf-8-sig')):
    a = atel.get(m['UiTextureAtlasID'])
    if a: sets[elem.get(m['UiTextureAtlasElementID'], '?')].add(a['UiTextureAtlasSetID'])
sets['common-dropdown-bg']                    # {'0', '1'} -> prefer set 1; still check context and blacklist
sets['GarrMission_EncounterAbilityBorder']    # {'0'}     -> this family is blacklisted, regardless of set
```
