# Field Guide Forever — visual polish round (owner request, 2026-10-22)

Repo: **cjber/bestiary-forever** (addon name Field Guide Forever, TOC `FieldGuideForever.toc`).

Owner's words: *"Visuals of the field guide still pretty rough can you please iterate more on them and actually
improve. Think about spacing, images, tabs used etc. kush lofs of ugly nits to solve."*

Read first: this file, `forever-handoff/brief.md`, the repo's `AGENTS.md`, the `wow-retail-ui-style` skill, and
`wow-mock-screenshots/NOTES.md`. The in-game UI wins over the mock: fix `UI/*.lua` first, then make
`tools/mockups.py` draw exactly what the Lua now draws. Never simplify the addon to suit the renderer, and never
edit a PNG.

## What is wrong today (verified in the source and in the current renders)

1. **Detail cards overlap.** `UI/Detail.lua`: `BuildRewards` is `Card(14, -320, 468, 66)` → bottom edge -386;
   `BuildSightings` is `Card(14, -370, 468, 112)` → top edge -370. They overlap by 16 units. The README does not
   show it because `tools/mockups.py` draws rewards at `ry+320` (h 66) and sightings at `ry+394` — the mock has
   silently drifted from the Lua.
2. **The detail column is lopsided.** The detail pane is 516 wide (`UI/Window.lua`, `right:SetSize(516, …)` at x 426)
   but every card is 468 wide at x 14 → 14 left margin, 34 right margin.
3. **The screenshots show three tabs; the addon has four.** `UI/Window.lua` `tabs` = CREATURES, RARES, SHINY,
   INSTANCES. `tools/mockups.py` calls `panel_tabs(... ["Creatures", "Rares", "Shiny"])` and indexes
   `("CREATURES","RARES","SHINY").index(tab)`. Every window scene misrepresents the tab strip.
4. **The filter control is in the wrong place in the mock.** Lua: `filterButton` at `TOPLEFT 288,-112`, 128×24,
   a `UIPanelButtonTemplate` to the right of the 250-wide search box. Mock: `filter_dropdown(canvas, px(942), …)`,
   a dropdown pinned to the far right of the window.
5. **Breadcrumb is a bare text in the mock.** Lua anchors a 20-high Button at (24,-90) with vertically centred text
   ending in `" ▾"`. Mock draws `text(px(24), py(90), …)` whose top is at 90 → the line sits ~9 units too high and
   has no caret.
6. **`Lv 40-40` and `Level 40-40`.** `UI/List.lua` and `UI/Detail.lua` print a range unconditionally. Single-level
   creatures must read `Lv 40` / `Level 40`; ranges use an en dash: `Lv 39–41`.
7. **Row geometry is not on a grid.** `UI/List.lua`: icon `TOPLEFT 10,-10` in a 58-high row (10 top / 16 bottom — not
   centred); name `52,-7`; sub `52,-26`; bar `52,-48`, 252 wide, 3 high. That leaves a 64×48 void under the icon, ends
   the bar 64 short of the counter column, and the 368-wide selected tint runs to the scroll gutter (scroll frame only
   reserves 26, and the tint visually touches the thumb).
8. **Bottom bar is a three-row staircase with mismatched buttons.** `BuildBottom`: label at (14,-8), `%` at (14,-23),
   bar at (120,-27) 320×6, count at (120,-38), `Open Journal` 112 wide, `Track Species` 132 wide, 14 gap, and the
   bar's own right inset (12) does not match its left inset (18).
9. **Header rhythm.** subtitle `TOP 0,-30`, `headerLine` at -52, tabs at -54: the rule is 2 units above the tab tops,
   so it reads as a stray line rather than the tab shelf. Tabs are placed at fixed `20 + (i-1)*100`, which is not how
   `PanelTemplates_TabResize` sizes them and can collide with localized labels. Tab x (20), search x (24) and
   breadcrumb x (24) do not share a left edge.
10. **Mock invents content that the addon never shows** — `"Rank I — Discovered"` in the Research card,
    `"Mastery · recorded deaths"`, `"Local records"` (Lua says `"Your records"`), `"Catalogued"` (Lua says
    `"Known"`), `"First rare or shiny record · local to this character"`, and dimmed checkmarks beside locked
    rewards. All of it must be replaced with the strings and states the Lua actually produces.
