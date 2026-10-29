# W1: Field Guide spawn coordinates, then "hunt these on the way"

Repo: `cjber/field-guide-forever` (folder `FieldGuideForever`, Interface 16001, `Locales/enUS.lua` only).
Read `../brief.md`, `../boundaries.md`, `../round9/README.md`, then `field-guide-forever/AGENTS.md` (its gate is the
strictest in the suite: stylua, luacheck, specs, ruff, check_generated, visual_audit, check_screenshots, changelog,
sift).

## Why

Field Guide knows where every creature spawns and shows the player nothing about it. QuestieDB hands
`spawns = table<AreaId, Coordinate[]>` to `Integrations/QuestieDB.lua` (it is stored on each species as
`spawns = row.spawns`, line ~127) and the code only reads the AreaId keys to decide which zone a species belongs
to - the coordinate lists are never touched. The addon draws no map markers at all.

The value is not another map overlay (boundaries §3 reserves the shared `ForeverMapMarkers` contract, which does
not exist yet). It is the route decision: "there are three uncatalogued rares within a minute of your route -
hunt them on the way?". Field Guide picks the targets, Shortest Path does the travel. That split is boundaries
rule 1 and rule 10: Shortest Path never chooses pickups, Field Guide never predicts spawns.

## PR 1 - spawn data in the public API (ship this first, small)

`Core/API.lua` is `version = 1` with no `minor`; Adventure Guide is at `minor = 3` and Shortest Path at
`minor = 1`, and `shortest-path-forever/types/API.lua` documents the convention: additions keep the version and
raise `minor`. Do the same here - `minor = 1`.

New functions, `nil` until `Ready()` and `ns.catalogueStatus == "ok"` (match every other call in the file):

- `API.Spawns(speciesId)` -> `{ map = uiMapID, x = 0..1, y = 0..1 }[]?` - every placeable spawn point of one
  species, `{}` when the species is known but has no placeable spawn (a dungeon-only creature whose area has no
  uiMapID). Copy the tables; never hand out `ns`'s own.
