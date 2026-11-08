-- luacheck: ignore 131 (the client reads the aliases, not this file)
-- Fixture for the shared exercise step: one slash command with two aliases, a saved call count, and a failure
-- that only shows on the load after a reload, the kind of bug a hand-written driver misses.
-- luacheck: globals SimSlashDB SlashCmdList SLASH_SIMSLASH1 SLASH_SIMSLASH2
local reloaded = false

local function Handle(message)
	SimSlashDB.last = message
	SimSlashDB.calls = SimSlashDB.calls + 1
	if SimSlashDB.failAfterReload and reloaded then
		error("SimSlash broke after reload")
	end
end

SLASH_SIMSLASH1 = "/simslash"
SLASH_SIMSLASH2 = "/ss"
SlashCmdList.SIMSLASH = Handle

local events = CreateFrame("Frame")
events:RegisterEvent("ADDON_LOADED")
events:SetScript("OnEvent", function(_, _, name)
	if name == "SimSlash" then
		SimSlashDB = SimSlashDB or { calls = 0 }
		reloaded = SimSlashDB.calls > 0
	end
end)
