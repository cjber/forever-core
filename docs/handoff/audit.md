# Comment and report audit, 2026-10-17

Sources: `cfwatch.py` (every page and reply, all five addons; 76 comments and replies), GitHub issues and PRs since
2026-09-25 in the five repos (non-owner authors and comments). Checked against origin/main as of the audit:
SPF 87d4872, AGF 77a3752, SkillUp cd1b61d, Legacy e3a78ca, Tweaks 920abf9.

Status key: (a) shipped and credited (name in THIRD_PARTY.md "Ideas and contributors" plus the changelog's
credits; older SPF/AGF/SkillUp releases credit through the 1.18.0/0.14.0-era "Credits" bullet and README, which
was the format before the per-bullet rule), (b) shipped but not credited, so the credits PR fixes it, (c) answered
by an existing setting, (d) still open, (e) declined earlier, H = being handled now by another agent, n/a = praise,
thanks or chat.

## Key findings

1. **cfwatch.py had Legacy's and Tweaks' CurseForge project IDs swapped.** The TOCs say Legacy is 1705879 and
   Tweaks is 1708506. So **overspark (dungeon entrances) posted on Legacy's page, not Tweaks'**, and
   **user_1l99gpqwx7i0dw5t (gamepad crash backing out of the addon menu) and HausWindseeker posted on Tweaks' page**.
   I fixed the MODS map in cfwatch.py; seen.json only stores comment IDs, so nothing else changes.
2. SPF totalCount is 45 but only 44 unique comments and replies come back (AGF 11 vs 10). Probably deleted comments
   that the API still counts. Nothing is missing from the pages.
3. Credit names now follow CurseForge displayName. On SPF two names were usernames that don't match what the page
   shows: `neil_team_brigade` is **team_Brigade** and `test1point6` is **Testvonfarkle**. Fixed in the SPF PR, along
   with capitalisation (The\_\_\_Fast, Alex21xx, Merlinqt, Maggew, Joster91; SkillUp Chuujitsuna). AGF still has
   `rhednak` and `jechten` (displayNames RhednaK, Jechten), left for the AGF #203 agent so I don't conflict with it.
4. No new (d) items: every bug report or request is shipped, answered by a setting, covered by an open issue, or
   being handled.

## Credits PRs

- SPF: https://github.com/cjber/shortest-path-forever/pull/220 (GenericP; Sol_Deus into #218's gamepad row; display names).
- SkillUp: https://github.com/cjber/skillup-forever/pull/170 (SilentGentlemanSG; Chuujitsuna, BallaRa, Syrberus casing).

Since the audit started, another session merged SkillUp #164–#167 (v0.16.0: Syrberus, kurila11478, BallaRa, kopuliak,
Chuujitsuna credited), #169 (v0.16.1 Questie tracker: deathmvp1, berserkerlxl), Legacy #140 (v0.10.0: overspark
credited), SPF #215 (v1.19.2 #214: deathmvp1, berserkerlxl), #217, #218 (gamepad: TRDeadbeat, tallsmartman). Open:
AGF #209 (credits deathmvp1 and berserkerlxl), Legacy #143. AGF #203 (Naburiel) still to credit.

## Shortest Path Forever (CurseForge 1708599)

