# Round: Shortest Path × Field Guide integration (spawns along the route)

Approved by the owner in #wow-addons on 2026-10-22, from the suite deep dive (idea 1). This round ships **three
slices**: a route proximity scan, HUD flags for the creatures it finds, and a detour cost for each one. Phase 2 of the
deep dive (a player-initiated hunt route that calls `NavigateRoute`) is **out of scope this round**; do not build it.

Boundaries that decide the shape (`forever-handoff/boundaries.md`, canonical):

- **Bestiary (bestiary-forever, "Field Guide Forever") proposes the targets; Shortest Path orders and executes travel.**
- **Tweaks owns rare alerting.** No chime, no sound, no alert frame, no nameplate or vignette marker. This feature is
  about route decisions only.
- **Field Guide must work with no other addon installed.** It gains an API and nothing else: no map pins, no `C_Map`
  calls, no UI change. Similarly SPF must degrade to nothing when Field Guide is absent, still loading, or at an API
  `minor` below 1.
- No automation: nothing re-routes the journey, adds a stop, or talks to the player unprompted. Pins and the tracker
  line are read-only displays.

Two PRs, in this order:

1. **bestiary-forever** - the spawn API (small, unblocks the other).
2. **shortest-path-forever** - the three slices, written so it works whether or not PR 1 has shipped.

Do not touch the existing `codex/engagement-tracking-*` branches or `Core/Progress.lua` work in either repo.

## PR 1 - bestiary-forever: expose creature spawn coordinates

Comment in the PR that this is Field Guide API **minor 1**, additive only.

`Core/API.lua`:

- `local API = { version = 1, minor = 1 }`. Record in the file's header comment that SPF's type docs say any addition
  raises `minor`, and name `Spawns` / `ZoneSpawns` as the minor-1 additions.
- `API.Spawns(speciesId)` returns flat rows, one per spawn point:
  `{ speciesID = integer, name = string, rare = boolean, catalogued = boolean, minLevel = integer, maxLevel = integer, map = integer, x = number, y = number }[]`,
  or `nil` when the answer is not known (not ready, catalogue not `ok`, unknown species, or no client zone table).
- `API.ZoneSpawns(zoneName)` returns the same row shape for every species in that zone (`nil` under the same
  conditions). `zoneName` follows `API.Species(zoneName)`: `nil` means the player's current zone, and an unknown name
  returns `nil` like the rest of the API.

Data sources and the two traps:

