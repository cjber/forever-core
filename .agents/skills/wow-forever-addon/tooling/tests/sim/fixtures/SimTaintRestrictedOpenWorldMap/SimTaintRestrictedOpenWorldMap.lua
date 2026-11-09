-- luacheck: ignore
-- C_Map.OpenWorldMap is documented with HasRestrictions = true, and this client refuses it to tainted code even
-- out of combat: an addon that calls it gets ADDON_ACTION_BLOCKED and the map does not open.
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	C_Map.OpenWorldMap(1454)
end)
