# AGENTS.md

Forever Core is the shared library under the WoW: Forever addon suite (Interface 16001). It is its own addon,
`ForeverCore`, and every Forever addon requires it with `## Dependencies: ForeverCore`. It owns the one objective-tracker
column the suite docks into, the grip and Lock switch that move it, the section order that stacks them, the Questie and
EQOT bridges that keep the column out from under another tracker's quest list, the report and issue windows, the error
journal and debug log, Forever Leaderboards, the minimap button, the world map quest log tabs, the settings-page chrome
and the Forever addons page. It is GPL-3.0-or-later.

## The two rules that matter

1. **This repo is the only copy of the shared runtime.** Nothing here is addon specific. Runtime files load once, from
   ForeverCore, and a consumer reads them through the `ForeverCore` table and `ForeverCore.Register`. Never copy a
   runtime file into a consumer, and never bend one toward a single addon: everything addon specific arrives through
   `Register` or the module API. Kiln Forever keeps its addon under `addon/KilnForever/`; `CONSUMER_ROOT` in
   `tools/check_core_shared.py` records that folder for the development tooling the consumers still receive.
2. **The shared files keep their consumer-visible paths.** Suite convention is flat Lua at a consumer repo's root; this
   repo keeps `UI/TrackerHost.lua`, `Core/SafeCall.lua` and the rest at the paths consumers name in their docs and
   specs, so a consumer's `loadfile("UI/TrackerHost.lua")` still finds core's own source when its spec loads it here.

## Commands

```sh
luacheck .
stylua --check .
python3 .agents/skills/wow-forever-addon/tooling/forever_tools/specs.py   # every spec, in parallel
python3 tools/fetch_tracker_ui.py && TRACKER_UI_ROOT=tools/.cache/tracker-ui luajit tests/tracker_host_spec.lua
bash tools/typecheck.sh                   # LuaLS 3.19.1 over the Lua, with the pinned WoW API annotations
python3 tools/check_consumers.py          # every consumer's tooling, ForeverCore pin and packaging match this repo
python3 tools/check_client_load.py        # every font object exists in the client; no TOC lists Bindings.xml (WFA-37)
python3 tools/check_menu_scroll.py        # a menu built from a list scrolls (WFA-36)
python3 tools/check_api_docs.py           # docs/api.md names every published API function and its minor
python3 tools/check_assets.py             # legacy chrome by name and by FileDataID age
python3 tools/gen_legacy_chrome.py        # regenerate the asset checker's pinned-build data
python3 tools/forever_perf.py             # the !!DevPerf and !!DevSmoke session report
python3 tools/headless/forever_client.py run -- tools/headless/perf_run.sh  # one profiled session in the headless client
python3 tools/sync_consumers.py ..        # copy this repo's development tooling into local checkouts
python3 tools/sync_curseforge.py ..       # check CurseForge descriptions match docs/curseforge.md (--push publishes)
python3 tools/check_package.py            # .release/ForeverCore holds every TOC file and no development folder
ruff check tools && ruff format --check tools
python3 -m unittest discover -s tools -p "test_*.py"
```

`tests/tracker_host_spec.lua` is the native integration spec: it runs Blizzard's real objective-tracker source,
fetched at a pinned revision by `tools/fetch_tracker_ui.py`, against this host. The other tracker specs stub everything
and run anywhere. `tests/api_spec.lua` loads the TOC in order, registers two fake addons and checks the public API.

## Layout

- `Core.lua`: ForeverCore's own install of the host's settings (`ns.TrackerHostSettings`), the one `ADDON_LOADED`
  handler that makes `ForeverCoreDB`, and the hooks that attach core's journal and log and run the tracker migration.
- `Expose.lua`: the public `ForeverCore` table (`API = 1`), its modules, `Register` and `/fcore`; the last file the TOC
  loads, because it publishes what the modules built.
- `Core/SafeCall.lua`: one global error handler for every registered addon, attributing by `AddOns/<name>/`; the
  per-addon context's `SafeCall`, `RecordError`, `CaughtErrors` and journal live here.
- `Core/Log.lua`: the structured log and its 200-line saved ring per addon, the one `/forever debug` switch and the
  lines the report copies.
- `Core/OpenMap.lua` and `Core/OpenSettings.lua`: core's shared openers for the client's restricted world map and
  settings panel functions, each run through `CreateSecureDelegate`, never in combat. They are runtime files, published
  as `ForeverCore.OpenMap` and `ForeverCore.OpenSettingsPanel`, not vendored into any consumer.
