-- luacheck: read globals scenario ADDON
scenario("native settings section registers from real Core", function(sim)
	sim.impl["C_SettingsUtil.OpenSettingsPanel"] = function(id, element)
		return sim.G.SettingsPanel:OpenToCategory(id, element)
	end
	sim:setGamepad(true)
	sim:login()
	sim.G.CreateSecureDelegate = nil
	local ns = assert(sim.loader.addons[ADDON]).ns
	assert(ns.SettingsSections, "real Core SettingsSections loaded")
	sim:runAs(
		ADDON,
		[[
 local ns = ...
 local category = Settings.RegisterVerticalLayoutCategory("Section integration")
 Settings.RegisterAddOnCategory(category)
 assert(ns.SettingsSections.Register(category, "Native section", "Section tooltip"))
 ns.testCategory = category
 ]],
		ns
	)
	local category = assert(ns.testCategory)
	sim:input(function()
		ns.OpenSettingsPanel(category:GetID())
	end)
	sim:advance(0.2)
	sim:expectNoErrors(ADDON)
	assert(sim.G.SettingsPanel:IsShown(), "settings visible")
	local box = sim.G.SettingsPanel:GetSettingsList().ScrollBox
	assert(box:GetDataProvider():GetSize() == 1, "native header row exists")
	local row = assert(box:FindFrame(box:GetDataProvider():Find(1)), "native header frame exists")
	assert(row.Title:GetText() == "Native section", "native row displays the heading")
	sim:input(function()
		sim.G.SettingsPanel:Close()
	end)
	sim:advance(0.1)
	sim:expectNoErrors(ADDON)
	sim:expectNoGamepadTaint(ADDON)
end)
