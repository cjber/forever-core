-- The core's public face, loaded after the shared files so it can publish what they built. Every Forever addon reads
-- ForeverCore for the modules it shares and calls ForeverCore.Register for the services that belong to it alone, and
-- /fcore prints the tracker's diagnostic while /forever debug drives the shared log.

local _, ns = ...

local core = {}
core.name = "ForeverCore"
-- Raised when a change breaks the interface below, so an addon can refuse to run against an older core. Version 2
-- retired Forever Leaderboards and peer stats.
core.API = 2
-- The core table's own minor, raised with each member added here outside a module. `Registered` arrived in minor 1;
-- a caller that needs it checks this first, the way a module member checks that module's minor.
core.minor = 2

core.TrackerHost = ns.TrackerHost
core.TrackerSection = ns.TrackerSection
core.TrackerLine = ns.TrackerLine
core.TrackerLock = ns.TrackerLock
core.TrackerOrder = ns.TrackerOrder
core.QuestLogTabs = ns.QuestLogTabs
core.ProfessionTabs = ns.ProfessionTabs
-- No Forever addon draws a minimap button any more. An addon release from before that still creates one while it
-- loads, so the table stays for one release as answers that draw nothing. Remove it once no supported release calls it.
---@type ForeverMinimapButtonAPI
core.MinimapButton = {
	Create = function() end,
	Destroy = function() end,
	Refresh = function() end,
	SetShown = function() end,
}
core.SettingsPage = ns.SettingsPage
core.SettingsSections = ns.SettingsSections
core.Text = ns.Text
core.APIKit = ns.APIKit
core.Open = ns.Open
core.Journey = ns.Journey
core.OpenMap = ns.OpenMap
core.OpenSettingsPanel = ns.OpenSettingsPanel
-- The Forever addons page is gone. An addon release from before that still calls these members while it loads, so
-- they stay for one release as answers that draw nothing: no hint shows, no link window opens, and Register hands
-- back the addon's own category, so an older "Forever addons" button opens the addon's own page. State still answers
-- from the client, because an addon decides what it offers from whether a sibling is running. Remove the table once
-- no supported release calls it.
---@type ForeverFamilyAPI
core.Family = {
	---@param folder string
	---@return "on"|"off"|"missing"
	State = function(folder)
		local addons = rawget(_G, "C_AddOns")
		if type(addons) ~= "table" or type(addons.IsAddOnLoaded) ~= "function" then
			return "off"
		end
		local ok, loaded = pcall(addons.IsAddOnLoaded, folder)
		if ok and loaded then
			return "on"
		end
		if type(addons.DoesAddOnExist) == "function" then
			local known, exists = pcall(addons.DoesAddOnExist, folder)
			return known and exists == false and "missing" or "off"
		end
		if type(addons.GetAddOnInfo) == "function" then
			local known, _, _, _, _, reason = pcall(addons.GetAddOnInfo, folder)
			return known and reason == "MISSING" and "missing" or "off"
		end
		return "off"
	end,
	Hint = function()
		return false
	end,
	Once = function()
		return false
	end,
	ShowLink = function()
		return false
	end,
	ShowSupport = function()
		return false
	end,
	Register = function(category)
		return category
	end,
}
core.Credits = ns.CreditsPage
core.ContextMenu = ns.ContextMenu
core.Art = ns.Art

-- Core's own credits are its generated Data/Credits.lua, loaded before this file onto ns.Credits; in an addon's own
-- namespace that same table is what it hands to ForeverCore.Credits.Register.
-- An addon's spec can load core without UI/Credits.lua, so the page is optional there.
if ns.CreditsPage then
	ns.CreditsPage.Register("ForeverCore", ns.Credits)
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
	if spec.open ~= nil then
		ns.RegisterOpener(addonName, spec.open, spec.openSecure)
	end
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

-- Whether an addon has reached Register, and so got far enough to start: every Forever addon's Core/Require.lua calls
-- Register after feature-checking the core members it needs. A consumer whose Require refused is a UIErrorsFrame line
-- and a stopped file list, never a Lua error, so a release gate asks this instead of reading the error frame.
---@param addonName string
---@return boolean
function core.Registered(addonName)
	if type(addonName) ~= "string" then
		return false
	end
	return contexts[addonName] ~= nil
end

-- Core's own errors and lines are recorded under ForeverCore. Core.lua's Start (converted copies) or its one
-- ADDON_LOADED handler (transitional unwrapped standalone) calls this once the store exists, so a first install
-- attaches exactly like a later one.
local self = core.Register("ForeverCore")
ns.AttachCoreDb = function()
	local store = ns.Store()
	if type(store) ~= "table" then
		return
	end
	self.Attach(store)
