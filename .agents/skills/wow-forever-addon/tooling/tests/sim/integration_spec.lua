-- forever_sim against the real Blizzard UI (fetch it first: python3 forever_sim/fetch.py --locale deDE), from
-- tooling/: luajit tests/sim/integration_spec.lua. Each check runs a fixture addon both ways: the pattern that
-- breaks in game must fail here, and its fix must pass.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
local fixtures = here .. "fixtures/"

local passed, failed = 0, 0
local function test(name, fn)
	local t0 = os.clock()
	local ok, err = xpcall(fn, debug.traceback)
	if ok then
		passed = passed + 1
		print(string.format("ok   %-78s %5.1fs", name, os.clock() - t0))
	else
		failed = failed + 1
		print(string.format("FAIL %s\n  %s", name, tostring(err):gsub("\n", "\n  ")))
	end
end
local function eq(a, b, label)
	if a ~= b then
		error(string.format("%s: expected %s, got %s", label or "value", tostring(b), tostring(a)), 2)
	end
end

local function blacksmith(sim)
	sim.world.professions = {
		{
			skillLineID = 164,
			name = "Blacksmithing",
			skill = 30,
			max = 75,
			categories = { { id = 1, name = "Materials" } },
			recipes = {
				{ id = 2660, name = "Rough Sharpening Stone", category = 1, itemID = 2862, reagents = { { 2835, 1 } } },
				{ id = 3115, name = "Rough Weightstone", category = 1, itemID = 3239, reagents = { { 2835, 1 } } },
			},
		},
	}
end

