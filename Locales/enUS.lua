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
L.MINIMAP_UNAVAILABLE = "Minimap unavailable; skipping custom button."

-- Forever Leaderboards.
L["Forever Leaderboards"] = "Forever Leaderboards"
L["Overall"] = "Overall"
L["Forever standing"] = "Forever standing"
L["Your guild and group"] = "Your guild and group"
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
L["1st"] = "1st"
L["2nd"] = "2nd"
L["3rd"] = "3rd"
L["4th"] = "4th"
L["5th"] = "5th"
L["6th"] = "6th"
L["7th"] = "7th"
L["8th"] = "8th"
L[", "] = ", "
