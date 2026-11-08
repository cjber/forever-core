---@type string, ForeverLeaderboardsNamespace
local _, ns = ...

-- The data half of Forever Leaderboards: overall points, one player's standing, the per-scope cache and the unit
-- tooltip. UI/Leaderboards.lua, loaded after this file, owns the window and the registrations; everything here works
-- from the registered specs through the `api` table it is handed, so it still knows no addon.
--
-- The cache makes a tooltip hover one lookup: Overall is built only when a board's revision, the scope, the
-- registration or the current week start changes, and Standing then reads the players-by-identity map built with it.
-- A board that cannot supply a revision is rebuilt when anything else invalidates the cache.

---@class ForeverLeaderboardsData
---@field VERSION integer
---@field MEDALS string[]
---@field Strings fun(): table<string, string>
---@field Identity fun(name: any, realm?: any): string?
---@field OwnName fun(): string?
---@field ClassOf fun(name: any): string?
---@field RefreshClasses fun(part?: "guild"|"group")
---@field InvalidateClasses fun(part?: "guild"|"group")
---@field WeekStart fun(now: number): number
---@field BoardRows fun(...: any): ForeverLeaderboardsRow[]
---@field Overall fun(api: ForeverLeaderboardsAPI, scope: ForeverLeaderboardsScope): ForeverLeaderboardsRow[]
---@field Standing fun(api: ForeverLeaderboardsAPI, name: string, scope: any): ForeverLeaderboardsStanding
---@field AddTooltip fun(api: ForeverLeaderboardsAPI, tooltip: GameTooltip)
local Data = { VERSION = 1 }
ns.LeaderboardsData = Data

local WEEK_SECONDS = 7 * 86400
local POINTS = { 10, 8, 6, 5, 4, 3, 2, 1 }
local ORDINALS = { "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th" }
Data.MEDALS = { "challenges-medal-gold", "challenges-medal-silver", "challenges-medal-bronze" }
local NO_STRINGS = {}

-- Every addon's L takes English phrases as keys. A phrase reads from this copy's L only, and as itself where that L
-- has no entry, so a line is never half translated. A phrase counts only as the L's own entry (rawget).
local strings = setmetatable({}, { __mode = "kv" })
---@return table<string, string>
function Data.Strings()
	local source = type(ns.L) == "table" and ns.L or NO_STRINGS
	local found = strings[source]
	if not found then
		found = setmetatable({}, {
			__index = function(_, phrase)
				local text = rawget(source, phrase)
				return type(text) == "string" and text or phrase
			end,
		})
		strings[source] = found
	end
	return found
end

local function Compact(text)
	return (text:gsub("[%s%-]", ""))
end

---@return string?
local function LocalRealm()
	local realm = (GetNormalizedRealmName and GetNormalizedRealmName()) or (GetRealmName and GetRealmName())
	if type(realm) == "string" and realm ~= "" then
		return Compact(realm):lower()
	end
end

-- The same identity Core/PeerStats.lua saves: a name, its realm when it is not this one, and neither spaces nor
-- punctuation, all lowercase. "Name", "Name-MyRealm" and "name-My Realm" are one player.
---@param name any
---@param realm? any
---@return string?
function Data.Identity(name, realm)
	if type(name) ~= "string" or name == "" then
		return nil
	end
	local plainName, plainRealm = name:match("^([^%-]+)%-(.+)$")
	plainName = Compact(plainName or name)
	if plainName == "" then
		return nil
	end
	plainRealm = plainRealm or (type(realm) == "string" and realm ~= "" and realm) or nil
	if plainRealm then
		plainRealm = Compact(plainRealm)
		if plainRealm == "" or plainRealm:lower() == LocalRealm() then
			plainRealm = nil
		end
	end
	return (plainRealm and (plainName .. "-" .. plainRealm) or plainName):lower()
end

-- Forever's client returns the surname as UnitName's second return. Blizzard's NameUtil joins the two with
-- Constants.CharacterNameSeparatorConsts.CHARACTERNAME_SURNAME_SEPARATOR; without that constant the second return is
-- the realm, as on a client with no surname, so only the first return is the player's name.
---@return string?
local function NameSeparator()
	local constants = rawget(_G, "Constants")
	local separators = type(constants) == "table" and constants.CharacterNameSeparatorConsts
	local separator = type(separators) == "table" and separators.CHARACTERNAME_SURNAME_SEPARATOR
	if type(separator) == "string" and separator ~= "" then
		return separator
	end
end

