-- ForeverCoreLoader, schema 1: the one registry every embedded ForeverCore copy in a client shares. A consumer's
-- Begin.lua calls Begin(folder, build, digest, chunks), its wrapped files call copy:Define(function(...) ... end), and
-- its End.lua calls copy:Seal(). Registration and definition run no runtime code. At PLAYER_LOGIN the loader elects the
-- highest sealed build, including standalone, and runs only that copy's chunks into a fresh namespace, and publishes
-- its facade once. A host first loaded after login activates on the next frame after its files load,
-- PLAYER_ENTERING_WORLD activates a session whose PLAYER_LOGIN the loader missed once SavedVariables are in, and an
-- activation reached in combat lockdown waits for PLAYER_REGEN_ENABLED. Trace() records which path ran.
--
-- Schema 1 is immutable: its methods and their meaning never change. A later schema is a new global name
-- (ForeverCoreLoader2), never an upgrade of this table. The first copy to load owns the registry for the session; a
-- newer revision of this file that loads second supervises an older one from outside (Supervise below).
local SCHEMA = 1
-- Revision 1 (ForeverCore 1.15.0) activated only at PLAYER_LOGIN and had no Trace, Seen or WorldEntry.
local REVISION = 2
local TRACE_LIMIT = 200

local function BuildVersion(build)
	return string.format("%d.%d.%d", math.floor(build / 1000000), math.floor(build / 1000) % 1000, build % 1000)
end

local function VersionBuild(version)
	local major, minor, patch = string.match(tostring(version or ""), "^v?(%d+)%.(%d+)%.(%d+)")
	if major ~= nil then
		return tonumber(major) * 1000000 + tonumber(minor) * 1000 + tonumber(patch)
	end
end

-- The installed standalone's own version, for the report. A table published before this loader has no build field.
local function InstalledVersion()
	local addons = rawget(_G, "C_AddOns")
	if type(addons) == "table" and type(addons.GetAddOnMetadata) == "function" then
		local ok, version = pcall(addons.GetAddOnMetadata, "ForeverCore", "Version")
		if ok and type(version) == "string" then
			return version
		end
	end
end

-- The notice in every shipped locale (WFA-34). The loader runs before any runtime's Locales, so it carries its own
-- line. The first %s is the installed standalone's version, the second the newest embedded one.
local OUTDATED = {
	enUS = "ForeverCore %s is older than the ForeverCore %s your addons include. Update ForeverCore, or delete the "
		.. "ForeverCore folder in Interface/AddOns: your addons carry their own copy.",
	deDE = "ForeverCore %s ist älter als das ForeverCore %s, das deine Addons enthalten. Aktualisiere ForeverCore "
		.. "oder lösche den Ordner ForeverCore in Interface/AddOns: deine Addons bringen ihre eigene Kopie mit.", -- mt
	esES = "ForeverCore %s es más antiguo que el ForeverCore %s que incluyen tus addons. Actualiza ForeverCore o "
		.. "borra la carpeta ForeverCore de Interface/AddOns: tus addons llevan su propia copia.", -- mt
	esMX = "ForeverCore %s es más antiguo que el ForeverCore %s que incluyen tus addons. Actualiza ForeverCore o "
		.. "borra la carpeta ForeverCore de Interface/AddOns: tus addons traen su propia copia.", -- mt
	frFR = "ForeverCore %s est plus ancien que le ForeverCore %s inclus dans vos addons. Mettez à jour ForeverCore "
		.. "ou supprimez le dossier ForeverCore dans Interface/AddOns : vos addons ont leur propre copie.", -- mt
	koKR = "ForeverCore %s 버전이 애드온에 포함된 ForeverCore %s보다 오래되었습니다. ForeverCore를 업데이트하거나 "
		.. "Interface/AddOns 폴더 안의 ForeverCore 폴더를 삭제하세요. 애드온에 자체 사본이 들어 있습니다.", -- mt
	ptBR = "O ForeverCore %s é mais antigo que o ForeverCore %s incluído nos seus addons. Atualize o ForeverCore "
		.. "ou apague a pasta ForeverCore em Interface/AddOns: seus addons trazem a própria cópia.", -- mt
	ruRU = "ForeverCore %s старее, чем ForeverCore %s в ваших аддонах. Обновите ForeverCore или удалите папку "
		.. "ForeverCore в Interface/AddOns: в ваших аддонах есть своя копия.", -- mt
	zhCN = "ForeverCore %s 比你的插件所含的 ForeverCore %s 旧。请更新 ForeverCore，"
		.. "或删除 Interface/AddOns 中的 ForeverCore 文件夹：你的插件自带一份副本。", -- mt
	zhTW = "ForeverCore %s 比你的插件所含的 ForeverCore %s 舊。請更新 ForeverCore，"
		.. "或刪除 Interface/AddOns 中的 ForeverCore 資料夾：你的插件自帶一份副本。", -- mt
}

