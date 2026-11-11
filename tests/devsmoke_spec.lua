-- Contract for the in-game smoke addon: it finds every loaded Forever addon's bare slash surface, runs each one
-- twice plus the world map, and records a pass or fail per surface without printing to chat.
local realPrint = print
local checks = 0
local function check(value, label)
	assert(value, label)
	checks = checks + 1
end
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

-- The client stubs the addon reaches for, all globals the way the client has them.
local addons = {}
local frames = {}
local queue = {}
local delays = {}
local taint = {}
local uiErrors = {}
local chat = {}
local defaultMessages = {}
local mapToggles = 0
local inCombat = false
local leaderboardCalls = {}
local fakeCalls = { count = 0, messages = {} }
-- The profiler clock the addon times each action with, and how many extra milliseconds the fake command spends on
-- each of its two runs: the second run is the slower one, so the surface has to keep that as its cost.
local stop = 0
local fakeDurations = { 0, 9 }

local function addAddon(name, loaded, deps)
	addons[#addons + 1] = { name = name, loaded = loaded ~= false, deps = deps }
end

local function addCommand(addonName, key, alias, handler)
	local global = "SLASH_" .. key .. "1"
	_G[global] = alias
	taint[global] = addonName
	SlashCmdList[key] = handler
end

_G.SlashCmdList = {}
_G.DevSmokeDB = nil
_G.SLASH_DEVSMOKE1 = nil
_G.print = function(...)
	chat[#chat + 1] = ...
end

_G.CreateFrame = function(kind)
	local frame = { kind = kind, events = {}, scripts = {} }
	function frame:RegisterEvent(event)
		self.events[event] = true
	end
	function frame:SetScript(script, handler)
		self.scripts[script] = handler
	end
	frames[#frames + 1] = frame
	return frame
end

local function fire(event, ...)
	for _, frame in ipairs(frames) do
		if frame.events[event] and frame.scripts.OnEvent then
			frame.scripts.OnEvent(frame, event, ...)
		end
	end
end

_G.issecurevariable = function(name)
	local owner = taint[name]
	if owner then
		return false, owner
	end
	return true
end

_G.C_AddOns = {
	GetNumAddOns = function()
		return #addons
	end,
	GetAddOnInfo = function(index)
		return addons[index] and addons[index].name or nil
	end,
	IsAddOnLoaded = function(which)
		local name = type(which) == "number" and addons[which] and addons[which].name or which
		for _, addon in ipairs(addons) do
			if addon.name == name then
				return addon.loaded
			end
		end
		return false
	end,
	-- The TOC's ## Dependencies names, as multiple return values the way the client answers.
	GetAddOnDependencies = function(which)
		local name = type(which) == "number" and addons[which] and addons[which].name or which
		for _, addon in ipairs(addons) do
			if addon.name == name then
				return unpack(addon.deps or {})
			end
		end
	end,
}

_G.C_Timer = {
	After = function(delay, handler)
		delays[#delays + 1] = delay
		queue[#queue + 1] = handler
	end,
}

local currentHandler
currentHandler = function(message)
	defaultMessages[#defaultMessages + 1] = message
end
_G.geterrorhandler = function()
	return currentHandler
end
_G.seterrorhandler = function(handler)
	currentHandler = handler
end

_G.InCombatLockdown = function()
	return inCombat
end

_G.UIErrorsFrame = {
	AddMessage = function(_, text)
		uiErrors[#uiErrors + 1] = text
	end,
}

_G.ToggleWorldMap = function()
	mapToggles = mapToggles + 1
end

local clock = 0
_G.time = function()
	clock = clock + 1
	return clock
end
_G.GetBuildInfo = function()
	return "1.60.1", "1.60.1.60000", "Nov 4 2026", "60000"
end
_G.debugstack = function()
	return "stack trace"
end
_G.debugprofilestop = function()
	stop = stop + 1
	return stop
end

local function drain()
	local steps = 0
	while #queue > 0 do
		local handler = table.remove(queue, 1)
		handler()
		steps = steps + 1
		assert(steps < 1000, "the step queue did not settle")
	end
end

local function latest()
	local runs = DevSmokeDB and DevSmokeDB.runs
	return runs and runs[#runs]
end

local function surfaceOf(run, label)
	for _, result in ipairs(run.results) do
		if result.surface == label then
			return result
		end
	end
end

-- A Forever addon, a non-Forever one, one that is not loaded, and a dev addon, as the client would list them. Ours is
-- the ForeverCore dependency, not the name: NaowhForever is third-party and BrandNewForever is in no list at all.
addAddon("!!DevSmoke")
addAddon("!!DevSessionLog")
addAddon("CommissionsForever", true, { "ForeverCore" })
addAddon("AtlasLootClassic")
addAddon("NaowhForever", true, { "AtlasLootClassic" })
addAddon("SkillUpForever", false, { "ForeverCore" })
addAddon("TweaksForever", true, { "ForeverCore" })
addAddon("MacroAssistForever", true, { "ForeverCore" })
addAddon("BrandNewForever", true, { "ForeverCore" })
addAddon("ForeverCore")

addCommand("CommissionsForever", "FAKE", "/fake", function(message, editBox)
	fakeCalls.count = fakeCalls.count + 1
	fakeCalls.messages[#fakeCalls.messages + 1] = { message = message, editBox = editBox }
	stop = stop + (fakeDurations[fakeCalls.count] or 0)
end)
addCommand("AtlasLootClassic", "ATLAS", "/atlas", function() end)
addCommand("NaowhForever", "NAOWH", "/naowh", function()
	error("a third-party addon's command must not run")
end)
addCommand("SkillUpForever", "SKILLUP", "/skillup", function() end)
local macroAssistCalls = 0
addCommand("MacroAssistForever", "MACROASSIST", "/macroassist", function()
	macroAssistCalls = macroAssistCalls + 1
end)
addCommand("BrandNewForever", "BRANDNEW", "/brandnew", function() end)
addCommand("TweaksForever", "TWEAKSFOREVER_RELOAD", "/rl", function()
	error("the reload command must not run")
end)
SlashCmdList["FOREVERLEADERBOARDS"] = function(message, ...)
	local second = ...
	leaderboardCalls[#leaderboardCalls + 1] = { message = message, extra = select("#", ...), second = second }
end
_G.SLASH_FOREVERLEADERBOARDS1 = "/forever"
_G.SLASH_FOREVERLEADERBOARDS2 = "/flb"
taint["SLASH_FOREVERLEADERBOARDS1"] = "ForeverCore"
taint["SLASH_FOREVERLEADERBOARDS2"] = "ForeverCore"

-- What the client's ChatFrameUtil.ImportListToHash does on every slash parse: each entry moves into the proxy table
-- behind the list's __index, and the list itself is wiped.
local function importSlashLists()
	local meta = getmetatable(SlashCmdList) or {}
	local proxy = meta.__index or {}
	for key, handler in pairs(SlashCmdList) do
		proxy[key] = handler
	end
	for key in pairs(proxy) do
		SlashCmdList[key] = nil
	end
	meta.__index = proxy
	setmetatable(SlashCmdList, meta)
end

local beforeLoad = {}
for key in pairs(_G) do
	beforeLoad[key] = true
end
assert(loadfile("tools/devsmoke/!!DevSmoke/Core.lua"))("!!DevSmoke", {})
local added = {}
for key in pairs(_G) do
	if not beforeLoad[key] then
		added[#added + 1] = key
	end
end
table.sort(added)
equal(table.concat(added, ","), "SLASH_DEVSMOKE1", "the addon adds only its slash alias at load")
taint["SLASH_DEVSMOKE1"] = "!!DevSmoke"

fire("PLAYER_LOGIN")
equal(SLASH_DEVSMOKE1, "/devsmoke", "the addon registers /devsmoke")
check(type(SlashCmdList.DEVSMOKE) == "function", "/devsmoke has a handler")
local listened = {}
for _, frame in ipairs(frames) do
	for event in pairs(frame.events) do
		listened[event] = true
	end
end
check(listened.PLAYER_LOGIN, "the addon waits for login")
check(
	listened.ADDON_ACTION_BLOCKED and listened.ADDON_ACTION_FORBIDDEN and listened.LUA_WARNING,
	"the addon listens for blocked and forbidden actions and warnings"
)

-- A run opens and closes each surface, then the world map, and only the fake addon's command counts as one.
local mapBefore = mapToggles
importSlashLists()
SlashCmdList.DEVSMOKE("", nil)
check(latest() ~= nil, "a run is recorded")
equal(#queue, 1, "one step waits after the first")
drain()
local run = latest()
equal(run.build, "60000", "the build string is recorded")
equal(fakeCalls.count, 2, "the fake surface runs twice")
equal(fakeCalls.messages[1].message, "", "the surface is run bare")
equal(fakeCalls.messages[1].editBox, nil, "the surface gets no edit box")
equal(fakeCalls.messages[2].message, "", "the surface is run bare the second time")
equal(mapToggles - mapBefore, 2, "the world map toggles twice")
local fake = surfaceOf(run, "CommissionsForever /fake")
check(fake ~= nil, "the surface is named after its addon and first alias")
check(fake.ok, "the fake surface passes")
equal(#fake.errors, 0, "a passing surface has no errors")
equal(fake.firstMs, 1, "the first run is timed on its own as the cold open")
equal(fake.ms, 10, "the surface keeps the slowest of its two runs")
local mapSurface = surfaceOf(run, "world map")
check(type(mapSurface.firstMs) == "number", "the world map's first run is timed")
equal(mapSurface.ms, mapSurface.firstMs, "a surface that costs the same twice keeps that cost")
local fakeSurfaces = 0
for _, result in ipairs(run.results) do
	if result.surface == "CommissionsForever /fake" then
		fakeSurfaces = fakeSurfaces + 1
	end
end
equal(fakeSurfaces, 1, "each command is one surface")
check(surfaceOf(run, "AtlasLootClassic /atlas") == nil, "a non-Forever addon is not a surface")
check(surfaceOf(run, "SkillUpForever /skillup") == nil, "an unloaded Forever addon is not a surface")
check(surfaceOf(run, "TweaksForever /rl") == nil, "the reload command is not a surface")
check(surfaceOf(run, "NaowhForever /naowh") == nil, "a third-party addon ending in Forever is not a surface")
check(surfaceOf(run, "!!DevSmoke /devsmoke") == nil, "the smoke addon does not test itself")
check(surfaceOf(run, "ForeverCore /forever") ~= nil, "the leaderboards command is a surface")
local macroAssist = surfaceOf(run, "MacroAssistForever /macroassist")
check(macroAssist ~= nil, "an addon depending on ForeverCore is a surface")
check(macroAssist.ok, "the Macro Assist surface passes")
equal(macroAssistCalls, 2, "the Macro Assist surface runs twice")
check(surfaceOf(run, "BrandNewForever /brandnew") ~= nil, "an addon in no list is covered by its dependency")
equal(#run.results, 5, "four commands and the world map")
equal(uiErrors[#uiErrors], ("Dev Smoke: %d surfaces, 0 failed"):format(#run.results), "the summary is shown")
equal(delays[1], 0.5, "steps are half a second apart")

-- A command that errors fails only its own surface, and the rest of the run goes on.
local boomCalls = 0
addCommand("CommissionsForever", "BOOM", "/boom", function()
	boomCalls = boomCalls + 1
	error("boom from the fake addon")
end)
SlashCmdList.DEVSMOKE("", nil)
drain()
run = latest()
local boom = surfaceOf(run, "CommissionsForever /boom")
check(boom ~= nil, "the second fake command is a surface")
equal(boom.ok, false, "an error fails its surface")
check(boom.errors[1]:find("boom from the fake addon", 1, true) ~= nil, "the error message is recorded")
equal(boom.errors[2], "stack trace", "the stack is recorded")
equal(boomCalls, 2, "a failing surface still runs twice")
check(type(boom.firstMs) == "number" and type(boom.ms) == "number", "a failing surface is still timed")
equal(surfaceOf(run, "CommissionsForever /fake").ok, true, "another surface still passes")
check(surfaceOf(run, "world map") ~= nil, "the run reaches the world map after an error")
equal(#run.results, 6, "the failing surface is still one surface")
equal(uiErrors[#uiErrors], "Dev Smoke: 6 surfaces, 1 failed", "the summary counts the failure")

-- /forever selftest starts a run; anything else reaches the shared leaderboards handler untouched.
local runsBefore = #DevSmokeDB.runs
SlashCmdList.FOREVERLEADERBOARDS("other", "extra")
equal(#DevSmokeDB.runs, runsBefore, "another /forever command does not start a run")
equal(leaderboardCalls[#leaderboardCalls].message, "other", "the original handler gets the same words")
equal(leaderboardCalls[#leaderboardCalls].second, "extra", "the original handler gets the same arguments")
SlashCmdList.FOREVERLEADERBOARDS("selftest")
equal(#DevSmokeDB.runs, runsBefore + 1, "/forever selftest starts a run")
drain()
run = latest()
equal(#run.results, 6, "/forever selftest runs every surface")

-- In combat nothing is run at all.
inCombat = true
runsBefore = #DevSmokeDB.runs
SlashCmdList.DEVSMOKE("", nil)
run = latest()
equal(#DevSmokeDB.runs, runsBefore + 1, "a combat run is still recorded")
equal(run.result, "skipped: in combat", "the run is marked skipped")
equal(#run.results, 0, "a skipped run tests nothing")
equal(#queue, 0, "a skipped run schedules nothing")
inCombat = false

-- The global error handler is chained while a run is active and restored afterwards.
local saved = geterrorhandler()
SlashCmdList.DEVSMOKE("", nil)
run = latest()
check(geterrorhandler() ~= saved, "a run chains the global error handler")
geterrorhandler()("chained failure")
local chainedTo
for _, result in ipairs(run.results) do
	for _, message in ipairs(result.errors) do
		if message:find("chained failure", 1, true) then
			chainedTo = result
		end
	end
end
check(chainedTo ~= nil, "a chained error is attributed to a surface")
equal(chainedTo.surface, run.results[1].surface, "the current step owns an error raised during it")
equal(defaultMessages[#defaultMessages], "chained failure", "the previous handler still sees the error")
drain()
equal(geterrorhandler(), saved, "the previous handler is restored after the run")

-- Taint and warning reports land in the step that is running when they arrive.
SlashCmdList.DEVSMOKE("", nil)
run = latest()
fire("ADDON_ACTION_BLOCKED", "CommissionsForever", "ProtectedThing")
fire("LUA_WARNING", "a warning")
drain()
local messages = {}
for _, result in ipairs(run.results) do
	for _, message in ipairs(result.errors) do
		messages[#messages + 1] = message
	end
end
local function contains(needle)
	for _, message in ipairs(messages) do
		if message:find(needle, 1, true) then
			return true
		end
	end
	return false
end
check(contains("ADDON_ACTION_BLOCKED: CommissionsForever ProtectedThing"), "a blocked action is recorded")
check(contains("LUA_WARNING: a warning"), "a warning is recorded")

-- The database keeps the newest twenty runs and nothing reaches chat.
for _ = 1, 25 do
	SlashCmdList.DEVSMOKE("", nil)
	drain()
end
equal(#DevSmokeDB.runs, 20, "only the last twenty runs are kept")
equal(#chat, 0, "nothing is printed to chat")

_G.print = realPrint
print(("smoke_spec: %d checks passed"):format(checks))
