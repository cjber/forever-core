-- luacheck: globals C_SettingsUtil SettingsPanel
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	assert(actual == expected, ("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)))
end

local combat = false
local calls = {}
local secureCalls = 0
_G.InCombatLockdown = function()
	return combat
end

_G.securecallfunction = function(fn, ...)
	equal(fn, C_SettingsUtil.OpenSettingsPanel, "secure call uses the restricted client opener")

	secureCalls = secureCalls + 1
	return fn(...)
end
_G.C_SettingsUtil = {
	OpenSettingsPanel = function(categoryID, element)
		calls[#calls + 1] = { categoryID, element }
	end,
}
_G.SettingsPanel = {
	OpenToCategory = function()
		error("the Lua wrapper must never be called, even when the C opener is missing")
	end,
}
local ns = {}
assert(loadfile("Core/OpenSettings.lua"))("ForeverCore", ns)
equal(ns.OpenSettingsPanel(313, "ForeverCore"), true, "settings opens securely")
equal(calls[1][1], 313, "category is passed")
equal(calls[1][2], "ForeverCore", "element is passed")
equal(secureCalls, 1, "one secure call is used")
equal(ns.OpenSettingsPanel(), true, "settings opens without a category")
equal(calls[2][1], nil, "missing category stays nil")
equal(calls[2][2], nil, "missing element stays nil")
combat = true
equal(ns.OpenSettingsPanel(314), false, "combat blocks settings")
equal(#calls, 2, "combat makes no call")
combat = false
_G.C_SettingsUtil = nil
equal(ns.OpenSettingsPanel(315), false, "missing panel blocks safely")
_G.C_SettingsUtil = {}
equal(ns.OpenSettingsPanel(315), false, "missing method blocks safely")
_G.C_SettingsUtil.OpenSettingsPanel = function(categoryID, element)
	calls[#calls + 1] = { categoryID, element }
end
_G.securecallfunction = nil
equal(ns.OpenSettingsPanel(315), false, "missing secure call blocks safely")
_G.securecallfunction = function(fn, ...)
	return fn(...)
end
_G.CreateSecureDelegate = function()
	error("must not be used")
end
equal(ns.OpenSettingsPanel(316, "row"), true, "delegate global is ignored")
equal(calls[3][1], 316, "category reaches Blizzard method")
equal(calls[3][2], "row", "element reaches Blizzard method")
print(("open_settings_spec: %d checks passed"):format(checks))
