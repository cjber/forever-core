-- ForeverCore's public API, loaded from the TOC the way the client loads it: one copy of every shared file, one
-- global, and per-addon contexts that keep their own errors, report and markers.
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

-- The fake client, shared with expose_subset_spec.lua so both specs run the files against the same stub.
local FakeClient = dofile("tests/fake_client.lua")
local widget = FakeClient.widget

-- The TOC's files, in order, the way the client loads them. XML templates are registered by the client loader; this
-- fake client runs Lua files only.
local Toc = dofile(".agents/skills/wow-forever-addon/tooling/forever_sim/toc.lua")
local function tocFiles()
	local files = {}
	for _, entry in ipairs(Toc.files(".", "ForeverCore.toc")) do
		if entry.kind == "lua" then
			files[#files + 1] = entry.path
		end
	end
	return files
end

local env, created = FakeClient.new()
local ns = {}
for _, path in ipairs(tocFiles()) do
	local chunk = assert(loadfile(path), path)
	setfenv(chunk, env)
	chunk("ForeverCore", ns)
end
local ForeverCore = env.ForeverCore
check(type(ForeverCore) == "table", "the TOC publishes ForeverCore")
equal(ForeverCore.API, 2, "the interface version is 2")
equal(ForeverCore.minor, 2, "the core table's own minor is 2")
check(type(ForeverCore.Register) == "function", "Register is the per-addon factory")
check(type(ForeverCore.Registered) == "function", "Registered says whether an addon reached Register")
check(not ForeverCore.Registered("AddonA"), "an addon that has not registered yet is false")
check(not ForeverCore.Registered(42), "a non-string name is false")
check(not ForeverCore.Registered(nil), "a nil name is false")
check(type(ForeverCore.ContextMenu) == "function", "ContextMenu is the shared menu")
check(ForeverCore.ContextMenu == ns.ContextMenu, "and it is the module UI/ContextMenu.lua built")
check(ForeverCore.Art == ns.Art, "ForeverCore publishes the Art helper")
check(ForeverCore.Art.minor == 2, "its minor is 2")
check(rawequal(env.ForeverTrackerHost, ns.TrackerHost), "ForeverTrackerHost publishes core's one host")
check(env.ForeverFamily == nil, "ForeverFamily is gone")
check(env.ForeverLeaderboards == nil, "ForeverLeaderboards is gone")
check(env.ForeverPeerStats == nil, "ForeverPeerStats is gone")
check(env.ForeverQuestLogTabs == nil, "ForeverQuestLogTabs is gone")
check(ForeverCore.ProfessionTabs == ns.ProfessionTabs, "ForeverCore publishes the ProfessionTabs module")
check(
	type(ForeverCore.QuestLogTabs.SetTabShown) == "function",
	"QuestLogTabs publishes SetTabShown with Register, Select, ShowQuests and Selected"
)
check(type(ForeverCore.Credits) == "table", "ForeverCore publishes the Credits module")
local coreNames, distinct = {}, 0
for _, row in ipairs(ns.Credits.players) do
	if not coreNames[row.name] then
		coreNames[row.name], distinct = true, distinct + 1
	end
end
equal(
	#ForeverCore.Credits.Players(),
	distinct,
	"core's own Data/Credits.lua is registered under ForeverCore, once per player"
)
check(ForeverCore.Credits.Line("ForeverCore") ~= nil, "and its one-line thanks reads")
check(env.ForeverErrorJournal == nil, "ForeverErrorJournal is gone")
check(env.ForeverDebugLog == nil, "ForeverDebugLog is gone")
check(env.ForeverMinimapButtons == nil, "ForeverMinimapButtons is gone")
check(env.ForeverMapMarkers == nil, "ForeverMapMarkers is gone")
check(ForeverCore.Attach == nil, "the old Attach helper is gone")
check(ForeverCore.Defaults == nil, "the old Defaults field is gone")
check(env.ForeverCoreDB == nil, "saved variables load after the files")

-- A first install: the client fires ForeverCore's ADDON_LOADED with no saved table. Core.lua's one handler makes it,
-- builds the host's settings and attaches core's own journal and log before any consumer registers.
local function fireAddonLoaded(addon)
	for _, frame in ipairs(created) do
		if frame.events and frame.events.ADDON_LOADED and frame.scripts and frame.scripts.OnEvent then
			frame.scripts.OnEvent(frame, "ADDON_LOADED", addon)
			return true
		end
	end
	return false
end
check(fireAddonLoaded("ForeverCore"), "the core's ADDON_LOADED handler runs")
check(type(env.ForeverCoreDB) == "table", "a first install gets a saved table")
check(type(env.ForeverCoreDB.trackerHost) == "table", "with the host's settings")
check(type(env.ForeverCoreDB.errors) == "table", "core's journal is attached")
check(type(env.ForeverCoreDB.log) == "table", "core's log ring is attached")

-- Two addons, each with its own saved table.
local A = ForeverCore.Register("AddonA", { db = { errors = {} } })
local B = ForeverCore.Register("AddonB", { db = { errors = {} } })
check(ForeverCore.Register("AddonA") == A, "Register is idempotent")
check(ForeverCore.Registered("AddonA"), "Registered is true for an addon that reached Register")
check(ForeverCore.Registered("ForeverCore"), "and for core itself")
check(not ForeverCore.Registered("NoSuchAddon"), "and false for a name that never did")
check(A.Report ~= B.Report, "each addon has its own report window")
check(A.MapCanvas ~= B.MapCanvas, "and its own map markers")

-- An error is attributed by the exact folder its stack names.
local ok = A.SafeCall("A borrowed error", function()
	error("Interface/AddOns/AddonA/Core.lua:1: borrow failed")
end)
check(ok == false, "a failing SafeCall returns false")
equal(#A.CaughtErrors(), 1, "AddonA keeps its own error")
equal(#B.CaughtErrors(), 0, "AddonB never sees it")
equal(#ForeverCore.Register("ForeverCore").CaughtErrors(), 0, "and neither does ForeverCore")

-- An error outside SafeCall goes through the one handler to the addon its stack names.
env.errorHandler("Interface/AddOns/AddonB/Core.lua:2: unwrapped")
equal(#B.CaughtErrors(), 1, "the one handler attributes an unwrapped error to AddonB")
equal(#A.CaughtErrors(), 1, "and leaves AddonA alone")

-- A blocked action names the addon the client blamed.
local blocked = created[1]
for _, frame in ipairs(created) do
	if frame.events and frame.events.ADDON_ACTION_BLOCKED then
		blocked = frame
		break
	end
end
check(blocked.events.ADDON_ACTION_BLOCKED == true, "SafeCall installs the one action-blocked frame")
blocked.scripts.OnEvent(blocked, "ADDON_ACTION_BLOCKED", "AddonB", "SetPoint")
local found = false
for _, entry in ipairs(B.CaughtErrors()) do
	if entry.kind == "blocked" and entry.message:find("SetPoint", 1, true) then
		found = true
	end
end
check(found, "a blocked action lands in the blamed addon's journal")
equal(#A.CaughtErrors(), 1, "and not in the other addon's")

-- A wrapped failure belongs to the addon that wrapped the call: every such stack also runs through ForeverCore's
-- SafeCall, so matching folders would file it under ForeverCore and any addon it passed through.
local beforeA, beforeB = #A.CaughtErrors(), #B.CaughtErrors()
local beforeCore = #ForeverCore.Register("ForeverCore").CaughtErrors()
B.SafeCall("borrowed call", function()
	error("Interface/AddOns/AddonA/Core.lua:3: borrowed failure")
end)
equal(#B.CaughtErrors(), beforeB + 1, "the error lands in the addon that wrapped the call")
equal(#A.CaughtErrors(), beforeA, "not in another addon its message names")
equal(#ForeverCore.Register("ForeverCore").CaughtErrors(), beforeCore, "nor in ForeverCore")

-- The report header names the addon and its version.
local header = A.Report.Text({})
check(header:find("AddonA 9.9.9", 1, true) ~= nil, "the report names AddonA and its version")
check(header:find("AddonB", 1, true) == nil, "and not another addon")

-- One tracker host, shared by every addon, so its scale is one setting.
local host = ForeverCore.TrackerHost
check(host ~= nil, "there is one tracker host")
check(rawequal(host, ns.TrackerHost), "and ForeverCore publishes it")
host.SetScale(1.25)
equal(host.GetScale(), 1.25, "the scale is one value")
check(A.TrackerHost == nil and B.TrackerHost == nil, "no addon owns a second host")
check(rawequal(ForeverCore.TrackerHost, host), "both addons read the same host")

-- The migration copies the first legacy tracker table offered, once.
local legacy = widget("Frame")
legacy.legacySettings = { scale = 1.5, attached = false, locked = true, x = 100, y = -200, backdropOpacity = 0.5 }
host.Attach(legacy)
local settings = env.ForeverCoreDB.trackerHost
equal(settings.scale, 1.5, "the legacy scale is copied")
equal(settings.attached, false, "the legacy attachment is copied")
equal(settings.locked, true, "the legacy Lock is copied")
equal(settings.x, 100, "the legacy x is copied")
equal(settings.y, -200, "the legacy y is copied")
equal(settings.backdropOpacity, 0.5, "the legacy backdrop is copied")
equal(settings.migrated, true, "the copy is marked done")
local later = widget("Frame")
later.legacySettings = { scale = 0.5, attached = true }
host.Attach(later)
equal(env.ForeverCoreDB.trackerHost.scale, 1.5, "a later offer changes nothing")

-- An attached legacy table's spot is dropped, and a place the store already has is kept.
env.ForeverCoreDB.trackerHost = { placement = "left" }
local attachedLegacy = widget("Frame")
attachedLegacy.legacySettings = { scale = 0.8, attached = true, x = 7, y = -7 }
host.Attach(attachedLegacy)
settings = env.ForeverCoreDB.trackerHost
equal(settings.placement, "left", "a legacy offer keeps the store's place")
equal(settings.x, nil, "an attached legacy spot is not copied")
equal(settings.scale, 0.8, "but its scale is")

print(("api_spec: %d checks passed"):format(checks))

check(type(ForeverCore.Open) == "function", "Open is published")
check(ForeverCore.Journey == nil, "Journey is gone")

local published = ForeverCore.APIKit.Addons()
equal(#published, 1, "core publishes its own API")
equal(published[1].name, "ForeverCore", "under its own name")
equal(published[1].version, ForeverCore.API, "with the interface number as its version")
equal(published[1].minor, ForeverCore.minor, "and the core minor")
equal(type(ForeverCore.API), "number", "ForeverCore.API stays a number")
check(published[1].api.Registered("Nobody") == false, "its Registered answers like ForeverCore.Registered")
check(published[1].api.Open == ForeverCore.Open, "and it publishes Open")
