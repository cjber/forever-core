local _, ns = ...

-- English phrases are the keys, so a phrase with no translation reads as English. These are the phrases core's own
-- files draw: the tracker column, its grip, the report and issue windows, the debug log, the family page, the
-- minimap notice, the quest list and the settings page.
---@type table<string, string>
local L = setmetatable({}, {
	__index = function(_, key)
		return key
	end,
})
ns.L = L

L["%s (%s)"] = "%s (%s)"
L["%s and %s"] = "%s and %s"
L["%s, %s and %s"] = "%s, %s and %s"
L["%s, %s, %s and %d more"] = "%s, %s, %s and %d more"
L["+%d more"] = "+%d more"
L[", "] = ", "
L["%d contributions"] = "%d contributions"
L["%d yd"] = "%d yd"
L["%s (last %d):"] = "%s (last %d):"
L["%s: no lines yet."] = "%s: no lines yet."
L["1 ms"] = "1 ms"
L["5 ms"] = "5 ms"
L["10 ms"] = "10 ms"
L["50 ms"] = "50 ms"
L["100 ms"] = "100 ms"
L["Addon"] = "Addon"
L["Adds a macro window with every macro in one list, a mono editor with live checks, and history."] =
	"Adds a macro window with every macro in one list, a mono editor with live checks, and history."
L["All addons"] = "All addons"
L["Application"] = "Application"
L["Attach to quest tracker"] = "Attach to quest tracker"
L["Bug"] = "Bug"
L["Bug: "] = "Bug: "
L["Close"] = "Close"
L["Copy issue link"] = "Copy issue link"
L["Copy link"] = "Copy link"
L["Copy report"] = "Copy report"
L["Copy the address, then open it in your browser."] = "Copy the address, then open it in your browser."
L["Debug log is already on and pinned for this character."] = "Debug log is already on and pinned for this character."
L["Debug log is off and unpinned."] = "Debug log is off and unpinned."
L["Debug log is off for this session; it is still pinned."] = "Debug log is off for this session; it is still pinned."
L["Debug log is off."] = "Debug log is off."
L["Debug log is on and pinned for this character."] = "Debug log is on and pinned for this character."
L["Debug log is on for this session."] = "Debug log is on for this session."
L["%d more rows not shown."] = "%d more rows not shown."
L["Debug capture is on: /forever debug off stops it."] = "Debug capture is on: /forever debug off stops it."
L["Debug capture is on. Attach the files in the client's Logs folder to your report. Turn it off with /forever debug off."] =
	"Debug capture is on. Attach the files in the client's Logs folder to your report. Turn it off with /forever debug off."
L["Debug capture is on. The client's logs are in its Logs folder; turn it off with /forever debug off."] =
	"Debug capture is on. The client's logs are in its Logs folder; turn it off with /forever debug off."
L["Debug capture is off and the client's settings are back; the debug log is off and unpinned."] =
	"Debug capture is off and the client's settings are back; the debug log is off and unpinned."
L["Debug capture could not start because ForeverCore has not finished loading."] =
	"Debug capture could not start because ForeverCore has not finished loading."
L["Don't suggest this again"] = "Don't suggest this again"
L["Drag to move"] = "Drag to move"
L["Feature request"] = "Feature request"
L["Feature request: "] = "Feature request: "
L["ForeverCore"] = "ForeverCore"
L["Forever addons"] = "Forever addons"
L["Forever quest list"] = "Forever quest list"
L["Forever tracker"] = "Forever tracker"
L["Hide this section"] = "Hide this section"
L["Inspired by"] = "Inspired by"
L["Installed, turned off"] = "Installed, turned off"
L["Keeps a cosmetic journal of the creatures you kill, zone by zone."] =
	"Keeps a cosmetic journal of the creatures you kill, zone by zone."
L["Lists your commission turn-ins, the materials in your bags and the next NPC to visit."] =
	"Lists your commission turn-ins, the materials in your bags and the next NPC to visit."
L["Lists your tracked quests in the Forever column, ready to turn in first, then this zone, then the rest by zone, nearest first. The game's own quest list is collapsed while this is on."] =
	"Lists your tracked quests in the Forever column, ready to turn in first, then this zone, then the rest by zone, nearest first. The game's own quest list is collapsed while this is on."
L["Lock the tracker"] = "Lock the tracker"
L["Last"] = "Last"
L["Memory KB"] = "Memory KB"
L["Memory: not available on this client."] = "Memory: not available on this client."
L["No addon has attached its log yet."] = "No addon has attached its log yet."
L["No one is listed yet."] = "No one is listed yet."
L["Not installed"] = "Not installed"
L["On"] = "On"
L["Open"] = "Open"
L["Picks quests for your level and plans them into one journey."] =
	"Picks quests for your level and plans them into one journey."
