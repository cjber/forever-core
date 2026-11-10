# AGENTS.md

Forever Core is the shared floor under the WoW: Forever addon suite (Interface 16001): the one objective-tracker
column the addons dock into, the grip and Lock switch that move it, the section order that stacks them, and the
Questie bridge that keeps the column out from under Questie's quest list. It is GPL-3.0-or-later and ships as its own
addon, `ForeverCore`.

## The two rules that matter

1. **The shared files are the source of truth, and nothing here is addon specific.** Tracker files are vendored byte
   for byte into adventure-guide-forever, legacy-forever, shortest-path-forever, skillup-forever and kiln-forever.
   Error capture, report and log files are vendored into every consumer addon, and Forever-family files into the five
   published addons, at the same paths (`Core/SafeCall.lua`, `Core/Log.lua`, `UI/Report.lua` and
   `UI/ForeverFamily.lua`; see `docs/adoption.md`). A fix lands here first, then `tools/sync_consumers.py` copies it
   out. Never edit a copy in a consumer repo and never bend these files toward one addon's needs: they read everything
   addon specific through the namespace (`ns.TrackerHostSettings`, `ns.ReportTitle`, `ns.L`), by design. Kiln Forever
   also keeps a Node bridge in its repository, so its addon mirrors core under `addon/KilnForever/`; `CONSUMER_ROOT`
   in `tools/check_core_shared.py` records that folder for every path the tools build.
2. **The paths mirror a consumer repo.** Suite convention is flat Lua at the repo root, and this repo is the one
   deliberate exception: keeping `UI/TrackerHost.lua` where the consumers keep it makes the vendored copy a pure
   copy, and lets their specs (`tests/tracker_host_spec.lua`, which loads `UI/TrackerHost.lua` by path) run here
   unchanged.

## Commands

```sh
luacheck .
stylua --check .
for s in tests/*_spec.lua; do luajit "$s" || exit 1; done
python3 tools/fetch_tracker_ui.py && TRACKER_UI_ROOT=tools/.cache/tracker-ui luajit tests/tracker_host_spec.lua
bash tools/typecheck.sh                   # LuaLS 3.19.1 over the shared Lua, with the pinned WoW API annotations
python3 tools/check_consumers.py          # every consumer's copy matches this repo
python3 tools/check_client_load.py        # every font object exists in the client; no TOC lists Bindings.xml (WFA-37)
python3 tools/check_menu_scroll.py        # a menu built from a list scrolls (WFA-36)
python3 tools/check_assets.py             # legacy chrome by name and by FileDataID age
python3 tools/check_shared_versions.py    # shared-file versions match their exact bytes
python3 tools/gen_legacy_chrome.py        # regenerate the asset checker's pinned-build data
python3 tools/forever_perf.py             # the !!DevPerf and !!DevSmoke session report
python3 tools/headless/forever_client.py run -- tools/headless/perf_run.sh  # one profiled session in the headless client
python3 tools/sync_consumers.py ..        # copy this repo's shared files into local checkouts
python3 tools/sync_curseforge.py ..       # publish changed docs/curseforge.md files as CurseForge descriptions
ruff check tools && ruff format --check tools
python3 -m unittest discover -s tools -p "test_*.py"
```

`tests/tracker_host_spec.lua` is the native integration spec: it runs Blizzard's real objective-tracker source,
fetched at a pinned revision by `tools/fetch_tracker_ui.py`, against this host. The other tracker specs stub everything
and run anywhere.

## Layout

- `Core.lua`: ForeverCore's own install of the host's settings (`ns.TrackerHostSettings`), in `ForeverCoreDB`.
- `Expose.lua`: the public `ForeverCore` table and `/fcore`; the last file the TOC loads, because it publishes what
  the shared modules built.
- `Core/SafeCall.lua`, `UI/Report.lua` and `UI/ForeverFamily.lua`: shared error capture, report, issue and link UI vendored into all five consumers.
- `Core/OpenMap.lua` and `Core/OpenSettings.lua`: the shared openers for the client's restricted world map and settings
  panel functions, each run through `CreateSecureDelegate`, never in combat, vendored only to the addons that open that
  one.
- `Core/Log.lua`: the shared structured log, its 200-line saved ring, the `/forever debug` switch and the lines the report copies.
- `tests/report_spec.lua`, `tests/debug_log_spec.lua` and `tests/forever_family_spec.lua`: their contract specs.
- `UI/TrackerHost.lua`: the private tracker column, its optional tooltip-art backdrop and opacity, its layout,
  combat and Edit Mode handling, and the `ForeverTrackerHost` global the first-loaded Forever addon publishes and the
  rest adopt.
