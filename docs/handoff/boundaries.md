# Suite boundaries: who owns what

Who does what across the WoW: Forever addons, and how to change it. This file is the single authority: an addon's
AGENTS.md says how to write code for that addon, this says which addon should own the feature at all.

**Status:** adopted by the owner 2026-10-21 ("this all makes sense to me").
**Last changed:** 2026-10-21.
**Lives at:** cjber/skills, branch `ccr-cc333990-q8ydc4-handoff`, `forever-handoff/boundaries.md`.
**Read it before:** assigning a new feature, moving code between addons, or briefing a coding agent.

## 1. One job each

| Addon | Repo | Owns | Never does |
|---|---|---|---|
| Forever Core | forever-core | The shared tracker column, grip and Lock switch, combat and Edit Mode handling, section order, the Questie bridge, and the shared visual primitives every section draws with | Any player-facing feature of its own |
| Adventure Guide | adventure-guide-forever | What to do next for your level and why: quest selection, skips, reasons, chains, journeys, breadcrumbs, zone flow, the RestedXP front-end, AtlasLoot readiness | Travel ordering, spawn spot choice, hearth timing, profession maths, accepting or turning in quests |
| Shortest Path | shortest-path-forever | Travel and the order you travel in: transport graph, walking routes, flight/boat/zeppelin/portal/ tram timing, arrival estimates, quest-log routing, nearest-something ranking | Choosing quests, judging eligibility, tracking completion, drawing entrances or challenges |
| Legacy | legacy-forever | Legacy challenges, zone completion percentages, exploration shading, dungeon and raid entrance challenge pins with done/not-done state | Navigating (it asks Shortest Path), drawing travel routes, quest selection |
| SkillUp | skillup-forever | Profession numbers: recipes, required skill, colour thresholds, skill-up chance, cheapest level path, shopping lists, trainer annotations, crafted gear | Journey selection, travel planning, other addons' UI |
| Tweaks | tweaks-forever | Small fixes to the stock client and chores done for you: quest accept and turn-in, vendors, bags, tooltips, nameplates, camp names, entrance pins | Anything specific to levelling, professions, tracking or challenges |
| Bestiary | bestiary-forever | Horizontal progression: creature cataloguing per zone, sightings, rare and variant records, zone bestiary completion, cosmetic-only rewards | Killing, looting, spawn prediction, anything the client API does not permit |
| Hoard | hoard-forever | The cross-container item index: where an item is across bags, bank, warband bank, guild bank, mail and other characters, with search over it and the public API for that question | Reagent planning or profession maths (SkillUp), bag UI fixes and vendor selling (Tweaks), lines added to Blizzard tooltips |
| Atlas | atlas-forever | The instance map viewer and index: an instance's own maps, wings and floors, entrance coordinates, and its contents as far as the client and QuestieDB place them | Completion state (Legacy), entrance pins on the world map (Tweaks), quest readiness (Adventure Guide), creature cataloguing (Bestiary), travel itself (Shortest Path) |

## 2. The boundary rules

1. Shortest Path does not choose quests, suggest pickups or judge eligibility. Adventure Guide does.
2. Adventure Guide does not order stops by travel, choose spawn spots or decide when to hearth. Shortest Path does.
3. Adventure Guide does not plan crafting or recipe sources. SkillUp does; Adventure Guide only says when a trainer visit fits.
4. Adventure Guide does not track exploration or completion. Legacy does; Adventure Guide may use Legacy's targets as reasons.
5. Adventure Guide never accepts, turns in or abandons a quest. Tweaks automates that when asked.
6. Shortest Path does not draw entrances, challenges or zone levels. Tweaks and Legacy do; Shortest Path draws travel only.
7. Tweaks does not plan routes. Its nearest-quest sort and its quest-item and target-creature keys follow Shortest Path's route when one is running.
8. Legacy does not navigate itself. It asks Shortest Path, with the game's own waypoint as the fallback.
9. No addon guides a fixed authored route. That is Polestar; Adventure Guide and Tweaks step aside for it.
10. Bestiary does not award anything that is not cosmetic, and does not duplicate Legacy's challenge tracking. Legacy may read Bestiary for a zone milestone (see §3).
11. Every addon must work alone: anything another addon provides has a fallback that works with none of the others installed.
12. Shared code is vendored from Forever Core, never re-implemented per addon (§5).

