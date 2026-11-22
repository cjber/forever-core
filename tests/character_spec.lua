-- ForeverCore.CharacterKey (#999): "Name-NormalizedRealm" on a named realm, so existing saves still match, and on a
-- Forever realm, which has no name, the full name and the GUID's server segment. Nil until the client knows enough.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

-- A client answering name, surname-or-realm, normalized realm, plain realm and GUID.
local function Key(client)
	local env = {
		UnitName = function(unit)
			assert(unit == "player")
			return client.name, client.second
		end,
		UnitGUID = function(unit)
			assert(unit == "player")
			return client.guid
		end,
		GetNormalizedRealmName = function()
			return client.normalized
		end,
		GetRealmName = function()
			return client.realm
		end,
		GetRealmID = function()
			return client.realmID
		end,
		UNKNOWNOBJECT = "Unknown",
	}
	env._G = env
	setmetatable(env, { __index = _G })
	local ns = {}
	local chunk = assert(loadfile("Core/Character.lua"))
	setfenv(chunk, env)
	chunk("ForeverCore", ns)
	return ns.CharacterKey()
end

local GUID = "Player-6941-006325F9"

-- A named realm keeps today's key, whatever the GUID or second name says.
equal(Key({ name = "Aria", normalized = "Firemaw", realm = "Firemaw", guid = GUID }), "Aria-Firemaw", "a named realm")
equal(
	Key({ name = "Aria", second = "Stone", normalized = "Firemaw", realm = "Firemaw", guid = GUID }),
	"Aria-Firemaw",
	"a named realm ignores a surname, so existing keys still match"
)
equal(
	Key({ name = "Aria", normalized = "ArgentDawn", realm = "Argent Dawn", guid = GUID }),
	"Aria-ArgentDawn",
	"the normalized realm, without its space"
)
equal(
	Key({ name = "Aria", normalized = "", realm = "Argent Dawn", guid = GUID }),
	"Aria-ArgentDawn",
	"early in loading the plain realm name, stripped the way the client normalizes it"
)
equal(
	Key({ name = "Aria", normalized = nil, realm = "Azjol-Nerub", guid = GUID }),
	"Aria-AzjolNerub",
	"a hyphen is stripped too"
)

-- A Forever realm: no realm name, so the full name and the server segment of the GUID.
local forever = { name = "Hel", second = "Io", normalized = "", realm = "", guid = GUID, realmID = 0 }
equal(Key(forever), "Hel Io-6941", "the live Forever case from #999")
equal(
	Key({ name = "Aria", second = "Stone", normalized = "", realm = "", guid = "Player-6941-0000ABCD", realmID = 0 }),
	"Aria Stone-6941",
	"one first name on one server"
)
equal(
	Key({ name = "Aria", second = "Guns", normalized = "", realm = "", guid = "Player-6941-0000ABCE", realmID = 0 }),
	"Aria Guns-6941",
	"and a different surname is a different key"
)
equal(
	Key({ name = "Aria", normalized = "", realm = "", guid = GUID, realmID = 0 }),
	"Aria-6941",
	"a character with no surname keys on its first name"
)
equal(
	Key({ name = "Aria", second = "", normalized = "", realm = "", guid = GUID, realmID = 0 }),
	"Aria-6941",
	"an empty surname is no surname"
)

-- Nil until the client has the name, and on a Forever realm the GUID.
equal(Key({ name = nil, normalized = "Firemaw", guid = GUID }), nil, "no name yet")
equal(Key({ name = "", normalized = "Firemaw", guid = GUID }), nil, "an empty name")
equal(Key({ name = "Unknown", normalized = "Firemaw", guid = GUID }), nil, "the client's placeholder name")
equal(Key({ name = "Hel", second = "Io", normalized = "", realm = "", guid = nil, realmID = 0 }), nil, "no GUID yet")
equal(Key({ name = "Hel", second = "Io", normalized = "", realm = "", guid = "", realmID = 0 }), nil, "an empty GUID")
equal(
	Key({ name = "Hel", second = "Io", normalized = "", realm = "", guid = "Creature-0-1-2-3-4-5", realmID = 0 }),
	nil,
	"not a player GUID"
)

-- A named realm still loading answers no name with a real ID: no key yet, never a Forever key it would later drop.
equal(
	Key({ name = "Aria", second = "Stone", normalized = "", realm = "", realmID = 4440, guid = GUID }),
	nil,
	"a realm with an ID but no name yet"
)
equal(Key({ name = "Aria", normalized = "", realm = "", realmID = nil, guid = GUID }), nil, "no realm ID yet")
equal(
	Key({ name = "Aria", normalized = "Firemaw", realm = "Firemaw", guid = nil }),
	nil,
	"a named realm with no GUID yet"
)

-- Read fresh on every call: a nil answer is not remembered, so the next call after the client knows has the key.
do
	local client = { name = nil, second = "Io", normalized = "", realm = "", guid = nil, realmID = 0 }
	local env = {
		UnitName = function()
			return client.name, client.second
		end,
		UnitGUID = function()
			return client.guid
		end,
		GetNormalizedRealmName = function()
			return client.normalized
		end,
		GetRealmName = function()
			return client.realm
		end,
		GetRealmID = function()
			return client.realmID
		end,
	}
	env._G = env
	setmetatable(env, { __index = _G })
	local ns = {}
	local chunk = assert(loadfile("Core/Character.lua"))
	setfenv(chunk, env)
	chunk("ForeverCore", ns)
	equal(ns.CharacterKey(), nil, "before the client knows")
	client.name = "Hel"
	equal(ns.CharacterKey(), nil, "a name but no GUID yet")
	client.guid = GUID
	equal(ns.CharacterKey(), "Hel Io-6941", "and once it knows, the key")
end

print(("character_spec: %d checks"):format(checks))
