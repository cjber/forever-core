-- luacheck: ignore
-- securecallfunction runs its function in the caller's execution taint: an addon that secures a Blizzard menu open
-- still writes the menu's Blizzard fields tainted by the addon.
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	SimTaintSecureCall = securecallfunction(MenuUtil.CreateContextMenu, UIParent, function(_, rootDescription)
		rootDescription:CreateTitle("SimTaintSecureCall")
	end)
end)
