# W4: gathering node route overlays (SkillUp proposes, Shortest Path routes)

Repo: `cjber/skillup-forever` (folder `SkillUpForever`). Shortest Path is read through its public API only -
you make **no** commits to `cjber/shortest-path-forever`.
Read `../brief.md`, `../boundaries.md`, `../round9/README.md`, then `skillup-forever/AGENTS.md`.

**Dependency: start only once W3's export PR is merged** (`cjber/skillup-forever` main contains the
`API.ShoppingList` entry in the CHANGELOG). W3 edits the same locale files and `UI/Shopping.lua`; starting early
buys you a conflict, not speed. While you wait, do the data feasibility check below and write your plan, then cut
your branch from fresh `origin/main`.

## Why

`boundaries.md` §3 hands this to SkillUp: "Gathering node route overlays | SkillUp | asks Shortest Path to route
between nodes; draws nothing itself". It has never been built. QuestieDB ships `ObjectDB.spawns` with exactly the
same shape as NPC spawns (`table<AreaId, Coordinate[]>`, see `Types/Object.t.lua:7` in the pinned QuestieDB
fixture), `Integrations/Prices.lua` already values a gathered material (`source = "gather"`), and W3 gives you the
list of what is still needed. So: "gather what this route needs, in the order that costs least".

## Feasibility check first (write it in the PR body)

The join is `reagent item -> object that yields it`. Establish it from data that already exists:
`Data/Sources.lua` / `Integrations/Sources.lua` say which reagents are gathered and by which profession, and
QuestieDB object rows carry names ("Peacebloom", "Copper Vein") and quest/loot references. Try, in this order:
1. the client's own node-to-item link if the pinned DB2 exports in this repo carry one;
2. QuestieDB object rows whose loot references name the item;
3. name matching against the reagent's name, case-insensitive, only as the last resort and only for objects whose
   name is unambiguous.

**If none of the three is reliable, stop and report** with what you tried. Hand-writing a node table (IDs, names
or coordinates) is forbidden - that is the same rule that keeps `Data/Reagents` honest, and a wrong node table
sends players to empty ground.

## What to build

1. `Model.Nodes`-style pure planning in `Core/Model.lua` or a new `Core/Nodes.lua`:
   `Nodes.Plan(needed, candidates, from, opts)` where `candidates` are `{ objectID, name, itemID, map, x, y }`
   and `from`/`opts` follow W1's hunt planner (injected `estimate`, budget, limit, deterministic order). Pure: no
   WoW API, no frames, injectable estimate, so it is pinned by a spec.
2. `Integrations/Nodes.lua`: read the node spawns through the same QuestieDB contract the other integration files
   use (`LibQuestieDB`, `RequireContract(2)`, `Support.Get("ObjectDB")`), with `loadstring` + `setfenv` for the
   packed tables, cached once, never per frame. Reuse the `Table()` helper pattern already in
   `skillup-forever/Integrations/Sources.lua` instead of writing a third copy.
3. `UI/Nodes.lua`: a "Gather on the way" section on the shopping panel listing the nodes it would add, the detour
   each costs and the total, with one button. The button calls
   `ShortestPathForever.API.NavigateRoute("SkillUpForever", stops)` (version-checked, `kind = "objective"`, real
   `title`/`tooltip`). No map drawing of any kind - that is the boundary. Fallback with SPF absent: set the game's
   own waypoint on the nearest node and say so.
4. Options: on/off (default off, because it is a route takeover), budget in minutes, node limit.
5. Only nodes whose material the current plan still needs and that are on the player's continent; never a node
   for a reagent that is already in the bags, never a node in a zone the planner cannot reach.
6. Nine locales for every new phrase (machine lines `-- mt`), `tools/check_locales.py` clean, mocked scene +
   README screenshot, `tools/check_screenshots.py --record`, and look at the rendered PNGs yourself.

## Specs

`tests/nodes_spec.lua` for the planner (needed filtering, budget, limit, unreachable last, stable order, empty
input, no estimate) and `tests/nodes_integration_spec.lua` with a fake ObjectDB and a fake `ShortestPathForever.API`
covering the route shape and every decline path. Extend the model specs for the item->node join once you have a
reliable source, with one real fixture row.

## Report

The feasibility finding first (which join you used, or why you stopped), gate lines, proposed version and
CHANGELOG entry, PR URL with head SHA, and the in-game checks for the owner. No version bump, no tag.
