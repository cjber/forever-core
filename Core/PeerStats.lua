local _, ns = ...

-- Bounded guild and group peer statistics for the Forever addons. ns.PeerStats.New(config) returns one instance per
-- addon: it sends that addon's own snapshot rows, stores validated rows from peers, and ranks a board. Nothing here
-- knows a metric, a label or a screen; the consumer names its metrics in `config` and draws its own UI.
--
-- config = {
--   addon    = "agf",                      -- wire addon id, 1-16 of [%w_-]
--   enabled  = function() return bool end, -- the saved setting; sharing is opt-out, so only an explicit false is off
--   db       = function() return table end, -- peer table owned by the caller; no table means off
--   snapshot = function() return { { metric=, subject=, value=, eventUnix= }, ... } end,
--   metrics  = { name = { subject = "all" | "numeric" | "qualified", first = bool } },
-- }
-- Subject modes also include "numeric_or_all" and "numeric_pair" (encounter_difficulty).
-- PeerStats.Listen(owner, config) observes config.addon's rows without taking over that addon's sender. Its
-- registration is private to owner, and it never sends a snapshot, even if one was supplied.
--
-- Saved layout: db[sender][metric][subject] = { value = n, eventUnix = n, relayed = true? }, with the sender's
-- display name saved beside the rows under DISPLAY_KEY. Keys stay compacted, so identity matching and saved data
-- never move.
--
-- Wire v1 on prefix WFAStats: "1|addon|metric|subject|value|unix" for the player's own rows, and v2 for rows heard
-- from a peer and passed on: "2|addon|metric|subject|value|unix|origin". GUILD, PARTY, RAID and INSTANCE_CHAT only.
-- A relayed row keeps the original player (origin) and its eventUnix: a client re-sends rows it has heard to its own
-- guild and group on its next Sync, never when a row arrives, so a relay cannot cascade. A relayed row replaces only
-- an older relayed row and never a row heard directly; a direct row always replaces a relayed one. A relay never
-- changes a saved identity, and a row from a foreign addon is ignored, so no suite-wide metric list exists. Old copies
-- match only "^1|" and drop v2 messages, so mixed installs stay compatible.
--
-- Every addon in the client shares one manager, which owns the send queue, the transport rate, the channel epochs and
-- the game events. The manager is module state: it is made once, when this file loads.

local PREFIX = "WFAStats"
local WIRE_VERSION = "1"
local RELAY_VERSION = "2"

-- Weekly baselines live beside the cumulative rows: `record.week`/`record.weekUnix` hold the first value heard this
-- week, and the player's own baseline sits under WEEKLY_KEY in the same metric/subject layout. Older saved tables have
-- neither, and both are optional, so an older copy still reads every row it wrote.
local WEEK_SECONDS = 7 * 86400
local WEEKLY_KEY = "\1week"
-- The display name saved beside a peer's metric rows. A metric name cannot contain a control byte, so this can never
-- collide with one.
local DISPLAY_KEY = "\1name"

local MAX_PAYLOAD = 128
local MAX_METRIC = 32
local MAX_SUBJECT = 24
local MAX_ADDON = 16
local MAX_NAME = 64
local MAX_VALUE = 1e9
local FUTURE_SECONDS = 300
local MAX_METRICS = 64
local MAX_PEERS = 100
local MAX_RELAYED_PEERS = 500
local MAX_SUBJECTS = 256
local MAX_ROWS = 1024
local MAX_QUEUE = 512
local MAX_SNAPSHOT = 2048
local MAX_SCAN_KEYS = 2000
local MAX_SCAN_SUBJECTS = 4096
local MAX_RATE_SENDERS = 200
local STALE_PEER_SECONDS = 30 * 86400
-- The freshest relay candidates, no older than 30 days. A relay is a hint, not a board dump; the shared transport
-- below spreads them over several Sync rounds instead of sending the whole store at once.
local MAX_RELAY_ROWS = 500
local RELAY_MAX_AGE = 30 * 86400
-- Per sender, per instance: room for a whole Field Guide snapshot, then ten rows a second.
local RECEIVE_BURST = 300
local RECEIVE_PER_SECOND = 10
-- Shared transport: the client's per-prefix budget, a burst of ten messages then one a second.
local SEND_BURST = 10
local SEND_PER_SECOND = 1
-- A relay round offers at most one burst; rows left over wait for the next round, which the manager starts once the
-- queue drains.
local RELAY_ROWS_PER_SYNC = SEND_BURST
local MAX_RETRIES = 5
local MAX_BACKOFF = 30
local MEMBERSHIP_DELAY = 1

local SUBJECT_MODES = { all = true, numeric = true, qualified = true, numeric_or_all = true, numeric_pair = true }
local ALLOWED_CHANNELS = { GUILD = true, PARTY = true, RAID = true, INSTANCE_CHAT = true }
local EVENTS = {
	"CHAT_MSG_ADDON",
	"GROUP_ROSTER_UPDATE",
	"PLAYER_GUILD_UPDATE",
	"PLAYER_ENTERING_WORLD",
	"PLAYER_REGEN_DISABLED",
	"PLAYER_REGEN_ENABLED",
}
local MEMBERSHIP_EVENTS = { GROUP_ROSTER_UPDATE = true, PLAYER_GUILD_UPDATE = true, PLAYER_ENTERING_WORLD = true }
local CHANNEL_ORDER = { "GUILD", "PARTY", "RAID", "INSTANCE_CHAT" }

---@param value any
---@param low number
---@param high number
---@return number|nil
local function IntIn(value, low, high)
	if type(value) ~= "number" or value ~= value or value < low or value > high or value ~= math.floor(value) then
		return nil
	end
	return value
end

---@param text any
---@return integer|nil
local function ParseInt(text, low, high)
	if type(text) ~= "string" or #text > 10 or not text:find("^%d+$") then
		return nil
	end
	return IntIn(tonumber(text), low, high)
end

local function Now()
	return GetServerTime and GetServerTime() or 0
end

-- Seconds until the next weekly reset, when this client can say. A restricted or malformed answer reads as unknown,
-- so the caller uses the Tuesday 15:00 UTC fallback rather than guessing at a week.
---@return number|nil
local function WeeklyRemaining()
	local api = rawget(_G, "C_DateAndTime")
	local get = type(api) == "table" and api.GetSecondsUntilWeeklyReset
	if type(get) ~= "function" then
		return nil
	end
	local ok, seconds = pcall(get)
	if ok and type(seconds) == "number" and seconds == seconds and seconds >= 0 and seconds <= WEEK_SECONDS then
		return seconds
	end
end

-- The instant the current week began: the client's reset countdown when it has one, else the last Tuesday 15:00 UTC.
---@param now number
---@return number
local function WeekStart(now)
	local remaining = WeeklyRemaining()
	if remaining then
		return now + remaining - WEEK_SECONDS
	end
	local date = os.date("!*t", now)
	if type(date) ~= "table" then
		return now - WEEK_SECONDS
	end
	local dayStart = now - (date.hour * 3600 + date.min * 60 + date.sec)
	local start = dayStart - (date.wday - 3) % 7 * 86400 + 15 * 3600
	if start > now then
		start = start - WEEK_SECONDS
	end
	return start
end

-- The same week start for a burst of rows stored at one instant: one client reset countdown answers for the second
-- it was read in. Without a server clock there is no second boundary to lean on, so it is read again each time.
local weekAt, weekStartAt
---@param now number
---@return number
local function WeekStartAt(now)
	if now ~= weekAt or now == 0 then
		weekAt, weekStartAt = now, WeekStart(now)
	end
	return weekStartAt
end

-- The first value heard this week, kept only while its timestamp is inside the current week.
---@param record table
---@param weekStart number
---@param now number
---@return number|nil value
---@return number|nil unix
local function SavedBaseline(record, weekStart, now)
	local value = IntIn(record.week, 0, MAX_VALUE)
	local unix = IntIn(record.weekUnix, 1, now + FUTURE_SECONDS)
	if value and unix and unix >= weekStart then
		return value, unix
	end
end

-- The earliest fresh baseline among a saved record and the row already in the store, or the current value when this
-- week has none yet. Used while rebuilding the saved table, where two spellings of one player merge.
---@param records table[]
---@param weekStart number
---@param now number
---@param value number
---@param unix number
---@return number
---@return number
local function BaselineOf(records, weekStart, now, value, unix)
	local bestValue, bestUnix
	for _, record in ipairs(records) do
		if type(record) == "table" then
			local base, baseUnix = SavedBaseline(record, weekStart, now)
			if base and baseUnix and (not bestUnix or baseUnix < bestUnix) then
				bestValue, bestUnix = base, baseUnix
			end
		end
	end
	return bestValue or value, bestUnix or unix
end

local function Compact(text)
	return (text:gsub("[%s%-]", ""))
end

local function LocalRealm()
	local realm = (GetNormalizedRealmName and GetNormalizedRealmName()) or (GetRealmName and GetRealmName())
	if type(realm) == "string" and realm ~= "" then
		return Compact(realm):lower()
	end
end