local function OutdatedText(version, newest)
	local getLocale = rawget(_G, "GetLocale")
	local locale = type(getLocale) == "function" and getLocale() or "enUS"
	local text = OUTDATED[locale] or OUTDATED.enUS
	return text:format(tostring(version or ""), BuildVersion(newest))
end

-- The outdated-standalone notice, on screen on the next frame. Never a chat line. NoticeOnce decides whether it shows.
local function ShowNotice(text)
	local function show()
		local dialogs = rawget(_G, "StaticPopupDialogs")
		local popup = rawget(_G, "StaticPopup_Show")
		if type(dialogs) ~= "table" or type(popup) ~= "function" then
			return
		end
		dialogs.FOREVERCORE_OUTDATED = dialogs.FOREVERCORE_OUTDATED
			or { text = "%s", button1 = rawget(_G, "OKAY") or "OK", timeout = 0, whileDead = true, hideOnEscape = true }
		popup("FOREVERCORE_OUTDATED", text)
	end
	local timer = rawget(_G, "C_Timer")
	if type(timer) == "table" and type(timer.After) == "function" then
		timer.After(0, show)
	else
		show()
	end
end

-- A player may keep an older standalone on purpose, so the notice shows once per installed standalone version. The
-- version it was shown for is kept in that standalone's own saved table (ForeverCoreDB, loaded before the world
-- entry), which exists whenever this notice can apply. Loader.Warning and the startup report keep the line.
local NOTICE_KEY = "outdatedNoticeVersion"
local function NoticeOnce(version, text)
	local db = rawget(_G, "ForeverCoreDB")
	local key = tostring(version or "?")
	if type(db) == "table" then
		if db[NOTICE_KEY] == key then
			return false
		end
		db[NOTICE_KEY] = key
	end
	ShowNotice(text)
	return true
end

