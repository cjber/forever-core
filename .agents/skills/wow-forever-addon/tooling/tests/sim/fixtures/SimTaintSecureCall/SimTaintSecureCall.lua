-- luacheck: ignore
-- securecallfunction runs its function from secure execution, not the caller's taint: a secure Blizzard function
-- called from addon code does not carry the addon into the state it writes.
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	EventRegistry:RegisterCallback("SimTaintSecureCall", function() end, events)
	securecallfunction(EventRegistry.TriggerEvent, EventRegistry, "SimTaintSecureCall")
end)
