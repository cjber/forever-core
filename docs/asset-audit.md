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

`our-own-art.png` is every texture the suite ships that is not client art: eight addon icons (seven present),
one shade, one dot, one zeppelin, two tooltip borders. This is the part that is actually "ours" to redesign, so
it matters more than the client sets.

Verified by inventory, not by eye alone:

| File | Size | Referenced by | Read |
|---|---|---|---|
| `<7 addons>/media/Icon.tga` | 64x64 | each TOC's `## IconTexture` | One consistent family: gold mark on a dark rounded plate. Keep. |
| Field Guide `media/Icon.tga` | **absent** | `FieldGuideForever.toc` line 7 asks for it | **Broken.** bestiary-forever has no `media/` directory at all, so the addon ships with no icon. |
| `legacy-forever/media/Shade.tga` | 256x64 | nothing | Dead file: no code, XML or TOC names it. |
| `shortest-path-forever/media/zeppelin.tga` | 64x64 | nothing | Dead file, same reason. |
| `shortest-path-forever/media/Dot.tga` | 32x32 | `UI/Route.lua:11` | Live, but a hard-edged circle with no alpha feathering: aliases when the route is drawn off a whole pixel. |
| `shortest-path-forever/media/Icon.tga` | 64x64 | TOC | Keep. |
| `tweaks-forever/media/TooltipBorder{Modern,Retail}.tga` | 32x32 | `UI/Tooltips.lua:43-44` | Deliberate: replacing the client's beige tooltip border is the feature. Keep, and named as an exception in the style rules. |

## What this means for the blacklist

The ban list should be **the old-style chrome**, which is what you said: `legacy*`, `warfront*`, `pvpqueue*`,
`pvptalents*` framing art, garrison and class-hall parchment, questlog parchment, and the stone/wood/leather
bevel family generally. Those are the pieces that fight flat client chrome on the same screen.

The garrison atmospheric backgrounds and the housing painted scenes are a separate category: they are
illustration, not chrome, and they sit behind content rather than around it. Banning them costs nothing today
(no addon uses them) but they are not the same sin as a parchment border.

Two sets are not a judgement call at all: covenant/soulbinds and most of the shop art cannot be drawn in this
build, so they are unusable regardless.

## Fixes this audit found, outside the ban list

1. `bestiary-forever` ships no `media/Icon.tga` while its TOC asks for one; needs the icon adding.
2. `legacy-forever/media/Shade.tga` and `shortest-path-forever/media/zeppelin.tga` are referenced by nothing;
   delete them.
3. `shortest-path-forever/media/Dot.tga` needs a feathered edge.