-- Hover a recipe, then a hostile unit in combat (secret text on the tooltip's lines), then another recipe.
local function tooltipScenario(addon)
	local sim = Sim.new()
	sim:addon(fixtures .. addon, addon)
	blacksmith(sim)
	sim:login()
	sim:openProfessions()
	sim:hoverRecipe(1)
	sim:leave()
	sim:enterCombat()
	sim:hoverUnit({ name = "Defias Bandit", level = 12, guid = "Creature-0-1-0-0-116-1", friendly = false })
	sim:unhoverUnit()
	sim:leaveCombat()
	sim:takeErrors()
	sim:hoverRecipe(2)
	return sim
end

test("Blizzard boot does not overflow the scroll callback stack", function()
	local sim = Sim.new()
	for _, err in ipairs(sim.errors) do
		assert(not err.message:find("stack overflow", 1, true), err.message .. "\n" .. (err.traceback or ""))
	end
end)

test("a reused frame in GameTooltip_InsertFrame raises the client's secret-number error", function()
	local sim = tooltipScenario("SimTooltipReuse")
	local e = sim:expectError(
		"Blizzard_SharedXML/SharedTooltipTemplates.lua:208: attempt to perform arithmetic on a secret number value"
			.. " (execution tainted by 'SimTooltipReuse')"
	)
	assert(e.traceback:find("SimTooltipReuse/SimTooltipReuse.lua", 1, true), e.traceback)
	assert(e.traceback:find("CallbackRegistry", 1, true), e.traceback)
end)

test("placing the frame on its own lines raises nothing", function()
	local sim = tooltipScenario("SimTooltipOwnLines")
	sim:expectNoErrors("SimTooltipOwnLines")
	eq(sim.G.GameTooltip:IsShown(), true, "tooltip shown")
end)

local function mapScenario(addon)
	local sim = Sim.new()
	sim:addon(fixtures .. addon, addon)
	sim.world.maps[1454] = { name = "Orgrimmar", parent = 1411 }
	sim.world.maps[1411] = { name = "Durotar", parent = 1414 }
	sim.world.maps[1414] = { name = "Kalimdor", parent = 947, mapType = 2 }
	sim:login()
	sim:setGamepad(true)
	sim:openWorldMap(1454)
	sim:zoomMap(1)
	sim:panMap(0.1, 0)
	sim:gamepadNavigate()
	return sim
end

local function orgrimmar(sim)
	sim.world.maps[1454] = { name = "Orgrimmar", parent = 1411 }
	sim.world.maps[1411] = { name = "Durotar", parent = 1414 }
	sim.world.maps[1414] = { name = "Kalimdor", parent = 947, mapType = 2 }
end

test("an addon's loadstring chunk runs under its own setfenv and still reports the addon", function()
	local sim = Sim.new()
	sim:login()
	sim:runAs(
		"SimData",
		[[
		local data = loadstring("return {[12]=1429}")
		setfenv(data, {})
		local ok, t = pcall(data)
		SimDataParsed = ok and t[12] or tostring(t)
		SimDataFn = loadstring("return function() end")()
	]]
	)
	sim:expectNoErrors("SimData")
	eq(sim.G.SimDataParsed, 1429, "data chunk parsed under its own environment")
	local fn, by = sim.G.SimDataFn, nil
	sim.run(function()
		fn()
		by = sim.taint.current
	end)
	eq(by, "SimData", "a loadstring function still reports its addon")
end)

test("the gamepad binding stack is watched, and backing out of a panel under the gamepad raises nothing", function()
	local sim = Sim.new()
	sim:login()
	local stack = sim.G.GamepadSharedUtility.InputBindingManager.bindingSetStack
	sim:runAs("SimBinder", "table.insert(GamepadSharedUtility.InputBindingManager.bindingSetStack, {})")
	local found = sim:gamepadTaint("SimBinder")
	eq(#found, 1, "binding stack write recorded")
	eq(found[1].table, "GamepadSharedUtility.InputBindingManager.bindingSetStack", "watched table")
	table.remove(stack)
	sim:takeErrors()
	sim:setGamepad(true)
	sim:input(function()
		sim.G.ShowUIPanel(sim.G.SettingsPanel)
	end)
	sim:input(function()
		sim.G.SettingsPanel:Close()
	end)
	for _, e in ipairs(sim:takeErrors()) do
		assert(not e.message:find("Spell%a+Target%a+"), e.message)
	end
end)

test("switching to the gamepad runs the interface transition, so a pooled menu's submenu opens clean", function()
	local sim = Sim.new()
	orgrimmar(sim)
	sim:login()
	local transitions = {}
	local listener = sim.G.CreateFrame("Frame")
	listener:RegisterEvent("INPUT_DEVICE_INTERFACE_TRANSITION")
	listener:SetScript("OnEvent", function(_, _, new, old)
		transitions[#transitions + 1] = new .. "<" .. old
	end)
	sim:openWorldMap(1454)
	local button = sim.G.WorldMapFrame.WorldMapTrackingOptionsButton
	sim:input(function()
		button:OpenMenu()
	end)
	sim:input(function()
		button:CloseMenu()
	end)
	sim:takeErrors()
	sim:setGamepad(true)
	local E = sim.G.Enum.InputDeviceInterfaceType
	eq(transitions[1], E.Gamepad .. "<" .. E.Mkb, "transition (new, old)")
	sim:input(function()
		button:OpenMenu()
	end)
	local submenu
	for _, d in button.menuDescription:EnumerateElementDescriptions() do
		if d:HasElements() then
			submenu = d
		end
	end
	assert(submenu, "the filter menu has a submenu")
	sim:input(function()
		submenu:ForceOpenSubmenu()
	end)
	sim:advance(0.1)
	sim:closeWorldMap()
	sim:setGamepad(false)
	eq(transitions[2], E.Mkb .. "<" .. E.Gamepad, "transition back")
	sim:expectNoErrors()
	-- The transition's CVars read as numbers in tainted code too, where an unset CVar reads nil.
	sim:runAs("SimCvar", 'SimEdgePan = GetCVarNumberOrDefault("GamepadMapEdgePanDistance")')
	eq(type(sim.G.SimEdgePan), "number", "gamepad map CVar under taint")
end)

test("native map API opens, closes and reopens with visibility callbacks", function()
	local sim = Sim.new()
	sim.world.maps[1454] = { name = "Orgrimmar", parent = 1411 }
	sim.world.maps[1411] = { name = "Durotar", parent = 1414 }
	sim.world.maps[1414] = { name = "Kalimdor", parent = 947, mapType = 2 }
	sim:login()
	for _, err in ipairs(sim:takeErrors()) do
		assert(not err.message:find("QuestMapFrame", 1, true), err.message)
	end
	local G = sim.G
	local shows, hides = 0, 0
	local opened = {}
	local listener = G.CreateFrame("Frame")
	listener:RegisterEvent("WORLD_MAP_OPEN")
	listener:SetScript("OnEvent", function(_, event, mapID)
		eq(event, "WORLD_MAP_OPEN", "documented map event")
		opened[#opened + 1] = mapID
	end)
	G.WorldMapFrame:HookScript("OnShow", function()
		shows = shows + 1
	end)
	G.WorldMapFrame:HookScript("OnHide", function()
		hides = hides + 1
	end)
	for cycle = 1, 2 do
		local mapID = cycle == 1 and 1454 or 1411
		sim.taint.dispatch("MapCaller", function()
			G.C_Map.OpenWorldMap(mapID)
			eq(opened[cycle], mapID, "API dispatches synchronous map event")
			eq(sim.taint.current, "MapCaller", "API restores caller taint")
		end)
		sim:advance(0.1)
		eq(G.WorldMapFrame:IsVisible(), true, "API opens map")
		eq(G.WorldMapFrame:GetMapID(), mapID, "requested map selected")
		eq(shows, cycle, "OnShow once per opening")
		sim:closeWorldMap()
		eq(G.WorldMapFrame:IsVisible(), false, "map closes")
		eq(hides, cycle, "OnHide once per closing")
		sim:expectNoErrors()
	end
end)

test("a map data provider added from addon code is gamepad-interface taint, and blocks the gamepad", function()
	local sim = mapScenario("SimMapProvider")
	local found = sim:gamepadTaint("SimMapProvider")
	assert(#found > 0, "no finding")
	eq(found[1].table, "WorldMapFrame.dataProviders")
	sim:expectError(
		"[ADDON_ACTION_BLOCKED] AddOn 'SimMapProvider' tried to call the protected function"
			.. " 'SetPreferredGamepadInteractTarget()'."
	)
	local ok = pcall(sim.expectNoGamepadTaint, sim, "SimMapProvider")
	eq(ok, false, "expectNoGamepadTaint fails")
end)

test("an addon's own overlay frame on the map leaves no gamepad-interface taint", function()
	local sim = mapScenario("SimMapOverlay")
	sim:expectNoGamepadTaint("SimMapOverlay")
	sim:expectNoErrors("SimMapOverlay")
end)

local function trackerScenario(saved)
	local sim = Sim.new()
	sim:stub("Questie")
	sim:addon(fixtures .. "SimTracker", "SimTracker")
	sim:login({ savedVariables = saved })
	sim:advance(6)
	return sim
end

test("a tracker column that moves aside clears Questie's quest list", function()
	local sim = trackerScenario({ SimTrackerDB = { avoidQuestie = true } })
	assert(sim:rect("Questie_BaseFrame"), "Questie's list is placed")
	sim:expectNoOverlap("SimTrackerColumn", "Questie_BaseFrame")
	sim:expectOnScreen("SimTrackerColumn")
end)

test("a saved state with the setting off is replayed and the overlap is caught", function()
	local sim = trackerScenario({ SimTrackerDB = { avoidQuestie = false } })
	assert(sim:overlap("SimTrackerColumn", "Questie_BaseFrame") > 0, "overlap detected")
	local ok, err = pcall(sim.expectNoOverlap, sim, "SimTrackerColumn", "Questie_BaseFrame")
	eq(ok, false)
	assert(err:find("overlaps", 1, true), err)
	eq(type(sim:savedState().SimTrackerDB.route), "table", "the saved state is repaired")
end)

test("unit identity is secret in combat for hostile units, readable out of it", function()
	local sim = Sim.new({ blizzard = {} })
	sim.world.units.target = { name = "Defias Bandit", level = 12, guid = "Creature-0-1", friendly = false }
	eq(sim.secret.is(sim.G.UnitName("target")), false, "out of combat")
	sim.inCombat = true
	sim.combatLockdown = true
	eq(sim.secret.is(sim.G.UnitName("target")), true, "in combat")
	eq(sim.secret.is(sim.G.UnitName("player")), false, "the player")
	eq(sim.secret.is(sim.G.UnitHealth("player")), true, "SecretReturns")
end)

test("a protected frame changed from addon code in combat is ADDON_ACTION_BLOCKED", function()
	local sim = Sim.new({ blizzard = {} })
	sim:runAs("SimCombat", 'SimSecureFrame = CreateFrame("Frame", "SimSecureFrame", UIParent)')
	sim.widgets.state[sim.G.SimSecureFrame].protected = true
	sim.inCombat = true
	sim.combatLockdown = true
	sim:runAs("SimCombat", "SimSecureFrame:SetPoint('CENTER')")
	sim:expectError(
		"[ADDON_ACTION_BLOCKED] AddOn 'SimCombat' tried to call the protected function 'SimSecureFrame:SetPoint()'"
	)
	sim.inCombat = false
	sim.combatLockdown = false
	sim:takeErrors()
	sim:runAs("SimCombat", "SimSecureFrame:SetPoint('CENTER')")
	eq(#sim.errors, 0, "allowed out of combat")
end)

test("combat start exposes the transition boundary and scopes loss-of-control secrets", function()
	local sim = Sim.new({ blizzard = {} })
	sim.impl["C_LossOfControl.GetActiveLossOfControlDataByUnit"] = function(unit)
		return { unit = unit, spellID = 123 }
	end
	sim:addon(fixtures .. "SimCombat", "SimCombat")
	sim:login()
	sim:enterCombat()
	eq(sim.G.SimCombatResults.affectingCombat, true, "player combat state during event")
	eq(sim.G.SimCombatResults.lockdown, false, "lockdown during event")
	eq(sim.secret.is(sim.G.SimCombatResults.playerLossOfControl), false, "player loss-of-control data")
	eq(sim.secret.is(sim.G.SimCombatResults.otherLossOfControl), true, "other-unit loss-of-control data")
	eq(sim.G.InCombatLockdown(), true, "lockdown after combat starts")
	eq(sim.G.UnitAffectingCombat("player"), true, "player combat state after combat starts")
	sim:leaveCombat()
	eq(sim.G.InCombatLockdown(), false, "lockdown after combat ends")
	eq(sim.G.UnitAffectingCombat("player"), false, "player combat state after combat ends")
end)

test("the client's strings follow the locale", function()
	local en = Sim.new({ blizzard = {} })
	local de = Sim.new({ blizzard = {}, locale = "deDE" })
	eq(de.G.GetLocale(), "deDE")
	assert(en.G.CANCEL ~= de.G.CANCEL, "CANCEL differs: " .. tostring(de.G.CANCEL))
end)

test("the booted Blizzard UI raises no error of its own in tainted execution", function()
	local sim = Sim.new()
	for _, e in ipairs(sim.errors) do
		assert(not e.taint, "tainted error during boot: " .. e.message)
	end
	local gaps = 0
	for _ in pairs(sim.gaps) do
		gaps = gaps + 1
	end
	print(
		string.format(
			"     boot %.1fs, %d Blizzard errors untainted, %d recorded gaps",
			sim.bootSeconds,
			#sim.errors,
			gaps
		)
	)
end)

test("Professions book page completes OnShow and runs post-hooks", function()
	local sim = Sim.new()
	eq(type(sim.G.ShowProfessionsFrame), "function", "load-on-demand bootstrap available before login")
	eq(sim.loader.loaded.Blizzard_Professions, nil, "bootstrap did not load the full addon")
	for _, name in ipairs({ "ExpansionTrial_LoadUI", "PVPUI_LoadUI", "Garrison_LoadUI", "ShowPerksProgramFrame" }) do
		eq(sim.G[name], nil, name .. " is excluded from the Forever client")
	end
	eq(sim.loader.blizzard("Blizzard_PVPUI"), false, "excluded addon cannot load by name")
	eq(sim.loader.blizzard("Blizzard_PVPUI:Bootstrap"), false, "excluded subset cannot load")
	eq(sim.loader.blizzard("Blizzard_PVPUI/Blizzard_PVPUI_Bootstrap.lua"), false, "excluded direct file cannot load")
	local bootstrap = sim.G.ShowProfessionsFrame
	sim.loader.bootstrap()
	sim:loadBlizzard("Blizzard_Professions/Blizzard_Professions_Bootstrap.lua")
	sim:loadBlizzard("Blizzard_Professions:Bootstrap")
	eq(sim.G.ShowProfessionsFrame, bootstrap, "bootstrap remains the same through all loader paths")
	blacksmith(sim)
	sim:login()
	local pf = sim:openProfessions(164)
	eq(sim.G.ShowProfessionsFrame, bootstrap, "full addon does not execute its bootstrap twice")
	local ran = false
	pf.BookPage:HookScript("OnShow", function()
		ran = true
	end)
	sim.widgets.dispatch(pf.ProfessionsOverviewTab, "OnMouseUp", "LeftButton", true)
	sim:advance(0.05)
	assert(ran, "BookPage OnShow hook did not run")
	assert(sim.G.OverlayPlayerCastingBarFrame, "casting bar available")
	sim:runAs(
		"SimProfessionCaller",
		[[
		assert(type(LE_FRAME_TUTORIAL_PROFESSION_QUALITY_REAGENTS) == "number")
		ProfessionsFrame.CraftingPage:Show()
		ProfessionsFrame.CraftingPage:Hide()
	]]
	)
	sim:expectNoErrors("SimProfessionCaller")
end)

print(string.format("integration_spec: %d passed, %d failed", passed, failed))
os.exit(failed == 0 and 0 or 1)
