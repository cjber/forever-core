-- Contract for the vendored out-of-date warning every consumer's Core/Require.lua calls.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local own = { title = "My Addon", tag = "v1.5.0" }
local core = { name = "ForeverCore", title = "ForeverCore", project = "1796337", loaded = true, enabled = 2 }
local FOREIGN_KEY = "%s: the installed ForeverCore is another addon (%s). "
	.. "Remove it and install ForeverCore from CurseForge."
local FOREIGN = "My Addon: the installed ForeverCore is another addon (Another Core UI). "
	.. "Remove it and install ForeverCore from CurseForge."
local MISSING_KEY =
	"%s needs ForeverCore. Install it from CurseForge, or choose Reinstall on ForeverCore in the CurseForge app."
local MISSING =
	"My Addon needs ForeverCore. Install it from CurseForge, or choose Reinstall on ForeverCore in the CurseForge app."
local DISABLED = "My Addon: ForeverCore is turned off. Enable it in the AddOns list to fix this."
local addons = {}
local messages = {}
local frames = {}
local loggedIn = true

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

-- Enough of the client's frame API for a line that waits for the world: registering, unregistering and one script.
_G.IsLoggedIn = function()
	return loggedIn
end
_G.CreateFrame = function()
	local frame = { events = {}, scripts = {} }
	function frame:RegisterEvent(event)
		self.events[event] = true
	end
	function frame:UnregisterEvent(event)
		self.events[event] = nil
	end
	function frame:SetScript(name, handler)
		self.scripts[name] = handler
	end
	frames[#frames + 1] = frame
	return frame
end
local function fire(event)
	for _, frame in ipairs(frames) do
		if frame.events[event] and frame.scripts.OnEvent then
			frame.scripts.OnEvent(frame, event)
		end
	end
end

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
		if field == "AddonCompartmentFunc" or field == "AddonCompartmentFuncOnEnter" then
			return item[field]
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
	GetAddOnOptionalDependencies = function(index)
		return unpack(addons[index] and addons[index].optional or {})
	end,
}

