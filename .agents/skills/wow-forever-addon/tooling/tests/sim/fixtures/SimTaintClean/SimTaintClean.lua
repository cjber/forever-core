-- luacheck: ignore
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	SimTaintClean = {}
	SimTaintClean.frame = CreateFrame("Frame", "SimTaintCleanFrame", UIParent)
	SimTaintClean.frame:SetSize(10, 10)
	SimTaintClean.value = 1
end)
