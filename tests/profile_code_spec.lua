-- The shareable profile code (docs/profile-code.md): version, base64url and compact JSON of this character's reads
-- plus each installed Forever addon's own API.Stats rows. This spec loads core's TOC the way the client does,
-- publishes one fake API per addon, and decodes every code back with the small base64url decoder below, so the
-- format the page reads is checked from the outside rather than by the writer's own functions.
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

-- Base64url (RFC 4648 section 5) with no padding, the other way round from Core/ProfileCode.lua's writer.
local function DecodeBase64Url(text)
	local alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
	local values = {}
	for index = 1, #alphabet do
		values[alphabet:sub(index, index)] = index - 1
	end
	local bytes, bits, count = {}, 0, 0
	for index = 1, #text do
		local symbol = text:sub(index, index)
		local value = values[symbol]
		assert(value ~= nil, "the code holds only base64url symbols, found " .. symbol)
		bits = bits * 64 + value
		count = count + 6
		while count >= 8 do
			count = count - 8
			bytes[#bytes + 1] = string.char(math.floor(bits / 2 ^ count) % 256)
			bits = bits % 2 ^ count
		end
	end
	assert(bits == 0, "an unpadded base64url tail carries no leftover bits")
	return table.concat(bytes)
end

-- The record a code carries, decoded from its version and dot.
local function Decode(code)
	local version, body = code:match("^(%d+)%.(.+)$")
	assert(version, "a code opens with its version and a dot: " .. code)
	equal(version, "1", "the code's version")
	return DecodeBase64Url(body)
end

-- The fake client, shared with the other TOC specs, and the TOC's files in order, as the client loads them.
local FakeClient = dofile("tests/fake_client.lua")
local Toc = dofile(".agents/skills/wow-forever-addon/tooling/forever_sim/toc.lua")
local env = FakeClient.new()
local ns = {}
for _, entry in ipairs(Toc.files(".", "ForeverCore.toc")) do
	if entry.kind == "lua" then
		-- Core's own quest list needs the full native tracker template, which this fake client does not build. The
		-- tracker host has already captured its native frame, so hiding it here only skips that optional section.
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

local ForeverCore = env.ForeverCore
local ProfileCode = ns.ProfileCode
check(type(ProfileCode) == "table", "Core/ProfileCode.lua publishes the module")
equal(ProfileCode.Version, 1, "the code's version is 1")
equal(ProfileCode.Url, "https://wow.cjber.dev/p/#", "the profile page and the fragment its code rides in")

-- One API per addon, published the way an addon publishes its own table at load.
local function Publish(name, stats)
	ForeverCore.APIKit.Publish(name, {
		version = 1,
		Stats = function()
			return stats()
		end,
	})
end

-- No addon published at all: the record is the character alone, and a code still decodes as one.
local empty = ProfileCode.Read()
equal(empty.name, "Tester", "the record carries the character's name")
equal(empty.class, "MAGE", "and the class file token")
equal(empty.level, 60, "and the level")
equal(empty.faction, "Alliance", "and the faction")
equal(empty.time, 1700000000, "and the time the code was made")
equal(next(empty.stats), nil, "an addon-less character has no stats at all")
equal(
	Decode(ProfileCode.Build(empty)),
	'{"n":"Tester","c":"MAGE","l":60,"f":"Alliance","t":1700000000,"s":{}}',
	"the empty record is the character's own fields and an empty stats object"
)

-- One addon present: only its section is in the code, under its short key, and every other addon is absent.
Publish("AdventureGuideForever", function()
	return {
		{ addon = "AdventureGuideForever", metric = "quest_turn_ins", subject = "all", value = 2 },
		{ addon = "AdventureGuideForever", metric = "quest_turn_in", subject = "101", value = 1 },
		{ addon = "AdventureGuideForever", metric = "quest_turn_in", subject = "102", value = 2 },
	}
end)
local only = ProfileCode.Build(ProfileCode.Read())
local onlyJson = Decode(only)
check(onlyJson:find('"s":{"adv":', 1, true) ~= nil, "Adventure Guide's rows are under the adv key")
equal(onlyJson:find('"spf"', 1, true), nil, "an addon that is not installed is absent")
equal(onlyJson:find('"leg"', 1, true), nil, "and so is every other one")
check(
	onlyJson:find('"quest_turn_in":3', 1, true) ~= nil,
	"a metric reported per subject (one row per quest) is summed across them"
)

-- Every addon present: one section each, keyed by the short key, metrics from each Stat row's own name.
Publish("ShortestPathForever", function()
	return {
		{ metric = "distance_yards", subject = "all", value = 120 },
		{ metric = "routes_completed", subject = "all", value = 3 },
		{ metric = "transports_used", subject = "all", value = 2 },
		{ metric = "flights_taken", subject = "all", value = 1 },
		{ metric = "portals_used", subject = "all", value = 1 },
	}
end)
Publish("SkillUpForever", function()
	return { { metric = "recipes_observed_learned", subject = "all", value = 5 } }
end)
Publish("LegacyForever", function()
	return {
		{ metric = "flight_path_known", subject = "1", value = 1 },
		{ metric = "flight_path_known", subject = "2", value = 1 },
		{ metric = "flight_path_known", subject = "3", value = 1 },
	}
end)
Publish("CommissionsForever", function()
	return { { metric = "commission_turnin", subject = "all", value = 4 } }
end)
Publish("FieldGuideForever", function()
	return {
		{ metric = "boss_kills", subject = "all", value = 0 },
		{ metric = "creature_kills", subject = "1", value = 5 },
		{ metric = "creature_kills", subject = "2", value = 7 },
	}
end)

local full = ProfileCode.Read()
equal(full.name, "Tester", "the full record still carries the character's name")
equal(full.class, "MAGE", "the class token")
equal(full.level, 60, "the level")
equal(full.faction, "Alliance", "the faction")
equal(full.time, 1700000000, "the time")
equal(full.stats.adv.quest_turn_in, 3, "the per-quest counts reach the record as one number")
equal(full.stats.adv.quest_turn_ins, 2, "the aggregate row keeps its own metric")
equal(full.stats.spf.distance_yards, 120, "Shortest Path's distance")
equal(full.stats.spf.routes_completed, 3, "and its journeys")
equal(full.stats.skl.recipes_observed_learned, 5, "SkillUp's recipes")
equal(full.stats.leg.flight_path_known, 3, "Legacy's known flight paths, summed over nodes")
equal(full.stats.com.commission_turnin, 4, "Commissions' turn-ins")
equal(full.stats.fgd.creature_kills, 12, "Field Guide's kills, summed over species")
equal(full.stats.fgd.boss_kills, 0, "a metric the addon reports at zero is kept rather than dropped")

local code = ProfileCode.Build(full)
equal(
	Decode(code),
	'{"n":"Tester","c":"MAGE","l":60,"f":"Alliance","t":1700000000,"s":{'
		.. '"adv":{"quest_turn_in":3,"quest_turn_ins":2},'
		.. '"com":{"commission_turnin":4},'
		.. '"fgd":{"boss_kills":0,"creature_kills":12},'
		.. '"leg":{"flight_path_known":3},'
		.. '"skl":{"recipes_observed_learned":5},'
		.. '"spf":{"distance_yards":120,"flights_taken":1,"portals_used":1,"routes_completed":3,"transports_used":2}'
		.. "}}",
	"every field of the full code decodes back to what the record holds, keys sorted"
)
equal(ProfileCode.Build(full), code, "the same record always makes the same code")
equal(ProfileCode.Link(full), ProfileCode.Url .. code, "the link is the page and the code after its fragment")

-- An addon whose read is not ready, and one whose read raises, are absent rather than breaking the code.
Publish("SkillUpForever", function()
	return nil, "loading"
end)
equal(ProfileCode.Read().stats.skl, nil, "a read with nothing to answer leaves its addon out")

Publish("FieldGuideForever", function()
	error("stats failed")
end)
local survived = ProfileCode.Build(ProfileCode.Read())
equal(Decode(survived):find('"fgd"', 1, true), nil, "a read that raises leaves its addon out too")

-- The size bound: every addon, every documented metric, and a nine-digit value in each. A browser URL handles
-- several kilobytes, and this stays well under two.
local everyMetric = {
	adv = { "quest_turn_in", "quest_turn_ins" },
	spf = { "distance_yards", "routes_completed", "transports_used", "flights_taken", "portals_used" },
	skl = { "recipes_observed_learned" },
	leg = { "flight_path_known" },
	com = { "commission_turnin" },
	fgd = {
		"boss_first_kill",
		"boss_first_sighting",
		"boss_kills",
		"boss_sightings",
		"bronze_finds",
		"creature_kills",
		"first_bronze",
		"first_gold",
		"first_kill",
		"first_shiny",
		"first_sighting",
		"first_silver",
		"gold_finds",
		"shiny_finds",
		"silver_finds",
	},
}
local largest = {
	name = "Barry Buckfast",
	class = "HUNTER",
	level = 80,
	faction = "Alliance",
	time = 1794516060,
	stats = {},
}
for key, metrics in pairs(everyMetric) do
	largest.stats[key] = {}
	for _, metric in ipairs(metrics) do
		largest.stats[key][metric] = 999999999
	end
end
local largestCode = ProfileCode.Build(largest)
check(#largestCode < 2048, ("a fully populated code stays under 2 KB, and is %d bytes"):format(#largestCode))
check(#largestCode > 0, "and it is a code")

-- The example fixture the site's empty state links to: the addon's own encoder wrote it, and it carries every addon.
local fixture = assert(io.open("docs/profile-code-example.txt", "r"), "docs/profile-code-example.txt")
local example = fixture:read("*a")
fixture:close()
example = example:match("^%s*(.-)%s*$")
local exampleJson = Decode(example)
check(exampleJson:find('"n":"Barry Buckfast"', 1, true) ~= nil, "the example is Barry Buckfast")
check(exampleJson:find('"c":"HUNTER"', 1, true) ~= nil, "a Hunter")
check(exampleJson:find('"l":21,', 1, true) ~= nil, "at level 21")
check(exampleJson:find('"f":"Alliance"', 1, true) ~= nil, "for the Alliance")
for _, key in ipairs({ '"adv"', '"spf"', '"skl"', '"leg"', '"com"', '"fgd"' }) do
	check(exampleJson:find(key, 1, true) ~= nil, "the example carries " .. key)
end

print(("profile_code_spec: %d checks passed"):format(checks))
