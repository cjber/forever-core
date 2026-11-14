local _, ns = ...

-- Native settings lists own their layout and gamepad focus state. Register through Blizzard's public Settings API;
-- never reach into a category's layout and call AddInitializer from addon code.
---@class ForeverSettingsSectionsAPI
local Sections = {}
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