- `API.ZoneSpawns(zoneName?)` -> `{ id, name, map, x, y, rare, catalogued }[]?` - one entry per spawn point in
  the zone (default: the player's current zone, exactly as `API.Species` resolves it), where `rare` is the
  species' `rare` flag from the catalogue and `catalogued` is `ns.Model.Specimen(...).count > 0`.
- `API.NearbySpawns(zoneName?, limit?)` is **not** wanted - ranking belongs to the caller (see PR 2).

Implementation notes:

- QuestieDB spawn keys are **AreaTable IDs**, and instances point at their map in `ContinentID`. Convert with
  the table QuestieDB already ships, the way `shortest-path-forever/UI/Nearby.lua` does: `lib.RequireContract`
  then `lib.Support.Get("ZoneDB").private.areaIdToUiMapId`, read with `loadstring` + `setfenv` (that file has a
  working `Table()` helper - read it, do not import it). Cache the decoded map once; never decode per call.
- QuestieDB coordinates are 0-100 floats, not 0-1. Normalise and **prove it with a spec** that reads a real
  fixture value: assert a known species' spawn lands inside its zone's map bounds and that no coordinate is
  outside 0..1 after conversion. If the fixture says otherwise, follow the fixture and say so in the PR body.
- Keep `Integrations/QuestieDB.lua` the only runtime reader of QuestieDB (AGENTS.md). If you need the
  AreaTable map at load time, expose it through that file (`ns.ClientData` already holds zones/maps), not from
  the UI or API file.
- Creature names, levels and placement stay machine-derived. Nothing hand-written, ever.

Specs: extend `tests/api_spec.lua` (or add `tests/spawns_spec.lua`) for ready/not-ready, unknown species,
species with no spawns, an instance-area species, and the wire-through of `rare`/`catalogued`. Use the existing
mock client and the mock catalogue (`tools/gen_mock_catalogue.py`), not a live client.

Nothing in PR 1 changes the UI, so no screenshot is needed. Say that in the PR body.

## PR 2 - "hunt these on the way" (the actual feature), cut from fresh main after PR 1 merges

1. `Core/Hunt.lua`, pure arithmetic in the mould of `Core/Model.lua` (no WoW API, no frames, no globals beyond
   `ns.Hunt`):

   ```lua
   -- candidates: { id, name, map, x, y, rare, catalogued }
   -- from:       { map, x, y }   (the player, or the current route stop)
   -- estimate:   function(fromPoint, toPoint) -> seconds?   -- injected; nil = unknown
   -- isCatalogued: function(speciesId) -> boolean            -- injected
   Hunt.Plan(candidates, from, opts) -> { stops = {...}, totalSeconds, skipped }
   ```

   Rules: drop `isCatalogued` species; keep `rare` **and** elite-rank species (rank 2/4 in the catalogue's own
   terms - do not invent a new definition of rare); rank by `estimate` then by squared distance so a missing
   estimate never drops a candidate to the bottom by accident; take at most `opts.limit` (default 5); never
   exceed `opts.budget` seconds total detour (default 180); return the same order every run for the same input.
2. `Integrations/ShortestPath.lua` - optional, version-checked exactly like `legacy-forever/Integrations/Navigate.lua`
   and `tweaks-forever/Integrations/Navigate.lua` do it (`ShortestPathForever.API`, `api.version == 1`, check each
   function you call). Use `Estimate` for the ranking and `NavigateRoute("FieldGuideForever", stops)` for the
   route; every stop gets `title`, `tooltip` (species name + "uncatalogued"), `kind = "objective"`. Decline
   cleanly when SPF is missing, in combat, or has journeys switched off.
3. `UI/Hunt.lua` - a panel reachable from the window (and `/fg hunt`): the zone, the planned stops with the
   detour each costs ("+0:42"), the total, and one button "Hunt these". Without SPF the button sets the game's
   own waypoint on the first stop (`C_Map.CanSetUserWaypointOnMap` then `C_Map.SetUserWaypoint` +
   `C_SuperTrack.SetSuperTrackedUserWaypoint`) and the panel says so.
4. Options in `Core/Settings.lua`: the feature switch (default on), the detour budget in minutes, and the stop
   limit. Saved in the existing `FieldGuideForeverDB.options` style - flat and serialisable.
5. Important: the route replaces any journey another addon owns (Shortest Path has one journey slot and marks
   the replaced owner's journey `\"replaced\"`). That is acceptable **only** because the player pressed the
   button. Do not auto-start a hunt, do not append stops to another owner's route, and do not add a passive
   overlay (that waits on the Forever Core marker contract).
6. Per repo AGENTS.md a user-facing feature needs a mocked scene and a README screenshot: add the scene to
   `tools/mockups.py`, render, run `tools/visual_audit.py` and `tools/check_screenshots.py --record`, then open
   the PNG at full resolution and look at it - overlap, clipping, truncation, rows drawn outside the panel. Fix
   the renderer's shared constants, never the PNG. Update `README.md` and `CHANGELOG.md`.

Specs: `tests/hunt_spec.lua` for the planner (catalogued dropped, budget enforced, limit enforced, stable order,
missing estimates, empty candidates, duplicate points); a `tests/hunt_integration_spec.lua` with a fake
`ShortestPathForever.API` for the route shape, the decline paths and the waypoint fallback; and the API spec
extended for the new members.

## Boundary notes

Field Guide chooses targets and prices detours; Shortest Path orders and executes travel. Field Guide must still
work with nothing else installed (waypoint fallback). Do not read another addon's internals, do not call
`C_Map.SetUserWaypoint` behind the player's back. If you think a boundary needs to move, say so in the PR body -
the coordinator owns `boundaries.md`, not you.

## Report

Full gate from `AGENTS.md` with the result lines, the proposed version and its CHANGELOG entry, the two PR URLs
with head SHAs, what you could not verify without a client, and the in-game `/reload` checks the owner should
run. Do not bump the TOC version or tag anything.