---@param unit string
---@return string?
local function UnitDisplayName(unit)
	local name, surname = UnitName(unit)
	if type(name) ~= "string" or name == "" then
		return nil
	end
	local separator = NameSeparator()
	if separator and type(surname) == "string" and surname ~= "" then
		return name .. separator .. surname
	end
	return name
end

---@return string?
function Data.OwnName()
	return UnitDisplayName("player")
end

-- Other players' rows carry only a name, and the wire format has no class to add. The client already knows who is what
-- class from the units beside the player and the guild roster, so a missing row class is answered from there: the
-- player's own from UnitClass("player"), a group member by short name, then a guild member from GetGuildRosterInfo's
-- classFileName. The answers are cached by short name ("Abe-OtherRealm" and "Abe" are one player), the group and guild
-- parts are built on first need, and a roster event rebuilds its part only while the window is shown.
local MAX_GUILD_MEMBERS = 2000
local MAX_CACHED_CLASSES = 512
local classCache = {}
local cachedClasses = 0
local groupClasses = {}
local guildClasses = {}
local groupStale, guildStale = true, true

-- A class token is a RAID_CLASS_COLORS key. The client returns the token beside the localized name, and a roster entry
-- returns it as classFileName; anything else is left to the neutral colour rather than drawn as a broken icon.
---@param value any
---@return string?
local function ClassToken(value)
	if type(value) ~= "string" or value == "" then
		return nil
	end
	local token = value:upper()
	local colors = rawget(_G, "RAID_CLASS_COLORS")
	if type(colors) == "table" and not colors[token] then
		return nil
	end
	return token
end

-- The name key every source is matched on: the client's short spelling when it can give one, else the part before the
-- realm, compacted and lowercased like Core/PeerStats.lua's identities.
---@param name any
---@return string?
local function ShortName(name)
	if type(name) ~= "string" or name == "" then
		return nil
	end
	local short
	local ambiguate = rawget(_G, "Ambiguate")
	if type(ambiguate) == "function" then
		local ok, value = pcall(ambiguate, name, "short")
		if ok and type(value) == "string" and value ~= "" then
			short = value
		end
	end
	short = short or name:match("^([^%-]+)%-") or name
	local key = Compact(short):lower()
	if key ~= "" then
		return key
	end
end

---@param unit string
---@return string?
local function UnitClassToken(unit)
	local _, class = UnitClass(unit)
	return ClassToken(class)
end

local function BuildGroup()
	local map = {}
	local function Remember(unit)
		local key = ShortName(UnitDisplayName(unit))
		if key then
			local class = UnitClassToken(unit)
			if class then
				map[key] = class
			end
		end
	end
	Remember("player")
	if IsInRaid and IsInRaid() then
		for index = 1, 40 do
			Remember("raid" .. index)
		end
	else
		for index = 1, 4 do
			Remember("party" .. index)
		end
	end
	groupClasses, groupStale = map, false
end

local function BuildGuild()
	local map = {}
	local total = GetNumGuildMembers and tonumber(GetNumGuildMembers()) or 0
	local get = GetGuildRosterInfo
	if type(get) == "function" and total and total > 0 then
		for index = 1, math.min(total, MAX_GUILD_MEMBERS) do
			local name, _, _, _, _, _, _, _, _, _, classFileName = get(index)
			local key = ShortName(name)
			local class = ClassToken(classFileName)
			if key and class then
				map[key] = class
			end
		end
	end
	guildClasses, guildStale = map, false
end

-- The player's class when the client can say it, else what a group member's unit or the guild roster says. The cache
-- keeps only answers it has, so a guild roster that arrives after the first row still fills later ones.
---@param name any
---@return string?
function Data.ClassOf(name)
	local key = ShortName(name)
	if not key then
		return nil
	end
	local class = classCache[key]
	if class then
		return class
	end
	if groupStale then
		BuildGroup()
	end
	class = groupClasses[key]
	if not class then
		if guildStale then
			BuildGuild()
		end
		class = guildClasses[key]
	end
	if class then
		if cachedClasses >= MAX_CACHED_CLASSES then
			classCache, cachedClasses = {}, 0
		end
		classCache[key], cachedClasses = class, cachedClasses + 1
	end
	return class
end

-- UI/Leaderboards.lua calls these on the roster events: while the window is shown its part is rebuilt at once, while
-- it is closed only marked stale so the next row lookup does the work.
---@param part? "guild"|"group" nil rebuilds both
function Data.RefreshClasses(part)
	if part ~= "group" then
		BuildGuild()
	end
	if part ~= "guild" then
		BuildGroup()
	end
end