## 3. Feature to owner

| Feature | Owner | Notes |
|---|---|---|
| Quest selection, skips, reasons, chains, breadcrumbs | Adventure Guide | unchanged |
| Journey cards, zone flow auto-detection | Adventure Guide | flow detection surfaces guide cards on zone entry or a signature questline |
| Dungeon readiness, AtlasLoot lookups | Adventure Guide | unchanged |
| Profession steps inside a journey | Adventure Guide | reads SkillUp's API; no profession maths |
| Party-shared quests, missable and expiry warnings | Adventure Guide | round 6 |
| Ordering your quest log for travel (*Route my quest log*) | Shortest Path | new; needs QuestieDB |
| Spawn spot choice, *Next spot*, elites, caves | Shortest Path | from Adventure Guide's planner |
| Objective to data-slot matching | Shortest Path | one copy only |
| Hand-in batching, town giver arrow | Shortest Path | |
| When to hearth on a route | Shortest Path | Adventure Guide keeps bind advice |
| Committed order, repaint counts, "you're here" | Shortest Path | |
| Nearest trainer, vendor or service by travel | Shortest Path | one `Nearest` API; SkillUp and Adventure Guide call it |
| Fastest route to a target (rare, quest mob, vendor) | Shortest Path | hotkey drops a breadcrumb path over the existing nav packs |
| Travel timers and ETAs for long flights and boat arrivals | Shortest Path | |
| Class trainer data (who teaches your class) | Tweaks | Adventure Guide and Shortest Path read `Trainers()` first |
| Dungeon and raid entrance pins | Tweaks | Legacy keeps its challenge badge on top and steps aside |
| Quest accept and turn-in automation | Tweaks | Adventure Guide stays advisory |
| Vendor junk and repair profiles | Tweaks | whitelist and blacklist per item |
| Modular per-tweak toggles | Tweaks | every tweak a checkbox, so ElvUI and Tukui users can turn off clashes |
| Legacy challenges, zone completion, exploration shading | Legacy | |
| Dungeon and raid completion pins (cleared this lockout, all time) | Legacy | |
| Ironman and hardcore milestones, personal bests | Legacy | local only, no leaderboards |
| Zone bestiary completion, creature records, rare and variant sightings | Bestiary | Legacy may read it for a *Zone Master* style milestone |
| Profession numbers, cheapest path, shopping list export | SkillUp | export hands raw materials to work-orders-forever or a shopping list |
| Gathering node route overlays | SkillUp | asks Shortest Path to route between nodes; draws nothing itself |
| Tracker column, grip, Lock, combat hiding, section order | Forever Core | one implementation, vendored (§5) |
| Shared visual primitives (backdrop, typography, section chrome) | Forever Core | moved here from the four addons that each had a copy |
| Map marker visibility contract (one owner per place type) | Forever Core | round 6 shared tooling; each addon registers what it draws |
| Creature spawn points on a route ("hunt these on the way") | Bestiary proposes, Shortest Path routes | new (round 9). Bestiary picks the targets and prices the detour, Shortest Path orders and executes the travel; no passive overlay until the marker contract lands |
| One `Nearest` ranking by travel | Shortest Path | new (round 9). SkillUp and Adventure Guide call it; see open question 4 |
| Shopping list export and one buy trip | SkillUp | new (round 9). Export as text and through the API; Shortest Path executes the trip; work-orders-forever consumes the plain `itemID:count` format |
| Detour cost on a suggestion | Adventure Guide, quoting Shortest Path | new (round 9). Travel price only, the choice stays Adventure Guide's |
| Cross-container item search ("where is it?") | Hoard Forever | new (round 9) |
| Instance map viewer, wings and entrance coordinates | Atlas Forever | new (round 9). It asks Shortest Path to travel |

## 4. Duplicates, and the one owner each got

