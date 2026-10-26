# wowmock notes

Things learned building WoW: Forever mock screenshots from wago.tools data. First user: tweaks-forever
`tools/screenshots.py` (gear.png, menu.png).

## wago.tools endpoints

- DB2 as CSV: `https://wago.tools/db2/<Table>/csv?build=<build>`. The Forever build is `1.60.1.70124`; list
  builds at `https://wago.tools/api/builds/latest`.
- File bytes: `https://wago.tools/api/casc/<fdid>?download&build=<build>`. **Always pass `&build=`.** Without it
  you get current retail (12.x), whose UI art differs. An unknown build returns HTTP 400.
- Path to fdid: `https://wago.tools/api/files?search=<substring>` returns `{"fdid": "path"}` for every match.
  It takes ~30-35 s a call, so resolve paths in parallel (`Wago.resolve`) and cache them in `paths.json`. Paths
  are lower-case with forward slashes and a `.blp` extension (`interface/common/whiteiconframe.blp`).
- Send a User-Agent; urllib's default is fine but a named one is polite.

## Textures

- Pillow 12 reads BLP2 palette and DXT, but **not encoding 3** (uncompressed BGRA, header byte 8 == 3), which
  the newer c60 atlas sheets use. `decode_texture` reads mip 0 raw: width/height at offset 12, first mip offset
  at 20, first mip size at 84, pixel order BGRA.
- Item icons: `Item.IconFileDataID`. Some items have 0 there; fall back to ItemModifiedAppearance (lowest
  OrderIndex) -> `ItemAppearance.DefaultIconFileDataID`.
- Many older items are absent from the Forever ItemSparse (e.g. Cruel Barb 5191). Check before planning a
  scene around an item.

## Atlases

- Element name (what `SetAtlas` takes, case-insensitive) -> `UiTextureAtlasElement.ID` -> all
  `UiTextureAtlasMember` rows with that `UiTextureAtlasElementID` -> `UiTextureAtlas` (FileDataID, size, set).
- An element has several members: plain, `-2x`, and `-c60` / `-c60-2x`. Choosing:
  1. A member in an atlas with `UiTextureAtlasSetID == 1` wins. That is the Forever ("c60") art set: gold
     metal frames, gold dropdown border, red/gold close button, beige tooltip border.
  2. Otherwise **avoid `-c60` members that sit in set-0 atlases**. Proof: the tooltip centre has a c60 member
     in a set-0 atlas that is brown; the real Forever tooltip is the blue-grey of the plain member.
  3. Then the resolution nearest the render scale, then the highest member ID (duplicates exist, e.g.
     common-search-border-left in atlases 1541 and 3172).
- Some elements only exist as `-2x` (`ui-frame-metal-*`, `bags-item-slot64`). That is fine; the logical size
  still comes out right.
- Logical size (UI units) = Override{Width,Height} if nonzero, else pixel size x 1024 / canvas width.
  Canvas = member's `UiCanvasID`, else the atlas's (UiCanvas 1 = 1024 wide, 2 = 2048). Check: the metal
  corner is 150 px on canvas 2 -> 75 units.
- Crop box = `Committed{Left,Top,Right,Bottom}` in atlas pixels. Scale by BLP size / AtlasWidth in case they
  differ.
- `CommittedFlags`: 4 tiles horizontally (names starting `_`), 2 tiles vertically (`!`), 6 both.
- **Slice margins**: `UiTextureAtlasElementSliceData` (Left, Top, Right, Bottom in UI units, SliceMode 0 =
  stretch). An atlas with a row there is drawn as a nine-slice by SetAtlas. `common-dropdown-bg` (16, 13, 16,
  19) is one; stretching it plain produces a fat blurry border.

## NineSlice layouts

