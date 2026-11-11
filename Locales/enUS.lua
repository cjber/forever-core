local _, ns = ...

-- English phrases are the keys, so a phrase with no translation reads as English. These are the phrases core's own
-- files draw: the tracker column, its grip, the report and issue windows, the debug log, the family page, the
-- leaderboards, the minimap notice, the quest list and the settings page.
---@type table<string, string>
local L = setmetatable({}, {
	__index = function(_, key)
		return key
	end,
})
ns.L = L

L["+%d more"] = "+%d more"
L[", "] = ", "
L["(you)"] = "(you)"
L["%d player from your guild and group"] = "%d player from your guild and group"
L["%d player you've met"] = "%d player you've met"
L["%d players from your guild and group"] = "%d players from your guild and group"
L["%d players you've met"] = "%d players you've met"
L["%d yd"] = "%d yd"
L["%s (last %d):"] = "%s (last %d):"
L["%s: no lines yet."] = "%s: no lines yet."
L["1st"] = "1st"
L["2nd"] = "2nd"
L["3rd"] = "3rd"
L["4th"] = "4th"
L["5th"] = "5th"
L["6th"] = "6th"
L["7th"] = "7th"
L["8th"] = "8th"
L["Adds a macro window with every macro in one list, a mono editor with live checks, and history."] =
	"Adds a macro window with every macro in one list, a mono editor with live checks, and history."
L["All time"] = "All time"
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
L["Don't suggest this again"] = "Don't suggest this again"
L["Drag to move"] = "Drag to move"
L["Feature request"] = "Feature request"
L["Feature request: "] = "Feature request: "
L["Forever Core"] = "Forever Core"
L["Forever Leaderboards"] = "Forever Leaderboards"
L["Forever addons"] = "Forever addons"
L["Forever quest list"] = "Forever quest list"
L["Forever standing"] = "Forever standing"
L["Forever tracker"] = "Forever tracker"
L["Forever: %s overall"] = "Forever: %s overall"
L["Forever: %s overall this week"] = "Forever: %s overall this week"
L["Guild and group"] = "Guild and group"
L["Guild and group members who use a Forever addon show up here."] =
	"Guild and group members who use a Forever addon show up here."
L["Hide this section"] = "Hide this section"
L["Installed, turned off"] = "Installed, turned off"
L["Keeps a cosmetic journal of the creatures you kill, zone by zone."] =
	"Keeps a cosmetic journal of the creatures you kill, zone by zone."
L["Lists your commission turn-ins, the materials in your bags and the next NPC to visit."] =
	"Lists your commission turn-ins, the materials in your bags and the next NPC to visit."
L["Lists your tracked quests in the Forever column, ready to turn in first, then this zone, then the rest by zone, nearest first. The game's own quest list is collapsed while this is on."] =
	"Lists your tracked quests in the Forever column, ready to turn in first, then this zone, then the rest by zone, nearest first. The game's own quest list is collapsed while this is on."
L["Lock the tracker"] = "Lock the tracker"
L["No addon has attached its log yet."] = "No addon has attached its log yet."
L["No one has shared yet"] = "No one has shared yet"
L["Not installed"] = "Not installed"
L["On"] = "On"
L["Open"] = "Open"
L["Others' values are player-reported."] = "Others' values are player-reported."
L["Overall"] = "Overall"
L["Picks quests for your level and plans them into one journey."] =
	"Picks quests for your level and plans them into one journey."
L["Plans the cheapest route to your next profession rank."] = "Plans the cheapest route to your next profession rank."
L["Plans the quickest way anywhere and guides you there, with live boat and zeppelin times."] =
	"Plans the quickest way anywhere and guides you there, with live boat and zeppelin times."
L["Player"] = "Player"
L["Players you've met"] = "Players you've met"
L["Players you've met who use a Forever addon show up here."] =
	"Players you've met who use a Forever addon show up here."
L["Points for placing on each addon's board."] = "Points for placing on each addon's board."
L["Quest automation, rare alerts and merchant handling for the default UI."] =
	"Quest automation, rare alerts and merchant handling for the default UI."
L["Rank"] = "Rank"
L["Ready to turn in"] = "Ready to turn in"
L["See where you stand on every Forever addon's board. Untick Share my progress there to keep your progress private."] =
	"See where you stand on every Forever addon's board. Untick Share my progress there to keep your progress private."
L["Report a bug or request a feature"] = "Report a bug or request a feature"
L["Share my progress"] = "Share my progress"
L["Show a quiet line where one of my other Forever addons would help. Only for addons you don't have."] =
	"Show a quiet line where one of my other Forever addons would help. Only for addons you don't have."
L["Shows the Legacy challenges you can advance in each zone."] =
	"Shows the Legacy challenges you can advance in each zone."
L["Suggest my other Forever addons"] = "Suggest my other Forever addons"
L["The Forever addons are free, with nothing locked behind them. If they help, you can buy me a coffee."] =
	"The Forever addons are free, with nothing locked behind them. If they help, you can buy me a coffee."
L["The link is selected. Press Ctrl+C (Cmd+C on a Mac), then paste into a browser; GitHub opens a filled-in issue."] =
	"The link is selected. Press Ctrl+C (Cmd+C on a Mac), then paste into a browser; GitHub opens a filled-in issue."
L["The text is selected. Press Ctrl+C (Cmd+C on a Mac) to copy it, then paste it into your bug report."] =
	"The text is selected. Press Ctrl+C (Cmd+C on a Mac) to copy it, then paste it into your bug report."
L["The tracker is locked. Turn off Lock the tracker to move it."] =
	"The tracker is locked. Turn off Lock the tracker to move it."
L["This addon"] = "This addon"
L["This week"] = "This week"
L["Title"] = "Title"
L["Total"] = "Total"
L["Tracker background"] = "Tracker background"
L["Usage: /forever debug, /forever debug pin, /forever debug off, /forever debug show"] =
	"Usage: /forever debug, /forever debug pin, /forever debug off, /forever debug show"
L["Use the game's quest list"] = "Use the game's quest list"
L["Uses Forever addons"] = "Uses Forever addons"
L["What happened, or what you would like"] = "What happened, or what you would like"
L["Your guild and group"] = "Your guild and group"
L["board"] = "board"
L["boards"] = "boards"
L.MINIMAP_UNAVAILABLE = "Minimap unavailable; skipping custom button."
L["MENU_BACK"] = "Back"
L["MENU_CHECKED"] = "[x] %s"
L["MENU_UNCHECKED"] = "[ ] %s"
L["MENU_SUBMENU"] = "%s >"