- `UI/TrackerLock.lua`: the grip and the Lock switch, which must load before the host.
- `UI/TrackerOrder.lua`: the section order (`uiOrder`, then attach order).
- `UI/TrackerQuestie.lua`: Questie's quest list, so the column steps beside it instead of under it.
- `UI/QuestLogTabs.lua`: the shared world map quest log side tab, stacking every addon's panel tab by order,
  restoring the client's own pages on demand and telling a panel through `shown` when it becomes visible or stops
  being visible, so panels set no OnShow or OnHide script under the map. `tests/quest_log_tabs_spec.lua` is its
  contract.
- `Core/LeaderboardsData.lua`: the leaderboards' data half, overall points, standing, the per-scope cache keyed on
  each board's `revision` and the unit-tooltip place. Loaded before `UI/Leaderboards.lua`, so a tooltip hover is one
  cache lookup rather than a board build and sort.
- `UI/Leaderboards.lua`: the shared Forever Leaderboards window, its registration and tabs, vendored with
  `Core/LeaderboardsData.lua` to the six consumers that carry `Core/PeerStats.lua`; each addon registers one board
  and nothing there knows an addon.
- `Locales/enUS.lua`: the phrases the shared files themselves draw. A consumer keeps its own locale file for its own
  copy; the phrases there are the only ones core owns.
- The suite's ownership boundaries live in `docs/handoff/boundaries.md`, with the rest of the suite notes in
  `docs/handoff/` (handoff briefs, audit notes, the ledger). Read `docs/handoff/boundaries.md` before assigning a
  feature or moving code between addons.
- `tools/check_core_shared.py`: the vendoring map (`VENDORED`, which consumer carries which file), the per-consumer
  addon folder `CONSUMER_ROOT` (kiln-forever keeps its copies under `addon/KilnForever/`) and the consumer-side check,
  vendored into every consumer. In a consumer it compares its copies with core main; with `--base REF` it checks only
  the vendored files `REF...HEAD` changes, so a hand edit fails a PR while a lag behind core does not.
- `tools/check_client_load.py`: the client load rule, vendored into every consumer with its font list
  `tools/blizzard_fonts.txt`: every font object the addon's Lua or XML inherits is one the client's UI or the addon
  defines, and no TOC lists Bindings.xml. Regenerate the list from the pinned Blizzard UI source with
  `python3 tools/check_client_load.py --blizzard-ui ../wow-handoff/blizzard-ui`; `tools/test_check_client_load.py` is
  its spec.
- `tools/check_menu_scroll.py`: the menu rule, vendored into every consumer: a menu description that gets entries in
  a loop calls `SetScrollMode` in the same function, or the loop says why it stays short (`-- menu-scroll-ok:
  <reason>`). It reads Lua through the skill pack's `forever_tools/lua.py` lexer; `tools/test_check_menu_scroll.py`
  is its spec.
- `tools/check_shared_versions.py`: the pin on every shared file whose version number gates takeover
  (`UI/Leaderboards.lua`, `UI/ForeverFamily.lua`, `Core/PeerStats.lua`). It reads the exact `local X = N` line and the
  file's sha256, and `tools/shared_versions.json` records both. A change without a raised version, a version that goes
  down or a raise that is not recorded fails; `--record` rewrites the JSON. `tools/test_check_shared_versions.py` is
  its spec. `Core/Log.lua` and `Core/LeaderboardsData.lua` are not pinned: their version fields do not select a copy in
  charge.
- `tools/gen_legacy_chrome.py`: regenerates the shared checker's pinned-build data, `.agents/skills/wow-forever-addon/tooling/forever_tools/legacy_chrome.txt`
  (old chrome by FileDataID), `.agents/skills/wow-forever-addon/tooling/forever_tools/interface_paths.txt` (the known interface-path set) and
  `.agents/skills/wow-forever-addon/tooling/forever_tools/backdrops.txt` (each `BACKDROP_*` global and the files it names, from the build's
  `Blizzard_SharedXML/Backdrop.lua`), from the wago.tools listfile for 1.60.1.70124. `tools/check_assets.py` is the entry point over this repo; the age rule
  itself lives in `.agents/skills/wow-forever-addon/tooling/forever_tools/assets.py`, and `tools/test_check_assets.py` is its spec.
- `tools/core-shared-drift.yml`: the drift workflow each consumer keeps under `.github/workflows/`, which runs the client load
  rule, the menu rule and that check on every PR (`--base`) and on a schedule (the full check). Its `core-shared` job is required in
  every consumer, so both rules gate every consumer PR with no change to the consumer's own CI. It lives outside `.github/workflows` so it never runs
  here; the `workflows` CI job lints it.
- `tools/check_consumers.py`, `tools/sync_consumers.py`: the vendoring gate and its fix, both reading the map above.
  `.github/workflows/drift.yml` runs the checker on a schedule only, so a core change never blocks on consumer release
  timing.