L["Peak"] = "Peak"
L["Performance (read when this window opened):"] = "Performance (read when this window opened):"
L["Performance: not available on this client."] = "Performance: not available on this client."
L["Performance: the client's add-on profiler is off."] = "Performance: the client's add-on profiler is off."
L["Plans the cheapest route to your next profession rank."] = "Plans the cheapest route to your next profession rank."
L["Plans the quickest way anywhere and guides you there, with live boat and zeppelin times."] =
	"Plans the quickest way anywhere and guides you there, with live boat and zeppelin times."
L["Players"] = "Players"
L["Quest automation, rare alerts and merchant handling for the default UI."] =
	"Quest automation, rare alerts and merchant handling for the default UI."
L["Ready to turn in"] = "Ready to turn in"
L["Recent"] = "Recent"
L["Report a bug or request a feature"] = "Report a bug or request a feature"
L["Session"] = "Session"
L["Show a quiet line where one of my other Forever addons would help. Only for addons you don't have."] =
	"Show a quiet line where one of my other Forever addons would help. Only for addons you don't have."
L["Shows the Legacy challenges you can advance in each zone."] =
	"Shows the Legacy challenges you can advance in each zone."
L["Suggest my other Forever addons"] = "Suggest my other Forever addons"
L["Thanks"] = "Thanks"
L["Thanks to %s"] = "Thanks to %s"
L["The Forever addons are free, with nothing locked behind them. If they help, you can buy me a coffee."] =
	"The Forever addons are free, with nothing locked behind them. If they help, you can buy me a coffee."
L["The link is selected. Press Ctrl+C (Cmd+C on a Mac), then paste into a browser; GitHub opens a filled-in issue."] =
	"The link is selected. Press Ctrl+C (Cmd+C on a Mac), then paste into a browser; GitHub opens a filled-in issue."
L["The players who helped each Forever addon."] = "The players who helped each Forever addon."
L["The text is selected. Press Ctrl+C (Cmd+C on a Mac) to copy it, then paste it into your bug report."] =
	"The text is selected. Press Ctrl+C (Cmd+C on a Mac) to copy it, then paste it into your bug report."
L["The tracker is locked. Turn off Lock the tracker to move it."] =
	"The tracker is locked. Turn off Lock the tracker to move it."
L["This addon"] = "This addon"
L["Title"] = "Title"
L["Tracker background"] = "Tracker background"
L["Tracker"] = "Tracker"
L["Click to %s"] = "Click to %s"
L["Right-click for options"] = "Right-click for options"
L["Unavailable in combat"] = "Unavailable in combat"
L["Usage: /forever debug, /forever debug on, /forever debug off, /forever debug pin, /forever debug show"] =
	"Usage: /forever debug, /forever debug on, /forever debug off, /forever debug pin, /forever debug show"
L["Use the game's quest list"] = "Use the game's quest list"
L["What happened, or what you would like"] = "What happened, or what you would like"
L.MINIMAP_UNAVAILABLE = "Minimap unavailable; skipping custom button."
L["MENU_BACK"] = "Back"
L["%s (%d)"] = "%s (%d)"
L["%s %d/%d"] = "%s %d/%d"
L["Abandon"] = "Abandon"
L["Abandoning a quest is not available."] = "Abandoning a quest is not available."
L["Collapse"] = "Collapse"
L["Expand"] = "Expand"
L["Focus"] = "Focus"
L["Stop focusing"] = "Stop focusing"
L["Objectives"] = "Objectives"
L["Open Quest Details"] = "Open Quest Details"
L["Hide Quest Details"] = "Hide Quest Details"
L["Open Quest Map"] = "Open Quest Map"
L["Quest"] = "Quest"
L["Quests"] = "Quests"
L["Route with Shortest Path"] = "Route with Shortest Path"
L["Shortest Path is not loaded."] = "Shortest Path is not loaded."
L["Shortest Path could not plan this route."] = "Shortest Path could not plan this route."
L["There is no map pin for this quest."] = "There is no map pin for this quest."
L["There is no quest link to share."] = "There is no quest link to share."
L["The world map is not available."] = "The world map is not available."
L["The quest log is not available."] = "The quest log is not available."
L["Untrack"] = "Untrack"
L["Share Quest"] = "Share Quest"
L["Share in Chat"] = "Share in Chat"
L["fold this zone"] = "fold this zone"
L["unfold this zone"] = "unfold this zone"
L["focus this quest"] = "focus this quest"