-- An older revision that loaded first owns the registry, and its private state cannot be replaced. This copy adds
-- what it lacks through its public schema-1 methods only: it records the world events for Seen and WorldEntry, and
-- activates the registry at PLAYER_ENTERING_WORLD when revision 1 missed PLAYER_LOGIN. Activation stays the old
-- loader's own: its Activate is idempotent, and the runtime's Login guards itself (ns.loginDone). When revision 1
-- adopted an older standalone over newer registered copies, the world entry shows the outdated notice once.
-- Revision 1 ignores Begin's chunk count, so it cannot refuse a truncated package; this copy cannot add that.
local function Supervise(old)
	if old.revision ~= nil or rawget(old, "supervised") ~= nil or type(CreateFrame) ~= "function" then
		return
	end
	old.supervised = REVISION
	local seen, entry, trace = {}, nil, {}
	local function Note(kind, detail)
		if #trace < TRACE_LIMIT then
			trace[#trace + 1] = { kind = kind, detail = detail }
		end
	end
	old.Seen = old.Seen or function(event)
		return seen[event] == true
	end
	old.WorldEntry = old.WorldEntry or function()
		if entry ~= nil then
			return entry[1], entry[2]
		end
	end
	old.Trace = old.Trace
		or function()
			local out = {}
			for index, item in ipairs(trace) do
				out[index] = { kind = item.kind, detail = item.detail }
			end
			return out
		end
	-- Activates a silent registry, then shows the outdated notice when revision 1 adopted an older standalone.
	local function Settle(reason)
		if old.Selected() == nil and old.Error() == nil then
			Note("activate", reason)
			old.Activate()
			local namespace = old.Namespace()
			if namespace ~= nil and type(namespace.Login) == "function" then
				pcall(namespace.Login)
			end
		end
		local selected = old.Selected()
		if selected == nil or selected.mode ~= "legacy" then
			return
		end
		local newest
		for _, copy in ipairs(old.Candidates()) do
			if copy.sealed and copy.rejected == nil and (newest == nil or copy.build > newest) then
				newest = copy.build
			end
		end
		local installed = VersionBuild(InstalledVersion())
		if newest ~= nil and (installed == nil or installed < newest) and old.Warning == nil then
			local text = OutdatedText(InstalledVersion(), newest)
			old.Warning = function()
				return text
			end
			Note("legacy", "older than embedded " .. BuildVersion(newest))
			Note("notice", NoticeOnce(InstalledVersion(), text) and "shown" or "already shown for this version")
		end
	end
	local frame = CreateFrame("Frame")
	frame:RegisterEvent("PLAYER_ENTERING_WORLD")
	frame:RegisterEvent("VARIABLES_LOADED")
	frame:SetScript("OnEvent", function(_, event, ...)
		seen[event] = true
		frame:UnregisterEvent(event)
		if event == "PLAYER_ENTERING_WORLD" then
			entry = { ... }
			-- The world is entered, so every startup host's files and SavedVariables are in.
			Settle("PLAYER_ENTERING_WORLD without PLAYER_LOGIN (revision 1 registry)")
		end
	end)
	Note("supervise", "revision 1 registry")
	-- Revision 1 listens only for PLAYER_LOGIN. When this copy first loads after login (both hosts loaded on demand or
	-- by hand after the world entry), neither event is coming, so the registry settles on the next frame, after this
	-- host's files have registered and sealed.
	local isLoggedIn = rawget(_G, "IsLoggedIn")
	if type(isLoggedIn) == "function" and isLoggedIn() == true then
		seen.PLAYER_ENTERING_WORLD, seen.VARIABLES_LOADED = true, true
		local timer = rawget(_G, "C_Timer")
		if type(timer) == "table" and type(timer.After) == "function" then
			timer.After(0, function()
				Settle("after login (revision 1 registry)")
			end)
		end
	end
end

local existing = rawget(_G, "ForeverCoreLoader")
if existing ~= nil then
	if type(existing) == "table" and existing.schema == SCHEMA and (existing.revision or 1) < REVISION then
		Supervise(existing)
	end
	return
end

local Loader = { schema = SCHEMA, revision = REVISION }
_G.ForeverCoreLoader = Loader

local state = {
	activated = false,
	loggedIn = false,
	loginRan = false,
	booting = false,
	readyRunning = false,
	scheduled = false,
	candidates = {},
	byFolder = {},
	rejections = {},
	onReady = {},
	stores = {},
	storesByFolder = {},
	trace = {},
	seen = {},
	addonLoaded = {},
}

-- The loader's own record of what happened, in order: each copy's begin, seal and rejection, the events that drove
-- activation and how the boot ended. A copy that registered but never ran is otherwise silent (Selected and Error
-- both nil), so this is what an in-game check reads to see which step was reached. Bounded, oldest dropped first.
local function Trace(kind, folder, detail)
	local trace = state.trace
	if #trace >= TRACE_LIMIT then
		table.remove(trace, 1)
	end
	trace[#trace + 1] = {
		kind = kind,
		folder = folder ~= nil and tostring(folder) or nil,
		detail = detail ~= nil and tostring(detail) or nil,
		time = type(GetTime) == "function" and GetTime() or nil,
	}
end

local function Record(folder, reason)
	state.rejections[#state.rejections + 1] = { folder = tostring(folder or "?"), reason = reason }
	Trace("reject", folder or "?", reason)
	return false, reason
end

-- The build is baked at release as major * 1000000 + minor * 1000 + patch. A value outside that shape is a broken
-- package, so the copy is rejected at Begin instead of competing with a number no release could have produced.
local function ValidBuild(build)
	return type(build) == "number" and build == build and build >= 1000000 and build % 1 == 0
end

-- An embedded copy lives under the consumer's Libs folder. The standalone participant keeps the top-level addon
-- layout its TOC and media already use, so its root is the addon folder itself.
local function Root(folder)
	if folder == "ForeverCore" then
		return "Interface\\AddOns\\ForeverCore"
	end
	return "Interface\\AddOns\\" .. folder .. "\\Libs\\ForeverCore"
end

-- Consumer callbacks are not boot chunks. Their failures must reach the client's own error handler (BugSack and the
-- script-error display), the way any other addon's startup error does. Recording one as well keeps it visible to
-- `/fcore` when the client has no handler; each kind of callback has its own field so a good boot stays readable.
local function Protected(field, callback)
	local handler = type(geterrorhandler) == "function" and geterrorhandler() or nil
	local failure
	local ok, err
	if type(handler) == "function" then
		ok, err = xpcall(callback, function(message)
			-- The client handler commonly returns nothing. Capture the original error before calling it so the record
			-- never degrades to the handler's return value.
			failure = tostring(message)
			return handler(message)
		end)
	else
		ok, err = pcall(callback)
	end
	if not ok then
		state[field] = state[field] or failure or tostring(err)
	end
	return ok, err
end

-- Work that must not run inside the event dispatch that triggered it runs on the next frame. Without C_Timer (a test
-- harness) it runs at once.
local function NextFrame(callback)
	local timer = rawget(_G, "C_Timer")
	if type(timer) == "table" and type(timer.After) == "function" then
		timer.After(0, callback)
	else
		callback()
	end
end

-- A session that cannot run ForeverCore says why once, through the client's error handler (BugSack, the script error
-- display), so each consumer's own ready step can stay quiet instead of repeating a generic failure.
local function ReportFailure()
	if state.failureReported or state.error == nil then
		return
	end
	state.failureReported = true
	local handler = type(geterrorhandler) == "function" and geterrorhandler() or nil
	if type(handler) == "function" then
		pcall(handler, "ForeverCore: " .. state.error)
	end
end

-- One login per session, after activation and its ready callbacks. Legacy and a failed boot have no namespace, so
-- they never run it. A converted runtime defines namespace.Login; a copy that does not is a broken package.
local function CallLogin()
	if state.loginRan or state.namespace == nil then
		return
	end
	state.loginRan = true
	local login = state.namespace.Login
	if type(login) ~= "function" then
		state.loginError = state.loginError
			or ("ForeverCore copy " .. state.namespace.folder .. " published no namespace Login")
		return false, state.loginError
	end
	return Protected("loginError", login)
end

