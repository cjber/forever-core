````markdown
# Handoff: coordinator for cjber's WoW: Forever addons

You are taking over as **coordinator** for five WoW: Forever addons. The owner is Cillian Berragan (GitHub `cjber`,
cjberragan@gmail.com). You run agents, review their PRs, merge them, and cut releases. The owner has given full
permission to merge and release, and trusts your judgement on most calls.

The previous session stopped on 2026-10-18 when the weekly usage limit ran out (it resets 2026-10-22 10:00 UTC). All
unfinished work is pushed to GitHub. Nothing is only local.

## Read first
Everything the old session had in its scratchpad is on **cjber/skills**, branch **`ccr-cc333990-q8ydc4-handoff`**, in the
`forever-handoff/` folder. Never merge this branch into main: it's notes only.

| File | What it is |
|---|---|
| `brief.md` | Shared agent rules: signing, trailers, PR flow, credits, comments. Every agent you start must read it. |
| `release-brief.md` | Release process: Phase 1 prep, then READY, then Phase 2 publish and verify. |
| `round6-brief.md` | The current feature round: work items S1–S3, A1–A4, H. |
| `design-agf-spf-split.md` | **Approved by the owner on 2026-10-17.** The plan for who does what across the five addons. It becomes round 7. |
| `overlay-notes.md` | How to draw on the world map without gamepad taint (`UI/MapCanvas.lua`, the `ForeverMapMarkers` registry). |
| `audit.md` | Audit of every CurseForge comment and GitHub report: status and credits. |
| `ledger.md` | Running log of every merge, release, decision and owner correction. Read it before you act. |
| `owner-checklist.md` | Things only the owner can do. |
| `cfwatch.py` | Fetches every CurseForge comment, all pages and replies. |
| `bugsweep-brief.md` | The 2026-10-17 bug sweep. Done; kept for reference. |
| `store/` | Store-page plans (exact descriptions, summaries, captions). The undated `<addon>-store.md` files are current; use them for the owner's pending pastes. |
| `tools/prwait.py`, `tools/ciwait.py` | Wait for a PR's checks (`prwait.py repo#N`) and for the main-branch `ci.yml` run (`ciwait.py repo sha`) before merging or releasing. `tools/family.lua` holds the 18 shared phrases × 9 locales. |
| `older-briefs/` | Earlier rounds (family page, translations, routes, visibility plan, round 2 decisions, the final report). Context only. |

## The addons
| Addon | Repo | CurseForge ID | Live version |
|---|---|---|---|
| Shortest Path Forever (SPF) | cjber/shortest-path-forever | 1708599 | 1.19.2, plus unreleased #217/#218/#219 on main |
| Adventure Guide Forever (AGF) | cjber/adventure-guide-forever | 1711538 | 0.17.1, plus unreleased #211 on main |
| SkillUp Forever | cjber/skillup-forever | 1705762 | 0.16.1, plus credits #170 on main |
| Legacy Forever | cjber/legacy-forever | **1705879** | 0.10.1 |
| Tweaks Forever | cjber/tweaks-forever | **1708506** | 0.14.1 |

Lua 5.1, Interface 16001, Forever build 1.60.1.70450. Agents never launch the game. Every PR lists its in-game `/reload`
checks for the owner. Check the live versions against each repo's tags before you rely on them.

## Hard rules
- **Commits.** Signed with `git commit -S`, author `cjberragan@gmail.com`. The global git email is a noreply address, so
  pass `-c user.email=cjberragan@gmail.com -c user.name="Cillian Berragan"`. The signing key is configured.
- **Trailers.** End each commit with:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01JcwULHwLekhyjYKyVykXY3`.
- **No model names** in commits, PRs or code.
- **Merging.** Branch protection is strict. Merge with squash and `expectedHeadSha`, and update the PR branch if it's
  behind. Agents never merge: they send `READY <PR URL> <head sha>` and you merge.
- **Releasing.** After the `ci.yml` push run on main passes, dispatch `release.yml` (input: version). Then verify the
  GitHub release, CurseForge, Wago and the zip.
- **Credits (WFA-33).** Credit every reporter or requester by CurseForge **displayName** (not their `user_xxx` username)
  in the changelog bullet and in THIRD_PARTY.md under `## Ideas and contributors`.
