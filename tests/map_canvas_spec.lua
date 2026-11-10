-- The map rejects writes and calls beyond the helper's read-only contract.
local Kit = dofile("tests/strict_map.lua")
Kit.Install(_G)
_G.Enum = {}
local checks = 0
local function check(value, message)
	checks = checks + 1
	assert(value, message)
end
-- A show or hide script on a frame inside the map runs addon code inside UIParentPanelManager's own show or hide,
-- and under the gamepad interface that taints the binding stack it clears there (#493). The view hears the close
-- through the panel manager's callback instead, and clears the hovered pin itself.
local function UnderMap(frame)
	while frame do
		-- The fixture's canvas stands in for the map's own canvas, which the client parents under the map.
		if frame == Kit.map or frame == Kit.canvas then
			return true
		end
		frame = frame.parent
	end
	return false
end
local function CheckNoVisibilityScripts(when)
	for _, frame in ipairs(Kit.frames) do
		if UnderMap(frame) then
			for _, script in ipairs({ "OnShow", "OnHide" }) do
				check(
					(frame.scripts or {})[script] == nil,
					when .. ": a frame under the map with an " .. script .. " script"
				)
			end
		end
	end
end
local ns = {
	SafeCall = function(_, fn, ...)
		return true, fn(...)
	end,
	SafeCallFor = function()
		return {
			SafeCall = function(_, _, fn, ...)
				return true, fn(...)
			end,
		}
	end,
}
assert(loadfile("UI/MapCanvas.lua"))("CanvasSpec", ns)
local changes = {}
local canvas = ns.MapCanvas
local otherCanvas = ns.MapCanvasFor("OtherAddon")
canvas.Watch(Kit.map, function(_, what)
	changes[#changes + 1] = what
end)
local actions = {}
local mixin = CreateFromMixins(canvas.PinMixin, {
	takesMouse = true,
	clicks = true,
	OnAcquired = function(self, x, y)
		self:SetPosition(x, y)
		self:UseFrameLevelType("PIN_FRAME_LEVEL_AREA_POI")
		self:SetScalingLimits(1, 1, 1.2)
	end,
	OnMouseClickAction = function(_, button)
		actions[#actions + 1] = button
	end,
})
local pool = canvas.Pool(Kit.map, mixin, { marker = "route" })
Kit.Tick()
local pin = pool:Acquire(0.25, 0.5)
CheckNoVisibilityScripts("the first pin")
check(pin.point[2] == Kit.canvas and pin.point[4] == 250 and pin.point[5] == -350, "position")
check(pin.level == 30, "native frame level")
check(pin.passThrough == nil, "the pin never calls the restricted SetPassThroughButtons")
check(pin.mouseClicks == true, "a clicking pin takes mouse clicks")
local function Click(button)
	Kit.mouseOver = pin
	pin:Run("OnEnter")
	Kit.Fire("GLOBAL_MOUSE_DOWN", button)
	Kit.Fire("GLOBAL_MOUSE_UP", button)
end
Click("LeftButton")
Click("RightButton")
Click("MiddleButton")
check(#actions == 1 and actions[1] == "LeftButton", "default clicks")
check(not pcall(function()
	Kit.map.overlayFrames[1] = pin
end), "map overlay writes fail")
pool:ReleaseAll()
check(#pool:Active() == 0, "released pool is empty")
check(pool:Acquire(0.5, 0.25) == pin, "released pins are reused")
pool:ReleaseAll()
mixin.ShouldMouseButtonBePassthrough = function()
	return false
end
-- New frames take both clicks when the consumer's policy passes neither.
pool = canvas.Pool(Kit.map, mixin, { marker = "route" })
pin = pool:Acquire(0.25, 0.5)
check(pin.passThrough == nil and pin.mouseClicks == true, "right action takes both buttons")
Click("RightButton")
check(#actions == 2 and actions[2] == "RightButton", "right action fires")
local count = 0
for _, active in ipairs(pool:Active()) do
	count = count + 1
	check(active == pin, "active iterator returns pin")
end
check(count == 1, "active count")
local markers = canvas.Markers(Kit.map)
check(#markers == 1 and markers[1].kind == "route" and markers[1].x == 0.25, "addon-keyed markers")
-- Visibility is per owner: one addon hiding its markers leaves another addon's pins and markers alone.
local otherMixin = CreateFromMixins(canvas.PinMixin, {
	OnAcquired = function(self, x, y)
		self:SetPosition(x, y)
	end,
})
local otherPool = otherCanvas.Pool(Kit.map, otherMixin, { marker = "other" })
local otherPin = otherPool:Acquire(0.75, 0.5)
check(#otherCanvas.Markers(Kit.map) == 1, "the second addon draws its own marker")
canvas.SetShown(Kit.map, false)
check(#canvas.Markers(Kit.map) == 0, "the first addon's markers are hidden")
check(#otherCanvas.Markers(Kit.map) == 1, "the second addon's markers still show")
check(pin:IsShown() == false and otherPin:IsShown() == true, "each addon's pins follow its own switch")
otherCanvas.SetShown(Kit.map, false)
check(#otherCanvas.Markers(Kit.map) == 0, "the second addon can hide its own markers too")
otherCanvas.SetShown(Kit.map, true)
check(#otherCanvas.Markers(Kit.map) == 1, "and show them again")
canvas.SetShown(Kit.map, true)
check(#canvas.Markers(Kit.map) == 1, "the first addon shows its markers again")
Kit.scale, Kit.zoom = 2, 1
Kit.Tick()
check(math.abs(pin.scale - 0.6) < 1e-9 and math.abs(pin.point[4] - 250 / 0.6) < 1e-9, "zoom preserves position")
canvas.SetShown(Kit.map, false)
check(#canvas.Markers(Kit.map) == 0, "hidden markers omitted")
canvas.SetShown(Kit.map, true)
Kit.mapID = 1415
check(#canvas.Markers(Kit.map) == 0, "stale map markers omitted")
Kit.Tick()
check(changes[#changes] == "map", "map change")
Kit.canvas:SetSize(800, 600)
Kit.Tick()
check(changes[#changes] == "size", "resize notification")
check(math.abs(pin.point[4] - 200 / 0.6) < 1e-9, "resize repositions pins")
CheckNoVisibilityScripts("the watch's frames")
Kit.Close()
check(changes[#changes] == "hide", "hide notification")
print(("map_canvas_spec: %d checks passed"):format(checks))
