-- luacheck: ignore
-- Registering a callback stores an addon function in the registry. Triggering it from secure code walks that
-- table through secureexecuterange: the pair runs tainted by the addon callback, but the secure caller is secure
-- again afterwards, so the dispatcher's later write carries no taint. Triggered from tainted code, the same walk
-- does not launder that caller.
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	EventRegistry:RegisterCallback("SimTaintCallbackRange", function() end, events)
	SimTaintCallbackRangeTrigger = function()
		EventRegistry:TriggerEvent("SimTaintCallbackRange")
	end
end)