- **Translations (WFA-34/16).** Every new phrase goes into all 9 locales, and `check_locales --release` must pass.
  Machine-translated lines are marked `-- mt`. Only lines identical to Brainc3ll's French in legacy-forever c6d663f
  count as human.
- **Generated data.** Never hand-edit generated `Data/`. Regenerate it with the repo's tools.
- **Polestar** (fitzforge/polestar, GPL-3.0). Read it for ideas only and never copy its code. Credit the idea. Fitz may
  use our code freely (the owner confirmed). **Don't comment on SPF #143 again.**
- **Secrets.** Never print one. A GitHub token goes only to api.github.com.
- **GitHub posts.** Don't post comments the owner hasn't asked for. Opening issues for player reports is fine.
- **Quality.** Before any cleanup, load `.agents/skills/sift-project/SKILL.md` in the repo. Follow each repo's AGENTS.md
  and `## Commands` gate.

## Other sessions
- **The owner's own parallel session** works on these repos using `fix/*`, `feat/*` and `release/*` branches. It
  shipped SkillUp 0.16.x, Legacy 0.10.x, SPF 1.19.2 and AGF 0.17.1. Owner's instruction: "focus on yours and keep an
  eye on all mine." Watch its PRs. Tell the owner about red CI or a conflict instead of commenting on its PRs. Never
  duplicate its work: check open PRs and recent merges before you start anything.
- **The owner's Nebula job** now watches comments; the old session's recurring check was deleted. Still run
  `cfwatch.py` before every release. CurseForge comments page with `page=N` from 0, because `pageIndex` is ignored.
  Pages are capped at 20, replies are nested, and credit goes to displayName.

## State at handoff

### Round 6 (Polestar-inspired features)
**Merged:**

| PR | What |
|---|---|
| SPF #217 | TomTom/Polestar compatibility and the API contract spec |
| SPF #218 | Gamepad-safe world map: `UI/MapCanvas.lua` and `ForeverMapMarkers`. Part of #158, which stays open for the in-game A/B |
| SPF #219 | Walks avoid zones 4+ levels above you and the other faction's towns |
| AGF #211 | Party-shared quests |

**Open PRs.** Check CI, then review and merge, or fix if red:
- AGF #210: objectives go to the main camp of normal mobs (A2a/b).
- AGF #212: put a quest first while its item is running out (A2c).
- AGF #213: warn before taking a quest that closes another (A1a).
- AGF #214: each step says why it wants a group (A1b).
- SPF #220: credits for missed CurseForge reporters, from the audit.
- cjber/skills #41: forever_sim, the headless Forever client for scenario tests. Its acceptance test was red on SkillUp
  0.15.0 with syrberus's exact taint error, and green on 0.16.0.

**Work saved on `-wip` branches.** Some contain mid-merge conflict markers, so resolve them before use. Check whether
the open PRs above already include this work.
- AGF: `ccr-cc333990-q8ydc4-quest-safety-wip`, `-group-lines-wip`, `-expiring-wip`, `-camp-wip`, and
  `-overlay-pins-wip`.
  - `-overlay-pins-wip` is A4, AGF's gamepad-safe map. It has no PR yet. Port it to SPF's `UI/MapCanvas.lua` and to
    overlay-notes.md.
- Legacy and Tweaks: `ccr-cc333990-q8ydc4-gamepad-map-wip` in each repo is H, their gamepad-safe maps. No PRs yet.
  - Its last step was "changelogs and THIRD_PARTY".
  - Tweaks' `Map/DungeonEntrances.lua` must read `ForeverMapMarkers` instead of SPF's old pin templates, which no
    longer exist on the map.
  - The marker registry rule: publish a copy, `local m = {}; for k,v in pairs(ForeverMapMarkers or {}) do m[k]=v end;
    m.MyAddon = fn; ForeverMapMarkers = m`. A direct field write fails the taint lint.
  - Comment on Tweaks #168 when H merges.
