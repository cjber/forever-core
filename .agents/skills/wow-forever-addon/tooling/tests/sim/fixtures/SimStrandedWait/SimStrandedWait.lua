-- luacheck: globals SimStrandedWaitEarly SimStrandedWaitLogin SimStrandedWaitWorld
-- A wait made at file load, before the login, calls back.
EventUtil.ContinueAfterAllEvents(function()
	SimStrandedWaitEarly = true
end, "VARIABLES_LOADED", "PLAYER_LOGIN")

-- What a file run at activation (after PLAYER_LOGIN) does.
local starter = CreateFrame("Frame")
starter:RegisterEvent("PLAYER_LOGIN")
starter:SetScript("OnEvent", function(self)
	self:UnregisterEvent("PLAYER_LOGIN")
	EventUtil.ContinueAfterAllEvents(function()
		SimStrandedWaitLogin = true
	end, "PLAYER_LOGIN")
	local variables = CreateFrame("Frame")
	variables:RegisterEvent("VARIABLES_LOADED")
	-- Registered and dropped again: nothing waits.
	local dropped = CreateFrame("Frame")
	dropped:RegisterEvent("PLAYER_LOGIN")
	dropped:UnregisterEvent("PLAYER_LOGIN")
	-- The world entry is still to come (and fires again on every loading screen): not a once-only wait.
	EventUtil.ContinueAfterAllEvents(function()
		SimStrandedWaitWorld = true
	end, "PLAYER_ENTERING_WORLD")
end)
