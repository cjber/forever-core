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
| `Core/PeerStats.lua` | bounded guild and group statistics transport and ranking |
| `tests/peer_stats_spec.lua` | transport, opt-out and ranking contract |
| `tools/check_core_shared.py` | the vendoring map and the consumer's own drift check |
| `.github/workflows/core-shared-drift.yml` | runs that check on every PR and on a schedule; copied from `tools/core-shared-drift.yml` |

`tools/check_core_shared.py` lists every shared file with the consumers that carry it; the table above is the
tracker, report and family set, and the map also holds the settings page, text, micro button and dead-code files.

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

## Peer statistics

Load `Core/PeerStats.lua` before the addon's statistics adapter. Create one instance with
`ns.PeerStats.New(config)`: `addon` is the wire identifier, `enabled()` reads the saved sharing switch,
`db()` returns the peer table, `snapshot()` returns this character's observed rows, and `metrics`
allowlists the addon's metric names. A metric declares `subject = "all"`, `"numeric"` or `"qualified"`;
`first = true` ranks its earliest timestamp. Other metrics rank the highest cumulative value.
Each snapshot row supplies `metric`, `subject`, `value` and `eventUnix`. Cumulative rows may omit the
timestamp; the first observation of each changed value gets a timestamp. First-completion rows require
an observed timestamp.

The adapter migrates its own saved layout to `sender -> metric -> subject -> { value, eventUnix }`
before registering. It owns metric definitions, recording, labels, settings and UI. The shared module
validates names and rows, bounds saved peers and incoming traffic, and sends only local snapshot rows
over `WFAStats` wire version 1 on guild and group channels. Received rows are never relayed. All loaded
copies share one versioned `ForeverPeerStats` manager, event frame and throttled queue.

Call `instance:Sync()` after the character's metrics change. For a sharing toggle, save the setting
first, then call `instance:SetEnabled(value)`. Disabling cancels pending sends immediately, blocks
receives and hides peers; it preserves recorded history. Enabling offers the snapshot again. Missing
settings or a missing peer table mean sharing is off. `instance:Shared()` returns a copy of the
validated peers, or an empty table while off. `instance:Board(metric, subject, localValue, localEventUnix)`
returns ranked rows with the personal row included even while sharing is off.

The queue holds at most 512 payloads. Overflow keys are bounded by the snapshot's 2048-row limit and
refilled from that snapshot as capacity returns. Each addon retains at most 100 peers, 256 subjects
per metric and 1024 rows per peer. Use client-observed values and timestamps, and present absent
peer data as unknown. These boards compare what peers report; they cannot verify another client.
