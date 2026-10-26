# Field Guide Forever — native large side tabs (owner request, 2026-10-26)

Repo: **cjber/bestiary-forever** (addon name Field Guide Forever, TOC `FieldGuideForever.toc`, Interface 16001).

Owner's words, in order: *"also improve the mocks and UI for the field guide; remember i like the large square bottom
tabs like we have on the side; usually prefer those over internal tabs please"*, then *"Doesn't look like you're using
native UI here? Make sure you absolutely are. Maybe it's right tabs not bottom. I may have been mistaken"*.

**This brief supersedes `field-guide-bottom-tabs.md` (now deleted), the hand-drawn plate design, and the branch
`codex/field-guide-square-bottom-tabs`.** That design drew its own plates with fills and 1px borders — exactly the
failure mode `wow-retail-ui-style` rule 11 forbids — and there is no bottom tab template in the client. Discard it.
Start this work from `main`.

Read first: this file, the repo's `AGENTS.md`, and the `wow-retail-ui-style` skill. The addon wins over the mock:
change `UI/*.lua` first, then make `tools/mockups.py` draw exactly what the Lua draws. Never edit a PNG.

Reference renders (already inspected at 1:1 and at 4x on the tab strip):
`docs/handoff/field-guide-native-side-tabs/reference-creatures.png` (Creatures selected) and
`reference-rares.png` (Rares selected, proving the state moves). Both are rendered from the real catalogue and the
client's own tab atlas.

## What the client actually ships — verified, do not re-derive

The native "large square tabs like on the side" is **`LargeSideTabButtonTemplate`**, and it is exactly what the
Quests/Map window uses. Verified against the pinned build (`1.60.1.70532`) and the retail-era FrameXML annotations
bundled at `legacy-forever/.types/vscode-wow-api`:

- Definition: `Blizzard_SharedXML/Mainline/SharedUIPanelTemplates.xml:981` — `Frame`, `mixin="SidePanelTabButtonMixin"`,
  default size **43x55** (the art it draws is 51x60).
- Layers: `BACKGROUND` texture atlas **`questlog-tab-side`**; `ARTWORK` `Icon` anchored **`CENTER x=-2`**;
  `OVERLAY` **`QuestLog-Tab-side-Glow-select`**; `HIGHLIGHT` **`QuestLog-Tab-side-Glow-hover`**.
- Mixin (`SharedUIPanelTemplates.lua:295`): `SetChecked(checked)` swaps `Icon` between the instance's `activeAtlas` and
  `inactiveAtlas` and shows/hides `SelectedTexture`; `OnMouseDown` nudges `Icon` to `CENTER -1,-1`, `OnMouseUp` to
  `CENTER -2,0`; `OnEnter` opens the tooltip `ANCHOR_RIGHT -4,-4` with `self.tooltipText`.
- Placement in Blizzard's own window (`Blizzard_UIPanels_Game/Mainline/QuestMapFrame.xml:267,397-425`): tabs hang
  **outside the right edge**, first tab `TOPLEFT` -> frame `TOPRIGHT` **x=3 y=-28**, each following tab
  `TOP` -> previous `BOTTOM` **y=-3**. They are **icon-only**; the name is the tooltip.
- Atlases resolve in the pinned build: `questlog-tab-side`, `QuestLog-Tab-side-Glow-select`,
  `QuestLog-Tab-side-Glow-hover` are all **51.0x60.0**; the native icon atlases are 29.0x29.0.
- **In-suite precedent, already shipping:** `skillup-forever/UI/Route.lua:1144` and `UI/Gear.lua:751` both do
  `CreateFrame("Frame", nil, ProfessionsFrame, "LargeSideTabButtonTemplate")`, set `tab.Icon:SetTexture(...)`,
  `tab:SetFillToInterior(true)`, `tab.tooltipText = L[...]`, `tab:SetChecked(...)`. Match that usage.

There is **no** bottom tab template and no bottom tab art in the client. Do not rotate or recolour the side plates.

## UI work

`UI/Window.lua`:

- Build the four tabs with `CreateFrame("Frame", nil, frame, "LargeSideTabButtonTemplate")`, as skillup does. Keep them
  in a `Window.tabButtons` array as today.
- Anchor: tab 1 `SetPoint("TOPLEFT", frame, "TOPRIGHT", 3, -28)`; tab *i* `SetPoint("TOPLEFT", tabButtons[i-1],
  "BOTTOMLEFT", 0, -3)`. They are children of the frame, so they hide, move and raise with it.
- Per tab: `tab.tooltipText = L["CREATURES"]` (etc.), `tab:EnableMouse(true)`,
  `tab:SetCustomOnMouseUpHandler(function(_, button, upInside) if button == "LeftButton" and upInside then
  Window.SetTab(key) end end)`.
