-- Converted ForeverCore chunks: the same source files called with a loader namespace (ns.copy present, elected or
-- standalone), proving the runtime keeps one ns.store and never publishes a global facade or creates ForeverCoreDB in
-- elected mode. The unwrapped standalone compatibility path is covered by core_spec.lua and api_spec.lua.
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local FakeClient = dofile("tests/fake_client.lua")
local Toc = dofile(".agents/skills/wow-forever-addon/tooling/forever_sim/toc.lua")

local function Files()
	local paths = {}
	for _, entry in ipairs(Toc.files(".", "ForeverCore.toc")) do
		if entry.kind == "lua" and entry.path ~= "Core/Loader.lua" then
			paths[#paths + 1] = entry.path
		end
	end
	return paths
end

-- Loads the real converted files in TOC order into `ns`, the way a consumer's Define chunks would be called. The
-- loader file itself is unwrapped and is not part of this list.
local function Converted(env, ns, onLoaded)
	for _, path in ipairs(Files()) do
		-- Core's own quest list needs the full native tracker template, which this fake client does not build; the
		-- API is defined before it returns and is exercised separately below.
		local native = env.ObjectiveTrackerFrame
		if path == "UI/TrackerQuests.lua" then
			env.ObjectiveTrackerFrame = nil
		end
		local chunk = assert(loadfile(path), path)
		setfenv(chunk, env)
		chunk("ForeverCore", ns)
		env.ObjectiveTrackerFrame = native
		if onLoaded then
			onLoaded(path)
		end
	end
end

-- Elected: Expose hands the facade to the namespace only, and Start runs on the supplied store.
local env = FakeClient.new()
local errors = { { signature = "saved", kind = "error", message = "before login", count = 2 } }
local log = { lines = { "2026-01-01 00:00:00 +1.0s saved line" }, pinned = true }
local supplied = {
	trackerHost = { attached = false, scale = 0 / 0, locked = "yes" },
	errors = errors,
	log = log,
}
local ns = { copy = {}, mode = "elected", store = supplied }
local globalAtExpose
Converted(env, ns, function(path)
	if path == "Expose.lua" then
		globalAtExpose = env.ForeverCore
	end
end)

check(globalAtExpose == nil, "converted Expose never publishes the global facade")
check(type(ns.ForeverCore) == "table", "the converted facade lives on the namespace")
check(env.ForeverCoreDB == nil, "loading converted chunks creates no ForeverCoreDB")
check(rawequal(ns.Store(), supplied), "the supplied elected store is the namespace store")

local order = {}
local migrate = ns.MigrateTrackerSettings
ns.MigrateTrackerSettings = function()
	local store = ns.Store()
	order.normalized = type(store.trackerHost) == "table"
	order.attached = type(store.errors) == "table" and type(store.log) == "table"
	order.history = rawequal(store.errors, errors) and rawequal(store.log, log)
	return migrate()
end
ns.Start()
check(order.normalized, "Start normalizes the tracker settings before migration")
check(order.attached, "Start attaches the journal and log before migration")
check(order.history, "attaching keeps the supplied history table identities")
check(rawequal(ns.Store(), supplied), "Start keeps the one supplied store")
equal(supplied.trackerHost.attached, false, "a supplied detach survives normalization")
equal(supplied.trackerHost.scale, 1, "a broken supplied scale is normalized")
equal(supplied.trackerHost.locked, false, "a broken supplied Lock switch is normalized")
check(rawequal(supplied.errors, errors), "the journal table is the supplied one")
check(rawequal(supplied.log, log), "the log table is the supplied one")
check(supplied.log.pinned == true, "the saved pin survives")
check(env.ForeverCoreDB == nil, "elected Start never creates or reads the global ForeverCoreDB")
ns.Login()
check(env.ForeverCoreDB == nil, "Login is a lifecycle no-op in this slice")

-- A section attached before Start can offer legacy tracker settings. The migration must land in the supplied elected
-- store; the initial table has no migrated marker, so the offer is eligible.
local legacyEnv = FakeClient.new()
local legacyStore = { trackerHost = { attached = true, scale = 1, locked = false } }
local legacyNs = { copy = {}, mode = "elected", store = legacyStore }
Converted(legacyEnv, legacyNs)
local legacySection = FakeClient.widget("Frame")
legacySection.legacySettings = { scale = 0.8, locked = true, x = 30, y = -40, backdropOpacity = 0.5 }
legacyNs.TrackerHost.Attach(legacySection)
equal(legacyStore.trackerHost.scale, 0.8, "pre-Start legacy scale migrates into the namespace store")
check(legacyStore.trackerHost.locked == true, "pre-Start legacy lock migrates")
equal(legacyStore.trackerHost.x, 30, "pre-Start legacy position migrates")
check(legacyStore.trackerHost.migrated == true, "the pre-Start migration is marked once")
check(legacyEnv.ForeverCoreDB == nil, "pre-Start migration creates no global ForeverCoreDB")
legacyNs.Start()
equal(legacyStore.trackerHost.scale, 0.8, "Start keeps the migrated scale")
check(legacyNs.Store() == legacyStore, "Start still uses the supplied elected store")
check(legacyEnv.ForeverCoreDB == nil, "Start after migration creates no global ForeverCoreDB")

-- Elected refuses to invent a store: real Core.lua as a converted chunk, no supplied table.
local absentEnv = FakeClient.new()
local absent = { copy = {}, mode = "elected" }
setfenv(assert(loadfile("Core.lua")), absentEnv)("ForeverCore", absent)
local ok, err = pcall(absent.Start)
equal(ok, false, "elected Start without a supplied store is refused")
check(tostring(err):find("supplied ns.store", 1, true) ~= nil, "and says the store is required")
check(absentEnv.ForeverCoreDB == nil, "the refusal creates no global ForeverCoreDB")

-- The standalone guard: a pre-saved-variables read caches no placeholder, then Start adopts the injected table and
-- keeps its settings and history. This is the same path a converted standalone takes at its ADDON_LOADED.
local standaloneEnv = FakeClient.new()
local standalone = { copy = {}, mode = "standalone" }
setfenv(assert(loadfile("Core.lua")), standaloneEnv)("ForeverCore", standalone)
local defaults = standalone.TrackerHostSettings()
check(defaults.attached == true and defaults.scale == 1, "a pre-saved-variables read answers with defaults")
check(standalone.Store() == nil, "and caches no placeholder store")
local injectedErrors = { { signature = "standalone", kind = "error", message = "saved", count = 3 } }
local injectedLog = { lines = { "2026-01-01 00:00:00 +2.0s kept" }, pinned = true }
standaloneEnv.ForeverCoreDB = {
	trackerHost = { attached = false, scale = 1.4 },
	errors = injectedErrors,
	log = injectedLog,
}
standalone.Start()
check(rawequal(standalone.Store(), standaloneEnv.ForeverCoreDB), "Start adopts the injected standalone table")
equal(standaloneEnv.ForeverCoreDB.trackerHost.scale, 1.4, "injected settings survive Start")
equal(standaloneEnv.ForeverCoreDB.trackerHost.attached, false, "including the injected detach")
check(rawequal(standaloneEnv.ForeverCoreDB.errors, injectedErrors), "injected journal history survives Start")
check(rawequal(standaloneEnv.ForeverCoreDB.log, injectedLog), "injected log history survives Start")

-- TrackerQuests writes the namespace store, never a global.
local questsEnv = FakeClient.new()
questsEnv.ObjectiveTrackerFrame = nil
local quests = {
	copy = {},
	mode = "elected",
	store = { questList = false },
	L = setmetatable({}, {
		__index = function(_, key)
			return key
		end,
	}),
}
function quests.Store()
	return quests.store
end
setfenv(assert(loadfile("UI/TrackerQuests.lua")), questsEnv)("ForeverCore", quests)
check(quests.TrackerQuests ~= nil, "the converted quest list publishes its API")
quests.TrackerQuests.SetEnabled(true)
check(quests.store.questList == true, "SetEnabled writes the namespace store")
check(quests.TrackerQuests.Enabled() == true, "Enabled reads the namespace store")
check(questsEnv.ForeverCoreDB == nil, "the converted quest list creates no global ForeverCoreDB")

print(("converted_runtime_spec: %d checks passed"):format(checks))
