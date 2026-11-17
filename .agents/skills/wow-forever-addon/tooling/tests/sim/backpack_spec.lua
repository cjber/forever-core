-- Backpack startup must initialize its token tracker through the native addon.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
local sim = Sim.new({ addon = false })
sim:login()
sim:expectNoErrors()
sim:input(function()
	sim.G.ToggleBackpack()
end)
sim:expectNoErrors()
assert(sim.G.C_AddOns.IsAddOnLoaded("Blizzard_TokenUI"))
print("backpack_spec: passed")