| Date | displayName | Summary | Status | Evidence |
|---|---|---|---|---|
| 09-30 | The___Fast | Phantom Powderfuse Port flight path; setting for minimum Hearthstone saving | a | 1.7.0; THIRD_PARTY row (renamed The\_\_\_Fast) |
| 10-06 | cidolfus27 | Take over RestedXP's arrow | a | 1.12.0 *Follow RestedXP guides*; THIRD_PARTY row |
| 10-07 | Alex21xx | Minimap settings button, resume RestedXP, metres | a | 1.14.0; THIRD_PARTY row |
| 10-07 | Alex21xx (reply) | Click a step to complete it; mark known flight points (Camp Taurajo not picked up) | a | 1.14.0 *Complete this step*, right-click flight master > known; THIRD_PARTY row |
| 10-07 | alexjustdoit | Set a point on the world map and route there | c | Shift-click the world map or minimap, or the map pin button top left of the map (answered by GenericP the same day; CHANGELOG "Shift-click the world map or minimap to plan") |
| 10-08 | GenericP | Questie icon steals the map click; or use TomTom waypoints | **b** | 1.14.0 "Plan directly over Questie icons" (Alt-click), 1.15.0 *Follow TomTom's arrow*; not credited, added in credits PR |
| 10-08 | user_bkkmzb8cknl1rh3y35110 | Move the guide | c | /path > Guidance > untick *Attach to quest tracker*, then drag (also the tracker's right-click menu since 1.17.0). Anonymous |
| 10-08 | o0saw0o | Turn off Journey display and arrow | a | 1.14.0 /path > Interface; THIRD_PARTY row |
| 10-09 | Merlinqt | Scale map icons | a | 1.14.0 /path > Map marks; THIRD_PARTY row |
| 10-09 | user_ena8k9jwrvkr3m2o | Crash with controller | H | SPF #158 (open, in-game A/B), mitigation #192 in 1.17.0, round 6 S2. Anonymous: generic thanks |
| 10-09 | Joster91 | Journey overlaps the quest log until +/- | a | 1.15.0/1.17.0; THIRD_PARTY row with rydoc |
| 10-09 | tallsmartman (reply) | Still breaks with gamepad | a | credited by SPF #218 (overlay map drawing, round 6 S2) |
| 10-10 | TRDeadbeat (reply) | Still freezes with controller | a | credited by SPF #218 |
| 10-10 | Alex21xx | Moonglade routes through unknown flight points (Horde) | a | 1.15.0 (#139), regression spec #184; THIRD_PARTY row |
| 10-11 | Maggew | Step description on the gold pin; finer compass, arrow keys | a | 1.15.0, #160, 1.17.0 (#190); THIRD_PARTY row |
| 10-12 | Maggew | JourneySearch.lua:190 division by zero | a | 1.15.0; THIRD_PARTY row |
| 10-12 | phear | Hide Forever Tracker with no route | a | 1.15.0; THIRD_PARTY row |
| 10-12 | berserkerlxl | TomTom integration not working; add /way | a | 1.15.0 `/way`, *Follow TomTom's arrow*; THIRD_PARTY row. #159 open for the in-game check |
| 10-12 | team_Brigade | Hide 'Forever Tracker' title when detached and idle | a | 1.15.0; THIRD_PARTY row renamed from neil_team_brigade |
| 10-13 | Testvonfarkle (reply) | Same as team_Brigade | a | THIRD_PARTY row renamed from test1point6 |
| 10-13 | rydoc | Journey collapses from the quest tracker (EllesmereUI) since 1.14 | a | 1.15.0/1.17.0 TrackerHost fixes; THIRD_PARTY row |
| 10-13 | Maggew | Compass background opacity slider | a | 1.15.0; THIRD_PARTY row |
| 10-14 | user_geseqn24hx6b3d9b | Make the tracker movable like the compass | a/c | /path > Guidance > *Attach to quest tracker* off, and the tracker menu (1.17.0). Anonymous: generic thanks |
| 10-15 | Sol_Deus | Gamepad: SetPreferredGamepadInteractTarget() blocked (also TomTom, Scrap) | **b** | #218 treated the rest as anonymous; Sol_Deus (username user_pj9n…) added to #218's gamepad row in SPF #220. #158 open for A/B |
| 10-15 | Alex21xx | Druid Moonglade routing again | a | as 10-10; owner replied 10-17 |
| 10-15 | deathmvp1 | Journal sits behind the quest list | a | SPF #214 via #215 (v1.19.2), credited |
| 10-17 | berserkerlxl (reply) | Diagnosis: it's Questie's tracker | a | credited in #215 (SPF), #169 (SkillUp), AGF #209 open |
| 10-08 | GenericP (2 replies) | Answers to other players | n/a | mentioned in GenericP's credit row |
| 10-09 | cidolfus27, Merlinqt (replies) | Thanks | n/a | |
| 10-12 | SumGokus | Praise | n/a | |

## Adventure Guide Forever (CurseForge 1711538)

| Date | displayName | Summary | Status | Evidence |
|---|---|---|---|---|
| 10-01 | Jechten | Slow to load | a | 0.10–0.13 load speedups; #166 still open (login measurement); THIRD_PARTY row (as `jechten`) |
| 10-02 | user_epti4zkxgks94zs0 | Slow, buggy: "turn in 2, pick up one" when only 1, UI hides, tracker objectives wrong | a (partial) | No repro detail; objective matching by name (#146 via #170), level-up timing (#149), count refresh (#154) since. round2.md called it vague. Anonymous |
| 10-03 | RhednaK | Integer overflow (Skyborne race) | a | 0.8.0; THIRD_PARTY row (as `rhednak`) |
| 10-04 | Lottus2727 | Asks for a Discord | n/a | Owner answered (no Discord; use GitHub issues) |
| 10-16 | Naburiel | Background behind the tracker | H | AGF #203 (bug sweep item 6). **Credit Naburiel by name** (the brief called it anonymous) |

## SkillUp Forever (CurseForge 1705762)

| Date | displayName | Summary | Status | Evidence |
|---|---|---|---|---|
| 10-08 | kopuliak | Hide the route tracker completely | a | 0.9.0 *Show tracked professions*; THIRD_PARTY row |
| 10-09 | user_z4cq3jpa83nj30ti | Quest tracker moved and stuck, Edit Mode can't fix it | a | #136 (0.12.0), changelog "another player on CurseForge". Anonymous |
| 10-09 | kopuliak | Heavy Sharpening Stone 125, "Patterned Bronze Shoulders" 120, Bronze Warhammer 125 craftable at 110; current AH price | a | #123/#138 (Warhammer 110). Shoulders is Patterned Bronze Bracers (2672, client orange 120, data 95), Stone 100. 0.9.1/0.9.2 Auctionator latest price. THIRD_PARTY row |
| 10-10 | Chuujitsuna | Can't move the objective window | a | #136; THIRD_PARTY row (now Chuujitsuna) |
| 10-11 | kopuliak | Line 208 secret number on hover | a | 0.10.0 and 0.16.0 (#161) credited |
| 10-11 | Chuujitsuna (reply) | Same error, needs a permanent fix | a | #161 via #164 (v0.16.0), credited |
| 10-11 | SilentGentlemanSG | Remove Buy Track Reagents button; misclick bought 68 bleach and 100+ thread | **b** | 0.10.0 "The merchant's buy button asks first" plus Options > AddOns > SkillUp Forever > Route and trainer > *Show the buy button at merchants*. round2.md named him user_lis26…; added in credits PR |
| 10-12 | user_abm7a6cpht6fli7n | Choose own recipe for the route | a | 0.10.0 *Not this recipe* (right-click a route step). Anonymous: generic thanks |
| 10-13 | berserkerlxl | Material cost at AH sell price, floored at vendor price | a | 0.10.0 Prices setting; THIRD_PARTY row |
| 10-14 | user_to4x644s8jthp4pw42386 | Empty post, then found the tab | n/a | |
| 10-16 | user_yzweof6n5oc0jlet | Search AH mats for N crafts | a | #142 (0.13.0), "Thanks to the CurseForge player who asked". Anonymous |
| 10-17 | BallaRa | Move the recipe tooltip off the reagents | a | #163 via #166 (v0.16.0), credited |
| 10-17 | Syrberus | Taint in GameTooltip_InsertFrame (Tooltip.lua:258) | a | #161 via #164 (v0.16.0), credited |
| 10-17 | kurila11478 | Buy reagents stuck; route empty | a | #162 via #165 (v0.16.0), credited |
| 10-09, 10-10 | kopuliak | Thanks | n/a | |

## Legacy Forever (CurseForge 1705879; cfwatch had it labelled Tweaks)

| Date | displayName | Summary | Status | Evidence |
|---|---|---|---|---|
| 10-17 | overspark | Option to stop drawing dungeon entrances (and praise for the zone summary) | a | Legacy #139 via #140 (v0.10.0), credited. **Posted on Legacy's page.** Tweaks also draws entrances: Options > AddOns > Tweaks Forever > Maps > *Instance entrances* (key `dungeonEntrances`, on by default, follows the world map's *Show instance entrances* filter); Tweaks already steps aside where a Legacy pin sits on an entrance |

## Tweaks Forever (CurseForge 1708506; cfwatch had it labelled Legacy)

| Date | displayName | Summary | Status | Evidence |
|---|---|---|---|---|
| 09-24 | HausWindseeker | Praise | n/a | |
| 10-08 | user_1l99gpqwx7i0dw5t | Crash backing out of the addon menu with a gamepad | H | Tweaks #168 (open, A/B), mitigation #194 in 0.12.1 ("has been reported"), round 6 H. **Tweaks' report, not SPF #158's.** Anonymous: generic thanks |

## GitHub (non-owner issues, PRs and comments since 2026-09-25)

| Repo | Date | Who | Summary | Status | Evidence |
|---|---|---|---|---|---|
| SPF | 10-15 | fitzforge | #144 drawn walk ends skip the line test | a | #187, changelog "Thanks to fitzforge", THIRD_PARTY "Fitz" row |
| SPF | 10-15 | fitzforge | #143 use SPF routes in Polestar (plus comments) | n/a | closed; owner confirmed 10-16. Polestar row in THIRD_PARTY |
| SPF | 10-10 | Zavian | #134 Shift-click swallows chat links | a | THIRD_PARTY row |
| SPF | 10-06 | wfournier | #122 UI scale | a | THIRD_PARTY row |
| SPF | 09-30 | Osipanda | #84 Forever boats ignored | a | THIRD_PARTY row |
| SPF | 09-28 | Nightwind416 | #76 Reposition tracker and compass | a | THIRD_PARTY row |
| AGF | 10-01 | fuguer-ai | #79 read-only current-stop API | a | THIRD_PARTY row |
| AGF | 09-28 | VinzNL | #62 don't recommend battlegrounds | a | THIRD_PARTY row |
| Legacy | 10-11 | Bigabyte | #103 tracker shifts in Edit Mode | a | THIRD_PARTY row |
| Legacy | 10-09 | Brainc3ll | PR #99 French translation | a | THIRD_PARTY rows in all repos that reuse it |
| Tweaks | 10-16 | Mouchoir | #202 login error, with fix | a | changelog "Thanks to Mouchoir", THIRD_PARTY row |
| Tweaks | 10-02 | Sojiro84 | #108 cursor tooltips, #109 Abandon button | a | THIRD_PARTY row |

Open owner-filed issues that track player reports: SPF #158 (gamepad), #159 (TomTom in game), #214 (Questie tracker),
AGF #166 (login), #203 (tracker background), SkillUp #161/#162/#163, Legacy #139, Tweaks #168. No other non-owner
comments on open issues.
