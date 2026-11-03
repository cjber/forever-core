-- Contract for the shared peer stats protocol and board (Core/PeerStats.lua), against a mocked client.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

-- Client mock ----------------------------------------------------------------------------------------------------
local clock, serverTime = 1000, 1700000000
local timers = {}
local sent = {}
local sendResult = 0
local inGuild, groupKind, groupSize = true, nil, 0
local frames = {}
local groupNames = {}

_G.GetTime = function()
	return clock
end
_G.GetServerTime = function()
	return serverTime
end
_G.C_Timer = {
	After = function(delay, callback)
		timers[#timers + 1] = { at = clock + delay, callback = callback, order = #timers }
	end,
}
_G.C_ChatInfo = {
	RegisterAddonMessagePrefix = function() end,
	SendAddonMessage = function(prefix, payload, channel)
		local result = type(sendResult) == "function" and sendResult(payload, channel) or sendResult
		if result == 0 or result == true then
			sent[#sent + 1] = { prefix = prefix, payload = payload, channel = channel }
		end
		return result
	end,
}
_G.IsInGuild = function()
	return inGuild
end
_G.LE_PARTY_CATEGORY_INSTANCE = 2
_G.LE_PARTY_CATEGORY_HOME = 1
_G.IsInGroup = function(category)
	if category == 2 then
		return groupKind == "INSTANCE_CHAT"
	end
	return groupKind ~= nil
end
_G.IsInRaid = function(category)
	if groupKind == "INSTANCE_CHAT" and category ~= 2 then
		return false
	end
	return groupKind == "RAID"
end
_G.GetNumGroupMembers = function(category)
	if groupKind == "INSTANCE_CHAT" and category ~= 2 then
		return 0
	end
	return groupSize
end
_G.UnitName = function(unit)
	return groupNames[unit] or "Me"
end
_G.GetNormalizedRealmName = function()
	return "MyRealm"
end
_G.CreateFrame = function()
	local frame = { events = {} }
	function frame:SetScript(_, handler)
		self.handler = handler
	end
	function frame:RegisterEvent(event)
		self.events[event] = true
	end
	function frame:UnregisterAllEvents()
		self.events = {}
	end
	frames[#frames + 1] = frame
	return frame
end

local function advance(seconds)
	local target = clock + seconds
	while true do
		local best
		for index, timer in ipairs(timers) do
			if timer.at <= target and (not best or timer.at < timers[best].at) then
				best = index
			end
		end
		if not best then
			break
		end
		local timer = table.remove(timers, best)
		clock = math.max(clock, timer.at)
		timer.callback()
	end
	clock = target
end

local function count(table_)
	local n = 0
	for _ in pairs(table_) do
		n = n + 1
	end
	return n
end

local function payloads()
	local list = {}
	for _, message in ipairs(sent) do
		list[#list + 1] = message.channel .. ":" .. message.payload
	end
	table.sort(list)
	return list
end

local function resetSent()
	for index = #sent, 1, -1 do
		sent[index] = nil
	end
end

local function fresh()
	_G.ForeverPeerStats = nil
	timers, sent, frames, groupNames = {}, {}, {}, {}
	clock, serverTime = 1000, 1700000000
	sendResult, inGuild, groupKind, groupSize = 0, true, nil, 0
	local ns = {}
	assert(loadfile("Core/PeerStats.lua"))("ForeverCore", ns)
	return ns
end

local function load(ns_)
	local ns = ns_ or {}
	assert(loadfile("Core/PeerStats.lua"))("ForeverCore", ns)
	return ns
end

local METRICS = {
	total = { subject = "all" },
	node = { subject = "numeric" },
	creature = { subject = "qualified" },
	firstkill = { subject = "numeric", first = true },
}

local function make(ns, overrides)
	local state = { enabled = true, db = {}, rows = {} }
	for key, value in pairs(overrides or {}) do
		state[key] = value
	end
	local peers = ns.PeerStats.New({
		addon = state.addon or "agf",
		enabled = function()
			return state.enabled
		end,
		db = function()
			return state.db
		end,
		snapshot = function()
			return state.rows
		end,
		metrics = METRICS,
	})
	return peers, state
end

local function wire(addon, metric, subject, value, unix)
	return table.concat({ "1", addon, metric, subject, value, unix }, "|")
end

local function recv(peers, payload, sender, channel)
	return peers:Receive("WFAStats", payload, channel or "GUILD", sender)
end

-- Receive: validation -------------------------------------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	equal(recv(peers, wire("agf", "total", "all", 5, now), "Alice-OtherRealm"), true, "valid row accepted")
	equal(state.db["Alice-OtherRealm"].total.all.value, 5, "row saved in canonical layout")
	equal(state.db["Alice-OtherRealm"].total.all.eventUnix, now, "event time saved")

	local function rejected(payload, sender, channel, reason, label)
		local ok, why = recv(peers, payload, sender or "Bob-OtherRealm", channel)
		equal(ok, false, label)
		if reason then
			equal(why, reason, label .. " reason")
		end
	end
	rejected(wire("other", "total", "all", 5, now), nil, nil, "addon", "foreign addon ignored")
	rejected(wire("agf", "total", "all", 5, now), nil, "WHISPER", "channel", "whisper rejected")
	rejected(wire("agf", "unknown", "all", 5, now), nil, nil, "metric", "unknown metric rejected")
	rejected(wire("agf", "total", "7", 5, now), nil, nil, "metric", "numeric subject on an all metric")
	rejected(wire("agf", "node", "all", 5, now), nil, nil, "metric", "all subject on a numeric metric")
	rejected(wire("agf", "node", "007", 5, now), nil, nil, "metric", "leading zero subject")
	rejected(wire("agf", "node", string.rep("9", 25), 5, now), nil, nil, "metric", "oversized subject")
	rejected(wire("agf", "creature", "12", 5, now), nil, nil, "metric", "unqualified subject")
	rejected(wire("agf", "total", "all", "-1", now), nil, nil, "value", "negative value")
	rejected(wire("agf", "total", "all", "1e3", now), nil, nil, "value", "exponent value")
	rejected(wire("agf", "total", "all", "1.5", now), nil, nil, "value", "fractional value")
	rejected(wire("agf", "total", "all", "nan", now), nil, nil, "value", "nan value")
	rejected(wire("agf", "total", "all", "inf", now), nil, nil, "value", "inf value")
	rejected(wire("agf", "total", "all", "1000000001", now), nil, nil, "value", "value above 1e9")
	rejected(wire("agf", "total", "all", "99999999999", now), nil, nil, "value", "overlong value")
	rejected(wire("agf", "total", "all", 5, now + 301), nil, nil, "value", "timestamp too far ahead")
	rejected(wire("agf", "total", "all", 5, 0), nil, nil, "value", "zero timestamp")
	rejected(wire("agf", "total", "all", 5, now) .. "|extra", nil, nil, "metric", "seventh field")
	rejected("1|agf|total|all|5", nil, nil, "metric", "missing field")
	rejected("2|agf|total|all|5|" .. now, nil, nil, "addon", "wrong version")
	rejected(wire("agf", "total", "all", 5, now) .. string.rep("x", 130), nil, nil, "payload", "oversized payload")
	rejected(42, nil, nil, "payload", "non-string payload")
	rejected(wire("agf", "total", "all", 5, now), "Bad|Name", nil, "sender", "pipe in sender")
	rejected(wire("agf", "total", "all", 5, now), "Bad\nName", nil, "sender", "control byte in sender")
	equal(
		recv(peers, wire("agf", "total", "all", 5, now), "Bob-OtherRealm"),
		true,
		"control: a valid row for Bob still works"
	)
	equal(peers:Receive("Other", wire("agf", "total", "all", 5, now), "GUILD", "Carl"), false, "wrong prefix")
	rejected(wire("agf", "total", "all", 5, now), 7, nil, "sender", "non-string sender")
	equal(count(state.db), 2, "only Alice and Bob stored after hostile input")

	-- Own name in every spelling.
	for _, name in ipairs({ "Me", "me", "Me-MyRealm", "Me-My Realm", "Me-My-Realm", "ME-myrealm" }) do
		rejected(wire("agf", "total", "all", 9, now), name, nil, "sender", "own name " .. name)
	end
	equal(
		recv(peers, wire("agf", "total", "all", 9, now), "Me-OtherRealm"),
		true,
		"own name on another realm is a peer"
	)
end

-- Receive: cumulative, stale, duplicate, out of order, first ---------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	equal(recv(peers, wire("agf", "total", "all", 5, now - 10), "Al-X"), true, "first value")
	local ok, why = recv(peers, wire("agf", "total", "all", 5, now - 10), "Al-X")
	equal(ok, false, "duplicate ignored")
	equal(why, "stale", "duplicate reason")
	equal(recv(peers, wire("agf", "total", "all", 4, now), "Al-X"), false, "lower value is stale")
	equal(recv(peers, wire("agf", "total", "all", 9, now - 20), "Al-X"), true, "higher value wins regardless of time")
	equal(recv(peers, wire("agf", "total", "all", 8, now), "Al-X"), false, "out of order lower value")
	equal(state.db["Al-X"].total.all.value, 9, "cumulative value kept")
	equal(recv(peers, wire("agf", "total", "all", 9, now), "Al-X"), true, "same value newer time refreshes")
	equal(state.db["Al-X"].total.all.eventUnix, now, "refreshed time")

	equal(recv(peers, wire("agf", "firstkill", "5", 1, now - 5), "Al-X"), true, "first record stored")
	equal(recv(peers, wire("agf", "firstkill", "5", 1, now - 1), "Al-X"), false, "later first record ignored")
	equal(recv(peers, wire("agf", "firstkill", "5", 1, now - 50), "Al-X"), true, "earlier first record replaces")
	equal(state.db["Al-X"].firstkill["5"].eventUnix, now - 50, "earliest kept")

	-- Identity collapse: one player however the name arrives.
	equal(recv(peers, wire("agf", "total", "all", 20, now), "Zed-My Realm"), true, "local realm spelled with space")
	equal(recv(peers, wire("agf", "total", "all", 21, now), "Zed"), true, "bare name is the same peer")
	equal(recv(peers, wire("agf", "total", "all", 22, now), "zed-MyRealm"), true, "case and realm collapse")
	equal(count(state.db), 2, "one Zed and one Al")
	equal(state.db.Zed.total.all.value, 22, "collapsed peer holds the best value")
end

-- Caps ----------------------------------------------------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	for index = 1, 100 do
		equal(recv(peers, wire("agf", "total", "all", index, now), "P" .. index .. "-R"), true, "peer " .. index)
	end
	local ok, why = recv(peers, wire("agf", "total", "all", 1, now), "P101-R")
	equal(ok, false, "101st peer rejected")
	equal(why, "peers", "peer cap reason")
	equal(count(state.db), 100, "peer table stays at 100")
	equal(recv(peers, wire("agf", "total", "all", 500, now), "P1-R"), true, "known peer still updates when full")

	-- A stale peer makes room.
	state.db["P2-R"].total.all.eventUnix = now - 40 * 86400
	local reload = make(load(), { db = state.db })
	equal(count(reload:Shared()) <= 100, true, "reload keeps the cap")
	equal(recv(reload, wire("agf", "total", "all", 1, now), "New-R"), true, "stale peer evicted for a new one")
	equal(state.db["P2-R"], nil, "evicted peer gone")

	-- Subjects per metric.
	local p2, s2 = make(fresh())
	for index = 1, 256 do
		equal(recv(p2, wire("agf", "node", index, 1, serverTime), "Cap-R"), true, "subject " .. index)
	end
	local over, reason = recv(p2, wire("agf", "node", 257, 1, serverTime), "Cap-R")
	equal(over, false, "257th subject rejected")
	equal(reason, "rows", "subject cap reason")
	equal(recv(p2, wire("agf", "node", 1, 2, serverTime), "Cap-R"), true, "existing subject updates at the cap")
	equal(count(s2.db["Cap-R"].node), 256, "subjects capped")
end

-- Per-sender rate ----------------------------------------------------------------------------------------------
do
	local ns = fresh()
	local peers = make(ns)
	local now = serverTime
	local accepted, limited = 0, 0
	for index = 1, 400 do
		local ok, why = recv(peers, wire("agf", "node", index, 1, now), "Flood-R")
		if ok then
			accepted = accepted + 1
		elseif why == "rate" then
			limited = limited + 1
		end
	end
	equal(accepted, 256, "burst allows a whole snapshot (rows capped at 256 subjects)")
	equal(limited > 0, true, "flood is rate limited")
	equal(recv(peers, wire("agf", "total", "all", 1, now), "Calm-R"), true, "another sender is unaffected")
	advance(5)
	equal(recv(peers, wire("agf", "total", "all", 2, now), "Flood-R"), true, "bucket refills over time")
	-- Foreign traffic does not spend this instance's budget.
	for _ = 1, 1000 do
		peers:Receive("WFAStats", wire("other", "total", "all", 1, now), "GUILD", "Calm-R")
	end
	equal(recv(peers, wire("agf", "total", "all", 3, now), "Calm-R"), true, "foreign addon rows cost nothing")
end

-- Saved state sanitization --------------------------------------------------------------------------------------
do
	local ns = fresh()
	local now = serverTime
	local db = {
		["Good-Realm"] = { total = { all = { value = 3, eventUnix = now } } },
		["good-realm"] = {
			total = { all = { value = 7, eventUnix = now - 5 } },
			node = { ["12"] = { value = 1, eventUnix = now } },
		},
		["Me"] = { total = { all = { value = 99, eventUnix = now } } },
		["Me-MyRealm"] = { total = { all = { value = 99, eventUnix = now } } },
		["Junk"] = "text",
		["Bad|Key"] = { total = { all = { value = 1, eventUnix = now } } },
		[5] = { total = { all = { value = 1, eventUnix = now } } },
		["Vals"] = {
			total = { all = { value = -1, eventUnix = now } },
			node = {
				["1"] = { value = 1.5, eventUnix = now },
				["2"] = { value = 1e12, eventUnix = now },
				["3"] = { value = 1, eventUnix = now + 10000 },
				["4"] = { value = 1, eventUnix = 0 },
				["5"] = { value = 1 / 0, eventUnix = now },
				["6"] = { value = 0 / 0, eventUnix = now },
				["7"] = "x",
				["08"] = { value = 1, eventUnix = now },
				["9"] = { value = 4, eventUnix = now },
			},
			bogus = { all = { value = 1, eventUnix = now } },
			creature = "nope",
		},
	}
	local peers = make(ns, { db = db })
	local shared = peers:Shared()
	equal(count(shared), 2, "own names, junk, bad keys dropped")
	equal(shared["Good-Realm"].total.all.value, 7, "duplicate identities merged on the best value")
	equal(shared["Good-Realm"].node["12"].value, 1, "merged peer keeps every row")
	equal(shared.Vals.node["9"].value, 4, "valid row kept")
	equal(count(shared.Vals.node), 1, "every malformed row dropped")
	equal(shared.Vals.bogus, nil, "unknown metric dropped")
	equal(db.Me, nil, "own row removed from saved state")
	equal(db[5], nil, "non-string key removed")

	-- Idempotent and independent of insertion order.
	local before = peers:Shared()
	local again = make(load(), { db = db, addon = "agf" }):Shared()
	equal(again["Good-Realm"].total.all.value, before["Good-Realm"].total.all.value, "sanitize is idempotent")

	-- Peer, row and subject caps in saved state.
	local big = {}
	for index = 1, 150 do
		big["Peer" .. string.format("%03d", index)] = { total = { all = { value = 1, eventUnix = now - index } } }
	end
	local capped = make(load(), { db = big })
	equal(count(capped:Shared()), 100, "saved peers capped at 100")
	equal(big.Peer001 ~= nil and big.Peer100 ~= nil and big.Peer101 == nil, true, "newest activity survives the cap")
	local wide = { Wide = { node = {}, creature = {}, firstkill = {} } }
	for index = 1, 600 do
		wide.Wide.node[tostring(index)] = { value = 1, eventUnix = now - index }
		wide.Wide.creature["c:" .. index] = { value = 1, eventUnix = now - index }
		wide.Wide.firstkill[tostring(index)] = { value = 1, eventUnix = now - index }
	end
	local widePeers = make(load(), { db = wide })
	local rows = 0
	for _, subjects in pairs(widePeers:Shared().Wide) do
		equal(count(subjects) <= 256, true, "256 subjects per metric")
		rows = rows + count(subjects)
	end
	equal(rows, 768, "per-metric caps apply before the 1024 row cap")
end

-- Unavailable db or setting ------------------------------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns, { db = false })
	state.rows = { { metric = "total", subject = "all", value = 1, eventUnix = serverTime } }
	equal(peers:IsEnabled(), false, "no db means disabled")
	equal(peers:Sync(), 0, "no send without a db")
	equal(recv(peers, wire("agf", "total", "all", 1, serverTime), "A-R"), false, "no receive without a db")
	equal(#peers:Board("total", "all", 3), 1, "board still has the personal row")
	equal(peers:Board("total", "all", 3)[1].value, 3, "personal value shown")
	state.db = {}
	equal(peers:IsEnabled(), true, "db arriving enables")
	state.enabled = nil
	equal(peers:IsEnabled(), false, "a falsy setting is off")

	local inert = ns.PeerStats.New({ addon = "bad addon!" })
	equal(inert:Sync(), 0, "invalid addon id is inert")
	equal(inert:SetEnabled(true), false, "inert instance cannot enable")
	equal(#inert:Board("x", nil, 1), 1, "inert board has the personal row")
	equal(count(ns.PeerStats.New():Shared()), 0, "missing config is safe")
end

-- Board ---------------------------------------------------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	recv(peers, wire("agf", "total", "all", 50, now), "Bea-X")
	recv(peers, wire("agf", "total", "all", 50, now), "Abe-X")
	recv(peers, wire("agf", "total", "all", 70, now), "Cy-X")
	recv(peers, wire("agf", "total", "all", 10, now), "Dee-X")
	local board = peers:Board("total", "all", 50, now)
	local names = {}
	for _, row in ipairs(board) do
		names[#names + 1] = row.rank .. row.name
	end
	equal(table.concat(names, ","), "1Cy-X,2Abe-X,3Bea-X,4Me,5Dee-X", "value descending, ties by identity")
	equal(board[4].self, true, "personal row flagged")
	equal(peers:Board("total", "all", nil)[5].value, 0, "missing local value is zero and still listed")
	equal(#peers:Board("nothing", "all", 4), 1, "unknown metric lists only the personal row")
	equal(#peers:Board("total", "bogus", 4), 1, "invalid subject lists only the personal row")
	equal(peers:Board("total", nil, 4)[1].rank, 1, "subject defaults to all")
	for _, row in ipairs(peers:Board("total", "all", 1e12)) do
		if row.self then
			equal(row.value, 0, "out of range local value is not trusted")
		end
	end

	-- First metrics rank by earliest time, rows without one last.
	recv(peers, wire("agf", "firstkill", "9", 1, now - 100), "Bea-X")
	recv(peers, wire("agf", "firstkill", "9", 1, now - 300), "Abe-X")
	recv(peers, wire("agf", "firstkill", "9", 1, now - 300), "Cy-X")
	local first = peers:Board("firstkill", "9", 1, now - 200)
	names = {}
	for _, row in ipairs(first) do
		names[#names + 1] = row.name
	end
	equal(table.concat(names, ","), "Abe-X,Cy-X,Me,Bea-X", "first record ascending, ties by identity")
	local none = peers:Board("firstkill", "9", 0, nil)
	equal(none[#none].self, true, "a personal row without a record ranks last")

	-- Disabled hides peers but keeps the personal row; the saved rows stay.
	state.enabled = false
	equal(#peers:Board("total", "all", 5), 1, "disabled board is only the personal row")
	equal(count(peers:Shared()), 0, "Shared is empty while disabled")
	equal(state.db["Cy-X"].total.all.value, 70, "cached rows are retained")
	state.enabled = true
	equal(#peers:Board("total", "all", 5), 5, "re-enabled board shows peers again")
	local copy = peers:Shared()
	copy["Cy-X"].total.all.value = 1
	equal(state.db["Cy-X"].total.all.value, 70, "Shared returns a copy")
end

-- Sending: snapshot, dedupe, channels, queue --------------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	state.rows = {
		{ metric = "total", subject = "all", value = 12, eventUnix = now },
		{ metric = "node", subject = "7", value = 1.9, eventUnix = now },
		{ metric = "total", subject = "all", value = 13, eventUnix = now },
		{ metric = "bogus", subject = "all", value = 1, eventUnix = now },
		{ metric = "node", subject = "x", value = 1, eventUnix = now },
		{ metric = "node", subject = "8", value = -1, eventUnix = now },
		{ metric = "firstkill", subject = "9", value = 1 },
		"junk",
	}
	equal(peers:Sync(), 2, "valid rows queued once per channel, last duplicate wins")
	equal(#sent, 0, "nothing is sent synchronously")
	advance(0)
	equal(
		table.concat(payloads(), ","),
		"GUILD:1|agf|node|7|1|" .. now .. ",GUILD:1|agf|total|all|13|" .. now,
		"wire v1"
	)
	equal(sent[1].prefix, "WFAStats", "prefix")
	equal(peers:Sync(), 0, "unchanged snapshot is not queued again")
	state.rows[1].value = 14
	state.rows[3].value = 14
	equal(peers:Sync(), 1, "a changed row is queued")
	advance(1)
	equal(#sent, 3, "the change is sent")

	-- Failure is not recorded as sent.
	resetSent()
	sendResult = 1
	state.rows = { { metric = "total", subject = "all", value = 20, eventUnix = now } }
	peers:Sync()
	advance(1)
	equal(#sent, 0, "failed send")
	sendResult = 0
	equal(peers:Sync(), 1, "failed send is offered again")
	advance(1)
	equal(#sent, 1, "then sent")

	-- Missing cumulative timestamps represent the same observation until its value changes.
	state.rows = { { metric = "total", subject = "all", value = 30 } }
	peers:Sync()
	advance(1)
	serverTime = serverTime + 10
	equal(peers:Sync(), 0, "an unchanged undated total is not resent as a new observation")
	state.rows[1].value = 31
	equal(peers:Sync(), 1, "a changed undated total is a new observation")
	advance(1)
	equal(state.rows[1].eventUnix, nil, "observation timestamps do not mutate the consumer snapshot")

	-- No channel, no sends.
	inGuild = false
	state.rows[1].value = 21
	equal(peers:Sync(), 0, "no channel available")
end

-- Channel departure, joining, no starvation --------------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	groupKind, groupSize = "PARTY", 2
	state.rows = {}
	for index = 1, 6 do
		state.rows[index] = { metric = "node", subject = tostring(index), value = 1, eventUnix = now }
	end
	equal(peers:Sync(), 12, "guild and party each get every row")
	groupKind, groupSize = nil, 0
	advance(0)
	equal(#sent > 0, true, "guild rows go out after the party left")
	for _, message in ipairs(sent) do
		equal(message.channel, "GUILD", "nothing goes to the channel that left")
	end
	equal(#sent, 6, "only the unavailable channel's entries were dropped")
	resetSent()
	groupKind, groupSize = "PARTY", 2
	equal(peers:Sync(), 6, "rejoining a group redistributes the same unchanged rows")
	advance(5)
	equal(#sent, 6, "to the party only")
	for _, message in ipairs(sent) do
		equal(message.channel, "PARTY", "party rows")
	end
	resetSent()
	equal(peers:Sync(), 0, "unchanged afterwards")
	groupSize = 3
	equal(peers:Sync(), 6, "a larger group gets the rows again")
	advance(5)
	equal(#sent, 6, "sent to the larger group")
	for _, row in ipairs(state.rows) do
		equal(row.value, 1, "snapshot untouched")
	end
	resetSent()
	groupNames.party1 = "NewMember"
	equal(peers:Sync(), 6, "a replacement member gets the rows even when group size is unchanged")
	advance(5)
	equal(#sent, 6, "replacement member triggers a party snapshot")
	equal(peers:Sync(), 0, "the same roster is not sent twice")
	groupNames.party1, groupNames.party2 = nil, "NewMember"
	equal(peers:Sync(), 0, "moving members between slots is the same audience")
	groupKind = "RAID"
	equal(peers:Sync(), 6, "a different group channel is a new audience")
	groupKind = "INSTANCE_CHAT"
	equal(peers:Sync(), 6, "instance chat is a new audience")
	advance(5)
	resetSent()
	groupSize = 4
	equal(peers:Sync(), 6, "an instance group join reads the instance roster, not the empty home group")
	advance(5)
	equal(#sent, 6, "the instance group's new member receives the snapshot")
	groupNames.party1 = "InstanceReplacement"
	equal(peers:Sync(), 6, "an instance replacement receives unchanged stats")
	local unitName = _G.UnitName
	local inaccessible = {}
	_G.canaccessvalue = function(value)
		return value ~= inaccessible
	end
	_G.UnitName = function(unit)
		if unit == "party1" then
			return inaccessible, "MyRealm"
		end
		return unitName(unit)
	end
	equal(
		pcall(function()
			peers:Sync()
		end),
		true,
		"an inaccessible roster name is never concatenated"
	)
	_G.UnitName = function(unit)
		if unit == "party1" then
			return "Member", inaccessible
		end
		return unitName(unit)
	end
	equal(
		pcall(function()
			peers:Sync()
		end),
		true,
		"an inaccessible roster realm is never concatenated"
	)
	_G.UnitName, _G.canaccessvalue = unitName, nil
end

-- Transport rate, throttle, queue cap ---------------------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	state.rows = {}
	for index = 1, 40 do
		state.rows[index] = { metric = "node", subject = tostring(index), value = 1, eventUnix = now }
	end
	peers:Sync()
	advance(0)
	equal(#sent, 10, "burst is bounded")
	advance(5)
	equal(#sent, 20, "then two a second")
	advance(30)
	equal(#sent, 40, "everything is eventually sent")
	equal(ns.PeerStats.New == nil, false, "namespace intact")

	-- Throttling backs off and retries a bounded number of times.
	local n2 = fresh()
	local p2, s2 = make(n2)
	s2.rows = { { metric = "total", subject = "all", value = 1, eventUnix = serverTime } }
	sendResult = 3
	local attempts = 0
	local base = _G.C_ChatInfo.SendAddonMessage
	_G.C_ChatInfo.SendAddonMessage = function(...)
		attempts = attempts + 1
		return base(...)
	end
	p2:Sync()
	advance(1000)
	equal(attempts, 6, "initial try plus five retries, then dropped")
	equal(_G.ForeverPeerStats.QueueSize(), 0, "throttled entry is dropped after the retries")
	sendResult = 0
	equal(p2:Sync(), 1, "dropped entry is offered by the next Sync")
	advance(5)
	equal(#sent, 1, "and goes out")
	_G.C_ChatInfo.SendAddonMessage = base

	-- Queue cap: 512 payloads pending, the rest refill from the snapshot as capacity returns.
	local n3 = fresh()
	local p3, s3 = make(n3)
	s3.rows = {}
	for index = 1, 600 do
		s3.rows[index] = { metric = "node", subject = tostring(index), value = 1, eventUnix = serverTime }
	end
	equal(p3:Sync(), 512, "queue holds at most 512")
	equal(_G.ForeverPeerStats.QueueSize(), 512, "queue size")
	advance(400)
	equal(#sent, 600, "overflow rows drain without another consumer event")
	equal(p3:Sync(), 0, "the complete snapshot was sent once")

	local multi = fresh()
	local pm, sm = make(multi)
	groupKind, groupSize = "PARTY", 2
	sm.rows = {}
	for index = 1, 300 do
		sm.rows[index] = s3.rows[index]
	end
	equal(pm:Sync(), 512, "two channels share the same bounded queue")
	advance(400)
	equal(#sent, 600, "overflow reaches both channels without another event")

	-- A permanent transport error must not turn backpressure into an endless retry loop.
	local n4 = fresh()
	local p4, s4 = make(n4)
	s4.rows = s3.rows
	sendResult = 1
	p4:Sync()
	advance(400)
	equal(_G.ForeverPeerStats.QueueSize(), 0, "failed batches drain without starving overflow")
	equal(#timers, 0, "permanent failures do not leave an automatic retry loop")
end

-- Coalescing ----------------------------------------------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	state.rows = { { metric = "total", subject = "all", value = 1, eventUnix = serverTime } }
	peers:Sync()
	state.rows[1].value = 2
	peers:Sync()
	state.rows[1].value = 3
	peers:Sync()
	equal(_G.ForeverPeerStats.QueueSize(), 1, "one queued entry per row and channel")
	advance(1)
	equal(#sent, 1, "one send")
	equal(sent[1].payload, wire("agf", "total", "all", 3, serverTime), "the latest value is sent")
end

-- Opt-out, cancel, re-enable, reload ----------------------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	state.rows = {}
	for index = 1, 5 do
		state.rows[index] = { metric = "node", subject = tostring(index), value = 1, eventUnix = now }
	end
	peers:Sync()
	equal(_G.ForeverPeerStats.QueueSize(), 5, "queued")
	state.enabled = false
	equal(peers:SetEnabled(false), false, "SetEnabled(false)")
	equal(_G.ForeverPeerStats.QueueSize(), 0, "queued sends cancelled at once")
	advance(10)
	equal(#sent, 0, "the old timer sends nothing")
	equal(peers:Sync(), 0, "no sync while off")
	equal(recv(peers, wire("agf", "total", "all", 1, now), "Pat-X"), false, "no receive while off")
	equal(state.db["Pat-X"], nil, "nothing stored while off")

	-- Off then on before the old timer fires: nothing slips out early or twice.
	state.enabled = true
	equal(peers:SetEnabled(true), true, "re-enabled")
	equal(_G.ForeverPeerStats.QueueSize(), 5, "re-enable resyncs everything")
	advance(10)
	equal(#sent, 5, "each row sent once after re-enable")

	-- Toggling repeatedly before any timer runs sends each row once.
	resetSent()
	peers:SetEnabled(false)
	peers:SetEnabled(true)
	peers:SetEnabled(false)
	peers:SetEnabled(true)
	advance(10)
	equal(#sent, 5, "rapid toggling does not multiply sends")

	-- The setting alone also disables, even without SetEnabled.
	resetSent()
	peers:Sync()
	state.rows[1].value = 2
	peers:Sync()
	state.enabled = false
	advance(10)
	equal(#sent, 0, "a saved-setting change stops queued sends at the next tick")
	equal(_G.ForeverPeerStats.QueueSize(), 0, "and empties the queue")
	state.enabled = true
	equal(peers:Sync(), 5, "turning it back on resends everything, sent cache was reset")
	advance(10)

	-- SetEnabled(true) does not override a saved false.
	state.enabled = false
	equal(peers:SetEnabled(true), false, "the saved setting is the truth")

	-- Reload: a new instance reads the saved setting and the cached peers come back.
	state.enabled = true
	recv(peers, wire("agf", "total", "all", 8, now), "Rod-X")
	local reloaded = make(fresh(), { db = state.db, rows = state.rows })
	equal(reloaded:Board("total", "all", 1)[1].name, "Rod-X", "cached peers are back after a reload")
	local off = make(fresh(), { db = state.db, enabled = false })
	equal(#off:Board("total", "all", 1), 1, "a saved false stays off after a reload")
	equal(off:Sync(), 0, "and does not send")
end

-- Several copies and addons --------------------------------------------------------------------------------------
do
	local first = fresh()
	local second = load()
	local third = load()
	equal(_G.ForeverPeerStats ~= nil, true, "global manager published")
	local manager = _G.ForeverPeerStats
	equal(manager.version, 2, "manager is versioned")
	equal(count(frames) >= 1, true, "one event frame")
	local live = 0
	for _, frame in ipairs(frames) do
		if frame.events.CHAT_MSG_ADDON then
			live = live + 1
		end
	end
	equal(live, 1, "all copies share one event registration")

	local now = serverTime
	local a, as = make(first, { addon = "agf" })
	local b, bs = make(second, { addon = "legacy" })
	local c, cs = make(third, { addon = "agf" })
	as.rows = { { metric = "total", subject = "all", value = 3, eventUnix = now } }
	bs.rows = { { metric = "node", subject = "5", value = 1, eventUnix = now } }
	cs.rows = as.rows
	equal(a:Sync(), 0, "an instance replaced by a second copy of the same addon is inert")
	equal(c:Sync(), 1, "the replacing instance sends")
	equal(b:Sync(), 1, "another addon sends its own row")
	advance(1)
	equal(
		table.concat(payloads(), ","),
		"GUILD:1|agf|total|all|3|" .. now .. ",GUILD:1|legacy|node|5|1|" .. now,
		"each addon's row is sent exactly once"
	)

	-- Events reach every addon, each keeps its own rows and nobody relays.
	resetSent()
	local frame
	for _, candidate in ipairs(frames) do
		if candidate.events.CHAT_MSG_ADDON then
			frame = candidate
		end
	end
	frame.handler(frame, "CHAT_MSG_ADDON", "WFAStats", wire("agf", "total", "all", 4, now), "GUILD", "Quin-X")
	frame.handler(frame, "CHAT_MSG_ADDON", "WFAStats", wire("legacy", "node", "5", 9, now), "GUILD", "Quin-X")
	frame.handler(frame, "CHAT_MSG_ADDON", "Other", wire("legacy", "node", "5", 10, now), "GUILD", "Quin-X")
	equal(cs.db["Quin-X"].total.all.value, 4, "agf stored its row")
	equal(cs.db["Quin-X"].node, nil, "agf did not store legacy's row")
	equal(bs.db["Quin-X"].node["5"].value, 9, "legacy stored its row")
	equal(bs.db["Quin-X"].total, nil, "legacy did not store agf's row")
	advance(60)
	equal(#sent, 0, "received rows are never relayed")
	equal(manager.QueueSize(), 0, "nothing queued by receiving")

	-- Membership events resync every enabled addon after a short delay.
	groupKind, groupSize = "PARTY", 2
	frame.handler(frame, "GROUP_ROSTER_UPDATE")
	frame.handler(frame, "GROUP_ROSTER_UPDATE")
	advance(0.5)
	equal(#sent, 0, "membership sync is debounced")
	advance(5)
	equal(#sent, 2, "each addon redistributes its unchanged row to the new party once")
	for _, message in ipairs(sent) do
		equal(message.channel, "PARTY", "to the party only")
	end

	-- Shared transport: two addons cannot exceed the burst together.
	resetSent()
	local many = {}
	for index = 1, 30 do
		many[index] = { metric = "node", subject = tostring(index), value = 1, eventUnix = now }
	end
	bs.rows = many
	b:Sync()
	advance(0)
	equal(#sent <= 10, true, "the transport stays rate limited across addons")
	-- One addon opting out does not disturb the other.
	bs.enabled = false
	b:SetEnabled(false)
	cs.rows = { { metric = "total", subject = "all", value = 99, eventUnix = now } }
	c:Sync()
	advance(60)
	local legacy, agf = 0, 0
	for _, message in ipairs(sent) do
		if message.payload:find("|legacy|", 1, true) then
			legacy = legacy + 1
		else
			agf = agf + 1
		end
	end
	equal(agf >= 1, true, "the other addon keeps sending")
	equal(legacy <= 10, true, "the opted-out addon stopped")
end

-- A newer manager takes over registered instances -----------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	state.rows = { { metric = "total", subject = "all", value = 1, eventUnix = serverTime } }
	_G.ForeverPeerStats.version = 1
	local old = _G.ForeverPeerStats
	load()
	equal(_G.ForeverPeerStats ~= old, true, "a newer copy replaces an older manager")
	equal(old.retired, true, "the old manager is retired")
	equal(peers:Sync(), 1, "registered instances move to the new manager")
	advance(1)
	equal(#sent, 1, "and send through it")
end

print(("peer_stats_spec: %d checks passed"):format(checks))
