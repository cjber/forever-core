-- luacheck: globals SettingsPanel securecallfunction
local _, ns = ...

-- SettingsPanel:OpenToCategory is Blizzard's own untainted entry point. Calling it through
-- securecallfunction preserves the client's taint boundary on builds without CreateSecureDelegate.
---@param categoryID? integer
---@param element? string
---@return boolean
function ns.OpenSettingsPanel(categoryID, element)
	if InCombatLockdown() or type(securecallfunction) ~= "function" then
		return false
	end
	if type(SettingsPanel) ~= "table" or type(SettingsPanel.OpenToCategory) ~= "function" then
		return false
	end
	securecallfunction(SettingsPanel.OpenToCategory, SettingsPanel, categoryID, element)
	return true
end
