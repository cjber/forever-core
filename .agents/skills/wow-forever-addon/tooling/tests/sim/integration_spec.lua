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

test("the gamepad binding stack is watched, and a tainted read blocks the gamepad", function()
	local sim = Sim.new()
	sim:login()
	local stack = sim.G.GamepadSharedUtility.InputBindingManager.bindingSetStack
	sim:runAs("SimBinder", "table.insert(GamepadSharedUtility.InputBindingManager.bindingSetStack, {})")
	local info = sim.taint.slotInfo(stack, #stack)
	assert(info and info.addon == "SimBinder", "binding stack slot carries the addon's taint")
	sim:setGamepad(true)
	sim:takeErrors()
	sim:gamepadNavigate()
	local found = sim:gamepadTaint("SimBinder")
	assert(#found > 0, "no finding")
	eq(found[1].key, #stack, "the tainted binding-set slot")
	local e = sim:expectError("Tainted field GamepadSharedUtility.InputBindingManager.bindingSetStack")
	assert(e.message:find("written by SimBinder", 1, true), e.message)
	assert(e.message:find("read by secure code", 1, true), e.message)
	table.remove(stack)
	sim:takeErrors()
	sim:input(function()
		sim.G.ShowUIPanel(sim.G.SettingsPanel)
	end)
	sim:input(function()
		sim.G.SettingsPanel:Close()
	end)
	for _, err in ipairs(sim:takeErrors()) do
		assert(not err.message:find("Spell%a+Target%a+"), err.message)
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

test("SettingsPanel opens and closes through the panel manager with no errors, mouse and gamepad", function()
	for _, gamepad in ipairs({ false, true }) do
		local sim = Sim.new()
		sim:login()
		local G = sim.G
		eq(G.ContainerFrame1:GetParent(), G.ContainerFrameContainer, "a bag frame takes its template's parent")
		sim:setGamepad(gamepad)
		sim:takeErrors()
		sim:input(function()
			G.ShowUIPanel(G.SettingsPanel)
		end)
		eq(G.SettingsPanel:IsShown(), true, "panel shown")
		sim:input(function()
			G.SettingsPanel:Close()
		end)
		sim:advance(0.1)
		eq(G.SettingsPanel:IsShown(), false, "panel closed")
		local errors = sim:takeErrors()
		if #errors > 0 then
			error((gamepad and "gamepad" or "mouse") .. ":\n" .. Sim.describe(errors))
		end
	end
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
		sim.run(function()
			G.C_Map.OpenWorldMap(mapID)
			eq(opened[cycle], mapID, "API dispatches synchronous map event")
			eq(sim.taint.current, nil, "API restores a secure caller's state")
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

test("closing the world map with the quest log shown closes the quest portrait, as the client does", function()
	local sim = Sim.new()
	sim.world.maps[1429] = { name = "Elwynn Forest", parent = 1415 }
	sim.world.maps[1415] = { name = "Eastern Kingdoms", parent = 947, mapType = 2 }
	orgrimmar(sim)
	sim:login()
	eq(type(sim.G.QuestFrame_HideQuestPortrait), "function", "QuestFrame is booted")
	sim:takeErrors()
	sim:openWorldMap(1429)
	sim:input(function()
		sim.G.WorldMapFrame:SetQuestLogPanelShown(true)
	end)
	sim:closeWorldMap()
	eq(sim.G.WorldMapFrame:IsVisible(), false, "the world map is hidden")
	sim:expectNoErrors()
end)

test("an error in a script handler is reported and the code that triggered it carries on", function()
	local sim = Sim.new()
	sim:login()
	local frame = sim.G.CreateFrame("Frame")
	frame:SetScript("OnHide", function()
		error("SimHide failed", 0)
	end)
	sim:takeErrors()
	local after = false
	sim:input(function()
		frame:Hide()
		after = true
	end)
	eq(frame:IsShown(), false, "the frame is hidden")
	eq(after, true, "the input after Hide runs")
	local e = sim:expectError("SimHide failed")
	assert(e.traceback:find("integration_spec.lua", 1, true), e.traceback)
end)

test("the legacy achievement natives answer from sim.world.achievements and nil for an unknown id", function()
	local sim = Sim.new({ blizzard = {} })
	sim.world.achievements = {
		categories = {
			{
				id = 1,
				name = "General",
				parent = -1,
				achievements = {
					{
						id = 6,
						name = "Level 60",
						description = "Reach level 60.",
						points = 10,
						completed = true,
						criteria = {
							{ text = "Reach level 60", type = 0, completed = true, quantity = 1, required = 1 },
						},
					},
				},
			},
			{ id = 2, name = "Quests", parent = 1, achievements = {} },
		},
	}
	local G = sim.G
	local categories = G.GetCategoryList()
	eq(#categories, 2, "category count")
	eq(categories[1], 1, "first category")

	local total, completed, incomplete = G.GetCategoryNumAchievements(1)
	eq(total, 1, "achievements in the category")
	eq(completed, 1, "completed")
	eq(incomplete, 0, "incomplete")

	local info = { G.GetAchievementInfo(1, 1) }
	eq(info[1], 6, "id by category and index")
	eq(info[2], "Level 60", "name")
	eq(info[3], 10, "points")
	eq(info[4], true, "completed")
	eq(info[8], "Reach level 60.", "description")
	eq(info[13], true, "earned by me")
	eq(select(1, G.GetAchievementInfo(6)), 6, "id by achievement id")

	eq(G.GetAchievementCategory(6), 1, "achievement category")
	local name, parent = G.GetCategoryInfo(1)
	eq(name, "General", "category name")
	eq(parent, -1, "category parent")
	eq(G.GetAchievementNumCriteria(6), 1, "criteria count")

	local text, criteriaType, done, quantity, required, _, _, _, _, criteriaID, eligible =
		G.GetAchievementCriteriaInfo(6, 1)
	eq(text, "Reach level 60", "criteria text")
	eq(criteriaType, 0, "criteria type")
	eq(done, true, "criteria completed")
	eq(quantity, 1, "criteria progress")
	eq(required, 1, "criteria required")
	eq(criteriaID, 1, "criteria id")
	eq(eligible, true, "criteria eligible")

	eq(G.GetAchievementInfo(999), nil, "unknown achievement")
	eq(G.GetAchievementInfo(1, 99), nil, "unknown achievement index")
	eq(G.GetAchievementCategory(999), nil, "unknown achievement category")
	eq(G.GetCategoryNumAchievements(999), nil, "unknown category")
	eq(G.GetCategoryInfo(999), nil, "unknown category info")
	eq(G.GetAchievementNumCriteria(999), nil, "unknown achievement criteria")
	eq(G.GetAchievementCriteriaInfo(999, 1), nil, "unknown criteria")
end)

test("a frame can inherit SecureActionButtonTemplate", function()
	local sim = Sim.new()
	local button = sim.G.CreateFrame("Button", "SimSecureActionButton", sim.G.UIParent, "SecureActionButtonTemplate")
	assert(button, "frame created")
	eq(type(button.SetAttribute), "function", "secure button methods")
	eq(type(sim.G.SecureActionButtonMixin), "table", "the template's mixin")
end)

test("a map data provider added from addon code taints the map's walk of it", function()
	local sim = mapScenario("SimMapProvider")
	local provider = sim.G.SimMapProvider
	assert(provider, "the fixture registered its provider")
	local slot = sim.taint.slotInfo(sim.G.WorldMapFrame.dataProviders, provider)
	assert(slot and slot.addon == "SimMapProvider", "the provider's slot carries the addon's taint")
	local method = sim.taint.slotInfo(provider, "RefreshAllData")
	assert(method and method.addon == "SimMapProvider", "the provider's method slot carries the addon's taint")
	-- secureexecuterange runs the pair tainted by that slot, so Blizzard's map walk is not laundered; the gate
	-- no longer reports a secure read of the provider, because there is none.
	sim:expectNoGamepadTaint("SimMapProvider")
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

test("a frame is protected implicitly through a protected descendant, not explicitly", function()
	local sim = Sim.new()
	sim:loadBlizzard("Blizzard_FrameXML/SecureTemplates.lua")
	sim:loadBlizzard("Blizzard_FrameXML/SecureTemplates.xml")
	sim:runAs(
		"SimImplicit",
		[[
		SimPlain = CreateFrame("Frame", "SimPlain", UIParent)
		SimSecureChild = CreateFrame("Button", "SimSecureChild", SimPlain, "SecureActionButtonTemplate")
		SimPlainNoChild = CreateFrame("Frame", "SimPlainNoChild", UIParent)
	]]
	)
	local protected, explicit = sim.G.SimPlain:IsProtected()
	eq(protected, true, "the parent is protected")
	eq(explicit, false, "the parent is not explicitly protected")
	protected, explicit = sim.G.SimSecureChild:IsProtected()
	eq(protected, true, "the secure child is protected")
	eq(explicit, true, "the secure child is explicitly protected")
	protected, explicit = sim.G.SimPlainNoChild:IsProtected()
	eq(protected, false, "a frame with no protected descendant is not protected")
	eq(explicit, false, "nor explicitly protected")
end)

test("implicit protection blocks a tainted Hide in combat, as the client does", function()
	local sim = Sim.new()
	sim:loadBlizzard("Blizzard_FrameXML/SecureTemplates.lua")
	sim:loadBlizzard("Blizzard_FrameXML/SecureTemplates.xml")
	sim:runAs(
		"SimImplicit",
		[[
		SimPlain = CreateFrame("Frame", "SimPlain", UIParent)
		CreateFrame("Button", "SimSecureChild", SimPlain, "SecureActionButtonTemplate")
		SimPlainNoChild = CreateFrame("Frame", "SimPlainNoChild", UIParent)
	]]
	)
	sim.inCombat = true
	sim.combatLockdown = true
	sim:runAs("SimImplicit", "SimPlain:Hide()")
	sim:expectError("[ADDON_ACTION_BLOCKED] AddOn 'SimImplicit' tried to call the protected function 'SimPlain:Hide()'")
	sim:takeErrors()
	sim:runAs("SimImplicit", "SimPlainNoChild:Hide()")
	eq(#sim.errors, 0, "a frame with no protected descendant is not blocked")
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

test("an XML frame from LargeSideTabButtonTemplate is a Frame, and refuses OnClick", function()
	local sim = Sim.new()
	blacksmith(sim)
	sim:login()
	local pf = sim:openProfessions(164)
	local tab = pf.ProfessionsOverviewTab
	eq(tab:GetObjectType(), "Frame", "the XML element names a Frame")
	eq(tab:IsObjectType("Button"), false, "the template's name does not make it a Button")
	eq(tab:HasScript("OnClick"), false, "a Frame does not support OnClick")
	local ok, err = pcall(function()
		tab:HookScript("OnClick", function() end)
	end)
	eq(ok, false, "HookScript OnClick")
	assert(
		tostring(err):find(
			"Frame:HookScript(): Cannot assign script handler for 'onclick' (script type not supported by this object)",
			1,
			true
		),
		err
	)
end)

test("slashCommands returns the first alias of each command an addon registered", function()
	local sim = Sim.new()
	sim:addon(fixtures .. "SimSlash", "SimSlash")
	sim:login()
	local commands = sim:slashCommands("SimSlash")
	eq(#commands, 1, "one command")
	eq(commands[1], "/simslash", "the first alias")
end)

test("slash runs a typed command as the chat box does, matching its alias in any case", function()
	local sim = Sim.new()
	sim:addon(fixtures .. "SimSlash", "SimSlash")
	sim:login()
	sim:slash("/SS hello")
	eq(sim.G.SimSlashDB.last, "hello", "the message reached the handler")
	eq(sim.G.SimSlashDB.calls, 1, "one call")
	sim:expectNoErrors("SimSlash")
end)

test("exercise drives an addon's commands in and out of combat and across a reload", function()
	local sim = Sim.new()
	sim:addon(fixtures .. "SimSlash", "SimSlash")
	local reloaded = sim:exercise()
	eq(sim.G.SimSlashDB.calls, 6, "twice and once in combat, for each interface")
	eq(reloaded.G.SimSlashDB.calls, 12, "the reload carried the count forward and ran both interfaces")
end)

test("exercise fails on an error only the reloaded client raises", function()
	local sim = Sim.new()
	sim:addon(fixtures .. "SimSlash", "SimSlash")
	local saved = { SimSlashDB = { calls = 0, failAfterReload = true } }
	local ok, err = pcall(sim.exercise, sim, { savedVariables = saved })
	eq(ok, false, "exercise failed")
	assert(tostring(err):find("SimSlash broke after reload", 1, true), err)
end)

test("the client's alert frames exist at startup and load again as a no-op", function()
	local sim = Sim.new()
	local frame = sim.G.AlertFrame
	eq(type(frame), "table", "AlertFrame")
	local errors = #sim.errors
	sim:loadBlizzard("Blizzard_FrameXML/Mainline/AlertFrames.lua")
	sim:loadBlizzard("Blizzard_FrameXML/Mainline/AlertFrames.xml")
	eq(sim.G.AlertFrame, frame, "the second load changes nothing")
	eq(#sim.errors, errors, "the second load raises nothing")
end)

test("the client's error frame exists at startup and takes a message", function()
	local sim = Sim.new()
	local frame = sim.G.UIErrorsFrame
	eq(type(frame), "table", "UIErrorsFrame")
	local errors = #sim.errors
	frame:AddMessage("x", 1, 0.1, 0.1)
	eq(#sim.errors, errors, "AddMessage raises no error")
end)

test("showing a panel in combat prints the blocked notice and raises no Lua error", function()
	local sim = Sim.new()
	sim:login()
	sim:enterCombat()
	sim:takeErrors()
	local before = #sim.chat
	sim:runAs("SimBlocked", "ShowUIPanel(SettingsPanel)")
	local errors = sim:takeErrors()
	eq(#errors, 0, Sim.describe(errors))
	eq(sim.G.SettingsPanel:IsShown(), false, "the panel stays closed")
	eq(#sim.chat, before + 1, "one notice")
	eq(sim.chat[#sim.chat], sim.G.INTERFACE_ACTION_BLOCKED, "the notice is the client's system message")
	-- The client's function replaces itself with a no-op after its first call.
	sim:runAs("SimBlocked", "ShowUIPanel(SettingsPanel)")
	eq(#sim:takeErrors(), 0, "still no Lua error")
	eq(#sim.chat, before + 1, "the notice is printed once per session")
	sim:leaveCombat()
end)

test("the GameRule enum carries the world map strata and the map opens without a usage error", function()
	local sim = Sim.new()
	orgrimmar(sim)
	eq(type(sim.G.Enum.GameRule.WorldMapFrameStrata), "number", "Enum.GameRule.WorldMapFrameStrata")
	sim:login()
	sim:takeErrors()
	sim:openWorldMap(1454)
	local errors = sim:takeErrors()
	eq(#errors, 0, Sim.describe(errors))
	eq(sim.G.WorldMapFrame:GetMapID(), 1454, "the requested map is open")
	eq(sim.G.WorldMapFrame:GetFrameStrata(), "MEDIUM", "the game rule's strata")
end)

print(string.format("integration_spec: %d passed, %d failed", passed, failed))
os.exit(failed == 0 and 0 or 1)
