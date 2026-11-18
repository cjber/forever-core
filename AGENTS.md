# AGENTS.md

ForeverCore is the shared library under the WoW: Forever addon suite (Interface 16001, GPL-3.0-or-later). It is
its own addon, `ForeverCore`; every Forever addon declares `## OptionalDeps: ForeverCore`, so the client loads it
first when installed and the addon still loads without it. It owns the one tracker column the suite docks into,
the section order, the report and issue windows, the error journal and debug log, the world map quest log tabs,
the Professions tabs and the settings-page chrome. It also holds the dev tooling vendored into each addon and
the suite skills in `.agents/skills`.

## Rules that matter

1. **This repo is the only copy of the shared runtime.** Nothing here is addon specific. A consumer reads the
   runtime through the `ForeverCore` table and `ForeverCore.Register`; never copy a runtime file into a consumer
   or bend one toward a single addon. Addon-specific behaviour arrives through `Register` or the module API.
2. **Shared files keep their consumer-visible paths** (`UI/TrackerHost.lua`, `Core/SafeCall.lua`, ...): flat Lua at
   the root, so a consumer's `loadfile("UI/TrackerHost.lua")` still finds core's source when its spec runs here.
3. **The native objective tracker is used only as an anchor:** `TrackerHost` anchors to `ObjectiveTrackerFrame`'s
   `TOPLEFT` and never reads its contents, visibility or geometry nor writes to it (no alpha, hook, Show, Hide,
   SetPoint). `tests/tracker_host_spec.lua` scans the TOC's files for a breach.
4. **Vendored tooling is edited here only.** `tools/forever_tools` and `tools/forever_sim` (from
   `.agents/skills/wow-forever-addon/tooling`) reach consumers with `python3 tools/sync_consumers.py ..`, never by
   editing a consumer's copy. `tools/check_core_shared.py` fails a PR that does.
5. **Raise `ForeverCore.API`** only when the public table or `Register` breaks. A core release reaches consumers
   through the stores: nothing is copied into them.
6. **Game-client checks go through the `wow in-game` agent.** Send it an `INGAME` request
   (`.agents/skills/wow-forever-addon/in-game.md#requesting-a-check`); never run `tools/headless/forever_client.py`
   or start the game, Battle.net or Wine yourself.

## Commands

```sh
tools/gate             # the gate: luacheck, StyLua, every spec in parallel (~1 s), ruff over tools/
tools/gate --changed   # lint only files changed against origin/main; ruff only when tools/ Python changed
bash tools/typecheck.sh   # LuaLS at tools/toolchain.json's pin (CI runs it)
```

The full command list, the tool inventory and what each CI job runs are in
[`docs/commands-and-ci.md`](docs/commands-and-ci.md); every runtime file and tool, with what it owns, is in
[`docs/layout.md`](docs/layout.md). Read `docs/handoff/boundaries.md` before assigning a feature or moving code
between addons. Repo-specific skills stay in that repo's `.agents/skills/`, never in `cjber/skills`. The native
tracker specs run against Blizzard's real source: `python3 tools/fetch_tracker_ui.py`, then
`TRACKER_UI_ROOT=tools/.cache/tracker-ui luajit tests/tracker_reflow_spec.lua` (the reflow spec skips without it).

## Releases

Each version needs changelog fragments consumed into a `CHANGELOG.md` entry before its `v*` tag
(`python3 tools/changelog.py release X.Y.Z` in the preparation commit); no other PR edits `CHANGELOG.md`.
`release.yml` waits for full CI and a green `headless-smoke` status on the exact commit, then packages for
GitHub and CurseForge. A change to the update notice or a locale needs `.visual-proof.json` from an `INGAME ...
kind: proof` request (`flows: update notice=<slash or Lua file>`). A core release re-releases every consumer
through `release-consumers.yml`. Load order: `ForeverCore.toc` loads the modules, then `Expose.lua` last; it has
no `OptionalDeps`. Skills for the suite (`wow-forever-addon`, `wow-addon-publish`, `wow-retail-ui-style`,
`wow-mock-screenshots`, `wow-visual-audit`, `foreverauras`) live in
`.agents/skills`; each addon pins them here.

## Standards

- `repo-standards`: the RS-* requirements every cjber and agent-labs-dev repo meets; its `audit.py` checks this repo.
- `wow-forever-addon`: the WFA-* addon rules, which win where stricter.
