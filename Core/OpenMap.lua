local _, ns = ...

-- The client's own restricted world map opener, run with secure execution taint. CreateSecureDelegate wraps a Lua
-- function so a call from addon code runs as the client, not as the addon. C_Map.OpenWorldMap is a HasRestrictions
-- function: called directly from addon code, the client refuses it and blames the addon
-- (cjber/adventure-guide-forever#411, cjber/forever-core#333). The delegate is created once, on first use, so a spec
-- without the client's delegate never runs it at load.
local secureOpenWorldMap

-- CreateSecureDelegate is absent on some Forever builds (cjber/adventure-guide-forever#592), and the C function is
-- itself refused from addon-tainted code: without the delegate there is no secure way to open it, so we leave it
-- closed rather than error or taint the client's fields. False when nothing was opened.
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
