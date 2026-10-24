# W2: Shortest Path `Nearest` - one ranking for the whole suite

Repo: `cjber/shortest-path-forever` (folder `ShortestPathForever`, Interface 16001).
Read `../brief.md`, `../boundaries.md`, `../round9/README.md`, then `shortest-path-forever/AGENTS.md`.

## Why

`boundaries.md` §3 gives Shortest Path "Nearest trainer, vendor or service by travel - one `Nearest` API; SkillUp
and Adventure Guide call it", and §6 lists `Nearest` as an outstanding contract "when they land". It has not
landed, so three addons each rank their own way:

- `shortest-path-forever/UI/Nearby.lua` builds an index from QuestieDB `npcFlags`, ranks by straight-line
  distance and navigates with `API.Navigate`. It has the only complete index in the suite.
- `skillup-forever/Integrations/Sources.lua` re-ranks vendors itself (straight-line, then up to `MAX_ESTIMATES = 6`
  travel estimates).
- Adventure Guide reads trainers from Tweaks (`Integrations/Tweaks.lua`) and has no travel ranking at all.

Every consumer also owns a copy of the "call it, fall back to the client waypoint" pattern (`legacy-forever/
Integrations/Navigate.lua`, `tweaks-forever/Integrations/Navigate.lua`). One ranked answer, priced by real travel,
removes two rankings and gives Field Guide the primitive its hunt route needs.

## What to build

Raise the API to `minor = 2` (`Core/API.lua:268` is `local API = { version = 1, minor = 1 }`; the convention in
`types/API.lua` is that additions keep the version and raise `minor`, and callers check `type(api.Name) ==
"function"`).

```lua
-- kind: one of the service keys this repo already understands (see the SERVICES table in UI/Nearby.lua:
-- class, trainer, repair, reagents, vendor, innkeeper, bank, auction, flight, stable) plus "mailbox" if and only
-- if the client exposes mailboxes through the same QuestieDB data.
-- from: { map = uiMapID, x, y } - nil means the player.
-- opts: { limit = 1..20 (default 5), specialty = string?, faction = "A"|"H"? }
API.Nearest(kind, from, opts) -> entries, reason
-- entries: { id = npcID, name, map, x, y, kind, specialty?, seconds?, distance?, newFlightPath?, zone? }[]
-- reason: "loading" | "noquestiedb" | "nomap" | nil
```

Rules:

1. **Real travel, not yards.** Rank by `seconds` from the planner (`Route/Planner` through the same path
   `Estimate` uses - this repo has `ns.EstimateLegs`, `API.Estimate`, and a 256-entry 5-second cache in
   `Core/API.lua`; reuse them, never call the planner directly from the API file). Price at most
   `max(8, limit * 2)` straight-line-nearest candidates, so a cold call stays inside the frame budget; anything
   unpriced keeps a straight-line position after the priced ones and carries `distance` instead of `seconds`.
2. **Same continent first.** A vendor on another continent must not outrank one in the next zone because the
   planner could not reach it. Entries the planner cannot reach keep `seconds = nil` and sort last.
3. **Deterministic ties**: equal `seconds`, then equal distance, then ascending `id`.
4. **Copies only.** Fresh tables per call; a caller editing its result must not touch the index.
5. **Never nil-trap.** Unknown `kind` -> `nil, "loading"`-style triple is wrong; return `nil` plus a reason from
   the vocabulary above, and validate `from` the way `Point()` does in `Core/API.lua` (finite, 0..1, integer map).

Implementation: move the QuestieDB index build out of `UI/Nearby.lua` into a new `Core/Nearest.lua` (data +
ranking, no frames), and have `UI/Nearby.lua` consume it so there is exactly one builder. Keep `UI/Nearby.lua`'s
observable behaviour identical - same menu, same order for the common case, same strings - and say in the PR body
what you measured. `Core/Nearest.lua` must load after `Core/Core.lua` and before `UI/Nearby.lua` in the TOC; do
not reorder anything else.

Also expose the same index through the API so a caller need not build one:

```lua
API.NearestKinds() -> string[]   -- the kinds this build can answer, sorted
```

## Non-goals

Do not add `RouteQuests` (separate item, needs the quest planner). Do not change `Estimate`, `Navigate`,
`NavigateRoute`, transport timing or the planner. Do not let a caller pass its own index or its own comparators.

## Tests and gates

- `tests/nearest_spec.lua`: each kind resolves; ordering by seconds with an injected planner; unreachable last;
  tie-break order; `limit` clamping; bad `from`; unknown kind; deep-copy isolation; empty index; QuestieDB missing.
- Extend the `tests/api_spec.lua`-style checks for `minor == 2` and the new members.
- `tests/ui.sh` and the Nearby behaviour must stay green. Run the full `AGENTS.md` gate, including
  `tools/typecheck.sh` (new API members need `types/API.lua` annotations), `luajit -joff tests/journey_bench.lua`,
  `python3 tools/check_locales.py` (nine translations for every new phrase, `-- mt` on machine lines) and
  `python3 .sift/gate.py --base origin/main`.
- If `UI/Nearby.lua` gains or changes a player-visible string, the screenshot suite (`tools/screenshots*.py`,
  `tools/check_screenshots.py`) must be re-recorded and you must look at the rendered PNGs.

## Report

Gate lines, the proposed version and CHANGELOG entry, the PR URL with head SHA, the measured cost of a cold
`Nearest` call (report the number from `tests/journey_bench.lua` or a spec timing), and anything you could not
verify without a client. No version bump, no tag.
