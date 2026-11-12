-- luacheck: globals C_Map securecallfunction
local _, ns = ...

-- Dispatch through the client's securecallfunction boundary. This does not change the caller's taint.
-- False means the boundary or the C opener is unavailable, or combat prevents the request.
---@param mapID? integer
---@return boolean
function ns.OpenMap(mapID)
	if InCombatLockdown() then
		return false
	end
	if type(securecallfunction) ~= "function" then
		return false
	end
	local open = C_Map and C_Map.OpenWorldMap
	if type(open) ~= "function" then
		return false
	end
	-- 0 is the client's "no map id": open where the player is rather than at a map that does not exist.
	local map = mapID ~= nil and mapID ~= 0 and mapID or nil
	securecallfunction(open, map)
	return true
end
