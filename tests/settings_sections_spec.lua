local checks = 0
local function check(value, message)
	checks = checks + 1
	assert(value, message)
end
local function equal(actual, expected, message)
	checks = checks + 1
	assert(actual == expected, ("%s: expected %s, got %s"):format(message, tostring(expected), tostring(actual)))
end

local registered
local calls = 0
_G.Settings = {
	RegisterInitializer = function(category, initializer)
		calls = calls + 1
		registered = { category = category, initializer = initializer }
	end,
}
_G.CreateSettingsListSectionHeaderInitializer = function(name, tooltip, newTagID)
	return { name = name, tooltip = tooltip, newTagID = newTagID }
end

local ns = {}
assert(loadfile("UI/SettingsSections.lua"))("ForeverCore", ns)
local category = { layout = {
	AddInitializer = function()
		error("the API must not mutate a settings layout")
	end,
} }
local initializer = ns.SettingsSections.Register(category, "Options", "Choose a setting", 7)
check(initializer ~= nil, "register returns the Blizzard initializer")
equal(calls, 1, "registers once through Settings.RegisterInitializer")
equal(registered.category, category, "preserves the category")
equal(registered.initializer, initializer, "registers the returned initializer")
equal(initializer.name, "Options", "preserves the localized heading")
equal(initializer.tooltip, "Choose a setting", "preserves the localized tooltip")
equal(initializer.newTagID, 7, "preserves the new tag")
check(ns.SettingsSections.Register(nil, "Invalid") == nil, "rejects a missing category")
check(ns.SettingsSections.Register(category, nil) == nil, "rejects a missing heading")

local makeHeader = _G.CreateSettingsListSectionHeaderInitializer
_G.CreateSettingsListSectionHeaderInitializer = nil
check(ns.SettingsSections.Register(category, "Missing API") == nil, "refuses a missing header API")
_G.CreateSettingsListSectionHeaderInitializer = makeHeader
local register = _G.Settings.RegisterInitializer
_G.Settings.RegisterInitializer = nil
check(ns.SettingsSections.Register(category, "Missing registration") == nil, "refuses missing registration")
_G.Settings.RegisterInitializer = register
equal(calls, 1, "invalid requests do not register rows")

print(("settings_sections_spec: %d checks"):format(checks))
