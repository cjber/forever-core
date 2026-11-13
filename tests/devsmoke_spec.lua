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
local foreverCalls = {}
local fakeCalls = { count = 0, messages = {} }
-- The profiler clock the addon times each action with, and how many extra milliseconds the fake command spends on
-- each of its two runs: the second run is the slower one, so the surface has to keep that as its cost.
local stop = 0
local fakeDurations = { 0, 9 }

local function addAddon(name, loaded, deps, version)
	addons[#addons + 1] = { name = name, loaded = loaded ~= false, deps = deps, version = version }
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
	GetAddOnMetadata = function(which, field)
		local name = type(which) == "number" and addons[which] and addons[which].name or which
		for _, addon in ipairs(addons) do
			if addon.name == name then
				return field == "Version" and addon.version or nil
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

-- The chat windows this session has: ChatFrame1 is General. The Agent tab is made by the addon on first use, with no
-- channels, and every command's lines land in its own message list.
local chatWindows = {}
local selectedChat = {}
local openedChat = {}
local function addChatWindow(name)
	local frame = { name = name, messages = {} }
	function frame:AddMessage(text)
		self.messages[#self.messages + 1] = text
	end
	chatWindows[#chatWindows + 1] = frame
	_G["ChatFrame" .. #chatWindows] = frame
	return frame
end
addChatWindow("General")
_G.NUM_CHAT_WINDOWS = 10
_G.GetChatWindowInfo = function(index)
	local frame = chatWindows[index]
	return frame and frame.name
end
_G.FCF_OpenNewWindow = function(name, noDefaultChannels)
	local frame = addChatWindow(name)
	openedChat[#openedChat + 1] = { name = name, noChannels = noDefaultChannels }
	return frame, #chatWindows
end
_G.FCF_SelectDockFrame = function(frame)
	selectedChat[#selectedChat + 1] = frame
end

local function agentMessages()
	local frame
	for _, window in ipairs(chatWindows) do
		if window.name == "Agent" then
			frame = window
		end
	end
	return frame and frame.messages or {}
end

-- The lines one command prints to the Agent tab, and nothing the command before it printed.
local function command(text)
	local before = #agentMessages()
	SlashCmdList.DEVSMOKE(text, nil)
	local messages = agentMessages()
	local lines = {}
	for index = before + 1, #messages do
		lines[#lines + 1] = messages[index]
	end
	return lines
end

-- This session's BugGrabber entries: the /run line's own error in one message, and an addon error whose stack names
-- a /run chunk in another, which is counted.
local bugSession = 7
local bugErrors = {}
_G.BugGrabber = {
	GetDB = function()
		return bugErrors
	end,
	GetSessionId = function()
		return bugSession
	end,
}

-- The Thanks page the addon opens and scrolls, and the profession tabs it selects.
local thanksOpen = {}
local selectedProfession
local scroll = { value = 0, immediate = false, range = 240 }
function scroll:GetVerticalScrollRange()
	return self.range
end
function scroll:SetVerticalScroll(value)
	self.value = value
end
-- The client's ScrollFrameTemplate bar: a percentage between 0 and 1, applied at once.
scroll.ScrollBar = {
	SetScrollPercentage = function(_, percentage, immediate)
		scroll.value = percentage * scroll.range
		scroll.immediate = immediate
	end,
}
local contents = { top = 500, parent = scroll }
function contents:GetTop()
	return self.top
end
function contents:GetParent()
	return self.parent
end
local creditsWindow = { contents = contents, rows = {}, shown = true }
function creditsWindow:IsShown()
	return self.shown
end
function creditsWindow:Hide()
	self.shown = false
end
local function creditRow(name, top)
	local holder = { top = top }
	function holder:GetTop()
		return self.top
	end
	function holder:IsShown()
		return self.visible ~= false
	end
	return { row = { name = name }, holder = holder }
end
creditsWindow.rows = { creditRow("Zerosprey42", 380), creditRow("Someone Else", 360) }
local creditPlayers = {
	{ name = "Zerosprey42", helped = { { addon = "ForeverCore", what = "an idea" } }, count = 1 },
}
local creditInspired = {
	{ name = "Jiik", helped = { { addon = "Adventure Guide Forever", what = "" } }, count = 1 },
}
_G.ForeverCore = {
	Credits = {
		Open = function(title)
			thanksOpen[#thanksOpen + 1] = title
			return true
		end,
		Players = function()
			return creditPlayers
		end,
		Inspired = function()
			return creditInspired
		end,
		window = creditsWindow,
	},
	ProfessionTabs = {
		Select = function(key)
			selectedProfession = key
		end,
	},
}

-- The windows /devsmoke close hides: the professions window, the world map and the settings panel.
local professionWindow = { shown = false }
function professionWindow:IsShown()
	return self.shown
end
function professionWindow:Hide()
	self.shown = false
end
_G.ProfessionsFrame = professionWindow
local worldMapWindow = { shown = true }
function worldMapWindow:IsShown()
	return self.shown
end
function worldMapWindow:Hide()
	self.shown = false
end
_G.WorldMapFrame = worldMapWindow
local settingsWindow = { shown = true }
function settingsWindow:IsShown()
	return self.shown
end
function settingsWindow:Close()
	self.shown = false
end
function settingsWindow:Hide()
	self.shown = false
end
_G.SettingsPanel = settingsWindow
local hiddenPanels = {}
_G.HideUIPanel = function(frame)
	hiddenPanels[#hiddenPanels + 1] = frame
	frame:Hide()
end
local openedSkills = {}
_G.C_TradeSkillUI = {
	OpenTradeSkill = function(id)
		openedSkills[#openedSkills + 1] = id
		professionWindow.shown = true
	end,
}

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
addAddon("CommissionsForever", true, { "ForeverCore" }, "1.2.3")
addAddon("AtlasLootClassic")
addAddon("NaowhForever", true, { "AtlasLootClassic" })
addAddon("SkillUpForever", false, { "ForeverCore" }, "1.4.0")
addAddon("TweaksForever", true, { "ForeverCore" }, "1.10.0")
addAddon("MacroAssistForever", true, { "ForeverCore" }, "2.0.0")
addAddon("BrandNewForever", true, { "ForeverCore" }, "0.9.0")
addAddon("ForeverCore", true, nil, "2.5.0")
addAddon("LibAHTab", true, nil, "1.0.4")

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
SlashCmdList["FOREVERCORE"] = function(message, ...)
	local second = ...
	foreverCalls[#foreverCalls + 1] = { message = message, extra = select("#", ...), second = second }
end
_G.SLASH_FOREVERCORE1 = "/fcore"
_G.SLASH_FOREVERCORE2 = "/forever"
taint["SLASH_FOREVERCORE1"] = "ForeverCore"
taint["SLASH_FOREVERCORE2"] = "ForeverCore"

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
check(surfaceOf(run, "ForeverCore /fcore") ~= nil, "core's command is a surface")
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

-- /forever selftest starts a run; anything else reaches core's handler untouched.
local runsBefore = #DevSmokeDB.runs
SlashCmdList.FOREVERCORE("other", "extra")
equal(#DevSmokeDB.runs, runsBefore, "another /forever command does not start a run")
equal(foreverCalls[#foreverCalls].message, "other", "the original handler gets the same words")
equal(foreverCalls[#foreverCalls].second, "extra", "the original handler gets the same arguments")
SlashCmdList.FOREVERCORE("selftest")
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

-- /devsmoke tab makes the Agent tab with no channels, selects it, and tab off returns to General.
local tabLines = command("tab")
equal(#openedChat, 1, "the Agent tab is created once")
equal(openedChat[1].name, "Agent", "the new tab is named Agent")
equal(openedChat[1].noChannels, true, "the Agent tab listens to no channels")
equal(selectedChat[#selectedChat], _G.ChatFrame2, "the Agent tab is selected")
equal(tabLines[1], "Dev Smoke: Agent tab selected", "the selection is reported")
command("tab")
equal(#openedChat, 1, "a second tab command reuses the Agent tab")
equal(selectedChat[#selectedChat], _G.ChatFrame2, "the Agent tab is selected again")
local offLines = command("tab off")
equal(selectedChat[#selectedChat], _G.ChatFrame1, "tab off selects General")
equal(offLines[1], "Dev Smoke: General tab selected", "the return to General is reported")

-- /devsmoke versions lists ForeverCore, LibAHTab and every loaded addon depending on ForeverCore.
local versionLines = command("versions")
equal(#versionLines, 7, "core, LibAHTab and four loaded Forever addons")
equal(versionLines[1], "Dev Smoke: addons", "the versions are headed")
equal(versionLines[2], "ForeverCore | version 2.5.0 | loaded", "core's own version")
equal(versionLines[3], "LibAHTab | version 1.0.4 | loaded", "the tab library's version")
equal(versionLines[4], "BrandNewForever | version 0.9.0 | loaded", "an addon in no list is listed")
equal(versionLines[7], "TweaksForever | version 1.10.0 | loaded", "the loaded addons are sorted by folder")
local listed = table.concat(versionLines, "\n")
check(not listed:find("SkillUpForever", 1, true), "an unloaded Forever addon is left out")
check(not listed:find("AtlasLootClassic", 1, true), "a non-Forever addon is left out")

-- /devsmoke errors reports this session's BugGrabber entries, minus the error a chat /run line itself raises.
bugErrors[#bugErrors + 1] = { message = "a plain error", session = 7 }
bugErrors[#bugErrors + 1] = { message = '[string "SLASH_FAKE"]:1: attempt to call a nil value', session = 7 }
bugErrors[#bugErrors + 1] = { message = "an earlier session's error", session = 6 }
bugErrors[#bugErrors + 1] = {
	message = "an addon error from a /run line",
	session = 7,
	stack = 'in function <[string "SLASH_FAKE"]:1>',
}
bugErrors[#bugErrors + 1] = { message = string.rep("long words ", 40), session = 7 }
local errorLines = command("errors")
equal(errorLines[1], "Dev Smoke: 3 errors this session", "only this session's own errors count")
equal(errorLines[2], "1: a plain error", "an error under 180 characters prints whole")
equal(errorLines[3], "2: an addon error from a /run line", "a /run chunk in the stack does not hide an addon error")
equal(#errorLines[4], 183, "a long error is cut to its first 180 characters")
check(errorLines[4]:find("long words", 1, true) ~= nil, "the cut keeps the start of the message")
local errorText = table.concat(errorLines, "\n")
check(not errorText:find("earlier session", 1, true), "an error from an earlier session is left out")
check(not errorText:find("attempt to call a nil value", 1, true), "the /run line's own error is left out")
local grabber = _G.BugGrabber
_G.BugGrabber = nil
local missingErrors = command("errors")
equal(missingErrors[1], "Dev Smoke: BugGrabber is not loaded", "a missing BugGrabber is reported")
_G.BugGrabber = grabber

-- /devsmoke thanks opens the filtered page and scrolls the list to the named player's row.
local thanksLines = command("thanks ForeverCore")
equal(thanksOpen[#thanksOpen], "ForeverCore", "the addon title opens its filtered page")
equal(thanksLines[1], "Dev Smoke: Thanks opened for ForeverCore", "the open is reported")
local scrolled = command("thanks Adventure Guide Forever Zerosprey42")
equal(thanksOpen[#thanksOpen], "Adventure Guide Forever", "a title with spaces opens whole")
equal(scroll.value, 120, "the named player's row is scrolled to the top")
equal(scroll.immediate, true, "the scroll is applied at once")
equal(scrolled[1], "Dev Smoke: Thanks at Zerosprey42", "the scroll is reported")
local absent = command("thanks ForeverCore Nobody")
equal(thanksOpen[#thanksOpen], "ForeverCore", "the page still opens for an unknown player")
equal(absent[1], "Dev Smoke: no credit row for Nobody", "a missing row is reported")
local thanksUsage = command("thanks")
equal(thanksUsage[1], "Dev Smoke: usage /devsmoke thanks <addon title> [player]", "no arguments prints usage")

-- /devsmoke prof opens Cooking when no profession window is open, then selects the addon's tab.
equal(professionWindow.shown, false, "no profession window is open yet")
local profLines = command("prof cooking")
equal(#openedSkills, 1, "the Cooking window is opened")
equal(openedSkills[1], 185, "Cooking is skill line 185")
equal(selectedProfession, "cooking", "the tab is selected")
equal(profLines[1], "Dev Smoke: profession tab cooking", "the selection is reported")
command("prof alchemy")
equal(#openedSkills, 1, "an open profession window is kept")
equal(selectedProfession, "alchemy", "the next tab is selected")

-- /devsmoke close hides the Thanks window, Professions, the world map and Settings through the client's own routes.
local closeLines = command("close")
equal(#hiddenPanels, 2, "the professions window and the world map go through the panel manager")
equal(hiddenPanels[1], professionWindow, "the professions window is hidden first")
equal(hiddenPanels[2], worldMapWindow, "the world map is hidden next")
equal(professionWindow.shown, false, "the professions window is hidden")
equal(worldMapWindow.shown, false, "the world map is hidden")
equal(settingsWindow.shown, false, "the settings panel is closed")
equal(creditsWindow.shown, false, "the Thanks window is hidden")
equal(closeLines[1], "Dev Smoke: closed 4 windows", "every open window is counted")
local again = command("close")
equal(again[1], "Dev Smoke: closed 0 windows", "a second close finds nothing open")

-- An unknown subcommand prints the usage instead of starting a run.
local runsBeforeUnknown = #DevSmokeDB.runs
local unknown = command("wat")
equal(#DevSmokeDB.runs, runsBeforeUnknown, "an unknown subcommand starts no run")
equal(unknown[1], "Dev Smoke: unknown command wat", "an unknown subcommand is reported")
equal(
	unknown[2],
	"Dev Smoke: /devsmoke, tab [off], versions, errors, eval, thanks <addon> [player], prof <tab>, close",
	"the usage lists every command"
)

-- /devsmoke eval runs the chunk the generated !!DevSmokeInbox addon defines: what it prints and every value it
-- returns reach the Agent tab and DevSmokeDB.eval, and an error is caught there instead of reaching BugGrabber. The
-- chunk's DevSmokeEvalRun token is copied into DevSmokeDB.eval.run, so a reader with only the SavedVariables file can
-- tell this snippet's own result from an earlier session's (#580).
local specPrint = _G.print
DevSmokeEvalRun = "run-1"
DevSmokeEval = function()
	print("a printed line")
	return "a returned value", 42
end
local evalLines = command("eval")
equal(evalLines[1], "Dev Smoke: eval ok, 3 lines", "a passing eval reports its line count")
equal(evalLines[2], "a printed line", "a printed line reaches the tab")
equal(evalLines[3], "a returned value", "the first returned value follows it")
equal(evalLines[4], "42", "every returned value is shown")
equal(DevSmokeDB.eval.ok, true, "a passing snippet is recorded")
equal(DevSmokeDB.eval.out[1], "a printed line", "the printed line is saved")
equal(DevSmokeDB.eval.out[2], "a returned value", "the returned value is saved")
equal(DevSmokeDB.eval.out[3], "42", "the last returned value is saved")
equal(DevSmokeDB.eval.err, nil, "a passing snippet records no error")
equal(DevSmokeDB.eval.run, "run-1", "the eval carries the token its chunk was written with")
check(type(DevSmokeDB.eval.ran) == "number", "the run time is recorded")
equal(_G.print, specPrint, "print is restored after a passing eval")

local beforeEvalBugs = #bugErrors
DevSmokeEval = function()
	print("before the error")
	error("boom from eval")
end
evalLines = command("eval")
equal(evalLines[1], "Dev Smoke: eval failed, 3 lines", "a failing eval reports its lines")
equal(evalLines[2], "before the error", "output before the error is kept")
check(evalLines[3]:find("boom from eval", 1, true) ~= nil, "the error message reaches the tab")
equal(evalLines[4], "stack trace", "the stack follows the message")
equal(DevSmokeDB.eval.ok, false, "a failing snippet is recorded")
check(DevSmokeDB.eval.err:find("boom from eval", 1, true) ~= nil, "the error is saved")
check(DevSmokeDB.eval.err:find("stack trace", 1, true) ~= nil, "the stack is saved")
equal(#bugErrors, beforeEvalBugs, "an eval error never reaches BugGrabber")
equal(_G.print, specPrint, "print is restored after a failing eval")

DevSmokeEval = function()
	print(string.rep("x", 600))
end
evalLines = command("eval")
equal(#evalLines, 4, "a long line is split into three Agent lines")
equal(#evalLines[2], 254, "the first chunk reaches the cut")
equal(#evalLines[3], 254, "the second chunk reaches the cut")
equal(#evalLines[4], 92, "the rest is its own line")
equal(#DevSmokeDB.eval.out, 3, "the saved output is split the same way")
equal(DevSmokeDB.eval.out[3]:sub(-1), "x", "the split keeps every character")

local ranBefore = DevSmokeDB.eval.ran
DevSmokeEvalRun = "run-2"
DevSmokeEval = function()
	return "again"
end
evalLines = command("eval")
equal(evalLines[2], "again", "a second eval reruns the loaded chunk")
check(DevSmokeDB.eval.ran > ranBefore, "a rerun records a new time")
equal(DevSmokeDB.eval.run, "run-2", "a rerun records the token of the chunk it ran")

-- The token is read before the chunk runs, so a snippet that reuses the name cannot move its result onto another run.
DevSmokeEvalRun = "run-3"
DevSmokeEval = function()
	DevSmokeEvalRun = "the snippet's own value"
	return "sneaky"
end
evalLines = command("eval")
equal(DevSmokeDB.eval.run, "run-3", "a snippet that writes the token's name cannot change its own attribution")
equal(evalLines[2], "sneaky", "the snippet still runs and returns its value")

DevSmokeEval = nil
DevSmokeEvalRun = nil
evalLines = command("eval")
equal(
	evalLines[1],
	"Dev Smoke: no eval loaded; run tools/devsmoke/eval.py FILE, then /reload",
	"an empty inbox says how to fill it"
)

-- At login the addon asks for the load-on-demand inbox and runs the chunk it defines, without a command.
addAddon("!!DevSmokeInbox")
local inboxLoads = {}
local addonAPI = C_AddOns
rawset(addonAPI, "LoadAddOn", function(name)
	inboxLoads[#inboxLoads + 1] = name
	DevSmokeEvalRun = "run-4"
	DevSmokeEval = function()
		return "from the inbox"
	end
	return true
end)
DevSmokeEval = nil
local beforeLoginLines = #agentMessages()
fire("PLAYER_LOGIN")
equal(inboxLoads[1], "!!DevSmokeInbox", "login asks for the generated inbox")
local loginLines = {}
for index = beforeLoginLines + 1, #agentMessages() do
	loginLines[#loginLines + 1] = agentMessages()[index]
end
equal(loginLines[1], "Dev Smoke: eval ok, 1 lines", "the login eval reports itself")
equal(loginLines[2], "from the inbox", "the login runs the chunk the inbox defined")
equal(DevSmokeDB.eval.run, "run-4", "the login eval carries the token the inbox's chunk was written with")

-- The client reads the inbox once a session: a later /devsmoke eval reruns the loaded chunk and asks for no reload,
-- so a snippet written after it needs /reload.
local reloadsBefore = #inboxLoads
local laterEval = command("eval")
equal(laterEval[2], "from the inbox", "a later eval reruns the chunk the inbox loaded")
equal(#inboxLoads, reloadsBefore, "a later eval does not load the inbox again")

for _, message in ipairs(agentMessages()) do
	check(#message < 255, "every Agent line stays under 255 characters")
end

-- The database keeps the newest twenty runs and nothing reaches chat.
for _ = 1, 25 do
	SlashCmdList.DEVSMOKE("", nil)
	drain()
end
equal(#DevSmokeDB.runs, 20, "only the last twenty runs are kept")
equal(#chat, 0, "nothing is printed to chat")

_G.print = realPrint
print(("smoke_spec: %d checks passed"):format(checks))