Copy them from `Blizzard_SharedXML/Mainline/NineSliceLayouts.lua`. Semantics (NineSlice.lua): corners anchor
at their own corner with (x, y), WoW y up; edges run between the adjacent corners' inner points; Center
runs TopLeftCorner BOTTOMRIGHT (+x, +y) to BottomRightCorner TOPLEFT (+x1, +y1). mirrorLayout flips TR
horizontally, BL vertically, BR both, BottomEdge vertically, RightEdge horizontally.

## Colours

- GlobalColor rows are signed ARGB ints: `value & 0xffffffff`, then A = >>24.
- Item name colours (tooltip): 9d9d9d / ffffff / 1eff00 / 0070dd / a335ee / ff8000.
- Bag quality borders use BAG_ITEM_QUALITY_COLORS -> GlobalColor: COMMON_GRAY a8a8a8 (common items **do** get
  a grey border), UNCOMMON_GREEN 15b300, RARE_BLUE 0091f2, EPIC_PURPLE c845fa. Poor gets none.
- Tooltip centre = `Tooltip-NineSlice-Center` tinted TOOLTIP_DEFAULT_BACKGROUND_COLOR (171730), alpha 1; the
  texture itself is ~76% opaque, so what is behind shows through slightly, as in game.
- PANEL_BACKGROUND_COLOR is ~1f1f21 at alpha 0.8.

## Fonts and text

- FRIZQT__ fdid 615960, ARIALN 615958 (paths `fonts/frizqt__.ttf`, `fonts/arialn.ttf`).
- Pillow `truetype(size=height x scale)` matches a WoW font object's height. Lay out a line box `height` tall
  and draw with the default 'la' anchor at its top.
- Font objects (Blizzard_Fonts_Shared FontStyles.xml): GameFontNormal/Highlight = Friz 12, shadow (1, -1),
  gold/white; GameTooltipHeaderText Friz 14 no shadow; GameTooltipText Friz 12 no shadow; NumberFontNormal =
  ARIALN 14 with outline (stroke 1 unit); GameFontDisableSmall Friz 10 grey 808080.
- `|cffRRGGBB...|r` escapes are parsed by `parse_colours`; `colored()` builds them the way addons do
  (`floor(c * 255)`).

## Widgets (sources)

- Tooltip: padding 10, 2 units between lines, width = widest line + 20, a double line counting both texts plus
  a 40-unit gap (engine-side; measured on the skillup screenshot, see SkillUp scenes). Money line = SetTooltipMoney: "Sell Price:" then coins, 13-unit icons, 4 units apart.
- Bag item tooltip anchor (ContainerFrameItemButton_CalculateItemTooltipAnchors): button on the right half of
  the screen -> tooltip BOTTOMRIGHT at button TOPLEFT; left half -> BOTTOMLEFT at TOPRIGHT.
- ItemButton: 37x37; icon BORDER; `Interface\Buttons\UI-Quickslot2` 64x64 centred (0, -1); count BOTTOMRIGHT
  (-5, 2); quality border `Interface\Common\WhiteIconFrame` OVERLAY; hover `ButtonHilight-Square` ADD.
  An addon texture created in ARTWORK lands above the icon and below the quality border.
- Backpack (ContainerFrame.xml / .lua): width 178 (engine constant, assumed), 4 columns, spacing 5, HeldBagLayout,
  portrait 36 at (-4, 1) masked by TempPortraitAlphaMask, search box 96x18 at (42, -37), sort button at (-9,
  -34), money frame 13 high at the bottom inside `common-coinbox-*`. Items fill bottom-right to top-left in
  reverse, so slot 1 is top-left.
- Blizzard_Menu (MenuStyle1): `common-dropdown-bg` from (-10, +3) to (+10, -3) at alpha 0.925; insets 8/8/8/15;
  child width +20; rows 20 high in GameFontHighlight; title gold; checkbox `common-dropdown-ticksquare` +
  `common-dropdown-icon-checkmark-yellow`; divider `UI-TooltipDivider-Transparent` 13 high; submenu arrow
  `ChatFrameExpandArrow` 16x16; highlight `UI-QuestTitleHighlight` ADD. A context menu opens with its
  top-left at the cursor.

