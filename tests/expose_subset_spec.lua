-- Expose.lua is the last file the TOC loads. A consumer's spec can load core's files without UI/Credits.lua, so the
-- subset must still publish ForeverCore, with Credits nil because the page never loaded.
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

-- The fake client, shared with api_spec.lua, so both specs run the files against the same stub.
local FakeClient = dofile("tests/fake_client.lua")

-- The TOC's Lua files, in order, the way the client loads them, minus UI/Credits.lua.
local Toc = dofile(".agents/skills/wow-forever-addon/tooling/forever_sim/toc.lua")
local subset = {}
local skipped = false
for _, entry in ipairs(Toc.files(".", "ForeverCore.toc")) do
	if entry.kind == "lua" then
		if entry.path == "UI/Credits.lua" then
			skipped = true
		else
			subset[#subset + 1] = entry.path
		end
	end
end
check(skipped, "the TOC loads UI/Credits.lua, so the subset is the load with that one file left out")
check(subset[#subset] == "Expose.lua", "Expose.lua still loads last")

local env = FakeClient.new()
local ns = {}
for _, path in ipairs(subset) do
	-- Core's own quest list needs the full native tracker template, which this fake client does not build. The tracker
	-- host has already captured its native frame, so hiding it here only skips that optional section.
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
check(type(ForeverCore) == "table", "Expose.lua runs without UI/Credits.lua and publishes ForeverCore")
equal(ForeverCore.API, 1, "the interface version is 1")
check(type(ForeverCore.Register) == "function", "Register is still the per-addon factory")
check(ns.CreditsPage == nil, "the page never loaded")
check(ForeverCore.Credits == nil, "ForeverCore.Credits is nil, because the page is what publishes it")
check(type(ns.Credits) == "table", "Data/Credits.lua still loads core's own generated rows")

print(("expose_subset_spec: %d checks passed"):format(checks))
