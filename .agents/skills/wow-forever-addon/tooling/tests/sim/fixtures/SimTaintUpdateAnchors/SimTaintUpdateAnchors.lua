-- luacheck: ignore
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	DebugBarManager:UpdateAnchors()
end)