## Item stats

ItemSparse `StatModifier_bonusStat_i` (type) and `StatPercentEditor_i` (allocation /10000). Value =
round(RandPropPoints[ilvl].{Good,Superior,Epic}_{slot} x allocation), slot 0 head/chest/legs/2H, 1
shoulder/waist/feet/hands/trinket, 2 neck/wrist/finger/back/off-hand, 3 one-hand, 4 ranged. Stat types: 3 Agi,
4 Str, 5 Int, 6 Spi, 7 Sta. Armour, weapon damage and durability need more tables and are not derived, so
prefer rings/necks/trinkets for a hovered item, or add those lines by hand.

## Verifying accuracy

Compare against real in-game screenshots, cropped and enlarged side by side with Pillow and viewed with Read.
The addons' README images are mocks now, so the real captures come from the revisions before they were
replaced (`git show <rev>:<path> > /tmp/x.png`):

- legacy-forever `8afee98:docs/screenshots/menu.png`: context menu (border, tick squares, yellow check, arrow,
  gold highlight, divider); `map.png` and `tracker.png` at the same revision.
- skillup-forever `be11638:docs/screenshots/tooltip.png`: tooltip border and centre colour (this caught the
  c60-centre mistake: ours was near-black, the real one blue-grey ~(19, 18, 28)).
- skillup-forever `be11638:docs/screenshots/window.png`: c60 portrait frame, Professions window, side tabs.

Blizzard's UI source for layout numbers: `~/drive/proj/wow-handoff/blizzard-ui/Interface/AddOns`.

## Legacy Forever scenes (world map, tracker)

Built for `legacy-forever/tools/screenshots.py` (map, menu, tracker). Legacy Forever's own real captures, which the
mocks replaced, stay in that repo's git history (`git log -- docs/screenshots`); use those revisions, not
the current files, as ground truth.

- Lookups: a wago search for a texture path takes ~30 s. Resolve every path a scene needs in one
  `ui.wago.resolve([...])` call, which runs them in parallel, before rendering.
- Map art: UiMap -> UiMapXMapArt (PhaseID 0) -> UiMapArt -> UiMapArtStyleLayer (layer size, tile size) ->
  UiMapArtTile rows. `map_art` stitches the base layer. WorldMapOverlay rows name OffsetX/Y, TextureWidth/Height
  and WorldMapOverlayTile rows; tiles are power-of-two textures that `draw_overlay` crops to the real size.
  Explored overlays draw at full colour; Legacy Forever shades unexplored ones by drawing the same tiles tinted
  (0, 0, 0, 0.25).
- WorldMapFrame (Camelot, minimized, quest log hidden): 702x534, title spacer 67, map container (2, 67) sized
  697x465. The map is fitted with min(697/1002, 465/668) and centred. The rock background tiles at the file's
  own pixel size / ui.scale.
- NavBar: from spacer + (64, -25) to BOTTOMRIGHT (-50, 9). Home button width min(128, text + 50). Other buttons
  are text + 53 with a dropdown arrow and text + 30 without. The last button uses the selected texture.
  Leftmost buttons have the higher frame level, so draw right to left or each chevron hides under its
  neighbour. A breadcrumb follows UiMap.ParentUiMapID up to the cosmic map (Ashenvale 1440 -> Kalimdor 1414 ->
  Azeroth 947 = "World").
- Map buttons: the tracking options button is LEFT of the NavBar's RIGHT (10, -2) with its red reset X hidden.
  Forever adds nothing to the top-right button column, so an addon's first button goes at the container's
  TOPRIGHT (-4, -2). The side toggle `QuestCollapse-Show-Up` is at BOTTOMRIGHT (-2, 1). The help-plate button
  is left out, because it is unknown whether Forever hides it.