- Spawns are already in memory: `Integrations/QuestieDB.lua` stores `species.spawns = row.spawns`, typed
  `QuestieDBSpawnList = table<AreaId, QuestieDBCoordinate[]>`, where a coordinate is `{[1] = x, [2] = y, [3] = phase?}`
  on the **0 to 100** scale (SPF's `UI/Nearby.lua` divides QuestieDB coordinates by 100 for the same reason). Divide
  by 100 and reject anything outside 0..1 or not a number, as `Core/API.lua` does for its other inputs.
- An AreaId is not a uiMapID. Convert with QuestieDB's own support tables, exactly as `UI/Nearby.lua` does:
  `lib.RequireContract(2)` then `lib.Support.Get("ZoneDB").private.areaIdToUiMapId`, plus
  `areaIdToUiMapIdOverride`; both arrive as Lua source strings, so `loadstring` + `setfenv` in a sandbox table. If the
  lib, the contract, or those tables are missing, return `nil` rather than guessing (a wrong map draws a pin in the
  wrong place).
- `catalogued` is the character's own progress: `ns.Model.Specimen(state, speciesID).count > 0` for the species.
- Build the converted zone table **once** per catalogue/character load and cache it (a zone can hold thousands of
  points); every call returns fresh copies so a caller cannot reach saved state or the cache. No client API calls, no
  frames, no per-frame work.
- Add whatever annotations `types/` needs; keep Lua 5.1 and the addon's existing style (tabs, `local _, ns = ...`).

Tests (`tests/`), LuaJIT specs through `tests/wow_mock.lua`:

- New `tests/spawns_spec.lua`: nil before `ADDON_LOADED`; rows have `map` from the support table including an override
  case; `x`/`y` are the coordinate divided by 100; junk coordinates (0.5, nil, -1, 250) are dropped; `catalogued`
  flips when the fixture specimen has a count; two calls return independent tables; a `LibQuestieDB` without
  `Support` returns `nil` and does not error.
- Keep `tests/api_spec.lua` green; assert `API.minor == 1` and `API.version == 1` there.

`CHANGELOG.md`: one `### Added` bullet under `[Unreleased]`. Say the API is additive and names the two functions; no
version bump in this PR (the release does that).

Gate: the `## Commands` block in `bestiary-forever/AGENTS.md`. No UI change, so no new mockup is required; if you touch
any README prose, say why in the PR.

## PR 2 - shortest-path-forever: sightings along the route

Three slices, one PR, three commits (scan, detour, flags). Every rule in `shortest-path-forever/AGENTS.md` applies:
the TOC lists every runtime file in load order, no `require`, Lua 5.1, `read_globals` only for real client APIs,
art at native aspect through `UI/Art.lua`, no idle `OnUpdate`, searches and tracker updates wait until combat ends.

### Slice 1 - route proximity scan (commit 1)

New `Journey/Sightings.lua` (TOC entry in the journey block, after `Journey/Itinerary.lua`), in two layers:

- **Pure geometry, no WoW API**, in the `Core/Model.lua` mould: `ns.Sightings.Scan(points, rows, corridor)` where
  `points` is the remaining route as `{ map, x, y }[]` (current position first, then every stop still ahead, in order)
  and `rows` are Field Guide's spawn rows. For each row, find the nearest segment on the same `map`; keep it when the
  perpendicular distance is within `corridor` **normalized map units** (document the constant and why: the suite ranks
  nearby things by straight-line normalized distance, see `UI/Nearby.lua`, because this client exposes no map yard
  scale). Return one candidate per **species** (its closest point), each
  `{ speciesID, name, rare, map, x, y, offset = perpendicular distance, along = position on the route 0..1 }`.
- **Enrichment and caching**, `ns.Sightings.Refresh()`: read `FieldGuideForever` and its `API`; require
  `API.Ready()` and `(API.minor or 0) >= 1` and `API.ZoneSpawns`; for each distinct zone on the remaining route call
  `API.ZoneSpawns(zoneName)` (zone name from `C_Map.GetMapInfo(mapID).name` where it agrees with
  `ns.FindZone`/`Data/Zones.lua`). Skip rows with `catalogued == true`. Recompute at most every 10 seconds and only on
  a journey being active, out of combat; also refresh on journey start, stop, arrival, route change and zone change.
  Cache the result in a module-local table; expose `ns.Sightings.List()` for the UI and the tracker. Never hold a
  reference to Field Guide's returned table.

Spec `tests/sightings_spec.lua`: the pure scan against fixtures (point beside a leg, point beyond the corridor, point
on another map, two spawns of one species, a route with three legs and a re-used map), the `catalogued` filter, the
`minor < 1` refusal, the absent-addon case (`FieldGuideForever = nil`), and that `Refresh` is a no-op with an empty
journey. Use the existing `tests/journey_driver.lua` harness.

### Slice 2 - detour calculation (commit 2)

Price the best candidates, one planner call per frame (the cost is documented in `Core/API.lua`: up to ~2.5 ms cold,
~0.003 ms cached; "at most one uncached call per frame").

- `ns.Sightings.Price(candidate, estimate)` - pure: given a function returning seconds for a leg, detour seconds =
  `estimate(here, spawn) + estimate(spawn, nextStop) - estimate(here, nextStop)`, floored at 0, `nil` when any leg is
  unreachable. Test it with a stub estimate; no planner in the pure spec.
- `ns.Sightings.Queue()` - keeps at most the five candidates with the smallest `offset` (the ones the player would
  actually pass), asks `API.EstimateDetail` for the three legs across frames, stores `candidate.detour`, and re-sorts
  the list by detour. Cache per candidate key (speciesID, map, x, y, next stop, route epoch) for 30 seconds. `here` is
  `ns.JourneyPosition()`, `nextStop` is `ns.NextJourneyStop()`; give up quietly on `"combat"` and retry after combat,
  and on `"invalid"`/`"unreachable"` leave the candidate unpriced.
- Tracker line: while a journey runs and candidates exist, the tracker's SPF section gains one line naming the nearest
  candidate and its detour ("Field Guide: Dishu, +12 s detour" style, phrased through `L`). It must not become a new
  tracker section or fight `UI/Tracker.lua`'s ordering; if the tracker cannot take a line without restructuring it,
  put the same line in `UI/Report.lua`'s route summary and say so in the PR.

### Slice 3 - HUD waypoint flags (commit 3)

New `UI/SightingPins.lua` (TOC after `UI/FlightPins.lua`), modelled on `UI/FlightPins.lua`'s pool:

- On the world map, draw one flag per priced or unpriced candidate on that map, at its `x`/`y`, using the map pin
  machinery in `UI/MapCanvas.lua`. **Native art only**, verified in the pinned Blizzard UI source and the client's
  atlas lookup as `UI/Looks.lua` does: no invented atlas names, no stretched art, `tools/lint_art.py` must pass. If no
  native mapping marker fits, say so in the PR and fall back to the map's own plain POI dot rather than inventing art.
- Tooltip: creature name, "uncatalogued" and "rare" when true, the detour in seconds when priced, and nothing else
  actionable. No click-to-navigate this round, no waypoint set, no sound.
- A setting ("Show Field Guide creatures along the route", default on) in `UI/Settings.lua` under the map/journey
  group, gated so nothing runs when Field Guide is absent.

### Shared for PR 2

- `ShortestPathForever.toc`: `## OptionalDeps: QuestieDB, TweaksForever, RXPGuides, FieldGuideForever`; both new files
  in load order.
- `.luacheckrc`: add `FieldGuideForever` to `read_globals` (it is a real addon global).
- `types/`: annotate the new namespace tables and any pin mixin so `tools/typecheck.sh` stays green.
- `Locales/enUS.lua`: every player-visible phrase through `L`. Then `python3 tools/phrases.py > Locales/phrases.txt`.
  Follow `Locales/README.md` for the other locales and the repo's own locale check; machine translations carry
  `-- mt`.
- `CHANGELOG.md`: one `### Added` bullet per slice under `[Unreleased]`, prose in the repo's voice, no version bump.
- Screenshots: the feature is user-facing, so add a mocked scene to `tools/screenshots.py` (route plus Field Guide
  flags on the map, and the tracker line), render with `python3 tools/screenshots.py`, `--record`
  `tools/check_screenshots.py`, run `tools/visual_audit.py`, and add the image to the README gallery. Then **open the
  rendered image at full resolution and inspect it**: overlapping controls, clipped pins, a flag drawn off the map, a
  truncated label, a pin covering a stop pin. A green audit is not a visual check.
- Full gate from `## Commands` in AGENTS.md, including `luajit -joff tests/journey_bench.lua` (the planner budget) and
  the packaged-file check.
- The PR body lists the in-game `/reload` checks the owner must do (map open with a route running, pins on two maps, a
  candidate catalogued mid-route disappears, Field Guide disabled and the journey still works).

## Report back

Send `READY <PR URL> <head sha>` per PR with a one-paragraph summary of what changed and the `/reload` list. Do not
merge. Commit with `git commit` and no signing flags (`-s`, `-S`, `--signoff` are all wrong here: GitHub signs).
Conventional commits, no model names in commits, PR bodies or code.
