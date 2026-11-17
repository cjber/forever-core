-- UI/TrackerLock.lua lets a section header drag the column and reads the Lock switch that stops the drag. It is loaded
-- on its own here: the host's settings arrive through ns.TrackerHost, so the module holds no copy of the switch, and a
-- host that is not loaded yet simply reads as unlocked.
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end
local frames, combat = {}, false
local function frame()
	local f = { width = 250, height = 0, scripts = {}, shown = true, scale = 1, left = 0, top = 640 }
	function f:SetParent(owner)
		self.parent = owner
	end
	function f:SetPoint(...)
		self.point = { ... }
	end
	function f:GetPoint()
		return unpack(self.point or {})
	end
	function f:SetHeight(value)
		self.height = value
	end
	function f:GetHeight()
		return self.height
	end
	function f:GetEffectiveScale()
		return self.scale
	end
	function f:SetScript(event, fn)
		self.scripts[event] = fn
	end
	function f:RegisterForDrag(button)
		self.dragButton = button
	end
	function f:HookScript(event, fn)
		self.scripts[event] = fn
	end
	function f:SetShown(value)
		self.shown = value
	end
	function f:IsShown()
		return self.shown
	end
	function f.Hide(self)
		self.shown = false
	end
	function f.Show(self)
		self.shown = true
	end
	function f:StartMoving()
		self.moving = true
	end
	function f:StopMovingOrSizing()
		self.moving = false
	end
	function f:GetLeft()
		return self.left
	end
	function f:GetTop()
		return self.top
	end
	frames[#frames + 1] = f
	return f
end
local parent = frame()
parent.height = 1080
local ns = {}
local env = setmetatable({
	UIParent = parent,
	CreateFrame = function(...)
		local made = frame(...)
		made.parent = select(3, ...)
		return made
	end,
	InCombatLockdown = function()
		return combat
	end,
}, { __index = _G })
env._G = env
setfenv(assert(loadfile("UI/TrackerLock.lua")), env)("Test", ns)
local module = assert(ns.TrackerLock, "the module registers itself on the namespace")

-- A host standing in for UI/TrackerHost.lua, which is what the drag asks for the switch and to save a position. The
-- module finds it on the namespace, as it does at runtime.
local locked, saved = false, {}
local host = {
	IsLocked = function()
		return locked
	end,
	SavePosition = function(x, y)
		saved[#saved + 1] = { x, y }
	end,
}

-- With no host loaded yet the module reads as unlocked rather than erroring: the TOC loads this file first.
check(module.Locked() == false, "a host that is not loaded yet reads as unlocked")
ns.TrackerHost = host
local created = #frames
local column = frame()
local drag = module.Drag(column, host)
check(#frames == created + 1, "the drag draws no frame of its own: no grip, no handle")
local header = frame()
drag.Attach(header)
check(header.dragButton == "LeftButton", "a section header drags with the left button")
local function press()
	header.scripts.OnMouseDown(header, "LeftButton")
	header.scripts.OnDragStart(header)
end

-- A host that answers but has no IsLocked, as an older companion addon's would.
host.IsLocked = nil
check(module.Locked() == false, "a host without IsLocked reads as unlocked")
host.IsLocked = function()
	return locked
end

-- Unlocked: a header drag moves the column and saves where it stopped.
press()
check(column.moving == true, "an unlocked header drag moves the column")
check(drag.Dragging() == true, "the host can see a drag in progress")
column.left, column.top = 500, 900
header.scripts.OnDragStop(header)
check(column.moving == false, "letting go stops the move")
check(drag.Dragging() == false, "a finished drag is no longer in progress")
check(drag.Dragged() == true, "the press that just ended was a drag, so its click is skipped")
check(#saved == 1, "the drag saves once")
check(saved[1][1] == 500 and saved[1][2] == -180, "the drag saves the column's screen position")
header.scripts.OnMouseDown(header, "LeftButton")
check(drag.Dragged() == false, "the next press starts as a click")

-- Locked: the drag is refused before it starts, so letting go saves nothing and the press stays a click.
locked = true
check(module.Locked(), "lock reads back from the host")
press()
check(column.moving == false, "a locked drag never starts")
column.left, column.top = 510, 910
header.scripts.OnDragStop(header)
check(#saved == 1, "a locked drag saves no new position")
check(drag.Dragged() == false, "a refused drag leaves the click alone")
locked = false

-- In combat the drag waits for it to end, as the host does.
combat = true
press()
check(column.moving == false, "a drag in combat waits")
combat = false
press()
check(column.moving == true, "the drag works once combat ends")
header.scripts.OnDragStop(header)

print("tracker_lock_spec: " .. checks .. " checks passed")
