---@type string, ForeverTrackerNamespace
local addonName, ns = ...

-- Addon drawings on the world map, on frames of its own, with nothing written into the map.
--
-- Forever's gamepad interface runs the map's Lua from secure code: every frame MapCanvasMixin:UpdateGamepadCursor walks
-- each pin in map.pinPools and keeps the ones under its cursor in map.currentPoIPins. A data provider an addon adds
-- sits in map.dataProviders, a pin it acquires puts its template, pool and frame in map.pinPools, and an overlay frame
-- it adds goes into map.overlayFrames, so that secure walk ran through the addon's values, tainted, and the gamepad's
-- later protected calls were blocked. The canvas adds no data provider, acquires no pin, adds no overlay frame
-- and calls no map method that writes. It only reads the map:
--   map:GetMapID(), map:GetCanvas(), map:GetCanvasScale(), map:GetCanvasZoomPercent(), map:GetGlobalPinScale(),
--   map:IsVisible() and map:GetPinFrameLevelsManager():GetValidFrameLevel(type)
-- (each returns a field or works one out from fields: Blizzard_MapCanvas.lua, MapCanvas_PinFrameLevelsManager.lua),
-- plus the canvas's size and the gamepad's SoftCursor. tests/map_canvas_spec.lua runs the map files against a map that
-- fails on any write.
--
-- One view per map: a frame of ours on the canvas, which clips it and shows and hides it with the map. It is made
-- with no parent and then moved there, since the gamepad interface follows frames created inside an open window.
-- Its OnUpdate runs only while the map shows and compares a few reads each frame, telling its listeners what changed:
--   "show"  the map opened    "map"  another map is shown    "size"  the canvas was resized
--   "scale" the zoom or the map's pin scale                  "hide"  the map closed
-- The pins sit on a layer under that frame, so combat hides them all at once.
--
-- Pins are plain frames that take the mouse with OnEnter and OnLeave only (the gamepad interface reads a frame with a
-- click script as a button of the window it scans). A click is a press and release over the hovered pin, seen through
-- GLOBAL_MOUSE_DOWN and GLOBAL_MOUSE_UP on a frame of ours. By default the right button goes through to the canvas
-- (zoom out); a pin may override it. Under the gamepad interface the nearest pin shows its tooltip.

---@alias ForeverCanvasMap WorldMapFrame

---@class ForeverMapCanvas
local MapCanvas = {}
ns.MapCanvas = MapCanvas

-- How near the gamepad's map cursor comes to a pin to point at it, in UI units (the map's MIN_PIN_DISTANCE_SQUARED).
local CURSOR_REACH = 12

---@class ForeverCanvasView
---@field map ForeverCanvasMap
---@field canvas Frame
---@field host Frame
---@field layer Frame
---@field shown boolean
---@field mapID? number
---@field width number
---@field height number
---@field scale number
---@field zoom number
---@field pinScale number
---@field listeners fun(view: ForeverCanvasView, what: string)[]
---@field pools ForeverCanvasPool[]
local View = {}
View.__index = View

---@type table<ForeverCanvasMap, ForeverCanvasView>
local views = {}
---@type ForeverCanvasPin?, ForeverCanvasPin?, string?
local hovered, pressed, pressedButton
-- Whether the gamepad's map cursor, not the mouse, hovered the pin.
local hoveredByCursor = false
---@type Frame
local clicks

-- Whether the game runs its gamepad interface.
---@return boolean
function MapCanvas.Gamepad()
	local styles, api = Enum.InputDeviceInterfaceType, C_InputInterfaceStyle
	return styles ~= nil and api ~= nil and api.GetCurrentStyle ~= nil and api.GetCurrentStyle() == styles.Gamepad
end

-- The frame level the map gives a pin of this type, read from its levels manager.
---@param levelType? string
---@return number
function View:Level(levelType)
	local levels = self.map.GetPinFrameLevelsManager and self.map:GetPinFrameLevelsManager()
	local level = levelType and levels and levels:GetValidFrameLevel(levelType)
	return level or self.canvas:GetFrameLevel() + 1
end

---@param view ForeverCanvasView
---@param what string
local function Fire(view, what)
	if what ~= "hide" then
		for _, pool in ipairs(view.pools) do
			for _, pin in ipairs(pool.active) do
				pin:ApplyScale()
				pin:ApplyPosition()
			end
		end
	end
	for _, listener in ipairs(view.listeners) do
		ns.SafeCall("map canvas " .. what, listener, view, what)
	end
end

