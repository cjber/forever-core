-- A world map that fails on any write, and frames enough to draw on it, for map canvas specs.
-- dofile("tests/strict_map.lua") returns the kit; Kit.Install(env) sets the client globals the map files read.
--
-- The map lets through only the reads UI/MapCanvas.lua lists: a field written on it, or any other method (such as
-- AddDataProvider, AcquirePin, AddOverlayFrame, RemoveAllPinsByTemplate or HookScript), raises an error naming it.
-- That is the proof that Forever's gamepad code, walking the map's own tables, never meets a value of ours.
local Kit = {}

-- Every frame made, in order, so a spec can find one by template.
Kit.frames = {}
Kit.events = {}
Kit.mapID = 1429
Kit.zoom, Kit.scale, Kit.pinScale = 0, 1, 1
Kit.visible = true
Kit.mouseFocus = false
Kit.combat = false

local Frame = {}
Frame.__index = function(_, key)
	local method = Frame[key]
	if method then
		return method
	end
	-- Engine methods a spec does not look at do nothing.
	if type(key) == "string" and key:match("^%u") then
		return function() end
	end
end

function Frame:SetScript(script, fn)
	self.scripts[script] = fn
end
function Frame:GetScript(script)
	return self.scripts[script]
end
function Frame:Run(script, ...)
	local fn = self.scripts[script]
	if fn then
		return fn(self, ...)
	end
end
function Frame:SetParent(parent)
	self.parent = parent
end
function Frame:GetParent()
	return self.parent
end
function Frame:Show()
	self.shown = true
end
function Frame:Hide()
	local was = self.shown
	self.shown = false
	if was then
		self:Run("OnHide")
	end
end
function Frame:SetShown(shown)
	if shown then
		self:Show()
	else
		self:Hide()
	end
end
function Frame:IsShown()
	return self.shown
end
-- Shown, with every parent up to the map shown.
function Frame:IsVisible()
	local frame = self
	while frame do
		if frame == Kit.map then
			return Kit.visible
		end
		if frame.shown == false then
			return false
		end
		frame = frame.parent
	end
	return true
end
function Frame:SetScale(scale)
	self.scale = scale
end
function Frame:GetScale()
	return self.scale or 1
end
function Frame:GetEffectiveScale()
	return self.scale or 1
end
function Frame:SetSize(width, height)
	self.width, self.height = width, height
end
function Frame:GetSize()
	return self.width or 0, self.height or 0
end
function Frame:GetWidth()
	return self.width or 0
end
function Frame:GetHeight()
	return self.height or 0
end
function Frame:SetPoint(...)
	self.point = { ... }
end
function Frame:ClearAllPoints()
	self.point = nil
end
function Frame:SetFrameLevel(level)
	self.level = level
end
function Frame:GetFrameLevel()
	return self.level or 1
end
function Frame:EnableMouse(enabled)
	self.mouse = enabled
end
function Frame:SetMouseClickEnabled(enabled)
	assert(not Kit.combat, "SetMouseClickEnabled is refused in combat")
	self.mouseClicks = enabled
end
function Frame:SetPassThroughButtons(...)
	assert(not Kit.combat, "SetPassThroughButtons is refused in combat")
	self.passThrough = { ... }
end
function Frame:IsMouseOver()
	return Kit.mouseOver == self
end
function Frame:GetCenter()
	return self.centerX, self.centerY
end
function Frame:RegisterEvent(event)
	self.events[event] = true
end
function Frame:UnregisterEvent(event)
	self.events[event] = nil
end
function Frame.CreateTexture()
	return Kit.Region()
end
function Frame.CreateFontString()
	return Kit.Region()
end
function Frame.GetLeft()
	return 0
end
function Frame.GetTop()
	return 0
end

-- A texture or font string: records what it was set to.
function Kit.Region()
	local region = { shown = true }
	return setmetatable(region, {
		__index = function(_, key)
			if key == "IsShown" then
				return function(self)
					return self.shown
				end
			elseif key == "Show" then
				return function(self)
					self.shown = true
				end
			elseif key == "Hide" then
				return function(self)
					self.shown = false
				end
			elseif key == "SetShown" then
				return function(self, shown)
					self.shown = shown
				end
			elseif key == "SetVertexColor" then
				return function(self, r, g, b, a)
					self.color = { r, g, b, a }
				end
			elseif key == "SetText" then
				return function(self, text)
					self.text = text
				end
			elseif key == "GetStringWidth" or key == "GetStringHeight" then
				return function()
					return 10
				end
			end
			return function() end
		end,
	})
end

-- A menu description that takes any call and returns itself, for a menu the spec does not read.
function Kit.MenuRoot()
	local root = {}
	return setmetatable(root, {
		__index = function()
			return function()
				return root
			end
		end,
	})
end

-- The pieces the addon's XML templates give a frame.
Kit.templates = {}

