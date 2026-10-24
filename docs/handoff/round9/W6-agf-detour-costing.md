# W6: Adventure Guide detour costing - what a side trip actually costs

Repo: `cjber/adventure-guide-forever` (folder `AdventureGuideForever`, Interface 16001).
Read `../brief.md`, `../boundaries.md`, `../round9/README.md`, then `adventure-guide-forever/AGENTS.md`
(planner, golden files, corpus, 3 ms frame budget).

## Why

Adventure Guide decides what to do next and says why (`Core/Recommendations.lua`, `Planning/Model.lua`,
`Planning/Steps.lua`), but it has never been able to say what a suggestion *costs*. Shortest Path can:
`EstimateDetail` returns total seconds plus per-leg `{ mode, to, seconds, wait, newFlightPath }`, and
`Estimate(fromMap, fromX, fromY, toMap, toX, toY)` returns seconds with a 256-entry 5-second cache. A player
choosing between "this quest is on your way" and "this quest is twenty minutes north" is making a travel decision
the guide currently hides.

This is also the decision layer the Field Guide hunt route (W1) needs to be honest rather than blind, so building
it first pays twice. Owner: Adventure Guide, quoting Shortest Path for travel. It changes nothing about who
decides.

## What to build

1. **Pure cost model** in a new `Planning/Detour.lua` (namespace `ns.Detour`), no WoW API, injectable estimator:

   ```lua
   -- base:  { from = p, to = p }        the current step or stop the player is heading to
   -- cand:  p                          the suggested side trip
   -- estimate: function(a, b) -> seconds?
   Detour.Cost(base, cand, estimate) -> { seconds, there, back?, legs? }?
   Detour.Label(seconds) -> string      -- "+1m 40s", localised
   ```

   `Cost` = `estimate(from, cand) + estimate(cand, to) - estimate(from, to)`, never negative (clamp at 0),
   `nil` when any leg is unpriced - an honest "unknown" beats a fabricated number. Same-map comparison uses the
   straight-line yard distance only for ordering, never for the displayed seconds.
2. **Integration** in `Integrations/ShortestPath.lua` (or the existing `Integrations/Integrations.lua`, whichever
   the repo already uses for SPF - `Integrations/Integrations.lua:17` holds the current SPF check): version-checked
   (`api.version == 1`, `type(api.EstimateDetail) == "function"`), rate-limited to the visible cards (at most 8
   estimates per refresh), cached by (from, to) pair for 30 seconds, and skipped in combat. When SPF is absent
   every cost is `nil` and the UI shows nothing at all - not "+0s".
3. **Surface** where the decision is made: the journey/quest card in `UI/Overview.lua` / `UI/Widgets.lua` gets a
   muted "+1m 40s" on the right of the card, with a tooltip listing the legs (`EstimateDetail`) when it is
   available: "walk 1m 10s to Kharanos, fly 30s to Ironforge". A setting (default on) switches the badge off.
4. **Sorting**: one extra order option "cheapest detour" beside the existing orders in `Planning/Order.lua`,
   showing the same number, with a stable tie-break on the existing order. Do not change the default.
5. Nine locales for every new phrase (`deDE esES esMX frFR koKR ptBR ruRU zhCN zhTW`, `-- mt` on machine lines),
   `python3 tools/check_locales.py` clean, `python3 tools/phrases.py` regenerated as the gate requires.
6. Screenshots: the card with a badge and the tooltip are user-facing - re-record with `tools/screenshots.py`
   (`WOWMOCK` set), run `tools/check_screenshots.py --record`, then open each changed PNG at full resolution and
   check for overlap, clipping and truncation. Match the native client style per `../wow-retail-ui-style` rules.

## Tests

- `tests/detour_spec.lua`: the arithmetic (including the clamp, a missing leg, a zero-cost same-point trip), the
  label formatting across 0s / 59s / 1m / 1h+, and the stable ordering of "cheapest detour".
- `tests/detour_integration_spec.lua`: fake `ShortestPathForever.API`; card badge present with an estimate,
  absent without SPF, absent when `EstimateDetail` is missing (older SPF), and the cache allowing only N calls
  per refresh.
- Golden files and the corpus build must be unchanged unless the card text genuinely changed; if
  `AGF_UPDATE_GOLDEN=1` was needed, say why in the PR body. Run `luajit -joff tests/plan_bench.lua` and
  `AGF_BENCH_STRICT=1 luajit -joff tests/plan_bench.lua` and paste both.

## Boundaries

Adventure Guide still chooses; it only quotes travel. Do not order stops by travel inside the planner, do not
re-order the journey itself, do not call the Shortest Path planner directly or read its internals, and do not add
a second estimate cache that outlives a reload. If the badge needs a phrase that another addon already owns, keep
your own copy - shared phrases are vendored from Forever Core, not linked.

## Report

Gate lines (including both bench numbers), proposed version and CHANGELOG entry, PR URL with head SHA, how many
estimates a refresh of the default view costs, and the in-game checks for the owner. No version bump, no tag.