11. **Padding constants are arbitrary.** Current mix: 6, 7, 8, 9, 10, 14, 16, 18. Nothing lines up between the
    header, the list, the cards and the footer.

## What to change — exact target geometry

Adopt one rhythm: **2 / 4 / 8 / 12 / 16**, card inset **10**, gap between cards **10**, header-to-first-line **6**,
column left edge **14**.

### Shell (`UI/Window.lua`)
- Tabs: keep `PanelTabButtonTemplate`; place tab 1 at `TOPLEFT 24,-58`; each later tab anchored `TOPLEFT` to the
  previous tab's `TOPRIGHT` with `4,0` (never a fixed 100 pitch). Keep `PanelTemplates_TabResize(button, 0)`.
- `headerLine` to `TOPLEFT 18,-52` / `TOPRIGHT -18,-52` (unchanged) and tabs at -58 gives the rule 6 units of air.
- Subtitle: `TOP 0,-28`.
- Search stays `(24,-112)`, 250×24; filter button stays `(288,-112)`, 128×24. Give both the same height (24) and the
  same text inset, so their baselines match.
- Breadcrumb stays `(24,-90)`, 390×20; text vertically centred (`"LEFT"`), caret kept.
- Left pane `(18,-146)` 396×494 and right pane `(426,-146)` 516×494 stay.
- Do not modify the 960×720 shell size.

### Bottom bar (`BuildBottom`)
Two rows instead of three, all inside the existing 924×58 bar at `BOTTOMLEFT 18,12`:
- Row 1: `"ZONE COMPLETION"` muted small at `(14,-10)`; the percentage in gold normal immediately after it
  (`x = 14 + label width + 8`); `"87 of 96 species"` muted small right-aligned to `x = 360` on the same baseline.
- Row 2: `Art.Bar(bar, 320, 10, "complete")` at `(14,-28)`; fill width `320 * fraction` (update `UpdateProgress`,
  which currently sets `318 * fraction`).
- Buttons: both **120×26**; `Track Species` at `TOPRIGHT -12,-16`, `Open Journal` at `TOPRIGHT -140,-16`
  (120 + 8 gap). Text unchanged.
- `tools/visual_audit.py` pins `BUTTON_WIDTH = {"Open Journal": 112, "Track Species": 132}` and a `MIN_INSET` of 8 —
  update the expected widths to 120 and the expected right inset to 12. Do not lower `MIN_GAP` or `MIN_INSET`.

### Creature rows (`UI/List.lua`)
Row height stays 58, row width **356** (scroll gutter 40: scroll frame `BOTTOMRIGHT -26` plus 14 clear).
- Icon 32×32 at `(10,-13)` — vertically centred; bezel unchanged.
- Name `(52,-8)`, width 252. Sub `(52,-27)`.
- Progress bar `(10,-49)`, width **332**, height 3 — one full-width foot under icon and text, ending at 342, i.e.
  14 clear of the row edge.
- Counter right-aligned `TOPRIGHT -14,-8`; glyph `TOPRIGHT -14,-28`.
- Selected/hover tint inset: left 4, right 8 (draw at x 4, width = row width − 12) so it never touches the gutter.
- Level string: `min == max and L"Lv %d" or L"Lv %d–%d"`.

### Detail pane (`UI/Detail.lua`)
- `CARD_WIDTH = 488` (14 both sides). Everything that used 468 moves to 488; this includes the research bar
  (width `CARD_WIDTH - 20`), the lore wrap width, and the note.
- Card pitch, top to bottom, with **10** between cards and **6** below the badge row:
  - portrait 58 at `(14,-14)`; name `(84,-18)`; sub `(84,-40)`; badges row `(14,-76)` h 18
  - Research `Card(14,-102,488,84)` — title `(10,-8)`; pips start `x = 28` step **112** (4 pips fit 488 with a
    14 right margin); pip label under the dot, centred, width 88; connector from dot+13 to the next dot−13;
    `"Mastery"` label `(10,-60)`; count right-aligned `TOPRIGHT -10,-60`; bar `(10,-74,468,4)`.
  - Lore `Card(14,-196,488,58)`; title `(10,-7)`; body `(10,-21)`, width 468, at most 2 lines
    (`if lore.SetMaxLines then lore:SetMaxLines(2) end`).
  - Variants title `(14,-264)`; three cards at y `-280`, width **157/157/158**, gap 8, height 52; title `(10,-7)`,
    glyph `TOPRIGHT -10,-7` in a 12-wide box, status `(10,-29)`.
  - Cosmetic rewards `Card(14,-342,488,66)`; title `(10,-7)`; two equal columns (col x 10 and 258), label width 120,
    status right-aligned to the column's right edge (234 and 482), rows at `-28` and `-48`.
  - Your records `Card(14,-418,488,60)` (this is the overlap fix); title `(10,-7)`; body `(10,-21)`, width 468,
    3 lines max.
  - `Detail.note` anchored `BOTTOMLEFT 14,2` in muted small, one line, and it must not collide with the last card
    (cards end at -478, pane is 494 → 16 clear).
