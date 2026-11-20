-- core_load.lua: a partial ForeverCore load runs without the files it leaves out (Core.lua, UI/TrackerHost.lua).
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local CoreLoad = dofile(here .. "../../forever_sim/core_load.lua")
local root = here .. "../../../../../../"

local function Env()
	local waits = {}
	local env = setmetatable({
		EventUtil = {
			ContinueAfterAllEvents = function(callback, ...)
				waits[#waits + 1] = { callback = callback, events = table.concat({ ... }, ",") }
			end,
		},
	}, { __index = _G })
	return env, waits
end

-- Core/SafeCall.lua installs its error handler through ns.AtStart, which Core.lua defines: run at once here.
local env = Env()
local ns = CoreLoad.load(env, { names = { "Core/SafeCall.lua" }, directory = root })
assert(type(ns.SafeCall) == "table" or type(ns.SafeCall) == "function", "SafeCall loads without Core.lua")
assert(ns.started == nil, "Core.lua did not load")
local ran = false
ns.AtStart(function()
	ran = true
end)
assert(ran, "AtStart work runs at once in a partial load")

-- A hand-built namespace beside the real UI/TrackerSection.lua: AfterWorldEvents waits for both world events.
local sectionEnv, waits = Env()
local hostNs = { TrackerHost = {}, SafeCall = ns.SafeCall }
local ok, problem = pcall(CoreLoad.file, sectionEnv, "UI/TrackerSection.lua", hostNs, { directory = root })
assert(ok, "TrackerSection loads beside a stand-in host: " .. tostring(problem))
assert(type(hostNs.AfterWorldEvents) == "function", "the stand-in host gets AfterWorldEvents")
local fired = false
hostNs.AfterWorldEvents(function()
	fired = true
end)
assert(waits[#waits].events == "PLAYER_ENTERING_WORLD,VARIABLES_LOADED" and not fired, "waits for both world events")
waits[#waits].callback()
assert(fired, "runs once both have fired")

-- A namespace's own functions win over the stand-ins.
local own = function() end
assert(CoreLoad.standIns({ AtStart = own }, env).AtStart == own, "an existing AtStart stays")

print("core_load_spec: passed")