- `UI/Art.lua`: the icon helper the report window draws its portrait with.
- `UI/Report.lua`: the per-addon report window and issue composer, bound to the addon's icon, version and `X-Website`.
- `UI/ForeverFamily.lua`: the Forever addons settings page and link windows, in core's L.
- `UI/TrackerHost.lua`: the private tracker column, its optional tooltip-art backdrop and opacity, its layout, combat
  and Edit Mode handling, and the one-time migration from a consumer's old tracker settings.
- `UI/ContextMenu.lua`: the suite's one context menu, drawn in its own frame because Blizzard's menu can assert on
  this client build; its own frames do not taint the gamepad interface's focus as Blizzard's menu does.
- `UI/TrackerLock.lua`: the grip and the Lock switch, which load before the host.
- `UI/TrackerOrder.lua`: the section order (`uiOrder`, then attach order).
- `UI/TrackerQuestie.lua` and `UI/TrackerEqot.lua`: another tracker's quest list, so the column steps beside it.
- `UI/TrackerQuests.lua` and `Core/QuestOrder.lua`: core's own optional quest list and its pure ordering.
- `UI/QuestLogTabs.lua`: the shared world map quest log side tab, stacking every addon's panel tab by order,
  restoring the client's own pages on demand and telling a panel through `shown` when it becomes visible or stops
  being visible, so panels set no OnShow or OnHide script under the map.
- `UI/ProfessionTabs.lua`: the shared side tab for addon pages in the Professions window, stacking every addon's tab
  under the client's own in registration order, handing the window back on a client tab or page, and keeping the
  window at one width for every profession and tab.
- `Core/LeaderboardsData.lua`: overall points, standing, the per-scope cache keyed on each board's `revision` and the
  unit-tooltip place. Loaded before `UI/Leaderboards.lua`, so a tooltip hover is one cache lookup rather than a board
  build and sort.
- `Core/APIKit.lua`: the shape every addon's own public API follows, published as `ForeverCore.APIKit`: `Hub` for a
  next-frame change dispatch, `NotReady` and `Invalid` for the two `nil, reason` answers, and `Publish` and `Addons`
  for the suite's published API list. `docs/api-conventions.md` is the convention, `docs/api.md` is ForeverCore's own
  page for third-party authors, and `tools/check_api_docs.py` checks an addon's `Core/API.lua` against its
  `docs/api.md`.
- `UI/Leaderboards.lua`: the one Forever Leaderboards window, its registration and tabs; each addon registers one board
  and nothing there knows an addon.
- `Core/PeerStats.lua`: bounded guild and group statistics transport and ranking behind the leaderboards.
- `Core/MinimapButton.lua`: the one minimap ring; each addon draws one button.
- `Core/Text.lua`: the shared search fold and ranking.
- `UI/SettingsPage.lua`: the settings canvas; `Register(name, build, L)` reads every label and tooltip through the
  calling addon's L.
- `UI/MapCanvas.lua`: read-only drawings on the world map, with each addon's markers keyed on its name.
- `Locales/`: core's own phrases in enUS and the nine shipped locales. A consumer keeps its own locale file for its own
  copy; the phrases here are the only ones core owns.
- The suite's ownership boundaries live in `docs/handoff/boundaries.md`, with the rest of the suite notes in
  `docs/handoff/`. Read `docs/handoff/boundaries.md` before assigning a feature or moving code between addons.
- `tools/check_core_shared.py`: the development-tooling map (`VENDORED`), the per-consumer addon folder
  `CONSUMER_ROOT`, and the consumer-side check, vendored into every consumer. In a consumer it compares its copies with
  core main; with `--base REF` it checks only the vendored files `REF...HEAD` changes, so a hand edit fails a PR while a
  lag behind core does not.
- `tools/check_client_load.py`: the client load rule, vendored with its font list `tools/blizzard_fonts.txt`: every
  font object the addon's Lua or XML inherits is one the client's UI or the addon defines, and no TOC lists
  Bindings.xml. Regenerate the list from the pinned Blizzard UI source with
  `python3 tools/check_client_load.py --blizzard-ui ../wow-handoff/blizzard-ui`; `tools/test_check_client_load.py` is
  its spec.
