-- luacheck: read globals scenario ADDON
-- Under this client a direct C_Map.OpenWorldMap from addon code is refused and blamed on the addon
-- (cjber/adventure-guide-forever#411, cjber/forever-core#333). The shared opener runs it through
-- the client's secure path, so the client performs it and the addon leaves no blocked action. Settings uses
-- SettingsPanel.OpenToCategory through securecallfunction on this build.
scenario("the shared opener asks the client to open the map and settings", function(sim)
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

	-- The call the issue saw: addon code asks the restricted C function directly and the client blocks it.
	sim:runAs(ADDON, "C_Map.OpenWorldMap(1454)")
	sim:advance(0.2)
	sim:expectError("tried to call the protected function 'C_Map.OpenWorldMap()'")
	sim:takeErrors()
	assert(not sim.G.WorldMapFrame:IsShown(), "the blocked call did not open the map")

	-- The shared opener makes the same request as the client, so nothing is blocked.
	local opened = sim:runAs(ADDON, "local ns, map = ...; return ns.OpenMap(map)", ns, 1454)
	sim:advance(0.3)
	assert(opened == true, "the opener reports the map opened")
	assert(sim.G.WorldMapFrame:IsShown(), "the map opens through the shared opener")
	sim:expectNoErrors(ADDON)

	-- SettingsPanel.OpenToCategory is Blizzard's secure path on this build.
	local panelCalls = 0
	sim.G.SettingsPanel = {
		OpenToCategory = function(_, categoryID, element)
			panelCalls = panelCalls + 1
			assert(categoryID == 1 and element == nil)
		end,
	}
	sim.G.securecallfunction = function(fn, ...)
		return fn(...)
	end
	sim.impl["C_SettingsUtil.OpenSettingsPanel"] = function()
		panelCalls = panelCalls + 1
	end
	local shown = sim:runAs(ADDON, "local ns = ...; return ns.OpenSettingsPanel(1)", ns)
	assert(shown == true, "the opener reports the settings panel opened")
	assert(panelCalls == 1, "the settings panel opens through the shared opener")
	sim:expectNoErrors(ADDON)
end)