- skills: `ccr-cc333990-q8ydc4-forever-sim-wip` holds the sim's newest uncommitted bits (layout and stand-ins). Fold it
  into #41.
- SPF: `ccr-cc333990-q8ydc4-credits-audit-wip`, which may duplicate #220.
- Bug sweep: `ccr-cc333990-q8ydc4-tracker-questie-bg-wip` (SPF), `-tooltip-taint-wip` and `-buy-reagents-stuck-wip`
  (SkillUp). The owner's session already shipped these fixes, so they're probably superseded. Don't open PRs from them
  unless something is missing. The tracker background (AGF #203, requested by Naburiel) belongs to the owner's session.
- Old worktrees `agf-data`, `spf-data` and `su-data` were data refreshes that were squash-merged long ago. Ignore them.

**Still to do in round 6:**
- **SPF #219 follow-up, ordered by the coordinator:**
  - Displayed times must be real travel seconds. Use the hazard factors only to choose the path.
  - Don't weight short connector walks (under about 200 yd) next to a dock or flight master, for example Theramore's
    dock to its flight master.
  - Add specs for both.
- **Deferred to the owner:**
  - S1b route styles: needs a local re-bake with the WoW client, and roads aren't marked in client data.
  - S1d cave arrival by subzone: needs a new data source, such as terrain area IDs from wago.tools.
- **Releases once round 6 merges:** SPF 1.20.0, AGF 0.18.0 (after 0.17.1), and Tweaks and Legacy patches if H lands.
  SkillUp releases its credits change whenever.

### Next: round 7, the approved design
Build `design-agf-spf-split.md` §12 end to end:
1. SPF router: quest task model, cost matrix, solver, goldens with a 5% gate.
2. SPF 1.21: *Route my quest log*, plus API minor 2 (`CanRouteQuests`, `RouteQuests`, `QuestRoute`, `NextSpot`,
   `Nearest`, and a Subscribe key `plan`).
3. Legacy `ShowsAreas()`; SkillUp and Tweaks use `Nearest` and `QuestRoute`.
4. AGF 0.19 switches over and keeps its planner as a fallback.
5. AGF 0.21 removes its old planner.

All 10 decisions in §11 are approved as recommended. Fan agents out in parallel, one worktree each, with
`brief.md` and the PR and review skills, and test end to end.

### Owner items (they need a login or the game)
- **Store description pastes.** Tweaks is next (from its store plan). AGF and SPF/SkillUp text has changed since. Also
  re-check that Wago saved the SPF and SkillUp text.
- **owner-checklist.md:**
  - add a signing key on GitHub;
  - add the WFA-33 line to the cjber/.github PR template;
  - add repo topics and pin the repos;
  - set up CurseForge Relations and Wago dependencies;
  - make `package` a required check;
  - delete the probe branches in cjber/skills;
  - do the in-game checks.
- **In-game A/Bs:**
  - SPF #158: gamepad taint log with only SPF enabled.
  - SPF #159, #161, #188; AGF #166; SkillUp #124; Tweaks #168.

## How to start
1. Clone the five repos and cjber/skills, and read the `forever-handoff/` bundle.
2. List open PRs in all five repos and in skills; note which come from the owner's session.
3. Review and merge the round-6 PRs that are green. Turn the `-wip` branches into PRs, starting with AGF A4 and
   Tweaks/Legacy H.
4. Dispatch the SPF #219 follow-up.
5. Run release prep for SPF 1.20.0 and AGF 0.18.0, run `cfwatch.py`, then release.
6. Start round 7.
7. Keep `ledger.md` updated as you go, and tell the owner briefly what shipped and what needs them.
````