- ObjectiveTracker: width 260, top padding 38, module spacing 10. A module header is 26 high but counts 25 in
  layout; fromHeaderOffsetY 10, blockOffsetX 20, fromBlockOffsetY 10, lineSpacing 4. The block header is
  OBJECTIVE_TRACKER_BLOCK_HEADER_COLOR (0.749, 0.612, 0) and lines are 0.8 grey. Both are capped at 2 lines
  (`wrap_text(..., max_lines=2)` ends the cut with "..."). The "- " dash sits 1 unit higher than the line text,
  and wrapped lines indent to the text, not the dash.
- Inline textures: `|A:atlas:h:w|a` and `|T path:h:w|t` markup is laid out by `Canvas.text` and `text_width`, so
  a count row such as an addon's icon + "9/18" measures like the game. `atlas_markup` builds the string.
- Faithful but surprising: map pins under the completion corner are hidden by it, just as in game.

## SkillUp scenes (Professions window)

Built for `skillup-forever/tools/screenshots.py` (window.png, tooltip.png). The real captures it replaced are in
that repo's git history.

- **Text width (fixed in `Ui.font`)**: Pillow's default RAQM layout uses fractional advances and set Friz 12
  ~6% narrower than the client ("Handstitched Leather Bracers": 190 px against 203 px at scale 1.2). The
  client uses FreeType's hinted whole-pixel advances, which `ImageFont.Layout.BASIC` reproduces (204 px). This
  changes every scene's text widths slightly; regenerate older scenes before comparing them.
- **Tooltip double lines**: with correct widths, the real capture puts a line's left and right texts 40 units
  apart when that line sets the width, so `TOOLTIP_COLUMN_GAP` is now 40 (it was 20).
- **Inline textures sit on the glyphs**, not the line box: Friz's ascent puts the digits ~1.5 units below the
  box centre, and real coins are level with the digits. `Canvas.text` now centres icons on the ink of "0".
- `|T` offsets were ignored; `InlineTexture.offset` now carries (offsetX, offsetY) and moves the icon without
  taking space. Coins in a tooltip or recipe row come out at the text's 12 units even though
  GetCoinTextureString asks for 14 (coin ink 11 px at scale 1.2), so the SkillUp script passes 12.
- **Camelot NineSlice overrides** (`Blizzard_SharedXML/Camelot/NineSliceLayoutOverrides.lua`) move the metal
  corners: TopRight x -2, BottomLeft y -8, BottomRight x -2 / y -8. `camelot_layout()` applies them;
  `PORTRAIT_FRAME_TEMPLATE_LAYOUT` is the Camelot-adjusted PortraitFrameTemplate. `HELD_BAG_LAYOUT` and the
  world map's `PORTRAIT_FRAME_LAYOUT` do not apply them yet.
- Atlas override sizes are not consistently in 1x units: `common-icon-chatlink`'s -2x member says 50 while the
  1x member says 25 (the real size). Across the tables, 37 elements share one override for both densities
  and 13 double it, so there is no global fix; pass the size explicitly when a -2x member wins.
- ProfessionsFrame (Camelot) is 673x594: background art at (2, 21) and (3, 21), recipe list at (5, 72) 304
  wide, schematic 360x484 at the list's TOPRIGHT +2, rank bar at (110, -40). Portrait sits under the
  NineSlice.
- Rank bar: fill is the first cell (top-left) of `Skillbar_Fill_Flipbook_<Profession>` (30 rows x 2 columns),
  masked to 453 x progress by `Professions-skillbar-mask`. The expansion dropdown hides itself with one child
  profession, as on Forever. The white/yellow button past the bar's end is the crafting page's LinkButton
  (`common-button-tertiary-square-normal` + `common-icon-chatlink`).
- Recipe rows: 20 high, spacing 1, top padding 5; the "Unlearned" divider is 70 high. The skill-up arrow sits
  1 unit higher for orange. Grey (learned, no skill-up) rows hide the arrow but keep its space.