| Duplicate | Today | After |
|---|---|---|
| Tracker column, grip and section order | Four byte-identical copies, synced by a four-way checker | Forever Core is the source; `tools/sync_consumers.py` copies it out, `tools/check_consumers.py` gates it |
| Tracker specs | Two specs duplicated across four repos | the contract specs live in Forever Core and are vendored with the code |
| Report and issue window | Five drifting copies and five inline slash dispatchers | Forever Core owns the shared report UI, spec and command helper; all five addons vendor them |
| Forever-family link box | Five byte-identical copies, synced by hand | Forever Core owns the UI and spec; all five addons vendor them |
| Error capture for the report window | Five hand-maintained `Core/SafeCall.lua` copies | Forever Core owns the module; all five addons vendor it byte for byte |
| Nearest trainer, vendor, service | Four rankings (Shortest Path, Adventure Guide, SkillUp, Tweaks) | Shortest Path ranks; the others keep their own knowledge and call it when present |
| Dungeon entrances | Four datasets | Tweaks owns pins, Shortest Path owns the door as a travel goal, Legacy owns the challenge badge. Two datasets stay: each addon must work alone |
| Exploration and zone completion | Legacy shading, Tweaks reveal tint, Adventure Guide hint | Legacy owns it, Tweaks keeps its reveal as a different feature, Adventure Guide reads Legacy targets |
| Quest order in the tracker | Tweaks sorts by straight distance, Shortest Path will have a real order | while a Shortest Path quest route runs, Tweaks follows it |
| Profession guidance | Adventure Guide hints, SkillUp routes | SkillUp owns; Adventure Guide quotes SkillUp |
| Map overlays and step-aside lists | One list per addon | one marker contract in Forever Core: one owner per place type |

## 5. Shared code: Forever Core

Forever Core owns the code that is identical in every addon, not the features those addons draw.

- **Vendored, not linked.** All five addons carry byte-identical copies of `Core/SafeCall.lua`,
  `UI/Report.lua`, `tests/report_spec.lua`, `UI/ForeverFamily.lua` and `tests/forever_family_spec.lua`.
  Adventure Guide, Legacy, Shortest Path and SkillUp also carry byte-identical copies of
  `UI/TrackerHost.lua`, `UI/TrackerLock.lua`, `UI/TrackerOrder.lua`, `UI/TrackerQuestie.lua` and the two tracker specs.
  Every addon still works with nothing else installed, and a fix lands once.
- **One source of truth.** A shared file changes in Forever Core first. Consumers are updated by running
  `tools/sync_consumers.py`, then one PR per consumer repo. `tools/check_consumers.py` fails on any byte difference.
- **Nothing addon specific inside core.** The shared files read everything through the namespace: `ns.TrackerHostSettings`
  for the saved settings and `ns.L` for the player's language.
- **One column at runtime.** The first Forever addon to load publishes `ForeverTrackerHost`; the rest adopt it. Forever
  Core lists the five addons as `OptionalDeps` so they load first and core adopts rather than starting a second column.
- **What stays per addon:** a section's own drawing, its blocks, its strings, and its settings page. Core never learns
  what a quest, a route, a recipe or a creature is.
- The Field Guide Forever consumer list now includes `bestiary-forever` for `Core/MicroButton.lua` and its contract
  spec; it does not join `ALL_CONSUMERS` or the tracker group because it has no tracker column. Field Guide is a
  private repo, so forever-core cannot read it over unauthenticated raw: it runs its own
  `tools/check_core_shared.py` from `.github/workflows/core-shared-drift.yml` against public core main, and
  `tools/check_consumers.py` lists it as a private consumer instead of fetching it.

## 6. Integration contracts

| From to | What flows | Contract |
|---|---|---|
| Adventure Guide to Shortest Path | a chosen set, to be ordered and travelled | `NavigateRoute`, `EstimateDetail`, `Navigate`, `CurrentStop`, `Cancel`, `Subscribe`, plus `RouteQuests` and `Nearest` when they land |
| Shortest Path to Adventure Guide | suggestions in quest menus, RestedXP ownership | `Suggestions`, `StartSuggestion`, `RestedXPIntegrated` |
| Adventure Guide to Tweaks | class trainers, entrances, window placement | `Trainers`, `TrainableSpells`, `DungeonEntrance`, the `EnsureWindow` event |
| Adventure Guide to SkillUp | professions tab, next step as a goal | `Professions`, `OpenRecipes` |
| Adventure Guide to Legacy | zone completion as a reason | `ZoneSummary`, `Targets`, `Subscribe` |
| Legacy, SkillUp, Tweaks to Shortest Path | send me somewhere | `Navigate`, `Estimate`, `Nearest` |
| Tweaks to Shortest Path | tracker sort and quest keys while a route runs | `QuestRoute` |
| Everything to Forever Core | tracker sections | `ForeverTrackerHost.Attach(module)`, `IsAttached`, `OnAttachmentChanged` |
| Polestar to Shortest Path | hand-off of an authored route | `NavigateRoute` with one stop, pinned by a contract spec |

