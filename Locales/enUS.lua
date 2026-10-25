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
L.MICRO_MENU_UNAVAILABLE = "Micro menu unavailable; skipping custom button."
