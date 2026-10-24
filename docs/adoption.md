# How a Forever addon adopts the core

The shared files are vendored, not linked. Each addon carries a byte-identical copy of the same files at the same
paths, so every addon still works on its own with nothing else installed, and the core's fixes reach players through
the addon they already have.

## What is shared

| File | What it is |
|---|---|
| `UI/TrackerHost.lua` | the private tracker column: layout, combat, Edit Mode, the `ForeverTrackerHost` global |
| `UI/TrackerLock.lua` | the grip and the Lock switch, loaded before the host |
| `UI/TrackerOrder.lua` | section order (`uiOrder`, then attach order) |
| `UI/TrackerQuestie.lua` | Questie's quest list, so the column steps beside it |
| `tests/tracker_host_spec.lua` | the native integration contract, run against Blizzard's own tracker source |
| `tests/tracker_host_harness.lua` | the tracker test harness shared by the four tracker consumers |
| `tests/tracker_questie_spec.lua` | the Questie placement contract |
| `tools/fetch_tracker_ui.py` | the pinned Blizzard tracker source the host spec runs against |
| `UI/Report.lua` | the shared report and issue composer |
| `tests/report_spec.lua` | the report and issue contract |
| `UI/ForeverFamily.lua` | the shared Forever-family link box |
| `tests/forever_family_spec.lua` | the link box contract |
| `Core/SafeCall.lua` | shared error capture used by the report window |

Everything addon specific arrives through the namespace, never through an edit to these files:
`ns.TrackerHostSettings()` returns the saved settings, `ns.ReportTitle` supplies the report's localized title,
`ns.L` carries the player's language, and a section is handed over with `ForeverTrackerHost.Attach(module)`.

## Why the paths are `UI/...` in a repo whose own addon is `ForeverCore`

Suite convention is flat Lua at the repo root, and this repo is the deliberate exception. Keeping the files where
every consumer keeps them makes vendoring a pure copy, and lets a consumer's spec, which loads `UI/TrackerHost.lua`
by path, run here unchanged.

## Changing a shared file

1. Change it here. Both specs and `luacheck` and `stylua` must pass; the host spec needs
   `python3 tools/fetch_tracker_ui.py` first.
2. Bump `CHANGELOG.md` and the tag when the change is worth a release of its own.
3. `python3 tools/sync_consumers.py <checkouts>` copies it into each checkout under `<checkouts>`.
4. One PR per consumer with all the shared files in it. Their own CI (luacheck, stylua, the specs, the package check)
   is the gate. Tracker files go to four addons; report, Forever-family and SafeCall files go to all five. The checker is green once every mapped consumer has the same bytes.

## When the addons disagree with the core

They cannot, in the steady state: `tools/check_consumers.py` fails on a byte difference, and that is the point. If a
consumer genuinely needs different behaviour, the change belongs behind the namespace, here, with the behaviour
switched by what that addon registers, so the four copies stay one file.

## Runtime: what a player sees

- One Forever addon installed, core absent: that addon builds the column from its own copy. Nothing changes.
- Several installed: the first to load publishes `ForeverTrackerHost`; the rest adopt it, so there is one column.
- Core installed too: `ForeverCore.toc` lists the five addons as `OptionalDeps`, so they load first and core adopts
  the column they built rather than starting a second one with settings nobody saved.