Every one of these is optional at runtime: the caller keeps a fallback that works with the other addon absent.

## 7. Naming

- Player text says "spots" for mob camps, not "camp": Tweaks already uses camp for campsites.
- Addon folders are PascalCase (`AdventureGuideForever`), repos are `-forever`, saved variables are `<Addon>DB`.
- Shared primitives are `Forever<Thing>` (`ForeverTrackerHost`, `ForeverMapMarkers`) so a reader can tell vendored
  code from feature code.

## 8. Changing these boundaries

The boundaries are meant to move as the addons iterate. To change one:

1. Say which row changes and why, in #wow-addons. A proposal is a one-line edit plus a reason.
2. The owner's call wins. A changed boundary that moves code needs the code move in the same round: the row is not true
   until the feature actually lives with its new owner, so a move and a row edit ship together or not at all.
3. Edit this file, add a row to the change log below, and add a line to `forever-handoff/ledger.md`.
4. If the change affects an addon's own docs, update that AGENTS.md in the same PR.

Rules that keep this file honest:

- One authority. If an addon's AGENTS.md and this file disagree about ownership, this file wins and the AGENTS.md is
  the bug.
- No aspirational rows. A row marked "new" is a plan, not a fact; it becomes a fact when the code lands.
- Open questions live in §9 until they are decided, and are moved, not deleted, when decided.

## 9. Open questions

1. Should Tweaks leave alone quests Adventure Guide ruled out (droppable), or automate them anyway? Today it automates.
2. Does the marker contract replace Tweaks' pin-template step-aside in the same round the pins become plain frames?
   Design note says yes; not yet scheduled.
3. Where does Bestiary's *Zone Master* style milestone live when Legacy is absent: Bestiary says it itself, or nothing?
4. Does Shortest Path's `Nearest` absorb Adventure Guide's `Planning/Services.lua` entirely, or keep it as the
   no-Shortest-Path fallback? Today: fallback.

## 10. Change log

| 2026-10-25 | Field Guide Forever (`bestiary-forever`) added to the shared micro-button consumer group with Adventure Guide; it remains outside the tracker consumer list | owner-approved micro-menu button brief |

| Date | Change | Who |
|---|---|---|
| 2026-10-21 | File created: one job per addon, twelve boundary rules, feature to owner table, duplicates resolved, Forever Core ownership and the vendoring rule, integration contracts, naming, the change process | owner approved, maintainer wrote |
| 2026-10-21 | Forever Core added as the seventh addon and the owner of the shared tracker column, grip, Lock, section order and visual primitives | maintainer, from the owner's 2026-10-21 approval |
| 2026-10-22 | Round 9: Bestiary proposes route spawns and Shortest Path routes them; `Nearest` belongs to Shortest Path; SkillUp gains the shopping export and one buy trip; Adventure Guide may quote a detour cost. All four are marked new and become fact when their round-9 PR lands | maintainer, from the owner's 2026-10-22 ask ("one task per existing enhancement") |
| 2026-10-22 | Hoard and Atlas added as the eighth and ninth addons, with their ownership rows and non-goals | maintainer, from the owner's 2026-10-22 ask ("one task for hoard forever and one for atlas forever") |
| 2026-10-24 | Report and issue UI, its contract spec, the Forever-family link box and its spec assigned to Forever Core for vendoring into all five addons | maintainer, from the owner's 2026-10-24 request to unify shared addon logic |
| 2026-10-24 | Error capture (`Core/SafeCall.lua`) assigned to Forever Core as the report window's shared dependency, vendored into all five addons | owner request to complete the shared-logic extraction |
