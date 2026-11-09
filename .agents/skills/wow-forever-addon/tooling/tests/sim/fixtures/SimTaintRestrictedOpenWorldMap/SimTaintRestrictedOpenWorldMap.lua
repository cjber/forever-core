-- luacheck: ignore
-- C_Map.OpenWorldMap is documented with HasRestrictions = true: an addon that calls it is refused with
-- ADDON_ACTION_BLOCKED and the map does not open.
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	C_Map.OpenWorldMap(1454)
end)
