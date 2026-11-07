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
| `tests/tracker_header_menu_spec.lua` | the section-header menu contract |
| `tests/tracker_questie_spec.lua` | the Questie placement contract |
| `tests/tracker_combat_spec.lua` | the column stays still as combat starts and ends |
| `tests/tracker_geometry_spec.lua` | the column below the native quests across tracker anchors and scales |
| `tests/tracker_host_lock_spec.lua` | the grip and the Lock switch on the host |
| `tools/fetch_tracker_ui.py` | the pinned Blizzard tracker source the host spec runs against |
| `UI/Report.lua` | the shared report and issue composer |
| `tests/report_spec.lua` | the report and issue contract |
| `UI/ForeverFamily.lua` | the shared Forever-family link box |
| `tests/forever_family_spec.lua` | the link box contract |
| `Core/SafeCall.lua` | shared error capture used by the report window |
| `Core/MinimapButton.lua` | the shared minimap button: one rim angle per addon, the LibDBIcon art and the hide flag |
| `tests/minimap_button_spec.lua` | the button's register, click, drag and hide contract |
| `Core/PeerStats.lua` | bounded guild and group statistics transport and ranking |
| `tests/peer_stats_spec.lua` | transport, opt-out and ranking contract |
| `Core/LeaderboardsData.lua` | overall points, standing, the per-scope cache and the unit tooltip |
| `UI/Leaderboards.lua` | the shared Forever Leaderboards window and its board registrations |
| `tests/leaderboards_spec.lua` | registration, takeover, overall points, pinned row, weekly and tooltip contract |
| `tools/check_core_shared.py` | the vendoring map and the consumer's own drift check |
| `tools/check_client_load.py` | the client load rule: fonts the client defines, no Bindings.xml in a TOC (WFA-37) |
| `tools/blizzard_fonts.txt` | the font objects the client's UI defines, generated from the pinned Blizzard UI source |
| `tools/check_menu_scroll.py` | the menu rule: a menu built from a list scrolls (WFA-36) |
| `.github/workflows/core-shared-drift.yml` | runs the client load rule, the menu rule and the drift check on every PR and on a schedule; copied from `tools/core-shared-drift.yml` |

`tools/check_core_shared.py` lists every shared file with the consumers that carry it; the table above is the
tracker, report, family, peer-statistics and leaderboard set, and the map also holds the settings page, text, minimap
button and dead-code files.

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
   is the gate. Tracker files go to four addons; report, Forever-family and SafeCall files go to all five. Peer
   statistics and the leaderboards go to the six that share a statistics adapter: the four tracker addons, Field Guide
   and Commissions. The checker is green once every mapped consumer has the same bytes.

## When the addons disagree with the core

They cannot, in the steady state: `tools/check_consumers.py` fails on a byte difference, and that is the point. If a
consumer genuinely needs different behaviour, the change belongs behind the namespace, here, with the behaviour
switched by what that addon registers, so the four copies stay one file.

## Runtime: what a player sees

- One Forever addon installed, core absent: that addon builds the column from its own copy. Nothing changes.
- Several installed: the first to load publishes `ForeverTrackerHost`; the rest adopt it, so there is one column.
- Core installed too: `ForeverCore.toc` lists the five addons as `OptionalDeps`, so they load first and core adopts
  the column they built rather than starting a second one with settings nobody saved.

## Minimap buttons

Load `Core/MinimapButton.lua` before the addon builds its button. `ns.MinimapButton.Create(spec)` parents one button
to `Minimap` and registers it in the suite-wide ring; `ns.MinimapButton.Refresh()` re-reads every addon's hide flag
and saved angle, and `Destroy(button)` takes one out again. A spec supplies `name`, `icon`, `title`, optional
`binding` and `subtext`, `onClick`, and the addon's saved `settings` table. The angle is written to
`settings.minimapButtonAngle` and the hide flag is read from `settings.minimapButtonHidden`, unless the spec names its
own `angleKey`/`hiddenKey` or supplies `getShown`. A drag moves the button around the rim and saves the angle it
stopped on. Nothing here hooks or resizes a Blizzard frame.

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
receives and hides peers; it preserves recorded history. Enabling offers the snapshot again. Sharing
is opt-out: a missing saved setting (or a config without an `enabled` function) means on, only an
explicit `false` is off, and a missing peer table still means off. `instance:Shared()` returns a copy
of the validated peers, or an empty table while off.
`instance:Board(metric, subject, localValue, localEventUnix)` returns ranked rows with the personal
row included even while sharing is off.
`instance:WeekBoard(metric, subject, localValue, localEventUnix)` mirrors it with this week's progress: each value is
the current value minus the first value heard per sender, metric and subject since the weekly reset. The reset comes
from `C_DateAndTime.GetSecondsUntilWeeklyReset` when the client has it, else the last Tuesday 15:00 UTC. The player's
own baseline uses the same metric/subject layout under a reserved key, so the saved peer layout is unchanged and an
older table simply gains baselines when it loads.

