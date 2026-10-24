# Who does what: Shortest Path, Adventure Guide and the other Forever addons

Design note, 2026-10-17. No code changes. Read from `origin/main`: SPF 1.19.1 (API 1, minor 1), AGF 0.17.0
(API 1, minor 2), SkillUp 0.15.1 (API 1), Legacy 0.9.1 (API 1), Tweaks 0.14.1 (API 3). Round 6 is still in
working trees and is listed where it matters.

The short version: ordering the quests already in your log is travel, so it moves to Shortest Path as *Route my
quest log*. Adventure Guide keeps choosing what to do and saying why, and hands the chosen set to Shortest Path to
order and travel. The other three keep their jobs, with a few duplicates given one owner.

## 1. Today

### Shortest Path Forever (SPF)

- **Travel.** `Routing/Planner.lua` (transport graph, teleports, hearth with cooldown), `Routing/Path*.lua`
  (walking maps from `Nav/`), `Journey/JourneySearch.lua` (one bounded search from you and one back from the goal),
  `Journey/Itinerary.lua` (later hops of a multi-stop route, planned with the estimate's planner, about 2 ms cold).
  `Core/PlanContext.lua` holds the inputs every plan shares.
- **Guidance.** Tracker, arrow, compass, map and minimap route, stop pins with quest badges, the gold quest area
  (`UI/QuestBlob.lua`), corpse run, `/way` and the TomTom stand-in, the RestedXP adapter (`Core/RestedXP.lua`).
- **Quest input today:** *Plan journey* on one quest (`Planner.QuestDestination`, native POIs only). QuestieDB is an
  optional dependency, read only by *Nearby services* (`UI/Nearby.lua`).
- **API** (`Core/API.lua`, `docs/api.md`): `Estimate`, `EstimateDetail`, `NavigateRoute` (1 to 64 stops with
  `kind`, `hold`, `radius`, `shapes`, `questID(s)`), `Navigate`, `CurrentStop`, `Cancel`, `Active`, `Ended`,
  `Subscribe`. Polestar relies on these meanings.

### Adventure Guide Forever (AGF)

Selection, which is AGF's job:

- `Planning/Journeys.lua`: the cards (story, carry, next zone, dungeons, callings, battlegrounds), chain lead
  (`Lead`), reasons, log triage (`Droppable`), added quests.
- `Planning/Zones.lua`, `Model.LevelPreference` (level weighting for zones and quests), `Model.ChainStart`.
- `Integrations/QuestieSource.lua` (the composed catalogue, eligibility through Questie's policy),
  `Core/Offers.lua` (givers that don't offer a quest), `Integrations/Dungeons.lua`, `AtlasLoot.lua`,
  `RestedXP.lua`, `Polestar.lua`, `UI/Hints/*` (profession, hearth, explore), `UI/StoryCompletion.lua`.

Routing, which is really travel ordering:

- `Planning/Laps.lua` (980 lines): picks a lap's quests by XP per yard, anchors stops to towns, walks the lap
  nearest-first, verifies pickup → objectives → hand-in and log capacity, commits and merges visits.
- `Planning/Routing.lua` (562): `NearestStop` greedy order, `Order` (cross each ocean once), `Stabilise` and
  `Ranks` (committed order, replace only when it saves enough), `InArea`, `NearAction`, `Model.Here`.
- `Planning/Steps.lua` `AreaNode` (which spawn spot for an objective, skipping mobs 3+ above you, `alternates`
  for *Next spot*), `OpenSlots` and `Integrations/QuestieObjectives.lua` (matching log objectives to data slots).
- `Planning/Travel.lua`: an offline yard cost, through the side's docks across an ocean. It knows nothing of
  flights, portals, hearth or terrain.
- `Planning/Decoration.lua` (which giver in a town the arrow points at), `Planning/Focus.lua` (select the quest on
  walking into its area), `Planning/Refresh.lua` (repaint counts without a plan).
- `Planning/Order.lua`: the player's own order (`prefs.customOrders`) and dependency checks. This one is half
  and half: the wish is the player's, the check is routing.

AGF already calls SPF for the step-1 travel line (`EstimateDetail`) and hands the ordered steps to
`NavigateRoute` (`Integrations/Integrations.lua`). So AGF orders with a straight-line cost and then asks SPF to
travel an order SPF would not have chosen. That is the overlap: two planners, and the worse cost model decides.

### SkillUp, Legacy, Tweaks

- **SkillUp** (`Core/Plan.lua`, `UI/Route.lua`): cheapest profession route, shopping, trainer annotations,
  crafted gear. `Integrations/Sources.lua` picks the nearest trainer or vendor by SPF `Estimate` and sends you with
  SPF `Navigate`, else TomTom, else the map waypoint. API: `Professions`, `Navigate`, `OpenRecipes`.
- **Legacy** (`Core/ZoneCompletion.lua`, `UI/Map*.lua`, `UI/Tracker.lua`): Legacy challenges, zone completion,
  undiscovered-area shading, dungeon and raid entrance pins. API: `ZoneSummary`, `Targets`, `Navigate`,
  `Subscribe`. Its zone tooltip suggests AGF (`UI/Completion.lua`).
- **Tweaks** (`Features/Automation.lua`, `Bags/*`, `Map/*`, `Quests/*`, `UI/*`): quest accept and turn-in,
  vendors, gear groups, unexplored-area reveal, zone levels, dungeon entrance pins and interior maps, nearest-quest
  tracker sort (`Quests/QuestDistance.lua`), quest keys, nameplates, campsites, future spells, Train all. API v3:
  `TrainableSpells`, `Trainers`, `DungeonEntrance`.

All five ship a copy of `UI/TrackerHost.lua` (WFA-5 slots) and `UI/ForeverFamily.lua` from shared tooling.

### Round 6, in progress

- **SPF:** level-aware walks, hostile towns and cave arrival (`r6-spf-costs`), route styles, the Polestar
  contract written down and pinned by `tests/api_contract_spec.lua` (`r6-polestar-compat`), and gamepad-safe map
  drawing on frames of its own, no data providers or pins (`UI/MapCanvas.lua`, `r6-map-overlay`).
- **AGF:** elite and spot choice and cave arrival (`r6-camp`, touching `Steps.lua` and `QuestieObjectives.lua`),
  expiring items and missable warnings (`r6-safety`), party-shared quests and group lines (`r6-party`),
  gamepad-safe overlay pins (`r6-overlay-pins`).
- **Legacy and Tweaks:** gamepad-safe map overlays, and a shared marker-visibility contract.

The plan assumes round 6 lands first. Two things follow. AGF's new spot, elite and cave logic is routing and moves
with the rest, so it should be written with SPF's cost model in mind, not tuned further in AGF. And Tweaks' entrance
pins step aside by matching other addons' pin templates (`LegacyForeverPinTemplate`,
`ShortestPathForever*PinTemplate` in `Map/DungeonEntrances.lua`); once those are plain frames, that list matches
nothing, so the marker contract has to replace it in the same round.

## 2. The family: one job each

- **Shortest Path:** get you there, and in what order, the fastest way.
- **Adventure Guide:** what to do next for your level, and why.
- **SkillUp:** the cheapest way to level a profession.
- **Legacy:** what's left of your Legacy challenges and zone completion.
- **Tweaks:** small fixes to the stock UI and chores done for you.

Boundaries:

- SPF does not choose quests, suggest pickups or judge eligibility; AGF does.
- AGF does not order stops by travel, choose spawn spots or decide when to hearth, once SPF can; SPF does.
- AGF does not plan crafting or recipe sources; SkillUp does. AGF only says when a trainer visit fits.
- AGF does not track exploration or completion; Legacy does. AGF may use Legacy's targets as reasons.
- AGF never accepts, turns in or abandons quests; Tweaks automates that when asked.
- SPF does not draw entrances, challenges or zone levels; Tweaks and Legacy do. SPF draws travel only.
- Tweaks does not plan routes; its nearest-quest sort and quest keys follow SPF's route when there is one.
- Legacy does not navigate itself; it asks SPF, with the game's waypoint as fallback.
- None of them guides a fixed authored route; that's Polestar, and AGF and Tweaks step aside for it.

A naming note: Tweaks already uses "camp" for campsites. In player text, mob camps should be "spots", as *Next
spot* already says.

## 3. Proposed split

| Feature | Owner after | Notes |
|---|---|---|
| Order of objectives, pickups, hand-ins | SPF | from `Laps.lua`, `Routing.lua` |
| Spawn spot choice, *Next spot*, elites, caves | SPF | from `Steps.lua AreaNode`, round 6 `r6-camp` |
| Log objective → data slot matching | SPF | `OpenSlots`, `QuestieObjectives.lua`; one copy only |
| Hand-in batching, town giver arrow | SPF | `Decoration.lua` |
| When to hearth on a route | SPF | planner already models hearth; AGF's hint keeps bind advice |
| Committed order, count repaints, "you're here" | SPF | `Stabilise`, `Refresh.lua`, `Focus.lua`, `Model.Here` |
| *Route my quest log* | SPF (new) | needs QuestieDB |
| Quest selection, skips, reasons, chains, breadcrumbs | AGF | unchanged |
| Dungeon readiness, AtlasLoot | AGF | unchanged |
| Legacy zone goals in journeys | AGF (new) | reads Legacy `Targets` |
| Profession steps in journeys | AGF | reads SkillUp API; no profession maths |
| Party-shared quests, missable and expiry warnings | AGF | round 6 |
| RestedXP front-end, Polestar aside | AGF | unchanged |
| Re-planning the set (level-up, not offered, party) | AGF | sends a new set to SPF |
| *Your order* (drag) | AGF UI, SPF checks | passed as a fixed prefix; see §9 |
| No-SPF fallback order | AGF | keeps `NearestStop`, `Order` and `Travel.lua` only |
| Nearest trainer, vendor, service by travel | SPF | new `Nearest` API; SkillUp and AGF call it |
| Class trainer data | Tweaks | AGF and SPF Nearby read `Trainers()` first |
| Dungeon entrance pins | Tweaks | Legacy keeps its challenge pins on top |
| Entrance as a travel goal | SPF | `ns.Entrances` already routes to the door |
| Zone completion, exploration | Legacy | Tweaks keeps the reveal tint, stepping aside as now |
| Quest accept/turn-in automation | Tweaks | AGF stays advisory |

## 4. Duplicates across the five, one owner each

1. **Nearest trainer, vendor, service.** SPF *Nearby services* (QuestieDB NPCs), AGF `Planning/Services.lua`
   (nearest class trainer by AGF's yard cost), SkillUp `Sources.lua` (straight-line shortlist, then SPF
   `Estimate` one by one), Tweaks `Trainers()` (who teaches your class). **Keep** each addon's knowledge (Tweaks:
   who teaches; SkillUp: who sells this book; SPF: generic services). **Expose** one ranking: SPF
   `Nearest(places, limit)` ranks candidates by travel. SkillUp and AGF switch to it when present and keep their
   current code as the fallback.
2. **Dungeon entrances.** SPF `ns.Entrances` (doors for routing), Tweaks `Data/DungeonEntrances.lua` (pins and
   API), Legacy entrance pins (with challenge points), AGF (QuestieDB, then Tweaks). **Keep** Tweaks as the pin
   owner and Legacy's pin as the challenge badge it steps aside for. **Move** AGF's "Go to entrance" to send the
   instance goal to SPF, which routes to the door; its QuestieDB → Tweaks chain stays for no-SPF. Two datasets
   remain (SPF needs it without Tweaks, Tweaks without SPF); both come from client data, so I'd accept that.
3. **Exploration and zone completion.** Legacy shading and percentages, Tweaks' blue reveal tint (already steps
   aside while Legacy's shading is on), AGF's explore hint and a text link to Legacy. **Keep** Legacy as owner and
   Tweaks' reveal as a different feature. **Fix** how Tweaks knows: it reads `LegacyForeverDB.showAreas`, another
   addon's saved variable; that becomes the marker contract or a `LegacyForever.API.ShowsAreas()`. **Expose**
   Legacy's `Targets` to AGF so explore hints and zone goals come from Legacy when it's on.
4. **Shared tracker and family page.** Five copies of TrackerHost and ForeverFamily, synced from shared tooling.
   **Keep**: it's vendored code, not a feature, and each addon must work alone. New rule for the tracker: when AGF
   hands a route to SPF, AGF's section shows the journey and the current step's *why*; SPF's shows the legs.
   Neither repeats the other's stop list.
5. **Quest automation.** Tweaks accepts and turns in; AGF never does. **Keep.** Open question in §9 on whether
   Tweaks should leave alone quests AGF ruled out.
6. **Quest order in the tracker.** Tweaks' *Nearest quests first* sorts by straight distance; SPF's quest route
   will have a real order. **Expose**: while an SPF quest route runs, Tweaks sorts by its order
   (`QuestRoute()`), and its *Use the nearest quest item* and *Target a creature* keys follow the current stop.
   Without one, nothing changes.
7. **Professions.** AGF profession hints and trainer reminders, SkillUp routes. **Keep** SkillUp as owner. AGF
   adds SkillUp's next step as a journey goal when you'll pass it, with SkillUp's reason, and drops its own rank
   reasoning where SkillUp answers.
8. **Map overlays.** SPF transport pins and route, AGF rings and givers (opt-in), Legacy challenges, Tweaks
   entrances, each with its own step-aside list. **Move** step-aside to round 6's shared marker contract (in shared
   tooling, like TrackerHost): each addon registers what it draws per place type, and one owner per type wins:
   SPF transport, Tweaks entrances, Legacy challenges, AGF route marks.
