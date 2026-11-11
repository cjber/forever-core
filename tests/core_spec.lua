-- ForeverCore's own install of the shared contract: the TOC ships every shared file, the settings the host reads
-- survive saved variables arriving late, and Expose.lua publishes the addon table the Forever addons call.
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end

-- The TOC is the one list of what ships, so a file it names must exist and every shared file must be named. The
-- shared reader expands its XML entry the way the client does, UI/TrackerSection.xml included.
local Toc = dofile(".agents/skills/wow-forever-addon/tooling/forever_sim/toc.lua")
local function tocFiles()
	local files = {}
	for _, entry in ipairs(Toc.files(".", "ForeverCore.toc")) do
		files[#files + 1] = entry.path
	end
	return files
end

local shipped = {}
local files = tocFiles()
for _, path in ipairs(files) do
	shipped[path] = true
	local handle = io.open(path, "rb")
	check(handle ~= nil, "TOC names a file that is not there: " .. path)
	if handle then
		handle:close()
	end
end
for _, path in ipairs({
	"Core.lua",
	"Core/SafeCall.lua",
	"Core/Log.lua",
	"Core/OpenMap.lua",
	"Core/OpenSettings.lua",
	"Core/Text.lua",
	"Core/PeerStats.lua",
	"Core/MinimapButton.lua",
	"Core/LeaderboardsData.lua",
	"Core/APIKit.lua",
	"Core/QuestOrder.lua",
	"UI/Art.lua",
	"UI/Report.lua",
	"UI/ForeverFamily.lua",
	"UI/SettingsPage.lua",
	"UI/TrackerHost.lua",
	"UI/TrackerSection.lua",
	"UI/TrackerSection.xml",
	"UI/TrackerLock.lua",
	"UI/TrackerOrder.lua",
	"UI/TrackerQuestie.lua",
	"UI/TrackerEqot.lua",
	"UI/TrackerQuests.lua",
	"UI/MapCanvas.lua",
	"UI/Leaderboards.lua",
	"UI/QuestLogTabs.lua",
	"UI/ProfessionTabs.lua",
	"Locales/enUS.lua",
	"Expose.lua",
}) do
	check(shipped[path] == true, "TOC does not load " .. path)
end
check(files[#files] == "Expose.lua", "Expose.lua loads last, after every module it publishes")
-- The lock, order and questie modules answer the host, so they load before it.
local hostAt, sectionAt, lockAt, menuAt
for index, path in ipairs(files) do
	hostAt = path == "UI/TrackerHost.lua" and index or hostAt
	sectionAt = path == "UI/TrackerSection.lua" and index or sectionAt
	lockAt = path == "UI/TrackerLock.lua" and index or lockAt
	menuAt = path == "UI/ContextMenu.lua" and index or menuAt
end
check(hostAt ~= nil and lockAt ~= nil and lockAt < hostAt, "the grip loads before the host it drags")
check(menuAt ~= nil and menuAt < hostAt, "the shared context menu loads before the host that opens it")
check(sectionAt ~= nil and hostAt < sectionAt, "the section API loads after the host it attaches to")
-- Art is what the report window draws its portrait with.
local artAt, reportAt
for index, path in ipairs(files) do
	artAt = path == "UI/Art.lua" and index or artAt
	reportAt = path == "UI/Report.lua" and index or reportAt
end
check(artAt ~= nil and reportAt ~= nil and artAt < reportAt, "the art helper loads before the report")
for _, locale in ipairs({
	"enUS",
	"deDE",
	"esES",
	"esMX",
	"frFR",
	"koKR",
	"ptBR",
	"ruRU",
	"zhCN",
	"zhTW",
}) do
	check(shipped["Locales/" .. locale .. ".lua"] == true, "core ships its own " .. locale .. " phrases")
end

-- The type declarations describe only the globals that still exist, and publish ForeverCore with its API type.
local function readFile(path)
	local handle = assert(io.open(path, "rb"))
	local text = handle:read("*a")
	handle:close()
	return text
end
local clientTypes = readFile("types/Client.lua")
for _, name in ipairs({
	"ForeverMapMarkers",
	"ForeverLeaderboards",
	"ForeverMinimapButtons",
	"ForeverQuestLogTabs",
	"ForeverPeerStats",
	"ForeverErrorJournal",
	"ForeverDebugLog",
}) do
	check(
		not clientTypes:find("\n" .. name .. " = nil", 1, true),
		"types/Client.lua still declares the deleted global " .. name
	)
end
check(
	clientTypes:find("\nForeverTrackerHost = nil", 1, true) ~= nil,
	"types/Client.lua declares the companion tracker registry"
)
local foreverTypes = readFile("types/Forever.lua")
check(
	foreverTypes:find("---@type ForeverCoreAPI", 1, true) ~= nil
		and foreverTypes:find("\nForeverCore = nil", 1, true) ~= nil,
	"types/Forever.lua declares ForeverCore with its API type"
)

-- Core.lua, loaded the way the client loads it, with no saved variables yet.
local ns = {}
local coreFrames = {}
local env = { type = type, math = math, pairs = pairs, ipairs = ipairs }
setmetatable(env, { __index = _G })
function env.CreateFrame()
	local frame = { events = {}, scripts = {} }
	function frame:RegisterEvent(event)
		self.events[event] = true
	end
	function frame:SetScript(name, callback)
		self.scripts[name] = callback
	end
	coreFrames[#coreFrames + 1] = frame
	return frame
end
local core = assert(loadfile("Core.lua"))
setfenv(core, env)
core("ForeverCore", ns)
check(ns.isCore == true, "Core.lua marks its namespace")
check(type(ns.TrackerHostSettings) == "function", "Core.lua publishes the host's settings")
check(ns.Defaults == nil, "the old defaults field is gone")
local settings = ns.TrackerHostSettings()
check(
	settings.attached == true and settings.locked == false and settings.scale == 1 and settings.backdropOpacity == 0,
	"a fresh install docks the column with no backdrop"
)
check(ns.TrackerHostSettings() ~= settings, "a table with no saved variables is never kept")

-- With saved variables, one table is kept and repaired.
env.ForeverCoreDB = { trackerHost = { attached = false, scale = 0 / 0, locked = "yes" } }
local saved = ns.TrackerHostSettings()
check(saved.attached == false, "a saved detach survives")
check(saved.scale == 1, "a broken scale falls back to 1")
check(saved.locked == false, "a broken Lock switch falls back to off")
check(saved.backdropOpacity == 0, "a broken backdrop opacity falls back to off")
check(env.ForeverCoreDB.trackerHost == saved, "the saved table is the one kept")

-- A first install has no ForeverCoreDB at ForeverCore's ADDON_LOADED: Core.lua's one handler makes the table, then runs
-- core's attach and the tracker migration through the hooks those files register, in that order.
env.ForeverCoreDB = nil
local order = {}
ns.AttachCoreDb = function()
	order[#order + 1] = "attach"
end
ns.MigrateTrackerSettings = function()
	order[#order + 1] = "migrate"
end
check(#coreFrames == 1 and coreFrames[1].events.ADDON_LOADED == true, "Core.lua registers the one ADDON_LOADED handler")
coreFrames[1].scripts.OnEvent(coreFrames[1], "ADDON_LOADED", "SomeOtherAddon")
check(env.ForeverCoreDB == nil, "another addon's ADDON_LOADED creates nothing")
coreFrames[1].scripts.OnEvent(coreFrames[1], "ADDON_LOADED", "ForeverCore")
check(type(env.ForeverCoreDB) == "table", "the first install gets a saved table")
check(type(env.ForeverCoreDB.trackerHost) == "table", "with the host's settings")
check(env.ForeverCoreDB.trackerHost.attached == true, "built from the one defaults constructor")
check(order[1] == "attach" and order[2] == "migrate", "core attaches before the tracker migration")

-- Expose.lua publishes the one public table and the per-addon factory.
ns.TrackerHost = { name = "host" }
ns.TrackerSection, ns.TrackerLine = { name = "section" }, { name = "line" }
ns.TrackerLock, ns.TrackerOrder = { name = "lock" }, { name = "order" }
ns.TrackerQuestie, ns.TrackerEqot, ns.TrackerQuests = { name = "questie" }, { name = "eqot" }, { name = "quests" }
ns.QuestLogTabs, ns.ProfessionTabs, ns.PeerStats = { name = "tabs" }, { name = "professions" }, { name = "peers" }
ns.Leaderboards, ns.LeaderboardsData = { name = "boards" }, { name = "data" }
ns.MinimapButton, ns.SettingsPage = { name = "minimap" }, { name = "settings" }
ns.Text, ns.QuestOrder = { name = "text" }, function()
	return {}
end
ns.OpenMap, ns.OpenSettingsPanel = function()
	return true
end, function()
	return true
end
ns.Family = { name = "family" }
ns.CreditsPage = {
	Register = function()
		return true
	end,
}
ns.ContextMenu = function()
	return nil
end
ns.CutText = function(text)
	return text
end
local safeCalls = {}
function ns.SafeCallFor(name)
	safeCalls[name] = safeCalls[name]
		or {
			SafeCall = function()
				return true
			end,
			RecordError = function() end,
			CaughtErrors = function()
				return {}
			end,
			Attach = function() end,
		}
	return safeCalls[name]
end
local logged = {}
function ns.LogFor(name)
	logged[name] = logged[name]
		or {
			Log = function() end,
			LogLines = function()
				return {}
			end,
			Attach = function() end,
		}
	return logged[name]
end
function ns.ReportFor(name, spec)
	return { name = name, spec = spec }
end
function ns.MapCanvasFor(name)
	return { name = name }
end
ns.DebugEnabled = function()
	return false
end
ns.DebugCommand = function()
	return true
end

env.SlashCmdList = {}
local framesBeforeExpose = #coreFrames
local expose = assert(loadfile("Expose.lua"))
setfenv(expose, env)
expose("ForeverCore", ns)
check(#coreFrames == framesBeforeExpose, "Expose registers no second ADDON_LOADED handler")
local ForeverCore = env.ForeverCore
check(type(ForeverCore) == "table", "Expose.lua publishes the core")
check(ForeverCore.name == "ForeverCore", "the core knows its name")
check(ForeverCore.API == 1, "the interface starts at version 1")
for _, field in ipairs({
	"TrackerHost",
	"TrackerSection",
	"TrackerLine",
	"TrackerLock",
	"TrackerOrder",
	"TrackerQuestie",
	"TrackerEqot",
	"TrackerQuests",
	"QuestLogTabs",
	"ProfessionTabs",
	"PeerStats",
	"Leaderboards",
	"LeaderboardsData",
	"MinimapButton",
	"SettingsPage",
	"Text",
	"QuestOrder",
	"OpenMap",
	"OpenSettingsPanel",
	"Family",
	"Credits",
	"ContextMenu",
}) do
	check(ForeverCore[field] ~= nil, "the core publishes " .. field)
end
check(
	ForeverCore.TrackerHost == ns.TrackerHost
		and ForeverCore.TrackerOrder == ns.TrackerOrder
		and ForeverCore.TrackerSection == ns.TrackerSection
		and ForeverCore.TrackerLine == ns.TrackerLine,
	"and the modules"
)
check(ForeverCore.Attach == nil, "the old Attach helper is gone")
check(ForeverCore.Defaults == nil, "the old Defaults field is gone")

-- Register returns one context per addon, with the services bound to it.
local spec = { title = "Example report", lines = function() end, db = { errors = {} } }
local first = ForeverCore.Register("ExampleAddon", spec)
local second = ForeverCore.Register("ExampleAddon")
check(first == second, "Register returns the same context for the same addon")
check(first.name == "ExampleAddon", "the context knows its addon")
check(first.Report ~= nil and first.MapCanvas ~= nil, "the report and canvas are the addon's")
check(type(first.SafeCall) == "function" and type(first.Log) == "function", "and the bound services")
check(type(first.Attach) == "function", "an addon can attach its saved table later")
check(ForeverCore.Register("OtherAddon").Report ~= first.Report, "a second addon gets its own report")

env.SLASH_FOREVERCORE1 = nil
check(env.SlashCmdList.FOREVERCORE ~= nil, "the slash command is registered")
local printed
env.print = function(text)
	printed = text
end
ns.TrackerHost.Debug = function()
	return "debug"
end
env.SlashCmdList.FOREVERCORE()
check(printed == "debug", "the slash command prints the host's diagnostic")

print(("core_spec: %d checks passed"):format(checks))
