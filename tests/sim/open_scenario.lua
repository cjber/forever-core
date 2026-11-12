-- luacheck: read globals scenario ADDON
-- C_Map.OpenWorldMap is documented with the pin's nocombat class: a plain out-of-combat addon call opens the map,
-- and the client refuses it in combat. The shared opener asks the same client function through securecallfunction.
scenario("the shared opener asks the client to open the map and settings", function(sim)
	local G = sim.G
	sim.world.maps[1454] = { name = "Durotar", parent = 1414, mapType = 3 }
	sim.world.maps[1414] = { name = "Kalimdor", parent = 947, mapType = 2 }
	sim.world.maps[947] = { name = "Azeroth", parent = 0, mapType = 1 }
	sim:login()
	local ns
	for _, entry in ipairs(sim.loader.addons) do
		if entry.name == ADDON then
			ns = entry.ns
		end
	end
	assert(ns, "the addon namespace is loaded")
	assert(type(ns.OpenMap) == "function", "the shared map opener is loaded")
	assert(type(ns.OpenSettingsPanel) == "function", "the shared settings opener is loaded")

	-- Out of combat the direct call opens, the way the live client does (#486).
	sim:runAs(ADDON, "C_Map.OpenWorldMap(1454)")
	sim:advance(0.2)
	sim:expectNoErrors(ADDON)
	assert(sim.G.WorldMapFrame:IsShown(), "the out-of-combat direct call opens the map")
	sim:closeWorldMap()

	-- In combat the documented restriction refuses it and blames the addon.
	sim:enterCombat()
	sim:runAs(ADDON, "C_Map.OpenWorldMap(1454)")
	sim:advance(0.2)
	sim:expectError("tried to call the protected function 'C_Map.OpenWorldMap()'")
	sim:takeErrors()
	assert(not sim.G.WorldMapFrame:IsShown(), "the combat call did not open the map")
	sim:leaveCombat()

	-- The shared opener makes the same request, so nothing is blocked.
	local opened = sim:runAs(ADDON, "local ns, map = ...; return ns.OpenMap(map)", ns, 1454)
	sim:advance(0.3)
	assert(opened == true, "the opener reports the map opened")
	assert(sim.G.WorldMapFrame:IsShown(), "the map opens through the shared opener")
	sim:expectNoErrors(ADDON)

	-- C_SettingsUtil.OpenSettingsPanel is Blizzard's restricted C path on this build.
	local panelCalls = 0
	local directTaint, wrapperTaint
	local wrapper = G.SettingsPanel.OpenToCategory
	G.SettingsPanel.OpenToCategory = function(self, categoryID, element)
		wrapperTaint = sim.taint.current
		return wrapper(self, categoryID, element)
	end
	sim.impl["C_SettingsUtil.OpenSettingsPanel"] = function(categoryID, element)
		panelCalls = panelCalls + 1
		directTaint = sim.taint.current
		assert(categoryID == 1 and element == nil)
		G.SettingsPanel:OpenToCategory(categoryID, element)
	end
	local shown = sim:runAs(ADDON, "local ns = ...; return ns.OpenSettingsPanel(1)", ns)
	assert(shown == true, "the opener reports the settings panel opened")
	assert(panelCalls == 1, "the settings panel opens through the shared opener")
	assert(directTaint == nil, "the native C opener enters the panel securely")
	sim:runAs(ADDON, "SettingsPanel:OpenToCategory(1)")
	assert(wrapperTaint == ADDON, "the Lua SettingsPanel wrapper remains addon-tainted")
	sim:expectNoErrors(ADDON)
end)
