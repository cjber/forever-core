# AGENTS.md

Forever Core is the shared floor under the WoW: Forever addon suite (Interface 16001): the one objective-tracker
column the addons dock into, the grip and Lock switch that move it, the section order that stacks them, and the
Questie bridge that keeps the column out from under Questie's quest list. It is GPL-3.0-or-later and ships as its own
addon, `ForeverCore`.

## The two rules that matter

1. **The shared files are the source of truth, and nothing here is addon specific.** Tracker files are vendored byte
   for byte into adventure-guide-forever, legacy-forever, shortest-path-forever and skillup-forever. Report and
   Forever-family files are vendored into all five consumer addons at the same paths
   (`docs/adoption.md`). A fix lands here first, then `tools/sync_consumers.py` copies it out. Never edit a copy in a
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
python3 tools/check_consumers.py          # every consumer's copy matches this repo
python3 tools/sync_consumers.py ~/wow     # copy this repo's shared files into local checkouts
ruff check tools && ruff format --check tools
```

`tests/tracker_host_spec.lua` is the native integration spec: it runs Blizzard's real objective-tracker source,
fetched at a pinned revision by `tools/fetch_tracker_ui.py`, against this host. The other four specs stub everything
and run anywhere.

## Layout

- `Core.lua`: ForeverCore's own install of the host's settings (`ns.TrackerHostSettings`), in `ForeverCoreDB`.
- `Expose.lua`: the public `ForeverCore` table and `/fcore`; the last file the TOC loads, because it publishes what
  the shared modules built.
- `UI/Report.lua` and `UI/ForeverFamily.lua`: shared report, issue and link UI vendored into all five consumers.
- `tests/report_spec.lua` and `tests/forever_family_spec.lua`: their contract specs.
- `UI/TrackerHost.lua`: the private tracker column, its layout, combat and Edit Mode handling, and the
  `ForeverTrackerHost` global the first-loaded Forever addon publishes and the rest adopt.
- `UI/TrackerLock.lua`: the grip and the Lock switch, which must load before the host.
- `UI/TrackerOrder.lua`: the section order (`uiOrder`, then attach order).
- `UI/TrackerQuestie.lua`: Questie's quest list, so the column steps beside it instead of under it.
- `Locales/enUS.lua`: the phrases the shared files themselves draw. A consumer keeps its own locale file for its own
  copy; these four phrases are the only ones core owns.
- The suite's ownership boundaries live in `docs/handoff/boundaries.md`, with the rest of the suite notes in
  `docs/handoff/` (handoff briefs, audit notes, the ledger). Read `docs/handoff/boundaries.md` before assigning a
  feature or moving code between addons.
- `tools/check_consumers.py`, `tools/sync_consumers.py`: the vendoring gate and its fix.
- `types/`: LuaLS declarations for the tracker contract.

## Agent skills

The suite-wide skills live here, in the one repo every addon already vendors from, so an addon repo carries only
what is specific to itself. Repo-specific skills (a repo's `release` checklist, its `sift-project` gate profile) stay
in that repo's `.agents/skills/`, never in `cjber/skills`; `cjber/skills` holds only skills that build repo-specific
logic out of a general rule (how `sift` functions, how `wowmock` renders).

| Skill | Load it when |
|---|---|
| `.agents/skills/wow-forever-addon/SKILL.md` | the shared standards pack (`WFA-*`), UI look, icon, docs, CI and release baseline |
| `.agents/skills/wow-addon-publish/SKILL.md` | publishing to CurseForge and Wago, or cutting a release |
| `.agents/skills/wow-retail-ui-style/SKILL.md` | drawing or auditing addon windows, frames and widgets |

Each addon declares `wow-forever-addon` under `## Standards` in its `AGENTS.md`, pinned to this repo. The pack's
tooling (`tooling/forever_tools`, `tooling/forever_sim`) is produced here and vendored byte for byte into the
consumers' `tools/`; edit it here, then run `sync.py update --source <this checkout>` in the consumer.

## Versions and releases

Every version needs a `CHANGELOG.md` entry before its `v*` tag. `release.yml` publishes the GitHub release with the
packager; there is no CurseForge or Wago page for a library addon, so no store tokens are involved. A core version
bump is adopted by consumers at their own pace: `tools/sync_consumers.py` in this repo, then one PR per consumer,
with `tools/check_consumers.py` going green once all four have moved.

## Load order

`ForeverCore.toc` lists the five Forever addons as `OptionalDeps`, which makes WoW load them before core when they
are installed. That ordering is the point: the addon that already owns the player's tracker settings builds the
column, and core adopts the published `ForeverTrackerHost` instead of starting a second one with settings nobody
saved. Do not remove those OptionalDeps.
