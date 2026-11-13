-- ForeverCoreLoader, schema 1: the one registry every embedded ForeverCore copy in a client shares. A consumer's
-- Begin.lua calls Begin(folder, build, digest), its wrapped files call copy:Define(function(ns) ... end), and its
-- End.lua calls copy:Seal(). Defining and registering run no runtime code: at PLAYER_LOGIN (or, for the standalone
-- copy, at its own ADDON_LOADED) the loader elects the highest sealed build, runs only that copy's chunks into a fresh
-- namespace, and publishes its facade once.
--
-- Schema 1 is immutable. A later schema is a new global name (ForeverCoreLoader2), never an upgrade of this table:
-- an older copy must never call a newer loader's methods or the reverse. The global name therefore carries the
-- contract, and the first copy to load owns the registry for the session.
local SCHEMA = 1

if rawget(_G, "ForeverCoreLoader") ~= nil then
	return
end

local Loader = { schema = SCHEMA }
_G.ForeverCoreLoader = Loader

local state = {
	activated = false,
	loggedIn = false,
	loginRan = false,
	booting = false,
	readyRunning = false,
	candidates = {},
	byFolder = {},
	rejections = {},
	onReady = {},
	stores = {},
	storesByFolder = {},
}

local function Record(folder, reason)
	state.rejections[#state.rejections + 1] = { folder = tostring(folder or "?"), reason = reason }
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

-- The one loading frame, created by the first Begin. Every copy shares it, so a second loader copy adds no event.
local function EnsureLoginFrame()
	if state.frame ~= nil or type(CreateFrame) ~= "function" then
		return
	end
	local frame = CreateFrame("Frame")
	frame:RegisterEvent("PLAYER_LOGIN")
	frame:SetScript("OnEvent", function(_, event, addon)
		if event == "PLAYER_LOGIN" then
			-- Offers close at login, whatever activated the runtime: a standalone copy activates at its own
			-- ADDON_LOADED, before every consumer has offered its store.
			state.loggedIn = true
			Loader.Activate()
			CallLogin()
		elseif event == "ADDON_LOADED" and addon == "ForeverCore" then
			Loader.Activate()
		end
	end)
	state.frame = frame
end

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

-- The End.lua marker. Only a sealed copy can be elected, so a truncated package loses without running anything.
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
	self.sealed = true
	-- The standalone participant activates at its own ADDON_LOADED, after its SavedVariables and before a dependent
	-- consumer's files load, so an unmigrated consumer still finds ForeverCore while its own TOC loads. Newest-wins
	-- is suspended for that session; an embedded copy loading later only registers.
	if self.standalone and not state.activated then
		state.standalone = self
		EnsureLoginFrame()
		if state.frame ~= nil then
			state.frame:RegisterEvent("ADDON_LOADED")
		end
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
-- before anything is published, so a failed Start leaves no facade.
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
	start()
	local facade = namespace.ForeverCore
	if type(facade) ~= "table" then
		error("ForeverCore copy " .. copy.folder .. " published no namespace facade", 0)
	end
	if type(facade.API) ~= "number" or type(facade.Register) ~= "function" then
		error("ForeverCore copy " .. copy.folder .. " published an incomplete facade", 0)
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
-- not interchangeable, so the loader refuses to choose between them: no folder name or load order is a reason to
-- boot one over the other. Equal builds with the same digest (including no digest) are the same package. A digest is
-- required by the final packaging contract; while it is optional in groundwork, a missing digest is not proof of
-- equal bytes.
local function Elect()
	local bestBuild
	local firstDigest
	local digestsDiffer = false
	for _, copy in ipairs(state.candidates) do
		if copy.sealed and copy.rejected == nil and not copy.standalone then
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
		if copy.sealed and copy.rejected == nil and not copy.standalone and copy.build == bestBuild then
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
	end
	state.error = "conflicting ForeverCore copies at build " .. bestBuild
	return nil
end

-- One activation per session, and one boot inside it. A failing winner is terminal: its chunks may already have
-- installed irreversible hooks, so a lower copy is never started over them.
function Loader.Activate()
	if state.activated then
		return state.facade
	end
	state.activated = true
	-- The frame's ADDON_LOADED job is the standalone activation; PLAYER_LOGIN still closes store offers.
	if state.frame ~= nil then
		state.frame:UnregisterEvent("ADDON_LOADED")
	end
	local legacy = state.legacy or LegacyCore()
	if legacy ~= nil then
		state.legacy = legacy
		state.facade = legacy
		state.selection = { mode = "legacy", core = legacy }
		RunReady()
		return legacy
	end
	local chosen
	if state.standalone ~= nil and state.standalone.sealed and state.standalone.rejected == nil then
		chosen = state.standalone
	else
		chosen = Elect()
	end
	if chosen == nil then
		state.error = state.error or "no sealed ForeverCore copy"
		RunReady()
		return nil
	end
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
	RunReady()
	return state.facade
end

-- A copy begins once, before PLAYER_LOGIN, and registers without side effects. A late begin is rejected: a runtime
-- that has already booted cannot be replaced in place. Under an adopted legacy table a later copy may still register,
-- because nothing of it will ever run.
function Loader.Begin(folder, build, digest)
	if type(folder) ~= "string" or folder == "" then
		return Rejected(folder, "folder", build, digest)
	end
	if digest ~= nil and (type(digest) ~= "string" or digest == "") then
		return Rejected(folder, "digest", build, digest)
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
		root = Root(folder),
		chunks = {},
		sealed = false,
		standalone = folder == "ForeverCore",
	}, { __index = methods })
	state.byFolder[folder] = copy
	state.candidates[#state.candidates + 1] = copy
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
-- later resolves the name with rawget(_G, name) at reconciliation, so a registration before SavedVariables arrive and
-- a later replacement are both valid. Strategy belongs to the replaceable runtime (Core/Store.lua), not this schema.
function Loader.OfferStore(folder, globalName)
	if type(folder) ~= "string" or folder == "" then
		return Record(folder, "store-folder")
	end
	if type(globalName) ~= "string" or globalName == "" then
		return Record(folder, "store-name")
	end
	-- A standalone copy activates at its own ADDON_LOADED, before consumers offer. Only login closes offers.
	if state.loggedIn then
		return Record(folder, "late")
	end
	if state.storesByFolder[folder] ~= nil then
		return Record(folder, "duplicate")
	end
	local entry = { folder = folder, globalName = globalName }
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

function Loader.Selected()
	if not state.activated or state.selection == nil then
		return nil
	end
	local selection = state.selection
	return {
		mode = selection.mode,
		build = selection.build,
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