-- The realm as this client spells it, used to turn a stored key without one back into a sender-shaped origin.
---@return string|nil
local function LocalRealmName()
	local realm = (GetNormalizedRealmName and GetNormalizedRealmName()) or (GetRealmName and GetRealmName())
	if type(realm) == "string" and realm ~= "" then
		return realm
	end
end

local function Readable(name, realm)
	local canAccess = rawget(_G, "canaccessvalue")
	if canAccess and (not canAccess(name) or not canAccess(realm)) then
		return nil
	end
	return name, realm
end

-- Forever's client returns the surname as UnitName's second return. Blizzard's NameUtil joins the two with
-- Constants.CharacterNameSeparatorConsts.CHARACTERNAME_SURNAME_SEPARATOR; without that constant the second return is
-- the realm, as on a client with no surname, so only the first return is the player's name.
---@return string|nil
local function NameSeparator()
	local constants = rawget(_G, "Constants")
	local separators = type(constants) == "table" and constants.CharacterNameSeparatorConsts
	local separator = type(separators) == "table" and separators.CHARACTERNAME_SURNAME_SEPARATOR
	if type(separator) == "string" and separator ~= "" then
		return separator
	end
end

---@param unit string
---@return string|nil
local function UnitDisplayName(unit)
	local name, surname = Readable(UnitName(unit))
	if type(name) ~= "string" or name == "" then
		return nil
	end
	local separator = NameSeparator()
	if separator and type(surname) == "string" and surname ~= "" then
		return name .. separator .. surname
	end
	return name
end

local function OwnName()
	return UnitDisplayName("player")
end

-- The saved key and the lowercase identity for a sender. Spaces and hyphens leave the realm, and the local realm
-- leaves the name, so "Name", "Name-MyRealm" and "name-My Realm" are one player.
---@param sender any
---@return string|nil key
---@return string|nil identity
local function Identity(sender)
	if type(sender) ~= "string" or sender == "" or #sender > MAX_NAME or sender:find("[%c|]") then
		return nil
	end
	local name, realm = sender:match("^([^%-]+)%-(.+)$")
	name = Compact(name or sender)
	realm = realm and Compact(realm)
	if name == "" then
		return nil
	end
	if realm == "" or (realm and realm:lower() == LocalRealm()) then
		realm = nil
	end
	local key = realm and (name .. "-" .. realm) or name
	return key, key:lower()
end

-- The sender's name as received, without its realm. The key stays compacted; this is only what a row draws.
---@param sender any
---@return string|nil
local function DisplayName(sender)
	if type(sender) ~= "string" or sender == "" or #sender > MAX_NAME or sender:find("[%c|]") then
		return nil
	end
	local name = sender:match("^([^%-]+)%-") or sender
	return name ~= "" and name or nil
end

-- How many sender names are kept. A snapshot arrives as a burst of one player's rows, relayed or not, so the last few
-- names cover nearly every message; the fold itself depends only on the name.
local NAME_CACHE = 4

-- The compacted key, identity and display read from a sender or relay origin, remembered from the last message.
---@param self ForeverPeerStatsInstance
---@param name string
---@return string|nil key
---@return string|nil identity
---@return string|nil display
local function SenderNames(self, name)
	local cache = self.names
	for index = 1, #cache do
		local entry = cache[index]
		if entry.name == name then
			return entry.key, entry.identity, entry.display
		end
	end
	local key, identity = Identity(name)
	local entry = { name = name, key = key, identity = identity, display = DisplayName(name) }
	if #cache >= NAME_CACHE then
		cache[NAME_CACHE] = nil
	end
	table.insert(cache, 1, entry)
	return key, identity, entry.display
end

-- A display name read back from the saved table. It is drawn as it arrived, so spaces survive.
---@param value any
---@return string|nil
local function SavedDisplay(value)
	if type(value) ~= "string" or value == "" or #value > MAX_NAME or value:find("[%c|]") then
		return nil
	end
	return value
end

-- The display for a peer saved before display names: split the compacted name at its single inner ASCII capital
-- ("DirtyjokeLovetties" becomes "Dirtyjoke Lovetties"), else leave the saved key as it is. The next message from that
-- player replaces it.
---@param key string
---@return string
local function KeyDisplay(key)
	local name, realm = key:match("^([^%-]+)%-(.+)$")
	name = name or key
	local split
	for index = 2, #name - 1 do
		local byte = name:byte(index)
		if byte >= 65 and byte <= 90 then
			if split then
				return key
			end
			split = index
		end
	end
	if not split then
		return key
	end
	local spaced = name:sub(1, split - 1) .. " " .. name:sub(split)
	return realm and (spaced .. "-" .. realm) or spaced
end

-- The player's own identity, normalised exactly as an incoming sender, so a Forever two-part name ("Hel Io") and the
-- compacted key it arrives under ("HelIo") are the same player.
---@return string|nil identity
local function OwnIdentity()
	local name = OwnName()
	if not name then
		return nil
	end
	local _, identity = Identity(name)
	return identity or Compact(name):lower()
end

-- The player's own identity, read once a name is available: a session's name, surname and realm do not change.
---@param self ForeverPeerStatsInstance
---@return string|nil identity
local function SelfIdentity(self)
	local identity = self.ownIdentity
	if not identity then
		identity = OwnIdentity()
		self.ownIdentity = identity
	end
	return identity
end

---@param mode string
---@param subject any
local function ValidSubject(mode, subject)
	if type(subject) ~= "string" or subject == "" or #subject > MAX_SUBJECT then
		return false
	end
	if mode == "all" then
		return subject == "all"
	elseif mode == "numeric" then
		return subject:find("^%d+$") ~= nil and (subject == "0" or subject:sub(1, 1) ~= "0")
	elseif mode == "numeric_or_all" then
		return subject == "all" or ValidSubject("numeric", subject)
	elseif mode == "numeric_pair" then
		local first, second = subject:match("^([1-9]%d*)_(%d+)$")
		return first ~= nil and (second == "0" or second:sub(1, 1) ~= "0")
	elseif mode == "qualified" then
		return subject:find("^[%a_][%w_]*:[%w_%.%-]+$") ~= nil
	end
	return false
end

-- A first metric keeps the earliest event; any other keeps the highest cumulative value.
local function Better(first, old, value, unix)
	if not old then
		return true
	end
	if first then
		return unix < old.eventUnix or (unix == old.eventUnix and value > old.value)
	end
	return value > old.value or (value == old.value and unix > old.eventUnix)
end

-- A passed-on row is a snapshot of what the origin reported, so the newest one wins even when its value is lower.
-- A first metric still keeps the earliest event: a later relay cannot make the first kill earlier.
local function RelayBetter(first, old, value, unix)
	if not old then
		return true
	end
	if first then
		return unix < old.eventUnix or (unix == old.eventUnix and value > old.value)
	end
	return unix > old.eventUnix or (unix == old.eventUnix and value > old.value)
end

