# Field Guide Forever — large square bottom tabs (owner request, 2026-10-26)

Repo: **cjber/bestiary-forever** (addon name Field Guide Forever, TOC `FieldGuideForever.toc`, Interface 16001).

Owner's words: *"also improve the mocks and UI for the field guide; remember i like the large square bottom tabs like
we have on the side; usually prefer those over internal tabs please"*

Read first: this file, `docs/handoff/field-guide-visual-polish.md`, the repo's `AGENTS.md`, and the
`wow-retail-ui-style` skill. The in-game UI wins over the mock: change `UI/*.lua` first, then make
`tools/mockups.py` draw exactly what the Lua now draws. Never simplify the addon to suit the renderer, never edit a PNG.

Reference render (already validated by eye against every acceptance point below):
`docs/handoff/field-guide-bottom-tabs/reference.png` — produced from the real catalogue and client art with the
constants in this brief.

## Decision — do not re-open the design

Ship **large square tabs docked along the bottom edge** of the window, hanging outside the frame like Blizzard's
Auction House tabs, replacing the four paper `PanelTabButtonTemplate` tabs currently sitting inside the frame at
`TOPLEFT 24,-58`. The `spine-left` / `spine-right` / `map-drawer` / `legacy-subpanel` renders in
`docs/screenshots/options/` stay as comparison images; the shipping window is the bottom strip.

## Tab chrome (validated at the window's 960×720, mock scale 2)

- Plate **64×64**, gap **6** between plates, plate 1's left edge at `frame left + 24` (the search box's inset).
- Plates hang **below** the frame: their top edge sits **6 units above** the frame's bottom edge, so the bottom bezel
  closes over the seam. Draw tabs **before** the frame art for exactly this reason.
- Icon **40×40**, 12 from the plate's left/right, **9** from the plate's top, inside
  `interface/common/whiteiconframe.blp`.
- Label: 8pt FRIZQT (a small variant of `GameFontDisableSmall`), centred, 11-high box whose top is `plate + size - 15`.
- **Active**: face `#35332b` with a 1-unit `#1c1e21` inner inset, a **3-unit gold lid** along the seam edge, gold border
  on the other three edges, gold icon bezel, gold label.
- **Inactive**: face `#141619`, border `#4d4a42`, brass icon bezel, body-text label.
- The selected state changes face, border, lid, bezel **and** label. No `PanelTemplates_*` art or helpers.

## UI work

`UI/Art.lua`: add the square-tab builder (e.g. `Art.SquareTab(parent, icon, label)`) plus any palette keys it needs in
`Art.COLORS` (plate-active, plate-idle, plate-border). It uses `CreateFrame("Button", nil, parent, "BackdropTemplate")`
with plate textures, the icon texture, the `whiteiconframe` bezel texture and a label FontString; expose
`button:SetSelected(on)` to drive all five state changes. Keep it in the palette/helpers file so `UI/Window.lua` only
places and drives the tabs.

`UI/Window.lua`:

- Delete `MakeTab`, `PanelTemplates_TabResize` / `PanelTemplates_SelectTab` / `PanelTemplates_DeselectTab`, and the
  header tab band. `.luacheckrc`: drop those three `read_globals` entries if nothing else uses them.
- Place tab `i` at `button:SetPoint("TOPLEFT", frame, "BOTTOMLEFT", 24 + (i-1)*70, 6)` — 64 plate + 6 gap, 6 tucked up
  under the bezel. Buttons are children of the frame, so they hide, move and raise with it.
- Reclaim the freed band: breadcrumb `24,-50`, search `24,-68` (250×24), filter button `288,-68` (128×24), divider
  `-100`, left pane `18,-110` (396 wide), right pane `426,-110` (516 wide), `PANEL_HEIGHT` **528** (content from 110 to
  `720-12-58-12`). `UpdateTabs` becomes "call `SetSelected` on each plate".
- Tabs stay **visible on every tab, Instances included** (today `Refresh` hides the breadcrumb, search, filter and
  bottom bar for `instances`; the tab strip must not hide). The Instances view's own top moves from `-146` to `-110`.
- Tab icons are **fixed client art**, never catalogue data: verify each path against the pinned build's listfile.
  Suggested: creatures `Interface\Icons\INV_Misc_Book_09`, rares `Interface\Icons\Ability_Hunter_BeastTaming`,
  shiny `Interface\Icons\INV_Enchant_ShardPrismaticLarge`, instances `Interface\Icons\INV_Misc_Coin_01` — swap any
  that the pinned client does not ship. The label carries the meaning; the icon is decoration.

## Mock work

- `tools/mockups.py`: one shared square-tab-strip helper used by `window()`; canvas grows by **58** at the bottom
  (`64 - 6`) so nothing is clipped, top/left/right margins unchanged.
- `docs/screenshots/layout.json`: replace the single `tabs` widget rect with the strip rect plus one rect per plate,
  all `role: "tabs"`, in the same units as the addon anchors them.
- `tools/visual_audit.py`: allow the tab strip to sit outside the frame's bottom edge by at most 64 units (still fully
  on the canvas), and keep the existing overlap/inset rules **between the plates** (6-unit gap is below the 8-unit
  `MIN_GAP` — exempt the plate-to-plate gap explicitly, with a comment saying tabs are meant to touch, or set gap 8;
  pick one and keep the addon and the mock identical). Document the exception in the module docstring.
- `tools/layout_options.py`: `current.png` now renders the shipping design (square bottom tabs); the other options are
  untouched. Add the `bottom` shape as its own render only if it is genuinely different from `current`.
- Re-render **every** README scene, `demo.gif` and `layout.json`; then `python3 tools/check_screenshots.py --record`.
- README: no new image entries needed; fix any caption or alt text that still describes the old tab strip.

## Acceptance

- Open every re-rendered PNG at full resolution and step through `demo.gif`: plates flush under the bezel on all four,
  active plate unmistakable, labels legible and uncut, nothing clipped at the canvas edge, nothing overlapping the
  footer's `Open Journal` / `Track Species`.
- The addon and the mock agree on plate size, gap, inset, tuck, icon size, label size and all five state colours.
- Gate green: `stylua --check .`, `luacheck .`, every `tests/*_spec.lua` under luajit, `ruff check tools`,
  `ruff format --check tools`, `check_generated.py`, `check_core_shared.py`, `visual_audit.py`, `check_screenshots.py`,
  `changelog.py --check`, `.sift/gate.py --base origin/main`, `.sift/agents.py check`.
- `CHANGELOG.md` entry under `## [Unreleased]` → **Changed**: Field Guide tabs are now large square plates docked along
  the bottom edge of the window, replacing the paper tabs inside the frame; the freed band moves the breadcrumb, search
  and list up.
- Open a PR with a green run. **Do not cut the release** — the maintainer merges and releases.