- Selection: `button:SetChecked(button.key == tab)` in `UpdateTabs` (replaces `PanelTemplates_SelectTab` /
  `PanelTemplates_DeselectTab`); `PanelTemplates_TabResize` goes away with `MakeTab`. Drop all three from
  `.luacheckrc` `read_globals` if nothing else uses them.
- Icons are fixed client item icons on `tab.Icon:SetTexture`, never catalogue art (the tab is decoration; the tooltip
  carries meaning). All four paths are in the pinned build's listfile:
  `Interface\Icons\INV_Misc_Book_09` (Creatures), `Interface\Icons\INV_Misc_Spyglass_02` (Rares),
  `Interface\Icons\INV_Scroll_03` (Shiny), `Interface\Icons\INV_Chest_Chain_05` (Instances).
- Reclaim the band the paper tabs occupied inside the frame. With the tabs outside, `BuildHeader` keeps only the
  portrait/title/close and the subtitle; delete the header rule line and the tab loop from it. New anchors, matching
  the reference render: breadcrumb `24,-44` (390x20), search `24,-62` (250x24), filter button `288,-62` (128x24),
  divider `-94`, left pane `18,-104` (396 wide), right pane `426,-104` (516 wide), `PANEL_HEIGHT` **534**.
- The strip stays **visible on every tab, Instances included**: the Instances branch of `Refresh` hides breadcrumb,
  search, filter and the bottom bar — it must not touch the tab frames. Move the Instances view's own top from `-146`
  to `-104`.

`UI/Art.lua`: no new palette keys, no plate textures, no border fills. If a shared helper is still wanted, it may only
wrap the template call and the tooltip/selection wiring — never draw chrome.

## Mock work

- `tools/mockups.py`: draw the strip with the real atlases, at the same anchors as the Lua —
  `canvas.draw(ui.atlas("questlog-tab-side"), x, y, 51, 60)`, the icon at `29x29` centred at `-2`, and
  `QuestLog-Tab-side-Glow-select` over the selected plate. No `canvas.fill`, no drawn borders.
- Canvas grows **60 units to the right** (51 plate + 3 offset + 6 margin); height unchanged.
- `docs/screenshots/layout.json`: one `role: "tabs"` rect per plate (51x60) plus the strip's bounding rect, in the
  same units the addon anchors them.
- `tools/visual_audit.py`: the tabs are legitimately **outside the frame's right edge** (by at most 54 units) and their
  plate-to-plate gap is **3**, below `MIN_GAP`. Exempt the strip from the "inside the frame" rule and exempt
  tab-to-tab and tab-to-frame pairs from the gap rule, with a comment naming `LargeSideTabButtonTemplate` and the
  Quest Log anchors as the reason. Every other widget keeps the existing rules. Say so in the module docstring.
- `tools/layout_options.py`: `current.png` now renders the shipping design (native right-side tabs); leave the other
  four comparison options untouched. Drop the hand-drawn `square_tab` helper if nothing else uses it.
- Re-render **every** README scene, `demo.gif` and `layout.json`, then `python3 tools/check_screenshots.py --record`.
- README captions/alt text: fix anything describing the old paper tabs.

## Acceptance

- Open every re-rendered PNG at full resolution and step through `demo.gif`. The plates must be client art — chamfered
  right corners, bevelled rim, gold `QuestLog-Tab-side-Glow-select` fill on the selected one — never flat fills.
  Four plates, even 3-unit gaps, first plate level with the title band, nothing clipped at the canvas edge, nothing
  overlapping the close button, search row or the footer's `Open Journal` / `Track Species`.
- Selection must visibly move when the tab changes (`demo.gif` is the proof, plus the two reference renders).
- The addon and the mock agree on: template name, 51x60 art size, `+3 / -28` anchor, `-3` stacking, 29x29 icon at
  `CENTER -2`, and the two glow atlases.
- Gate green: `stylua --check .`, `luacheck .`, every `tests/*_spec.lua` under luajit, `ruff check tools`,
  `ruff format --check tools`, `check_generated.py`, `check_core_shared.py`, `visual_audit.py`, `check_screenshots.py`,
  `changelog.py --check`, `.sift/gate.py --base origin/main`, `.sift/agents.py check`.

  `tests/wow_mock.lua` must stub `CreateFrame` for `"LargeSideTabButtonTemplate"` returning a frame with `Icon`,
  `SelectedTexture`, `SetChecked`, `SetCustomOnMouseUpHandler` and `tooltipText`, so the window specs still run.
- `CHANGELOG.md`, under `## [Unreleased]` -> **Changed**: the Field Guide's paper tabs inside the window are replaced
  by the client's own `LargeSideTabButtonTemplate` plates hung off the right edge, as the Quest Log does; the freed
  band moves the breadcrumb, search and panes up.
- Open a PR with a green run. **Do not cut the release** — the maintainer merges and releases.