---@param part? "guild"|"group" nil invalidates both
function Data.InvalidateClasses(part)
	if part ~= "group" then
		guildStale = true
	end
	if part ~= "guild" then
		groupStale = true
	end
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

-- The instant the current week began, matching Core/PeerStats.lua's WeekStart: the client's reset countdown when it
-- has one, else the last Tuesday 15:00 UTC. The cache rebuilds when this differs.
---@param now number
---@return number
function Data.WeekStart(now)
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

-- One board's rows, with relayed rows included only while the window's reach is "met". The flag lives on the shared
-- peer manager, so it is set only when that manager exists and is always restored, even when the board raises.
---@param api ForeverLeaderboardsAPI
---@param spec ForeverLeaderboardsSpec
---@param scope ForeverLeaderboardsScope
---@return ForeverLeaderboardsRow[]
function Data.BoardRows(api, spec, scope)
	local manager = rawget(_G, "ForeverPeerStats")
	local managed = type(manager) == "table"
	local previous
	if managed then
		previous = manager.includeRelayed
		manager.includeRelayed = api.reach == "met"
	end
	local ok, rows = pcall(spec.board, scope)
	if managed then
		manager.includeRelayed = previous
	end
	if ok and type(rows) == "table" then
		return rows
	end
	return {}
end

-- One board's contribution to the cache key. Revising a counter is the consumer's way of saying a stored row or its
-- own snapshot changed; a board without one contributes nothing and waits for another board to invalidate the cache.
---@param api ForeverLeaderboardsAPI
---@return number
local function Revisions(api)
	local sum = 0
	for _, key in ipairs(api.order or {}) do
		local spec = api.boards and api.boards[key]
		local revision = spec and spec.revision
		if type(revision) == "function" then
			local ok, value = pcall(revision)
			if ok and type(value) == "number" and value == value then
				sum = sum + value
			end
		end
	end
	return sum
end

-- A player heard on several boards may arrive as a full display name on one and a compacted key on another. Keep the
-- full name when either board supplies one, so a consumer's older row never shortens a peer's name.
---@param current string?
---@param candidate any
---@return string?
local function BetterName(current, candidate)
	if type(candidate) ~= "string" or candidate == "" then
		return current
	end
	if type(current) ~= "string" or current == "" then
		return candidate
	end
	if candidate:find("%s") and not current:find("%s") then
		return candidate
	end
	return current
end

