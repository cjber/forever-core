-- luacheck: ignore
-- A script fired synchronously by a Lua call runs in the caller's taint: an addon calling Show() on a Blizzard
-- frame hands its taint to the frame's Blizzard OnShow handler. This is not an engine dispatch.
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	SettingsPanel:Show()
end)