9. **Navigate fallbacks.** Legacy, Tweaks and SkillUp each have SPF → TomTom → waypoint. **Keep**; it's small.
10. **QuestieDB readers.** AGF reads the whole catalogue; SPF, Tweaks, Legacy and SkillUp read slices. **Keep**
    separate, but SPF's quest route reads only the log's quests on demand, never a fifth full catalogue.

No feature disappears: every move above keeps the old path as the fallback when the other addon is absent.

## 5. Integration map

| From → to | What flows | Today | Proposed |
|---|---|---|---|
| AGF → SPF | travel line, route | `EstimateDetail`, `NavigateRoute`, `Navigate`, `CurrentStop`, `Cancel`, `Subscribe` | + `RouteQuests`, `QuestRoute`, `NextSpot`, `Nearest` |
| SPF → AGF | suggestions in quest menus, RXP owner | `Suggestions`, `StartSuggestion`, `RestedXPIntegrated` | unchanged |
| AGF → Tweaks | class trainers, entrances | `Trainers`, `TrainableSpells`, `DungeonEntrance` | unchanged |
| AGF → SkillUp | professions tab | `Professions`, `OpenRecipes` | + next step as a goal |
| AGF → Legacy | zone completion | family text link only | `ZoneSummary`, `Targets`, `Subscribe` |
| Legacy → AGF | zone tooltip suggestion | addon folder check | unchanged |
| Legacy → SPF | send to objective | `Navigate` | unchanged |
| SkillUp → SPF | nearest NPC, send | `Estimate` loop, `Navigate` | `Nearest`, `Navigate` |
| Tweaks → SPF | send to entrance | `Navigate` | + `QuestRoute` for tracker sort and keys |
| Tweaks → Legacy | reveal steps aside, pin cover | reads `LegacyForeverDB`, pin template | marker contract |
| Tweaks → AGF | window placement | `AdventureGuideForever.EnsureWindow` event | unchanged |
| All ↔ all | tracker slots, family page | vendored TrackerHost, ForeverFamily | + vendored marker contract |
| Polestar → SPF | hand-off | `NavigateRoute` (1 stop), `Active`, `Ended`, `Cancel`, `Subscribe` | unchanged, pinned by contract spec |

