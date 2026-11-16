-- The installed-but-unregistered diagnostic (core#509): `/fcore report` must identify a Forever addon the client
-- installed but which never registered, show its versions, load/dependency state and first captured error, and point
-- at the client error frame when ForeverCore never saw one. The tracker debug fallthrough stays for unknown commands.
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

local env = FakeClient.new()
local ns = {}
for _, entry in ipairs(Toc.files(".", "ForeverCore.toc")) do
	if entry.kind == "lua" then
		-- Core's own quest list needs the full native tracker template this fake client does not build.
		local native = env.ObjectiveTrackerFrame
		if entry.path == "UI/TrackerQuests.lua" then
			env.ObjectiveTrackerFrame = nil
		end
		local chunk = assert(loadfile(entry.path), entry.path)
		setfenv(chunk, env)
		chunk("ForeverCore", ns)
		env.ObjectiveTrackerFrame = native
	end
end
local ForeverCore = assert(env.ForeverCore, "the TOC publishes ForeverCore")

-- An installed consumer that never reached Register, and one that did. The client sees the first as not loaded.
local names = { "AddonA", "AddonB", "ForeverCore" }
local metadata = {
	AddonA = {
		Version = "1.2.3",
		["X-Forever-Core"] = "v1.12.1",
		Dependencies = "ForeverCore",
		OptionalDeps = "Questie",
	},
	AddonB = { Version = "0.9.0", ["X-Forever-Core"] = "v1.12.0", Dependencies = "ForeverCore" },
	ForeverCore = { Version = "1.12.1" },
}
env.C_AddOns = {
	GetNumAddOns = function()
		return #names
	end,
	GetAddOnInfo = function(index)
		if type(index) == "number" then
			return names[index]
		end
		return index, index, "", index ~= "AddonA", index == "AddonA" and "DEP_MISSING" or nil
	end,
	GetAddOnMetadata = function(name, key)
		return metadata[name] and metadata[name][key] or nil
	end,
	IsAddOnLoaded = function(name)
		return name == "AddonB"
	end,
	GetAddOnDependencies = function(name)
		if name == "AddonA" then
			return "MissingCoreDependency"
		end
		return "ForeverCore"
	end,
	GetAddOnEnableState = function(name)
		return name == "AddonA" and 0 or 1
	end,
}

local B = ForeverCore.Register("AddonB")
B.RecordError("startup", "B failed to initialize")

-- A registered copy of the loader is visible to the report even if it never booted.
local candidate = env.ForeverCoreLoader.Begin("AddonA", 1012001, "digest-a")
candidate:Define(function() end)

local printed = {}
env.print = function(text)
	printed[#printed + 1] = tostring(text)
end
local function run(command)
	printed = {}
	env.SlashCmdList.FOREVERCORE(command)
	return table.concat(printed, "\n")
end

local debugCalls = 0
ForeverCore.TrackerHost.Debug = function()
	debugCalls = debugCalls + 1
	return "tracker debug"
end

local output = run("report AddonA")
equal(debugCalls, 0, "report does not fall through to the tracker debug")
check(output:find("AddonA 1.2.3", 1, true) ~= nil, "the unregistered addon and its installed version are named")
check(output:find("Not loaded", 1, true) ~= nil, "its startup state is named")
check(output:find("core pin: v1.12.1", 1, true) ~= nil, "the core version it bundles is named")
check(output:find("Requires: MissingCoreDependency", 1, true) ~= nil, "its dependency is named")
check(output:find("scriptErrors 1", 1, true) ~= nil, "it points at the client error frame")
check(output:find("Loadable: false; reason: DEP_MISSING", 1, true), "the client's exact refusal reason is included")
check(output:find("Core copies:", 1, true) ~= nil, "the installed core copies are listed")
check(output:find("AddonA: build 1012001", 1, true) ~= nil, "with the registered build")
check(output:find("Core: 1.12.1", 1, true) ~= nil, "the report names the running core version")

output = run("report AddonB")
check(output:find("AddonB 0.9.0: Registered", 1, true) ~= nil, "a registered addon is reported registered")
check(output:find("First error: B failed to initialize", 1, true) ~= nil, "its first captured error is shown")
equal(debugCalls, 0, "a named report still does not reach the tracker debug")

output = run("report")
check(output:find("AddonA 1.2.3", 1, true) ~= nil, "an unfocused report lists the unregistered addon")
check(output:find("AddonB 0.9.0", 1, true) ~= nil, "and the registered one")

-- The runtime build comes from the elected copy, not an unrelated standalone addon version.
env.ForeverCoreLoader.Selected = function()
	return { mode = "elected", folder = "AddonB", build = 1023004 }
end
output = run("report AddonB")
check(output:find("Core: 1.23.4; API 2", 1, true), "the report identifies the elected runtime version")

-- Every shipped locale translates each diagnostic phrase with the same placeholders.
local english = ns.L
for _, locale in ipairs({ "deDE", "esES", "esMX", "frFR", "koKR", "ptBR", "ruRU", "zhCN", "zhTW" }) do
	ns.L = setmetatable({}, getmetatable(english))
	env.GetLocale = function()
		return locale
	end
	setfenv(assert(loadfile("Locales/" .. locale .. ".lua")), env)("ForeverCore", ns)
	check(ns.L["ForeverCore startup report"] ~= "ForeverCore startup report", locale .. " translates the report title")
	for _, phrase in ipairs({
		"Core: %s; API %s",
		"Runtime: %s copy %s",
		"Runtime error: %s",
		"Standalone runtime",
		"Core copies:",
		"Rejected",
		"Sealed",
		"Unsealed",
		"%s: build %s, %s",
		'No installed Forever addon named "%s".',
		"No installed Forever addons found.",
		"Enable ForeverCore or a Forever addon in AddOns if /fcore is unavailable, then /reload and read Lua errors.",
		"Installed Forever addons:",
		"Registered",
		"Loaded but not registered",
		"Not loaded",
		"Load: %s; enabled: %s; core pin: %s",
		"Requires: %s; optional: %s",
		"Loadable: %s; reason: %s",
		"First error: %s",
		"No error captured. Use /console scriptErrors 1, then /reload and read the first error naming %s.",
		"Callback error: %s",
		"Login error: %s",
		"Copy %s: %s",
	}) do
		local translated = rawget(ns.L, phrase)
		check(type(translated) == "string", locale .. " has diagnostic phrase: " .. phrase)
		local function placeholders(text)
			local found = {}
			for token in text:gmatch("%%[sd]") do
				found[#found + 1] = token
			end
			return table.concat(found)
		end
		equal(placeholders(translated), placeholders(phrase), locale .. " preserves placeholders")
	end
	check(run("report AddonA"):find(ns.L["ForeverCore startup report"], 1, true), locale .. " is used by the command")
end
ns.L = english

-- With nothing installed, the answer must not promise that this command can run when core itself is missing.
names = {}
output = run("report")
check(output:find("/fcore is unavailable", 1, true) ~= nil, "the no-addon report describes the core-missing evidence")
check(output:find("ForeverCore or a Forever addon in AddOns", 1, true) ~= nil, "and names the AddOns check")

-- Existing command behaviour: quests toggles the list, an unknown word still prints the tracker diagnostic.
local toggled = 0
ForeverCore.TrackerQuests.Toggle = function()
	toggled = toggled + 1
end
run("quests")
equal(toggled, 1, "/fcore quests still toggles the quest list")
equal(run("other"), "tracker debug", "an unknown command keeps the tracker debug fallthrough")

print(("startup_diagnostic_spec: %d checks passed"):format(checks))
