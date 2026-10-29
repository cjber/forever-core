# Coordinator ledger
## wowaddon (done)
- #6 -> PR #7 READY (comments only; upstream dependabot fix v0.400.0). Not merged.
- #4 -> closed completed; moved items -> SPF #161 (new bug, in-game A/B), SPF #162 (new, owner decision), AGF #161.
- Decisions closed as status quo inside #4: wow-xuu.32 Attune wrapper not planned (ARR); wow-xuu.33 Legacy quick menu toggles kept.
- Release process: none (private, v1.0.0 Unreleased, no workflow). No release.
- Post-merge check: Insights > Dependency graph > Dependabot bun job succeeds.
## SkillUp (agent 1 done; agent 2 on #121 + ports)
- #124 -> PR #125 READY (/su trainers); issue left open (trainer visits in game).
- #123 -> left open, needs in-game check (client SkillLineAbility unchanged vs Classic; classic-db 125 only source).
- #122 -> left open, needs WFA-28 waiver (classic-db gameobject_template lock + client Lock DB2) + skinning rule decision.
- Owner decisions: #122 waiver, #122 skinning before confirmation, #124 override file waiver.
- In-game (#125): /su trainers lines; visit BS/LW/Tailoring trainer -> confirmed count rises; trainer window chance/cost and route training still fine.
- Changelog (#125, already in [Unreleased]): **Check the trainer requirements SkillUp guesses with /su trainers.**
## Owner decisions 2026-10-15 ("permission to merge and do all and cut releases when happy") -> took my recommendations
- Merges: coordinator merges green+reviewed PRs. Releases: cut when happy (no pre-tag stop required now; still report).
- SkillUp #122 waiver agreed; skinning '?' until confirmed; #124 no override file (generator exceptions).
- SPF #162: build tooltip time line (a).
- wowaddon: #4 status-quo closes stand; no lockfileVersion CI check.
## Merged
- wowaddon #7 (978a5b6) closes #6
- skillup-forever #125 (4a5d141) refs #124
- skills #32 (39548c0) shared tooling: package/doctor/screens/editorconfig/secret; WFA-30, WFA-31 new
- legacy-forever #114 (4d2fed5) closes #113. In-game: tick Quests + tracker, /reload in quest zone -> no hitch, ? then count; open map right after reload -> pending then counted; only-Quests -> section stays, % ? then number; continent badge tooltip counts + "N of M zones complete"; /lf audit still prints.
- Legacy changelog (#114, in [Unreleased]): **No hitch when you open the map or the tracker draws straight after logging in with Quests counted.**
## WAITING ON AGF #156 PR -> resume: Legacy agent (ae494ec28c06d0a6e), SkillUp-2 (a93299d6d632769f7, also #121/#122), Tweaks, SPF ports
- tweaks-forever #170 (74baec0) closes #152 Polestar conflicts. In-game (with Polestar): settings greyed naming Polestar (repair, fast loot, gossip, quests, reveal, zone levels; sell junk NOT greyed); merchant: one repair, greys by Polestar, marked green by Tweaks; toggle Polestar auto repair off -> Tweaks repair available w/o reload; Polestar reveal Off -> Tweaks reveal available; quest mob after Polestar_QuestDB loaded -> quest tooltips greyed, one set of lines.
- skillup-forever #126 (a444fd2) part of #121: Expert FA/Cooking books from client DB2. #121 open for Artisan -> NEW OWNER DECISION: WFA-28 waiver classic-db quest_template RewSpell (Triage, Dirge/Clamlette) or wait for QuestieDB.
  In-game: FA 140/150 target 170 -> "Buy and read Expert First Aid - Under Wraps at 125" price 1g; hover -> "No trainer teaches this rank: a book does." + vendor waypoint; tracker matches; book in bags -> "Read ..."; Cooking -> Expert Cookbook; route stops at 225.
- tweaks-forever #171 (a5251ba) closes #153. In-game: ordinary quest accepted; PvP quest left open, NPC moves to next quest; gold-cost hand-in stays open; item-started auto-accept closes w/o error, quest once; area popup Blizzard's no error.
- tweaks #173 (#154 repair retry) needs main merge. In-game: short money + junk -> "not enough money" then "repaired for"; enough money -> one line; short no junk, close, loot money -> no repair.
- AGF #169 = #156 report window (open); AGF #167 = #145 (CI).
- SPF #164 (9c2d86b) Subscribe, part of AGF#159. API version stays 1, minor=1 (additive). In-game: /run SPFSUB=ShortestPathForever.API.Subscribe(function(c) print("SPF",c.started,c.changed,c.ended,c.stop,c.active) end); shift-click map -> true nil nil nil true; elsewhere -> nil true nil nil nil; untick/tick guidance -> active true; clear -> ended,active; AGF multi-stop reach stop -> changed,stop; SPFSUB() -> silent.
- skillup-forever #128 closes #122 (node colours; waiver in AGENTS.md; skinning ? behind CORPSE_RULE_CONFIRMED). In-game: Mining~140 Copper "Mining 1 · grey", Iron "Mining 125 · orange until 150"; Mithril "Skill range starts at 175" red; herb check; no Mining -> no line; setting off removes; SKINNING RULE: level 22 beast needs 110, refuses at 109 -> then set CORPSE_RULE_CONFIRMED=true; non-English nothing.
- skills #33 (ae183f1) ty fix + editorconfig luacheckrc/pkgmeta. Pin = ae183f1. Docs PRs pending: AGF #168, SPF #165, Tweaks #172, SkillUp #127, Legacy #115
- tweaks #173 (e7efde3) closes #154.
- tweaks #168 (gamepad crash) and #169 (AH decide) commented, left open. Tweaks #174 = report port (held for AGF #169 fixes).
- Legacy #116 (/lf report port) + #117 (wrong_objective form + translation form) HELD for AGF #169 fixes. Merge #116 before #117.
  In-game #116: /lf report window w/ icon, text selected; Ctrl+C paste has version/build, Character, Place, audit, "Errors: none caught", Other addons; typing doesn't change, Esc closes, reuse window; /lf audit same; /lf help lists report; BugSack quiet.
  Changelog: **`/lf report` gives you something to paste into a bug report.**
- Coordinator calls: Legacy form uses `bug` label; added translation form.
- skills #34 (ceffa4d) rename secret->readable (gitleaks). Pin = ceffa4d.
- AGF #168 docs (eea6237) merged. SPF #165 / Tweaks #172 / SkillUp #127 / Legacy #115 updated-branch, awaiting CI.
- NOTE: branch protection strict (up-to-date required).
- docs merged: SPF #165 (172fa47), Tweaks #172 (2899d8d), SkillUp #127 (0a18a48), Legacy #115 (8393ff4). Parts of AGF #162/#163/#165 done in all 5.
- legacy #116 (37029b5) /lf report merged. #117 updating.
- tweaks #174 (3f94f25) /tweaks report merged. In-game: /tweaks report window, Differs from default / Standing down for / Missing an addon / Errors / Other addons; Esc; /tweaks opens settings; BugSack stack points at Tweaks file.
- tweaks #175 (#157 best reward), #176 (#156 summon/res guards), #177 (AGF#157 form) queued.
- tweaks #175 (26f5dc9) closes Tweaks #157 best reward coin (on by default, marks only; Polestar qol.rewardHighlight conflict). In-game: coin on highest sell-price choice; tie/single -> none; quest log none; scroll clips; toggle off hides.
- skillup #130 (6f1090f) screenshot harness fix (post-calls by type). #131 /su report port pending.
- legacy #117 (13c135f) issue forms merged. Legacy: all issues done (#113), ports done. After merge: issue chooser shows Bug report, Translation, Wrong objective, no blank.
- SPF sync #168 (5053ab8) forever_tools ceffa4d + package job. Pending syncs: SkillUp #129, Tweaks #179, Legacy #118, AGF tbd.
- tweaks #176 (356913a) Tweaks #156 summon/res/bg-release guards. Queue: #177 forms, #178 (#155 social), sync #179.
- skillup #131 (fdea9d3) /su report merged. #132 forms pending. Legacy #119 (feature_request.yml restore) opened by coordinator.
- AGF #169 (fc2ba5c) report window merged (AGF part of #156). #167 (#145) next.
- syncs merged: Tweaks #179 (a3c67c6), Legacy #118 (8fbc13f). Pending: SkillUp #129, AGF #171. Legacy #119 updated.
- skillup #132 (8186f5a) wrong-number + org forms merged. SkillUp agent done except owner/in-game blocked.
## SkillUp FINAL: #122 closed (#128); #121 open (Artisan waiver decision); #123 open (in-game); #124 open (trainer visits); ports #131/#132 merged; #125,#126,#130 merged.
  In-game /su report: window w/ versions, character, settings, providers, per-profession route; Audit + Trainers lines with profession open; Esc; <2000 chars; BugSack errors listed.
- legacy #119 (12df42a) feature_request.yml restored. Legacy fully merged.
- skillup sync #129 (c3bd029) merged. SkillUp fully merged. AGF sync #171 pending.
- tweaks #177 (ccb7afb) issue forms merged. #178 (#155 social, all off by default; guild-invite decline skipped: game has Block Guild Invites) updating. #180 (#166) pending.
  In-game #178: duel except friends/guild; accept party invites from friends (Shift keeps popup; bg queue keeps popup); decline strangers.
- tweaks #178 (e786921) closes #155.
- AGF #170 (d3ef394) closes #146 (objectives by name).
- tweaks #180 (ebaf49e) closes #166 quest levels in dialogs. Next #181 (#160 map coords), #182 (#158 tooltips).
- SPF #163 (ef8a2fe) closes #147 hearth bind point from landing. Pending: #167 (fixes SPF #166 double-submit), #169 (#148 restore journey), #170 (/path report).
- tweaks #181 (2dd1ecb) closes #160 map coords. Next #182 (#158), #183 (#161).
- AGF #167 (a4ee0c9) closes #145 secret GUIDs/forbidden tooltips (ns.Readable). Both AGF bugs done.
- tweaks #182 (e80ef8b) closes #158 item/object tooltips. Next #183 (#161), #184 (#163).
- tweaks #183 (7c046d3) closes #161 loot debounce. Next #184 (#163), #185 (#162).
- tweaks #184 (1bdf6a6) closes #163 Shift at merchants. Next #185 (#162), #186 (#165 rare alerts).
- AGF sync #171 (1a48ac9) merged. All 5 addons synced to skills ceffa4d.
- tweaks #185 (57bff05) closes #162 zone map reveal. Next #186 (#165), #187 (#167).
- CLOSED umbrella AGF #158 #160 #161 #162 #163 #165 with PR list comments.
- Tooling FINAL decisions for owner: (1) AGF screenshot check vs data refresh (AGF dumps from tests/scenes.lua, re-render needs AtlasLoot locally) -> accept / exempt data/refresh / loosen; (2) add `package` job to required checks per repo ruleset; (3) unverified scenes.sha256 baselines AGF/SPF/Tweaks need local re-render.
  Tooling in-game: Tweaks: in combat hover NPCs/players/campfire, quest lines, class colours, camp lines, minimap quest giver tooltip, nameplate icons, no error. SkillUp: vendor in combat/instance no error; reagent/node/corpse lines show.
  SkillUp changelog: **No error from a vendor the game hides.**
- SPF #167 (29b3156) closes SPF #166 double-submit no-plan.
- tweaks #186 (4c2bdec) closes #165 rare alerts (off by default; no data). Next #187 (#167), #188 (#159).
- SPF #171 (68277c7) wrong-route + translation + org forms (part AGF#157).
- tweaks #187 (db14db0) closes #167 XP/hr. Next #188 (#159).
- tweaks #188 (8b78a34) closes #159 quest item/target keys (default on, inert until bound).
## Tweaks FINAL: all merged (#170-#188). Open: #164 (in-game measure + spirit healer data maybe waiver), #168 (needs crash log/repro), #169 (owner decision AH).
  Decisions: #188 default on (inert until bound); display features on by default (#175,#180,#181,#187); Nova Rares folder `NovaRares` unverified.
  Narrowed: #166 gossip list skipped (Blizzard mixin hook forbidden); #155 guild-invite decline skipped.
  In-game list: see Tweaks agent report (Polestar, quests, repair, report, reward coin, summons/res/bg, forms, social, quest levels, coords, tooltips, loot, Shift merchant, zone map, rare alerts, XP/hr, keys).
## SPF status 19:50: #170 (c68f09f) and #169 (1beef55) CI running; #172 (#162) needs refresh; next arrival sound #155.
- SPF #153 closed not_planned (driver already replans on speed change, Journey.lua:485-491).
- SPF owner decisions: #143 Polestar credit/bundling/dependency; #144 take Fitz's branch vs write our own; #151 extend AreaTrigger WFA-28 waiver to instance entrances; #154 observation importer data file + waiver.
- SPF blocked in-game: #158 controller taint, #161 map filter crash, #159 TomTom checklist, #103 in-game verification item.
## AGF status 19:50: #172 (#150), #173 (#148+#149), #174 (#157+#164), #175 (#159 AGF, SPF_SHA 9c2d86b) CI running. Next PRs: #147, #151 (camp half), #154; #153 after #172.
- AGF open with blockers: #152 (drop rates need WFA-28 waiver), #166 (login measurement; steps posted).
- AGF PROPOSED CLOSE (owner): #155 live quest XP (only affects new pickups; client gives XP only for logged quests; needs quest-log selection).
- AGF #151: service half ("another NPC" trainers) maybe close on camp half -> owner.
- SPF #170 (fa16e9e) /path report merged (SPF part #156). AGF #172 (99e5aef) closes #150. AGF #173 conflicts -> agent.
- SPF #169 (676a0c2) closes #148 keep journey across reload (off by default). Queue: #172 (#162), #173 (#155 sound), #174 (#156 compass time).
- [restart ~20:30] AGF #173 merged (closes #148,#149). Resumed AGF + SPF agents.
- SPF #172 (f244091) closes #162 faction saving line (2-min threshold).
- AGF #174 (9e68f33) forms + /agf where + tests/README (AGF part #164). Closed AGF #157 umbrella. #164 waits on SPF part.
- SPF #173 (85e456f) closes #155 arrival sound (off by default).
- SPF #174 (006f341) closes #156 compass time (off by default). AGF #164 closed by AGF #174 already; SPF part = SPF #176.
- AGF #175 (3f40032) AGF Subscribe + SPF follow; closed AGF #159. In-game: clear SPF journey -> guide notices (Go back) w/o waypoint move; last stop then new stop sent once; older SPF still works.
- SPF #175 (77ce214) closes #150 flight point tooltips.
- AGF #176 (cf0a4a0) closes #147 giver window offers. Next #177 (#153), #178 (part #151), #179 (#154).
- SPF #176 (fbf9423) tests/README + Ways to help (SPF part AGF#164).
- AGF #177 (92cb132) closes #153 shift-click locked search row.
- SPF #177 (7c1d5f0) closes #149 + #160 arrow easing, Shift-drag fine placing; stops arrow idle OnUpdate (#152 partial?).
- AGF #178 (bc28a15) part #151 Next spot (camp half). #151 open for owner (trainer half).
- AGF #179 (19fe228) closes #154 count-only cheap refresh. AGF agent done.
## AGF FINAL: merged #167 #169 #170 #172-#179. Open: #151 (trainer half, owner), #152 (drop-rate waiver), #155 (proposed close), #166 (login measurement).
  AGF in-game list (10 items) in AGF final report; authors note: AdventureGuideForever.API.Subscribe minor=1.
  Note: AGF screenshot baseline verified via AtlasLoot data.lua fetched; byte-identical.
- SPF #178 (9377981) TomTom stand-in gaps (part SPF #159; open for in-game checklist).
## RELEASE PREP launched ~21:5x: Tweaks (aef4e8d, last v0.11.5), SkillUp (ab8c535, v0.10.0), Legacy (a4d4443, v0.6.21), AGF (a2c0de2, v0.12.2). SPF (v1.15.0) after SPF agent finishes. Tag order SPF, AGF, Tweaks, SkillUp, Legacy. Release = workflow_dispatch(version) on main after ci.yml push run green.
- RELEASE Legacy #120 merged (1d32a24) v0.7.0. Dispatch Release version=0.7.0 after ci.yml push green; tag order last.
  Legacy release in-game: install over 0.6.21, update line names /lf report (frFR too); /lf report window; /lf help; Quests+tracker reload no hitch; map right after reload; continent badge; BugSack quiet.
  Store plan: scratchpad/release/legacy-forever-store.md (map.png/continent.png >2MB -> JPEG q90).
- SPF #179 (3e3e174) closes #152 minimap route rests.
- skillup #134 (64c45a3) fix: no charge/vendor for held Expert book. #133 (v0.11.0 prep) updated from main, merge next. WHATS_NEW 'First Aid and Cooking routes go past 150.'
  SkillUp release checklist (8 items) in SkillUp release agent report; store plan scratchpad/release/skillup-forever-store.md (8 gallery imgs, replace 7).
- SPF #180 (97c49db) closes #157 minimap rim goal.
- RELEASE SkillUp #133 merged (13897e3) v0.11.0.
- RELEASE Tweaks #189 merged (8762d54) v0.12.0. Notes: scratchpad/tweaks-0.12.0-notes.md. Atlas fetched from WoWInterface pinned sha256.
  Tweaks release: rare alerts SOUNDKIT.RAID_WARNING violates WFA-26 -> fix PR requested before tag. Tweaks checklist 18 items in release agent report. Store plan scratchpad/release/tweaks-forever-store.md (4 JPEGs in tweaks-gallery/). Missing gallery images for XP/hr, coin, report, levels, tooltips (follow-up).
  Classic Era pins moved to 1.15.9.70003, classic-db ec4f596 (rows identical).
- SPF #181 (05569eb) changelog For addon authors move. SPF work done; release prep next.
## SPF FINAL: merged #163-#181; #153 closed not_planned; SPF #159 auto-closed by #178 -> REOPENED for live checklist. Open: #103, #143, #144, #151, #154, #158, #159, #161.
  SPF in-game list (12 items) in SPF final report. SPF release prep agent launched.
- tweaks #190 (375d308) WFA-26 fix: rare alert chime = file 893809 ui_vignette_mapping_01.ogg (no rare-specific sound exists). Owner: check chime in game. Tweaks 0.12.0 ready.
- RELEASE AGF #180 merged v0.13.0 (dated 2026-10-16). Notes scratchpad/release/agf-0.13.0-notes.md. #151 comment: Next spot hidden inside area (follow-up).
  AGF release checklist 12 items in AGF release agent report; store plan scratchpad/release/adventure-guide-forever-store.md (gallery demo,panel,map,tracker,restedxp,loot,search).
- PUBLISH SPF 1.16.0 dispatched 00:40 (ci green b1ad5bd). Verifier resumed.
- SPF 1.16.0 PUBLISHED: run https://github.com/cjber/shortest-path-forever/actions/runs/38830754015 ; release https://github.com/cjber/shortest-path-forever/releases/tag/v1.16.0 ; Wago live https://addons.wago.io/addons/shortest-path-forever/versions ; CurseForge upload ok (project 1708599) public page pending moderation. Tag lightweight (workflow), not signed annotated.
- PUBLISH AGF 0.13.0 dispatched ~00:45 (ci green b288d69). Verifier resumed.
- AGF 0.13.0 PUBLISHED: run https://github.com/cjber/adventure-guide-forever/actions/runs/38830958535 ; release https://github.com/cjber/adventure-guide-forever/releases/tag/v0.13.0 ; CF https://www.curseforge.com/wow/addons/adventure-guide-forever/files/9202451 ; Wago https://addons.wago.io/addons/adventure-guide-forever/versions
- PUBLISH Tweaks 0.12.0 dispatched (ci green 375d308).
- Tweaks 0.12.0 PUBLISHED: run https://github.com/cjber/tweaks-forever/actions/runs/38831696914 ; release https://github.com/cjber/tweaks-forever/releases/tag/v0.12.0 ; Wago live https://addons.wago.io/addons/ZKxOWd6k ; CF upload ok, public pending (author console https://authors.curseforge.com/#/projects/1708506/files).
- PUBLISH SkillUp 0.11.0 dispatched (ci green 13897e3).
- SkillUp 0.11.0 PUBLISHED: run https://github.com/cjber/skillup-forever/actions/runs/38831889979 ; release https://github.com/cjber/skillup-forever/releases/tag/v0.11.0 ; Wago live https://addons.wago.io/addons/skillup-forever/versions ; CF upload ok, public pending.
- PUBLISH Legacy 0.7.0 dispatched (ci green 1d32a24).
- Legacy 0.7.0 PUBLISHED: run https://github.com/cjber/legacy-forever/actions/runs/38832056439 ; release https://github.com/cjber/legacy-forever/releases/tag/v0.7.0 ; CF file 9202495 live; Wago live.
## ROUND 2 (owner delegated all decisions 2026-10-16): decisions + CF comment triage in scratchpad/round2.md. Agents: SPF aa6087d, SkillUp aa213f7, Tweaks a36a24c, AGF adbd838. Wago comments unreadable (redirect). Legacy: no CF comments, no round-2 work.
## PATCH 1.60.1.70425 (wago 2026-10-16 00:50). refresh-data.yml dispatched in all 5 repos ~03:30. Agents told; Legacy round-2 agent a4408c7 launched for data + 0.7.1.
- Legacy #121 (data 70425): approved pull_request run 38844905841 via rerun; merge when green.
- SkillUp #135 data 70425: 9 new crafts, Tinkerbox removed, Greater Mender scroll moved, 72 prices, Shoulder->Shoulders. Approved run 38844953599; merge when green.
- Legacy #121 merged (1badc4d) data 70425. Approved bot runs: AGF #181 (38845783475), SPF #183 (38845360136). Tweaks data is agent PR #192. Merges wait for agents' READY review.
- TrackerHost shared fix: SkillUp #137 = source (unclamp/re-anchor bug, CF report). Port byte-identical to SPF, AGF, Legacy after merge (Tweaks has none). Releases wait for it.
- SkillUp #135 merged (4f638c3) data 70425.
- SPF #184 merged: Moonglade regression spec (fixed in 1.15.0 #139; reporter likely pre-1.15). Compass background may already exist (1.15.0).
- tweaks #191 (6356b67) closes #169 AH column removed + lint rule. #194 gamepad mitigation (part #168) needs main merge. #164 closed not_planned. #192 data pending.
- skillup #137 (a66df30) TrackerHost shared fix merged; port requested SPF/AGF/Legacy. tweaks #194 (f88898e) gamepad mitigation (part #168).
- tweaks #192 (b1dbf1d) data 70425 (gen_camp tent fix, 4 ForeverQuests). Tweaks -> release prep 0.12.1.
- skillup #138 (bb2a8a6) closes #123 Bronze Warhammer 110 (SEEN_REQUIREMENTS cap). Next #121 Artisan; confirm misclick + AH price.
- SPF #183 (50f52dc) data 70425 (2 taxi timings). SPF to bump shared tracker UI REVISION 69913->70425 after #185; then AGF/SkillUp/Legacy pin same.
- legacy #122 merged (TrackerHost a66df30). Review found combat early-return bugs (a,b,c) -> SPF fixes in TrackerHost + UI REVISION 70425; then final file byte-identical to AGF/SkillUp/Legacy; releases wait.
- RELEASE Tweaks #195 merged v0.12.1 (AH removal, gamepad mitigation, data 70425). #193 closed. Tweaks independent of TrackerHost -> publish after ci.yml push green.
- PUBLISH Tweaks 0.12.1 dispatched 04:13 (ci green 8a25c58).
- SPF #185 merged TrackerHost port (f7f8f291). UI-pin + combat fixes PR next.
- AGF #181 (8e4580d) data 70425 (2 AreaTable IDs). All 5 repos now on 70425 data.
- skillup #139 merged closes #121 Artisan (quest_template waiver). SkillUp release waits for final TrackerHost.
- Tweaks 0.12.1 PUBLISHED: run https://github.com/cjber/tweaks-forever/actions/runs/38849487077 ; release https://github.com/cjber/tweaks-forever/releases/tag/v0.12.1 ; CF file 9203672 live ; Wago live. #168 open (A/B). Follow-ups: tent in camp buff tooltip; move data-table taint rule into shared forever_tools.
- SPF #186 merged (60300a7): FINAL TrackerHost f8d56a4e + UI REVISION b401e03 (70425). Port spec in scratchpad/trackerhost-final.md. SPF area.png/minimap.png changed at release.
- skillup #140 merged final TrackerHost port. SkillUp -> release prep 0.12.0.
- legacy #124 merged final TrackerHost. Combat edge findings 1-5 filed as SPF issue (follow-up, not blocking). Legacy -> #123 0.7.1 READY next.
- RELEASE Legacy #123 merged v0.7.1 (TrackerHost final, data 70425). Publish after CI.
- SkillUp #141 (0.12.0 prep) HELD: decided retire Tinkerbox recipes (output + teaching item gone in 70425) via generator rule before release.
- PUBLISH Legacy 0.7.1 dispatched 05:05 (ci green e505c46).
- Legacy 0.7.1 PUBLISHED: run https://github.com/cjber/legacy-forever/actions/runs/38853967330 ; release https://github.com/cjber/legacy-forever/releases/tag/v0.7.1 ; CF 9203962 approved ; Wago live. (zip CRLF; TrackerHost matches after CR strip)
- SPF #187 merged closes #144 (own fix). #189 #151: approved Map DB2 corpse points for 20 dungeons (+AreaTrigger raids). #143 closed completed, #154 not_planned.
- RELEASE SkillUp #141 merged v0.12.0 (Tinkerbox retired via explicit RETIRED list + check_retired; literal rule would drop ~100 live recipes).
- PUBLISH SkillUp 0.12.0 dispatched 05:30 (ci green 578d31f).
- SkillUp 0.12.0 PUBLISHED: run https://github.com/cjber/skillup-forever/actions/runs/38856108120 ; release https://github.com/cjber/skillup-forever/releases/tag/v0.12.0 ; CF 9204147 approved ; Wago live.
- SPF #189 merged closes #151 instance entrances (26 doors, Map corpse point + AreaTrigger Naxx). Queue #190 nudge, #191 attach menu, #158.
- AGF #184 merged final TrackerHost (all 4 repos now f8d56a4e on main). Queue #182 #183 #185.
- SPF #190 merged arrow-key nudge. #191 next, then #158.
- SPF #191 merged attach-to-tracker menu. #192 gamepad mitigation (part #158) pending; then 1.17.0 prep.
## NEXT AFTER ROUND 2: owner asked (no code) for a full PLAN to improve visibility of addons, esp AGF; cross-linking & encouraging usage in-addon and on pages; may rethink some. Deliver after AGF+SPF releases done.
- AGF #182 merged closes #151 Next spot inside area. Queue #183 #185.
- SPF #192 merged gamepad mitigation (part #158). SPF -> 1.17.0 release PR.
- RELEASE SPF #193 merged v1.17.0.
- AGF #183 merged (screenshot stale = warning on data/refresh only). #185 next.
- PUBLISH SPF 1.17.0 dispatched 07:16 (ci green 431c587).
- NEW CF request (SkillUp): AH search mats for N crafts. SkillUp agent resumed to check/build + release.
- SPF 1.17.0 PUBLISHED: run https://github.com/cjber/shortest-path-forever/actions/runs/38866127580 ; release v1.17.0 ; Wago live ; CF pending moderation.
- 2026-10-16: SkillUp #143 (closes #142), #145 merged; v0.13.0 released (716df27, CurseForge 9204861 approved, Wago stable).
- 2026-10-16: AGF #185 (closes #152), #186 merged; v0.14.0 released (59075dfc; Wago listed; CurseForge pending moderation). #187 next for 0.14.1. SPF #194 OpenMap tracking issue filed.
- 2026-10-16 OWNER CORRECTION: SPF #143 — Fitz/Polestar may take SPF's code directly (owner clarified on GitHub). Our 'API only, no copying' comment was wrong. Don't comment on it again.
- OWNER CHECKLIST (round 3): add to cjber/.github/.github/PULL_REQUEST_TEMPLATE.md: "- [ ] A reporter or requester is credited in the changelog bullet and THIRD_PARTY.md (WFA-33)" (session has no push to cjber/.github). Strip <!-- forever-family --> marker lines when pasting store copy. Wago comments not readable: owner skims for names. CurseForge Relations + Wago deps (SPF optional). GitHub topics + pinned repos. Discord invite if wanted. Optional: purge QuestieDB corpus from AGF git history (force-push).
- 2026-10-16: Legacy v0.8.0 released (2a507ce).
- 2026-10-16: SkillUp v0.14.0 released (058843f; Wago live, CF pending moderation).
- 2026-10-16: Tweaks v0.13.0 released (7ad2585; Wago live, CF pending).
- 2026-10-16: SPF v1.18.0 released (c2dedd3; Wago live, CF pending).
- 2026-10-16: Tweaks v0.13.1 released (394533b; #202 Mouchoir login fix).
- 2026-10-16: AGF v0.15.0 released (de3d35f; Wago live, CF pending).
- 2026-10-16: Tweaks v0.14.0 released (178e107, translations).
- 2026-10-16: Legacy v0.9.0 released (2589eae, translations).
- 2026-10-16: SkillUp v0.15.0 released (5ff9bfe, translations).
- 2026-10-16: SPF v1.19.0 released (a7cace7, translations).
- 2026-10-16: AGF v0.16.0 released (f68e2a2, translations; CF approved file 9212012).
- 2026-10-17: AGF v0.17.0 released (77a3752; Polestar step-aside).
- 2026-10-17 OWNER APPROVED design-agf-spf-split.md (round 7 after round 6 + bug sweep). CF comments: old fetch read page 1 only (API pages via page=N, ignores pageIndex) -> SPF 09-30..10-08 comments missed. New watch/cfwatch.py (all pages+replies, seen.json). Audit agent launched. Scheduled task trig_01SxgDS5iHDEnSH5rtTwtWTx every 3h. overspark posted on Tweaks page (Tweaks already has dungeonEntrances setting).
- 2026-10-17 Owner: my 3-hourly comment task DELETED (Nebula job does it, prompt /home/user/nebula-comment-watch.md). How to read CF comments: GET https://www.curseforge.com/api/v1/mods/<id>/comments?page=N&pageSize=20 (page from 0; pageIndex ignored; max 20; replies nested; credit displayName). IDs SPF 1708599 AGF 1711538 SU 1705762 LF 1708506 TW 1705879. Script watch/cfwatch.py. Still run it before every release.
- 2026-10-17 ~16:00 2nd restart. PARALLEL SESSION (branches fix/*, feat/*, release/*) merged+released: SkillUp #164-167 v0.16.0; Legacy #140 entrance switch v0.10.0; SPF #215 Questie tracker + v1.19.2 (#216). Open: AGF #209, Legacy #143, SkillUp #169 (tracker, -signed). Our bug agents for SkillUp/Legacy/tracker NOT resumed (redundant). Tracker background (AGF #203, Naburiel) still unbuilt -> ask owner.
- Owner: the parallel session is THEIRS. Focus on ours; WATCH theirs (posture: watching; report to owner, never comment on their PRs). Subscribed AGF #209, Legacy #143, SkillUp #169. Tracker background #203 left to them. Watch for new PRs from their branches (fix/ feat/ release/) on each check.
- SPF #217 (S3 Polestar/TomTom compat) merged 42bf0f9. Decision (mine): SPF takes TomTom global from Polestar's shim only when SPF's own 'Let guides set TomTom waypoints' is on; gives it back when off — OK.
- SkillUp #170 credits (SilentGentlemanSG; name casing) merged b4ca8af. forever_sim acceptance: red on SU v0.15.0 with exact syrberus error, green on main.
- SPF #218 (S2 gamepad-safe map, part of #158) merged 8cf8313. Decision: gamepad A-click on SPF pins dropped (tooltips follow cursor) — accepted. H told to port Tweaks DungeonEntrances to ForeverMapMarkers.
- AGF #211 (A3 party quests) merged 1b08abf.
- SPF #219 (S1a+c level/faction hazards) merged 8d7f2f0. Decisions: waiver OK; displayed times must be REAL (hazard only for choice) + exempt short transport connector walks -> follow-up PR by A. S1b (route styles, needs owner local bake + road textures) and S1d (caves by subzone, needs wago terrain source) DEFERRED, owner later. A does SPF 1.20.0 prep after follow-up.
- 2026-10-18 USAGE LIMIT (resets 2026-10-22 10:00 UTC). All agents stopped. Unfinished work pushed as <branch>-wip: AGF quest-safety/group-lines/expiring/camp/overlay-pins; Legacy+Tweaks gamepad-map; skills forever-sim; SPF credits-audit; bug-sweep tracker-questie-bg/tooltip-taint/buy-reagents-stuck (likely superseded by owner's fix/* PRs). Open: AGF #210 #212 #213 #214, SPF #220, skills #41. CF IDs corrected: Legacy 1705879, Tweaks 1708506 (were swapped in cfwatch + Nebula prompt).
## Round 9 (2026-10-22) - one task per enhancement + Hoard and Atlas
- Owner ask: "one task per existing enhancement then one task for hoard forever and one for atlas forever ... go fully ship all give agents as much info as possible". Queue in `round9/README.md`, one brief per work item W1-W8.
- W1 Field Guide spawn API + hunt route (field-guide-forever); W2 SPF `Nearest` (shortest-path-forever); W3 SkillUp shopping API/export/buy trip (skillup-forever); W4 gathering nodes (skillup-forever, after W3); W5 Legacy x Field Guide Zone Master (legacy-forever); W6 AGF detour costing (adventure-guide-forever); W7 Hoard Forever and W8 Atlas Forever staged under `staging/` on cjber/skills because `gh repo create` is 403 for the workspace App.
- boundaries.md: Hoard and Atlas added as addons 8 and 9; round-9 feature rows marked new; two change-log rows.

## Round 10 (2026-10-24) - report and issue unification
- Owner asked to unify report, issue and similar duplicated logic across the addon suite, extending Forever Core where sensible.
- boundaries.md: report/issue UI and Forever-family link box assigned to Forever Core; shared copies and specs mapped to all five addons.
- Implementation and consumer adoption are in progress under `round10-report-unification.md`.