-- The outdated-standalone notice, after the world is entered (see NoticeOnce).
local function ShowWarning()
	if state.warning == nil or state.warningShown then
		return
	end
	if not state.seen.PLAYER_ENTERING_WORLD then
		state.warnAtEntry = true
		return
	end
	state.warningShown = true
	local shown = NoticeOnce(state.selection and state.selection.version, state.warning)
	Trace("notice", "ForeverCore", shown and "shown" or "already shown for this version")
end

-- Logged in means PLAYER_LOGIN has fired in this session, whether this loader saw it or the client says so. A copy
-- whose file first loads after login (an addon enabled mid-session, LoadAddOn) never sees PLAYER_LOGIN.
-- PLAYER_LOGIN and ADDON_LOADED drive activation. PLAYER_ENTERING_WORLD and VARIABLES_LOADED are also recorded once
-- seen (Loader.Seen), because a runtime that boots after either has fired must not wait for it again: an
-- EventUtil.ContinueAfterAllEvents registered after the event never completes.
local WORLD_EVENTS = { "PLAYER_ENTERING_WORLD", "VARIABLES_LOADED" }

local function LoggedIn()
	local isLoggedIn = rawget(_G, "IsLoggedIn")
	return state.loggedIn or (type(isLoggedIn) == "function" and isLoggedIn() == true)
end

local function InCombat()
	local lockdown = rawget(_G, "InCombatLockdown")
	return type(lockdown) == "function" and lockdown() == true
end

-- Booting reconciles every offered account store, so it waits until they are loaded: VARIABLES_LOADED, or the
-- ADDON_LOADED of every host whose copy is sealed. With no sealed copy there is nothing to wait for, and activation
-- records that instead.
local function SavedVariablesReady()
	if state.seen.VARIABLES_LOADED then
		return true
	end
	for _, copy in ipairs(state.candidates) do
		if copy.sealed and copy.rejected == nil and not state.addonLoaded[copy.folder] then
			return false
		end
	end
	return true
end

-- Activation and its one login, from whichever path reached the loader first. Boot creates frames and installs hooks,
-- so under combat lockdown it waits for PLAYER_REGEN_ENABLED instead of failing for the whole session.
local function ActivateNow(reason, folder)
	if state.activated then
		return
	end
	if InCombat() and state.frame ~= nil then
		if state.pending == nil then
			state.pending = { reason = reason, folder = folder }
			Trace("wait", folder, "combat lockdown: " .. reason)
			state.frame:RegisterEvent("PLAYER_REGEN_ENABLED")
		end
		return
	end
	Trace("activate", folder, reason)
	state.loggedIn = true
	Loader.Activate()
	if state.activated then
		if state.frame ~= nil then
			state.frame:UnregisterEvent("PLAYER_LOGIN")
		end
		CallLogin()
	end
end

-- After login, activation runs on the next frame rather than inside the ADDON_LOADED dispatch or the file load that
-- asked for it: a load-on-demand host's files, SavedVariables and ADDON_LOADED handlers have all run by then, and the
-- consumer files' event replay is the only delivery of the event it replays.
local function ScheduleActivation(reason, folder)
	if state.activated or state.scheduled then
		return
	end
	state.scheduled = true
	NextFrame(function()
		state.scheduled = false
		ActivateNow(reason, folder)
	end)
end

-- A store offered by a host that joined an already running copy is reconciled once that host's SavedVariables and
-- its own ADDON_LOADED handlers have run, so its account table gets the live mirror this session.
local function ReconcileLateStore(folder)
	local entry = state.storesByFolder[folder]
	if entry == nil or not entry.late then
		return
	end
	entry.late = nil
	NextFrame(function()
		local namespace = state.namespace
		if namespace ~= nil and type(namespace.RefreshStore) == "function" then
			Trace("store", folder, "late offer reconciled")
			Protected("loginError", namespace.RefreshStore)
		end
	end)
end