## 6. SPF "Route my quest log"

**Inputs.** The live log (`C_QuestLog`: quests, complete flags, objective counts) and, from QuestieDB, for those
quests only: objective spawns (creatures, objects, item drops) with mob levels, hand-in NPC or object spawns, and
givers when a goal asks for a pickup. Native POIs (`GetNextWaypoint`, quest POIs) fill gaps, as
`Planner.QuestDestination` does now. QuestieDB stays optional: without it the entry points are hidden, not greyed,
and `CanRouteQuests()` says why.

**Ordering.**

1. Tasks: each open objective with its candidate spots (spawn clusters, medoid, radius, mob level, elite and cave
   flags from round 6); each quest's hand-in, after all its objectives; pickups only when a caller sends them.
2. Visits: objectives whose spots overlap on one map merge, as `MergeLapVisits` does now.
3. Costs: SPF's own travel seconds between visit points, from the estimate's planner (no endpoint searches),
   level-aware walks, hostile towns and route style from round 6, cave arrival at the mouth. Work time per visit
   from objective counts, scaled by level like AGF's `WorkFactor`. The matrix is built across frames on the
   existing job scheduler, inside the 3 ms frame budget.
4. Solve: precedence-constrained ordering with spot choice. Nearest insertion, then 2-opt and or-opt moves that keep
   pickup → objectives → hand-in and log capacity. Each objective takes the spot that adds least, with a penalty for
   mobs 3+ above you and for elites unless grouped. Hand-ins in one town batch; a hand-in waits when a later visit
   passes its town anyway.