- Rarity pills: height 18, gap 6, left 14, `width = max(50, text width + 14)`, text centred both ways.
- Variant unknown state: `—` glyph and `"0 / 3"`; known state: `✓` glyph and `L"Known"`. Glyph and status share the
  same insets on all three cards.
- Reward markers: the client checkmark in `complete` when unlocked, a muted `—` text when locked. Never a dimmed
  green check for a locked reward.
- Research: keep the top-right rank label only if you add it to the Lua too, as a real phrase
  (`L"Rank %s — %s"` plus the four rank names already present). It is worth keeping: it reads better than pips
  alone. If you add it, it is the only new visible string in this round and must go in `Locales/enUS.lua`.
- All new/changed phrases go in `Locales/enUS.lua` and any phrase files `AGENTS.md` asks you to regenerate.

### Renderer (`tools/mockups.py`, and `tools/wowmock` only if a widget is genuinely wrong)
Mirror every number above. Then:
- Draw all four tabs; select the tab the scene is showing; the Instances scene selects INSTANCES.
- Move the filter control to `(288,-112)` as a 128×24 client panel button (same art the Lua uses), not a dropdown.
- Breadcrumb: 20-high box at `(24,-90)`, text vertically centred, caret included.
- Use the Lua's strings and states for badges, variants, rewards, research and records (item 10 above).
- Wrap the lore by pixel width, not `textwrap.wrap(..., 74)`.
- Icons: the list icon sits at `(10,-13)`; the detail portrait stays a 58 circular mask. Verify each row icon is the
  per-NPC model icon from `Data/CreatureIcons.lua`, not a family fallback and not the question mark. If any scene
  still shows a fallback for a species that has generated art, fix the resolution before rendering.
- The window subtitle is centred on the frame, but the circular portrait makes that look shifted right. Centre the
  subtitle on the title's own span (the frame's TitleContainer), not on the full window width.
- Keep renders deterministic; keep the shared GIF palette and `disposal=2`.

### Layout audit
`tools/visual_audit.py` only knows about tabs, search, filter and the two buttons. Add the detail cards, the badge
row, the research bar and the bottom-bar progress group to `LAYOUT` with their real rects, and extend the rules:
every card inside its pane, no card overlapping another, no card closer than 8 to its pane edge. Fix the code, not
the thresholds.

## Acceptance gates
- `stylua --check .`, `luacheck .`, every `tests/*_spec.lua` under luajit, `ruff check tools`,
  `ruff format --check tools`, `ty check tools`, `python3 tools/check_generated.py`,
  `python3 tools/visual_audit.py`, `python3 tools/check_screenshots.py`, `python3 tools/changelog.py --check`,
  `.sift/gate.py --base origin/main` and `.sift/agents.py check` — all green.
- Re-render **every** scene and `demo.gif`; `python3 tools/check_screenshots.py --record` to restamp
  `docs/screenshots/scenes.sha256`.
- Open every PNG the README references at full resolution AND step every GIF frame. Zoom-crop and re-check four
  regions: header + tabs, list rows, the five detail cards, bottom bar. Nothing clipped, cramped, overlapping,
  mis-baselined or touching a border.
- Add or extend a spec for the level-string formatting and for any model function you touch.
- One focused PR from fresh `origin/main`, conventional commit prefix, no `-s` (GitHub signs), brief body with
  Why / What / Gate / In-game checks (`/fg`, all four tabs, search + each filter, row select, scroll to the last
  row, 0% and 100% zone completion, UI scale 100% and 150%).
- State in the PR any place the mock still cannot match the client, honestly, instead of faking it.
