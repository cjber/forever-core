-- This character's shareable profile code: version 1, base64url of compact JSON, written up in docs/profile-code.md.
-- The record is the client's own character reads plus each installed Forever addon's public API.Stats, so no addon
-- needs an export of its own. Nothing is sent anywhere and nothing new is saved: the player copies the link out of
-- the game, and the profile page reads it from the URL fragment in their own browser.

local _, ns = ...

local ProfileCode = {}
-- The version the code opens with, before its dot. A reader refuses a version it does not know.
ProfileCode.Version = 1
-- The profile page, with the code after the #. The fragment never reaches the server.
ProfileCode.Url = "https://wow.cjber.dev/p/#"

-- The addons a code carries: the name each publishes its API under, and the short key the code and the page use.
---@class ForeverProfileAddon
---@field name string the API name the addon publishes under
---@field key string the short key this code uses for it
---@type ForeverProfileAddon[]
ProfileCode.Addons = {
	{ name = "AdventureGuideForever", key = "adv" },
	{ name = "ShortestPathForever", key = "spf" },
	{ name = "SkillUpForever", key = "skl" },
	{ name = "LegacyForever", key = "leg" },
	{ name = "CommissionsForever", key = "com" },
	{ name = "FieldGuideForever", key = "fgd" },
}

-- base64url's alphabet: the 62 usual symbols with - and _ in place of + and /, so the code needs no escaping.
local ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

---@param value integer
---@return string
local function Symbol(value)
	return ALPHABET:sub(value + 1, value + 1)
end

-- base64url with no padding: the tail carries only the symbols its bytes fill.
---@param text string
---@return string
local function Base64(text)
	local out = {}
	for index = 1, #text, 3 do
		local first, second, third = text:byte(index, index + 2)
		local packed = first * 65536 + (second or 0) * 256 + (third or 0)
		out[#out + 1] = Symbol(math.floor(packed / 262144) % 64)
		out[#out + 1] = Symbol(math.floor(packed / 4096) % 64)
		if second then
			out[#out + 1] = Symbol(math.floor(packed / 64) % 64)
		end
		if third then
			out[#out + 1] = Symbol(packed % 64)
		end
	end
	return table.concat(out)
end

-- A JSON string, with the quotes, backslashes and control characters that would break the record escaped. Bytes
-- above 127 are the player's own name in UTF-8, which JSON carries as they are.
---@param text any
---@return string
local function Quote(text)
	local escaped = tostring(text or ""):gsub('[%c"\\]', function(character)
		if character == '"' then
			return '\\"'
		elseif character == "\\" then
			return "\\\\"
		elseif character == "\n" then
			return "\\n"
		elseif character == "\r" then
			return "\\r"
		elseif character == "\t" then
			return "\\t"
		end
		return ("\\u%04x"):format(character:byte())
	end)
	return '"' .. escaped .. '"'
end

-- A whole number for JSON. Every number a code carries is a count or a unix time, so a missing or broken value is 0
-- and a fraction is floored rather than written as an exponent no reader expects.
---@param value any
---@return number
local function Count(value)
	value = tonumber(value)
	if type(value) ~= "number" or value ~= value or value == math.huge or value == -math.huge then
		return 0
	end
	return math.floor(value)
end

-- One number per metric an addon reports: the sum of that metric's rows. A metric an addon reports per subject
-- (Legacy's known flight paths, Adventure Guide's per-quest record) therefore totals across the character's subjects.
---@param rows any
---@return table<string, number>
local function Metrics(rows)
	local metrics = {}
	if type(rows) ~= "table" then
		return metrics
	end
	for _, row in ipairs(rows) do
		if type(row) == "table" and type(row.metric) == "string" then
			local value = tonumber(row.value)
			if value ~= nil and value == value and value > -math.huge and value < math.huge then
				metrics[row.metric] = (metrics[row.metric] or 0) + value
			end
		end
	end
	return metrics
end

-- This character's record: name, class token, level, faction, the time the code was made, and one table of numbers
-- per installed addon that answered Stats. An addon that is not installed, or has not published its API, is absent.
---@class ForeverProfileRecord
---@field name string
---@field class string the class file token, such as HUNTER
---@field level integer
---@field faction string Alliance, Horde or Neutral
---@field time integer unix seconds
---@field stats table<string, table<string, number>>

---@return ForeverProfileRecord
function ProfileCode.Read()
	local _, class = UnitClass("player")
	---@type ForeverProfileRecord
	local record = {
		name = tostring(UnitName("player") or ""),
		class = tostring(class or ""),
		level = Count(UnitLevel("player")),
		faction = tostring(UnitFactionGroup("player") or ""),
		time = Count(GetServerTime()),
		stats = {},
	}
	local published = {}
	for _, entry in ipairs(ns.APIKit.Addons()) do
		published[entry.name] = entry
	end
	for _, addon in ipairs(ProfileCode.Addons) do
		local entry = published[addon.name]
		local api = entry and entry.api
		if type(api) == "table" and type(api.Stats) == "function" then
			local ok, rows = ns.SafeCallFor(addon.name):SafeCall("profile stats", api.Stats)
			if ok then
				local metrics = Metrics(rows)
				if next(metrics) ~= nil then
					record.stats[addon.key] = metrics
				end
			end
		end
	end
	return record
end

-- The code for `record`: the version, a dot, then the record as base64url JSON. Keys are written in sorted order, so
-- the same record always makes the same code.
---@param record ForeverProfileRecord
---@return string
function ProfileCode.Build(record)
	local stats = record.stats or {}
	local addonKeys = {}
	for key in pairs(stats) do
		addonKeys[#addonKeys + 1] = key
	end
	table.sort(addonKeys)
	local sections = {}
	for _, key in ipairs(addonKeys) do
		local metrics = {}
		for metric in pairs(stats[key]) do
			metrics[#metrics + 1] = metric
		end
		table.sort(metrics)
		local fields = {}
		for _, metric in ipairs(metrics) do
			fields[#fields + 1] = Quote(metric) .. ":" .. ("%d"):format(Count(stats[key][metric]))
		end
		sections[#sections + 1] = Quote(key) .. ":{" .. table.concat(fields, ",") .. "}"
	end
	local json = ('{"n":%s,"c":%s,"l":%d,"f":%s,"t":%d,"s":{%s}}'):format(
		Quote(record.name),
		Quote(record.class),
		Count(record.level),
		Quote(record.faction),
		Count(record.time),
		table.concat(sections, ",")
	)
	return ("%d.%s"):format(ProfileCode.Version, Base64(json))
end

-- The profile page's link for `record`, or for a fresh read when none is given.
---@param record? ForeverProfileRecord
---@return string
function ProfileCode.Link(record)
	return ProfileCode.Url .. ProfileCode.Build(record or ProfileCode.Read())
end

ns.ProfileCode = ProfileCode