5. Hearth: one hearth edge per cooldown, from anywhere to the bind point, priced as the planner prices it now. The
   route says "Hearth to Lakeshire" where it saves time and *Use hearth and teleports* is on.
6. Stability: AGF's committed-order rule moves over: the new order replaces the old only when it saves a set share
   and a set number of seconds. Count ticks repaint without a plan (`LogShape`).

Output is the same journey `NavigateRoute` drives: numbered stops, badges, held objective areas with `radius`,
`shapes` and `questIDs`, the gold area, *Next spot* on the stop's menu.

**Entry points.** The SPF tracker header menu, the quest log title menu and objective tracker menu (next to *Plan
journey*), the world map tracking menu, and `/path quests` (`/path quests stop`). Menus only; map drawing stays on
the gamepad-safe canvas.

**Settings** (Guidance, under *Quest log route*): include hand-ins of finished quests (on); hearth when it saves
time (uses the existing setting); avoid spots this many levels above me (3); avoid elites unless grouped (on);
stops shown ahead (10, at most 64). A right-click *Leave out of route* on a stop lasts the session. *Keep journeys
after a reload* also restarts a quest route (`Journey/Resume.lua`).

**Without AGF.** Everything above works on its own. SPF routes exactly what is in the log and never suggests a
pickup. With AGF running a journey, the menu entry reads *Route my quest log instead* and replaces it the normal way
(`Ended` says `"replaced"` to AGF).