---@return table
function Kit.CreateFrame(frameType, name, parent, template)
	local frame = setmetatable({
		frameType = frameType,
		name = name,
		parent = parent,
		madeUnder = parent,
		template = template,
		scripts = {},
		events = {},
	}, Frame)
	frame.shown = true
	if template then
		assert(Kit.templates[template], "no stub for template " .. template)(frame)
	end
	Kit.frames[#Kit.frames + 1] = frame
	return frame
end

-- The frames made from `template`, or plain frames (template false) under `parent`.
function Kit.Made(template)
	local made = {}
	for _, frame in ipairs(Kit.frames) do
		if frame.template == template then
			made[#made + 1] = frame
		end
	end
	return made
end

-- Fires an event at every frame registered for it.
function Kit.Fire(event, ...)
	for _, frame in ipairs(Kit.frames) do
		if frame.events[event] then
			frame:Run("OnEvent", event, ...)
		end
	end
end

Kit.canvas = Kit.CreateFrame("Frame")
Kit.canvas:SetSize(1000, 700)
Kit.canvas.level = 10
Kit.container = Kit.CreateFrame("Frame")
Kit.mask = Kit.Region()

local levels = setmetatable({
	GetValidFrameLevel = function(_, levelType)
		return ({ PIN_FRAME_LEVEL_AREA_POI = 30, PIN_FRAME_LEVEL_MAP_EXPLORATION = 20 })[levelType]
	end,
}, {
	__newindex = function(_, key)
		error("wrote the map's pin frame levels manager: " .. tostring(key), 2)
	end,
})

-- The reads UI/MapCanvas.lua names, and nothing else.
local READS = {
	GetMapID = function()
		return Kit.mapID
	end,
	GetCanvas = function()
		return Kit.canvas
	end,
	GetCanvasScale = function()
		return Kit.scale
	end,
	GetCanvasZoomPercent = function()
		return Kit.zoom
	end,
	GetGlobalPinScale = function()
		return Kit.pinScale
	end,
	IsVisible = function()
		return Kit.visible
	end,
	IsShown = function()
		return Kit.visible
	end,
	GetPinFrameLevelsManager = function()
		return levels
	end,
	GetCanvasContainer = function()
		return Kit.container
	end,
	IsCanvasMouseFocus = function()
		return Kit.mouseFocus
	end,
	GetMaskTexture = function()
		return Kit.mask
	end,
	GetUseMaskTexture = function()
		return true
	end,
}

local overlays = setmetatable({}, {
	__newindex = function(_, key)
		error("wrote the map's overlayFrames: " .. tostring(key), 2)
	end,
})
Kit.map = setmetatable({}, {
	__index = function(_, key)
		if key == "overlayFrames" then
			return overlays
		end
		return READS[key] or error("called or read the map's " .. tostring(key), 2)
	end,
	__newindex = function(_, key)
		error("wrote the map's " .. tostring(key), 2)
	end,
})

-- One frame of the map's view: every OnUpdate a shown frame of ours has runs once.
function Kit.Tick()
	for _, frame in ipairs(Kit.frames) do
		if frame.scripts.OnUpdate and frame:IsVisible() then
			frame:Run("OnUpdate", 0.016)
		end
	end
end

-- Closes the map: the panel manager tells its callbacks, as the client's HideUIPanel does after hiding it.
function Kit.Close()
	Kit.visible = false
	for _, frame in ipairs(Kit.frames) do
		if frame.parent == Kit.canvas then
			frame:Run("OnHide")
		end
	end
	EventRegistry:TriggerEvent("UIParentPanelManager.HideUIPanel", Kit.map)
end

function Kit.Install(env)
	local registry = {}
	env.EventRegistry = {
		RegisterCallback = function(_, event, callback, owner)
			registry[event] = registry[event] or {}
			table.insert(registry[event], { callback = callback, owner = owner })
		end,
		TriggerEvent = function(_, event, ...)
			for _, entry in ipairs(registry[event] or {}) do
				entry.callback(entry.owner, ...)
			end
		end,
	}
	env.WorldMapFrame = Kit.map
	env.CreateFrame = Kit.CreateFrame
	env.InCombatLockdown = function()
		return Kit.combat
	end
	env.Saturate = function(value)
		return math.max(0, math.min(1, value))
	end
	env.Lerp = function(a, b, t)
		return a + (b - a) * t
	end
	env.CreateTexturePool = function()
		local pool = { active = {} }
		function pool.Acquire()
			local texture = Kit.Region()
			pool.active[#pool.active + 1] = texture
			return texture
		end
		function pool.ReleaseAll()
			pool.active = {}
		end
		return pool
	end
	env.Mixin = function(object, ...)
		for _, mixin in ipairs({ ... }) do
			for key, value in pairs(mixin) do
				object[key] = value
			end
		end
		return object
	end
	env.CreateFromMixins = function(...)
		return env.Mixin({}, ...)
	end
	env.GetCursorPosition = function()
		return Kit.cursorX or 0, Kit.cursorY or 0
	end
end

return Kit
