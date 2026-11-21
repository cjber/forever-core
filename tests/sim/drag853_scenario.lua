-- luacheck: read globals scenario
scenario("drag853: a header drag ends before combat lockdown", function(sim)
	sim:login()
	local G = sim.G
	local stops, savedX, savedY = 0
	local function beforeLockdown()
		assert(not G.InCombatLockdown(), "drag touched the column in lockdown")
	end
	local column = {
		StartMoving = beforeLockdown,
		StopMovingOrSizing = function()
			beforeLockdown()
			stops = stops + 1
		end,
		GetEffectiveScale = function()
			beforeLockdown()
			return G.UIParent:GetEffectiveScale()
		end,
		GetLeft = function()
			beforeLockdown()
			return 320
		end,
		GetTop = function()
			beforeLockdown()
			return G.UIParent:GetHeight() - 140
		end,
	}
	local drag = G.ForeverCore.TrackerLock.Drag(column, {
		SavePosition = function(x, y)
			beforeLockdown()
			savedX, savedY = x, y
		end,
	})
	local scripts = {}
	drag.Attach({
		RegisterForDrag = function() end,
		HookScript = function(_, script, callback)
			scripts[script] = callback
		end,
	})
	scripts.OnDragStart()
	assert(drag.Dragging(), "the header started a drag")
	sim:enterCombat()
	assert(stops == 1 and not drag.Dragging(), "combat entry stopped the move before lockdown")
	assert(savedX == 320 and savedY == -140, "combat entry saved the position")
	scripts.OnDragStop()
	assert(stops == 1 and drag.Dragged(), "releasing the header does not stop twice or click")
	sim:leaveCombat()
	sim:expectNoErrors("ForeverCore")
end)
