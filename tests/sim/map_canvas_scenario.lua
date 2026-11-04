-- luacheck: read globals scenario ADDON
scenario("shared canvas stays outside the gamepad map tables", { addon = false }, function(sim)
	local ns = {
		SafeCall = function(_, fn, ...)
			return true, fn(...)
		end,
	}
	sim:runAs(ADDON, "")
	assert(sim.templates.loadLua("UI/MapCanvas.lua", ADDON .. "/UI/MapCanvas.lua", ADDON, ns))
	sim.world.maps[1454] = { name = "Orgrimmar", parent = 1411 }
	sim.world.maps[1411] = { name = "Durotar", parent = 1414 }
	sim.world.maps[1414] = { name = "Kalimdor", parent = 947, mapType = 2 }
	sim:login()
	sim:openWorldMap(1454)
	sim:runAs(
		ADDON,
		[[
		local ns = ...
		local mixin = CreateFromMixins(ns.MapCanvas.PinMixin, {
			takesMouse = true,
			clicks = true,
			OnAcquired = function(self)
				self:SetPosition(0.5, 0.5)
				self:SetScalingLimits(1, 1, 1.2)
			end,
		})
		ns.pool = ns.MapCanvas.Pool(WorldMapFrame, mixin, {marker = "route"})
		ns.MapCanvas.Watch(WorldMapFrame, function(_, what)
			if what ~= "hide" then
				ns.pool:ReleaseAll()
				ns.pool:Acquire()
			end
		end)
	]],
		ns
	)
	sim:advance(0.1)
	assert(#ns.pool:Active() == 1, "opening the map draws a private pin")
	sim:setGamepad(true)
	sim:zoomMap(1)
	sim:panMap(0.1, 0)
	sim:gamepadNavigate()
	sim:openWorldMap(1411)
	sim:gamepadNavigate()
	sim:closeWorldMap()
	sim:expectNoGamepadTaint(ADDON)
	sim:expectNoErrors(ADDON)
end)