---@param pin ForeverCanvasPin?
local function SetHovered(pin)
	if hovered == pin then
		return
	end
	local previous = hovered
	hovered = pin
	if previous then
		previous:OnMouseLeave()
	end
	if pin then
		pin:OnMouseEnter()
	end
end

-- The pin nearest the gamepad's map cursor and within reach, among those that take the mouse.
---@param view ForeverCanvasView
---@return ForeverCanvasPin?
local function PinAtCursor(view)
	local cursor = SoftCursor
	if not (cursor and cursor:IsShown()) then
		return nil
	end
	local left, bottom, width, height = cursor:GetRect()
	if not left then
		return nil
	end
	local cursorScale = cursor:GetEffectiveScale()
	local cx, cy = (left + width / 2) * cursorScale, (bottom + height / 2) * cursorScale
	local reach = CURSOR_REACH * cursorScale
	local best, bestDistance = nil, reach * reach
	for _, pool in ipairs(view.pools) do
		for _, pin in ipairs(pool.active) do
			if pin.takesMouse and pin:IsVisible() then
				local x, y = pin:GetCenter()
				if x then
					local scale = pin:GetEffectiveScale()
					local dx, dy = x * scale - cx, y * scale - cy
					local distance = dx * dx + dy * dy
					if distance <= bestDistance then
						best, bestDistance = pin, distance
					end
				end
			end
		end
	end
	return best
end

---@param view ForeverCanvasView
local function Update(view)
	local map, canvas = view.map, view.canvas
	if not map:IsVisible() then
		return
	end
	local scale = map:GetCanvasScale()
	if not scale or scale <= 0 then
		scale = 1
	end
	local mapID, width, height = map:GetMapID(), canvas:GetWidth() or 0, canvas:GetHeight() or 0
	local zoom, pinScale = Saturate(map:GetCanvasZoomPercent() or 0), map:GetGlobalPinScale() or 1
	local first, changedMap = not view.shown, mapID ~= view.mapID
	local sized = width ~= view.width or height ~= view.height
	local scaled = scale ~= view.scale or zoom ~= view.zoom or pinScale ~= view.pinScale
	view.mapID, view.width, view.height, view.scale, view.zoom, view.pinScale =
		mapID, width, height, scale, zoom, pinScale
	if first then
		view.shown = true
		clicks:RegisterEvent("GLOBAL_MOUSE_DOWN")
		clicks:RegisterEvent("GLOBAL_MOUSE_UP")
		Fire(view, "show")
	elseif changedMap then
		Fire(view, "map")
	elseif sized then
		Fire(view, "size")
	elseif scaled then
		Fire(view, "scale")
	end
	-- Under the gamepad interface the map cursor hovers the pin nearest it; it never takes over one the mouse is on.
	-- A pin the mouse is really over stays its own.
	local mouseHolds = hovered and not hoveredByCursor and hovered:IsMouseOver()
	if not mouseHolds and hovered and hovered.view == view and hoveredByCursor and not MapCanvas.Gamepad() then
		SetHovered(nil)
		hoveredByCursor = false
	elseif not mouseHolds and MapCanvas.Gamepad() then
		local pin = PinAtCursor(view)
		if pin or (hovered and hovered.view == view) then
			SetHovered(pin)
			hoveredByCursor = pin ~= nil
		end
	end
end

---@param view ForeverCanvasView
local function Hide(view)
	if hovered and hovered.view == view then
		SetHovered(nil)
	end
	if pressed and pressed.view == view then
		pressed = nil
	end
	local open = false
	for _, other in pairs(views) do
		open = open or (other ~= view and other.shown)
	end
	if not open then
		clicks:UnregisterEvent("GLOBAL_MOUSE_DOWN")
		clicks:UnregisterEvent("GLOBAL_MOUSE_UP")
	end
	if view.shown then
		view.shown = false
		Fire(view, "hide")
	end
end

-- A frame made with no parent, then set under `parent`: the gamepad interface follows frames created in an open window.
---@param frameType string
---@param parent Frame
---@param template? string
---@return Frame
function MapCanvas.FrameUnder(frameType, parent, template)
	local frame = CreateFrame(frameType, nil, nil, template)
	frame:SetParent(parent)
	return frame
end