-- Ranked overall rows, summed from each board's own rank order: 10, 8, 6, 5, 4, 3, 2, 1 points per place. Only
-- players who placed appear; a player on a board but outside the points is found by Standing and gets no row.
---@param api ForeverLeaderboardsAPI
---@param scope ForeverLeaderboardsScope
---@return ForeverLeaderboardsRow[] rows
---@return table<string, ForeverLeaderboardsPlayer> players
local function Build(api, scope)
	local L = Data.Strings()
	local players, order = {}, {}
	for _, spec in ipairs(api:Boards()) do
		local rows = Data.BoardRows(api, spec, scope)
		local seen = {}
		for index, row in ipairs(rows) do
			local name = type(row) == "table" and row.name or nil
			local identity = type(row) == "table"
					and type(row.identity) == "string"
					and row.identity ~= ""
					and row.identity
				or nil
			identity = identity or Data.Identity(name)
			if identity and not seen[identity] then
				seen[identity] = true
				local player = players[identity]
				if not player then
					player = {
						identity = identity,
						found = true,
						points = 0,
						rank = 0,
						boards = 0,
						places = {},
						name = name,
					}
					players[identity], order[#order + 1] = player, identity
				end
				player.name = BetterName(player.name, name)
				if type(row.class) == "string" and row.class ~= "" then
					player.class = row.class
				end
				player.you = player.you or row.you == true
				local points = POINTS[index]
				if points then
					player.points = player.points + points
					player.boards = player.boards + 1
					player.places[#player.places + 1] =
						{ key = spec.key or "", title = spec.title, rank = index, points = points }
				end
			end
		end
	end
	local placed = {}
	for _, identity in ipairs(order) do
		local player = players[identity]
		if player.points > 0 then
			player.identity = identity
			placed[#placed + 1] = player
		end
	end
	table.sort(placed, function(a, b)
		if a.points ~= b.points then
			return a.points > b.points
		end
		return a.identity < b.identity
	end)
	local rows = {}
	for index, player in ipairs(placed) do
		player.rank = index
		rows[index] = {
			name = player.name,
			identity = player.identity,
			class = player.class or Data.ClassOf(player.name),
			value = player.points,
			extra = player.boards .. " " .. L[player.boards == 1 and "board" or "boards"],
			you = player.you == true,
		}
	end
	return rows, players
end

-- One cache slot per scope and reach. The window and the tooltip both read the slot, so a hover never sorts or
-- rebuilds a board while nothing changed.
local cache = {
	week = { group = {}, met = {} },
	all = { group = {}, met = {} },
}

---@param api ForeverLeaderboardsAPI
---@param scope ForeverLeaderboardsScope
---@return ForeverLeaderboardsRow[] rows
---@return table<string, ForeverLeaderboardsPlayer> players
local function Snapshot(api, scope)
	scope = scope == "all" and "all" or "week"
	local reach = api.reach == "met" and "met" or "group"
	local weekStart = Data.WeekStart(Now())
	local revisions = Revisions(api)
	local registration = tonumber(api.registration) or 0
	local slot = cache[scope][reach]
	if
		slot.rows
		and slot.revisions == revisions
		and slot.registration == registration
		and slot.weekStart == weekStart
	then
		return slot.rows, slot.players
	end
	local rows, players = Build(api, scope)
	slot.rows, slot.players = rows, players
	slot.revisions, slot.registration, slot.weekStart = revisions, registration, weekStart
	return rows, players
end

-- The overall board for the window and any caller that wants it.
---@param api ForeverLeaderboardsAPI
---@param scope ForeverLeaderboardsScope
---@return ForeverLeaderboardsRow[]
function Data.Overall(api, scope)
	return (Snapshot(api, scope))
end

-- The overall place of one player, from the same cache the window reads.
---@param api ForeverLeaderboardsAPI
---@param name string
---@param scope ForeverLeaderboardsScope
---@return ForeverLeaderboardsStanding
function Data.Standing(api, name, scope)
	local identity = Data.Identity(name)
	local _, players = Snapshot(api, scope or api.scope)
	local player = identity and players[identity]
	if not player then
		return { found = false, points = 0, rank = 0, boards = 0, places = {} }
	end
	return {
		found = true,
		points = player.points,
		rank = player.rank or 0,
		boards = player.boards,
		places = player.places,
	}
end

---@param rank integer
---@param L table<string, string>
---@return string
local function Ordinal(rank, L)
	local phrase = ORDINALS[rank]
	return phrase and L[phrase] or (rank .. ".")
end

-- The unit tooltip's two lines: the medal and the overall place, then the per-addon places in grey. A player heard
-- over PeerStats but placing nowhere gets one grey line. Nothing at all for a player no board has heard.
---@param api ForeverLeaderboardsAPI
---@param tooltip GameTooltip
function Data.AddTooltip(api, tooltip)
	if not tooltip or type(tooltip.GetUnit) ~= "function" then
		return
	end
	-- GameTooltip:GetUnit returns the displayed name first, then the unit token (Blizzard_SharedXMLGame/Tooltip/
	-- TooltipUtil.lua, TooltipUtil.GetDisplayedUnit).
	local ok, _, unit = pcall(tooltip.GetUnit, tooltip)
	if not ok or type(unit) ~= "string" then
		return
	end
	local name, surname = UnitName(unit)
	local canAccess = rawget(_G, "canaccessvalue")
	if
		type(name) ~= "string"
		or name == ""
		or (canAccess and (not canAccess(name) or (surname ~= nil and not canAccess(surname))))
	then
		return
	end
	local separator = NameSeparator()
	local lookup = name
	if type(surname) == "string" and surname ~= "" then
		lookup = name .. (separator or "-") .. surname
	end
	local identity = Data.Identity(lookup)
	local standing = identity and Data.Standing(api, identity, api.scope)
	if not standing or not standing.found then
		return
	end
	local L = Data.Strings()
	if standing.points <= 0 then
		tooltip:AddLine(L["Uses Forever addons"], GRAY_FONT_COLOR:GetRGB())
		return
	end
	local medal = Data.MEDALS[standing.rank]
	local phrase = api.scope == "week" and L["Forever: %s overall this week"] or L["Forever: %s overall"]
	local line = (medal and ("|A:" .. medal .. ":14:14|a ") or "") .. phrase:format(Ordinal(standing.rank, L))
	tooltip:AddLine(line, NORMAL_FONT_COLOR:GetRGB())
	local places = {}
	for _, place in ipairs(standing.places) do
		places[#places + 1] = place.title .. " " .. Ordinal(place.rank, L)
	end
	if #places > 0 then
		tooltip:AddLine(table.concat(places, L[", "]), GRAY_FONT_COLOR:GetRGB())
	end
end
