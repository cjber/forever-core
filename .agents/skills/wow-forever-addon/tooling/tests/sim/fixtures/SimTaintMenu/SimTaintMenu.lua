-- luacheck: ignore
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	local menu = MenuUtil.CreateContextMenu(UIParent, function(_, rootDescription)
		rootDescription:CreateTitle("SimTaintMenu")
		rootDescription:CreateButton("SimTaintMenu", function() end)
	end)
	SimTaintMenu = menu
end)
