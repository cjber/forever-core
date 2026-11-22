---@type string, ForeverTrackerNamespace
local _, ns = ...

-- How the player moves the shared tracker: a left-button drag on any section header moves the whole private column
-- UI/TrackerHost.lua owns, and the Lock switch in the header's right-click menu stops that drag. There is no handle,
-- cursor or hint of its own. Locking writes the saved switch, never a frame, so it is safe to change in combat.
--
-- Shared with UI/TrackerHost.lua: TrackerLock.Locked reads the switch through the host's own IsLocked, and a finished
-- drag goes to the host's SavePosition.
---@class ForeverTrackerLock
local TrackerLock = {}
ns.TrackerLock = TrackerLock

-- The switch lives in the player's saved tracker settings, which the host owns, so this module keeps no copy of it.
---@return boolean
function TrackerLock.Locked()
	local host = ns.TrackerHost
	return host ~= nil and host.IsLocked ~= nil and host.IsLocked() == true
end

-- Returns what the host needs to let its headers drag `host`: Attach for each section header, whether a drag is in
-- progress, and whether the press that just ended was a drag, so the header's click action skips it.
---@param host Frame
---@param source ForeverTrackerHostAPI
---@return ForeverTrackerDrag
function TrackerLock.Drag(host, source)
	-- Only a drag a header started keeps moving, so OnDragStop ignores whatever a locked or combat press refused.
	local dragging, dragged = false, false
	local function Start()
		-- The column holds still in combat, when its secure item buttons are protected.
		if TrackerLock.Locked() or InCombatLockdown() then
			return
		end
		dragging, dragged = true, true
		host:StartMoving()
	end
	local function Stop()
		if not dragging then
			return
		end
		dragging = false
		if InCombatLockdown() then
			return
		end
		host:StopMovingOrSizing()
		local scale = host:GetEffectiveScale() / UIParent:GetEffectiveScale()
		source.SavePosition((host:GetLeft() or 0) * scale, (host:GetTop() or 0) * scale - UIParent:GetHeight())
	end
	-- Finish moving the column while the combat-entry event can still move protected frames.
	local combatEvents = CreateFrame("Frame")
	combatEvents:RegisterEvent("PLAYER_REGEN_DISABLED")
	combatEvents:SetScript("OnEvent", Stop)
	return {
		---@param header Frame
		Attach = function(header)
			header:RegisterForDrag("LeftButton")
			-- A new press starts undragged, whichever of OnDragStop and OnMouseUp the client sends first.
			header:HookScript("OnMouseDown", function()
				dragged = false
			end)
			header:HookScript("OnDragStart", Start)
			header:HookScript("OnDragStop", Stop)
		end,
		Dragging = function()
			return dragging
		end,
		Dragged = function()
			return dragged
		end,
	}
end
