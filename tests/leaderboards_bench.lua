-- Bench for the leaderboards data path: 1,000 realm messages through PeerStats:Receive, then 1,000 unit tooltip
-- lookups through the window's data half. Run from the repo root: luajit -joff tests/leaderboards_bench.lua
local harness = dofile("tests/leaderboards_harness.lua")
local Client, Load = harness.Client, harness.Load
local Create = harness.Create

local MESSAGE_COUNT = 1000
local TOOLTIP_COUNT = 1000
-- Core/PeerStats.lua MAX_PEERS: the store keeps 100 peers, so later distinct senders are refused by design.
local STORE_CAP = 100

local PREFIX = "WFAStats"
local WIRE_VERSION = "1"
local ADDON = "agf"
local METRIC = "total"
local SUBJECT = "all"

local function report(name, calls, seconds)
	local ms = seconds * 1000
	print(("%s %d calls %.3f ms %.3f us/call"):format(name, calls, ms, ms * 1000 / calls))
end

Client()
local env = harness.env
-- PeerStats reads GetTime for the per-sender rate bucket; the leaderboards harness does not stub it.
env.GetTime = function()
	return 1000
end

local api, ns = Load()
setfenv(assert(loadfile("Core/PeerStats.lua")), env)("ForeverCore", ns)

local db = {}
local peers = ns.PeerStats.New({
	addon = ADDON,
	enabled = function()
		return true
	end,
	db = function()
		return db
	end,
	metrics = { [METRIC] = { subject = SUBJECT } },
})
assert(peers ~= nil, "PeerStats.New returned an instance")

-- Part 1: one valid wire v1 message per sender, alternating the two channels the instance sends on.
local now = harness.serverTime
local results = {}
local started = os.clock()
for index = 1, MESSAGE_COUNT do
	local sender = "Name" .. index .. "-SomeRealm"
	local channel = index % 2 == 0 and "PARTY" or "GUILD"
	-- Core/PeerStats.lua Instance:Sync builds exactly this payload with table.concat.
	local payload = table.concat({ WIRE_VERSION, ADDON, METRIC, SUBJECT, index, now }, "|")
	results[index] = { peers:Receive(PREFIX, payload, channel, sender) }
end
local receiveSeconds = os.clock() - started

local accepted = 0
for index = 1, MESSAGE_COUNT do
	local ok, why = results[index][1], results[index][2]
	if ok then
		accepted = accepted + 1
	else
		assert(
			why == "rate" or why == "peers",
			("message %d was refused for %s, which is not a by-design refusal"):format(index, tostring(why))
		)
	end
end
assert(accepted == STORE_CAP, ("expected the store cap of %d accepted, got %d"):format(STORE_CAP, accepted))
print(("realm_messages accepted %d of %d messages"):format(accepted, MESSAGE_COUNT))
report("realm_messages", MESSAGE_COUNT, receiveSeconds)

-- Part 2: two boards over that PeerStats data, then a hover per lookup. Odd calls name a stored peer, even calls name
-- a player no board has heard.
local function boardSpec(title, weekly)
	return {
		title = title,
		metric = title,
		icon = harness.ICON,
		board = function()
			if weekly then
				return peers:WeekBoard(METRIC, SUBJECT, 0, now)
			end
			return peers:Board(METRIC, SUBJECT, 0, now)
		end,
	}
end
assert(api:Register("total", boardSpec("Total", false)), "the total board registers")
assert(api:Register("weekly", boardSpec("Weekly", true)), "the weekly board registers")

local tokens = {}
for index = 1, TOOLTIP_COUNT do
	local token = "bench" .. index
	local name
	if index % 2 == 1 then
		name = "Name" .. (math.floor((index - 1) / 2) % STORE_CAP + 1)
	else
		name = "Nobody" .. index
	end
	harness.unitNames[token] = { name, "SomeRealm" }
	tokens[index] = token
end

local tooltip = Create("GameTooltip")
tooltip.unit = tokens[1]
api:AddTooltip(tooltip)
tooltip.lines = nil

local lineCounts = {}
started = os.clock()
for index = 1, TOOLTIP_COUNT do
	tooltip.lines = nil
	tooltip.unit = tokens[index]
	api:AddTooltip(tooltip)
	local lines = rawget(tooltip, "lines")
	lineCounts[index] = lines and #lines or 0
end
local tooltipSeconds = os.clock() - started

for index = 1, TOOLTIP_COUNT do
	if index % 2 == 1 then
		assert(lineCounts[index] >= 1, ("known unit %d drew no tooltip line"):format(index))
	else
		assert(lineCounts[index] == 0, ("unknown unit %d drew a tooltip line"):format(index))
	end
end
report("tooltip_lookups", TOOLTIP_COUNT, tooltipSeconds)
