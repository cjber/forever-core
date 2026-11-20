-- A wait for a loading event the client fires once per session (PLAYER_LOGIN, VARIABLES_LOADED), made after it
-- fired, never calls back: the files of an addon whose packaged ForeverCore is elected at login run then
-- (cjber/forever-core#984). Sim:strandedWaits names each such wait with the addon line that made it.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")

local sim = Sim.new()
sim:addon(here .. "fixtures/SimStrandedWait", "SimStrandedWait")
sim:login()
sim:expectNoErrors()
local G = sim.G
assert(G.SimStrandedWaitEarly, "a wait made before the login calls back")
assert(G.SimStrandedWaitWorld, "a wait for the world entry still to come calls back")
assert(G.SimStrandedWaitLogin == nil, "the late login wait never calls back")

local waits = sim:strandedWaits("SimStrandedWait")
local found = {}
for _, wait in ipairs(waits) do
	assert(wait.site and wait.site.file:match("SimStrandedWait%.lua$"), "the wait names the addon's file")
	found[#found + 1] = wait.kind .. " " .. wait.event .. " " .. wait.site.line
end
table.sort(found)
assert(
	table.concat(found, ", ") == "callback PLAYER_LOGIN 12, frame VARIABLES_LOADED 16",
	"stranded waits: " .. table.concat(found, ", ")
)
assert(#sim:strandedWaits("SomeOtherAddon") == 0, "filtered by addon")
local ok, err = pcall(sim.expectNoStrandedWaits, sim, "SimStrandedWait")
assert(not ok and err:find("SimStrandedWait.lua:12: SimStrandedWait waits for PLAYER_LOGIN", 1, true), tostring(err))

-- The login again (a scenario's sim:event) reaches every pending wait, so none is stranded any more.
sim:event("PLAYER_LOGIN")
assert(G.SimStrandedWaitLogin, "the wait got the event")
assert(#sim:strandedWaits("SimStrandedWait") == 1, "only the frame wait for VARIABLES_LOADED stays")

-- Waits made before the events fire are never stranded.
local early = Sim.new()
early:login()
early:runAs("SimEarlyWait", "EventUtil.ContinueAfterAllEvents(function() end, 'PLAYER_ENTERING_WORLD')")
early:expectNoStrandedWaits()
print("stranded_wait_spec: late once-only waits are named, early ones and the world entry are not")