## 7. New SPF API for AGF

`version` stays 1, `minor` goes to 2. Nothing existing changes meaning.

- `CanRouteQuests()` → `true`, or `false` and `"noquestiedb"`, `"loading"` or `"disabled"`.
- `RouteQuests(owner, request, options)` → boolean, reason. `request` is `{questIDs = {...}}` or
  `{questIDs = {...}, goals = {...}}`. A goal is `{key, kind, map, x, y, title?, tooltip?, radius?, shapes?,
  questID?, after?}`, `kind` being `"pickup"`, `"visit"`, `"trainer"` and the existing stop kinds, `after` a list of
  goal keys or quest IDs it must follow (a breadcrumb's next pickup after its hand-in). Log quests go by ID, so SPF
  resolves their objectives and AGF keeps no copy of that code. `options`: `prefix` (goal keys or quest IDs to keep
  first, in order, for *Your order*), `hearth`, `maxStops`.
- `QuestRoute(owner)` → fresh `{status = "planning"|"ready", seconds, stops = {{key, kind, questIDs, map, x, y,
  seconds}}}` or `nil`. `CurrentStop(owner)` indexes these stops.
- `NextSpot(owner)` → boolean. Moves the current objective stop to its next spot.
- `Nearest(places, limit)` → the places ranked by travel seconds from you, each with `seconds`; sliced, cached as
  `Estimate` is.
- `Subscribe` gains one key, `plan`: the owner's ordered stops changed. Existing keys keep their meaning.

A quest route is a journey like any other: `Active`, `CurrentStop`, `Ended` (same four reasons), `Cancel` and the
`stop`, `started`, `changed`, `ended`, `active` keys answer as for `NavigateRoute`. Polestar's single-stop hand-off is
untouched. `tests/api_contract_spec.lua` gains the new functions and keeps every round 6 assertion. AGF checks
`api.minor >= 2` and each function before use.

## 8. AGF after

AGF is the part that thinks about you: your level, your log, your party, your stories, your Legacy and your
professions, and tells you what's worth doing next and why. It re-plans when those change. Polestar plays an
authored route; AGF has none and makes no fixed simulation, so the two stay apart.

It keeps selection with reasons, chains and breadcrumbs, dungeon readiness with AtlasLoot, party-shared quests,
missable and expiry warnings, RestedXP, the Polestar aside, the API (`Suggestions`, `StartSuggestion`,
`CurrentStop`, `NextStops`). It gains Legacy goals ("counts toward Explore Felwood"), SkillUp steps when you pass a
trainer, and room for things only it can do: "what gets me to the next level" from `Model.QuestXP`, a log triage
view before a long trip, group-quest finding for a party, and a dungeon readiness checklist.

Hand-off: on Start, AGF sends its card's set with `RouteQuests`, with chosen pickups as goals and *Your order* as
`prefix`. Its `CurrentStop`/`NextStops` copy `QuestRoute`. *Next spot* in AGF's menus calls `NextSpot`. When the set
changes, it sends a new request.

Without SPF, or with SPF older than minor 2: the game's waypoint and the simple order AGF already has
(`NearestStop`, `Order`, `Travel.lua`). That fallback stays for good. `Laps.lua`, `Stabilise`, the
`optimisedRoute` beta and the spot code go after the overlap.

## 9. Migration without regressions

**Release order.** Round 6 everywhere. Then SPF ships the router behind its own menu, with the API at minor 2
(SPF 1.21). AGF 0.19 switches only when `minor >= 2` and `CanRouteQuests()`; its planner stays as the fallback and
behind a hidden switch for two releases. AGF 0.21 removes it, once two SPF releases pass with no route regressions
on the *Wrong route* and *Wrong stop* forms.

**Saved variables.** AGF `customOrders` stays in AGF (sent as `prefix`). `optimisedRoute` is retired with a
changelog line; nothing to carry. `sessionCamps` is session-only. SPF adds `ShortestPathForeverDB.questRoute`
(settings) and `ShortestPathForeverCharDB.questRoute` (committed order, for resume). No secrets, no cross-addon
saved-variable reads; Tweaks stops reading `LegacyForeverDB`.

**Tests.** AGF's goldens (`tests/golden/*.txt`) split: card and selection lines stay; step order lines are mirrored
into SPF goldens built from the same fixtures plus a QuestieDB slice. For the overlap, a gate: on every fixture, SPF's
order is never more than 5% slower in travel seconds than AGF's, and never breaks precedence. Port
`order_spec`, `route_order_spec`, `next_camp_spec`, `near_first_spec` and `laps_spec` to SPF; AGF keeps
`order_spec` for the fallback. SPF bench: matrix plus solve stays under the 3 ms frame budget at 25 visits.

**Rollback.** SPF can switch the API off (`CanRouteQuests` → `"disabled"`) and AGF falls back the next rebuild,
with no AGF release. AGF's hidden switch flips its own planner back. Until removal, both paths ship.

## 10. Store and README framing

- **SPF:** "The fastest way anywhere in WoW: Forever, and the fastest order for the quests in your log."
- **AGF:** "Picks what to do next for your level, and says why. Shortest Path Forever takes you there."
- **SkillUp:** unchanged: the cheapest way to level a profession, in the Professions window.
- **Legacy:** unchanged: what's left of your Legacy challenges, on the world map.
- **Tweaks:** unchanged: small fixes to the stock UI, and chores done for you.

Cross-links: SPF's README says *Route my quest log* needs QuestieDB and that AGF chooses which quests. AGF's says
"Shortest Path orders and travels your route; without it, the game's waypoint". The family page lines change to
the one-line jobs in §2. AGF's copy keeps saying it has no fixed guide.

## 11. Decisions for the owner

1. **Does SPF resolve objectives itself, or take spots from AGF?** I'd have SPF do it, reading only the log's quests,
   so one copy of the code exists and SPF works alone.
2. **Who owns *Next spot*?** SPF; AGF's menu calls `NextSpot`.
3. ***Your order*.** Keep the drag in AGF, sent as `prefix`; SPF orders the rest. Moving the UI to SPF is cleaner but
   loses AGF's step list.
4. **Performance.** Cap the solve at 25 visits ahead and plan the rest roughly. Accept a route that settles over a
   second or two, as journeys already do.
5. **Two tracker sections.** AGF shows why, SPF shows legs, as in §4. Alternative: AGF hides its section while SPF
   leads. I'd keep both.
6. **Tweaks and AGF skips.** Should auto-accept leave alone quests AGF ruled out? I'd say no for now: automation
   stays simple, and AGF's skip means "don't suggest", not "refuse".
7. **Entrance data twice.** Accept it; both come from client data.
8. **Legacy goals default.** Off by default in AGF, a setting under Journeys.
9. **The `optimisedRoute` beta.** Retire it rather than port its heuristics; SPF's solver replaces both.
10. **SPF's identity.** Ordering your log is travel. SPF must never suggest a pickup; I'd write that into its
    AGENTS.md.

## 12. Phased plan

Effort: S under a day, M a few days, L a week or more. Arrows are cross-repo dependencies.

**Phase 0, round 6** (in flight). All five land; marker contract in shared tooling. Tweaks' entrance step-aside
moves to the contract in the same round (M) → needs SPF and Legacy canvas changes.

**Phase 1, SPF router, no UI** (parallel with phase 2's Legacy, Tweaks and SkillUp work).
1. SPF: quest task model and QuestieDB reader for log quests, slot matching ported from AGF (M).
2. SPF: cost matrix on the job scheduler, solver, hearth edge, stability (L).
3. SPF: goldens mirrored from AGF fixtures, the 5% gate, bench (M) → needs AGF fixtures exported (S, AGF).

**Phase 2, SPF UI and API** (SPF 1.21).
4. SPF: entry points, settings, resume, *Next spot* (M).
5. SPF: `CanRouteQuests`, `RouteQuests`, `QuestRoute`, `NextSpot`, `Nearest`, `plan` key, contract spec, docs (M).
6. Legacy: `ShowsAreas()` or contract registration (S). Can run any time.
7. SkillUp: use `Nearest` when present (S) → needs 5.
8. Tweaks: tracker sort and quest keys follow `QuestRoute` (S) → needs 5.

**Phase 3, AGF switches** (AGF 0.19) → needs SPF 1.21.
9. AGF: hand-off through `RouteQuests`, `NextSpot`, `prefix`, hidden fallback switch (M).
10. AGF: Legacy goals through `Targets` (M), SkillUp steps as goals (S). Parallel with 9.
11. AGF: "Go to entrance" as an SPF goal; nearest trainer through `Nearest` (S).
12. README, store copy and family lines for SPF and AGF (S each).

**Phase 4, cleanup** (AGF 0.21), after two clean SPF releases.
13. AGF: remove `Laps.lua`, `Stabilise`, spot code, `optimisedRoute`; keep the simple fallback (M).
14. AGF: goldens keep selection only (S).

Steps 1-3 and 6 can start the day round 6 merges. 7, 8, 9, 10 and 11 run in parallel once 5 ships.
