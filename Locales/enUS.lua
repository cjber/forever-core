local ns = select(2, ...)

-- English phrases are the keys, so a phrase with no translation reads as English. A consuming addon vendors these
-- files but keeps its own Locales/enUS.lua, which is where its player-facing copy lives; the strings below are the
-- ones the shared files themselves draw.
---@type table<string, string>
local L = setmetatable({}, {
	__index = function(_, key)
		return key
	end,
})
ns.L = L

L["Forever tracker"] = "Forever tracker"
L["Drag to move"] = "Drag to move"
L["The tracker is locked. Turn off Lock the tracker to move it."] =
	"The tracker is locked. Turn off Lock the tracker to move it."
L["Attach to quest tracker"] = "Attach to quest tracker"
L["Lock the tracker"] = "Lock the tracker"
L["Tracker background"] = "Tracker background"
L.MINIMAP_UNAVAILABLE = "Minimap unavailable; skipping custom button."

-- Forever quest list.
L["Forever quest list"] = "Forever quest list"
L["Lists your tracked quests in the Forever column, ready to turn in first, then this zone, then the rest by zone, nearest first. The game's own quest list is collapsed while this is on."] =
	"Lists your tracked quests in the Forever column, ready to turn in first, then this zone, then the rest by zone, nearest first. The game's own quest list is collapsed while this is on."
L["Use the game's quest list"] = "Use the game's quest list"
L["Ready to turn in"] = "Ready to turn in"
L["%d yd"] = "%d yd"

-- Forever Leaderboards.
L["Forever Leaderboards"] = "Forever Leaderboards"
L["Overall"] = "Overall"
L["Forever standing"] = "Forever standing"
L["Your guild and group"] = "Your guild and group"
L["Players you've met"] = "Players you've met"
L["This week"] = "This week"
L["All time"] = "All time"
L["Rank"] = "Rank"
L["Player"] = "Player"
L["No one has reported yet."] = "No one has reported yet."
L["Share my progress"] = "Share my progress"
L["Others' values are player-reported."] = "Others' values are player-reported."
L["Points for placing on each addon's board."] = "Points for placing on each addon's board."
L["(you)"] = "(you)"
L["board"] = "board"
L["boards"] = "boards"
L["Uses Forever addons"] = "Uses Forever addons"
L["Forever: %s overall this week"] = "Forever: %s overall this week"
L["Forever: %s overall"] = "Forever: %s overall"

-- Shared debug log.
L["Debug log is off."] = "Debug log is off."
L["Debug log is on for this session."] = "Debug log is on for this session."
L["Debug log is on and pinned for this character."] = "Debug log is on and pinned for this character."
L["Debug log is already on and pinned for this character."] = "Debug log is already on and pinned for this character."
L["Debug log is off for this session; it is still pinned."] = "Debug log is off for this session; it is still pinned."
L["Debug log is off and unpinned."] = "Debug log is off and unpinned."
L["No addon has attached its log yet."] = "No addon has attached its log yet."
L["%s (last %d):"] = "%s (last %d):"
L["%s: no lines yet."] = "%s: no lines yet."
L["Usage: /forever debug, /forever debug pin, /forever debug off, /forever debug show"] =
	"Usage: /forever debug, /forever debug pin, /forever debug off, /forever debug show"
L["1st"] = "1st"
L["2nd"] = "2nd"
L["3rd"] = "3rd"
L["4th"] = "4th"
L["5th"] = "5th"
L["6th"] = "6th"
L["7th"] = "7th"
L["8th"] = "8th"
L[", "] = ", "
