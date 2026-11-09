-- luacheck: ignore
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	local container = next(ObjectiveTrackerManager.containers)
	SimTaintModule = { AddModule = function() end, RemoveModule = function() end }
	ObjectiveTrackerManager:SetModuleContainer(SimTaintModule, container)
end)
