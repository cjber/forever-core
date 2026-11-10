-- Run from the repository root: luajit tests/open_map_spec.lua
-- The shared world map opener asks the client's own restricted C_Map.OpenWorldMap to open, through
-- CreateSecureDelegate: called directly from addon code the client refuses it (cjber/adventure-guide-forever#411,
-- cjber/forever-core#333). It never opens in combat, and it reports false when the client cannot open anything.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local mapCalls = {}
local combat = false
local built = 0
local function RawOpenWorldMap(mapID)
	mapCalls[#mapCalls + 1] = mapID
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
_G.CreateSecureDelegate = CreateDelegate

local function fresh()
	local ns = {}
	assert(loadfile("Core/OpenMap.lua"))("ForeverCore", ns)
	return ns
end

local function reset()
	mapCalls = {}
	combat = false
	built = 0
	_G.C_Map = { OpenWorldMap = RawOpenWorldMap }
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

-- In combat nothing opens, and no delegate is built for a call that cannot run.
reset()
combat = true
ns = fresh()
equal(ns.OpenMap(1413), false, "combat: no map")
equal(#mapCalls, 0, "combat: the map opener is not called")
equal(built, 0, "combat: no delegate is built")

-- A build without CreateSecureDelegate leaves it closed and reports it, rather than erroring (#592).
reset()
_G.CreateSecureDelegate = nil
ns = fresh()
equal(ns.OpenMap(1413), false, "no delegate: no map")
equal(#mapCalls, 0, "no delegate: the map opener is not called")

-- A client without the C function has nothing to delegate to.
reset()
_G.C_Map = {}
ns = fresh()
equal(ns.OpenMap(1413), false, "no C_Map opener: no map")
equal(built, 0, "no C function: no delegate is built")

print(("open_map_spec: %d checks passed"):format(checks))
