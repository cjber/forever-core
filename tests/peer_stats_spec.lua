-- Contract for the shared peer stats protocol and board (Core/PeerStats.lua), against a mocked client.
-- rule-ignore: file-size-no-growth - vendored byte for byte from forever-core
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
local weekRemaining
local inCombatNow = false

_G.InCombatLockdown = function()
	return inCombatNow
end
_G.GetTime = function()
	return clock
end
_G.GetServerTime = function()
	return serverTime
end
_G.C_DateAndTime = {
	GetSecondsUntilWeeklyReset = function()
		return weekRemaining
	end,
}
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
	weekRemaining, inCombatNow = nil, false
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

local function relayWire(addon, metric, subject, value, unix, origin)
	return table.concat({ "2", addon, metric, subject, value, unix, origin }, "|")
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
	rejected("3|agf|total|all|5|" .. now, nil, nil, "addon", "wrong version")
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

-- Own name with a Forever surname --------------------------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	groupNames.player = "Hel Io"

	-- The echoed broadcast can arrive under the spaced name or the compacted key.
	for _, sender in ipairs({ "Hel Io", "HelIo", "hel io-MyRealm", "helio-MyRealm" }) do
		local ok, why = recv(peers, wire("agf", "total", "all", 85, now), sender)
		equal(ok, false, "own two-part name ignored: " .. sender)
		equal(why, "sender", "own two-part name reason: " .. sender)
	end
	equal(count(state.db), 0, "own broadcast stored nothing")

	equal(recv(peers, wire("agf", "total", "all", 85, now), "Hello"), true, "another player is accepted")
	equal(state.db.Hello.total.all.value, 85, "another player is stored")

	-- A saved copy from before the fix may hold the player under the compacted key.
	local db = {
		HelIo = { total = { all = { value = 85, eventUnix = now } } },
		["Hel Io-MyRealm"] = { total = { all = { value = 85, eventUnix = now } } },
		Hello = { total = { all = { value = 85, eventUnix = now } } },
	}
	local reloaded = make(load(), { db = db })
	equal(count(reloaded:Shared()), 1, "old own rows are dropped and the peer kept")
	equal(db.HelIo, nil, "compacted own key removed")
	equal(db["Hel Io-MyRealm"], nil, "own name with realm removed")
	local board = reloaded:Board("total", "all", 85, now)
	equal(#board, 2, "the board has one personal row and one peer")
	local ownRows = 0
	for _, row in ipairs(board) do
		if row.self then
			ownRows = ownRows + 1
			equal(row.identity, "helio", "personal row identity is compacted")
			equal(row.name, "Hel Io", "personal row keeps the display name")
		end
	end
	equal(ownRows, 1, "the player appears once")
end

-- Display names beside the compacted keys ------------------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	equal(
		recv(peers, wire("agf", "total", "all", 42, now), "Dirtyjoke Lovetties-OtherRealm"),
		true,
		"a spaced sender is accepted"
	)
	equal(state.db["DirtyjokeLovetties-OtherRealm"].total.all.value, 42, "the compacted key still holds the row")
	equal(
		state.db["DirtyjokeLovetties-OtherRealm"]["\1name"],
		"Dirtyjoke Lovetties",
		"the display name is saved beside the row, without the realm"
	)
	local board = peers:Board("total", "all", 1, now)
	local peerName
	for _, row in ipairs(board) do
		if not row.self then
			peerName = row.name
		end
	end
	equal(peerName, "Dirtyjoke Lovetties", "the board row draws the full name")
	equal(peers:Shared()["DirtyjokeLovetties-OtherRealm"]["\1name"], nil, "Shared leaves the display name out")
	local sharedRow = peers:Shared()["DirtyjokeLovetties-OtherRealm"]
	for metric, subjects in pairs(sharedRow) do
		equal(type(subjects), "table", "every value in a Shared row is a metric table: " .. tostring(metric))
	end
	local reloaded = make(load(), { db = state.db })
	local reloadedName
	for _, row in ipairs(reloaded:Board("total", "all", 1, now)) do
		if row.identity == "dirtyjokelovetties-otherrealm" then
			reloadedName = row.name
		end
	end
	equal(reloadedName, "Dirtyjoke Lovetties", "a saved display name survives a reload")
end

-- Old rows without a display name --------------------------------------------------------------------------------
do
	local ns = fresh()
	local now = serverTime
	local db = {
		DirtyjokeLovetties = { total = { all = { value = 3, eventUnix = now } } },
		NewGame = { total = { all = { value = 2, eventUnix = now } } },
		["Abe-OtherRealm"] = { total = { all = { value = 1, eventUnix = now } } },
	}
	local peers = make(ns, { db = db })
	local names = {}
	for _, row in ipairs(peers:Board("total", "all", 0, now)) do
		names[row.identity] = row.name
	end
	equal(names.dirtyjokelovetties, "Dirtyjoke Lovetties", "a single inner capital becomes the name break")
	equal(names.newgame, "New Game", "and another one does too")
	equal(names["abe-otherrealm"], "Abe-OtherRealm", "a key with no single inner capital is shown as it is")
	equal(db.DirtyjokeLovetties["\1name"], nil, "the fallback is not saved")

	-- The next message replaces the guess and keeps the compacted key.
	equal(recv(peers, wire("agf", "total", "all", 4, now), "Dirtyjoke Lovetties"), true, "a new row from the player")
	equal(db.DirtyjokeLovetties["\1name"], "Dirtyjoke Lovetties", "the sender's spelling is saved beside the same key")
	equal(db.DirtyjokeLovetties.total.all.value, 4, "and the row still lives under it")
	equal(recv(peers, wire("agf", "total", "all", 1, now), "New Game"), true, "an older value still brings the name")
	equal(db.NewGame["\1name"], "New Game", "saved beside the unchanged key")
	equal(db.NewGame.total.all.value, 2, "while the better value stays")
end

-- The own name from both UnitName returns -------------------------------------------------------------------------
do
	local ns = fresh()
	local unitName = _G.UnitName
	_G.UnitName = function(unit)
		if unit == "player" then
			return "Hel", "Io"
		end
		return unitName(unit)
	end
	_G.Constants = { CharacterNameSeparatorConsts = { CHARACTERNAME_SURNAME_SEPARATOR = " " } }
	local peers = make(ns)
	local now = serverTime
	local board = peers:Board("total", "all", 3, now)
	equal(board[1].name, "Hel Io", "the personal row joins both returns")
	equal(board[1].identity, "helio", "and keeps the compacted identity")
	equal(recv(peers, wire("agf", "total", "all", 9, now), "HelIo"), false, "the own compacted key is still the player")
	_G.UnitName = unitName
	_G.Constants = nil
end

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
	-- Sharing is opt-out: a missing saved setting reads as on, and only an explicit false is off.
	state.enabled = nil
	equal(peers:IsEnabled(), true, "a missing setting means sharing is on")
	state.enabled = false
	equal(peers:IsEnabled(), false, "only an explicit false is off")
	state.enabled = true
	local plainDb = {}
	local plain = ns.PeerStats.New({
		addon = "plain",
		db = function()
			return plainDb
		end,
		metrics = METRICS,
	})
	equal(plain:IsEnabled(), true, "a config without an enabled function shares by default")
	plain:SetEnabled(false)
	equal(plain:IsEnabled(), false, "and the explicit switch still turns it off")

	local inert = ns.PeerStats.New({ addon = "bad addon!" })
	equal(inert:Sync(), 0, "invalid addon id is inert")
	equal(inert:SetEnabled(true), false, "inert instance cannot enable")
	equal(#inert:Board("x", nil, 1), 1, "inert board has the personal row")
	equal(count(ns.PeerStats.New():Shared()), 0, "missing config is safe")
end

-- Revision: the cache key the leaderboards read ----------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	equal(peers:Revision(), 0, "a fresh instance starts at zero")
	equal(recv(peers, wire("agf", "total", "all", 5, now), "Rev-X"), true, "a row is stored")
	local afterReceive = peers:Revision()
	equal(afterReceive > 0, true, "a stored row raises the revision")
	equal(recv(peers, wire("agf", "total", "all", 4, now), "Rev-X"), false, "a stale row is refused")
	equal(peers:Revision(), afterReceive, "a refused row leaves it alone")

	state.rows = { { metric = "total", subject = "all", value = 7, eventUnix = now } }
	equal(peers:Sync(), 1, "the snapshot is queued; the guild row skips the guild it was heard on")
	local afterSync = peers:Revision()
	equal(afterSync > afterReceive, true, "a changed snapshot raises the revision")
	advance(1)
	equal(peers:Sync(), 0, "an unchanged snapshot is not queued")
	equal(peers:Revision(), afterSync, "and leaves the revision alone")

	state.enabled = false
	equal(peers:IsEnabled(), false, "the saved setting turns sharing off")
	local afterOff = peers:Revision()
	equal(afterOff > afterSync, true, "the visibility change raises the revision")
	state.enabled = true
	peers:IsEnabled()
	equal(peers:Revision() > afterOff, true, "and so does turning it back on")

	local reloaded = make(load(ns), { db = state.db, rows = state.rows })
	equal(reloaded:Revision(), 0, "a reloaded instance starts at zero")
	reloaded:IsEnabled()
	equal(reloaded:Revision() > 0, true, "reading its saved table raises the revision")
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
	equal(table.concat(names, ","), "1Cy,2Abe,3Bea,4Me,5Dee", "value descending, ties by identity")
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
	equal(table.concat(names, ","), "Abe,Cy,Me,Bea", "first record ascending, ties by identity")
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
	equal(reloaded:Board("total", "all", 1)[1].name, "Rod", "cached peers are back after a reload")
	local off = make(fresh(), { db = state.db, enabled = false })
	equal(#off:Board("total", "all", 1), 1, "a saved false stays off after a reload")
	equal(off:Sync(), 0, "and does not send")
end

-- Combat defers sends --------------------------------------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local manager = _G.ForeverPeerStats
	state.rows = { { metric = "total", subject = "all", value = 3, eventUnix = serverTime } }
	inCombatNow = true
	manager.OnEvent("PLAYER_REGEN_DISABLED")
	peers:Sync()
	advance(30)
	equal(#sent, 0, "nothing is sent in combat")
	equal(manager.QueueSize(), 1, "the queued row waits")
	inCombatNow = false
	manager.OnEvent("PLAYER_REGEN_ENABLED")
	advance(1)
	equal(#sent, 1, "it goes out when combat ends")
	equal(peers:Sync(), 0, "and is not offered twice")

	-- A queue built while the client reports combat waits too, even without the event.
	resetSent()
	local otherNs = fresh()
	inCombatNow = true
	local other, otherState = make(otherNs)
	otherState.rows = { { metric = "total", subject = "all", value = 4, eventUnix = serverTime } }
	other:Sync()
	advance(30)
	equal(#sent, 0, "the live combat check holds the row")
	inCombatNow = false
	_G.ForeverPeerStats.OnEvent("PLAYER_REGEN_ENABLED")
	advance(1)
	equal(#sent, 1, "and releases it when the fight ends")
end

-- Several copies and addons --------------------------------------------------------------------------------------
do
	local first = fresh()
	local second = load()
	local third = load()
	equal(_G.ForeverPeerStats ~= nil, true, "global manager published")
	local manager = _G.ForeverPeerStats
	equal(manager.version, 7, "manager is versioned")
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

	-- Events reach every addon, each keeps its own rows, and receiving queues no relay of its own.
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
	equal(#sent, 0, "receiving queues no relay by itself")
	equal(manager.QueueSize(), 0, "nothing queued by receiving")

	-- Membership events resync every enabled addon after a short delay. Each now sends its own row and the row it
	-- heard from Quin to the new party, but not back to the guild it heard Quin on.
	groupKind, groupSize = "PARTY", 2
	frame.handler(frame, "GROUP_ROSTER_UPDATE")
	frame.handler(frame, "GROUP_ROSTER_UPDATE")
	advance(0.5)
	equal(#sent, 0, "membership sync is debounced")
	advance(5)
	equal(#sent, 4, "each addon sends its own row and Quin's relay to the new party once")
	local relayed = 0
	for _, message in ipairs(sent) do
		equal(message.channel, "PARTY", "to the party only")
		if message.payload:sub(1, 2) == "2|" then
			relayed = relayed + 1
			equal(message.payload:find("|Quin%-X$") ~= nil, true, "the relay keeps Quin as its origin")
		end
	end
	equal(relayed, 2, "one relay per addon about Quin")

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
	_G.ForeverPeerStats.version = 2
	local old = _G.ForeverPeerStats
	load()
	equal(_G.ForeverPeerStats ~= old, true, "a newer copy replaces an older manager")
	equal(old.retired, true, "the old manager is retired")
	equal(peers:Sync(), 1, "registered instances move to the new manager")
	advance(1)
	equal(#sent, 1, "and send through it")
end

-- Read-only subscriptions preserve foreign-addon reads without replacing its sender or relaying reports.
do
	local ns = fresh()
	local observed, enabled = {}, true
	local reader = ns.PeerStats.Listen("fieldguide", {
		addon = "agf",
		enabled = function()
			return enabled
		end,
		db = function()
			return observed
		end,
		metrics = METRICS,
		snapshot = function()
			return { { metric = "total", subject = "all", value = 999, eventUnix = serverTime } }
		end,
	})
	local sender, state = make(load())
	state.rows = { { metric = "total", subject = "all", value = 3, eventUnix = serverTime } }
	equal(reader:Sync(), 0, "a reader cannot send even with a snapshot")
	equal(sender:Sync(), 1, "the actual addon still sends after a reader registered first")
	advance(1)
	equal(#sent, 1, "the subscriber adds no sends")
	resetSent()
	local manager = _G.ForeverPeerStats
	manager.OnEvent("CHAT_MSG_ADDON", "WFAStats", wire("agf", "total", "all", 8, serverTime), "GUILD", "Alice-X")
	equal(observed["Alice-X"].total.all.value, 8, "the reader receives its configured source")
	equal(state.db["Alice-X"].total.all.value, 8, "the actual addon receives the same report independently")
	advance(30)
	equal(#sent, 0, "the reader never relays incoming rows")
	enabled = false
	reader:SetEnabled(false)
	equal(count(reader:Shared()), 0, "the reader hides reports while disabled")
	equal(
		recv(reader, wire("agf", "total", "all", 9, serverTime), "Alice-X"),
		false,
		"an opted-out reader ignores reports"
	)
	equal(
		recv(sender, wire("agf", "total", "all", 9, serverTime), "Alice-X"),
		true,
		"the source addon remains independent"
	)
	enabled = true
	reader:SetEnabled(true)
	equal(reader:Shared()["Alice-X"].total.all.value, 8, "re-enable retains the reader's own saved reports")
	local replacement = ns.PeerStats.Listen("fieldguide", { addon = "agf", metrics = METRICS })
	equal(reader.dead, true, "another copy replaces only the same owner's subscription")
	equal(sender.dead, false, "replacing a subscription leaves the real sender alive")
	equal(replacement:Sync(), 0, "a reader with no database is inert")
	local another = ns.PeerStats.Listen("legacy", { addon = "agf", metrics = METRICS })
	equal(replacement.dead, false, "another subscriber owner does not replace this reader")
	equal(another.dead, false, "a second owner can subscribe to the same source")
	equal(ns.PeerStats.Listen(nil, { addon = "agf" }).dead, true, "a reader needs a valid owner")
	equal(ns.PeerStats.Listen("bad owner", { addon = "agf" }).dead, true, "invalid reader owners are rejected")
	equal(ns.PeerStats.Listen("fieldguide", { addon = "bad source" }).dead, true, "invalid reader sources are rejected")
	local old = _G.ForeverPeerStats
	old.version = 2
	load()
	equal(_G.ForeverPeerStats ~= old, true, "a manager upgrade keeps subscriptions separate")
	equal(sender.dead, false, "manager takeover preserves the source sender")
	equal(replacement.dead, false, "manager takeover preserves the first owner subscription")
	equal(another.dead, false, "manager takeover preserves the second owner subscription")
end

-- Existing node/difficulty subjects stay valid alongside explicit aggregate subjects.
do
	local ns = fresh()
	local db = {}
	local peers = ns.PeerStats.New({
		addon = "fieldguide",
		enabled = function()
			return true
		end,
		db = function()
			return db
		end,
		metrics = { kills = { subject = "numeric_or_all" }, boss = { subject = "numeric_pair" } },
	})
	equal(recv(peers, wire("fieldguide", "kills", "all", 3, serverTime), "Alice-X"), true, "aggregate subject accepted")
	equal(recv(peers, wire("fieldguide", "kills", "42", 3, serverTime), "Alice-X"), true, "numeric subject accepted")
	equal(
		recv(peers, wire("fieldguide", "kills", "042", 3, serverTime), "Alice-X"),
		false,
		"ambiguous numeric subject rejected"
	)
	equal(
		recv(peers, wire("fieldguide", "boss", "77_0", 3, serverTime), "Alice-X"),
		true,
		"encounter difficulty zero accepted"
	)
	equal(
		recv(peers, wire("fieldguide", "boss", "77_3", 3, serverTime), "Alice-X"),
		true,
		"encounter difficulty accepted"
	)
	for _, subject in ipairs({ "all", "77", "0_3", "077_3", "77_03", "77_-3", "77_3_4" }) do
		equal(
			recv(peers, wire("fieldguide", "boss", subject, 3, serverTime), "Alice-X"),
			false,
			"invalid pair " .. subject
		)
	end
end

-- Weekly baselines and WeekBoard ---------------------------------------------------------------------------------
do
	local ns = fresh()
	-- 100,000 seconds to the next reset puts this week's start 504,800 seconds before serverTime.
	weekRemaining = 100000
	local peers, state = make(ns)
	local now = serverTime
	equal(recv(peers, wire("agf", "total", "all", 52, now - 100), "Wk-X"), true, "first peer value")
	equal(state.db["Wk-X"].total.all.week, 52, "the first value heard this week is the baseline")
	equal(state.db["Wk-X"].total.all.weekUnix, now - 100, "with its timestamp")
	equal(recv(peers, wire("agf", "total", "all", 60, now), "Wk-X"), true, "second peer value")
	local board = peers:WeekBoard("total", "all", 5, now)
	equal(#board, 2, "one personal row and one peer")
	equal(board[1].name, "Wk", "the peer's weekly value ranks first")
	equal(board[1].value, 8, "current minus the first value heard")
	equal(board[2].self, true, "the personal row is there")
	equal(board[2].value, 0, "a first observation is the personal baseline")

	-- The player's own baseline persists in the same table, in the same layout.
	local before = state.db["\1week"].total.all.value
	equal(before, 5, "the personal baseline is saved")
	board = peers:WeekBoard("total", "all", 12, now)
	equal(board[1].value, 8, "the peer is unchanged")
	equal(board[2].value, 7, "the player's progress is measured from their baseline")

	local reloaded = make(load(), { db = state.db, rows = state.rows })
	board = reloaded:WeekBoard("total", "all", 15, now)
	local own, peer
	for _, row in ipairs(board) do
		if row.self then
			own = row.value
		else
			peer = row.value
		end
	end
	equal(own, 10, "the personal baseline survives a reload")
	equal(peer, 8, "so does the peer's")

	-- Past the weekly reset, last week's baselines no longer count.
	serverTime = serverTime + 100000
	weekRemaining = 604700
	board = reloaded:WeekBoard("total", "all", 15, serverTime)
	for _, row in ipairs(board) do
		equal(row.value, 0, "a stale baseline reads as no progress this week")
	end
	recv(reloaded, wire("agf", "total", "all", 70, serverTime), "Wk-X")
	board = reloaded:WeekBoard("total", "all", 20, serverTime)
	own, peer = nil, nil
	for _, row in ipairs(board) do
		if row.self then
			own = row.value
		else
			peer = row.value
		end
	end
	equal(own, 5, "the player's baseline was retaken by the first post-reset call")
	equal(peer, 0, "so is the peer's")
	recv(reloaded, wire("agf", "total", "all", 79, serverTime), "Wk-X")
	local resumed = reloaded:WeekBoard("total", "all", 25, serverTime)
	equal(resumed[1].value, 10, "then the player's weekly progress resumes")
	equal(resumed[2].value, 9, "and the peer's")

	-- A first metric counts whether the record happened this week.
	local firstPeers = make(fresh())
	weekRemaining = 100000
	local weekStart = serverTime + 100000 - 604800
	recv(firstPeers, wire("agf", "firstkill", "9", 1, weekStart - 100), "Old-X")
	recv(firstPeers, wire("agf", "firstkill", "9", 1, weekStart + 100), "New-X")
	local firstBoard = firstPeers:WeekBoard("firstkill", "9", 1, weekStart - 50)
	local old, new
	for _, row in ipairs(firstBoard) do
		if row.name == "Old" then
			old = row.value
		elseif row.name == "New" then
			new = row.value
		end
	end
	equal(new, 1, "a peer's first record this week counts")
	equal(old, 0, "last week's does not")
	local ownRow
	for _, row in ipairs(firstBoard) do
		if row.self then
			ownRow = row
		end
	end
	equal(ownRow.value, 0, "a personal record before the reset has no weekly count")
	local selfRow
	for _, row in ipairs(firstPeers:WeekBoard("firstkill", "9", 1, weekStart + 50)) do
		if row.self then
			selfRow = row
		end
	end
	equal(selfRow.value, 1, "and a personal record this week counts")

	-- Old saved rows have no baseline; the module fills one at the row's value and reads nothing as progress.
	local oldDb = { Old = { total = { all = { value = 50, eventUnix = serverTime - 50 } } } }
	local oldPeers = make(load(), { db = oldDb })
	local shared = oldPeers:Shared()
	equal(shared.Old.total.all.value, 50, "an old row still loads")
	equal(shared.Old.total.all.week, 50, "its baseline starts at the current value")
	equal(shared.Old.total.all.weekUnix, serverTime - 50, "with the row's own time")
	equal(oldPeers:WeekBoard("total", "all", 10, serverTime)[1].value, 0, "the old peer has no weekly progress")
	local malformed = { Bad = { total = { all = { value = 5, eventUnix = serverTime, week = -1, weekUnix = 1 } } } }
	local malformedPeers = make(load(), { db = malformed })
	equal(malformedPeers:Shared().Bad.total.all.week, 5, "a malformed baseline is replaced")

	-- No weekly API: the Tuesday 15:00 UTC reset is the fallback. 1700000000 is a Tuesday.
	local fallback = fresh()
	_G.C_DateAndTime = nil
	serverTime = 1699974400 -- Tuesday 15:06:40 UTC
	local fallbackPeers = make(fallback)
	local reset = 1699974000 -- Tuesday 15:00 UTC
	recv(fallbackPeers, wire("agf", "total", "all", 10, reset - 600), "Fall-X")
	recv(fallbackPeers, wire("agf", "total", "all", 12, reset + 100), "Fall-X")
	equal(fallbackPeers:WeekBoard("total", "all", 1, reset + 200)[1].value, 0, "the first value after the reset")
	recv(fallbackPeers, wire("agf", "total", "all", 16, reset + 200), "Fall-X")
	equal(fallbackPeers:WeekBoard("total", "all", 1, reset + 300)[1].value, 4, "progress since the reset")
	_G.C_DateAndTime = {
		GetSecondsUntilWeeklyReset = function()
			return weekRemaining
		end,
	}
end

-- Relay receive, the reach flag and the two peer caps -----------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	equal(
		recv(peers, relayWire("agf", "total", "all", 5, now, "Cat-OtherRealm"), "B-OtherRealm"),
		true,
		"a relayed row is stored"
	)
	equal(state.db["Cat-OtherRealm"].total.all.value, 5, "under the origin's key")
	equal(state.db["Cat-OtherRealm"].total.all.relayed, true, "marked as relayed")
	equal(state.db["B-OtherRealm"], nil, "not under the relayer")
	equal(#peers:Board("total", "all", 0, now), 1, "the default board leaves a relayed row out")
	equal(peers:Shared()["Cat-OtherRealm"], nil, "Shared leaves it out by default")
	_G.ForeverPeerStats.includeRelayed = true
	local board = peers:Board("total", "all", 0, now)
	equal(#board, 2, "the met reach includes it")
	local relayedRow
	for _, candidaterow in ipairs(board) do
		if not candidaterow.self then
			relayedRow = candidaterow
		end
	end
	equal(relayedRow.relayed, true, "the row says it is relayed")
	equal(#peers:WeekBoard("total", "all", 0, now), 2, "WeekBoard includes it for the met reach too")
	_G.ForeverPeerStats.includeRelayed = false
	equal(#peers:Board("total", "all", 0, now), 1, "and the default hides it again")
end

-- A relay may not name the player or its own relayer -------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	local ok, why = recv(peers, relayWire("agf", "total", "all", 5, now, "Me-MyRealm"), "B-OtherRealm")
	equal(ok, false, "a relay naming the player is dropped")
	equal(why, "relay", "with the relay reason")
	ok, why = recv(peers, relayWire("agf", "total", "all", 5, now, "B-OtherRealm"), "B-OtherRealm")
	equal(ok, false, "a relay naming its own relayer is dropped")
	equal(why, "relay", "with the relay reason")
	ok, why = recv(peers, relayWire("agf", "total", "all", 5, now, "Bad|Origin"), "B-OtherRealm")
	equal(ok, false, "an unreadable origin is dropped")
	equal(why, "relay", "with the relay reason")
	equal(count(state.db), 0, "nothing stored")
end

-- Direct records and relayed records never cross -----------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	equal(recv(peers, wire("agf", "total", "all", 5, now - 10), "Cat-OtherRealm"), true, "a direct row first")
	local ok, why = recv(peers, relayWire("agf", "total", "all", 99, now, "Cat-OtherRealm"), "B-OtherRealm")
	equal(ok, false, "a relay never replaces a direct record")
	equal(why, "direct", "with the direct reason")
	equal(state.db["Cat-OtherRealm"].total.all.value, 5, "the direct value stays")
	equal(state.db["Cat-OtherRealm"].total.all.relayed, nil, "and the record stays direct")
end

do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	equal(
		recv(peers, relayWire("agf", "total", "all", 99, now, "Cat-OtherRealm"), "B-OtherRealm"),
		true,
		"a relayed row first"
	)
	equal(state.db["Cat-OtherRealm"].total.all.relayed, true, "marked relayed")
	equal(recv(peers, wire("agf", "total", "all", 1, now - 100), "Cat-OtherRealm"), true, "a lower direct row")
	equal(state.db["Cat-OtherRealm"].total.all.value, 1, "replaces the relayed value")
	equal(state.db["Cat-OtherRealm"].total.all.relayed, nil, "and clears the mark")
end

do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	equal(
		recv(peers, relayWire("agf", "total", "all", 5, now - 10, "Cat-OtherRealm"), "B-OtherRealm"),
		true,
		"first relay"
	)
	local ok, why = recv(peers, relayWire("agf", "total", "all", 4, now, "Cat-OtherRealm"), "B-OtherRealm")
	equal(ok, false, "a lower relay is stale")
	equal(why, "stale", "with the stale reason")
	equal(
		recv(peers, relayWire("agf", "total", "all", 5, now, "Cat-OtherRealm"), "B-OtherRealm"),
		true,
		"a better relay replaces it"
	)
	equal(state.db["Cat-OtherRealm"].total.all.eventUnix, now, "with its time")
end

-- A relay fills a missing display name and never changes a saved one ---------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	equal(
		recv(peers, wire("agf", "total", "all", 5, now - 10), "Dirtyjoke Lovetties-OtherRealm"),
		true,
		"a direct row sets the name"
	)
	local key = "DirtyjokeLovetties-OtherRealm"
	equal(state.db[key]["\1name"], "Dirtyjoke Lovetties", "saved")
	equal(
		recv(peers, relayWire("agf", "total", "all", 9, now, "DirtyjokeLovetties-OtherRealm"), "B-OtherRealm"),
		false,
		"the relay does not replace the direct row"
	)
	equal(state.db[key]["\1name"], "Dirtyjoke Lovetties", "a relay never changes a saved display name")

	local db = {
		["OldPeer-OtherRealm"] = { total = { all = { value = 1, eventUnix = now - 100, relayed = true } } },
	}
	local savedPeers, savedState = make(load(), { db = db })
	equal(savedState.db["OldPeer-OtherRealm"]["\1name"], nil, "an old row has no display name")
	equal(
		recv(savedPeers, relayWire("agf", "total", "all", 2, now, "Old Peer-OtherRealm"), "B-OtherRealm"),
		true,
		"a relay stores a better row"
	)
	equal(savedState.db["OldPeer-OtherRealm"]["\1name"], "Old Peer", "and fills the missing display name")
end

-- Relay-only peers have their own 400 cap and never displace a direct peer ---------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	equal(recv(peers, wire("agf", "total", "all", 1, now - 1000), "Direct-R"), true, "a direct peer")
	for index = 1, 400 do
		local origin = "P" .. index .. "-R"
		equal(
			recv(peers, relayWire("agf", "total", "all", 1, now - 500 + index, origin), "Relayer" .. index .. "-R"),
			true,
			"relay-only peer " .. index
		)
	end
	equal(count(state.db), 401, "400 relay-only peers and one direct peer")
	equal(state.db["P1-R"] ~= nil, true, "the oldest relay-only peer is there at the cap")
	equal(
		recv(peers, relayWire("agf", "total", "all", 1, now, "P401-R"), "Relayer401-R"),
		true,
		"the 401st relay-only peer is accepted"
	)
	equal(state.db["P1-R"], nil, "the least recently active relay-only peer is evicted")
	equal(state.db["P2-R"] ~= nil, true, "the next one stays")
	equal(state.db["P401-R"] ~= nil, true, "the new one is stored")
	equal(state.db["Direct-R"] ~= nil, true, "a direct peer is never evicted for a relay")

	for index = 1, 99 do
		equal(recv(peers, wire("agf", "total", "all", 1, now), "D" .. index .. "-R"), true, "direct peer " .. index)
	end
	local rejected, why = recv(peers, wire("agf", "total", "all", 1, now), "D100-R")
	equal(rejected, false, "the direct cap still stops a new direct peer")
	equal(why, "peers", "for the peer cap")
	equal(state.db["P2-R"] ~= nil, true, "and relay-only peers are still not evicted for it")
end

-- Sync relays the newest rows, skips the channel the origin was heard on, and does nothing twice ------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	local now = serverTime
	groupKind, groupSize = "PARTY", 2
	state.rows = {}
	equal(recv(peers, wire("agf", "total", "all", 1, now), "Seen-R", "PARTY"), true, "seen on the party channel")
	equal(recv(peers, wire("agf", "total", "all", 1, now - 1), "Local"), true, "a peer on the local realm")
	for index = 2, 26 do
		equal(recv(peers, wire("agf", "total", "all", 1, now - index), "R" .. index .. "-R"), true, "peer " .. index)
	end
	equal(recv(peers, wire("agf", "total", "all", 1, now - 8 * 86400), "Old-R"), true, "an old row")
	equal(_G.ForeverPeerStats.QueueSize(), 0, "receiving queues nothing")
	equal(peers:Sync(), 24, "24 relay sends: Seen to the guild, the guild rows to the party")
	advance(60)
	local relayed = {}
	for _, message in ipairs(sent) do
		if message.payload:sub(1, 2) == "2|" then
			relayed[#relayed + 1] = message
		end
	end
	equal(#relayed, 24, "exactly the relay cap goes out")
	equal(
		relayed[1].payload,
		table.concat({ "2", "agf", "total", "all", 1, now, "Seen-R" }, "|"),
		"the newest row is first"
	)
	equal(
		relayed[2].payload,
		table.concat({ "2", "agf", "total", "all", 1, now - 1, "Local-MyRealm" }, "|"),
		"a local-realm key is spelled out with the relayer's realm"
	)
	equal(relayed[1].channel, "GUILD", "a row heard on the party is not sent back to the party")
	local sawOld, sawR24 = false, false
	for _, message in ipairs(relayed) do
		if message.payload:find("|Old%-R$") then
			sawOld = true
		end
		if message.payload:find("|R24%-R$") then
			sawR24 = true
		end
	end
	equal(sawOld, false, "a row older than seven days is not relayed")
	equal(sawR24, false, "the 25th newest row is over the cap")
	equal(peers:Sync(), 0, "a second Sync with nothing changed queues no relay")
	equal(recv(peers, wire("agf", "total", "all", 2, now), "Seen-R", "PARTY"), true, "the row changes")
	equal(peers:Sync(), 1, "and only that relay is offered again")
end

-- Only a sending New instance relays, and only its own addon's rows -----------------------------------------------
do
	local ns = fresh()
	local observed, enabled = {}, true
	local reader = ns.PeerStats.Listen("fieldguide", {
		addon = "agf",
		enabled = function()
			return enabled
		end,
		db = function()
			return observed
		end,
		metrics = METRICS,
	})
	equal(recv(reader, wire("agf", "total", "all", 4, serverTime), "Alice-R"), true, "a reader still receives")
	equal(reader:Sync(), 0, "a Listen instance relays nothing")
	advance(1)
	equal(#sent, 0, "and sends nothing")

	local offDb = { ["Alice-R"] = { total = { all = { value = 4, eventUnix = serverTime } } } }
	local off = make(ns, { db = offDb, enabled = false })
	equal(off:Sync(), 0, "a disabled instance relays nothing")
	advance(1)
	equal(#sent, 0, "and still sends nothing")

	resetSent()
	local firstDb, secondDb = {}, {}
	local first = make(load(), { addon = "agf", db = firstDb })
	local second = make(load(), { addon = "legacy", db = secondDb })
	firstDb["First-R"] = { total = { all = { value = 1, eventUnix = serverTime } } }
	secondDb["Second-R"] = { node = { ["5"] = { value = 1, eventUnix = serverTime } } }
	equal(first:Sync(), 1, "the first addon relays its own row")
	equal(second:Sync(), 1, "the second addon relays its own row")
	advance(1)
	local byAddon = {}
	for _, message in ipairs(sent) do
		if message.payload:sub(1, 2) == "2|" then
			local addon = message.payload:match("^2|([^|]*)|")
			byAddon[addon] = (byAddon[addon] or 0) + 1
		end
	end
	equal(byAddon.agf, 1, "agf relays only its own metric rows")
	equal(byAddon.legacy, 1, "legacy relays only its own metric rows")
end

-- Receiving a relay queues nothing -------------------------------------------------------------------------------
do
	local ns = fresh()
	local peers = make(ns)
	equal(
		recv(peers, relayWire("agf", "total", "all", 5, serverTime, "Cat-OtherRealm"), "B-OtherRealm"),
		true,
		"a relay is stored"
	)
	equal(_G.ForeverPeerStats.QueueSize(), 0, "and queues no send")
	advance(10)
	equal(#sent, 0, "nothing leaves the client")

	-- A later Sync can pass the relayed row on, keeping the origin it arrived with.
	groupKind, groupSize = "PARTY", 2
	equal(peers:Sync(), 2, "the next Sync relays it to the open channels")
	advance(1)
	local passed = false
	for _, message in ipairs(sent) do
		if message.payload:find("|Cat%-OtherRealm$") then
			passed = true
		end
	end
	equal(passed, true, "the relayed row keeps its origin when passed on")
end

-- SanitizeStore keeps only relayed = true, and a reload keeps the row out of the default board --------------------
do
	local ns = fresh()
	local now = serverTime
	local db = {
		OnlyRelayed = { total = { all = { value = 5, eventUnix = now, relayed = true } } },
		NotTrue = { total = { all = { value = 6, eventUnix = now, relayed = "yes" } } },
		FalseFlag = { total = { all = { value = 7, eventUnix = now, relayed = false } } },
	}
	local peers = make(ns, { db = db })
	equal(peers:IsEnabled(), true, "the saved store is read")
	equal(db.OnlyRelayed.total.all.relayed, true, "relayed = true survives sanitize")
	equal(db.NotTrue.total.all.relayed, nil, "a non-true mark is dropped")
	equal(db.FalseFlag.total.all.relayed, nil, "false is dropped")
	equal(#peers:Board("total", "all", 0, now), 3, "the default board hides the relay-only row")
	_G.ForeverPeerStats.includeRelayed = true
	equal(#peers:Board("total", "all", 0, now), 4, "the met reach shows it")
	_G.ForeverPeerStats.includeRelayed = false

	local reloaded = make(load(), { db = db })
	equal(#reloaded:Board("total", "all", 0, now), 3, "a reload keeps relayed rows out of the board")
	_G.ForeverPeerStats.includeRelayed = true
	equal(#reloaded:Board("total", "all", 0, now), 4, "but the mark survived and the met reach finds it")
	_G.ForeverPeerStats.includeRelayed = false
end

-- Manager takeover from a v6 copy --------------------------------------------------------------------------------
do
	local ns = fresh()
	local peers, state = make(ns)
	equal(_G.ForeverPeerStats.version, 7, "this copy is manager version 7")
	state.rows = { { metric = "total", subject = "all", value = 3, eventUnix = serverTime } }
	_G.ForeverPeerStats.version = 6
	local old = _G.ForeverPeerStats
	load()
	equal(_G.ForeverPeerStats ~= old, true, "a v6 manager is replaced")
	equal(old.retired, true, "and retired")
	equal(_G.ForeverPeerStats.version, 7, "by version 7")
	equal(peers:Sync(), 1, "registered instances move to the new manager")
	advance(1)
	equal(#sent, 1, "and send through it")
end

print(("peer_stats_spec: %d checks passed"):format(checks))
