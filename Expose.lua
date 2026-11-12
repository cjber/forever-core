-- The core's public face, loaded after the shared files so it can publish what they built. Every Forever addon reads
-- ForeverCore for the modules it shares and calls ForeverCore.Register for the services that belong to it alone, and
-- /fcore prints the tracker's diagnostic.

local _, ns = ...

local core = {}
core.name = "ForeverCore"
-- Raised when a change breaks the interface below, so an addon can refuse to run against an older core.
core.API = 1

core.TrackerHost = ns.TrackerHost
core.TrackerSection = ns.TrackerSection
core.TrackerLine = ns.TrackerLine
core.TrackerLock = ns.TrackerLock
core.TrackerOrder = ns.TrackerOrder
core.TrackerQuestie = ns.TrackerQuestie
core.TrackerEqot = ns.TrackerEqot
core.TrackerQuests = ns.TrackerQuests
core.QuestLogTabs = ns.QuestLogTabs
core.ProfessionTabs = ns.ProfessionTabs
core.PeerStats = ns.PeerStats
core.Leaderboards = ns.Leaderboards
core.LeaderboardsData = ns.LeaderboardsData
core.MinimapButton = ns.MinimapButton
core.SettingsPage = ns.SettingsPage
core.SettingsSections = ns.SettingsSections
core.Text = ns.Text
core.QuestOrder = ns.QuestOrder
core.APIKit = ns.APIKit
core.OpenMap = ns.OpenMap
core.OpenSettingsPanel = ns.OpenSettingsPanel
core.Family = ns.Family
core.Credits = ns.CreditsPage
core.ContextMenu = ns.ContextMenu

-- Core's own credits are its generated Data/Credits.lua, loaded before this file onto ns.Credits; in an addon's own
-- namespace that same table is what it hands to ForeverCore.Credits.Register.
-- An addon's spec can load core without UI/Credits.lua, so the page is optional there.
if ns.CreditsPage then
	ns.CreditsPage.Register("Forever Core", ns.Credits)
end

-- One context per addon name, so Register twice returns the same tables and the same window.
---@type table<string, ForeverCoreAddon>
local contexts = {}

-- The saved table's journal lives under `errors` and its log ring under `log`.
---@param context ForeverCoreAddon
---@param db table
local function AttachDb(context, db)
	if type(db) ~= "table" then
		return
	end
	local journal = db.errors
	if type(journal) ~= "table" then
		journal = {}
		db.errors = journal
	end
	ns.SafeCallFor(context.name):Attach(journal)
	ns.LogFor(context.name):Attach(db)
end

-- The per-addon services: the error journal and log bound to `addonName`, its report window and its map markers.
---@param addonName string
---@param spec? ForeverCoreSpec
---@return ForeverCoreAddon
function core.Register(addonName, spec)
	addonName = tostring(addonName or "?")
	spec = spec or {}
	local context = contexts[addonName]
	if context then
		if spec.db ~= nil then
			AttachDb(context, spec.db)
		end
		return context
	end
	local safe = ns.SafeCallFor(addonName)
	local log = ns.LogFor(addonName)
	context = {
		name = addonName,
		SafeCall = function(...)
			return safe:SafeCall(...)
		end,
		RecordError = function(...)
			safe:RecordError(...)
		end,
		CaughtErrors = function()
			return safe:CaughtErrors()
		end,
		CutText = ns.CutText,
		Log = function(...)
			log:Log(...)
		end,
		LogLines = function(...)
			return log:LogLines(...)
		end,
		DebugEnabled = ns.DebugEnabled,
		DebugCommand = ns.DebugCommand,
		Report = ns.ReportFor(addonName, {
			title = spec.title,
			lines = spec.lines,
			safe = safe,
			log = log,
		}),
		MapCanvas = ns.MapCanvasFor(addonName),
		Attach = function(db)
			AttachDb(context, db)
		end,
	}
	contexts[addonName] = context
	if spec.db ~= nil then
		AttachDb(context, spec.db)
	end
	return context
end

-- Core's own errors and lines are recorded under ForeverCore. Core.lua's one ADDON_LOADED handler calls this once the
-- saved table exists, so a first install attaches exactly like a later one.
local self = core.Register("ForeverCore")
ns.AttachCoreDb = function()
	if type(ForeverCoreDB) ~= "table" then
		return
	end
	self.Attach(ForeverCoreDB)
end

ForeverCore = core

if SlashCmdList ~= nil then
	SLASH_FOREVERCORE1 = "/fcore"
	SlashCmdList.FOREVERCORE = function(message)
		local command = tostring(message or ""):match("^%s*(%S*)")
		if command:lower() == "quests" then
			if ns.TrackerQuests ~= nil then
				ns.TrackerQuests.Toggle()
			end
			return
		end
		local host = ns.TrackerHost
		if host ~= nil and host.Debug ~= nil then
			print(host.Debug())
		end
	end
end
