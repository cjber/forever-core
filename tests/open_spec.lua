-- Run from the repository root: luajit tests/open_spec.lua
-- The shared opener asks the client's own restricted functions to open the world map and the settings panel, through
-- CreateSecureDelegate: called directly from addon code the client refuses both (cjber/adventure-guide-forever#411,
-- cjber/forever-core#333). It never opens in combat, and it reports false when the client cannot open anything.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local mapCalls, settingsCalls = {}, {}
local combat = false
local built = 0
local function RawOpenWorldMap(mapID)
	mapCalls[#mapCalls + 1] = mapID
end
local function RawOpenSettingsPanel(categoryID, element)
	settingsCalls[#settingsCalls + 1] = { categoryID, element }
end
local function CreateDelegate(fn)
	built = built + 1
	return function(...)
		return fn(...)
	end
end

_G.InCombatLockdown = function()
	return combat
end
_G.C_Map = { OpenWorldMap = RawOpenWorldMap }
_G.C_SettingsUtil = { OpenSettingsPanel = RawOpenSettingsPanel }
_G.CreateSecureDelegate = CreateDelegate

local function fresh()
	local ns = {}
	assert(loadfile("Core/Open.lua"))("ForeverCore", ns)
	return ns
end

local function reset()
	mapCalls, settingsCalls = {}, {}
	combat = false
	built = 0
	_G.C_Map = { OpenWorldMap = RawOpenWorldMap }
	_G.C_SettingsUtil = { OpenSettingsPanel = RawOpenSettingsPanel }
	_G.CreateSecureDelegate = CreateDelegate
end

-- The world map: the client's opener is wrapped once and run, and no map id stays no map id.
reset()
local ns = fresh()
equal(ns.OpenMap(1413), true, "map: opens")
equal(#mapCalls, 1, "map: the client opener runs once")
equal(mapCalls[1], 1413, "map: on the requested map")
equal(built, 1, "map: through one secure delegate")
equal(ns.OpenMap(0), true, "map: a zero map id opens")
equal(mapCalls[2], nil, "map: zero becomes the client's no-map id")
equal(ns.OpenMap(), true, "map: no map id opens")
equal(mapCalls[3], nil, "map: no map id stays nil")
equal(built, 1, "map: the delegate is reused")

-- The settings panel: same delegate rule, with and without a category and scroll target.
reset()
ns = fresh()
equal(ns.OpenSettingsPanel(313), true, "settings: opens")
equal(settingsCalls[1][1], 313, "settings: on the requested category")
equal(settingsCalls[1][2], nil, "settings: with no scroll target")
equal(built, 1, "settings: through one secure delegate")
equal(ns.OpenSettingsPanel(313, "ForeverCore"), true, "settings: opens at a row")
equal(settingsCalls[2][1], 313, "settings: the category is kept")
equal(settingsCalls[2][2], "ForeverCore", "settings: the scroll target is passed")
equal(ns.OpenSettingsPanel(), true, "settings: no category opens the panel")
equal(settingsCalls[3][1], nil, "settings: no category stays nil")
equal(built, 1, "settings: the delegate is reused")

-- In combat nothing opens, and no delegate is built for a call that cannot run.
reset()
combat = true
ns = fresh()
equal(ns.OpenMap(1413), false, "combat: no map")
equal(ns.OpenSettingsPanel(313), false, "combat: no settings")
equal(#mapCalls, 0, "combat: the map opener is not called")
equal(#settingsCalls, 0, "combat: the settings opener is not called")
equal(built, 0, "combat: no delegate is built")

-- A build without CreateSecureDelegate leaves both closed and reports it, rather than erroring (#592).
reset()
_G.CreateSecureDelegate = nil
ns = fresh()
equal(ns.OpenMap(1413), false, "no delegate: no map")
equal(ns.OpenSettingsPanel(313), false, "no delegate: no settings")
equal(#mapCalls, 0, "no delegate: the map opener is not called")
equal(#settingsCalls, 0, "no delegate: the settings opener is not called")

-- A client without the C function has nothing to delegate to.
reset()
_G.C_Map = {}
_G.C_SettingsUtil = {}
ns = fresh()
equal(ns.OpenMap(1413), false, "no C_Map opener: no map")
equal(ns.OpenSettingsPanel(313), false, "no C_SettingsUtil opener: no settings")
equal(built, 0, "no C function: no delegate is built")

print(("open_spec: %d checks passed"):format(checks))