- Schematic: `Init` re-anchors Reagents to the description's BOTTOMLEFT (0, -20), overriding the XML anchor.
  The client wrapped "23/5 Light Leather" (~106 units) in the 108-wide Name box, so it keeps some slack.
- The overview side tab's `INV_SideTab_Professions_c60` is in neither the wago listfile nor
  ManifestInterfaceData, so its file data ID is unknown and Trade_Blacksmithing stands in. `Wago.resolve`
  used to crash on a miss (the search returns `[]`, not `{}`); it now raises its "no file" KeyError.

## Shortest Path Forever scenes

- `tools/screenshots.py` uses LuaJIT `Path.FindSync` and `Planner.LegPoints`, loading bundled Nav0/Nav1.
  Walking arrays also carry `wet` metadata: distinguish numeric array keys when serializing. Route 295
  is Auberdine–Menethil; 11167 also calls at Southshore. Route 292 is Menethil–Theramore.
- Dock labels must follow the current data: with three Auberdine piers, DockPierName(8) is
  “Auberdine northeast pier”, not the older mock’s hardcoded “north pier”. Hover labels use projected
  cluster coordinates; dock 24 becomes “northwest pier” there, but “west pier” in the tracker.
- UiMapAssignment projects `(world y, world x)` in reverse from Region_4/Region_3 to Region_1/Region_0,
  then into UiMin/UiMax. This supplies both continents' rectangles on UiMap 947 (Azeroth).
- `objective_tracker(..., container=False)` starts at the module header, as in owner capture 21.
  Its AutoScalingFontString has width 200 and minimum height 12. Journey totals moved to this header
  after that capture; the destination remains a separate block heading. Boats is a separate scene:
  the addon owns one module, with dock content appended beneath a journey when both are active.
- Owner map/tracker captures use approximately 1.2 pixels per UI unit. Parchment crops align at
  Darkshore `(171,171,460,553)` and Kalimdor `(249,18,633,548)` within a 1.2-scale map face. Pin sizes,
  tracker wrapping and colours compare well; font baselines/rasterization still vary by a few pixels.
- Shared `minimap_art(ui, map_id, x, y, radius)` reads the pinned Map.WdtFileDataID's MAID chunk.
  MAID entries contain **eight** uint32 IDs: index 6 is the terrain normal map, index 7 is minimapTexture.
  At Kalimdor tile (30,20), 1290784 is the normal map and 207875 is the actual Auberdine minimap.
  Each tile spans 1600/3 yards, with tile coordinates `32 - world_y/unit, 32 - world_x/unit`.
  These minimap textures are 256 square. The helper stitches before cropping, so tile boundaries align.
- Camelot Skin.lua selects `UI-HUD-Minimap-Frame` and `ui-hud-minimap-frame-generic-mask`; the face is
  198 square. Diel.lua supplies the moon/day indicator at (63,72), under `UI-HUD-Minimap-Frame-Cycle`.
  Reference 19 confirms the frame and terrain. The selected 233⅓-yard radius and 16-unit native waypoint
  are engine-side assumptions; the mock omits other tracked POIs/navigation beams.
- `tooltip_backdrop` uses legacy texture IDs 137056/137057, not modern GameTooltip NineSlice art.
  Backdrop.lua's horizontal UV mapping requires ROTATE_270 (clockwise); ROTATE_90 reverses top/bottom
  and leaves disconnected corners. The compass's border is 12 units with 3-unit insets. The supplied
  compass capture predates its soft border, stock fonts and proportion-preserving marker update.
- `world_map_frame` now applies `camelot_layout(PORTRAIT_FRAME_LAYOUT)` to its metal corners, matching
  Camelot's x=-2 right-corner adjustment and y=-8 bottom offsets.