end

-- A converted copy hands its facade to the loader on the namespace only; Boot publishes the global once. The
-- unwrapped standalone path keeps its old global publication until packaging conversion.
if ns.copy ~= nil then
	ns.ForeverCore = core
	core.loaderSchema = 1
	core.build = ns.copy.build
else
	ForeverCore = core
end

local function AddOnMetadata(name, key)
	local addons = rawget(_G, "C_AddOns")
	if type(addons) ~= "table" or type(addons.GetAddOnMetadata) ~= "function" then
		return nil
	end
	local ok, value = pcall(addons.GetAddOnMetadata, name, key)
	return ok and value or nil
end

local function AddOnLoaded(name)
	local addons = rawget(_G, "C_AddOns")
	if type(addons) ~= "table" or type(addons.IsAddOnLoaded) ~= "function" then
		return nil
	end
	local ok, loaded = pcall(addons.IsAddOnLoaded, name)
	return ok and loaded == true or false
end

local function AddOnEnableState(name)
	local addons = rawget(_G, "C_AddOns")
	if type(addons) ~= "table" or type(addons.GetAddOnEnableState) ~= "function" then
		return nil
	end
	local ok, state = pcall(addons.GetAddOnEnableState, name)
	return ok and state or nil
end

-- Every installed Forever addon, recognised by the pin every consumer records in its TOC. The pin is also the version
-- a sibling bundled, so it belongs in the report beside the addon's own version.
local function InstalledConsumers()
	local addons = rawget(_G, "C_AddOns")
	if type(addons) ~= "table" or type(addons.GetNumAddOns) ~= "function" then
		return {}
	end
	local total = 0
	pcall(function()
		total = addons.GetNumAddOns()
	end)
	local found = {}
	for index = 1, tonumber(total) or 0 do
		local name
		pcall(function()
			name = addons.GetAddOnInfo(index)
		end)
		if type(name) ~= "string" or name == "" then
			break
		end
		local pin = AddOnMetadata(name, "X-Forever-Core")
		if pin ~= nil or name == "ForeverCore" then
			found[#found + 1] = name
		end
	end
	table.sort(found)
	return found
end

local function FirstCaught(name)
	local context = contexts[name]
	if context == nil then
		return nil
	end
	local caught = context.CaughtErrors()
	return caught[1]
end

local function CoreCopies()
	local loader = rawget(_G, "ForeverCoreLoader")
	if type(loader) ~= "table" or type(loader.Candidates) ~= "function" then
		return {}
	end
	return loader.Candidates()
end

-- The installed-but-unregistered answer (core#509). It lists what the client knows about every Forever addon, and for
-- a consumer that never reached Register it names the first captured error when one exists or the exact next
-- diagnostic (the client error frame) when ForeverCore never saw one.
---@param focus? string
---@return string[]
local function StartupReport(focus)
	local L = ns.L
	local lines = { L["ForeverCore startup report"] }
	local loader = rawget(_G, "ForeverCoreLoader")
	local selected = type(loader) == "table" and type(loader.Selected) == "function" and loader.Selected() or nil
	local version = AddOnMetadata("ForeverCore", "Version") or "?"
	if selected and type(selected.build) == "number" then
		local build = selected.build
		version = ("%d.%d.%d"):format(math.floor(build / 1000000), math.floor(build / 1000) % 1000, build % 1000)
	end
	lines[#lines + 1] = L["Core: %s; API %s"]:format(tostring(version), tostring(core.API))
	if selected ~= nil then
		lines[#lines + 1] = L["Runtime: %s copy %s"]:format(tostring(selected.mode), tostring(selected.folder))
	elseif type(loader) == "table" and type(loader.Error) == "function" and loader.Error() then
		lines[#lines + 1] = L["Runtime error: %s"]:format(loader.Error())
	else
		lines[#lines + 1] = L["Standalone runtime"]
	end
	local copies = CoreCopies()
	if #copies > 0 then
		lines[#lines + 1] = L["Core copies:"]
		for _, copy in ipairs(copies) do
			local status = copy.rejected and L["Rejected"] or (copy.sealed and L["Sealed"] or L["Unsealed"])
			lines[#lines + 1] = L["%s: build %s, %s"]:format(tostring(copy.folder), tostring(copy.build), status)
		end
	end

	local installed = InstalledConsumers()
	local wanted = tostring(focus or ""):match("^%s*(.-)%s*$")
	if wanted ~= "" then
		local kept = {}
		for _, name in ipairs(installed) do
			if name:lower() == wanted:lower() then
				kept[#kept + 1] = name
			end
		end
		installed = kept
	end
	if #installed == 0 then
		lines[#lines + 1] = wanted ~= "" and L['No installed Forever addon named "%s".']:format(wanted)
			or L["No installed Forever addons found."]
		lines[#lines + 1] =
			L["Enable ForeverCore or a Forever addon in AddOns if /fcore is unavailable, then /reload and read Lua errors."]
		return lines
	end

	lines[#lines + 1] = L["Installed Forever addons:"]
	local addons = rawget(_G, "C_AddOns")
	for _, name in ipairs(installed) do
		local registered = contexts[name] ~= nil
		local loaded = AddOnLoaded(name)
		local state = AddOnEnableState(name)
		local addonVersion = AddOnMetadata(name, "Version") or "?"
		local pin = AddOnMetadata(name, "X-Forever-Core") or "?"
		local dependencies = AddOnMetadata(name, "Dependencies") or "?"
		local optional = AddOnMetadata(name, "OptionalDeps") or "?"
		if type(addons) == "table" and type(addons.GetAddOnDependencies) == "function" then
			local values = { pcall(addons.GetAddOnDependencies, name) }
			if values[1] then
				table.remove(values, 1)
				dependencies = #values > 0 and table.concat(values, ", ") or "-"
			end
		end
		local label = registered and L["Registered"] or (loaded and L["Loaded but not registered"] or L["Not loaded"])
		lines[#lines + 1] = ("%s %s: %s"):format(name, addonVersion, label)
		lines[#lines + 1] = L["Load: %s; enabled: %s; core pin: %s"]:format(
			tostring(loaded),
			state ~= nil and tostring(state) or "?",
			pin
		)
		lines[#lines + 1] = L["Requires: %s; optional: %s"]:format(dependencies, optional)
		if type(addons) == "table" and type(addons.GetAddOnInfo) == "function" then
			local ok, _, _, _, loadable, reason = pcall(addons.GetAddOnInfo, name)
			if ok then
				lines[#lines + 1] = L["Loadable: %s; reason: %s"]:format(tostring(loadable), tostring(reason or "-"))
			end
		end
		local first = FirstCaught(name)
		if first ~= nil then
			lines[#lines + 1] = L["First error: %s"]:format(tostring(first.message or first.kind or "?"))
		elseif not registered then
			lines[#lines + 1] =
				L["No error captured. Use /console scriptErrors 1, then /reload and read the first error naming %s."]:format(
					name
				)
		end
	end

	if type(loader) == "table" then
		local callback = type(loader.CallbackError) == "function" and loader.CallbackError() or nil
		local login = type(loader.LoginError) == "function" and loader.LoginError() or nil
		if callback then
			lines[#lines + 1] = L["Callback error: %s"]:format(callback)
		end
		if login then
			lines[#lines + 1] = L["Login error: %s"]:format(login)
		end
		local rejections = type(loader.Rejections) == "function" and loader.Rejections() or {}
		for _, rejection in ipairs(rejections) do
			lines[#lines + 1] = L["Copy %s: %s"]:format(tostring(rejection.folder), tostring(rejection.reason))
		end
	end
	return lines
end

ns.StartupReport = StartupReport

if SlashCmdList ~= nil then
	SLASH_FOREVERCORE1 = "/fcore"
	-- A consumer that already owns /forever keeps it.
	local foreverTaken = false
	for index = 1, 9 do
		if rawget(_G, "SLASH_FOREVER" .. index) ~= nil then
			foreverTaken = true
			break
		end
	end
	SLASH_FOREVERCORE2 = not foreverTaken and "/forever" or nil
	SlashCmdList.FOREVERCORE = function(message)
		local text = tostring(message or "")
		local command, argument = text:match("^%s*(%S*)%s*(.*)$")
		command = command or ""
		if command:lower() == "report" then
			for _, line in ipairs(StartupReport(argument)) do
				print(line)
			end
			return
		end
		if command:lower() == "debug" then
			if type(ns.DebugCommand) == "function" then
				ns.DebugCommand(text:match("^%s*%S+%s*(.*)$"))
			end
			return
		end
		local host = ns.TrackerHost
		if host ~= nil and host.Debug ~= nil then
			print(host.Debug())
		end
	end
end
