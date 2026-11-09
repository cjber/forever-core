-- luacheck: ignore
-- A C API that runs Blizzard Lua keeps the caller's taint: an addon scheduling a Blizzard function through
-- C_Timer.After leaves the fields that function writes tainted by the addon, before and after the frame boundary.
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	C_Timer.After(0, GenerateClosure(WorldMapFrame.HandleUserActionToggleSelf, WorldMapFrame))
end)
