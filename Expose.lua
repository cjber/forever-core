-- The core's public face, loaded after the shared files so it can publish what they built. A Forever addon reads
-- ForeverCore.TrackerHost when it wants the column without vendoring the host itself, and /fcore prints the same
-- diagnostic the addons' own slash commands print.
local ns = select(2, ...)

local core = {}
core.name = "ForeverCore"
core.Defaults = ns.Defaults
core.TrackerHost = ns.TrackerHost
core.TrackerLock = ns.TrackerLock
core.TrackerOrder = ns.TrackerOrder
core.TrackerQuestie = ns.TrackerQuestie

---Attaches a section frame to the shared column; false when there is no column (no native tracker).
---@param module ForeverTrackerModule
---@return boolean
function core.Attach(module)
	local host = ns.TrackerHost
	if host == nil then
		return false
	end
	host.Attach(module)
	return true
end

ForeverCore = core -- taint-ok: addon-owned registry of the shared primitives

if SlashCmdList ~= nil then
	SLASH_FOREVERCORE1 = "/fcore"
	SlashCmdList.FOREVERCORE = function()
		local host = ns.TrackerHost
		if host ~= nil and host.Debug ~= nil then
			print(host.Debug())
		end
	end
end
