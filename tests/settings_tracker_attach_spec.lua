-- The shared tracker's "Attach to quest tracker" row comes from core for every consumer (#910): one label, one
-- tooltip, a proxy over the host's saved choice, and a redraw when the choice changes elsewhere.
local checks = 0
local function check(value, message)
	checks = checks + 1
	assert(value, message)
end
local function equal(actual, expected, message)
	checks = checks + 1
	assert(actual == expected, ("%s: expected %s, got %s"):format(message, tostring(expected), tostring(actual)))
end

local L = setmetatable({}, {
	__index = function(_, key)
		return key
	end,
})
local saved = { attached = true }
local callbacks = {}
local picks = {}
local host = {
	GetSettings = function()
		return saved
	end,
	SetAttached = function(value)
		picks[#picks + 1] = value
		saved.attached = value
		for _, callback in ipairs(callbacks) do
			callback(value)
		end
	end,
	OnAttachmentChanged = function(callback)
		callbacks[#callbacks + 1] = callback
	end,
}

local registered, notified = {}, {}
_G.Settings = {
	VarType = { Boolean = "boolean" },
	RegisterProxySetting = function(category, variable, varType, name, default, get, set)
		local setting = {
			category = category,
			variable = variable,
			varType = varType,
			name = name,
			default = default,
			get = get,
			set = set,
		}
		return setting
	end,
	CreateCheckboxInitializer = function(setting, options, tooltip)
		return { setting = setting, options = options, tooltip = tooltip }
	end,
	RegisterInitializer = function(category, initializer)
		registered[#registered + 1] = { category = category, initializer = initializer }
	end,
	NotifyUpdate = function(variable)
		notified[#notified + 1] = variable
	end,
}

local ns = { L = L, TrackerHost = host }
-- SettingsPage loads first in the TOC and holds the tooltip phrase.
_G.CreateFrame = function() end
assert(loadfile("UI/SettingsPage.lua"))("ForeverCore", ns)
assert(loadfile("UI/SettingsSections.lua"))("ForeverCore", ns)
equal(ns.SettingsSections.minor, 1, "the module minor names RegisterTrackerAttach")

local category = {}
local setting, initializer = ns.SettingsSections.RegisterTrackerAttach(category, "TestAddon_trackerAttached")
check(setting and initializer, "registers the row")
equal(#registered, 1, "one initializer goes in through Settings.RegisterInitializer")
equal(registered[1].category, category, "into the addon's category")
equal(setting.variable, "TestAddon_trackerAttached", "under the addon's own variable")
equal(setting.name, "Attach to quest tracker", "core's label")
equal(setting.varType, "boolean", "a boolean row")
equal(setting.default, true, "on by default, the Under placement")
check(initializer.tooltip:find("Every Forever addon shows this same setting", 1, true), "core's tooltip")
equal(setting.get(), true, "reads the host's saved choice")
setting.set(false)
equal(picks[1], false, "writes through SetAttached")
equal(setting.get(), false, "reads the new choice")
equal(notified[#notified], "TestAddon_trackerAttached", "a change anywhere redraws the row")

-- A second addon gets the same row in its own category, and both redraw on one change.
local other = ns.SettingsSections.RegisterTrackerAttach({}, "OtherAddon_trackerAttached")
equal(other.name, setting.name, "the same label in every addon")
host.SetAttached(true)
local seen = {}
for _, variable in ipairs(notified) do
	seen[variable] = true
end
check(seen.TestAddon_trackerAttached and seen.OtherAddon_trackerAttached, "both rows redraw")

-- A second call for the same variable hands back the first row instead of registering it again.
local count = #registered
local again = ns.SettingsSections.RegisterTrackerAttach(category, "TestAddon_trackerAttached")
equal(again, setting, "the same row comes back")
equal(#registered, count, "and nothing more is registered")

-- An older adopted tracker is drawing: no row, since its attach behaves differently.
ns.TrackerHostForeign = true
equal(ns.SettingsSections.RegisterTrackerAttach({}, "Foreign_trackerAttached"), nil, "no row on an adopted host")
ns.TrackerHostForeign = nil

-- Missing pieces register nothing instead of erroring.
equal(ns.SettingsSections.RegisterTrackerAttach(nil, "X"), nil, "rejects a missing category")
equal(ns.SettingsSections.RegisterTrackerAttach({}, nil), nil, "rejects a missing variable")
ns.TrackerHost = { GetSettings = host.GetSettings }
equal(ns.SettingsSections.RegisterTrackerAttach({}, "Y"), nil, "refuses a host without SetAttached")
ns.TrackerHost = host

-- The canvas page variant: the same words, and it ticks itself when the choice changes elsewhere.
local created = {}
_G.CreateFrame = function()
	local frame = { checked = nil, scripts = {} }
	function frame.SetPoint() end
	function frame:SetChecked(value)
		self.checked = value
	end
	function frame:GetChecked()
		return self.checked
	end
	function frame:SetScript(name, fn)
		self.scripts[name] = fn
	end
	function frame.CreateFontString()
		return {
			SetPoint = function() end,
			SetText = function(text, value)
				text.value = value
			end,
		}
	end
	created[#created + 1] = frame
	return frame
end
local pageNs = { L = L, TrackerHost = host }
assert(loadfile("UI/SettingsPage.lua"))("ForeverCore", pageNs)
equal(pageNs.SettingsPage.minor, 1, "the page minor names AddTrackerAttach")
local panel = { foreverL = {} }
function panel.CreateFontString()
	return { SetPoint = function() end, SetText = function() end }
end
local box = pageNs.SettingsPage.AddTrackerAttach(panel)
check(box, "adds the tick box")
equal(box.checked, true, "ticked while attached")
check(box.tooltipText:find("Every Forever addon shows this same setting", 1, true), "core's tooltip on the canvas")
box.checked = false
box.scripts.OnClick(box)
equal(saved.attached, false, "a click writes through SetAttached")
host.SetAttached(true)
equal(box.checked, true, "a change elsewhere ticks it again")
equal(pageNs.SettingsPage.AddTrackerAttach(panel), box, "a panel gets one tick box")
pageNs.TrackerHostForeign = true
equal(pageNs.SettingsPage.AddTrackerAttach({ foreverL = {} }), nil, "no tick box on an adopted host")

print(("settings_tracker_attach_spec: %d checks"):format(checks))