- `tools/check_menu_scroll.py`: the menu rule, vendored into every consumer: a menu description that gets entries in a
  loop calls `SetScrollMode` in the same function, or the loop says why it stays short (`-- menu-scroll-ok: <reason>`).
  It reads Lua through the skill pack's `forever_tools/lua.py` lexer; `tools/test_check_menu_scroll.py` is its spec.
- `tools/gen_legacy_chrome.py`: regenerates the shared checker's pinned-build data from the wago.tools listfile for
  1.60.1.70124. `tools/check_assets.py` is the entry point over this repo; the age rule lives in
  `.agents/skills/wow-forever-addon/tooling/forever_tools/assets.py`, and `tools/test_check_assets.py` is its spec.
- `tools/core-shared-drift.yml`: the drift workflow each consumer keeps under `.github/workflows/`, running the client
  load rule, the menu rule and the tooling check on every PR (`--base`) and on a schedule. Its `core-shared` job is
  required in every consumer. It lives outside `.github/workflows` so it never runs here; the `workflows` CI job lints
  it.
- `tools/check_consumers.py`, `tools/sync_consumers.py`: the tooling gate and its fix, both reading the map above.
  Beyond the file copies, the gate checks each consumer once: its `tools/forever-core.txt` must name core's latest
  release tag (the GitHub API, or with `--local` this checkout's newest `v*` tag), and a consumer whose root TOC lists
  ForeverCore in `## Dependencies` must ship it in its own zip (`externals:` at the pin and
  `move-folders:` `<package-as>/ForeverCore: ForeverCore`), must not also list `- forevercore` under
  `required-dependencies:`, and must carry `## X-Forever-Core: <pin>` in that TOC, the tag a sibling addon compares.
  `.github/workflows/drift.yml` runs the checker on a schedule only, so a core change never blocks on consumer release
  timing.
- `tools/sync_consumer_prs.py`: the automatic tooling sync behind `.github/workflows/sync-consumers.yml`. On every push
  to main, and again from the release workflow once a release is published (a tag a workflow creates with
  `GITHUB_TOKEN` fires no push event), it derives the consumers from `VENDORED` plus the live repositories that vendor
  `tools/forever_tools/` or `tools/forever_sim/`, runs the same syncs as `sync_consumers.py`, regenerates each
  consumer's `Locales/phrases.txt` when it has `tools/phrases.py`, and moves each consumer's `tools/forever-core.txt`
  pin to core's latest release when it lags (one API read per run, and a failed read leaves the pins alone). A moved pin
  also rewrites that consumer's `.pkgmeta` ForeverCore external and `## X-Forever-Core:`, and, when that consumer's
  `.pkgmeta` ships a ForeverCore external whose tag changed, adds a marked `CHANGELOG.md` release entry, then the run
  creates the signed commit through the GraphQL `createCommitOnBranch` mutation and opens an auto-merging PR in each
  consumer. It needs the `CONSUMER_SYNC_TOKEN` secret; without it the job prints a notice and stays green.
  `tools/test_sync_consumer_prs.py` is its spec.
- `tools/release_consumers.py`: the automatic consumer release behind `.github/workflows/release-consumers.yml`, on a
  20-minute schedule. For each consumer it reads main's head and that commit's `CHANGELOG.md`; when the newest
  `## [X.Y.Z]` entry carries `<!-- forever-core-sync -->`, its tag does not exist, no `release.yml` run is queued or
  running, no `release.yml` run at that head has already failed, and `ci.yml` on that head is green, it dispatches the
  consumer's `release.yml` with the version and commit. A consumer whose release already failed at main's head is
  reported as failed, so the job goes red instead of retrying every 20 minutes; the maintainer fixes it and dispatches
  by hand.
  Every core release therefore re-releases every consumer, whose zips all carry the same `ForeverCore` folder. It is
  dispatch-only and idempotent. `CONSUMER_SYNC_TOKEN` needs Actions write on the consumers; without the secret the job
  prints a notice and stays green. `tools/test_release_consumers.py` is its spec.
- `tools/devsmoke/!!DevSmoke`: the `!!DevSmoke` dev addon behind `/forever selftest`, linked into the client from
  this checkout. It opens and closes every loaded addon that depends on ForeverCore (read from the client, so a new
  addon is covered with no list to update) and the world map, saving a pass or fail per surface in `DevSmokeDB`,
  which `tools/forever_errors.py` and `tools/forever_perf.py` read. `tests/devsmoke_spec.lua` is its spec.
- `tools/discord_digest.py`: the Discord release digest, with pure payload builders over GitHub releases and
  `CHANGELOG.md` data and a thin fetch and post layer. `.github/workflows/discord-digest.yml` posts hourly on the
  schedule only; `tools/test_discord_digest.py` is its spec.
- `tools/release_check.py` and `tools/changelog.py`: the release gate (the commit's full CI run on main) and the
  version's CHANGELOG notes, both thin wrappers over the skill pack's `forever_tools`.
- `types/`: LuaLS declarations. `types/ForeverTracker.lua` is the tracker contract; `types/Forever.lua` holds the
  `ForeverCoreAPI`, `ForeverCoreAddon` context and the modules' classes; `types/Client.lua` is the client API core
  reads. `tools/typecheck.sh` checks every Lua file outside `tests/`, `tools/`, `docs/` and `.agents/` against them;
  CI installs LuaLS 3.19.1 by checksum, and the script refuses any other version.

## CI

`.github/workflows/ci.yml` runs on every PR and push to main: `deadcode`, `check` (luacheck, the specs, the native
tracker spec, StyLua, ruff, the `tools/` unit tests), `typecheck`, `project-rules` (the client load rule and the menu
rule), `packaged`, `secrets` and `workflows` (actionlint and zizmor over `.github` and the consumer workflow template).
`.github/workflows/forever-tools.yml` and `.github/workflows/forever-sim.yml` test the skill pack's tooling on every PR,
with no path filter, so they can be required checks. Every PR job runs on `ubuntu-24.04`, and LuaJIT and luacheck are
installed at that release's exact apt versions, so a runner image update cannot change them.
`.github/workflows/suite.yml` runs `tools/suite_load.py` daily and on demand (`gh workflow run suite.yml`): it clones
ForeverCore and every published addon's main and runs `tests/suite/suite_scenario.lua`, which loads ForeverCore first
with the addons that require it in one forever_sim client and calls `sim:exercise()`. It reads other repositories'
main, so it is not a PR job. Locally, `python3 tools/suite_load.py --root ..` runs it over the sibling checkouts as
they are.

## Agent skills

The suite-wide skills live here, in the one repo every addon already vendors from, so an addon repo carries only
what is specific to itself. Repo-specific skills (a repo's `release` checklist, its `tools/repo_rules.py`) stay
in that repo's `.agents/skills/`, never in `cjber/skills`; `cjber/skills` holds only skills that build repo-specific
logic out of a general rule.

| Skill | Load it when |
|---|---|
| `.agents/skills/wow-forever-addon/SKILL.md` | the shared standards pack (`WFA-*`), UI look, icon, docs, CI and release baseline |
| `.agents/skills/wow-addon-publish/SKILL.md` | publishing to CurseForge and Wago, or cutting a release |
| `.agents/skills/wow-retail-ui-style/SKILL.md` | drawing or auditing addon windows, frames and widgets |

Each addon declares `wow-forever-addon` under `## Standards` in its `AGENTS.md`, pinned to this repo. The pack's
tooling (`tooling/forever_tools`, `tooling/forever_sim`) is produced here and vendored byte for byte into the
consumers' `tools/`; edit it here, then run `sync.py update --source <this checkout>` in the consumer.

## Versions and releases

Every version needs a `CHANGELOG.md` entry before its `v*` tag. `.github/workflows/release.yml` waits for full CI on
the commit, checks it with `tools/release_check.py`, writes the version's notes with `tools/changelog.py`, and runs the
packager with `CF_API_KEY`, `WAGO_API_TOKEN` and `GITHUB_OAUTH`, so the GitHub release, CurseForge and Wago all get the
same words. CurseForge is the published description and gallery; Wago is an upload mirror with a fixed stub pointing
at CurseForge. A core version bump reaches consumers through the stores, since they require it; nothing is copied into
them. Raise `ForeverCore.API` only when the public table or `Register` breaks.

## Load order

`ForeverCore.toc` loads the module files, then `Expose.lua` last. Consumers declare `## Dependencies: ForeverCore`, so
the client loads ForeverCore before them and exactly one copy of each shared file runs. `ForeverCore.toc` has no
`OptionalDeps`: it does not adopt anything built by another addon.
