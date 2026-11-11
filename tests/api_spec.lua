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
	-- Core's own quest list needs the full native tracker template, which this fake client does not build. The
	-- tracker host has already captured its native frame, so hiding it here only skips that optional section.
	local native = env.ObjectiveTrackerFrame
	if path == "UI/TrackerQuests.lua" then
		env.ObjectiveTrackerFrame = nil
	end
	local chunk = assert(loadfile(path), path)
	setfenv(chunk, env)
	chunk("ForeverCore", ns)
	env.ObjectiveTrackerFrame = native
end
local ForeverCore = env.ForeverCore
check(type(ForeverCore) == "table", "the TOC publishes ForeverCore")
equal(ForeverCore.API, 1, "the interface version is 1")
check(type(ForeverCore.Register) == "function", "Register is the per-addon factory")
check(type(ForeverCore.ContextMenu) == "function", "ContextMenu is the shared menu")
check(ForeverCore.ContextMenu == ns.ContextMenu, "and it is the module UI/ContextMenu.lua built")
check(rawequal(env.ForeverTrackerHost, ns.TrackerHost), "ForeverTrackerHost publishes core's one host")
check(env.ForeverFamily == nil, "ForeverFamily is gone")
check(env.ForeverLeaderboards == nil, "ForeverLeaderboards is gone")
check(env.ForeverPeerStats == nil, "ForeverPeerStats is gone")
check(env.ForeverQuestLogTabs == nil, "ForeverQuestLogTabs is gone")
check(ForeverCore.ProfessionTabs == ns.ProfessionTabs, "ForeverCore publishes the ProfessionTabs module")
check(type(ForeverCore.Credits) == "table", "ForeverCore publishes the Credits module")
equal(#ForeverCore.Credits.Players(), 12, "core's own Data/Credits.lua is registered under Forever Core")
check(ForeverCore.Credits.Line("Forever Core") ~= nil, "and its one-line thanks reads")
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

print(("api_spec: %d checks passed"):format(checks))
