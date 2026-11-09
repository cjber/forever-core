-- luacheck: ignore
-- Registering a callback stores an addon function in the registry. Triggering it from secure code walks that
-- table through secureexecuterange, which must not taint the dispatcher's later writes.
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	EventRegistry:RegisterCallback("SimTaintCallbackRange", function() end, events)
end)