local function OnEvent(frame, event, name, ...)
	if event == "PLAYER_ENTERING_WORLD" or event == "VARIABLES_LOADED" then
		-- Recorded before any activation below, so the runtime it boots already sees this event as past.
		state.seen[event] = true
		if event == "PLAYER_ENTERING_WORLD" and state.worldEntry == nil then
			state.worldEntry = { name, ... }
		end
		frame:UnregisterEvent(event)
		if event == "PLAYER_ENTERING_WORLD" and state.warnAtEntry then
			state.warnAtEntry = nil
			ShowWarning()
		end
	elseif event == "PLAYER_REGEN_ENABLED" then
		frame:UnregisterEvent(event)
		local pending = state.pending
		state.pending = nil
		if pending ~= nil then
			ActivateNow(pending.reason .. ", after combat", pending.folder)
		end
		return
	elseif event == "ADDON_LOADED" and state.byFolder[name] ~= nil then
		state.addonLoaded[name] = true
	end
	if state.activated then
		if event == "ADDON_LOADED" then
			ReconcileLateStore(name)
		end
		return
	end
	if event == "PLAYER_LOGIN" then
		-- All startup copies and account globals are available before election.
		ActivateNow("PLAYER_LOGIN")
	elseif event == "ADDON_LOADED" then
		if state.byFolder[name] == nil then
			return
		end
		if LoggedIn() then
			ScheduleActivation("ADDON_LOADED after login", name)
		elseif state.seen.PLAYER_ENTERING_WORLD and SavedVariablesReady() then
			ScheduleActivation("PLAYER_ENTERING_WORLD without PLAYER_LOGIN", name)
		end
	elseif state.seen.PLAYER_ENTERING_WORLD then
		-- PLAYER_ENTERING_WORLD, or a VARIABLES_LOADED that completes the stores it was waiting for. Like the
		-- after-login path, it runs on the next frame, so the consumer files' replay of the world entry they missed is
		-- its only delivery.
		if SavedVariablesReady() then
			ScheduleActivation("PLAYER_ENTERING_WORLD without PLAYER_LOGIN")
		elseif event == "PLAYER_ENTERING_WORLD" then
			Trace("wait", nil, "PLAYER_ENTERING_WORLD before SavedVariables")
		end
	end
end

-- The one loading frame, created by the first Begin. Every copy shares it, so a second loader copy adds no event.
-- PLAYER_LOGIN is the normal path. PLAYER_ENTERING_WORLD follows PLAYER_LOGIN on every login and reload, so a session
-- in which this frame missed PLAYER_LOGIN still activates there, and the trace says so. ADDON_LOADED stays registered
-- after activation for hosts that join the running copy.
local function EnsureLoginFrame()
	if state.frame ~= nil or type(CreateFrame) ~= "function" then
		return
	end
	local frame = CreateFrame("Frame")
	state.frame = frame
	frame:RegisterEvent("PLAYER_LOGIN")
	frame:RegisterEvent("ADDON_LOADED")
	for _, event in ipairs(WORLD_EVENTS) do
		frame:RegisterEvent(event)
	end
	if LoggedIn() then
		-- A host first loaded after login is a load-on-demand addon, which the client loads once the world is
		-- entered; no client call says so directly. The frame still records an entry that fires later.
		for _, event in ipairs(WORLD_EVENTS) do
			state.seen[event] = true
		end
	end
	frame:SetScript("OnEvent", OnEvent)
end

-- Defined with the legacy helpers below; Seal reports a newly sealed copy to it.
local CheckLegacyAge

local methods = {}

