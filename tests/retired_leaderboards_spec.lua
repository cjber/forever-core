-- The retired Forever Leaderboards and peer stats shim: an older addon release still calls these members while it
-- loads, so they answer with an empty board or a no-op. Nothing is stored, no prefix is registered and nothing sends.
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
local env, created = FakeClient.new()

-- No core file may register an addon-message prefix or send one, including the retired shim.
local prefixes, sent = {}, {}
env.C_ChatInfo = {
	RegisterAddonMessagePrefix = function(prefix)
		prefixes[#prefixes + 1] = prefix
	end,
	SendAddonMessage = function(...)
		sent[#sent + 1] = { ... }
		return 0
	end,
}

local ns = {}
for _, entry in ipairs(Toc.files(".", "ForeverCore.toc")) do
	if entry.kind == "lua" then
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

local core = env.ForeverCore
check(type(core) == "table", "the TOC publishes ForeverCore")
check(type(core.Leaderboards) == "table", "ForeverCore.Leaderboards is still there for older releases")
check(type(core.PeerStats) == "table", "ForeverCore.PeerStats is still there for older releases")

-- The exact load-time calls Shortest Path Forever v1.33.1 makes.
local boards = core.Leaderboards
boards:Register("spf", {
	title = "Shortest Path Forever",
	board = function()
		return { { name = "Someone", value = 1 } }
	end,
	revision = function()
		return 1
	end,
})
boards:Open("spf")
boards:Select("spf")
boards:Toggle()
equal(#boards:Boards(), 0, "no board is registered")
equal(#boards:Overall("week"), 0, "there is no overall board")
equal(boards:Standing("Someone", "week"), nil, "nobody has a standing")

local peer = core.PeerStats.New({
	addon = "spf",
	db = function()
		return {}
	end,
	snapshot = function()
		return { { metric = "routes", subject = "all", value = 1 } }
	end,
})
equal(#peer:Shared(), 0, "no shared rows")
equal(#peer:Board("routes", "all", 1), 0, "no board rows")
equal(#peer:WeekBoard("routes", "all", 1), 0, "no weekly board rows")
equal(peer:Revision(), 0, "nothing has changed")
equal(peer:IsEnabled(), false, "sharing is off")
peer:Sync()
peer:SetEnabled(true)
peer:Cancel()
peer:Retire()
peer:Receive("WFAStats", "1|spf|routes|all|1|1", "GUILD", "Someone")
peer:RecordSent({})
equal(type(core.PeerStats.Listen("fieldguide", {})), "table", "a reader is inert rather than nil")

equal(#prefixes, 0, "no addon message prefix is registered")
equal(#sent, 0, "nothing is sent to other players")
for _, frame in ipairs(created) do
	check(not (frame.events and frame.events.CHAT_MSG_ADDON), "nothing listens for addon messages")
end

print(("retired_leaderboards_spec: %d checks passed"):format(checks))
