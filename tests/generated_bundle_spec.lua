-- Loads producer outputs, including the eager XML declarations. The fake client
-- verifies Lua lifecycle and declaration ownership, not native template rendering.
if not arg[1] then
	assert(os.execute("python3 tools/test_build_embedded_core.py GeneratedBundleTests.test_runtime") == 0)
	return
end
local root = arg[1]
local FakeClient = dofile("tests/fake_client.lua")
local Toc = dofile(".agents/skills/wow-forever-addon/tooling/forever_sim/toc.lua")
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end
local function clone(value)
	if type(value) ~= "table" then
		return value
	end
	local copy = {}
	for key, item in pairs(value) do
		copy[key] = clone(item)
	end
	return copy
end
local function session(order, saved, newer)
	local env, frames = FakeClient.new()
	-- Native tracker rendering is outside this harness. Do not manufacture its
	-- frames or methods just to make a generated package pass.
	env.ObjectiveTrackerFrame = nil
	local function event(name, addon)
		local listeners = {}
		for _, frame in ipairs(frames) do
			if frame.events[name] then
				listeners[#listeners + 1] = frame
			end
		end
		for _, frame in ipairs(listeners) do
			frame.scripts.OnEvent(frame, name, addon)
		end
	end
	local declarations = {}
	for _, folder in ipairs(order) do
		local host = {}
		local path = root .. (newer and "/newer" or "") .. "/" .. folder
		for _, file in ipairs(Toc.files(path, folder .. ".toc")) do
			if file.kind == "lua" then
				setfenv(assert(loadfile(file.path)), env)(folder, host)
			else
				for _, template in ipairs(Toc.templates(file.path)) do
					check(not declarations[template.name], "no duplicate eager XML template")
					check(template.inherits == "ObjectiveTrackerLineTemplate", "native base template preserved")
					declarations[template.name] = folder
				end
			end
		end
		check(env.ForeverCore == nil, "TOC definitions never boot a runtime")
		check(env.ConsumerStarts == nil, "consumer initialization waits for readiness")
		-- The client restores account globals after files and before ADDON_LOADED.
		env[folder .. "DB"] = saved and clone(saved[folder]) or nil
		event("ADDON_LOADED", folder)
		check(env.ForeverCore == nil, "own ADDON_LOADED cannot activate early")
	end
	event("VARIABLES_LOADED")
	event("PLAYER_LOGIN")
	local loader = env.ForeverCoreLoader
	check(loader.Error() == nil, "boot: " .. tostring(loader.Error()))
	check(loader.CallbackError() == nil, "consumer startup: " .. tostring(loader.CallbackError()))
	check(loader.LoginError() == nil, "login: " .. tostring(loader.LoginError()))
	local hasStandalone = false
	for _, folder in ipairs(order) do
		hasStandalone = hasStandalone or folder == "ForeverCore"
	end
	check((env.ConsumerStarts or 0) == #order - (hasStandalone and 1 or 0), "each generated ready entry runs once")
	local winner = #order == 1 and order[1] or "ConsumerB"
	if newer and hasStandalone then
		winner = "ForeverCore"
	end
	check(loader.Selected().mode == (winner == "ForeverCore" and "standalone" or "elected"), "selected mode")
	check(loader.Selected().folder == winner, "newest schema-compatible build wins independently of load order")
	check((env.ForeverCoreDB ~= nil) == hasStandalone, "standalone SavedVariables ownership")
	check(#loader.Rejections() == 0, "no rejected registration, offer or seal")
	local expectedRoot = "Interface\\AddOns\\" .. winner .. (winner == "ForeverCore" and "" or "\\Libs\\ForeverCore")
	check(loader.Selected().root == expectedRoot, "selected installed media root")
	check(env.ForeverCore.Art.Marker(1) == expectedRoot .. "\\media\\Numbers\\1", "marker uses selected package")
	local template = env.ForeverCore.TrackerLine.template
	check(declarations[template] == winner, "public template belongs to elected package")
	for _, folder in ipairs(order) do
		check(type(env[folder .. "DB"]) == "table", "first-install account table initialized")
		if folder ~= "ForeverCore" then
			check(type(env[folder .. "DB"].ForeverCoreStore) == "table", "offered account table receives mirror")
			check(env[folder .. "DB"].ForeverCoreStore == loader.Namespace().Store(), "mirror is the live store")
		end
	end
	return env, loader
end
for _, order in ipairs({ { "ConsumerA", "ConsumerB" }, { "ConsumerB", "ConsumerA" } }) do
	local env, loader = session(order)
	loader.Namespace().Store().trackerHost.scale = 1.37
	local saved = { ConsumerA = clone(env.ConsumerADB), ConsumerB = clone(env.ConsumerBDB) }
	local _, reloaded = session(order, saved)
	check(reloaded.Namespace().Store().trackerHost.scale == 1.37, "settings survive reload through account mirrors")
	for _, survivor in ipairs(order) do
		local remaining, afterRemoval = session({ survivor }, saved)
		check(afterRemoval.Namespace().Store().trackerHost.scale == 1.37, "settings survive sibling removal")
		local removed = survivor == "ConsumerA" and "ConsumerB" or "ConsumerA"
		check(remaining[removed .. "DB"] == nil, "removed addon's globals are not loaded")
	end
end
-- All six orders exercise a lower and a higher standalone build against two
-- eligible embedded builds. No ADDON_LOADED may activate any generated copy.
for _, order in ipairs({
	{ "ForeverCore", "ConsumerA", "ConsumerB" },
	{ "ForeverCore", "ConsumerB", "ConsumerA" },
	{ "ConsumerA", "ForeverCore", "ConsumerB" },
	{ "ConsumerB", "ForeverCore", "ConsumerA" },
	{ "ConsumerA", "ConsumerB", "ForeverCore" },
	{ "ConsumerB", "ConsumerA", "ForeverCore" },
}) do
	session(order)
	session(order, nil, true)
end
session({ "ForeverCore" }, nil, true)
-- An already published facade makes OnReady synchronous. It still cannot start
-- the consumer until that consumer's own SavedVariables have been restored.
do
	local env, frames = FakeClient.new()
	local registrations = 0
	env.ForeverCore = {
		API = 2,
		TrackerLine = { SetInteractive = function() end },
		Register = function()
			registrations = registrations + 1
			check(env.ConsumerADB.existing == true, "early facade sees restored account settings")
			return {}
		end,
	}
	local host = {}
	local path = root .. "/ConsumerA"
	for _, file in ipairs(Toc.files(path, "ConsumerA.toc")) do
		if file.kind == "lua" then
			setfenv(assert(loadfile(file.path)), env)("ConsumerA", host)
		end
	end
	check(registrations == 0, "legacy readiness does not initialize before SavedVariables")
	check(env.ConsumerADB == nil, "legacy readiness does not create a premature account global")
	env.ConsumerADB = { existing = true }
	for _, frame in ipairs(frames) do
		if frame.events.ADDON_LOADED then
			frame.scripts.OnEvent(frame, "ADDON_LOADED", "UnrelatedAddon")
			check(registrations == 0, "unrelated ADDON_LOADED does not initialize consumer")
			frame.scripts.OnEvent(frame, "ADDON_LOADED", "ConsumerA")
		end
	end
	check(registrations == 1, "legacy consumer initializes once after own ADDON_LOADED")
end
-- A facade outside the declared API2 contract is refused visibly, never treated
-- as a compatible legacy runtime or replaced with a second active runtime.
do
	local env = FakeClient.new()
	local legacy = {
		API = 1,
		Register = function()
			error("must not initialize")
		end,
	}
	env.ForeverCore = legacy
	local host = {}
	for _, file in ipairs(Toc.files(root .. "/ConsumerA", "ConsumerA.toc")) do
		if file.kind == "lua" then
			setfenv(assert(loadfile(file.path)), env)("ConsumerA", host)
		end
	end
	check(env.ForeverCore == legacy, "unsupported existing facade is never overwritten")
	check(env.ConsumerStarts == nil, "unsupported API cannot initialize consumer")
	check(
		string.find(env.ForeverCoreLoader.CallbackError() or "", "incompatible ForeverCore API", 1, true),
		"unsupported legacy API is reported"
	)
end
-- Real unwrapped canonical source is the supported API2 legacy facade fixture.
-- It owns its already-running runtime; embedded wrappers must remain inert.
for _, order in ipairs({
	{ "Legacy", "ConsumerA", "ConsumerB" },
	{ "ConsumerA", "Legacy", "ConsumerB" },
	{ "ConsumerA", "ConsumerB", "Legacy" },
}) do
	local env, frames = FakeClient.new()
	env.ObjectiveTrackerFrame = nil
	local function event(name, addon)
		local listeners = {}
		for _, frame in ipairs(frames) do
			if frame.events[name] then
				listeners[#listeners + 1] = frame
			end
		end
		for _, frame in ipairs(listeners) do
			frame.scripts.OnEvent(frame, name, addon)
		end
	end
	local facade
	for _, item in ipairs(order) do
		local legacy = item == "Legacy"
		local folder = legacy and "ForeverCore" or item
		local path = legacy and "." or root .. "/" .. folder
		local host = {}
		for _, file in ipairs(Toc.files(path, folder .. ".toc")) do
			if file.kind == "lua" then
				setfenv(assert(loadfile(file.path)), env)(folder, host)
			end
		end
		env[folder .. "DB"] = { existing = true }
		event("ADDON_LOADED", folder)
		if legacy then
			facade = env.ForeverCore
		end
	end
	event("PLAYER_LOGIN")
	check(env.ForeverCore == facade, "legacy public facade is retained unchanged")
	check(env.ForeverCore.API == 2, "real legacy fixture has the supported public API")
	check(env.ForeverCoreLoader.Namespace() == nil, "no second runtime boots beside legacy")
	check(env.ForeverCoreLoader.Selected().mode == "legacy", "legacy coexistence is explicit")
	check(env.ForeverCoreLoader.CallbackError() == nil, "real legacy startup succeeds")
	check(env.ConsumerStarts == 2, "both consumers initialize against real legacy public facade")
	check(#env.ForeverCoreLoader.Rejections() == 0, "legacy wrappers seal without false assertion")
end
-- The bridge release carries ForeverCoreDB across the switch: the tracker column's position, its Lock and its
-- options survive installing an embedded consumer beside the standalone, then removing either one, in every order.
-- The real unwrapped source is the standalone; its login writes the mirror into each offered consumer table, and a
-- later session reconciles whichever tables the client still loads.
local function bridgeSession(order, saved)
	local env, frames = FakeClient.new()
	env.ObjectiveTrackerFrame = nil
	local function event(name, addon)
		local listeners = {}
		for _, frame in ipairs(frames) do
			if frame.events[name] then
				listeners[#listeners + 1] = frame
			end
		end
		for _, frame in ipairs(listeners) do
			frame.scripts.OnEvent(frame, name, addon)
		end
	end
	for _, item in ipairs(order) do
		local legacy = item == "Legacy"
		local folder = legacy and "ForeverCore" or item
		local host = {}
		for _, file in ipairs(Toc.files(legacy and "." or root .. "/" .. folder, folder .. ".toc")) do
			if file.kind == "lua" then
				setfenv(assert(loadfile(file.path)), env)(folder, host)
			end
		end
		env[folder .. "DB"] = saved and clone(saved[folder .. "DB"]) or nil
		event("ADDON_LOADED", folder)
	end
	event("VARIABLES_LOADED")
	event("PLAYER_LOGIN")
	local loader = env.ForeverCoreLoader
	check(loader.Error() == nil and loader.CallbackError() == nil, "bridge session boots cleanly")
	return env, loader
end
local function snapshot(env)
	local out = {}
	for _, name in ipairs({ "ForeverCoreDB", "ConsumerADB", "ConsumerBDB" }) do
		out[name] = clone(rawget(env, name))
	end
	return out
end
local function trackerHost(env, loader)
	-- The standalone alone never meets the loader: no consumer begins a copy, so nothing is selected.
	local selected = loader.Selected()
	if selected == nil or selected.mode == "legacy" then
		return env.ForeverCoreDB.trackerHost
	end
	return loader.Namespace().Store().trackerHost
end
local function sameColumn(settings, expected, label)
	for key, value in pairs(expected) do
		check(settings[key] == value, label .. ": trackerHost." .. key .. " carried over")
	end
end
local column = { attached = false, x = 412, y = -230, locked = true, scale = 1.2, backdropOpacity = 0.4 }
for _, order in ipairs({
	{ "Legacy", "ConsumerA", "ConsumerB" },
	{ "ConsumerA", "Legacy", "ConsumerB" },
	{ "ConsumerA", "ConsumerB", "Legacy" },
}) do
	-- Before the update: the standalone alone, with the player's column saved.
	local before = bridgeSession({ "Legacy" }, { ForeverCoreDB = { trackerHost = clone(column) } })
	-- Update: the bridge consumers install beside the standalone.
	local env, loader = bridgeSession(order, snapshot(before))
	check(loader.Selected().mode == "legacy", "the installed standalone keeps running during the bridge")
	sameColumn(trackerHost(env, loader), column, "update")
	for _, consumer in ipairs({ "ConsumerA", "ConsumerB" }) do
		sameColumn(env[consumer .. "DB"].ForeverCoreStore.trackerHost, column, consumer .. " mirror")
	end
	local bridged = snapshot(env)
	-- Uninstall the standalone: the embedded runtime reads the mirrors.
	for _, consumers in ipairs({ { "ConsumerA", "ConsumerB" }, { "ConsumerB", "ConsumerA" }, { "ConsumerA" } }) do
		local embedded, elected = bridgeSession(consumers, bridged)
		check(elected.Selected().mode == "elected", "an embedded copy runs once the standalone is gone")
		sameColumn(trackerHost(embedded, elected), column, "standalone removed")
	end
	-- Uninstall the consumers instead: the standalone keeps its own table.
	local alone, standalone = bridgeSession({ "Legacy" }, bridged)
	sameColumn(trackerHost(alone, standalone), column, "consumers removed")
	-- A change made while embedded survives the standalone coming back with its older, unchanged table.
	local embedded, elected = bridgeSession({ "ConsumerA", "ConsumerB" }, bridged)
	trackerHost(embedded, elected).scale = 1.5
	trackerHost(embedded, elected).locked = false
	local changed = snapshot(embedded)
	changed.ForeverCoreDB = bridged.ForeverCoreDB
	local back, reinstalled = bridgeSession(order, changed)
	sameColumn(
		trackerHost(back, reinstalled),
		{ scale = 1.5, locked = false, x = 412, y = -230 },
		"standalone reinstalled"
	)
end
-- A first install of the embedded consumer, then the standalone added later with no saved table of its own, keeps the
-- column the consumer saved.
do
	local embedded, elected = bridgeSession({ "ConsumerA" })
	for key, value in pairs(column) do
		trackerHost(embedded, elected)[key] = value
	end
	local saved = snapshot(embedded)
	local env, loader = bridgeSession({ "Legacy", "ConsumerA" }, saved)
	sameColumn(trackerHost(env, loader), column, "standalone added later")
end
-- Actual canonical files with only deDE moved before enUS must conflict before
-- any runtime chunk executes, regardless of which same-version copy loads first.
for _, order in ipairs({ { "ConsumerA", "ConsumerB" }, { "ConsumerB", "ConsumerA" } }) do
	local env, frames = FakeClient.new()
	env.GetLocale = function()
		return "deDE"
	end
	env.ObjectiveTrackerFrame = nil
	for _, folder in ipairs(order) do
		local host = {}
		for _, file in ipairs(Toc.files(root .. "/conflict/" .. folder, folder .. ".toc")) do
			if file.kind == "lua" then
				setfenv(assert(loadfile(file.path)), env)(folder, host)
			end
		end
		env[folder .. "DB"] = {}
		for _, frame in ipairs(frames) do
			if frame.events.ADDON_LOADED then
				frame.scripts.OnEvent(frame, "ADDON_LOADED", folder)
			end
		end
	end
	for _, frame in ipairs(frames) do
		if frame.events.PLAYER_LOGIN then
			frame.scripts.OnEvent(frame, "PLAYER_LOGIN")
		end
	end
	local loader = env.ForeverCoreLoader
	check(loader.Error() == "conflicting ForeverCore copies at build 1012001", "ordered graph conflict reported")
	check(loader.Selected() == nil and loader.Namespace() == nil, "neither ordered graph boots")
	check(env.ForeverCore == nil and env.ConsumerStarts == nil, "conflicting copies never publish or initialize")
	local rejected = {}
	for _, rejection in ipairs(loader.Rejections()) do
		check(rejection.reason == "tie-conflict", "graph mismatch is an election conflict")
		rejected[rejection.folder] = true
	end
	check(#loader.Rejections() == 2 and rejected.ConsumerA and rejected.ConsumerB, "both graph candidates refused")
end
print("generated bundle: " .. checks .. " checks passed")
