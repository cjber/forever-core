-- Run from the repository root: luajit tests/open_map_spec.lua
-- The shared world map opener asks the client's restricted C_Map.OpenWorldMap through securecallfunction.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local mapCalls = {}
local combat = false
local function RawOpenWorldMap(mapID)
	mapCalls[#mapCalls + 1] = { mapID = mapID }
end

_G.InCombatLockdown = function()
	return combat
end
_G.C_Map = { OpenWorldMap = RawOpenWorldMap }
_G.securecallfunction = function(fn, ...)
	equal(fn, RawOpenWorldMap, "secure boundary receives the exact C opener")
	return fn(...)
end

local function fresh()
	local ns = {}
	assert(loadfile("Core/OpenMap.lua"))("ForeverCore", ns)
	return ns
end

local function reset()
	mapCalls = {}
	combat = false
	_G.C_Map = { OpenWorldMap = RawOpenWorldMap }
	_G.securecallfunction = function(fn, ...)
		equal(fn, RawOpenWorldMap, "secure boundary receives the exact C opener")
		return fn(...)
	end
end

-- The world map receives the requested ID, with zero and omitted IDs normalized to nil.
reset()
local ns = fresh()
equal(ns.OpenMap(1413), true, "map: opens")
equal(#mapCalls, 1, "map: the client opener runs once")
equal(mapCalls[1].mapID, 1413, "map: on the requested map")
equal(ns.OpenMap(0), true, "map: a zero map id opens")
equal(mapCalls[2].mapID, nil, "map: zero becomes the client's no-map id")
equal(ns.OpenMap(), true, "map: no map id opens")
equal(mapCalls[3].mapID, nil, "map: no map id stays nil")

equal(#mapCalls, 3, "all calls, including nil map IDs, reach the opener")

-- In combat nothing opens.
reset()
combat = true
ns = fresh()
equal(ns.OpenMap(1413), false, "combat: no map")
equal(#mapCalls, 0, "combat: the map opener is not called")

-- A build without securecallfunction leaves it closed and reports it.
reset()
_G.securecallfunction = nil
ns = fresh()
equal(ns.OpenMap(1413), false, "no secure boundary: no map")
equal(#mapCalls, 0, "no secure boundary: the map opener is not called")

-- A client without the C function leaves the map closed.
reset()
_G.C_Map = {}
ns = fresh()
equal(ns.OpenMap(1413), false, "no C_Map opener: no map")

print(("open_map_spec: %d checks passed"):format(checks))
