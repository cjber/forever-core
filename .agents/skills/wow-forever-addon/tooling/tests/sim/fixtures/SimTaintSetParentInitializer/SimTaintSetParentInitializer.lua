-- luacheck: ignore
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	SimTaintObject = CreateFromMixins(SettingsListElementInitializer)
	SimTaintObject:SetParentInitializer(function() end)
end)