local function SortedStringKeys(source, limit)
	local keys = {}
	for key in pairs(source) do
		if type(key) == "string" then
			keys[#keys + 1] = key
		end
	end
	table.sort(keys)
	for index = #keys, limit + 1, -1 do
		keys[index] = nil
	end
	return keys
end

-- The client's send result codes, read once: the enum is fixed for the session and this runs on every pump.
local sendSuccess, sendThrottles
local function SendResultCodes()
	if not sendSuccess then
		local codes = Enum and Enum.SendAddonMessageResult
		sendSuccess = (codes and codes.Success) or 0
		sendThrottles = {
			[(codes and codes.AddonMessageThrottle) or 3] = true,
			[(codes and codes.ChannelThrottle) or 8] = true,
		}
	end
	return sendSuccess, sendThrottles
end

--------------------------------------------------------------------------------------------------------------------
-- Manager

local function CreateManager()
	local m = { order = {}, instances = {}, epoch = {} }
	local queue, queueIndex = {}, {}
	local timerPending, timerToken, syncPending = false, 0, false
	local available, groupSize, roster = {}, 0, ""
	local tokens, tokenTime, blockedUntil = SEND_BURST, nil, 0
	local inCombat = type(InCombatLockdown) == "function" and InCombatLockdown() == true or false
	local Pump

	local function Remove(position)
		local entry = table.remove(queue, position)
		queueIndex[entry.qk] = nil
	end

	function m.Schedule(delay)
		if timerPending or m.retired or not (C_Timer and C_Timer.After) then
			return
		end
		timerPending, timerToken = true, timerToken + 1
		local token = timerToken
		C_Timer.After(delay, function()
			if token == timerToken and not m.retired then
				Pump()
			end
		end)
	end

	-- The channels this client can send on now, in a fixed order, and the same as a set. An epoch rises each time a
	-- channel appears or its membership changes, so a row already sent there reaches the new audience.
	---@return string[] list
	---@return table<string, boolean> set
	function m.Channels()
		local now = {}
		if IsInGuild and IsInGuild() then
			now.GUILD = true
		end
		local instanceCategory = rawget(_G, "LE_PARTY_CATEGORY_INSTANCE")
		local category = rawget(_G, "LE_PARTY_CATEGORY_HOME")
		if instanceCategory and IsInGroup and IsInGroup(instanceCategory) then
			now.INSTANCE_CHAT = true
			category = instanceCategory
		elseif IsInRaid and IsInRaid() then
			now.RAID = true
		elseif IsInGroup and IsInGroup() then
			now.PARTY = true
		end
		local size = _G.GetNumGroupMembers and tonumber(_G.GetNumGroupMembers(category)) or 0
		local members = {}
		local raid = IsInRaid and IsInRaid(category)
		for index = 1, math.min(size, 40) do
			local unit = raid and ("raid" .. index) or (index == size and "player" or "party" .. index)
			local name, realm = Readable(UnitName(unit))
			members[#members + 1] = name and (name .. "-" .. (realm or "")) or unit
		end
		table.sort(members)
		local signature = table.concat(members, "|")
		local list = {}
		for _, channel in ipairs(CHANNEL_ORDER) do
			if now[channel] then
				list[#list + 1] = channel
				local changed = channel ~= "GUILD" and (size ~= groupSize or signature ~= roster)
				if not available[channel] or changed then
					m.epoch[channel] = (m.epoch[channel] or 0) + 1
				end
			end
		end
		available, groupSize, roster = now, size, signature
		return list, now
	end

	-- Queue one payload, coalescing on the (addon, channel, row) key. False when the queue is full; the row is not
	-- recorded as sent, so the next Sync offers it again.
	function m.Enqueue(inst, channel, key, payload, value, unix)
		local qk = inst.addon .. "|" .. channel .. "|" .. key
		local entry = queueIndex[qk]
		if not entry then
			if #queue >= MAX_QUEUE then
				return false
			end
			entry = { qk = qk, inst = inst, channel = channel, key = key }
			queue[#queue + 1] = entry
			queueIndex[qk] = entry
		end
		entry.payload, entry.value, entry.unix = payload, value, unix
		entry.gen, entry.epoch, entry.retries = inst.gen, m.epoch[channel] or 0, 0
		-- In combat the queue waits for PLAYER_REGEN_ENABLED rather than scheduling a pump that would only
		-- return; that keeps combat free of timers as well as sends.
		if not inCombat then
			m.Schedule(0)
		end
		return true
	end

	-- Drop every queued entry of one instance.
	function m.Purge(inst)
		local kept = {}
		for _, entry in ipairs(queue) do
			if entry.inst == inst then
				queueIndex[entry.qk] = nil
			else
				kept[#kept + 1] = entry
			end
		end
		for index = #queue, 1, -1 do
			queue[index] = nil
		end
		for index, entry in ipairs(kept) do
			queue[index] = entry
		end
	end

	function m.QueueSize()
		return #queue
	end

	function m.Register(inst)
		local key = inst.key or inst.addon
		local old = m.instances[key]
		if old == inst then
			return
		end
		if old then
			old:Retire()
		else
			m.order[#m.order + 1] = key
		end
		m.instances[key] = inst
	end

	function m.SyncAll()
		local count = #m.order
		for index = 1, count do
			local inst = m.instances[m.order[index]]
			if inst then
				pcall(inst.Sync, inst)
			end
		end
	end

	function Pump()
		timerPending = false
		if m.retired then
			return
		end
		-- Nothing leaves the client in combat. The queue keeps its entries and PLAYER_REGEN_ENABLED schedules
		-- this pump again, so a change made mid-fight is deferred rather than dropped.
		if inCombat or (type(InCombatLockdown) == "function" and InCombatLockdown() == true) then
			inCombat = true
			return
		end
		local now = GetTime()
		tokens = math.min(SEND_BURST, tokens + (now - (tokenTime or now)) * SEND_PER_SECOND)
		tokenTime = now
		local _, open = m.Channels()
		local count = #m.order
		for index = 1, count do
			local inst = m.instances[m.order[index]]
			if inst then
				inst:IsEnabled()
			end
		end
		local success, throttles = SendResultCodes()
		local send = C_ChatInfo and C_ChatInfo.SendAddonMessage
		local delay
		local position = 1
		while position <= #queue do
			local entry = queue[position]
			local inst = entry.inst
			if inst.dead or entry.gen ~= inst.gen or not inst.active or not open[entry.channel] or not send then
				Remove(position)
			elseif now < blockedUntil then
				delay = blockedUntil - now
				break
			elseif tokens < 1 then
				delay = (1 - tokens) / SEND_PER_SECOND
				break
			else
				local ok, result = pcall(send, PREFIX, entry.payload, entry.channel)
				if ok and (result == true or result == success) then
					tokens = tokens - 1
					inst:RecordSent(entry)
					Remove(position)
				elseif ok and throttles[result] then
					entry.retries = entry.retries + 1
					if entry.retries > MAX_RETRIES then
						Remove(position)
					else
						blockedUntil = now + math.min(MAX_BACKOFF, 2 ^ entry.retries)
						delay = blockedUntil - now
						break
					end
				else
					Remove(position)
				end
			end
		end
		-- Only rows refused for capacity, and relay rows still owed to a channel, are retried automatically. Transport
		-- failures remain eligible for the next consumer Sync, but cannot keep an overflow refill alive forever.
		if #queue == 0 then
			for _, addon in ipairs(m.order) do
				local inst = m.instances[addon]
				if inst and (next(inst.deferred) or inst.relayPending.head) then
					pcall(inst.Sync, inst, inst.deferred)
				end
			end
		end
		if #queue > 0 and delay then
			m.Schedule(delay)
		end
	end
	m.Pump = Pump

	function m.OnEvent(event, ...)
		if event == "CHAT_MSG_ADDON" then
			local prefix, text, channel, sender = ...
			if prefix ~= PREFIX then
				return
			end
			-- The count is read once, so an instance a consumer callback registers during the message waits for the
			-- next one, exactly as a snapshot of the order did.
			local count = #m.order
			for index = 1, count do
				local inst = m.instances[m.order[index]]
				if inst then
					inst:Receive(prefix, text, channel, sender)
				end
			end
		elseif event == "PLAYER_REGEN_DISABLED" then
			inCombat = true
		elseif event == "PLAYER_REGEN_ENABLED" then
			inCombat = false
			m.Schedule(0)
		elseif MEMBERSHIP_EVENTS[event] then
			if not (C_Timer and C_Timer.After) then
				m.SyncAll()
			elseif not syncPending then
				syncPending = true
				C_Timer.After(MEMBERSHIP_DELAY, function()
					syncPending = false
					if not m.retired then
						m.SyncAll()
					end
				end)
			end
		end
	end

	-- Hand the game events to a newer manager.
	function m.Retire()
		m.retired = true
		if m.frame and m.frame.UnregisterAllEvents then
			m.frame:UnregisterAllEvents()
		end
	end

	if C_ChatInfo and C_ChatInfo.RegisterAddonMessagePrefix then
		pcall(C_ChatInfo.RegisterAddonMessagePrefix, PREFIX)
	end
	if CreateFrame then
		local frame = CreateFrame("Frame")
		frame:SetScript("OnEvent", function(_, event, ...)
			m.OnEvent(event, ...)
		end)
		for _, event in ipairs(EVENTS) do
			frame:RegisterEvent(event)
		end
		m.frame = frame
	end
	return m
end

local manager = CreateManager()

-- The manager now published, which a newer copy may have replaced since this file ran.
local function Manager()
	return manager
end

--------------------------------------------------------------------------------------------------------------------
-- Relay queue

-- A relayed row's wire payload is built once, when the row is stored or changes. Two linked lists over the same
-- items keep that work off the Sync round: `relayOrder` holds every fresh candidate newest first, and `relayPending`
-- the rows still owed to an open channel, so a round walks only the rows it sends instead of the whole store.

---@param list table
---@param item table
---@param before table|nil the item to go in front of; nil appends
---@param prevField string
---@param nextField string
local function ListLink(list, item, before, prevField, nextField)
	local previous = list.tail
	if before then
		previous = before[prevField]
	end
	item[prevField], item[nextField] = previous, before
	if previous then
		previous[nextField] = item
	else
		list.head = item
	end
	if before then
		before[prevField] = item
	else
		list.tail = item
	end
end

---@param list table
---@param item table
---@param prevField string
---@param nextField string
local function ListUnlink(list, item, prevField, nextField)
	local previous, following = item[prevField], item[nextField]
	if previous then
		previous[nextField] = following
	else
		list.head = following
	end
	if following then
		following[prevField] = previous
	else
		list.tail = previous
	end
	item[prevField], item[nextField] = nil, nil
end

-- The sender-shaped origin a receiver runs Identity() and DisplayName() on: the stored display name, a hyphen, and
-- the realm the key leaves out or the relayer's own realm. Nil when no safe origin can be built.
---@param store table|nil
---@param key string
---@return string|nil origin
local function RelayOrigin(store, key)
	local peer = store and store[key]
	local name = key:match("^([^%-]+)") or key
	local display = type(peer) == "table" and SavedDisplay(peer[DISPLAY_KEY]) or nil
	if not display or display:find("%-") then
		display = KeyDisplay(name)
	end
	local realm = key:match("^[^%-]+%-(.+)$") or LocalRealmName()
	if not realm then
		return nil
	end
	local origin = display .. "-" .. realm
	if #origin > MAX_NAME or origin:find("[%c|]") then
		return nil
	end
	return origin
end

-- Newest first, then the identity, metric and subject, so a capped selection is the same on every client.
---@param a table
---@param b table
---@return boolean
local function RelayBefore(a, b)
	if a.unix ~= b.unix then
		return a.unix > b.unix
	end
	if a.identity ~= b.identity then
		return a.identity < b.identity
	end
	if a.metric ~= b.metric then
		return a.metric < b.metric
	end
	return a.subject < b.subject
end

-- Forget one candidate, with the sent and heard records only it could use.
---@param self ForeverPeerStatsInstance
---@param item table
local function RelayDrop(self, item)
	if item.owed then
		item.owed = nil
		ListUnlink(self.relayPending, item, "owedPrev", "owedNext")
	end
	ListUnlink(self.relayOrder, item, "prev", "next")
	if self.relayItems[item.key] == item then
		self.relayItems[item.key] = nil
		self.relayCount = self.relayCount - 1
	end
	local key = item.key
	for _, channel in ipairs(CHANNEL_ORDER) do
		local sendKey = channel .. "|" .. key
		self.sent[sendKey] = nil
		self.relayHeard[sendKey] = nil
	end
end

-- Put an unlinked item at its place in the newest-first order, and in the owed list while it still owes a send.
---@param self ForeverPeerStatsInstance
---@param item table
local function RelayPlace(self, item)
	local at = self.relayOrder.head
	while at and RelayBefore(at, item) do
		at = at.next
	end
	ListLink(self.relayOrder, item, at, "prev", "next")
	if item.owed then
		local owedAt = self.relayPending.head
		while owedAt and RelayBefore(owedAt, item) do
			owedAt = owedAt.owedNext
		end
		ListLink(self.relayPending, item, owedAt, "owedPrev", "owedNext")
	end
end

-- Record one stored row's wire payload. A message is built here when a row changes and in RelayBuild when the store
-- loads, so a Sync round never concatenates. Only a row whose event time moves backwards can change place under a full
-- cap; it keeps its place in the set rather than displacing a row the cap already let go, which is the one selection
-- the old whole-store scan could differ on.
---@param self ForeverPeerStatsInstance
---@param store table
---@param identity string
---@param metric string
---@param subject string
---@param value number
---@param unix number
---@param origin string|nil the peer's origin, when the caller already built it
local function RelayRow(self, store, identity, metric, subject, value, unix, origin)
	-- A row that is older than the full cap's oldest cannot enter, and the cap's tail is the first thing to compare
	-- with: inline so a rejected row allocates nothing, not even the key or a probe. Only the tail itself can be older
	-- than the tail and still be an item already held, so its fields continue to the update below.
	if self.relayCount >= MAX_RELAY_ROWS then
		local tail = self.relayOrder.tail
		if tail then
			local before
			if unix ~= tail.unix then
				before = unix > tail.unix
			elseif identity ~= tail.identity then
				before = identity < tail.identity
			elseif metric ~= tail.metric then
				before = metric < tail.metric
			else
				before = subject < tail.subject
			end
			if
				not before
				and (unix ~= tail.unix or identity ~= tail.identity or metric ~= tail.metric or subject ~= tail.subject)
			then
				return
			end
		end
	end
	local key = "r|" .. identity .. "|" .. metric .. "|" .. subject
	local item = self.relayItems[key]
	if not origin then
		local peerKey = self.index[identity]
		origin = peerKey and RelayOrigin(store, peerKey) or nil
	end
	local payload = origin and table.concat({ RELAY_VERSION, self.addon, metric, subject, value, unix, origin }, "|")
	if not payload or #payload > MAX_PAYLOAD then
		if item then
			RelayDrop(self, item)
		end
		return
	end
	if item then
		if item.owed then
			item.owed = nil
			ListUnlink(self.relayPending, item, "owedPrev", "owedNext")
		end
		ListUnlink(self.relayOrder, item, "prev", "next")
	else
		item = { key = key, identity = identity, metric = metric, subject = subject }
		self.relayItems[key] = item
		self.relayCount = self.relayCount + 1
	end
	item.value, item.unix, item.payload, item.owed = value, unix, payload, true
	RelayPlace(self, item)
	while self.relayCount > MAX_RELAY_ROWS do
		RelayDrop(self, self.relayOrder.tail)
	end
end

-- Build the candidate set once from a store a sanitize just rebuilt, so every later round only walks its queue. The
-- fresh rows are collected first and sorted once, rather than inserted into the list one at a time; a big store then
-- pays one sort instead of one walk of the cap per row.
---@param self ForeverPeerStatsInstance
---@param store table
---@param now number
local function RelayBuild(self, store, now)
	local item = self.relayOrder.head
	while item do
		local following = item.next
		RelayDrop(self, item)
		item = following
	end
	local oldest = now - RELAY_MAX_AGE
	local fresh = {}
	for identity, key in pairs(self.index) do
		local peer = store[key]
		local origin = type(peer) == "table" and RelayOrigin(store, key) or nil
		if type(peer) == "table" then
			for metric, subjects in pairs(peer) do
				if type(subjects) == "table" and self.metrics[metric] then
					for subject, record in pairs(subjects) do
						local unix = type(record) == "table" and record.eventUnix
						local value = type(record) == "table" and record.value
						if type(unix) == "number" and unix >= oldest and type(value) == "number" then
							fresh[#fresh + 1] = {
								identity = identity,
								metric = metric,
								subject = subject,
								unix = unix,
								value = value,
								origin = origin,
							}
						end
					end
				end
			end
		end
	end
	table.sort(fresh, RelayBefore)
	local kept = 0
	for _, row in ipairs(fresh) do
		if kept >= MAX_RELAY_ROWS then
			break
		end
		-- A row without a safe origin, or one whose message would be too long, is not a candidate; the next row takes
		-- the place the cap did not spend on it.
		local origin = row.origin
		if origin then
			local payload =
				table.concat({ RELAY_VERSION, self.addon, row.metric, row.subject, row.value, row.unix, origin }, "|")
			if #payload <= MAX_PAYLOAD then
				local key = "r|" .. row.identity .. "|" .. row.metric .. "|" .. row.subject
				local candidate = {
					key = key,
					identity = row.identity,
					metric = row.metric,
					subject = row.subject,
					value = row.value,
					unix = row.unix,
					payload = payload,
					owed = true,
				}
				self.relayItems[key] = candidate
				self.relayCount = self.relayCount + 1
				ListLink(self.relayOrder, candidate, nil, "prev", "next")
				ListLink(self.relayPending, candidate, nil, "owedPrev", "owedNext")
				kept = kept + 1
			end
		end
	end
end

-- A peer's display name changed: the name is part of every payload, and the order does not move with it.
---@param self ForeverPeerStatsInstance
---@param store table
---@param identity string
local function RelayRename(self, store, identity)
	local peerKey = self.index[identity]
	local origin = peerKey and RelayOrigin(store, peerKey) or nil
	for _, item in pairs(self.relayItems) do
		if item.identity == identity then
			local payload = origin
				and table.concat(
					{ RELAY_VERSION, self.addon, item.metric, item.subject, item.value, item.unix, origin },
					"|"
				)
			if not payload or #payload > MAX_PAYLOAD then
				RelayDrop(self, item)
			else
				item.payload = payload
			end
		end
	end
end

-- A peer left the store: its rows go with it.
---@param self ForeverPeerStatsInstance
---@param identity string
local function RelayForget(self, identity)
	for _, item in pairs(self.relayItems) do
		if item.identity == identity then
			RelayDrop(self, item)
		end
	end
end

-- This row is on every open channel: it stays a candidate, but no round owes it any more.
---@param self ForeverPeerStatsInstance
---@param item table
local function RelaySettle(self, item)
	item.owed = nil
	ListUnlink(self.relayPending, item, "owedPrev", "owedNext")
end

-- Every fresh candidate is owed again: a channel changed its audience, or every sent record was just cleared. The
-- owed list is rebuilt from the order list, so it stays newest first.
---@param self ForeverPeerStatsInstance
---@param now number
local function RelayRepend(self, now)
	local pending = self.relayPending
	local item = pending.head
	while item do
		local following = item.owedNext
		item.owed, item.owedPrev, item.owedNext = nil, nil, nil
		item = following
	end
	pending.head, pending.tail = nil, nil
	local oldest = now - RELAY_MAX_AGE
	item = self.relayOrder.head
	while item do
		local following = item.next
		if item.unix < oldest then
			RelayDrop(self, item)
		else
			item.owed = true
			ListLink(pending, item, nil, "owedPrev", "owedNext")
		end
		item = following
	end
end

--------------------------------------------------------------------------------------------------------------------
-- Saved state

-- Rebuild `raw` in place as the canonical layout: unknown metrics, bad subjects and values, own name and duplicate
-- identities removed, rows and peers capped. The result depends only on the content, never on iteration order.
---@param self ForeverPeerStatsInstance
local function SanitizeStore(self, raw)
	local now = Now()
	local weekStart = WeekStart(now)
	local own = OwnIdentity()
	local merged, order = {}, {}
	for _, key in ipairs(SortedStringKeys(raw, MAX_SCAN_KEYS)) do
		local clean, identity = Identity(key)
		local peerRaw = raw[key]
		if clean and identity and identity ~= own and type(peerRaw) == "table" then
			local peer = merged[identity]
			local display = SavedDisplay(peerRaw[DISPLAY_KEY])
			if not peer then
				peer = { key = clean, identity = identity, rows = {}, display = display }
				merged[identity], order[#order + 1] = peer, identity
			elseif not peer.display then
				peer.display = display
			end
			for _, metric in ipairs(self.metricList) do
				local subjects = peerRaw[metric]
				if type(subjects) == "table" then
					local config = self.metrics[metric]
					for _, subject in ipairs(SortedStringKeys(subjects, MAX_SCAN_SUBJECTS)) do
						local record = subjects[subject]
						if ValidSubject(config.subject, subject) and type(record) == "table" then
							local value = IntIn(record.value, 0, MAX_VALUE)
							local unix = IntIn(record.eventUnix, 1, now + FUTURE_SECONDS)
							local slot = metric .. "|" .. subject
							local previous = peer.rows[slot]
							local relayed = record.relayed == true
							local previousRelayed = previous ~= nil and previous.relayed == true
							local better
							if previous and previousRelayed ~= relayed then
								-- A direct row beats a relayed one whatever its value; a relay never overwrites one
								-- that was heard directly, even when it is newer.
								better = previousRelayed
							else
								better = Better(config.first, previous, value, unix)
							end
							if value and unix and better then
								local row = {
									metric = metric,
									subject = subject,
									value = value,
									eventUnix = unix,
									relayed = relayed or nil,
								}
								if not config.first then
									row.week, row.weekUnix =
										BaselineOf({ record, previous }, weekStart, now, value, unix)
								end
								peer.rows[slot] = row
							end
						end
					end
				end
			end
		end
	end

	-- The player's own baseline shares the peer layout but has its own key, so a saved table never lists the player as
	-- a peer. Keep only rows inside the current week.
	local ownWeek, ownRows = {}, 0
	local ownRaw = raw[WEEKLY_KEY]
	if type(ownRaw) == "table" then
		for _, metric in ipairs(self.metricList) do
			local subjects = ownRaw[metric]
			if type(subjects) == "table" then
				local config = self.metrics[metric]
				for _, subject in ipairs(SortedStringKeys(subjects, MAX_SCAN_SUBJECTS)) do
					local record = subjects[subject]
					if ownRows < MAX_ROWS and ValidSubject(config.subject, subject) and type(record) == "table" then
						local value = IntIn(record.value, 0, MAX_VALUE)
						local unix = IntIn(record.eventUnix, 1, now + FUTURE_SECONDS)
						if value and unix and unix >= weekStart then
							ownWeek[metric] = ownWeek[metric] or {}
							ownWeek[metric][subject] = { value = value, eventUnix = unix }
							ownRows = ownRows + 1
						end
					end
				end
			end
		end
	end

	local peers = {}
	for _, identity in ipairs(order) do
		local peer = merged[identity]
		local list = {}
		for _, row in pairs(peer.rows) do
			list[#list + 1] = row
		end
		table.sort(list, function(a, b)
			if a.eventUnix ~= b.eventUnix then
				return a.eventUnix > b.eventUnix
			end
			if a.metric ~= b.metric then
				return a.metric < b.metric
			end
			return a.subject < b.subject
		end)
		local kept, perMetric = {}, {}
		for _, row in ipairs(list) do
			if #kept < MAX_ROWS and (perMetric[row.metric] or 0) < MAX_SUBJECTS then
				kept[#kept + 1] = row
				perMetric[row.metric] = (perMetric[row.metric] or 0) + 1
			end
		end
		if #kept > 0 then
			peer.list, peer.latest = kept, kept[1].eventUnix
			peer.relayOnly = true
			for _, row in ipairs(kept) do
				if row.relayed ~= true then
					peer.relayOnly = false
					break
				end
			end
			peers[#peers + 1] = peer
		end
	end
	table.sort(peers, function(a, b)
		if a.latest ~= b.latest then
			return a.latest > b.latest
		end
		return a.identity < b.identity
	end)
	-- Two caps: players heard directly keep the old 100, players only ever passed on keep 500. A relay-only peer
	-- never takes the place of one heard directly.
	local direct, relayed = {}, {}
	for _, peer in ipairs(peers) do
		if peer.relayOnly then
			relayed[#relayed + 1] = peer
		else
			direct[#direct + 1] = peer
		end
	end
	for index = #direct, MAX_PEERS + 1, -1 do
		direct[index] = nil
	end
	for index = #relayed, MAX_RELAYED_PEERS + 1, -1 do
		relayed[index] = nil
	end

	for key in pairs(raw) do
		raw[key] = nil
	end
	self.index, self.latest = {}, {}
	self.peerCount, self.relayedCount = #direct, #relayed
	self.relayOnly, self.heardOn, self.relayHeard = {}, {}, {}
	local function Save(peer)
		local saved = {}
		if peer.display then
			saved[DISPLAY_KEY] = peer.display
		end
		for _, row in ipairs(peer.list) do
			saved[row.metric] = saved[row.metric] or {}
			saved[row.metric][row.subject] = {
				value = row.value,
				eventUnix = row.eventUnix,
				week = row.week,
				weekUnix = row.weekUnix,
				relayed = row.relayed == true or nil,
			}
		end
		raw[peer.key] = saved
		self.index[peer.identity], self.latest[peer.identity] = peer.key, peer.latest
		if peer.relayOnly then
			self.relayOnly[peer.identity] = true
		end
	end
	for _, peer in ipairs(direct) do
		Save(peer)
	end
	for _, peer in ipairs(relayed) do
		Save(peer)
	end
	if next(ownWeek) then
		raw[WEEKLY_KEY] = ownWeek
	end
	RelayBuild(self, raw, now)
	self.revision = self.revision + 1
end

-- A consumer callback runs in the registering addon's SafeCall, so a failure lands in that addon's journal.
---@param config table
---@param label string
---@param fn function
---@return boolean ok, any ...
local function RunSafe(config, label, fn, ...)
	local safe = type(config) == "table" and config.safeCall
	if safe then
		return safe(label, fn, ...)
	end
	if ns.SafeCall then
		return ns.SafeCall(label, fn, ...)
	end
	return pcall(fn, ...)
end

-- The caller's peer table, sanitized the first time it is seen; nil while there is none.
---@param self ForeverPeerStatsInstance
local function EnsureStore(self)
	local ok, store = RunSafe(self.config, "peer stats database", self.config.db)
	if not ok or type(store) ~= "table" then
		return nil
	end
	if store ~= self.store then
		SanitizeStore(self, store)
		self.store = store
	end
	return store
end

--------------------------------------------------------------------------------------------------------------------
-- Instance

---@class ForeverPeerStatsInstance
---@field config table
---@field addon string
---@field key string
---@field readOnly boolean
---@field dead boolean
---@field active boolean
---@field override boolean|nil
---@field gen integer
---@field sent table
---@field observed table<string, {value: number, unix: number, item: table}>
---@field sentRows table<string, boolean> the snapshot send keys the last round offered
---@field weekLocal table<string, {value: number, eventUnix: number}> the player's own baselines while there is no db
---@field deferred table<string, boolean>
---@field rate table
---@field rateCount integer
---@field index table<string, string>
---@field latest table<string, integer>
---@field peerCount integer peers with at least one row heard directly
---@field relayedCount integer peers whose every row arrived as a relay
---@field relayOnly table<string, boolean> the identities that count toward MAX_RELAYED_PEERS
---@field heardOn table<string, table<string, boolean>> channels an origin was heard on directly this session
---@field relayHeard table<string, {value: number, unix: number}> `channel|r|...` relayed rows a channel already carries
---@field metrics table<string, {subject: string, first: boolean}>
---@field metricList string[]
---@field store table|nil
---@field relayOrder {head: table|nil, tail: table|nil} every fresh relay candidate, newest first
---@field relayPending {head: table|nil, tail: table|nil} the candidates still owed to an open channel
---@field relayItems table<string, table> a relay candidate by row key
---@field relayCount integer candidates held, at most MAX_RELAY_ROWS
---@field relayEpoch table<string, integer> the epoch each channel had when the rows were last offered
---@field names {name: string, key: string|nil, identity: string|nil, display: string|nil}[] the last names read
---@field observedCount integer rows in the last accepted snapshot
---@field ownIdentity string|nil the player's identity, read once a name is available
---@field revision integer the cache key LeaderboardsData sums; raised when a stored row or snapshot changes
local Instance = {}
Instance.__index = Instance

-- Queued sends gone, sent cache reset: nothing queued before this call can be sent after it, and every relay row is
-- owed to its channels again.
function Instance:Cancel()
	self.gen = self.gen + 1
	self.sent = {}
	self.deferred = {}
	RelayRepend(self, Now())
	local current = Manager()
	if current then
		current.Purge(self)
	end
end

function Instance:Retire()
	self.dead = true
	self.active = false
	self:Cancel()
end

-- Whether this instance may send, receive and show peers now. Saving is opt-out: only an explicit false from the
-- saved setting is off, so a missing setting (or no setting function at all) shares once a database exists.
-- SetEnabled(false) overrides it until SetEnabled(true), and a missing database still means off.
function Instance:IsEnabled()
	local on = false
	if not self.dead and self.override ~= false then
		local allowed = true
		if type(self.config.enabled) == "function" then
			local ok, value = RunSafe(self.config, "peer stats enabled", self.config.enabled)
			allowed = not ok or value ~= false
		end
		on = allowed and EnsureStore(self) ~= nil or false
	end
	if self.active and not on then
		self:Cancel()
	end
	if self.active ~= on then
		self.revision = self.revision + 1
	end
	self.active = on
	return on
end

-- The cache key UI/Leaderboards.lua reads through a board's `revision` callback. It rises whenever a stored peer row,
-- the player's own snapshot or the enabled state changes, so an open window and a tooltip hover rebuild only then.
---@return integer
function Instance:Revision()
	return self.revision
end

function Instance:RecordSent(entry)
	if entry.gen == self.gen then
		self.sent[entry.channel .. "|" .. entry.key] =
			{ key = entry.key, value = entry.value, unix = entry.unix, epoch = entry.epoch }
	end
end

-- Offer the consumer's snapshot, then the newest rows heard from peers, to every open channel. A relayed row skips a
-- channel the origin was heard on directly this session, since that audience already has it. Rows unchanged since
-- their last successful send on a channel are skipped. Returns how many sends were queued.
function Instance:Sync(onlyDeferred)
	self.deferred = {}
	local current = Manager()
	if self.readOnly or not current or not self:IsEnabled() then
		return 0
	end
	local channels = current.Channels()
	if #channels == 0 then
		return 0
	end
	local now = Now()
	local list, byKey, present = {}, {}, {}
	if type(self.config.snapshot) == "function" then
		local ok, rows = RunSafe(self.config, "peer stats snapshot", self.config.snapshot)
		if ok and type(rows) == "table" then
			local previous = self.observed
			local observed, count = {}, 0
			for index = 1, math.min(#rows, MAX_SNAPSHOT) do
				local row = rows[index]
				local config = type(row) == "table" and type(row.metric) == "string" and self.metrics[row.metric]
				if config and ValidSubject(config.subject, row.subject) then
					local value = type(row.value) == "number" and row.value == row.value and math.floor(row.value)
						or nil
					value = value and IntIn(value, 0, MAX_VALUE)
					local key = row.metric .. "|" .. row.subject
					local unix = IntIn(row.eventUnix, 1, now + FUTURE_SECONDS)
					local cached = previous[key]
					if not unix and not config.first and (row.eventUnix == nil or type(row.eventUnix) == "number") then
						unix = cached and cached.value == value and cached.unix or now
					end
					if value and unix then
						local item, slot
						if cached and cached.value == value and cached.unix == unix then
							-- Unchanged: the payload built when this row last changed is still the one to send.
							item, slot = cached.item, cached
						else
							item = { key = key, value = value, unix = unix }
							item.payload =
								table.concat({ WIRE_VERSION, self.addon, row.metric, row.subject, value, unix }, "|")
							slot = { value = value, unix = unix, item = item }
						end
						if not observed[key] then
							count = count + 1
						end
						observed[key] = slot
						if byKey[key] then
							list[byKey[key]] = item
						else
							list[#list + 1] = item
							byKey[key] = #list
						end
					end
				end
			end
			-- The player's own snapshot is the other half of a board, so a change there invalidates the same cache
			-- as a peer row. An unchanged snapshot leaves the revision alone, and with it a hover's single lookup.
			local changed = count ~= self.observedCount
			if not changed then
				for key, slot in pairs(observed) do
					local old = previous[key]
					if not old or old.value ~= slot.value or old.unix ~= slot.unix then
						changed = true
						break
					end
				end
			end
			if changed then
				self.revision = self.revision + 1
			end
			self.observed, self.observedCount = observed, count
		end
	end

	-- A channel appeared or its audience changed, so every row is owed there again, exactly as its new epoch implies.
	local epochs, stale = self.relayEpoch, false
	for _, channel in ipairs(channels) do
		local epoch = current.epoch[channel] or 0
		if epochs[channel] ~= epoch then
			epochs[channel] = epoch
			stale = true
		end
	end
	if stale then
		RelayRepend(self, now)
	end

	-- The player's own rows go to every open channel.
	local queued = 0
	for _, item in ipairs(list) do
		for _, channel in ipairs(channels) do
			local sendKey = channel .. "|" .. item.key
			present[sendKey] = true
			local last = self.sent[sendKey]
			local same = last
				and last.value == item.value
				and last.unix == item.unix
				and last.epoch == (current.epoch[channel] or 0)
			if not same and (not onlyDeferred or onlyDeferred[sendKey]) then
				if current.Enqueue(self, channel, item.key, item.payload, item.value, item.unix) then
					queued = queued + 1
				else
					self.deferred[sendKey] = true
				end
			end
		end
	end
	local previousRows = self.sentRows or {}
	for sendKey in pairs(previousRows) do
		if not present[sendKey] then
			self.sent[sendKey] = nil
		end
	end
	self.sentRows = present

	-- A relay round offers one burst of messages; the rows it did not reach stay at the head of its queue, so the
	-- manager starts the next round once this one has drained. A round therefore walks the rows it sends, never the
	-- store, and every Sync stays inside the client's per-prefix budget however large the store is.
	local relayBudget = RELAY_ROWS_PER_SYNC
	local oldest = now - RELAY_MAX_AGE
	local item = self.relayPending.head
	while item and relayBudget > 0 do
		local following = item.owedNext
		if item.unix < oldest then
			RelayDrop(self, item)
		else
			local skip = self.heardOn[item.identity]
			local settled = true
			for _, channel in ipairs(channels) do
				if not (skip and skip[channel]) then
					local sendKey = channel .. "|" .. item.key
					local last = self.sent[sendKey]
					local heard = self.relayHeard[sendKey]
					local same = (
						last
						and last.value == item.value
						and last.unix == item.unix
						and last.epoch == (current.epoch[channel] or 0)
					) or (heard and heard.value == item.value and heard.unix == item.unix)
					if not same then
						if current.Enqueue(self, channel, item.key, item.payload, item.value, item.unix) then
							queued = queued + 1
							relayBudget = relayBudget - 1
						else
							settled = false
						end
					end
				end
			end
			if settled then
				RelaySettle(self, item)
			end
		end
		item = following
	end
	return queued
end

-- Explicit opt-out cancels this instance's queue at once and hides peers; opt-in resends everything.
---@param flag boolean
---@return boolean enabled
function Instance:SetEnabled(flag)
	if self.dead then
		return false
	end
	if flag then
		self.override = nil
		self:Cancel()
		if self:IsEnabled() then
			self:Sync()
			return true
		end
		return false
	end
	self.override = false
	if self.active then
		self.revision = self.revision + 1
	end
	self.active = false
	self:Cancel()
	return false
end

---@param self ForeverPeerStatsInstance
local function AllowSender(self, identity)
	local now = GetTime()
	local bucket = self.rate[identity]
	if not bucket then
		if self.rateCount >= MAX_RATE_SENDERS then
			local oldest
			for key, other in pairs(self.rate) do
				if
					not oldest
					or other.last < self.rate[oldest].last
					or (other.last == self.rate[oldest].last and key < oldest)
				then
					oldest = key
				end
			end
			self.rate[oldest], self.rateCount = nil, self.rateCount - 1
		end
		bucket = { tokens = RECEIVE_BURST, last = now }
		self.rate[identity], self.rateCount = bucket, self.rateCount + 1
	end
	bucket.tokens = math.min(RECEIVE_BURST, bucket.tokens + math.max(0, now - bucket.last) * RECEIVE_PER_SECOND)
	bucket.last = now
	if bucket.tokens < 1 then
		return false
	end
	bucket.tokens = bucket.tokens - 1
	return true
end

-- Drop one peer from every in-memory index, including the channel memory that bounds itself on the peer caps.
---@param self ForeverPeerStatsInstance
---@param identity string
local function DropPeer(self, identity)
	local key = self.index[identity]
	if not key then
		return
	end
	if self.relayOnly[identity] then
		self.relayOnly[identity] = nil
		self.relayedCount = self.relayedCount - 1
	else
		self.peerCount = self.peerCount - 1
	end
	self.store[key] = nil
	RelayForget(self, identity)
	self.index[identity], self.latest[identity], self.heardOn[identity] = nil, nil, nil
end

-- Make room for a directly heard peer by dropping the least recently active direct peer, but only when it is stale.
-- A relay-only peer never makes room this way.
---@param self ForeverPeerStatsInstance
local function EvictStalePeer(self)
	local oldest
	for identity, latest in pairs(self.latest) do
		if
			not self.relayOnly[identity]
			and (not oldest or latest < self.latest[oldest] or (latest == self.latest[oldest] and identity < oldest))
		then
			oldest = identity
		end
	end
	if oldest and self.latest[oldest] < Now() - STALE_PEER_SECONDS then
		DropPeer(self, oldest)
		return true
	end
	return false
end

-- Make room for a new relay-only peer by dropping the least recently active relay-only one, stale or not.
---@param self ForeverPeerStatsInstance
local function EvictRelayedPeer(self)
	local oldest
	for identity in pairs(self.relayOnly) do
		if
			not oldest
			or self.latest[identity] < self.latest[oldest]
			or (self.latest[identity] == self.latest[oldest] and identity < oldest)
		then
			oldest = identity
		end
	end
	if oldest then
		DropPeer(self, oldest)
		return true
	end
	return false
end

-- Count a peer as directly heard once one of its rows is stored without the relay mark.
---@param self ForeverPeerStatsInstance
---@param identity string
local function MakeDirect(self, identity)
	if self.relayOnly[identity] then
		self.relayOnly[identity] = nil
		self.relayedCount = self.relayedCount - 1
		self.peerCount = self.peerCount + 1
	end
end

---@param self ForeverPeerStatsInstance
local function Apply(self, key, identity, display, config, metric, subject, value, unix, relayed)
	local store = self.store
	if not store then
		return false, "disabled"
	end
	local peerKey = self.index[identity]
	local peer = peerKey and store[peerKey]
	local changed = false
	if not peer then
		if relayed then
			if self.relayedCount >= MAX_RELAYED_PEERS and not EvictRelayedPeer(self) then
				return false, "peers"
			end
			peer = {}
			store[key], self.index[identity] = peer, key
			self.relayOnly[identity] = true
			self.relayedCount = self.relayedCount + 1
		else
			if self.peerCount >= MAX_PEERS and not EvictStalePeer(self) then
				return false, "peers"
			end
			peer = {}
			store[key], self.index[identity] = peer, key
			self.peerCount = self.peerCount + 1
		end
		changed = true
	end
	-- The display name is the sender's own spelling, saved beside the compacted key. A stale row still replaces an
	-- older row's missing or run-together name. A relay may only fill a missing name, never change a saved one.
	if display and (not relayed or peer[DISPLAY_KEY] == nil) and peer[DISPLAY_KEY] ~= display then
		peer[DISPLAY_KEY] = display
		changed = true
		if peerKey then
			-- The name is part of every payload this peer already has queued.
			RelayRename(self, store, identity)
		end
	end
	local subjects = peer[metric]
	local record = subjects and subjects[subject]
	if record then
		if relayed and record.relayed ~= true then
			-- A row heard directly always outranks a passed-on one, whatever the values say.
			if changed then
				self.revision = self.revision + 1
			end
			return false, "direct"
		end
		if not relayed and record.relayed == true then
			-- A direct row always replaces a relayed one, even a lower value, and clears the mark.
			record.value, record.eventUnix, record.relayed = value, unix, nil
			MakeDirect(self, identity)
		else
			local better
			if relayed and record.relayed == true then
				better = RelayBetter(config.first, record, value, unix)
			else
				better = Better(config.first, record, value, unix)
			end
			if not better then
				if changed then
					self.revision = self.revision + 1
					return true
				end
				return false, "stale"
			end
			record.value, record.eventUnix, record.relayed = value, unix, relayed or nil
		end
	else
		local total, inMetric = 0, 0
		for name, rows in pairs(peer) do
			if type(rows) == "table" then
				for _ in pairs(rows) do
					total = total + 1
					if name == metric then
						inMetric = inMetric + 1
					end
				end
			end
		end
		if total >= MAX_ROWS or inMetric >= MAX_SUBJECTS then
			if changed then
				self.revision = self.revision + 1
			end
			return false, "rows"
		end
		subjects = subjects or {}
		record = { value = value, eventUnix = unix, relayed = relayed or nil }
		peer[metric], subjects[subject] = subjects, record
		if not relayed then
			MakeDirect(self, identity)
		end
	end
	-- The first value heard this week is the baseline a weekly board subtracts. A baseline from before the current
	-- reset is replaced by this observation, which is then the first one heard this week.
	if not config.first then
		local now = Now()
		local baseline = SavedBaseline(record, WeekStartAt(now), now)
		if not baseline then
			record.week, record.weekUnix = value, unix
		end
	end
	RelayRow(self, store, identity, metric, subject, record.value, record.eventUnix)
	if unix > (self.latest[identity] or 0) then
		self.latest[identity] = unix
	end
	self.revision = self.revision + 1
	return true
end

-- One addon message. Returns true when it changed a saved row, else false and why.
---@return boolean changed
---@return string? reason
function Instance:Receive(prefix, payload, channel, sender)
	if self.dead or prefix ~= PREFIX then
		return false, "prefix"
	end
	if type(payload) ~= "string" or #payload > MAX_PAYLOAD then
		return false, "payload"
	end
	if not ALLOWED_CHANNELS[channel] then
		return false, "channel"
	end
	-- "1|" or "2|", and this addon's field, by byte: a foreign message costs no capture or concatenation.
	local marker = payload:byte(1)
	if (marker ~= 49 and marker ~= 50) or payload:byte(2) ~= 124 then
		return false, "addon"
	end
	if payload:find(self.addon, 3, true) ~= 3 or payload:byte(3 + #self.addon) ~= 124 then
		return false, "addon"
	end
	if not self:IsEnabled() then
		return false, "disabled"
	end
	local key, identity, display = SenderNames(self, sender)
	local own = SelfIdentity(self)
	if not key or not identity or identity == own then
		return false, "sender"
	end
	if not AllowSender(self, identity) then
		return false, "rate"
	end
	local metric, subject, valueText, unixText, origin
	if marker == 50 then
		metric, subject, valueText, unixText, origin =
			payload:match("^2|[^|]*|([^|]*)|([^|]*)|([^|]*)|([^|]*)|([^|]*)$")
		local originKey, originIdentity, originDisplay
		if origin then
			originKey, originIdentity, originDisplay = SenderNames(self, origin)
		end
		if not originKey or originIdentity == own or originIdentity == identity then
			return false, "relay"
		end
		local config = metric and #metric <= MAX_METRIC and self.metrics[metric]
		if not config or not ValidSubject(config.subject, subject) then
			return false, "metric"
		end
		local value = ParseInt(valueText, 0, MAX_VALUE)
		local unix = ParseInt(unixText, 1, Now() + FUTURE_SECONDS)
		if not value or not unix then
			return false, "value"
		end
		local changed, why =
			Apply(self, originKey, originIdentity, originDisplay, config, metric, subject, value, unix, true)
		-- This channel already carries this exact row: without the note every listener would pass the same row back
		-- to the channel it came from, once per member. Only a row the relay holds keeps the note, so the memory
		-- stays inside the relay cap rather than growing with every row a stranger sends.
		local relayKey = "r|" .. originIdentity .. "|" .. metric .. "|" .. subject
		if self.relayItems[relayKey] then
			self.relayHeard[channel .. "|" .. relayKey] = { value = value, unix = unix }
		end
		return changed, why
	end
	metric, subject, valueText, unixText = payload:match("^1|[^|]*|([^|]*)|([^|]*)|([^|]*)|([^|]*)$")
	local config = metric and #metric <= MAX_METRIC and self.metrics[metric]
	if not config or not ValidSubject(config.subject, subject) then
		return false, "metric"
	end
	local value = ParseInt(valueText, 0, MAX_VALUE)
	local unix = ParseInt(unixText, 1, Now() + FUTURE_SECONDS)
	if not value or not unix then
		return false, "value"
	end
	local changed, why = Apply(self, key, identity, display, config, metric, subject, value, unix, false)
	if self.index[identity] then
		---@type table<string, boolean>|nil
		local heard = self.heardOn[identity]
		if not heard then
			heard = {}
			self.heardOn[identity] = heard
		end
		heard[channel] = true
	end
	return changed, why
end

-- Whether this call includes rows heard only through a relay. Only Core/LeaderboardsData.lua sets it, and only for
-- the length of one board call.
---@return boolean
local function IncludeRelayed()
	local current = Manager()
	return current ~= nil and current.includeRelayed == true
end

-- A deep copy of every cached peer's metric tables in the saved layout; empty while disabled. Relayed rows stay out
-- unless the current board call asked for them.
function Instance:Shared()
	local copy = {}
	if not self:IsEnabled() then
		return copy
	end
	local relayed = IncludeRelayed()
	for peer, metrics in pairs(self.store) do
		local saved = {}
		for metric, subjects in pairs(metrics) do
			if type(subjects) == "table" then
				local rows = {}
				for subject, record in pairs(subjects) do
					if relayed or record.relayed ~= true then
						rows[subject] = {
							value = record.value,
							eventUnix = record.eventUnix,
							week = record.week,
							weekUnix = record.weekUnix,
							relayed = record.relayed == true or nil,
						}
					end
				end
				if next(rows) then
					saved[metric] = rows
				end
			end
		end
		if next(saved) then
			copy[peer] = saved
		end
	end
	return copy
end

-- What a peer's row draws: the saved display name, else the old key split at its single inner ASCII capital.
---@param self ForeverPeerStatsInstance
---@param key string
---@return string
local function PeerDisplay(self, key)
	local peer = self.store and self.store[key]
	local saved = type(peer) == "table" and SavedDisplay(peer[DISPLAY_KEY])
	return saved or KeyDisplay(key)
end

-- Ranked rows for one metric and subject: the personal row always, peers only while enabled. A first metric ranks by
-- earliest eventUnix (a row without one last); any other by value, highest first. Ties fall to the lowercase
-- identity, so the order never changes between runs. Rows: { rank, name, identity, value, eventUnix, self }.
---@param metric string
---@param subject? string defaults to "all"
---@param localValue? number
---@param localEventUnix? number
function Instance:Board(metric, subject, localValue, localEventUnix)
	subject = subject or "all"
	local config = self.metrics[metric]
	local first = config and config.first
	local name = OwnName() or "player"
	local rows = {
		{
			name = name,
			identity = SelfIdentity(self) or name:lower(),
			value = IntIn(type(localValue) == "number" and math.floor(localValue) or nil, 0, MAX_VALUE) or 0,
			eventUnix = IntIn(localEventUnix, 1, Now() + FUTURE_SECONDS),
			self = true,
		},
	}
	if config and ValidSubject(config.subject, subject) and self:IsEnabled() then
		local relayed = IncludeRelayed()
		for identity, key in pairs(self.index) do
			local subjects = self.store[key] and self.store[key][metric]
			local record = subjects and subjects[subject]
			if record and identity ~= rows[1].identity and (relayed or record.relayed ~= true) then
				rows[#rows + 1] = {
					name = PeerDisplay(self, key),
					identity = identity,
					value = record.value,
					eventUnix = record.eventUnix,
					relayed = record.relayed == true or nil,
				}
			end
		end
	end
	table.sort(rows, function(a, b)
		if first then
			if (a.eventUnix == nil) ~= (b.eventUnix == nil) then
				return a.eventUnix ~= nil
			end
			if a.eventUnix ~= b.eventUnix then
				return a.eventUnix < b.eventUnix
			end
		elseif a.value ~= b.value then
			return a.value > b.value
		end
		return a.identity < b.identity
	end)
	for rank, row in ipairs(rows) do
		row.rank = rank
	end
	return rows
end

---@param rows table
---@return integer
local function OwnRowCount(rows)
	local total = 0
	for _, subjects in pairs(rows) do
		if type(subjects) == "table" then
			for _ in pairs(subjects) do
				total = total + 1
			end
		end
	end
	return total
end

-- The value the player's own current total is measured from this week. Saved under WEEKLY_KEY beside the peers, or
-- in memory while the caller has no peer table yet.
---@param self ForeverPeerStatsInstance
---@param metric string
---@param subject string
---@param value number
---@return number baseline
local function LocalBaseline(self, metric, subject, value)
	local now = Now()
	local weekStart = WeekStart(now)
	local store = EnsureStore(self)
	if not store then
		local key = metric .. "|" .. subject
		local cached = self.weekLocal[key]
		if type(cached) ~= "table" or type(cached.eventUnix) ~= "number" or cached.eventUnix < weekStart then
			cached = { value = value, eventUnix = now }
			self.weekLocal[key] = cached
		end
		return cached.value
	end
	local rows = store[WEEKLY_KEY]
	if type(rows) ~= "table" then
		rows = {}
		store[WEEKLY_KEY] = rows
	end
	local subjects = rows[metric]
	if type(subjects) ~= "table" then
		if OwnRowCount(rows) >= MAX_ROWS then
			return value
		end
		subjects = {}
		rows[metric] = subjects
	end
	local record = subjects[subject]
	if not record and OwnRowCount(rows) >= MAX_ROWS then
		return value
	end
	local savedValue = type(record) == "table" and IntIn(record.value, 0, MAX_VALUE) or nil
	local savedUnix = type(record) == "table" and IntIn(record.eventUnix, 1, now + FUTURE_SECONDS) or nil
	if not savedValue or not savedUnix or savedUnix < weekStart then
		record = { value = value, eventUnix = now }
		subjects[subject] = record
		return value
	end
	return savedValue
end

-- The weekly board, mirroring Board: the personal row always, peers only while enabled. A cumulative metric ranks by
-- the current value minus the first value heard this week; a first metric counts a record inside this week. Rows:
-- { rank, name, identity, value, eventUnix, self }.
---@param metric string
---@param subject? string defaults to "all"
---@param localValue? number
---@param localEventUnix? number
function Instance:WeekBoard(metric, subject, localValue, localEventUnix)
	subject = subject or "all"
	local config = self.metrics[metric]
	local first = config and config.first
	local now = Now()
	local weekStart = WeekStart(now)
	local name = OwnName() or "player"
	local value = IntIn(type(localValue) == "number" and math.floor(localValue) or nil, 0, MAX_VALUE) or 0
	local localUnix = IntIn(localEventUnix, 1, now + FUTURE_SECONDS)
	local ownValue
	if first then
		ownValue = localUnix and localUnix >= weekStart and 1 or 0
	elseif config and ValidSubject(config.subject, subject) then
		ownValue = math.max(0, value - LocalBaseline(self, metric, subject, value))
	else
		ownValue = 0
	end
	local rows = {
		{
			name = name,
			identity = SelfIdentity(self) or name:lower(),
			value = ownValue,
			eventUnix = localUnix,
			self = true,
		},
	}
	if config and ValidSubject(config.subject, subject) and self:IsEnabled() then
		local relayed = IncludeRelayed()
		for identity, key in pairs(self.index) do
			local subjects = self.store[key] and self.store[key][metric]
			local record = subjects and subjects[subject]
			if record and identity ~= rows[1].identity and (relayed or record.relayed ~= true) then
				local weekly
				if first then
					weekly = record.eventUnix and record.eventUnix >= weekStart and 1 or 0
				else
					local baseline = SavedBaseline(record, weekStart, now) or record.value
					weekly = math.max(0, record.value - baseline)
				end
				rows[#rows + 1] = {
					name = PeerDisplay(self, key),
					identity = identity,
					value = weekly,
					eventUnix = record.eventUnix,
					relayed = record.relayed == true or nil,
				}
			end
		end
	end
	table.sort(rows, function(a, b)
		if first then
			if (a.eventUnix == nil) ~= (b.eventUnix == nil) then
				return a.eventUnix ~= nil
			end
			if a.eventUnix ~= b.eventUnix then
				return a.eventUnix < b.eventUnix
			end
		elseif a.value ~= b.value then
			return a.value > b.value
		end
		return a.identity < b.identity
	end)
	for rank, row in ipairs(rows) do
		row.rank = rank
	end
	return rows
end

--------------------------------------------------------------------------------------------------------------------

---@class ForeverPeerStatsNamespace
local PeerStats = { PREFIX = PREFIX, Identity = Identity }

-- A new instance for `config`, registered with the shared manager. A second instance for the same addon replaces the
-- first, so two loaded copies never send twice. A config without a valid addon id returns an inert instance.
---@param config table
---@return ForeverPeerStatsInstance
local function New(config, owner)
	config = type(config) == "table" and config or {}
	local addon = type(config.addon) == "string" and #config.addon <= MAX_ADDON and config.addon:find("^[%w_%-]+$")
	local readOnly = owner ~= false
	local validOwner = type(owner) == "string" and #owner <= MAX_ADDON and owner:find("^[%w_%-]+$")
	local dead = not addon or (readOnly and not validOwner)
	---@type ForeverPeerStatsInstance
	local self = setmetatable({
		config = config,
		addon = addon and config.addon or "",
		key = not dead and (type(owner) == "string" and (owner .. "@" .. config.addon) or config.addon) or "",
		readOnly = readOnly,
		dead = dead,
		active = false,
		gen = 0,
		sent = {},
		observed = {},
		weekLocal = {},
		deferred = {},
		rate = {},
		rateCount = 0,
		index = {},
		latest = {},
		peerCount = 0,
		relayedCount = 0,
		relayOnly = {},
		heardOn = {},
		relayHeard = {},
		relayOrder = {},
		relayPending = {},
		relayItems = {},
		relayCount = 0,
		relayEpoch = {},
		names = {},
		observedCount = 0,
		metrics = {},
		metricList = {},
		revision = 0,
	}, Instance)
	if type(config.metrics) == "table" then
		for _, metric in ipairs(SortedStringKeys(config.metrics, MAX_METRICS)) do
			local entry = config.metrics[metric]
			local mode = type(entry) == "table" and entry.subject or ""
			if #metric <= MAX_METRIC and metric:find("^[%w_%.%-]+$") and SUBJECT_MODES[mode] then
				self.metrics[metric] = { subject = mode, first = entry.first == true }
				self.metricList[#self.metricList + 1] = metric
			end
		end
	end
	if not dead then
		local current = Manager()
		if current then
			current.Register(self)
		end
	end
	return self
end

function PeerStats.New(config)
	return New(config, false)
end

---@param owner string owner addon id, independent of the observed config.addon
---@param config table
---@return ForeverPeerStatsInstance
function PeerStats.Listen(owner, config)
	return New(config, owner or "")
end

-- The one manager this file made, for Core/LeaderboardsData.lua's reach switch and for a spec.
---@return table
function PeerStats.Manager()
	return manager
end

-- Rebuild the relay set from a sanitized store, for the spec that measures one build without the sanitize around it.
---@param instance ForeverPeerStatsInstance
---@param store table
---@param now number
function PeerStats.Rebuild(instance, store, now)
	RelayBuild(instance, store, now)
end

ns.PeerStats = PeerStats
