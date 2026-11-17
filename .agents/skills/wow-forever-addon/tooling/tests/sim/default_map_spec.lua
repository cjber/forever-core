-- The native map's default selection must refer to a map in the default world.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
local sim = Sim.new({ addon = false })
sim:login()
sim:openWorldMap()
local id = sim.G.WorldMapFrame:GetMapID()
assert(sim.G.C_Map.GetMapInfo(id), "native default map " .. tostring(id) .. " missing")
assert(sim.G.C_Map.GetMapInfo(947).mapType == sim.G.Enum.UIMapType.World, "Azeroth must be a World map")
sim:expectNoErrors()
assert(sim.G.C_Map.GetMapInfo(999999999) == nil, "unknown maps remain absent")
print("default_map_spec: passed")