- `tools/sync_consumer_prs.py`: the automatic consumer sync behind `.github/workflows/sync-consumers.yml`. On every push
  to main it derives the consumers from `VENDORED` plus the live repositories that vendor `tools/forever_tools/` or
  `tools/forever_sim/`, runs the same three syncs as `sync_consumers.py` and regenerates each consumer's
  `Locales/phrases.txt` when it has `tools/phrases.py`, then builds the signed commit on a scratch branch through the
  GraphQL `createCommitOnBranch` mutation and moves `forever-core-sync` to it in one ref update, with an
  auto-merging PR in each consumer. It needs the `CONSUMER_SYNC_TOKEN` secret; without it the job prints a notice and
  stays green. `tools/test_sync_consumer_prs.py` is its spec.
- `tools/discord_digest.py`: the Discord release digest, with pure payload builders over GitHub releases and
  `CHANGELOG.md` data and a thin fetch and post layer. `.github/workflows/discord-digest.yml` posts hourly on the
  schedule only; `tools/test_discord_digest.py` is its spec.
- `types/`: LuaLS declarations. `types/ForeverTracker.lua` is the tracker contract (settings, host, lock, order and
  the namespace fields the tracker files read), vendored with the tracker files so a consumer declares none of it by
  hand; `types/Forever.lua` and `types/Client.lua` are core's own and stay here.
  `tools/typecheck.sh` checks every Lua file outside `tests/`, `tools/`, `docs/` and `.agents/` against them; CI
  installs LuaLS 3.19.1 by checksum, and the script refuses any other version.

## CI

`.github/workflows/ci.yml` runs on every PR and push to main: `deadcode`, `check` (luacheck, the specs, the native
tracker spec, StyLua, ruff, the `tools/` unit tests), `typecheck`, `project-rules` (the client load rule and the menu rule), `packaged`, `secrets` and
`workflows` (actionlint and zizmor over `.github` and the consumer workflow template).
`.github/workflows/forever-tools.yml` and `.github/workflows/forever-sim.yml` test the skill pack's tooling on every PR,
with no path filter, so they can be required checks. Every PR job runs on `ubuntu-24.04`, and LuaJIT and luacheck are
installed at that release's exact apt versions, so a runner image update cannot change them.
`.github/workflows/suite.yml` runs `tools/suite_load.py` daily and on demand (`gh workflow run suite.yml`): it clones
every published addon's main and runs `tests/suite/suite_scenario.lua`, which loads them all with ForeverCore in one
forever_sim client and calls `sim:exercise()`. It reads other repositories' main, so it is not a PR job. Locally,
`python3 tools/suite_load.py --root ..` runs it over the sibling checkouts as they are.

## Agent skills

The suite-wide skills live here, in the one repo every addon already vendors from, so an addon repo carries only
what is specific to itself. Repo-specific skills (a repo's `release` checklist, its `tools/repo_rules.py`) stay
in that repo's `.agents/skills/`, never in `cjber/skills`; `cjber/skills` holds only skills that build repo-specific
logic out of a general rule (how `sloppatrol` functions, how `wowmock` renders).

| Skill | Load it when |
|---|---|
| `.agents/skills/wow-forever-addon/SKILL.md` | the shared standards pack (`WFA-*`), UI look, icon, docs, CI and release baseline |
| `.agents/skills/wow-addon-publish/SKILL.md` | publishing to CurseForge and Wago, or cutting a release |
| `.agents/skills/wow-retail-ui-style/SKILL.md` | drawing or auditing addon windows, frames and widgets |

Each addon declares `wow-forever-addon` under `## Standards` in its `AGENTS.md`, pinned to this repo. The pack's
tooling (`tooling/forever_tools`, `tooling/forever_sim`) is produced here and vendored byte for byte into the
consumers' `tools/`; edit it here, then run `sync.py update --source <this checkout>` in the consumer.

## Versions and releases

Every version needs a `CHANGELOG.md` entry before its `v*` tag. `.github/workflows/release.yml` publishes the GitHub release with the
packager; there is no CurseForge or Wago page for a library addon, so no store tokens are involved. A core version
bump is adopted by consumers at their own pace: `tools/sync_consumers.py` in this repo, then one PR per consumer,
with `tools/check_consumers.py` going green once all five have moved.

## Load order

`ForeverCore.toc` lists the five Forever addons as `OptionalDeps`, which makes WoW load them before core when they
are installed. That ordering is the point: the addon that already owns the player's tracker settings builds the
column, and core adopts the published `ForeverTrackerHost` instead of starting a second one with settings nobody
saved. Do not remove those OptionalDeps.