- Route widths/dashes are physical pixels. Static 2x images keep 2-pixel cores, 4-pixel outlines and
  6/5 dashes; a GIF must render at final size to preserve them. Draw all outlines below all cores.
  For a shared GIF palette, weight UI crops as heavily as map parchment and reserve white, grey,
  gold and cyan: an unweighted map can otherwise turn the small tracker text yellow.
- All assets now fetch successfully. Eight PNGs and an eight-second GIF render deterministically.
  `docs/verification/` contains enlarged owner comparisons and sampled GIF frames. No owner dock-tooltip
  capture was supplied; its stock widget was checked against SkillUp's real `be11638` tooltip, its
  content/anchors against Map.lua. No game client was used.

## Tweaks Forever scenes (exploration, junk, campsite, Edit Mode)

- Junk marks: ContainerFrame.xml's JunkIcon is `bags-junkcoin` at atlas size, TOPLEFT (1, 0), OVERLAY 5,
  over the quality border (`item_button(junk=True)`, `container_frame(junk=indices)`). The game shows it
  on greys only at a merchant, so keep greys out of a bag scene unless the addon draws their coin.
- Revealed maps: draw the addon's unexplored overlays first, tinted, then `map_overlays` (the explored
  areas) at full colour on top, as the addon's ARTWORK -1 layer sits under Blizzard's. Redridge (1433)
  reads well; Stranglethorn (1434) overlay tiles raised an IndexError in `draw_overlay`.
- Tooltip wrapping is not modelled: `tooltip` sizes to its widest line. A wrapped line in-game stops at
  about spell-tooltip width, so keep lines under ~250 units or split them by hand.
- Campsite aura 1230587 has an empty Spell.Description_lang in this build; the addon's line falls back
  to the aura name. The scene asserts this so a build that adds text fails loudly.
- Edit Mode widgets, all numbers from the templates:
  `dialog_border` (DialogBorderTranslucentTemplate: Bg black 0.8 inset 7, DiamondMetal `Dialog` layout,
  which Camelot does not override); `unique_corners_layout(kit)` + `draw_nine_slice` (skips pieces whose
  atlas the build lacks; `OptionsFrame` has no Center); `panel_tabs` (PanelTabButtonTemplate: width text
  + 20, min 72; active art at x-1 / right +8 and 42 high, inactive x-3 / +7 and 36 high; tabs 3 apart;
  selected text white 3 below centre, others gold 2 above); `minimal_slider`
  (MinimalSliderWithSteppersTemplate: bar 19 in, steppers 11x19 / 9x18 4 outside, 20x19 thumb travelling
  `w - 38 - 20`); `ui_panel_button` (UI-Panel-Button-Up texcoords, 12-wide caps, red in this client);
  `close_button`; `edit_mode_checkbox` (32x32 UI-CheckBox-Up/Check files, GameFontHighlightMedium label
  +5, rows 32 apart); `edit_mode_selection` (EditModeSystemSelectionLayout: corner mirrored 8 outside,
  centre at 50% alpha, label GameFontHighlightLarge centred when selected).
- `minimal_scrollbar(visible=, offset=)` draws the small thumb (track minus 38, `minThumbExtent` 23).
  ScrollFrameTemplate hangs its bar at TOPRIGHT (6, 2) to BOTTOMRIGHT (6, 5). Clip scroll content by
  drawing it on its own canvas of the scroll frame's size, then pasting.
- `Canvas.nine_slice` honours a piece's own `mirrorLayout`, as NineSlice.lua does.
- Edit Mode's real screen also shows every HUD system's blue highlight box over the game world; a scene
  on the plain backdrop leaves them out. No reference capture of the Windows tab exists yet.

`basic_panel(ui, title, w, h)` renders BasicFrameTemplateWithInset, including its inset, stock title and close button. Layout follows Blizzard_UIPanelTemplates/Mainline/UIPanelTemplates.xml:558–704; used for Tweaks gear groups/quest abandonment and SPF nearby services.