local function run(entries, ready, L, core_addon, logged, slash)
	addons = {
		{ name = "MyAddon", title = own.title, loaded = true, enabled = 2, deps = { "ForeverCore" }, tag = own.tag },
	}
	if core_addon ~= false then
		addons[#addons + 1] = core_addon or core
	end
	for _, item in ipairs(entries or {}) do
		addons[#addons + 1] = item
	end
	messages = {}
	frames = {}
	loggedIn = logged ~= false
	local ns = { L = L }
	assert(loadfile("tools/consumer/ForeverRequire.lua"))("MyAddon", ns)
	local result = ns.ForeverRequire(ready, slash)
	return ns, result, messages[1] and messages[1].text
end

-- Ready does nothing at all.
do
	local ns, result = run({}, true)
	equal(result, true, "ready returns true")
	equal(ns.broken, nil, "ready leaves the addon unbroken")
	equal(#messages, 0, "ready shows no message")
	equal(#frames, 0, "ready creates no frame")
end

-- No ForeverCore folder at all names the install, whatever else is installed.
do
	local culprit = entry({ name = "LegacyForever", title = "Legacy Forever", tag = "v1.4.1" })
	local ns, result, text = run({ culprit }, false, nil, false)
	equal(result, false, "a missing core returns false")
	equal(ns.broken, true, "a missing core marks the addon broken")
	equal(text, MISSING, "a missing core names the install")
	equal(#messages, 1, "a missing core takes one line")
	equal(messages[1].red, 1, "the missing core line uses the error red")
	equal(messages[1].green, 0.1, "the missing core line uses the error green")
	equal(messages[1].blue, 0.1, "the missing core line uses the error blue")
end

-- A missing core is named before an out-of-date dependent or a reinstall.
do
	local _, _, text = run({}, false, nil, false)
	equal(text, MISSING, "a missing core is named with nothing else installed")
	local L = { [MISSING_KEY] = "%s: install ForeverCore first." }
	local _, _, overridden = run({}, false, L, false)
	equal(overridden, "My Addon: install ForeverCore first.", "ns.L overrides the missing phrase")
end

-- An installed but turned off ForeverCore asks for it to be enabled, not installed again.
do
	local off = { name = "ForeverCore", title = "ForeverCore", loaded = false, enabled = 0, project = "1796337" }
	local ns, result, text = run({}, false, nil, off)
	equal(result, false, "a turned off core returns false")
	equal(ns.broken, true, "a turned off core marks the addon broken")
	equal(text, DISABLED, "a turned off core asks for it to be enabled")
	equal(#messages, 1, "a turned off core takes one line")
	equal(messages[1].red, 1, "the turned off line uses the error red")
	equal(messages[1].green, 0.1, "the turned off line uses the error green")
	equal(messages[1].blue, 0.1, "the turned off line uses the error blue")
	local culprit = entry({ name = "LegacyForever", title = "Legacy Forever", tag = "v1.4.1" })
	local _, _, blames = run({ culprit }, false, nil, off)
	equal(blames, text, "a turned off core is named instead of the out-of-date addon")
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

-- A consumer that names ForeverCore in OptionalDeps is still named when it is out of date.
do
	local optional = entry({
		name = "OptionalForever",
		title = "Optional Forever",
		tag = "v1.4.0",
		deps = {},
		optional = { "ForeverCore" },
	})
	local _, _, text = run({ optional }, false)
	equal(
		text,
		"My Addon: Optional Forever is out of date. Update it to fix this.",
		"an optional-dependent addon is named"
	)
end

-- Without a readable addon list, the checks fall back to the reinstall line rather than claiming core is missing.
do
	local global = _G.C_AddOns.GetNumAddOns
	_G.C_AddOns.GetNumAddOns = nil
	local _, _, text = run({}, false)
	_G.C_AddOns.GetNumAddOns = global
	equal(
		text,
		"My Addon could not start. Reinstall My Addon to fix this.",
		"an unreadable addon list keeps the reinstall line"
	)
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
	local other = { name = "ForeverCore", title = "Another Core UI", project = "5842317", loaded = true, enabled = 2 }
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
	local ours = { name = "ForeverCore", title = "ForeverCore", project = "1796337", loaded = true, enabled = 2 }
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
	local old = {
		name = "ForeverCore",
		title = "ForeverCore",
		website = "https://github.com/cjber/forever-core",
		loaded = true,
		enabled = 2,
	}
	local _, _, text = run({}, false, nil, old)
	equal(text, "My Addon could not start. Reinstall My Addon to fix this.", "our website keeps the reinstall line")
	local other = {
		name = "ForeverCore",
		title = "Another Core UI",
		website = "https://example.com/forever-core-ui",
		loaded = true,
		enabled = 2,
	}
	local _, _, named = run({}, false, nil, other)
	equal(named, FOREIGN, "another website names the addon")
end

-- A core naming neither marker cannot be proved foreign, so the reinstall line stays.
do
	local bare = { name = "ForeverCore", title = "Another Core UI", loaded = true, enabled = 2 }
	local _, _, text = run({}, false, nil, bare)
	equal(
		text,
		"My Addon could not start. Reinstall My Addon to fix this.",
		"an unidentifiable core asks for a reinstall"
	)
end

-- A metadata call that errors is handled: no Lua error, and the existing line.
do
	local broken = { name = "ForeverCore", title = "ForeverCore", project_error = true, loaded = true, enabled = 2 }
	local _, _, text = run({}, false, nil, broken)
	equal(
		text,
		"My Addon could not start. Reinstall My Addon to fix this.",
		"a metadata error keeps the reinstall line"
	)
end

-- Colour codes come off the foreign core's title, and ns.L overrides the new phrase.
do
	local other = {
		name = "ForeverCore",
		title = "|cffff0000Another Core UI|r",
		project = "5842317",
		loaded = true,
		enabled = 2,
	}
	local _, _, text = run({}, false, nil, other)
	equal(text, FOREIGN, "the foreign title is stripped")
	local L = { [FOREIGN_KEY] = "%s: %s is not our core." }
	local _, _, overridden = run({}, false, L, other)
	equal(overridden, "My Addon: Another Core UI is not our core.", "ns.L overrides the foreign phrase")
end

-- A player still on the loading screen sees the line once the world is drawn, and only once.
do
	local ns, result = run({}, false, nil, false, false)
	equal(result, false, "a logged out addon returns false")
	equal(ns.broken, true, "a logged out addon is marked broken")
	equal(#messages, 0, "a logged out addon shows no line while the world loads")
	equal(#frames, 1, "a logged out addon waits on one frame")
	fire("PLAYER_ENTERING_WORLD")
	equal(#messages, 1, "the first entering world shows the line")
	equal(messages[1].text, MISSING, "the line kept for the world is the same text")
	equal(messages[1].red, 1, "the world line uses the error red")
	equal(messages[1].green, 0.1, "the world line uses the error green")
	equal(messages[1].blue, 0.1, "the world line uses the error blue")
	fire("PLAYER_ENTERING_WORLD")
	equal(#messages, 1, "a second entering world does not repeat the line")

	local off = { name = "ForeverCore", title = "ForeverCore", loaded = false, enabled = 0, project = "1796337" }
	local _, _, text = run({}, false, nil, off, false)
	equal(text, nil, "a logged out turned off core waits too")
	fire("PLAYER_ENTERING_WORLD")
	equal(messages[1] and messages[1].text, DISABLED, "the world shows the branch the addon took")
end

-- A player already in the world sees the line at once, as before.
do
	local ns, result, text = run({}, false, nil, false, true)
	equal(result, false, "a logged in addon returns false")
	equal(ns.broken, true, "a logged in addon is marked broken")
	equal(text, MISSING, "a logged in player sees the line at once")
	equal(#messages, 1, "a logged in player takes one line")
	equal(#frames, 0, "a logged in player needs no frame")
	fire("PLAYER_ENTERING_WORLD")
	equal(#messages, 1, "a later entering world adds no second line")
end

-- A stopped addon's own entry points repeat the line instead of doing nothing or raising an error (#996 in Shortest
-- Path: players who turned ForeverCore off saw the addon stop with no reason they noticed).
do
	local off = { name = "ForeverCore", title = "ForeverCore", loaded = false, enabled = 0, project = "1796337" }
	own.AddonCompartmentFunc = "MyAddon_OnCompartmentClick"
	own.AddonCompartmentFuncOnEnter = "MyAddon_OnCompartmentEnter"
	_G.SlashCmdList = {}
	run({}, false, nil, off, true, { key = "MYADDON", "/myaddon", "/my" })
	equal(_G.SLASH_MYADDON1, "/myaddon", "the first slash word is registered")
	equal(_G.SLASH_MYADDON2, "/my", "the second slash word is registered")
	_G.SlashCmdList.MYADDON("")
	equal(#messages, 2, "the slash command repeats the line")
	equal(messages[2].text, DISABLED, "the slash command names the same fix")
	_G.MyAddon_OnCompartmentClick("MyAddon", "LeftButton")
	equal(#messages, 3, "a compartment click repeats the line")
	equal(messages[3].text, DISABLED, "the compartment click names the same fix")
	_G.MyAddon_OnCompartmentEnter("MyAddon")
	equal(#messages, 3, "hovering the compartment entry shows nothing")

	-- A ready addon defines its own entry points, and one already defined is never replaced.
	_G.MyAddon_OnCompartmentClick, _G.MyAddon_OnCompartmentEnter = nil, nil
	_G.SlashCmdList, _G.SLASH_MYADDON1, _G.SLASH_MYADDON2 = {}, nil, nil
	run({}, true, nil, nil, true, { key = "MYADDON", "/myaddon" })
	equal(_G.MyAddon_OnCompartmentClick, nil, "a ready addon gets no stand-in compartment function")
	equal(_G.SlashCmdList.MYADDON, nil, "a ready addon gets no stand-in slash command")
	local mine = function() end
	_G.MyAddon_OnCompartmentClick = mine
	run({}, false, nil, off, true)
	equal(_G.MyAddon_OnCompartmentClick, mine, "an addon's own compartment function stays")
	own.AddonCompartmentFunc, own.AddonCompartmentFuncOnEnter = nil, nil
	_G.MyAddon_OnCompartmentClick, _G.MyAddon_OnCompartmentEnter, _G.SlashCmdList = nil, nil, nil
end

print(("forever_require_spec: %d checks passed"):format(checks))
