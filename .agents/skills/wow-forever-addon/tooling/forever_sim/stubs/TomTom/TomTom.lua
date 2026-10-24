-- luacheck: globals TomTom
-- A stand-in for TomTom's waypoint API, written for forever_sim from its documented calls (no TomTom code).
-- TomTom.waypoints lists every waypoint added and not removed, for scenarios to read.
TomTom = { waypoints = {}, closest = nil }

function TomTom:AddWaypoint(mapID, x, y, opts)
	local uid = { mapID, x, y, title = opts and opts.title, opts = opts }
	table.insert(self.waypoints, uid)
	return uid
end

function TomTom:RemoveWaypoint(uid)
	for i, w in ipairs(self.waypoints) do
		if w == uid then
			table.remove(self.waypoints, i)
			if self.closest == uid then
				self.closest = nil
			end
			return true
		end
	end
	return false
end

function TomTom:IsValidWaypoint(uid)
	for _, w in ipairs(self.waypoints) do
		if w == uid then
			return true
		end
	end
	return false
end

function TomTom:SetClosestWaypoint(uid)
	self.closest = uid
end

function TomTom:GetClosestWaypoint()
	return self.closest or self.waypoints[1]
end

function TomTom.HideAllWaypoints() end

function TomTom.GetKeyArgs(_, mapID, x, y, title)
	return string.format("%d:%.4f:%.4f:%s", mapID or 0, x or 0, y or 0, tostring(title))
end
