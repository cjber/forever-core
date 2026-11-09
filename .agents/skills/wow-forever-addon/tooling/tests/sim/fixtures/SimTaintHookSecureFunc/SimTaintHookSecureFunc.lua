-- luacheck: ignore
-- A hooksecurefunc post-hook is a secure boundary: the Blizzard function an addon installs as the hook runs
-- secure even when the hooked method was called from addon code.
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	hooksecurefunc(WorldMapFrame, "GetMapID", WorldMapFrame.SetMapID)
	-- The extra argument reaches the post-hook, which writes the map fields the gate watches.
	WorldMapFrame:GetMapID(1454)
end)
