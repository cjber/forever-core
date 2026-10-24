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
	eq(sim.secret.is(sim.G.UnitName("target")), true, "in combat")
	eq(sim.secret.is(sim.G.UnitName("player")), false, "the player")
	eq(sim.secret.is(sim.G.UnitHealth("player")), true, "SecretReturns")
end)

test("a protected frame changed from addon code in combat is ADDON_ACTION_BLOCKED", function()
	local sim = Sim.new({ blizzard = {} })
	sim:runAs("SimCombat", 'SimSecureFrame = CreateFrame("Frame", "SimSecureFrame", UIParent)')
	sim.widgets.state[sim.G.SimSecureFrame].protected = true
	sim.inCombat = true
	sim:runAs("SimCombat", "SimSecureFrame:SetPoint('CENTER')")
	sim:expectError(
		"[ADDON_ACTION_BLOCKED] AddOn 'SimCombat' tried to call the protected function 'SimSecureFrame:SetPoint()'"
	)
	sim.inCombat = false
	sim:takeErrors()
	sim:runAs("SimCombat", "SimSecureFrame:SetPoint('CENTER')")
	eq(#sim.errors, 0, "allowed out of combat")
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

print(string.format("integration_spec: %d passed, %d failed", passed, failed))
os.exit(failed == 0 and 0 or 1)
