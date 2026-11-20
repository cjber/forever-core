-- Lock the Forever tracker in place: while it is on, a section header's drag moves nothing, and it can be turned on or
-- off in combat because it is a saved switch read when the player drags, never a frame move.
--
-- tests/tracker_host_spec.lua covers the rest of the host and stays at the gate's 1000-line limit, so the lock's cases
-- live here, over the same stubbed client surface. The file is byte-identical across the four Forever addons
-- (tools/check_shared_tracker.py), so it names no addon and reads its saved slot through ns.TrackerHostSettings.
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end
local function noop() end
local timers, showed, frames, combat = {}, nil, {}, false
local parent
-- The frame API the host and the header drag use, so a suppressed drag can be told from a move and from a native write.
local function frame()
	local f = { width = 250, height = 0, scripts = {} }
	function f:SetPoint(...)
		self.point = { ... }
	end
	function f.GetPoint(self)
		return unpack(self.point or { "TOPRIGHT", parent, "TOPRIGHT", 0, -100 })
	end
	function f:SetWidth(value)
		self.width = value
	end
	function f:GetWidth()
		return self.width
	end
	function f:SetHeight(value)
		self.height = value
	end
	function f:GetHeight()
		return self.height
	end
	function f:GetEffectiveScale()
		return self.scale or 1
	end
	function f:GetScale()
		return self.scale or 1
	end
	function f:SetScale(value)
		self.scale = value
	end
	function f.GetTop(self)
		return self.top or 640
	end
	function f.GetLeft(self)
		return self.left or 0
	end
	function f.GetRight(self)
		return self:GetLeft() + self:GetWidth()
	end
	function f.GetBottom(self)
		return self:GetTop() - self:GetHeight()
	end
	function f.GetCenter(self)
		return (self:GetLeft() + self:GetRight()) / 2, (self:GetTop() + self:GetBottom()) / 2
	end
	function f:IsShown()
		return self.shown ~= false
	end
	function f:SetScript(event, fn)
		self.scripts[event] = fn
	end
	-- The host watches the native frame's size and the header button; nothing of ours is hooked.
	function f:HookScript(event, fn)
		self.scripts[event] = fn
	end
	function f:SetParent(owner)
		self.parent = owner
	end
	function f:ClearAllPoints()
		self.point = nil
	end
	f.RegisterEvent = noop
	f.SetMovable, f.RegisterForDrag, f.EnableMouse = noop, noop, noop
	f.clamped = true
	function f:SetClampedToScreen(value)
		self.clamped = value
	end
	function f:IsClampedToScreen()
		return self.clamped
	end
	function f:SetShown(value)
		self.shown = value
	end
	function f:StartMoving()
		self.moving = true
	end
	function f:StopMovingOrSizing()
		self.moving = false
	end
	f.Show = function(self)
		self.shown = true
	end
	f.Hide = function(self)
		self.shown = false
	end
	-- The optional backdrop is the only texture the host makes; the lock spec only needs it not to error.
	function f.CreateTexture(_)
		return {
			SetPoint = noop,
			SetAtlas = noop,
			SetVertexColor = noop,
			SetShown = noop,
			Hide = noop,
		}
	end
	frames[#frames + 1] = f
	return f
end
local native = frame()
local minimap = frame()
minimap.left, minimap.right, minimap.top, minimap.bottom, minimap.shown = 900, 1100, 700, 500, false
parent = frame()
parent.width = 1200
parent:SetHeight(1080)
native.height = 300
native.NineSlice = {
	GetBottom = function()
		return 0
	end,
	GetCenter = function()
		return native:GetCenter()
	end,
	GetEffectiveScale = function()
		return 1
	end,
}
local nativeHeader = frame()
nativeHeader.MinimizeButton = frame()
native.Header = nativeHeader
function native.UpdateHeaderPosition() end
function native.IsCollapsed()
	return false
end
function native.UpdateHeight() end
local ns = {
	-- English phrases, as the addon that translates by phrase has them. Nothing is set for the lock's constant key,
	-- so the host falls back to its own English sentence, which is what a player without that translation reads.
	L = setmetatable({}, {
		__index = function(_, key)
			return key
		end,
	}),
}
-- A saved table shaped like the host's own slot in the player's saved variables. A spec writes fields on it, the way
-- another addon's options row does through the host's setters.
local hostSettings = { attached = false, x = 100, y = -100 }
---@return ForeverTrackerSettings
function ns.TrackerHostSettings()
	return hostSettings
end
local env = setmetatable({
	InCombatLockdown = function()
		return combat
	end,
	ObjectiveTrackerFrame = native,
	Minimap = minimap,
	UIParent = parent,
	CreateFrame = frame,
	GameTooltip = GameTooltip,
	C_Timer = {
		After = function(_, fn)
			timers[#timers + 1] = fn
		end,
	},
	EventUtil = {
		ContinueAfterAllEvents = function(fn)
			showed = fn
		end,
	},
	EventRegistry = { RegisterCallback = noop, TriggerEvent = noop },
	EditModeManagerFrame = {
		scripts = {},
		IsEditModeActive = function()
			return false
		end,
		IsShown = function()
			return false
		end,
		HookScript = function(self, event, fn)
			self.scripts[event] = fn
		end,
	},
	C_XMLUtil = {
		GetTemplateInfo = function()
			return { type = "Frame" }
		end,
	},
	Mixin = function(target, mixin)
		for key, value in pairs(mixin) do
			target[key] = value
		end
	end,
	hooksecurefunc = function()
		error("the shared host must not hook anything")
	end,
	CreateFramePoolCollection = function()
		return {
			GetOrCreatePool = function()
				return {
					Acquire = function()
						return frame(), true
					end,
				}
			end,
			Release = noop,
		}
	end,
}, { __index = _G })
env._G = env
-- In TOC order: UI/TrackerLock.lua, then the host that hands it each section header.
setfenv(assert(loadfile("UI/TrackerLock.lua")), env)("Test", ns)
setfenv(assert(loadfile("UI/TrackerOrder.lua")), env)("Test", ns) -- the section order, loaded before the host
setfenv(assert(loadfile("UI/TrackerHost.lua")), env)("Test", ns)
local host = frames[6]
-- One section, so there is a header to drag. It draws nothing: the lock cases need no layout.
local section = frame()
section.Header = frame()
section.Update = noop
function section.GetContentsHeight()
	return 0
end
ns.TrackerHost.Attach(section)
local header = section.Header
local function drain()
	local pending = timers
	timers = {}
	for _, fn in ipairs(pending) do
		fn()
	end
end
showed()
drain()
local function drag()
	header.scripts.OnMouseDown(header, "LeftButton")
	header.scripts.OnDragStart(header)
	-- Let go somewhere a drag would have put it: a suppressed drag must neither move nor save.
	host.left, host.top = 500, 900
	header.scripts.OnDragStop(header)
	drain()
end

-- Off for a fresh player, for a missing value and for one that is not a boolean.
check(ns.TrackerHost.IsLocked() == false, "lock is off by default")
check(hostSettings.locked == false, "a fresh tracker settings table saves lock as off")
hostSettings.locked = "yes"
check(ns.TrackerHost.IsLocked() == false, "a saved lock that is not a boolean reads as off")
hostSettings.locked = nil
check(ns.TrackerHost.IsLocked() == false, "a missing lock reads as off")

-- Unlocked: a section header drags the column.
drag()
check(host.moving == false and hostSettings.x == 500 and hostSettings.y == -180, "an unlocked drag moves and saves")

-- Locked: OnDragStart returns before it starts anything, so the column stays put and nothing is saved.
ns.TrackerHost.SetLocked(true)
check(ns.TrackerHost.IsLocked(), "lock reads back from the saved settings")
local savedX, savedY = hostSettings.x, hostSettings.y
drag()
check(not host.moving, "a locked drag never starts moving the column")
check(hostSettings.x == savedX and hostSettings.y == savedY, "a locked drag saves no new position")

-- The next drag after unlocking works again.
ns.TrackerHost.SetLocked(false)
check(not ns.TrackerHost.IsLocked() and hostSettings.locked == false, "turning lock off saves it")
drag()
check(not host.moving and hostSettings.x == 500 and hostSettings.y == -180, "the next drag saves again")
ns.TrackerHost.SetLocked(true)
check(ns.TrackerHost.IsLocked() and hostSettings.locked == true, "turning lock on saves it")
drag()
check(not host.moving, "the next drag after locking is suppressed")

-- In combat the switch is safe to change: it writes the saved value and nothing else.
local nativePoint, nativeHeight = native.point, native.height
local writes = 0
local setPoint, setHeight, clearPoints = host.SetPoint, host.SetHeight, host.ClearAllPoints
host.SetPoint = function(self, ...)
	writes = writes + 1
	return setPoint(self, ...)
end
host.SetHeight = function(self, ...)
	writes = writes + 1
	return setHeight(self, ...)
end
host.ClearAllPoints = function(self, ...)
	writes = writes + 1
	return clearPoints(self, ...)
end
combat = true
ns.TrackerHost.SetLocked(false)
check(hostSettings.locked == false and not ns.TrackerHost.IsLocked(), "lock turns off in combat")
ns.TrackerHost.SetLocked(true)
check(hostSettings.locked == true and ns.TrackerHost.IsLocked(), "lock turns back on in combat")
check(writes == 0, "changing lock in combat moves no frame")
-- Combat already suppresses a drag on its own, so unlocking there is still no move to start.
ns.TrackerHost.SetLocked(false)
drag()
check(not host.moving, "an unlocked drag still waits for combat to end")
combat = false
check(
	native.point == nativePoint and native.height == nativeHeight,
	"changing lock writes nothing on the native tracker"
)
host.SetPoint, host.SetHeight, host.ClearAllPoints = setPoint, setHeight, clearPoints
drag()
check(host.moving == false and hostSettings.x == 500 and hostSettings.y == -180, "the drag works again after combat")

-- The attach checkbox picks Under, which releases the drag.
ns.TrackerHost.SetAttached(true)
drain()
check(
	ns.TrackerHost.IsAttachedToQuestTracker() and hostSettings.x == nil,
	"attaching puts the column under the tracker"
)

print("tracker_host_lock_spec: " .. checks .. " checks passed")
