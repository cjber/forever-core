---
name: sift-project
description: Project profile for sift in Forever Core: the exact quality-gate and evidence commands, live roots that must never be deleted as dead code, exclusions, conventions and risk order. Load before running sift or any code-quality, cleanup or dead-code work in this repository.
---

# sift project profile: Forever Core

Forever Core is the shared floor under the WoW: Forever addon suite (Interface 16001, Lua 5.1 sandbox):
the one objective-tracker column the addons dock into, its grip and Lock switch, the section order, and the
Questie bridge. It ships as its own addon, `ForeverCore.toc`. The tracker, error capture, report and
Forever-family files here are the source of truth and are vendored byte for byte into the consumer addons by
`tools/sync_consumers.py`; a fix lands here first and is copied out.

## Gate

Run in order from the repository root. All must pass before and after any audit slice.

| Step | Command | Pass means |
|---|---|---|
| Format (Lua) | `stylua --check .` | exit 0 (StyLua 2.5.2) |
| Lint (Lua) | `luacheck .` | 0 warnings / 0 errors |
| Specs | `for s in tests/*_spec.lua; do luajit "$s" || exit 1; done` | every spec exits 0 |
| Native tracker | `python3 tools/fetch_tracker_ui.py && TRACKER_UI_ROOT=tools/.cache/tracker-ui luajit tests/tracker_host_spec.lua` | passes; runs Blizzard's tracker source at the pinned revision |
| Vendoring | `python3 tools/check_consumers.py` | every consumer's vendored copy matches this repo |
| Python | `ruff check tools && ruff format --check tools` | exit 0 (Ruff 0.16.8) |
| Dead code | `python3 tools/deadcode.py --check` | exit 0 |
| Package | BigWigs packager `-d -z` then `python3 tools/check_package.py` | every loaded file ships, no development folder does |
| Sift | `python3 .sift/gate.py --base origin/main && python3 .sift/agents.py check` | 0 findings; skills match their standards |

## Live roots

- `ForeverCore.toc` is the client file list and load order; a file it does not list never runs.
- `UI/TrackerHost.lua`, `UI/TrackerLock.lua`, `UI/TrackerOrder.lua`, `UI/TrackerQuestie.lua` are vendored
  into the consumer addons byte for byte. Their public surface is read by those copies and their specs.
- `Core/SafeCall.lua`, `UI/Report.lua`, `UI/ForeverFamily.lua` are shared error capture, report and family UI,
  vendored into all five consumer addons at the same paths.
- `Expose.lua` publishes the public `ForeverCore` table and `/fcore`; it is the last file the TOC loads.
- `types/` holds the LuaLS tracker contract declarations; consumers' `types/` stubs mirror it.
- The paths mirror a consumer repo on purpose (`UI/TrackerHost.lua` stays at that path so the vendored copy
  is a pure copy). Never flatten or re-home a shared file.

## Exclusions

- `tools/.cache/` and `.release/` are build output, never source.
- `docs/handoff/` holds briefs, audit notes and the ledger; they are prose records, not code.

## Conventions

- Everything shared reads addon-specific values through the namespace (`ns.TrackerHostSettings`,
  `ns.ReportTitle`, `ns.L`). Never bend a shared file toward one addon.
- Never edit a vendored copy in a consumer repo; change it here and run `tools/sync_consumers.py ~/wow`.
- Do not hand-write test doubles for the tracker: `tools/fetch_tracker_ui.py` fetches Blizzard's real source at a
  pinned revision, so the integration spec exercises the client's own code.

## Risk order

1. The vendored copies drifting from this repo (run `tools/check_consumers.py` first).
2. Load-order changes: `UI/TrackerLock.lua` must load before the host; `Expose.lua` last.
3. Anything that moves a shared file to a new path, which silently breaks every consumer's spec.
