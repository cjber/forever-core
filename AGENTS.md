# AGENTS.md

Forever Core is the shared floor under the WoW: Forever addon suite (Interface 16001): the one objective-tracker
column the addons dock into, the grip and Lock switch that move it, the section order that stacks them, and the
Questie bridge that keeps the column out from under Questie's quest list. It is GPL-3.0-or-later and ships as its own
addon, `ForeverCore`.

## The two rules that matter

1. **The shared files are the source of truth, and nothing here is addon specific.** Tracker files are vendored byte
   for byte into adventure-guide-forever, legacy-forever, shortest-path-forever and skillup-forever. Error capture,
   report and Forever-family files are vendored into all five consumer addons at the same paths
   (`Core/SafeCall.lua`, `UI/Report.lua` and `UI/ForeverFamily.lua`; see `docs/adoption.md`). A fix lands here first, then `tools/sync_consumers.py` copies it out. Never edit a copy in a
   consumer repo and never bend these files toward one addon's needs: they read everything addon specific through the
   namespace (`ns.TrackerHostSettings`, `ns.ReportTitle`, `ns.L`), by design.
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
python3 tools/gen_legacy_chrome.py        # regenerate the asset checker's pinned-build data
python3 tools/sync_consumers.py ..        # copy this repo's shared files into local checkouts
ruff check tools && ruff format --check tools
python3 -m unittest discover -s tools -p "test_*.py"
python3 .sloppatrol/gate.py --base origin/main && python3 .sloppatrol/agents.py check
```

`tests/tracker_host_spec.lua` is the native integration spec: it runs Blizzard's real objective-tracker source,
fetched at a pinned revision by `tools/fetch_tracker_ui.py`, against this host. The other tracker specs stub everything
and run anywhere.

## Layout

- `Core.lua`: ForeverCore's own install of the host's settings (`ns.TrackerHostSettings`), in `ForeverCoreDB`.
- `Expose.lua`: the public `ForeverCore` table and `/fcore`; the last file the TOC loads, because it publishes what
  the shared modules built.
- `Core/SafeCall.lua`, `UI/Report.lua` and `UI/ForeverFamily.lua`: shared error capture, report, issue and link UI vendored into all five consumers.
- `tests/report_spec.lua` and `tests/forever_family_spec.lua`: their contract specs.
- `UI/TrackerHost.lua`: the private tracker column, its layout, combat and Edit Mode handling, and the
  `ForeverTrackerHost` global the first-loaded Forever addon publishes and the rest adopt.
- `UI/TrackerLock.lua`: the grip and the Lock switch, which must load before the host.
- `UI/TrackerOrder.lua`: the section order (`uiOrder`, then attach order).
- `UI/TrackerQuestie.lua`: Questie's quest list, so the column steps beside it instead of under it.
- `Locales/enUS.lua`: the phrases the shared files themselves draw. A consumer keeps its own locale file for its own
  copy; the phrases there are the only ones core owns.
- The suite's ownership boundaries live in `docs/handoff/boundaries.md`, with the rest of the suite notes in
  `docs/handoff/` (handoff briefs, audit notes, the ledger). Read `docs/handoff/boundaries.md` before assigning a
  feature or moving code between addons.
- `tools/check_core_shared.py`: the vendoring map (`VENDORED`, which consumer carries which file) and the consumer-side
  check, vendored into every consumer. In a consumer it compares its copies with core main; with `--base REF` it
  checks only the vendored files `REF...HEAD` changes, so a hand edit fails a PR while a lag behind core does not.
- `tools/check_client_load.py`: the client load rule, vendored into every consumer with its font list
  `tools/blizzard_fonts.txt`: every font object the addon's Lua or XML inherits is one the client's UI or the addon
  defines, and no TOC lists Bindings.xml. Regenerate the list from the pinned Blizzard UI source with
  `python3 tools/check_client_load.py --blizzard-ui ../wow-handoff/blizzard-ui`; `tools/test_check_client_load.py` is
  its spec.
- `tools/check_menu_scroll.py`: the menu rule, vendored into every consumer: a menu description that gets entries in
  a loop calls `SetScrollMode` in the same function, or the loop says why it stays short (`-- menu-scroll-ok:
  <reason>`). It reads Lua through the skill pack's `forever_tools/lua.py` lexer; `tools/test_check_menu_scroll.py`
  is its spec.
- `tools/gen_legacy_chrome.py`: regenerates the shared checker's pinned-build data, `forever_tools/legacy_chrome.txt`
  (old chrome by FileDataID) and `forever_tools/interface_paths.txt` (the known interface-path set), from the
  wago.tools listfile for 1.60.1.70124. `tools/check_assets.py` is the entry point over this repo; the age rule
  itself lives in the skill pack's `forever_tools/assets.py`, and `tools/test_check_assets.py` is its spec.
- `tools/core-shared-drift.yml`: the drift workflow each consumer keeps under `.github/workflows/`, which runs the client load
  rule, the menu rule and that check on every PR (`--base`) and on a schedule (the full check). Its `core-shared` job is required in
  every consumer, so both rules gate every consumer PR with no change to the consumer's own CI. It lives outside `.github/workflows` so it never runs
  here; the `workflows` CI job lints it.
- `tools/check_consumers.py`, `tools/sync_consumers.py`: the vendoring gate and its fix, both reading the map above.
  `.github/workflows/drift.yml` runs the checker on a schedule only, so a core change never blocks on consumer release
  timing.
- `types/`: LuaLS declarations for the tracker contract and the client globals the shared files read.
  `tools/typecheck.sh` checks every Lua file outside `tests/`, `tools/`, `docs/` and `.agents/` against them; CI
  installs LuaLS 3.19.1 by checksum, and the script refuses any other version.

## CI

`.github/workflows/ci.yml` runs on every PR and push to main: `deadcode`, `check` (luacheck, the specs, the native
tracker spec, StyLua, ruff, the `tools/` unit tests, the client load rule and the menu rule), `typecheck`, `project-rules`, `packaged`, `secrets` and
`workflows` (actionlint and zizmor over `.github` and the consumer workflow template).
`.github/workflows/forever-tools.yml` and `.github/workflows/forever-sim.yml` test the skill pack's tooling on every PR,
with no path filter, so they can be required checks. Every PR job runs on `ubuntu-24.04`, and LuaJIT and luacheck are
installed at that release's exact apt versions, so a runner image update cannot change them.

## Agent skills

The suite-wide skills live here, in the one repo every addon already vendors from, so an addon repo carries only
what is specific to itself. Repo-specific skills (a repo's `release` checklist, its `sloppatrol-project` gate profile) stay
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
