-- Contract for the vendored out-of-date warning every consumer's Core/Require.lua calls.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local own = { title = "My Addon", tag = "v1.5.0" }
local core = { name = "ForeverCore", title = "ForeverCore", project = "1796337" }
local FOREIGN_KEY = "%s: the installed ForeverCore is another addon (%s). "
	.. "Remove it and install ForeverCore from CurseForge."
local FOREIGN = "My Addon: the installed ForeverCore is another addon (Another Core UI). "
	.. "Remove it and install ForeverCore from CurseForge."
local addons = {}
local messages = {}

local function entry(overrides)
	local item = {
		name = "OtherForever",
		title = "Other Forever",
		loaded = true,
		enabled = 2,
		deps = { "ForeverCore" },
		tag = "v1.5.0",
	}
	for key, value in pairs(overrides or {}) do
		item[key] = value
	end
	return item
end

_G.UnitName = function()
	return "Player"
end
_G.GetAddOnMetadata = function(name, field)
	if name == "MyAddon" and field == "X-Forever-Core" then
		return own.tag
	end
end
_G.UIErrorsFrame = {
	AddMessage = function(_, text, red, green, blue)
		messages[#messages + 1] = { text = text, red = red, green = green, blue = blue }
	end,
}

_G.C_AddOns = {
	GetNumAddOns = function()
		return #addons
	end,
	GetAddOnInfo = function(index)
		return addons[index] and addons[index].name
	end,
	GetAddOnMetadata = function(target, field)
		local item = type(target) == "number" and addons[target] or (target == "MyAddon" and own)
		if not item then
			return nil
		end
		if field == "Title" then
			return item.title
		end
		if field == "X-Forever-Core" then
			return item.tag
		end
		if field == "X-Curse-Project-ID" then
			if item.project_error then
				error("metadata unavailable")
			end
			return item.project
		end
		if field == "X-Website" then
			return item.website
		end
	end,
	IsAddOnLoaded = function(index)
		return addons[index] and addons[index].loaded
	end,
	GetAddOnEnableState = function(index)
		return addons[index] and addons[index].enabled
	end,
	GetAddOnDependencies = function(index)
		return unpack(addons[index] and addons[index].deps or {})
	end,
}

local function run(entries, ready, L, installed)
	addons = {
		{ name = "MyAddon", title = own.title, loaded = true, enabled = 2, deps = { "ForeverCore" }, tag = own.tag },
		installed or core,
	}
	for _, item in ipairs(entries or {}) do
		addons[#addons + 1] = item
	end
	messages = {}
	local ns = { L = L }
	assert(loadfile("tools/consumer/ForeverRequire.lua"))("MyAddon", ns)
	local result = ns.ForeverRequire(ready)
	return ns, result, messages[1] and messages[1].text
end

-- Ready does nothing at all.
do
	local ns, result = run({}, true)
	equal(result, true, "ready returns true")
	equal(ns.broken, nil, "ready leaves the addon unbroken")
	equal(#messages, 0, "ready shows no message")
end

-- One older culprit is named.
do
	local ns, result, text = run({ entry({ name = "LegacyForever", title = "Legacy Forever", tag = "v1.4.1" }) }, false)
	equal(result, false, "an unready addon returns false")
	equal(ns.broken, true, "an unready addon is marked broken")
	equal(text, "My Addon: Legacy Forever is out of date. Update it to fix this.", "one old addon is named")
	equal(messages[1].red, 1, "the message uses the error red")
	equal(messages[1].green, 0.1, "the message uses the error green")
	equal(messages[1].blue, 0.1, "the message uses the error blue")
end

-- Two older culprits share one line, and the second dependency counts.
do
	local first = entry({ name = "AlphaForever", title = "Alpha", tag = "v1.4.0" })
	local second = entry({ name = "BetaForever", title = "Beta", tag = "v1.3.0", deps = { "SomeLib", "ForeverCore" } })
	local _, _, text = run({ first, second }, false)
	equal(text, "My Addon: Alpha and Beta are out of date. Update them to fix this.", "two old addons are named once")
end

-- A culprit with no X-Forever-Core field is out of date.
do
	local missing = entry({ name = "OldForever", title = "Old Forever" })
	missing.tag = nil
	local _, _, text = run({ missing }, false)
	equal(text, "My Addon: Old Forever is out of date. Update it to fix this.", "a missing core field counts")
end

-- An up-to-date addon is not named.
do
	local _, _, text = run({ entry({ name = "NewForever", title = "New Forever", tag = "v1.5.0" }) }, false)
	equal(text, "My Addon could not start. Reinstall My Addon to fix this.", "an up-to-date addon is not named")
end

-- A disabled dependent is ignored.
do
	local off = entry({ name = "OffForever", title = "Off Forever", tag = "v1.0.0", loaded = false, enabled = 0 })
	local _, _, text = run({ off }, false)
	equal(text, "My Addon could not start. Reinstall My Addon to fix this.", "a disabled addon is ignored")
end

-- An addon that does not depend on ForeverCore is ignored.
do
	local other = entry({ name = "QuestAddon", title = "Quest Addon", tag = "v1.0.0", deps = { "Questie" } })
	local _, _, text = run({ other }, false)
	equal(text, "My Addon could not start. Reinstall My Addon to fix this.", "a non-dependent addon is ignored")
end

-- No culprit gives the reinstall line.
do
	local _, _, text = run({}, false)
	equal(text, "My Addon could not start. Reinstall My Addon to fix this.", "no culprit asks for a reinstall")
end

-- The client API names the culprit even when the bare global is missing.
do
	local global = _G.GetAddOnMetadata
	_G.GetAddOnMetadata = nil
	local culprit = entry({ name = "LegacyForever", title = "Legacy Forever", tag = "v1.4.1" })
	local _, _, text = run({ culprit }, false)
	_G.GetAddOnMetadata = global
	equal(text, "My Addon: Legacy Forever is out of date. Update it to fix this.", "C_AddOns names the culprit")
end

-- Colour codes come off both titles.
do
	own.title = "|cff00ff00My Addon|r"
	local culprit = entry({ name = "LegacyForever", title = "|cffff0000Legacy Forever|r", tag = "v1.4.1" })
	local _, _, text = run({ culprit }, false)
	equal(text, "My Addon: Legacy Forever is out of date. Update it to fix this.", "colour codes are stripped")
	own.title = "My Addon"
end

-- ns.L overrides a phrase.
do
	local L = { ["%s: %s is out of date. Update it to fix this."] = "%s: update %s now." }
	local culprit = entry({ name = "LegacyForever", title = "Legacy Forever", tag = "v1.4.1" })
	local _, _, text = run({ culprit }, false, L)
	equal(text, "My Addon: update Legacy Forever now.", "ns.L overrides the phrase")
end

-- An English-only ns.L holds true for each phrase, so the key is printed.
do
	local L = { ["%s could not start. Reinstall %s to fix this."] = true }
	local _, _, text = run({}, false, L)
	equal(text, "My Addon could not start. Reinstall My Addon to fix this.", "a true phrase prints the English key")
end

-- ns.L with a translated string prints the translation.
do
	local L = { ["%s: %s are out of date. Update them to fix this."] = "%s must be updated: %s." }
	local first = entry({ name = "AlphaForever", title = "Alpha", tag = "v1.4.0" })
	local second = entry({ name = "BetaForever", title = "Beta", tag = "v1.3.0" })
	local _, _, text = run({ first, second }, false, L)
	equal(text, "My Addon must be updated: Alpha and Beta.", "a translated string is printed")
end

-- A ForeverCore folder that is another addon's is named in one line, never blamed on an out-of-date dependent.
do
	local other = { name = "ForeverCore", title = "Another Core UI", project = "5842317" }
	local ns, result, text = run({}, false, nil, other)
	equal(result, false, "a foreign core returns false")
	equal(ns.broken, true, "a foreign core marks the addon broken")
	equal(text, FOREIGN, "a foreign core is named")
	equal(#messages, 1, "a foreign core takes one line")
	equal(messages[1].red, 1, "the foreign core line uses the error red")
	equal(messages[1].green, 0.1, "the foreign core line uses the error green")
	equal(messages[1].blue, 0.1, "the foreign core line uses the error blue")

	local culprit = entry({ name = "LegacyForever", title = "Legacy Forever", tag = "v1.4.1" })
	local _, _, blames = run({ culprit }, false, nil, other)
	equal(blames, text, "a foreign core is named instead of the out-of-date addon")
end

-- Our project ID keeps the existing branches, whether a dependent is out of date or nothing is named.
do
	local ours = { name = "ForeverCore", title = "ForeverCore", project = "1796337" }
	local culprit = entry({ name = "LegacyForever", title = "Legacy Forever", tag = "v1.4.1" })
	local _, _, text = run({ culprit }, false, nil, ours)
	equal(
		text,
		"My Addon: Legacy Forever is out of date. Update it to fix this.",
		"our core keeps the out-of-date line"
	)
	local _, _, reinstall = run({}, false, nil, ours)
	equal(reinstall, "My Addon could not start. Reinstall My Addon to fix this.", "our core keeps the reinstall line")
end

-- A core that predates the project ID is still ours by its website, and another site is another addon.
do
	local old = { name = "ForeverCore", title = "ForeverCore", website = "https://github.com/cjber/forever-core" }
	local _, _, text = run({}, false, nil, old)
	equal(text, "My Addon could not start. Reinstall My Addon to fix this.", "our website keeps the reinstall line")
	local other = { name = "ForeverCore", title = "Another Core UI", website = "https://example.com/forever-core-ui" }
	local _, _, named = run({}, false, nil, other)
	equal(named, FOREIGN, "another website names the addon")
end

-- A core naming neither marker cannot be proved foreign, so the reinstall line stays.
do
	local bare = { name = "ForeverCore", title = "Another Core UI" }
	local _, _, text = run({}, false, nil, bare)
	equal(
		text,
		"My Addon could not start. Reinstall My Addon to fix this.",
		"an unidentifiable core asks for a reinstall"
	)
end

-- A metadata call that errors is handled: no Lua error, and the existing line.
do
	local broken = { name = "ForeverCore", title = "ForeverCore", project_error = true }
	local _, _, text = run({}, false, nil, broken)
	equal(
		text,
		"My Addon could not start. Reinstall My Addon to fix this.",
		"a metadata error keeps the reinstall line"
	)
end

-- Colour codes come off the foreign core's title, and ns.L overrides the new phrase.
do
	local other = { name = "ForeverCore", title = "|cffff0000Another Core UI|r", project = "5842317" }
	local _, _, text = run({}, false, nil, other)
	equal(text, FOREIGN, "the foreign title is stripped")
	local L = { [FOREIGN_KEY] = "%s: %s is not our core." }
	local _, _, overridden = run({}, false, L, other)
	equal(overridden, "My Addon: Another Core UI is not our core.", "ns.L overrides the foreign phrase")
end

print(("forever_require_spec: %d checks passed"):format(checks))
