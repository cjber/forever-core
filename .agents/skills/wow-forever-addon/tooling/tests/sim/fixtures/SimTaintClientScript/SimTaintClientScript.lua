-- luacheck: ignore
-- A script the client dispatches starts secure: an addon calling Show() on a Blizzard frame does not hand its
-- taint to the frame's Blizzard OnShow handler.
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	SettingsPanel:Show()
end)
