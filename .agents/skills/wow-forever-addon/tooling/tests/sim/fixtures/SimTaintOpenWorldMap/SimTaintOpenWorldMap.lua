-- luacheck: ignore
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	OpenWorldMap(1454)
end)
