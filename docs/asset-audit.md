# Asset audit: client art and our own art, for a keep/ban decision

Owner review sheets for `docs/asset-registry.md`. Every image here is cropped from the client's own atlas sheets
for build **1.60.1.70124**, or from a file the suite ships, rendered by `tools/asset_sheet.py`. Nothing is
redrawn or approximated, so what you see is what the client draws.

    python3 tools/asset_sheet.py --out docs/asset-audit     # regenerate every sheet

Labels are the element names `SetAtlas` takes, so a keep/ban decision here maps straight onto code.

## The client sets

"Elements" counts every atlas element whose name starts with the set's prefix. "Drawable" counts, of the first
40 element names alphabetically, how many actually render in this build; the rest have no committed member or
their atlas sheet is not shipped, so no addon can use them whatever we decide.

| Set | Elements | Drawable of 40 | Sheet | Read |
|---|---|---|---|---|
| native retail chrome (`common-`, `ui-frame-`, `minimal-`, `tooltip-`, `128-redbutton`) | 639 | 18 | `native-retail.png` | Flat metal, focus rings, masks, thin nine-slice trims. This is the look to keep. |
| garrison / class hall (`Garr*`, `ClassHall_*`, `orderhall*`) | 715 | 40 | `garrison-classhall.png` | Two different things: parchment mission-board maps with curled edges, and full-bleed painterly backgrounds with vignettes. The backgrounds are usable as illustration; the parchment is dated as chrome. |
| covenant / soulbinds | 334 | 11 | `covenant-soulbinds.png` | Full-bleed scenic art for a choice screen. Mostly undrawable here. |
| warfronts | 168 | 33 | `warfronts.png` | Embossed faction banners, stone/iron bevels, tiered-rarity icon plates. Old-style chrome. |
| housing | 170 | 40 | `housing.png` | Painted dashboard scenes plus flipbook particle FX. Scenic only; several sheets are missing. |
| pvp queue / pvp talents | 60 | 36 | `pvp-queue.png` | Stone and iron reward chests, painted queue banners, honour-bar rings. Dated. |
| shop / store | 515 | 39 | `shop-store.png` | Marketing art and 3D-preview backdrops; much of it is not shipped in this build. |
| dragonriding / plunderstorm | 215 | 21 | `dragonriding-plunderstorm.png` | Mode skins. Icon-level pieces are retail-era flat; the framing art is not. |
| `legacy*` | 60 | 39 | `legacy-old-style.png` | Dark wood and leather bevels, gold ribbons, bronze tree rings. The "very old style" you were leaning to ban. |
| questlog | 67 | 19 | `questlog.png` | Parchment column art. Mostly undrawable here. |

## Our own art

`our-own-art.png` shows the suite's remaining raster art: seven addon icons, one route dot and two tooltip borders.

Verified by inventory, not by eye alone:

| File | Size | Referenced by | Read |
|---|---|---|---|
| `<7 addons>/media/Icon.tga` | 64x64 | each TOC's `## IconTexture` | One consistent family: gold mark on a dark rounded plate. Keep. |
| Field Guide icon | Blizzard `INV_Misc_Book_09` | `FieldGuideForever.toc` | Uses the client book icon; no duplicate addon texture is needed. |
| `legacy-forever/media/Shade.tga` | Removed | Screenshot-only shading now uses a flat fill. |
| `shortest-path-forever/media/zeppelin.tga` | Removed | Runtime and screenshots use the client `flightmasterferry` atlas. |
| `shortest-path-forever/media/Dot.tga` | 32x32 | `UI/Route.lua:11` | Live route brush with a feathered alpha edge. |
| `shortest-path-forever/media/Icon.tga` | 64x64 | TOC | Keep. |
| `tweaks-forever/media/TooltipBorder{Modern,Retail}.tga` | 32x32 | `UI/Tooltips.lua:43-44` | Deliberate: replacing the client's beige tooltip border is the feature. Keep, and named as an exception in the style rules. |


## Addon UI audit

The right-edge integrations already use Blizzard's `LargeSideTabButtonTemplate`: Adventure Guide on the quest map,
and SkillUp's Gear and Route tabs on the profession panel. Hoard's and Tweaks' horizontal tabs live inside standalone
windows, so their `PanelTabButtonTemplate` is the matching native control. The other suite addons have no custom
right-edge tab UI.

The runtime UI uses Blizzard widget templates for controls. The few custom art pieces are semantic content (addon
icons and route strokes) or Tweaks' existing tooltip-style feature; we found no expansion-era frame chrome in runtime
Lua/XML. Garrison and other expansion names found by text search are zone names or test fixtures, not drawn assets.

## What this means for the blacklist

The keep list is the approved native retail set in `native-retail.png`. Use it for addon chrome; use Blizzard widgets
and templates for controls. Expansion-specific frames and painterly scenes stay out of addon UI, including garrison,
class hall, housing, warfront, PvP queue, questlog parchment, and legacy wood/leather pieces.

Game content icons remain Blizzard-owned content art; they are not frame chrome.

Two sets are not a judgement call at all: covenant/soulbinds and most of the shop art cannot be drawn in this
build, so they are unusable regardless.

## Fixes this audit found, outside the ban list

1. Field Guide's missing packaged icon is fixed by using the client book icon already used by its window.
2. Screenshot-only textures are not shipping assets; shade and zeppelin textures were removed and their screenshots now use flat/client art.
3. `shortest-path-forever/media/Dot.tga` now has a feathered edge.