-- The view of `map`, made the first time it is asked for; `listener`, when given, hears what changes.
---@param map ForeverCanvasMap
---@param listener? fun(view: ForeverCanvasView, what: string)
---@return ForeverCanvasView
function MapCanvas.Watch(map, listener)
	local view = views[map]
	if not view then
		local canvas = map:GetCanvas()
		view = setmetatable({
			map = map,
			canvas = canvas,
			shown = false,
			width = 0,
			height = 0,
			scale = 1,
			zoom = 0,
			pinScale = 1,
			listeners = {},
			pools = {},
		}, View)
		local host = MapCanvas.FrameUnder("Frame", canvas)
		host:SetAllPoints(canvas)
		host:EnableMouse(false)
		host:SetScript("OnUpdate", function()
			Update(view)
		end)
		host:SetScript("OnHide", function()
			Hide(view)
		end)
		local layer = MapCanvas.FrameUnder("Frame", host)
		layer:SetAllPoints(host)
		layer:EnableMouse(false)
		view.host, view.layer = host, layer
		views[map] = view
	end
	if listener then
		view.listeners[#view.listeners + 1] = listener
	end
	return view
end

-- Shows or hides every pin of ours on `map`: combat hides them.
---@param map ForeverCanvasMap
---@param shown boolean
function MapCanvas.SetShown(map, shown)
	local view = views[map]
	if view then
		if not shown and hovered and hovered.view == view then
			SetHovered(nil)
		end
		view.layer:SetShown(shown)
	end
end

--[[ Pins ]]

-- The base of every pin: placed at map fractions, and a constant size on screen between startScale zoomed out and
-- endScale zoomed in, times the map's pin scale unless it ignores it, as the map's own pins (MapCanvasPinMixin).
-- A pin with no limits that ignores the pin scale grows with the terrain.
---@class ForeverCanvasPin : Frame
---@field view ForeverCanvasView
---@field mapX? number
---@field mapY? number
---@field scaleFactor? number
---@field startScale? number
---@field endScale? number
---@field ignoreGlobalPinScale? boolean
---@field levelType? string
---@field takesMouse? boolean
---@field clicks? boolean whether clicks act on this pin
---@field OnMouseClickAction? fun(self: ForeverCanvasPin, button: string)
local Pin = {}
MapCanvas.PinMixin = Pin

function Pin.OnLoad() end
---@param ... any
-- luacheck: ignore 212 -- Each pin mixin defines its own acquired arguments.
function Pin:OnAcquired(...) end
function Pin:OnReleased() end
function Pin:OnMouseEnter() end
function Pin:OnMouseLeave() end

---@param button string
---@return boolean
function Pin.ShouldMouseButtonBePassthrough(_, button)
	return button ~= "LeftButton"
end

---@return ForeverCanvasMap
function Pin:GetMap()
	return self.view.map
end

---@param x number
---@param y number
function Pin:SetPosition(x, y)
	self.mapX, self.mapY = x, y
	self:ApplyPosition()
end

---@return number?, number?
function Pin:GetPosition()
	return self.mapX, self.mapY
end

---@param factor number
---@param startScale number
---@param endScale number
function Pin:SetScalingLimits(factor, startScale, endScale)
	self.scaleFactor, self.startScale, self.endScale = factor, math.max(startScale, 0.01), math.max(endScale, 0.01)
end

---@param ignore boolean
function Pin:SetIgnoreGlobalPinScale(ignore)
	self.ignoreGlobalPinScale = ignore
end

---@param levelType string
function Pin:UseFrameLevelType(levelType)
	self.levelType = levelType
end

function Pin:ApplyScale()
	local view = self.view
	local scale
	if self.startScale and self.endScale then
		scale = Lerp(self.startScale, self.endScale, Saturate(self.scaleFactor * view.zoom)) / view.scale
	elseif not self.ignoreGlobalPinScale then
		scale = 1
	end
	if scale then
		if not self.ignoreGlobalPinScale then
			scale = scale * view.pinScale
		end
		self:SetScale(scale)
	end
end

function Pin:ApplyPosition()
	local x, y = self.mapX, self.mapY
	if not (x and y) then
		return
	end
	local view, scale = self.view, self:GetScale()
	self:ClearAllPoints()
	self:SetPoint("CENTER", view.canvas, "TOPLEFT", view.width * x / scale, -view.height * y / scale)
end

-- Clicking pins choose which buttons pass through to the canvas; non-clicking pins let every press through.
function Pin:ApplyClicks()
	if not self.takesMouse then
		return
	end
	self:SetMouseClickEnabled(self.clicks == true)
	if self.clicks then
		local through = {}
		for _, button in ipairs({ "LeftButton", "RightButton" }) do
			if self:ShouldMouseButtonBePassthrough(button) then
				through[#through + 1] = button
			end
		end
		self:SetPassThroughButtons(unpack(through))
	end
end

--[[ Pools ]]

---@class ForeverCanvasPool
---@field view ForeverCanvasView
---@field mixin table
---@field template? string
---@field marker? string
---@field active ForeverCanvasPin[]
---@field free ForeverCanvasPin[]
local Pool = {}
Pool.__index = Pool

local function OnEnter(pin)
	SetHovered(pin)
	hoveredByCursor = false
end

local function OnLeave(pin)
	if hovered == pin then
		SetHovered(nil)
	end
end

---@return ForeverCanvasPin
function Pool:Acquire(...)
	local pin = table.remove(self.free)
	if not pin then
		pin = MapCanvas.FrameUnder("Frame", self.view.layer, self.template) --[[@as ForeverCanvasPin]]
		Mixin(pin, self.mixin)
		pin.view = self.view
		pin:OnLoad()
		pin:EnableMouse(pin.takesMouse == true)
		if pin.takesMouse then
			pin:SetScript("OnEnter", OnEnter)
			pin:SetScript("OnLeave", OnLeave)
		end
	end
	self.active[#self.active + 1] = pin
	pin:Show()
	pin:OnAcquired(...)
	pin:SetFrameLevel(self.view:Level(pin.levelType))
	pin:ApplyScale()
	pin:ApplyPosition()
	pin:ApplyClicks()
	return pin
end

---@return ForeverCanvasPin[]
-- The live list: finish iterating before acquiring or releasing pins.
function Pool:Active()
	return self.active
end

function Pool:ReleaseAll()
	for index = #self.active, 1, -1 do
		local pin = self.active[index]
		self.active[index] = nil
		if hovered == pin then
			SetHovered(nil)
		end
		if pressed == pin then
			pressed = nil
		end
		pin:Hide()
		pin:ClearAllPoints()
		pin:OnReleased()
		pin.mapX, pin.mapY = nil, nil
		self.free[#self.free + 1] = pin
	end
end

-- A pool of pins on `map`'s view: frames from `template` wearing `mixin`, which builds on MapCanvas.PinMixin. A pool
-- with a `marker` kind lists its shown pins for the other Forever addons (ForeverMapMarkers, below).
---@param map ForeverCanvasMap
---@param mixin table
---@param options? {template?: string, marker?: string}
---@return ForeverCanvasPool
function MapCanvas.Pool(map, mixin, options)
	local view = MapCanvas.Watch(map)
	options = options or {}
	local pool = setmetatable({
		view = view,
		mixin = mixin,
		template = options.template,
		marker = options.marker,
		active = {},
		free = {},
	}, Pool)
	view.pools[#view.pools + 1] = pool
	return pool
end

--[[ Clicks ]]

---@param pin ForeverCanvasPin
---@param button string
local function Click(pin, button)
	if pin.clicks and not pin:ShouldMouseButtonBePassthrough(button) and pin.OnMouseClickAction then
		pin:OnMouseClickAction(button)
	end
end

clicks = CreateFrame("Frame")
clicks:SetScript("OnEvent", function(_, event, button)
	if event == "GLOBAL_MOUSE_DOWN" then
		pressed, pressedButton = nil, button
		if hovered and hovered:IsVisible() and hovered:IsMouseOver() then
			pressed = hovered
		end
		return
	end
	local pin = pressed
	pressed = nil
	if pin and pin == hovered and button == pressedButton and pin:IsVisible() and pin:IsMouseOver() then
		ns.SafeCall("map pin click", Click, pin, button)
	end
end)

--[[ ForeverMapMarkers ]]

-- The Forever addons' markers on the world map, for each other (Tweaks Forever keeps its dungeon entrances clear of
-- them): with every addon drawing on frames of its own, none can find another's through the map's pin pools. The
-- first addon to load makes the global table, and each sets one function under its folder name:
--   ForeverMapMarkers[addonName] = function(map) -> { { x = number, y = number, kind = string }... }
-- x and y are the shown markers' fractions on map:GetMapID(), in a fresh table; it never errors.
-- Published as a copy with our entry added, never a field written into the table another addon made; readers look
-- the global up each time, since a later addon replaces it.
local function OurMarkers(map)
	local markers, view = {}, views[map]
	-- Shown, not hidden for combat, and drawn for the map it shows now (a map just turned redraws on its next frame).
	if not (view and view.shown and view.layer:IsShown() and view.mapID == map:GetMapID()) then
		return markers
	end
	for _, pool in ipairs(view.pools) do
		if pool.marker then
			for _, pin in ipairs(pool.active) do
				local x, y = pin:GetPosition()
				if x and pin:IsShown() then
					markers[#markers + 1] = { x = x, y = y, kind = pool.marker }
				end
			end
		end
	end
	return markers
end

local published = {}
for addon, markers in pairs(ForeverMapMarkers or {}) do
	published[addon] = markers
end
published[addonName] = OurMarkers
ForeverMapMarkers = published
