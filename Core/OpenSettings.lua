-- luacheck: globals C_SettingsUtil securecallfunction
local _, ns = ...

-- The restricted C opener is the client's own entry point. Calling the Lua SettingsPanel wrapper also enters its
-- gamepad focus code under the addon's call path, which can produce a blocked-action message.
---@param categoryID? integer
---@param element? string
---@return boolean
function ns.OpenSettingsPanel(categoryID, element)
	if InCombatLockdown() or type(securecallfunction) ~= "function" then
		return false
	end
	local open = C_SettingsUtil and C_SettingsUtil.OpenSettingsPanel
	if type(open) ~= "function" then
		return false
	end
	securecallfunction(open, categoryID, element)
	return true
end
