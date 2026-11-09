-- luacheck: ignore
-- A C API that runs Blizzard's Lua runs it secure: a timer the addon schedules calls a Blizzard function, and
-- the state that function writes carries no taint.
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	C_Timer.After(0, GenerateClosure(WorldMapFrame.HandleUserActionToggleSelf, WorldMapFrame))
end)