The queue holds at most 512 payloads. Overflow keys are bounded by the snapshot's 2048-row limit and
refilled from that snapshot as capacity returns. Each addon retains at most 100 peers, 256 subjects
per metric and 1024 rows per peer. Use client-observed values and timestamps, and present absent
peer data as unknown. These boards compare what peers report; they cannot verify another client.

## Leaderboards

Load `Core/LeaderboardsData.lua` and then `UI/Leaderboards.lua`, and register one board before anything opens the
window:

```lua
ForeverLeaderboards:Register("guide", {
	title = "Adventure Guide Forever", -- the addon's name on its side tab and in its tooltip place
	icon = "Interface\\AddOns\\AdventureGuideForever\\media\\Icon",
	metric = "Quests turned in", -- the heading above the list
	order = 2, -- optional; tab order after Overall, registration order otherwise
	revision = function() -- the cache rebuilds when this counter moves
		return peers:Revision()
	end,
	board = function(scope) -- "week" or "all"
		local method = scope == "week" and "WeekBoard" or "Board"
		local rows = peers[method](peers, "quests", "all", total, changedAt)
		for _, row in ipairs(rows) do
			row.you, row.class, row.extra = row.self, classOf(row.name), nil
		end
		return rows
	end,
	sharing = function()
		return db.shareProgress
	end,
	setSharing = function(value)
		db.shareProgress = value
		peers:SetEnabled(value)
	end,
})
```

The addon sorts its rows. A row is `{ name =, class =, value =, extra =, you = }`: `you` marks the
player, `class` is a `RAID_CLASS_COLORS` key (or nil), `extra` is the grey value before the number
("377 total", "5 boards"), and `value` is the number in the right-hand column. For `scope == "week"`
the value is the delta the module draws as a green `+N`, so a PeerStats consumer uses `WeekBoard`.

Overall is cached per scope. A PeerStats board passes `revision = function() return peers:Revision() end`;
`Revision` rises when a stored peer row, the player's own snapshot or the sharing state changes. The
cache rebuilds only when the summed revisions, the scope, the registered board list or the current week
start changes, and the window and a tooltip hover read the same cache. A board without a revision is
rebuilt when any other board or the week changes it.

The first copy to load publishes `ForeverLeaderboards`; later copies join it, and a copy with a higher
`LEADERBOARDS_VERSION` takes over with every registration already made. `:Open(key)` shows one board
(Overall when the key is omitted or unknown) and `:Toggle()` shows or hides the window; `/forever` and
`/flb` open it too, and `/forever` stays with a consumer that already claimed it. Overall is first on
the side rail and sums 10, 8, 6, 5, 4, 3, 2 and 1 points for the first eight places on each board;
its second column counts the boards that scored. The window is an ordinary addon frame: it is built on
first open (never at login), has no `OnUpdate`, is not protected, writes nothing to chat and draws no
glow. The "Share my progress" switch is the selected board's own `sharing`/`setSharing`; on Overall it
turns every registered board that offers one on or off together. Sharing is opt-out: a missing or nil
setting reads as checked, and only an explicit `false` unchecks it.

The unit tooltip gets a gold line with the player's overall place and a grey line of their per-addon
places for anyone on a registered board. Someone the boards know but who places nowhere gets one
"Uses Forever addons" line. The hook is installed once, by the copy that publishes the global, and a
newer copy takes it over. Nothing in the window knows an addon: it reads the registered specs and
`ns.L` only. A consumer's `types/Client.lua` declares the client widgets this file reads
(`CreateDataProvider`, `CreateScrollBoxListLinearView`, `ScrollUtil`, `ScrollBoxConstants` and
`RAID_CLASS_COLORS`), as core's does.
