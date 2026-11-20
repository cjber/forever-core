local _, ns = ...

-- Native settings lists own their layout and gamepad focus state. Register through Blizzard's public Settings API;
-- never reach into a category's layout and call AddInitializer from addon code.
---@class ForeverSettingsSectionsAPI
local Sections = {}
-- Raised with each member the module adds. RegisterTrackerAttach arrived in minor 1.
Sections.minor = 1
ns.SettingsSections = Sections

local delegates = setmetatable({}, { __mode = "k" })

---@param fn function
---@return function
local function Secure(fn)
	if type(CreateSecureDelegate) ~= "function" then
		return fn
	end
	local delegate = delegates[fn]
	if not delegate then
		delegate = CreateSecureDelegate(fn)
		delegates[fn] = delegate
	end
	return delegate
end

---@param category table
---@param name string
---@param tooltip? string
---@param newTagID? number
---@return table?
function Sections.Register(category, name, tooltip, newTagID)
	if type(category) ~= "table" or type(name) ~= "string" then
		return nil
	end
	if not Settings or type(Settings.RegisterInitializer) ~= "function" then
		return nil
	end
	if type(CreateSettingsListSectionHeaderInitializer) ~= "function" then
		return nil
	end
	local initializer = Secure(CreateSettingsListSectionHeaderInitializer)(name, tooltip, newTagID)
	if type(initializer) ~= "table" then
		return nil
	end
	Settings.RegisterInitializer(category, initializer)
	return initializer
end

-- The rows already registered, by variable.
local registeredAttach = {}

-- The shared tracker's "Attach to quest tracker" row, registered here so every addon that draws in the column shows
-- the same setting with the same words, and a player finds it in whichever addon they open (#910). On is the Under
-- placement and off is Left, the same choice as the column's right-click Tracker position menu. The addon picks only
-- the category and a variable name of its own; the row is a proxy that reads and writes the host's saved choice, and
-- it redraws when a drag or another addon's row changes that choice. Its tooltip phrase is SettingsPage's.
---@param category table
---@param variable string unique to the addon, such as "AdventureGuideForever_trackerAttached"
---@return table? setting
---@return table? initializer
function Sections.RegisterTrackerAttach(category, variable)
	local host = ns.TrackerHost
	if type(category) ~= "table" or type(variable) ~= "string" or type(host) ~= "table" then
		return nil
	end
	-- An older store build's tracker can be the one drawing (TrackerHost adopts it): its attach keeps a dragged spot
	-- and some builds stub it, so the row would promise a move that never happens. Show no row then.
	if ns.TrackerHostForeign then
		return nil
	end
	-- Blizzard's Settings refuses a variable twice, so a second call hands back the first row.
	if registeredAttach[variable] then
		return registeredAttach[variable].setting, registeredAttach[variable].initializer
	end
	if
		type(host.GetSettings) ~= "function"
		or type(host.SetAttached) ~= "function"
		or type(host.OnAttachmentChanged) ~= "function"
	then
		return nil
	end
	if
		not Settings
		or type(Settings.RegisterProxySetting) ~= "function"
		or type(Settings.CreateCheckboxInitializer) ~= "function"
		or type(Settings.RegisterInitializer) ~= "function"
	then
		return nil
	end
	local L = ns.L
	local setting = Settings.RegisterProxySetting(
		category,
		variable,
		Settings.VarType and Settings.VarType.Boolean or "boolean",
		L["Attach to quest tracker"],
		true,
		function()
			return host.GetSettings().attached == true
		end,
		function(value)
			host.SetAttached(value == true)
		end
	)
	local initializer = Secure(Settings.CreateCheckboxInitializer)(setting, nil, L[ns.TRACKER_ATTACH_TOOLTIP])
	Settings.RegisterInitializer(category, initializer)
	host.OnAttachmentChanged(function()
		if type(Settings.NotifyUpdate) == "function" then
			Settings.NotifyUpdate(variable)
		end
	end)
	registeredAttach[variable] = { setting = setting, initializer = initializer }
	return setting, initializer
end