-- One wrapped file. Defining is registration only; the chunk runs at activation, in the order the TOC listed it.
function methods:Define(chunk)
	if self.rejected ~= nil then
		return false, self.rejected
	end
	if self.sealed then
		return false, "sealed"
	end
	if type(chunk) ~= "function" then
		self.rejected = "chunk"
		return Record(self.folder, "chunk")
	end
	self.chunks[#self.chunks + 1] = chunk
	return self
end

-- The End.lua marker. Only a sealed copy can be elected, so a truncated package loses without running anything: a
-- copy that named its chunk count at Begin must have defined exactly that many. A copy sealed after login with no
-- activation yet (load on demand, a manual load) activates on the next frame.
function methods:Seal()
	if self.rejected ~= nil then
		return false, self.rejected
	end
	if self.sealed then
		return false, "sealed"
	end
	if #self.chunks == 0 then
		self.rejected = "empty"
		return Record(self.folder, "empty")
	end
	if self.expected ~= nil and #self.chunks ~= self.expected then
		self.rejected = "incomplete"
		return Record(self.folder, "incomplete")
	end
	self.sealed = true
	Trace("seal", self.folder, #self.chunks)
	CheckLegacyAge()
	if not state.activated and LoggedIn() then
		ScheduleActivation("sealed after login", self.folder)
	end
	return true
end

local function Rejected(folder, reason, build, digest)
	Record(folder, reason)
	return setmetatable({
		folder = tostring(folder or "?"),
		build = build,
		digest = digest,
		root = "",
		chunks = {},
		sealed = false,
		rejected = reason,
	}, { __index = methods })
end

-- A legacy table is any ForeverCore that predates this loader schema. It is adopted as it is, never neutralised:
-- its hooks and named frames cannot be undone, so a second runtime must not start beside it.
local function LegacyCore()
	local core = rawget(_G, "ForeverCore")
	if type(core) == "table" and core.loaderSchema ~= SCHEMA then
		return core
	end
end

-- An adopted legacy table that is older than a registered copy still serves the session, since a second runtime cannot
-- start beside it, and the player is told which install to update. Older means a lower build than the newest
-- registered copy; a standalone whose version cannot be read is treated as older, since it has no loader schema.
function CheckLegacyAge()
	local selection = state.selection
	if selection == nil or selection.mode ~= "legacy" then
		return
	end
	local newest
	for _, copy in ipairs(state.candidates) do
		if copy.sealed and copy.rejected == nil and (newest == nil or copy.build > newest) then
			newest = copy.build
		end
	end
	if newest == nil or (selection.newest ~= nil and selection.newest >= newest) then
		return
	end
	if selection.build ~= nil and selection.build >= newest then
		return
	end
	selection.newest = newest
	state.warning = OutdatedText(selection.version, newest)
	Trace("legacy", "ForeverCore", "older than embedded " .. BuildVersion(newest))
	ShowWarning()
end

-- What every embedding consumer's ready step uses: API 2, Register and the tracker line with SetInteractive. One rule
-- for every mode: a legacy table that fails it is not adopted (a second runtime cannot start beside it, so the session
-- fails naming its version), and an elected copy that fails it is refused before its Start.
local CONSUMER_API = 2
local function ServesConsumers(core)
	local line = core.TrackerLine
	return core.API == CONSUMER_API
		and type(core.Register) == "function"
		and type(line) == "table"
		and type(line.SetInteractive) == "function"
end

-- A consumer callback is not a boot chunk: it runs after the winner owns the session. One failure is reported and
-- recorded without stopping the next callback.
local function CallReady(callback)
	return Protected("callbackError", function()
		return callback(state.facade, Loader.Selected())
	end)
end

-- Registration order is run order. A callback that registers another OnReady while this loop runs queues it after
-- the callbacks already waiting, rather than running it ahead of them.
local function RunReady()
	if state.readyRan then
		return
	end
	state.readyRan = true
	state.readyRunning = true
	local index = 1
	while index <= #state.onReady do
		CallReady(state.onReady[index])
		index = index + 1
	end
	state.onReady = {}
	state.readyRunning = false
end

-- Runs the winner's chunks into one fresh namespace. Only this function may set the global facade, and only once.
-- Each wrapped file is called with the same varargs the standalone main chunk sees: the fixed identity "ForeverCore",
-- then the namespace. The namespace carries its mode before the first chunk and the runtime's explicit Start runs
-- before anything is published, so a failed Start leaves no facade. Defining the runtime creates no frame, event or
-- hook (tests/embedded_loader_spec.lua checks every core file), so a copy refused here leaves the client untouched.
local function Boot(copy)
	local namespace = { folder = copy.folder, root = copy.root, copy = copy }
	namespace.mode = copy.standalone and "standalone" or "elected"
	for index = 1, #copy.chunks do
		copy.chunks[index]("ForeverCore", namespace)
	end
	local start = namespace.Start
	if type(start) ~= "function" then
		error("ForeverCore copy " .. copy.folder .. " published no namespace Start", 0)
	end
	if type(namespace.Login) ~= "function" then
		error("ForeverCore copy " .. copy.folder .. " published no namespace Login", 0)
	end
	local facade = namespace.ForeverCore
	if type(facade) ~= "table" then
		error("ForeverCore copy " .. copy.folder .. " published no namespace facade", 0)
	end
	if not ServesConsumers(facade) then
		error("ForeverCore copy " .. copy.folder .. " published a facade the consumers cannot use", 0)
	end
	-- The copy's End.lua names its own tracker line template, which every consumer's ready step draws with.
	if type(facade.TrackerLine.template) ~= "string" then
		error("ForeverCore copy " .. copy.folder .. " published no tracker line template", 0)
	end
	if facade.loaderSchema ~= nil and facade.loaderSchema ~= SCHEMA then
		error("ForeverCore copy " .. copy.folder .. " published an incompatible loader schema", 0)
	end
	if facade.build ~= nil and facade.build ~= copy.build then
		error("ForeverCore copy " .. copy.folder .. " published a build that is not the sealed build", 0)
	end
	local published = rawget(_G, "ForeverCore")
	if published ~= nil and published ~= facade then
		error("ForeverCore copy " .. copy.folder .. " found another ForeverCore already published", 0)
	end
	start()
	if namespace.ForeverCore ~= facade then
		error("ForeverCore copy " .. copy.folder .. " replaced its facade during Start", 0)
	end
	published = rawget(_G, "ForeverCore")
	if published ~= nil and published ~= facade then
		error("ForeverCore copy " .. copy.folder .. " found another ForeverCore already published", 0)
	end
	if published == nil then
		_G.ForeverCore = facade
	end
	if facade.loaderSchema == nil then
		facade.loaderSchema = SCHEMA
	end
	if facade.build == nil then
		facade.build = copy.build
	end
	state.namespace = namespace
	state.facade = facade
end

-- The election picks the highest sealed build. Two copies at that highest build with different content digests are
-- not interchangeable (a consumer rebuilt with newer tooling, a modified package), so the loader chooses neither: no
-- folder name or load order is a reason to boot one over the other. Every copy at that build is diagnosed and the
-- election moves to the next lower sealed build. Equal builds with the same digest (including no digest) are the
-- same package. A missing digest is not proof of equal bytes.
local function Elect()
	local excluded = {}
	while true do
		local bestBuild
		local firstDigest
		local digestsDiffer = false
		for _, copy in ipairs(state.candidates) do
			if copy.sealed and copy.rejected == nil and not excluded[copy] then
				if bestBuild == nil or copy.build > bestBuild then
					bestBuild = copy.build
					firstDigest = copy.digest
					digestsDiffer = false
				elseif copy.build == bestBuild and copy.digest ~= firstDigest then
					digestsDiffer = true
				end
			end
		end
		if bestBuild == nil then
			return nil
		end
		local tied = {}
		for _, copy in ipairs(state.candidates) do
			if copy.sealed and copy.rejected == nil and not excluded[copy] and copy.build == bestBuild then
				tied[#tied + 1] = copy
			end
		end
		if not digestsDiffer then
			return tied[1]
		end
		-- Every copy at the tied build is diagnosed, including two that share one digest: the set as a whole is the
		-- conflict, and a report that names only the first of a repeated digest hides a candidate.
		for _, copy in ipairs(tied) do
			Record(copy.folder, "tie-conflict")
			excluded[copy] = true
		end
		state.conflict = state.conflict or bestBuild
		Trace("elect", nil, "conflicting copies at " .. BuildVersion(bestBuild) .. "; trying a lower build")
	end
end

-- One activation per session, and one boot inside it. A failing winner is terminal: its Start may already have
-- installed irreversible hooks, so a lower copy is never started over it. With no sealed copy nothing ran, so the
-- session stays open: the error is recorded, ready callbacks wait, and a host that seals later can still activate.
function Loader.Activate()
	if state.activated then
		return state.facade
	end
	local legacy = state.legacy or LegacyCore()
	if legacy ~= nil then
		state.activated = true
		state.legacy = legacy
		local version = InstalledVersion()
		if not ServesConsumers(legacy) then
			state.error = "the installed ForeverCore "
				.. tostring(version or "standalone")
				.. " is too old for the embedded copies; update or disable it"
			Trace("legacy", "ForeverCore", "incompatible " .. tostring(version))
			ReportFailure()
			RunReady()
			return nil
		end
		state.facade = legacy
		state.selection = { mode = "legacy", core = legacy, version = version, build = VersionBuild(version) }
		Trace("legacy", "ForeverCore", version)
		CheckLegacyAge()
		RunReady()
		return legacy
	end
	-- A copy that began but never sealed is a package whose files did not all load. It cannot run, so the report
	-- names it rather than leaving it out silently.
	for _, copy in ipairs(state.candidates) do
		if not copy.sealed and copy.rejected == nil and not copy.unsealedReported then
			copy.unsealedReported = true
			Record(copy.folder, "unsealed")
		end
	end
	local chosen = Elect()
	if chosen == nil then
		if state.conflict ~= nil then
			state.activated = true
			state.error = "conflicting ForeverCore copies at build " .. state.conflict
			Trace("boot", nil, state.error)
			ReportFailure()
			RunReady()
			return nil
		end
		state.error = "no sealed ForeverCore copy"
		Trace("boot", nil, state.error .. "; waiting for a sealed copy")
		return nil
	end
	state.activated = true
	state.error = nil
	state.booting = true
	local ok, err = pcall(Boot, chosen)
	state.booting = false
	if ok then
		state.selection = {
			mode = chosen.standalone and "standalone" or "elected",
			build = chosen.build,
			folder = chosen.folder,
			root = chosen.root,
			core = state.facade,
		}
	else
		state.error = tostring(err)
		state.selection = nil
	end
	Trace("boot", chosen.folder, ok and "ok" or state.error)
	ReportFailure()
	RunReady()
	return state.facade
end

-- A copy begins once and registers without side effects. A begin after activation is rejected: a runtime that has
-- already booted cannot be replaced in place. Under an adopted legacy table a later copy may still register, because
-- nothing of it will ever run. `chunks`, when given, is the number of Define calls the package makes, so Seal can
-- refuse a package with missing files.
function Loader.Begin(folder, build, digest, chunks)
	if type(folder) ~= "string" or folder == "" then
		return Rejected(folder, "folder", build, digest)
	end
	if digest ~= nil and (type(digest) ~= "string" or digest == "") then
		return Rejected(folder, "digest", build, digest)
	end
	if chunks ~= nil and (type(chunks) ~= "number" or chunks < 1 or chunks % 1 ~= 0) then
		return Rejected(folder, "chunks", build, digest)
	end
	if state.legacy == nil then
		state.legacy = LegacyCore()
		-- 1.8 is already loaded at the first consumer's file load. Activating it now means that consumer's OnReady
		-- runs inside the same file load, which is where 1.8's Register and TrackerSection use already works.
		if state.legacy ~= nil then
			Loader.Activate()
		end
	end
	if state.activated and state.legacy == nil then
		return Rejected(folder, "late", build, digest)
	end
	if not ValidBuild(build) then
		return Rejected(folder, "build", build, digest)
	end
	if state.byFolder[folder] ~= nil then
		return Rejected(folder, "duplicate", build, digest)
	end
	local copy = setmetatable({
		folder = folder,
		build = build,
		digest = digest,
		expected = chunks,
		root = Root(folder),
		chunks = {},
		sealed = false,
		standalone = folder == "ForeverCore",
	}, { __index = methods })
	state.byFolder[folder] = copy
	state.candidates[#state.candidates + 1] = copy
	Trace("begin", folder, build)
	EnsureLoginFrame()
	return copy
end

-- Ready callbacks are consumer files that cannot touch Core until activation. Registration order is run order, and
-- a registration made after activation runs at once. A registration made from inside a ready callback queues behind
-- the callbacks already waiting. One callback's error is reported and recorded without stopping the next.
function Loader.OnReady(callback)
	if type(callback) ~= "function" then
		error("ForeverCoreLoader.OnReady: function expected", 2)
	end
	if state.activated and not state.booting and not state.readyRunning then
		return CallReady(callback)
	end
	state.onReady[#state.onReady + 1] = callback
	return true
end

-- The saved-variable seam. The loader retains only the folder and the explicit account SavedVariables global name; it
-- never captures the table, accepts a getter, looks the name up, or applies any migration policy. The elected runtime
-- resolves the name with rawget(_G, name) at reconciliation, so a registration before SavedVariables arrive and a
-- later replacement are both valid. Strategy belongs to the replaceable runtime, not this schema. An offer made after
-- activation (a host joining the running copy) is reconciled at that host's ADDON_LOADED.
function Loader.OfferStore(folder, globalName)
	if type(folder) ~= "string" or folder == "" then
		return Record(folder, "store-folder")
	end
	if type(globalName) ~= "string" or globalName == "" then
		return Record(folder, "store-name")
	end
	-- The converted standalone repeats its generated offer when its runtime chunk boots.
	local existingOffer = state.storesByFolder[folder]
	if existingOffer ~= nil and existingOffer.globalName == globalName then
		return true
	end
	if existingOffer ~= nil then
		return Record(folder, "duplicate")
	end
	local entry = { folder = folder, globalName = globalName, late = state.activated or nil }
	state.stores[#state.stores + 1] = entry
	state.storesByFolder[folder] = entry
	return true
end

-- The runtime resolves each offered name against the live globals at reconciliation. Entries are returned in offer
-- order with no lookup, copy, validation of the current value, or choice.
function Loader.Offers()
	local out = {}
	for index, entry in ipairs(state.stores) do
		out[index] = { folder = entry.folder, globalName = entry.globalName }
	end
	return out
end

-- Every registered copy, in Begin order. The diagnostic path needs the installed versions even when the highest one
-- never booted, and the runtime needs the winning copy's build for state provenance.
function Loader.Candidates()
	local out = {}
	for index, copy in ipairs(state.candidates) do
		out[index] = {
			folder = copy.folder,
			build = copy.build,
			digest = copy.digest,
			root = copy.root,
			sealed = copy.sealed == true,
			standalone = copy.standalone == true,
			rejected = copy.rejected,
		}
	end
	return out
end

-- The running copy. A legacy selection also carries the newest registered copy's build (`newest`) when the adopted
-- table is older than it, which is also Warning().
function Loader.Selected()
	if not state.activated or state.selection == nil then
		return nil
	end
	local selection = state.selection
	return {
		mode = selection.mode,
		version = selection.version,
		build = selection.build,
		newest = selection.newest,
		folder = selection.folder,
		root = selection.root,
		core = selection.core,
	}
end

function Loader.Namespace()
	return state.namespace
end

function Loader.Facade()
	return state.facade
end

-- The boot error only. Consumer callback and runtime login failures are separate records, because the runtime itself
-- may have booted cleanly (core#509).
function Loader.Error()
	return state.error
end

-- A session that runs but should be fixed by the player (an outdated standalone). The on-screen notice shows once
-- per standalone version; this stays readable every session.
function Loader.Warning()
	return state.warning
end

function Loader.CallbackError()
	return state.callbackError
end

function Loader.LoginError()
	return state.loginError
end

function Loader.Rejections()
	local out = {}
	for index, rejection in ipairs(state.rejections) do
		out[index] = { folder = rejection.folder, reason = rejection.reason }
	end
	return out
end

-- The loader's ordered record (see Trace above), copied so a caller cannot change it.
function Loader.Trace()
	local out = {}
	for index, entry in ipairs(state.trace) do
		out[index] = { kind = entry.kind, folder = entry.folder, detail = entry.detail, time = entry.time }
	end
	return out
end

-- Whether PLAYER_ENTERING_WORLD or VARIABLES_LOADED has already fired this session, as the loading frame saw it. The
-- runtime's waits skip an event that is already past instead of waiting for one that will not come again.
function Loader.Seen(event)
	return state.seen[event] == true
end

-- The arguments of the first PLAYER_ENTERING_WORLD the loading frame saw (isInitialLogin, isReloadingUi), for a
-- runtime booted after it that needs to know which kind of entry this session began with.
function Loader.WorldEntry()
	local entry = state.worldEntry
	if entry ~= nil then
		return entry[1], entry[2]
	end
end
