# Forever addons: release checklist, 2026-10-16

Publishing order: SPF → AGF → Tweaks → SkillUp → Legacy. Each version's full notes are its `CHANGELOG.md` entry on main, which is what the Release workflow publishes.

| Addon | Version | Release commit | Store plan (apply by hand) |
|---|---|---|---|
| Shortest Path Forever | **1.16.0** (from 1.15.0) | b1ad5bd (#182) | `scratchpad/release/shortest-path-forever-store.md` |
| Adventure Guide Forever | **0.13.0** (from 0.12.2) | b288d69 (#180) | `scratchpad/release/adventure-guide-forever-store.md` |
| Tweaks Forever | **0.12.0** (from 0.11.5) | 375d308 (#189, #190) | `scratchpad/release/tweaks-forever-store.md` (four JPEGs in `release/tweaks-gallery/`) |
| SkillUp Forever | **0.11.0** (from 0.10.0) | 13897e3 (#133, #134) | `scratchpad/release/skillup-forever-store.md` |
| Legacy Forever | **0.7.0** (from 0.6.21) | 1d32a24 (#120) | `scratchpad/release/legacy-forever-store.md` (map.png and continent.png as JPEG) |

Store paths are under `/tmp/claude-0/-home-user/76bf530e-5da5-583c-877f-df32f2ad82fa/scratchpad/`. This session has no store or browser access, so you apply the summaries, descriptions and galleries by hand.

## Changelog headlines

**SPF 1.16.0**
- Keep journeys after a reload
- `/path report`
- The arrow eases round and moves, with Shift-drag for fine placement
- The time left under the compass
- A sound when you arrive
- Flight point tooltips list their flights
- The goal stays on the minimap's edge
- See what the other faction's boats would save
- More guides' waypoints work without TomTom
- The Hearthstone works on a new install
- A journey started again to the same place no longer stalls
- Less work while you stand still
- *For addon authors:* `Subscribe` (version 1, minor 1); the TomTom stand-in answers more calls

**AGF 0.13.0**
- The guide learns when a giver doesn't have a quest
- Next spot
- Start a locked quest's chain from the search
- Search puts the best match first
- `/agf report`
- `/agf where`
- Follows Shortest Path the moment it changes
- The arrow stops flipping between nearby givers
- Level-up suggestions use your new level
- Two-kill and two-collect objectives keep the right one on the route
- No NPC tooltip errors in combat or instances
- Killing and looting for a quest costs less
- *For addon authors:* `Subscribe` (minor 1)

**Tweaks 0.12.0**
- Coordinates on the world map
- XP per hour on the experience bar
- The reward that sells for most is marked
- Quest progress on item and object tooltips
- Quest levels in dialogs
- Keys for the nearest quest item and target
- The unexplored tint on the zone map
- Rare alerts, with the map marker chime
- Party invites by sender, and duels from friends
- `/tweaks report`
- Hold Shift at a merchant
- Junk sales pay for the repair
- Summons and resurrections are accepted more carefully
- Quest automation leaves the costly quests to you
- Polestar respected
- Faster auto loot asks for each item once
- Data checked against Forever 1.60.1.70374 and Classic Era 1.15.9.70003

**SkillUp 0.11.0**
- First Aid and Cooking routes go past 150
- Herb and ore nodes show the skill they need
- `/su trainers`
- `/su report`
- No error from a vendor the game hides
- *For addon authors:* book ranks in `Professions()`

**Legacy 0.7.0**
- `/lf report`
- One error no longer stops the rest of an update
- No hitch on the map or tracker straight after login
- `/lf audit` lists unknown objectives in a stable order

## In-game `/reload` checks

Install over the previous version and `/reload` once. Each addon should print its update line once.

### Shortest Path Forever 1.16.0
1. **Keep journeys:** tick it in Guidance. A Shift-click journey comes back about 2 s after `/reload`. AGF routes come back as AGF's own, a cleared journey stays cleared, nothing starts after more than 30 min, and nothing starts with the option off.
2. **`/path report`:** text is selected; Ctrl+C copies it, Escape closes it, and it can be dragged. With `/path debug` on, it shows ride samples.
3. **Arrow:** it swings smoothly. *Move the arrow* keeps its place after a reload, and right-click resets it. *Arrow scale* 150% works. Shift-drag moves at a quarter speed. Standing still, `/path perf` shows no steady cost.
4. **Compass time:** matches the tracker, counts down at a dock, and shows the corpse run as a ghost.
5. **Arrival sound:** one ping on arrival. No sound when you clear a journey or reach AGF route stops.
6. **Flight master tooltip:** "Flights from here" with times; undiscovered points are grey.
7. **Minimap rim:** a far goal shows faded on the rim and slides onto the goal as you approach. The minimap line rests when you stand still and follows after Alt-Z.
8. **Faction hint:** Alliance, routes off, Ratchet to Booty Bay: "Through Horde transport: about N min faster", shown only when the saving is 2 min or more.
9. **TomTom stand-in (TomTom disabled):** Questie and RestedXP waypoints work. `GetClosestWaypoint`, `WaypointExists` and `ClearAllWaypoints` behave.
10. **Hearthstone landing:** `/run ShortestPathForeverCharDB.bind = nil`, hearth, then the bind is recorded. Try another continent, a dungeon exit and Astral Recall.
11. **Resent journey:** a double `NavigateRoute`, or a double Shift-click, still plans.
12. **Subscribe:** the `/run SPFSUB=…` probe prints started, changed and ended correctly; `SPFSUB()` silences it.
13. **Taint:** with `/console taintLog 1`, nothing new appears, including in combat.

### Adventure Guide Forever 0.13.0
1. **`/agf report`:** text is selected, Ctrl+C copies it, Escape closes it, and with BugSack the stack points at the failing line. `/agf where` shows the shorter version. `/agf help` lists both.
2. **Next spot:** from outside a multi-camp area, it moves the arrow and the SPF stop. It's absent inside the area (known limit, noted on #151).
3. **Missing giver quest:** one "Skipped …: the giver didn't offer it." line, and the quest leaves the route. A level-up or a hand-in there brings it back.
4. **Search:** "wolf" puts titles starting with "wolf" first, and reversed words still match. A locked row says "Starts with …", and shift-click adds that quest.
5. **Givers:** two givers close together in town don't flip the arrow. Ding next to a quest that just turned green: suggestions use the new level.
6. **Guns of Northwatch:** kill Smythe first; his area leaves and the other two stay.
7. **Tooltips:** hover NPCs, players, pets and objects in combat and instances: no Lua errors.
8. **Kill counts:** they tick with no hitch and the step order holds. Finishing an objective replans.
9. **Shortest Path:** clearing an SPF journey is noticed at once. An older SPF still works.
10. **Issue forms:** GitHub "New issue" offers Bug report, Feature request, Wrong stop and Translation.

### Tweaks Forever 0.12.0
1. **Coordinates:** player and cursor positions on the world map; only the cursor inside a dungeon; the dungeon button doesn't cover them; switching off under Maps hides them.
2. **XP per hour:** XP per hour, time to level and kills or quests to level, after about 5 min.
3. **Reward coin:** a gold coin on the highest-selling reward choice. None on a tie or a single reward, and it scrolls with the item.
4. **Quest tooltips (QuestieDB):** "n/m" on quest items and objects, and "Starts a quest: …".
5. **Quest levels in dialogs:** `[level] Title` on greeting lists and detail titles, never doubled.
6. **Keys:** both appear in Key Bindings. The item key uses the nearest quest item; the target key cycles creatures. No blocked actions in combat.
7. **Zone map reveal:** Shift+M shows the tint, and it clears as you discover areas.
8. **Rare alerts (turn on):** one line plus the map marker chime near Mother Fang. Not the raid warning or quest-reward sound. No repeat for 10 min, held through combat, one chime for two rares. **Tell me if the chime feels wrong.**
9. **Invites and duels (turn on):** friends' and guild invites accepted, but not while queued or with Shift. Strangers declined. Friends' duels still prompt.
10. **`/tweaks report`:** opens with the text selected; `/tweaks` alone still opens settings.
11. **Merchant:** Shift skips repair and junk selling. Arriving short, the repair follows once the junk sells.
12. **Summons and resurrections:** a summon in combat is accepted after combat; Shift leaves it to you; resurrection waits out the delay; Shift as you die in a battleground keeps you dead.
13. **Quest automation:** PvP-flagging quests and gold-cost hand-ins stay open for you; an item-started auto-accept closes cleanly.
14. **Auto loot:** fast-looting several corpses gives no "object is busy" errors.
15. **Polestar loaded:** matching Tweaks options grey out naming Polestar, change with it without a reload, and Polestar sells greys while Tweaks sells marked items.
16. **Atlas 1.54:** the dungeon map in Blackfathom Deeps opens with its legend.
17. **Tooltips in combat:** hover NPCs, players and a campfire: quest lines, class colours and camp lines show, with no error.
18. **General:** no Lua errors or blocked actions anywhere.

### SkillUp Forever 0.11.0
1. **Expert books:** First Aid at about 140, target 170: "Buy and read Expert First Aid - Under Wraps at 125" (1g). The vendor tooltip and waypoint work. Once you've bought it, the row says "You have it" and the total drops by 1g. Cooking shows the Expert Cookbook. Routes stop at 225.
2. **Tracker:** its first line matches the route. While you hold the book, there's no vendor waypoint.
3. **Nodes (English client, Mining about 140):** Copper "Mining 1 · grey", Iron "Mining 125 · orange until 150", Mithril red, herbs the same. No line without the skill, the setting hides it, a corpse shows "Skinning ?", and a non-English client shows nothing.
4. **Skinning rule (your decision):** a level 22 beast should be skinnable at exactly 110 and refused at 109. If so, set `CORPSE_RULE_CONFIRMED = true`.
5. **`/su trainers`:** one line per profession. After a trainer visit, the confirmed count rises.
6. **`/su report`:** text is selected and Ctrl+C copies it. With a profession open, the audit and trainer lines appear. Escape closes it, it stays under 2,000 characters, and BugSack errors are listed.
7. **Vendors:** talking to a vendor in combat or an instance gives no Lua error.
8. **Regression:** `/su audit`, native recipe colours, route and tracker updates after a craft, and trainer annotations all as before.

### Legacy Forever 0.7.0
1. **Update line:** names `/lf report`, in French on a frFR client.
2. **`/lf report`:** the window opens with the portrait and the text selected. Ctrl+C copies it, it ends with "Errors: none caught" and "Other addons (n)", Escape closes it, and it can be dragged.
3. **`/lf help` and `/lf audit`:** help lists `report` second; `/lf audit` prints the same lines as the report.
4. **Quests counted, tracker on:** `/reload` in a quest zone gives no hitch, with `?` showing briefly before the counts.
5. **Map right after `/reload`:** no hitch, and the corner fills in. A continent badge tooltip shows the zone counts and "N of M zones complete".
6. **BugSack:** nothing new in normal play.
7. **Issue forms:** GitHub "New issue" offers Bug report, Feature request, Translation and Wrong objective.

### wowaddon (no release)
After #7: Insights → Dependency graph → Dependabot shows the `bun` job succeeding.
