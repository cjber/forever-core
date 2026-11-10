local _, ns = ...

-- The client's own restricted openers, run with secure execution taint. CreateSecureDelegate wraps a Lua function so
-- a call from addon code runs as the client, not as the addon. C_Map.OpenWorldMap and C_SettingsUtil.OpenSettingsPanel
-- are both HasRestrictions functions: called directly from addon code, the client refuses them and blames the addon
-- (cjber/adventure-guide-forever#411, cjber/forever-core#333). Each delegate is created once, on first use, so a spec
-- without the client's delegate never runs it at load.
local secureOpenWorldMap
local secureOpenSettingsPanel

-- CreateSecureDelegate is absent on some Forever builds (cjber/adventure-guide-forever#592), and the C functions are
-- themselves refused from addon-tainted code: without the delegate there is no secure way to open either one, so we
-- leave it closed rather than error or taint the client's fields. False when nothing was opened.
---@param mapID? integer
---@return boolean
function ns.OpenMap(mapID)
	if InCombatLockdown() then
		return false
	end
	if not secureOpenWorldMap then
		local open = C_Map and C_Map.OpenWorldMap
		if type(CreateSecureDelegate) ~= "function" or type(open) ~= "function" then
			return false
		end
		secureOpenWorldMap = CreateSecureDelegate(open)
	end
	-- 0 is the client's "no map id": open where the player is rather than at a map that does not exist.
	local map = mapID ~= nil and mapID ~= 0 and mapID or nil
	secureOpenWorldMap(map)
	return true
end

-- Opens Options, optionally on a category and scrolled to an element, through the client's own
-- C_SettingsUtil.OpenSettingsPanel. Never in combat, like the client's own panel code. False when nothing opened.
---@param categoryID? integer
---@param element? string
---@return boolean
function ns.OpenSettingsPanel(categoryID, element)
	if InCombatLockdown() then
		return false
	end
	if not secureOpenSettingsPanel then
		local open = C_SettingsUtil and C_SettingsUtil.OpenSettingsPanel
		if type(CreateSecureDelegate) ~= "function" or type(open) ~= "function" then
			return false
		end
		secureOpenSettingsPanel = CreateSecureDelegate(open)
	end
	secureOpenSettingsPanel(categoryID, element)
	return true
end
