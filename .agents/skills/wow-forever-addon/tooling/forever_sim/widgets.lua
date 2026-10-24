-- The widget layer: frames, regions, font strings, textures, animations and fonts, with anchoring and layout,
-- visibility, scripts and events. Every method the client documents exists (Blizzard_APIDocumentationGenerated's
-- ScriptObject systems); those not written here keep what a setter stores for its getter, or return the documented
-- type's zero value. Each method carries the client's secret and protection rules from the same documentation:
-- secret arguments add aspects, secret aspects and secret anchoring make getters return secrets, and protected
-- methods on protected frames are blocked for tainted code in combat.
local Secret = require("veil")

local M = {}

-- Widget type -> { parent type, documented API systems }.
local TYPES = {
	Object = { nil, { "SimpleObjectAPI" } },
	FrameScriptObject = { "Object", { "SimpleFrameScriptObjectAPI" } },
	ScriptRegion = { "FrameScriptObject", { "SimpleScriptRegionAPI", "SimpleScriptRegionResizingAPI" } },
	Region = { "ScriptRegion", { "SimpleRegionAPI" } },
	TextureBase = { "Region", { "SimpleTextureBaseAPI" } },
	Texture = { "TextureBase", { "SimpleTextureAPI" } },
	MaskTexture = { "TextureBase", { "SimpleMaskTextureAPI" } },
	Line = { "TextureBase", { "SimpleLineAPI" } },
	FontString = { "Region", { "SimpleFontStringAPI" } },
	Frame = { "Region", { "SimpleFrameAPI" } },
	Button = { "Frame", { "SimpleButtonAPI" } },
	CheckButton = { "Button", { "SimpleCheckboxAPI" } },
	EditBox = { "Frame", { "SimpleEditBoxAPI" } },
	ScrollFrame = { "Frame", { "SimpleScrollFrameAPI" } },
	Slider = { "Frame", { "SimpleSliderAPI" } },
	StatusBar = { "Frame", { "SimpleStatusBarAPI" } },
	ColorSelect = { "Frame", { "SimpleColorSelectAPI" } },
	MessageFrame = { "Frame", { "SimpleMessageFrameAPI" } },
	ScrollingMessageFrame = { "Frame", { "SimpleMessageFrameAPI" } },
	SimpleHTML = { "Frame", { "SimpleHTMLAPI" } },
	Browser = { "Frame", { "SimpleBrowserAPI" } },
	MovieFrame = { "Frame", { "SimpleMovieAPI" } },
	Model = { "Frame", { "SimpleModelAPI" } },
	PlayerModel = { "Model", { "FrameAPICharacterModelBase" } },
	DressUpModel = { "PlayerModel", { "FrameAPIDressUpModel" } },
	CinematicModel = { "PlayerModel", { "FrameAPICinematicModel" } },
	TabardModel = { "PlayerModel", { "FrameAPITabardModelBase", "FrameAPITabardModel" } },
	ModelScene = { "Frame", { "FrameAPIModelSceneFrame" } },
	ModelSceneActor = { "Object", { "FrameAPIModelSceneFrameActorBase", "FrameAPIModelSceneFrameActor" } },
	Cooldown = { "Frame", { "FrameAPICooldown" } },
	GameTooltip = { "Frame", { "FrameAPITooltip" } },
	Minimap = { "Frame", { "MinimapFrameAPI" } },
	OffScreenFrame = { "Frame", { "SimpleOffScreenFrameAPI" } },
	Checkout = { "Frame", { "FrameAPISimpleCheckout" } },
	FogOfWarFrame = { "Frame", { "FrameAPIFogOfWarFrame" } },
	UnitPositionFrame = { "Frame", { "FrameAPIUnitPositionFrame" } },
	QuestPOIFrame = { "Frame", { "FrameAPIBlob", "FrameAPIQuestPOI" } },
	ScenarioPOIFrame = { "Frame", { "FrameAPIBlob", "FrameAPIScenarioPOI" } },
	ArchaeologyDigSiteFrame = { "Frame", { "FrameAPIBlob", "FrameAPIArchaeologyDigSiteFrame" } },
	MapScene = { "Frame", { "SimpleMapSceneAPI" } },
	AnimationGroup = { "FrameScriptObject", { "SimpleAnimatableObjectAPI", "SimpleAnimGroupAPI" } },
	Animation = { "FrameScriptObject", { "SimpleAnimAPI" } },
	Alpha = { "Animation", { "SimpleAnimAlphaAPI" } },
	Scale = { "Animation", { "SimpleAnimScaleAPI" } },
	LineScale = { "Scale", { "SimpleAnimScaleLineAPI" } },
	Translation = { "Animation", { "SimpleAnimTranslationAPI" } },
	LineTranslation = { "Translation", { "SimpleAnimTranslationLineAPI" } },
	Rotation = { "Animation", { "SimpleAnimRotationAPI" } },
	Path = { "Animation", { "SimpleAnimPathAPI" } },
	FlipBook = { "Animation", { "SimpleAnimFlipBookAPI" } },
	TextureCoordTranslation = { "Animation", { "SimpleAnimTextureCoordTranslationAPI" } },
	VertexColor = { "Animation", { "SimpleAnimVertexColorAPI" } },
	RadialProgress = { "Animation", { "SimpleAnimRadialProgressAPI" } },
	ControlPoint = { "FrameScriptObject", { "SimpleControlPointAPI" } },
	Font = { "FrameScriptObject", { "SimpleFontAPI" } },
}
M.TYPES = TYPES

-- XML tags and CreateFrame types that are spelled differently from their widget type.
local ALIASES = {
	Checkbox = "CheckButton",
	ItemButton = "Button",
	DropdownButton = "Button",
	EventButton = "Button",
	EventFrame = "Frame",
	EventEditBox = "EditBox",
	EventScrollFrame = "ScrollFrame",
	ContainedAlertFrame = "Frame",
	ScopedModifier = "Frame",
	WorldFrame = "Frame",
	ModelFFX = "Model",
	CharacterModelBase = "PlayerModel",
	CinematicModel = "CinematicModel",
	UnitPositionFrame = "UnitPositionFrame",
	Blob = "Frame",
	POIFrame = "Frame",
	TabardModel = "TabardModel",
	ArchaeologyDigsiteFrame = "ArchaeologyDigSiteFrame",
}
M.ALIASES = ALIASES

local POINTS = {
	TOPLEFT = { "LEFT", "TOP" },
	TOP = { "CENTER", "TOP" },
	TOPRIGHT = { "RIGHT", "TOP" },
	LEFT = { "LEFT", "CENTER" },
	CENTER = { "CENTER", "CENTER" },
	RIGHT = { "RIGHT", "CENTER" },
	BOTTOMLEFT = { "LEFT", "BOTTOM" },
	BOTTOM = { "CENTER", "BOTTOM" },
	BOTTOMRIGHT = { "RIGHT", "BOTTOM" },
}
M.POINTS = POINTS

local STRATA = {
	"WORLD",
	"BACKGROUND",
	"LOW",
	"MEDIUM",
	"HIGH",
	"DIALOG",
	"FULLSCREEN",
	"FULLSCREEN_DIALOG",
	"TOOLTIP",
	"BLIZZARD",
}
local STRATA_INDEX = {}
for i, s in ipairs(STRATA) do
	STRATA_INDEX[s] = i
end
M.STRATA_INDEX = STRATA_INDEX

local function isA(typeName, ancestor)
	while typeName do
		if typeName == ancestor then
			return true
		end
		typeName = TYPES[typeName] and TYPES[typeName][1]
	end
	return false
end
M.isA = isA

local function zeroOf(ret)
	if ret.Nilable then
		return nil
	end
	local t = ret.Type
	if t == "bool" then
		return false
	elseif t == "number" or t == "uiUnit" or t == "luaIndex" or t == "size" or t == "normalizedValue" then
		return 0
	elseif t == "string" or t == "cstring" or t == "textureAtlas" or t == "FramePoint" or t == "DrawLayer" then
		return t == "FramePoint" and "CENTER" or (t == "DrawLayer" and "ARTWORK" or "")
	elseif t == "FrameStrata" then
		return "MEDIUM"
	end
	return nil
end

function M.build(sim)
	local G, Taint = sim.G, sim.taint
	local S = setmetatable({}, { __mode = "k" }) -- object -> state
	local W = { state = S, all = {}, byType = {}, methods = {}, metas = {} }
	sim.widgets = W
	local layoutGen = 0
	local function dirty()
		layoutGen = layoutGen + 1
	end
	W.dirty = dirty

	local function st(obj)
		local s = S[obj]
		if not s then
			error("not a widget: " .. tostring(obj), 3)
		end
		return s
	end
	W.st = st

	---------------------------------------------------------------------------
	-- Scripts
	---------------------------------------------------------------------------
	-- Runs obj's script `name` as the client does when Lua code triggers it (Show, Click, SetValue...): the
	-- handler inherits the caller's taint, plus the taint of whoever set it; each HookScript hook runs isolated.
	local function fire(obj, name, ...)
		local s = S[obj]
		if not s or not s.scripts then
			return
		end
		local intrinsic = s.intrinsic and s.intrinsic[name]
		if intrinsic and intrinsic.pre then
			intrinsic.pre(obj, ...)
		end
		local handler = s.scripts[name]
		if handler then
			local by = s.scriptTaint[name]
			if by and not Taint.current then
				Taint.set(by)
			end
			handler(obj, ...)
		end
		if intrinsic and intrinsic.post then
			intrinsic.post(obj, ...)
		end
		local hooks = s.hooks and s.hooks[name]
		if hooks then
			for _, hook in ipairs(hooks) do
				Taint.securecall(hook, obj, ...)
			end
		end
	end
	W.fire = fire

	-- Runs a script from the client's side (input, events, OnUpdate): a fresh dispatch, secure unless the handler
	-- was set by an addon.
	function W.dispatch(obj, name, ...)
		local s = S[obj]
		if not s or not s.scripts then
			return
		end
		if not s.scripts[name] and not (s.hooks and s.hooks[name]) and not (s.intrinsic and s.intrinsic[name]) then
			return
		end
		return Taint.dispatch(s.scriptTaint[name], fire, obj, name, ...)
	end

	---------------------------------------------------------------------------
	-- Layout
	---------------------------------------------------------------------------
	local root -- UIParent-sized screen rect owner

	local function effectiveScale(obj)
		local s = S[obj]
		local scale = 1
		local guard = 0
		while s do
			scale = scale * (Secret.unwrap(s.scale) or 1)
			if s.ignoreParentScale then
				break
			end
			s = s.parent and S[s.parent]
			guard = guard + 1
			if guard > 200 then
				break
			end
		end
		return scale
	end
	W.effectiveScale = effectiveScale

	local function plain(text)
		text = tostring(Secret.unwrap(text) or "")
		text = text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|T.-|t", "WW"):gsub("|A.-|a", "WW")
		text = text:gsub("|n", "\n")
		return text
	end

	-- The measured size of a font string's text, in its own units.
	local function textSize(s)
		local height = s.fontHeight or 12
		local text = plain(s.text)
		if text == "" then
			return 0, 0
		end
		local widest, lines = 0, 0
		for line in (text .. "\n"):gmatch("(.-)\n") do
			lines = lines + 1
			local w = #line * height * 0.5
			if w > widest then
				widest = w
			end
		end
		local maxWidth = Secret.unwrap(s.width)
		if maxWidth and maxWidth > 0 and widest > maxWidth and s.wordWrap ~= false then
			lines = lines + math.ceil(widest / maxWidth) - 1
			widest = maxWidth
		end
		if s.maxLines and s.maxLines > 0 then
			lines = math.min(lines, s.maxLines)
		end
		return widest, lines * height + (lines - 1) * (s.spacing or 0)
	end
	W.textSize = textSize

	local rectCache = setmetatable({}, { __mode = "k" })

	-- Screen rect { left, bottom, width, height } in screen units, or nil when the region is not placed.
	-- Anchor chains can be thousands long (pools of rows), so dependencies are resolved with an explicit stack,
	-- deepest first; a region in an anchoring loop has no rect.
	local function cachedRect(obj)
		local c = rectCache[obj]
		if c and c.gen == layoutGen then
			return true, c.rect
		end
		return false
	end

	local function targetsOf(obj)
		local s = S[obj]
		local out = {}
		for i, p in ipairs(s.points) do
			local target = p.relativeTo
			if target == nil then
				target = s.parent or root
			end
			out[i] = target
		end
		return out
	end

	local function computeOne(obj)
		local s = S[obj]
		if obj == root then
			return { 0, 0, sim.screenWidth, sim.screenHeight }
		end
		local es = effectiveScale(obj)
		local L, R, CX, T, B, CY
		for i, p in ipairs(s.points) do
			local target = p.relativeTo
			if target == nil then
				target = s.parent or root
			end
			local _, tr = cachedRect(target)
			if tr then
				local hx, vy = POINTS[p.relativePoint][1], POINTS[p.relativePoint][2]
				local tx = hx == "LEFT" and tr[1] or (hx == "RIGHT" and tr[1] + tr[3] or tr[1] + tr[3] / 2)
				local ty = vy == "BOTTOM" and tr[2] or (vy == "TOP" and tr[2] + tr[4] or tr[2] + tr[4] / 2)
				local x = tx + (Secret.unwrap(p.x) or 0) * es
				local y = ty + (Secret.unwrap(p.y) or 0) * es
				local ph, pv = POINTS[p.point][1], POINTS[p.point][2]
				if ph == "LEFT" then
					L = x
				elseif ph == "RIGHT" then
					R = x
				else
					CX = x
				end
				if pv == "TOP" then
					T = y
				elseif pv == "BOTTOM" then
					B = y
				else
					CY = y
				end
			end
			local _ = i
		end
		local w, h = Secret.unwrap(s.width), Secret.unwrap(s.height)
		if s.kind == "FontString" and (not w or w == 0 or not h or h == 0) then
			local tw, th = textSize(s)
			if not w or w == 0 then
				w = tw
			end
			if not h or h == 0 then
				h = th
			end
		end
		w, h = (w or 0) * es, (h or 0) * es
		local left, width, bottom, height
		if L and R then
			left, width = L, R - L
		elseif L and CX then
			left, width = L, (CX - L) * 2
		elseif R and CX then
			left, width = CX - (R - CX), (R - CX) * 2
		elseif L then
			left, width = L, w
		elseif R then
			left, width = R - w, w
		elseif CX then
			left, width = CX - w / 2, w
		end
		if B and T then
			bottom, height = B, T - B
		elseif B and CY then
			bottom, height = B, (CY - B) * 2
		elseif T and CY then
			bottom, height = CY - (T - CY), (T - CY) * 2
		elseif B then
			bottom, height = B, h
		elseif T then
			bottom, height = T - h, h
		elseif CY then
			bottom, height = CY - h / 2, h
		end
		if left and bottom then
			return { left, bottom, width, height }
		end
		return nil
	end

	local function rect(obj)
		local ok, cached = cachedRect(obj)
		if ok then
			return cached
		end
		if not S[obj] then
			return nil
		end
		local stack, onStack = { obj }, { [obj] = true }
		while #stack > 0 do
			local top = stack[#stack]
			local pending
			if top ~= root then
				for _, target in ipairs(targetsOf(top)) do
					if S[target] and not cachedRect(target) and not onStack[target] then
						pending = target
						break
					end
				end
			end
			if pending then
				stack[#stack + 1] = pending
				onStack[pending] = true
			else
				rectCache[top] = { gen = layoutGen, rect = computeOne(top) }
				stack[#stack] = nil
				onStack[top] = nil
			end
		end
		local _, r = cachedRect(obj)
		return r
	end
	W.rect = rect

	-- True when the region's placement depends on a region with a secret aspect (the client's secret anchoring).
	local function anchoringSecret(obj, depth)
		local s = S[obj]
		if not s or (depth or 0) > 50 then
			return false
		end
		if s.secretSize then
			return true
		end
		for _, p in ipairs(s.points) do
			local target = p.relativeTo or s.parent
			if target and target ~= root then
				local ts = S[target]
				if ts and (next(ts.aspects) ~= nil or anchoringSecret(target, (depth or 0) + 1)) then
					return true
				end
			end
		end
		return false
	end
	W.anchoringSecret = anchoringSecret

	-- Would anchoring obj to target create a loop?
	local function dependsOn(target, obj, depth)
		if target == obj then
			return true
		end
		local s = S[target]
		if not s or (depth or 0) > 100 then
			return false
		end
		for _, p in ipairs(s.points) do
			local t = p.relativeTo or s.parent
			if t and dependsOn(t, obj, (depth or 0) + 1) then
				return true
			end
		end
		return false
	end

	---------------------------------------------------------------------------
	-- Visibility
	---------------------------------------------------------------------------
	local function isVisible(obj)
		local s = S[obj]
		local guard = 0
		while s do
			if not s.shown then
				return false
			end
			if not s.parent then
				return obj == root or s.kind ~= nil
			end
			s = S[s.parent]
			guard = guard + 1
			if guard > 200 then
				return false
			end
		end
		return false
	end
	W.isVisible = isVisible

	local function visibilityChanged(obj, visible)
		local s = S[obj]
		if not s then
			return
		end
		if s.kind == "GameTooltip" and not visible then
			s.owner = nil
		end
		fire(obj, visible and "OnShow" or "OnHide")
		for _, child in ipairs(s.children or {}) do
			local cs = S[child]
			if cs and cs.shown then
				visibilityChanged(child, visible)
			end
		end
	end

	local function setShown(obj, shown)
		local s = st(obj)
		shown = not not shown
		if s.shown == shown then
			return
		end
		local before = isVisible(obj)
		s.shown = shown
		dirty()
		local after = isVisible(obj)
		if before ~= after then
			visibilityChanged(obj, after)
		end
	end

	---------------------------------------------------------------------------
	-- Objects
	---------------------------------------------------------------------------
	local function addChild(parent, obj)
		local ps = S[parent]
		if not ps then
			return
		end
		local s = S[obj]
		if not s.isRegion and not s.isFrame then
			return -- animation groups, animations and actors are not children
		end
		local list = s.isRegion and "regions" or "children"
		ps[list] = ps[list] or {}
		table.insert(ps[list], obj)
	end

	local function removeChild(parent, obj)
		local ps = S[parent]
		if not ps then
			return
		end
		for _, list in ipairs({ "children", "regions" }) do
			local l = ps[list]
			if l then
				for i = #l, 1, -1 do
					if l[i] == obj then
						table.remove(l, i)
					end
				end
			end
		end
	end

	local function resolveName(name, parent)
		if type(name) ~= "string" or name == "" then
			return nil
		end
		if name:find("$parent", 1, true) or name:find("$Parent", 1, true) then
			local p = parent
			local pname
			while p do
				pname = S[p] and S[p].name
				if pname then
					break
				end
				p = S[p] and S[p].parent
			end
			name = name:gsub("%$[pP]arent", ((pname or ""):gsub("%%", "%%%%")))
		end
		return name
	end
	W.resolveName = resolveName

	local objectCount = 0
	function W.new(kind, name, parent, extra)
		kind = ALIASES[kind] or kind
		if not TYPES[kind] then
			kind = "Frame"
		end
		local meta = W.metas[kind]
		local obj = setmetatable({}, meta)
		objectCount = objectCount + 1
		local s = {
			kind = kind,
			id = objectCount,
			points = {},
			aspects = {},
			shown = true,
			scale = 1,
			alpha = 1,
			props = {},
			isRegion = isA(kind, "Region") and not isA(kind, "Frame"),
			isFrame = isA(kind, "Frame"),
		}
		S[obj] = s
		obj[0] = newproxy(false)
		name = resolveName(name, parent)
		if name then
			s.name = name
			-- The client writes the global for the frame; it carries the creating code's taint.
			sim.env[name] = obj
		end
		if s.isFrame or kind == "AnimationGroup" or isA(kind, "Animation") then
			s.scripts, s.scriptTaint, s.hooks = {}, {}, {}
		end
		if s.isFrame then
			s.events = {}
			s.attributes = {}
			s.strata = "MEDIUM"
			s.level = 0
		end
		if extra then
			for k, v in pairs(extra) do
				s[k] = v
			end
		end
		if parent and S[parent] then
			s.parent = parent
			addChild(parent, obj)
			if s.isFrame and S[parent].isFrame then
				s.strata = S[parent].strata
				s.level = (S[parent].level or 0) + 1
			end
		end
		W.all[#W.all + 1] = obj
		W.byType[kind] = W.byType[kind] or {}
		table.insert(W.byType[kind], obj)
		dirty()
		return obj
	end

	function W.setRoot(obj)
		root = obj
		dirty()
	end
	function W.root()
		return root
	end

	---------------------------------------------------------------------------
	-- Hand-written methods, by type. `self` is the object.
	---------------------------------------------------------------------------
	local impl = {}
	W.impl = impl
	for t in pairs(TYPES) do
		impl[t] = {}
	end

	-- Object / FrameScriptObject
	impl.Object.GetName = function(self)
		return st(self).name
	end
	impl.Object.GetDebugName = function(self)
		local s = st(self)
		if s.name then
			return s.name
		end
		local parent = s.parent
		if parent then
			for k, v in pairs(parent) do
				if v == self then
					return parent:GetDebugName() .. "." .. tostring(k)
				end
			end
			return parent:GetDebugName() .. ".?"
		end
		return tostring(self)
	end
	impl.Object.GetParent = function(self)
		return st(self).parent
	end
	impl.Object.GetParentKey = function(self)
		return st(self).parentKey
	end
	impl.Object.SetParentKey = function(self, key)
		st(self).parentKey = key
	end
	impl.FrameScriptObject.GetObjectType = function(self)
		return st(self).kind
	end
	impl.FrameScriptObject.IsObjectType = function(self, t)
		return isA(st(self).kind, ALIASES[t] or t)
	end
	impl.FrameScriptObject.IsForbidden = function(self)
		return st(self).forbidden == true
	end
	impl.FrameScriptObject.SetForbidden = function(self)
		st(self).forbidden = true
	end

	-- ScriptRegion: scripts, visibility, mouse.
	impl.ScriptRegion.SetScript = function(self, name, handler)
		local s = st(self)
		if not s.scripts then
			s.scripts, s.scriptTaint, s.hooks = {}, {}, {}
		end
		s.scripts[name] = handler
		s.scriptTaint[name] = Taint.current
		s.hooks[name] = nil
	end
	impl.ScriptRegion.GetScript = function(self, name)
		local s = st(self)
		return s.scripts and s.scripts[name]
	end
	impl.ScriptRegion.HasScript = function()
		return true
	end
	impl.ScriptRegion.HookScript = function(self, name, hook)
		local s = st(self)
		if not s.scripts then
			s.scripts, s.scriptTaint, s.hooks = {}, {}, {}
		end
		if not s.scripts[name] then
			-- Hooking an empty script sets it, as the client does.
			s.scripts[name] = hook
			s.scriptTaint[name] = Taint.current
			return true
		end
		s.hooks[name] = s.hooks[name] or {}
		table.insert(s.hooks[name], hook)
		return true
	end
	impl.ScriptRegion.ClearScripts = function(self)
		local s = st(self)
		s.scripts, s.scriptTaint, s.hooks = {}, {}, {}
	end
	impl.ScriptRegion.Show = function(self)
		setShown(self, true)
	end
	impl.ScriptRegion.Hide = function(self)
		setShown(self, false)
	end
	impl.ScriptRegion.SetShown = function(self, shown)
		setShown(self, shown)
	end
	impl.ScriptRegion.IsShown = function(self)
		return st(self).shown
	end
	impl.ScriptRegion.IsVisible = function(self)
		return isVisible(self)
	end
	impl.ScriptRegion.GetParent = impl.Object.GetParent
	impl.ScriptRegion.EnableMouse = function(self, on)
		local s = st(self)
		s.mouseClick, s.mouseMotion = not not on, not not on
	end
	impl.ScriptRegion.IsMouseEnabled = function(self)
		local s = st(self)
		return s.mouseClick == true or s.mouseMotion == true
	end
	impl.ScriptRegion.SetMouseClickEnabled = function(self, on)
		st(self).mouseClick = not not on
	end
	impl.ScriptRegion.IsMouseClickEnabled = function(self)
		return st(self).mouseClick == true
	end
	impl.ScriptRegion.SetMouseMotionEnabled = function(self, on)
		st(self).mouseMotion = not not on
	end
	impl.ScriptRegion.IsMouseMotionEnabled = function(self)
		return st(self).mouseMotion == true
	end
	impl.ScriptRegion.IsMouseOver = function(self, top, bottom, left, right)
		local r = rect(self)
		local mx, my = sim.mouseX, sim.mouseY
		if not r or not mx then
			return false
		end
		return mx >= r[1] - (left or 0)
			and mx <= r[1] + r[3] + (right or 0)
			and my >= r[2] - (bottom or 0)
			and my <= r[2] + r[4] + (top or 0)
	end
	impl.ScriptRegion.IsMouseMotionFocus = function(self)
		return sim.mouseFocus == self
	end
	impl.ScriptRegion.IsAnchoringSecret = function(self)
		return anchoringSecret(self)
	end
	impl.ScriptRegion.HasSecretAspect = function(self, aspect)
		return st(self).aspects[aspect] == true
	end
	impl.ScriptRegion.HasAnySecretAspect = function(self)
		return next(st(self).aspects) ~= nil
	end
	impl.ScriptRegion.SetToDefaults = function(self)
		local s = st(self)
		s.aspects = {}
		s.secretSize = nil
		s.text = nil
		dirty()
	end
	impl.ScriptRegion.IsProtected = function(self)
		local s = st(self)
		return s.protected == true, s.protected == true
	end
	impl.ScriptRegion.CanChangeProtectedState = function()
		return not Taint.current and not sim.inCombat
	end
	impl.ScriptRegion.GetSourceLocation = function(self)
		return st(self).source
	end

	-- Geometry.
	local function getRect(self)
		local r = rect(self)
		if not r then
			return nil
		end
		local es = effectiveScale(self)
		return r[1] / es, r[2] / es, r[3] / es, r[4] / es
	end
	impl.ScriptRegion.GetLeft = function(self)
		local l = getRect(self)
		return l
	end
	impl.ScriptRegion.GetBottom = function(self)
		local _, b = getRect(self)
		return b
	end
	impl.ScriptRegion.GetRight = function(self)
		local l, _, w = getRect(self)
		return l and l + w
	end
	impl.ScriptRegion.GetTop = function(self)
		local _, b, _, h = getRect(self)
		return b and b + h
	end
	impl.ScriptRegion.GetCenter = function(self)
		local l, b, w, h = getRect(self)
		if not l then
			return nil
		end
		return l + w / 2, b + h / 2
	end
	impl.ScriptRegion.GetRect = function(self)
		return getRect(self)
	end
	impl.ScriptRegion.GetScaledRect = function(self)
		local r = rect(self)
		if r then
			return r[1], r[2], r[3], r[4]
		end
	end
	local function getWidth(self)
		local s = st(self)
		local r = #s.points > 1 and rect(self)
		if r then
			return r[3] / effectiveScale(self)
		end
		if s.kind == "FontString" and (Secret.unwrap(s.width) or 0) <= 0 then
			return (textSize(s))
		end
		return Secret.unwrap(s.width) or 0
	end
	local function getHeight(self)
		local s = st(self)
		local r = #s.points > 1 and rect(self)
		if r then
			return r[4] / effectiveScale(self)
		end
		if s.kind == "FontString" and (Secret.unwrap(s.height) or 0) <= 0 then
			local _, h = textSize(s)
			return h
		end
		return Secret.unwrap(s.height) or 0
	end
	impl.ScriptRegion.GetWidth = function(self)
		return getWidth(self)
	end
	impl.ScriptRegion.GetHeight = function(self)
		return getHeight(self)
	end
	impl.ScriptRegion.GetSize = function(self)
		return getWidth(self), getHeight(self)
	end
	impl.ScriptRegion.IsRectValid = function(self)
		return rect(self) ~= nil
	end
	impl.ScriptRegion.Intersects = function(self, other)
		local a, b = rect(self), rect(other)
		if not a or not b then
			return false
		end
		return a[1] < b[1] + b[3] and b[1] < a[1] + a[3] and a[2] < b[2] + b[4] and b[2] < a[2] + a[4]
	end
	impl.ScriptRegion.IsDragging = function()
		return false
	end
	impl.ScriptRegion.IsCollapsed = function()
		return false
	end

	-- Resizing.
	local function checkTarget(self, target)
		if target == nil then
			return nil
		end
		if type(target) == "string" then
			local name = resolveName(target, st(self).parent)
			target = G[name]
			if target == nil then
				return false
			end
		end
		if not S[target] then
			error("SetPoint(): bad relative frame", 4)
		end
		if dependsOn(target, self) then
			error("Action[SetPoint] failed because[Cannot anchor to a region dependent on it]", 4)
		end
		return target
	end

	local function setPoint(self, point, a, b, c, d)
		local s = st(self)
		point = type(point) == "string" and point:upper() or point
		if not POINTS[point] then
			error(string.format("SetPoint(): Invalid region point '%s'", tostring(point)), 3)
		end
		local relativeTo, relativePoint, x, y
		if type(a) == "number" or (a == nil and b == nil) or Secret.is(a) then
			relativeTo, relativePoint, x, y = nil, point, a, b
		else
			relativeTo, relativePoint, x, y = a, b, c, d
			if type(relativePoint) == "number" or Secret.is(relativePoint) then
				relativePoint, x, y = point, relativePoint, x
			end
		end
		relativePoint = type(relativePoint) == "string" and relativePoint:upper() or point
		if not POINTS[relativePoint] then
			relativePoint = point
		end
		local target = checkTarget(self, relativeTo)
		if target == false then
			error(string.format("SetPoint(): Couldn't find region named '%s'", tostring(relativeTo)), 3)
		end
		for i = #s.points, 1, -1 do
			if s.points[i].point == point then
				table.remove(s.points, i)
			end
		end
		table.insert(s.points, {
			point = point,
			relativeTo = target,
			explicitTarget = relativeTo ~= nil,
			relativePoint = relativePoint,
			x = x or 0,
			y = y or 0,
		})
		dirty()
	end
	W.setPoint = setPoint
	impl.ScriptRegion.SetPoint = setPoint
	impl.ScriptRegion.ClearAllPoints = function(self)
		st(self).points = {}
		dirty()
	end
	impl.ScriptRegion.ClearPoint = function(self, point)
		local s = st(self)
		for i = #s.points, 1, -1 do
			if s.points[i].point == point then
				table.remove(s.points, i)
			end
		end
		dirty()
	end
	impl.ScriptRegion.SetAllPoints = function(self, target, _)
		local s = st(self)
		s.points = {}
		target = target or s.parent
		if type(target) == "boolean" then
			target = s.parent
		end
		setPoint(self, "TOPLEFT", target, "TOPLEFT", 0, 0)
		setPoint(self, "BOTTOMRIGHT", target, "BOTTOMRIGHT", 0, 0)
	end
	impl.ScriptRegion.GetNumPoints = function(self)
		return #st(self).points
	end
	impl.ScriptRegion.GetPoint = function(self, index)
		local p = st(self).points[index or 1]
		if p then
			return p.point, p.explicitTarget and p.relativeTo or p.relativeTo, p.relativePoint, p.x, p.y
		end
	end
	impl.ScriptRegion.GetPointByName = function(self, name)
		for _, p in ipairs(st(self).points) do
			if p.point == name then
				return p.point, p.relativeTo, p.relativePoint, p.x, p.y
			end
		end
	end
	impl.ScriptRegion.AdjustPointsOffset = function(self, dx, dy)
		for _, p in ipairs(st(self).points) do
			p.x, p.y = p.x + dx, p.y + dy
		end
		dirty()
	end
	impl.ScriptRegion.ClearPointsOffset = function(self)
		for _, p in ipairs(st(self).points) do
			p.x, p.y = 0, 0
		end
		dirty()
	end
	local function setDim(self, key, value)
		local s = st(self)
		if Secret.is(value) then
			s.secretSize = true
		end
		s[key] = value
		dirty()
		if s.isFrame then
			fire(self, "OnSizeChanged", getWidth(self), getHeight(self))
		end
	end
	impl.ScriptRegion.SetWidth = function(self, w)
		setDim(self, "width", w)
	end
	impl.ScriptRegion.SetHeight = function(self, h)
		setDim(self, "height", h)
	end
	impl.ScriptRegion.SetSize = function(self, w, h)
		local s = st(self)
		if Secret.is(w) or Secret.is(h) then
			s.secretSize = true
		end
		s.width, s.height = w, h
		dirty()
		if s.isFrame then
			fire(self, "OnSizeChanged", getWidth(self), getHeight(self))
		end
	end

	-- Region.
	impl.Region.SetAlpha = function(self, a)
		st(self).alpha = a
	end
	impl.Region.GetAlpha = function(self)
		return st(self).alpha
	end
	impl.Region.GetEffectiveAlpha = function(self)
		local s, a = st(self), 1
		while s do
			a = a * (Secret.unwrap(s.alpha) or 1)
			s = s.parent and S[s.parent]
		end
		return a
	end
	impl.Region.SetScale = function(self, scale)
		st(self).scale = scale
		dirty()
	end
	impl.Region.GetScale = function(self)
		return st(self).scale
	end
	impl.Region.GetEffectiveScale = function(self)
		return effectiveScale(self)
	end
	impl.Region.SetIgnoreParentScale = function(self, on)
		st(self).ignoreParentScale = on
		dirty()
	end
	impl.Region.IsIgnoringParentScale = function(self)
		return st(self).ignoreParentScale == true
	end
	impl.Region.SetDrawLayer = function(self, layer, sublevel)
		local s = st(self)
		s.layer, s.sublevel = layer, sublevel or s.sublevel or 0
	end
	impl.Region.GetDrawLayer = function(self)
		local s = st(self)
		return s.layer or "ARTWORK", s.sublevel or 0
	end
	impl.Region.SetVertexColor = function(self, r, g, b, a)
		st(self).vertexColor = { r, g, b, a or 1 }
	end
	impl.Region.GetVertexColor = function(self)
		local c = st(self).vertexColor or { 1, 1, 1, 1 }
		return c[1], c[2], c[3], c[4]
	end
	impl.Region.SetParent = function(self, parent)
		local s = st(self)
		if type(parent) == "string" then
			parent = G[parent]
		end
		local before = isVisible(self)
		if s.parent then
			removeChild(s.parent, self)
		end
		s.parent = parent
		if parent then
			addChild(parent, self)
			if s.isFrame and S[parent] and S[parent].isFrame then
				s.level = (S[parent].level or 0) + 1
				s.strata = S[parent].strata
			end
		end
		dirty()
		local after = isVisible(self)
		if before ~= after then
			visibilityChanged(self, after)
		end
	end
	impl.Region.IsObjectLoaded = function()
		return true
	end

	-- Frame.
	impl.Frame.GetChildren = function(self)
		return unpack(st(self).children or {})
	end
	impl.Frame.GetNumChildren = function(self)
		return #(st(self).children or {})
	end
	impl.Frame.GetRegions = function(self)
		return unpack(st(self).regions or {})
	end
	impl.Frame.GetNumRegions = function(self)
		return #(st(self).regions or {})
	end
	impl.Frame.GetAdditionalRegions = function()
		return nil
	end
	impl.Frame.SetID = function(self, id)
		st(self).frameID = id
	end
	impl.Frame.GetID = function(self)
		return st(self).frameID or 0
	end
	impl.Frame.SetFrameStrata = function(self, strata)
		st(self).strata = strata
	end
	impl.Frame.GetFrameStrata = function(self)
		return st(self).strata or "MEDIUM"
	end
	impl.Frame.SetFrameLevel = function(self, level)
		st(self).level = level
	end
	impl.Frame.GetFrameLevel = function(self)
		return st(self).level or 0
	end
	impl.Frame.SetFixedFrameLevel = function(self, on)
		st(self).fixedLevel = on
	end
	impl.Frame.SetFixedFrameStrata = function(self, on)
		st(self).fixedStrata = on
	end
	impl.Frame.SetToplevel = function(self, on)
		st(self).toplevel = on
	end
	impl.Frame.Raise = function(self)
		local s = st(self)
		s.level = (s.level or 0) + 1
	end
	impl.Frame.Lower = function(self)
		local s = st(self)
		s.level = math.max(0, (s.level or 0) - 1)
	end
	impl.Frame.RegisterEvent = function(self, event)
		local s = st(self)
		if not sim.knownEvent(event) then
			error(string.format('Attempt to register unknown event "%s"', tostring(event)), 2)
		end
		if not s.events[event] then
			s.events[event] = true
			sim.events.register(self, event)
		end
		return true
	end
	impl.Frame.RegisterUnitEvent = function(self, event, ...)
		local s = st(self)
		impl.Frame.RegisterEvent(self, event)
		s.unitEvents = s.unitEvents or {}
		s.unitEvents[event] = { ... }
		return true
	end
	impl.Frame.UnregisterEvent = function(self, event)
		local s = st(self)
		if s.events[event] then
			s.events[event] = nil
			sim.events.unregister(self, event)
		end
	end
	impl.Frame.UnregisterAllEvents = function(self)
		local s = st(self)
		for event in pairs(s.events) do
			sim.events.unregister(self, event)
		end
		s.events = {}
	end
	impl.Frame.RegisterAllEvents = function(self)
		st(self).allEvents = true
		sim.events.register(self, "*")
	end
	impl.Frame.IsEventRegistered = function(self, event)
		return st(self).events[event] == true
	end
	impl.Frame.SetAttribute = function(self, name, value)
		local s = st(self)
		if s.protected and Taint.current and sim.inCombat then
			sim.blocked(self, "SetAttribute")
			return
		end
		s.attributes[name] = value
		fire(self, "OnAttributeChanged", name, value)
	end
	impl.Frame.SetAttributeNoHandler = function(self, name, value)
		st(self).attributes[name] = value
	end
	impl.Frame.GetAttribute = function(self, name)
		return st(self).attributes[name]
	end
	impl.Frame.CreateTexture = function(self, name, layer, template, sublevel)
		return sim.templates.createRegion("Texture", name, self, template, layer, sublevel)
	end
	impl.Frame.CreateMaskTexture = function(self, name, layer, template, sublevel)
		return sim.templates.createRegion("MaskTexture", name, self, template, layer, sublevel)
	end
	impl.Frame.CreateLine = function(self, name, layer, template, sublevel)
		return sim.templates.createRegion("Line", name, self, template, layer, sublevel)
	end
	impl.Frame.CreateFontString = function(self, name, layer, template)
		return sim.templates.createRegion("FontString", name, self, template, layer)
	end
	impl.Frame.CreateAnimationGroup = function(self, name, template)
		return sim.templates.createAnimationGroup(self, name, template)
	end
	impl.Frame.GetAnimationGroups = function(self)
		return unpack(st(self).animationGroups or {})
	end
	impl.Frame.SetClampedToScreen = function(self, on)
		st(self).clamped = on
	end
	impl.Frame.IsClampedToScreen = function(self)
		return st(self).clamped == true
	end
	impl.Frame.SetMovable = function(self, on)
		st(self).movable = on
	end
	impl.Frame.IsMovable = function(self)
		return st(self).movable == true
	end
	impl.Frame.SetResizable = function(self, on)
		st(self).resizable = on
	end
	impl.Frame.IsResizable = function(self)
		return st(self).resizable == true
	end
	impl.Frame.StartMoving = function() end
	impl.Frame.StopMovingOrSizing = function() end
	impl.Frame.SetUserPlaced = function(self, on)
		st(self).userPlaced = on
	end
	impl.Frame.IsUserPlaced = function(self)
		return st(self).userPlaced == true
	end
	impl.Frame.EnableKeyboard = function(self, on)
		st(self).keyboard = on
	end
	impl.Frame.IsKeyboardEnabled = function(self)
		return st(self).keyboard == true
	end
	impl.Frame.EnableMouseWheel = function(self, on)
		st(self).wheel = on
	end
	impl.Frame.IsMouseWheelEnabled = function(self)
		return st(self).wheel == true
	end
	impl.Frame.GetEffectiveAlpha = impl.Region.GetEffectiveAlpha
	impl.Frame.GetBoundsRect = function(self)
		return getRect(self)
	end
	impl.Frame.DoesClipChildren = function(self)
		return st(self).clip == true
	end
	impl.Frame.SetClipsChildren = function(self, on)
		st(self).clip = on
	end
	impl.Frame.SetHitRectInsets = function(self, l, r, t, b)
		st(self).hitRect = { l, r, t, b }
	end
	impl.Frame.GetHitRectInsets = function(self)
		local h = st(self).hitRect or { 0, 0, 0, 0 }
		return h[1], h[2], h[3], h[4]
	end
	impl.Frame.SetFlattensRenderLayers = function() end
	impl.Frame.SetPropagateKeyboardInput = function(self, on)
		st(self).propagateKeyboard = on
	end
	impl.Frame.GetPropagateKeyboardInput = function(self)
		return st(self).propagateKeyboard == true
	end
	impl.Frame.SetResizeBounds = function(self, a, b, c, d)
		st(self).resizeBounds = { a, b, c, d }
	end
	impl.Frame.GetResizeBounds = function(self)
		local r = st(self).resizeBounds or { 0, 0, 0, 0 }
		return r[1], r[2], r[3], r[4]
	end
	impl.Frame.ExecuteAttribute = function(self, name, ...)
		local f = st(self).attributes[name]
		if type(f) == "function" then
			return f(self, ...)
		end
	end

	-- Button.
	local function buttonRegion(self, key, kind, layer, value)
		local s = st(self)
		local region = s[key]
		if value == nil then
			return region
		end
		if type(value) == "table" and S[value] then
			region = value
			S[region].parent = self
		else
			if not region then
				region = sim.templates.createRegion(kind or "Texture", nil, self, nil, layer)
				region:SetAllPoints(self)
			end
			if type(value) == "string" or type(value) == "number" then
				if kind == "FontString" then
					region:SetText(value)
				else
					region:SetTexture(value)
				end
			end
		end
		s[key] = region
		return region
	end
	for _, spec in ipairs({
		{ "NormalTexture", "ARTWORK" },
		{ "PushedTexture", "ARTWORK" },
		{ "DisabledTexture", "ARTWORK" },
		{ "HighlightTexture", "HIGHLIGHT" },
	}) do
		local key, layer = spec[1], spec[2]
		impl.Button["Set" .. key] = function(self, value)
			buttonRegion(self, key, "Texture", layer, value)
		end
		impl.Button["Get" .. key] = function(self)
			return st(self)[key]
		end
		impl.Button["Clear" .. key] = function(self)
			local region = st(self)[key]
			if region then
				region:SetTexture(nil)
			end
		end
		impl.Button["Set" .. key:gsub("Texture$", "Atlas")] = function(self, atlas)
			buttonRegion(self, key, "Texture", layer, "atlas")
			st(self)[key]:SetAtlas(atlas)
		end
	end
	impl.CheckButton.SetCheckedTexture = function(self, value)
		buttonRegion(self, "CheckedTexture", "Texture", "ARTWORK", value)
	end
	impl.CheckButton.GetCheckedTexture = function(self)
		return st(self).CheckedTexture
	end
	impl.CheckButton.SetDisabledCheckedTexture = function(self, value)
		buttonRegion(self, "DisabledCheckedTexture", "Texture", "ARTWORK", value)
	end
	impl.CheckButton.GetDisabledCheckedTexture = function(self)
		return st(self).DisabledCheckedTexture
	end
	impl.Button.SetFontString = function(self, fs)
		st(self).fontString = fs
	end
	impl.Button.GetFontString = function(self)
		return st(self).fontString
	end
	local function buttonText(self)
		local s = st(self)
		if not s.fontString then
			local fs = sim.templates.createRegion("FontString", nil, self, nil, "ARTWORK")
			fs:SetPoint("CENTER")
			local font = s.normalFont
			if font then
				fs:SetFontObject(font)
			end
			s.fontString = fs
		end
		return s.fontString
	end
	impl.Button.SetText = function(self, text)
		buttonText(self):SetText(text)
	end
	impl.Button.SetFormattedText = function(self, fmt, ...)
		buttonText(self):SetFormattedText(fmt, ...)
	end
	impl.Button.GetText = function(self)
		local fs = st(self).fontString
		return fs and fs:GetText()
	end
	impl.Button.GetTextWidth = function(self)
		local fs = st(self).fontString
		return fs and fs:GetStringWidth() or 0
	end
	impl.Button.GetTextHeight = function(self)
		local fs = st(self).fontString
		return fs and fs:GetStringHeight() or 0
	end
	for _, key in ipairs({ "Normal", "Highlight", "Disabled" }) do
		impl.Button["Set" .. key .. "FontObject"] = function(self, font)
			local s = st(self)
			s[key:lower() .. "Font"] = font
			if key == "Normal" and s.fontString and font then
				s.fontString:SetFontObject(font)
			end
		end
		impl.Button["Get" .. key .. "FontObject"] = function(self)
			return st(self)[key:lower() .. "Font"]
		end
	end
	impl.Button.Enable = function(self)
		local s = st(self)
		if s.disabled then
			s.disabled = false
			fire(self, "OnEnable")
		end
	end
	impl.Button.Disable = function(self)
		local s = st(self)
		if not s.disabled then
			s.disabled = true
			fire(self, "OnDisable")
		end
	end
	impl.Button.SetEnabled = function(self, on)
		if on then
			impl.Button.Enable(self)
		else
			impl.Button.Disable(self)
		end
	end
	impl.Button.IsEnabled = function(self)
		return not st(self).disabled
	end
	impl.Button.RegisterForClicks = function(self, ...)
		st(self).clicks = { ... }
	end
	impl.Button.RegisterForMouse = function(self, ...)
		st(self).mouseButtons = { ... }
	end
	impl.Button.SetButtonState = function(self, state, locked)
		local s = st(self)
		s.buttonState, s.buttonLocked = state, locked
	end
	impl.Button.GetButtonState = function(self)
		return st(self).buttonState or "NORMAL"
	end
	impl.Button.LockHighlight = function(self)
		st(self).highlightLocked = true
	end
	impl.Button.UnlockHighlight = function(self)
		st(self).highlightLocked = false
	end
	impl.Button.SetHighlightLocked = function(self, on)
		st(self).highlightLocked = on
	end
	impl.Button.IsHighlightLocked = function(self)
		return st(self).highlightLocked == true
	end
	impl.Button.Click = function(self, button, down)
		local s = st(self)
		if s.disabled then
			return
		end
		button = button or "LeftButton"
		fire(self, "PreClick", button, down or false)
		if s.kind == "CheckButton" then
			s.checked = not s.checked
		end
		fire(self, "OnClick", button, down or false)
		fire(self, "PostClick", button, down or false)
	end
	impl.CheckButton.SetChecked = function(self, on)
		st(self).checked = not not on
	end
	impl.CheckButton.GetChecked = function(self)
		return st(self).checked == true
	end

	-- EditBox.
	impl.EditBox.SetText = function(self, text)
		local s = st(self)
		text = text == nil and "" or text
		if not Secret.is(text) then
			text = tostring(text)
			if s.maxLetters and s.maxLetters > 0 then
				text = text:sub(1, s.maxLetters)
			end
		end
		if s.text == text then
			return
		end
		s.text = text
		fire(self, "OnTextChanged", false)
	end
	impl.EditBox.GetText = function(self)
		return st(self).text or ""
	end
	impl.EditBox.Insert = function(self, text)
		local s = st(self)
		s.text = (s.text or "") .. tostring(text)
		fire(self, "OnTextChanged", true)
	end
	impl.EditBox.GetNumber = function(self)
		return tonumber(st(self).text) or 0
	end
	impl.EditBox.SetNumber = function(self, n)
		impl.EditBox.SetText(self, tostring(n))
	end
	impl.EditBox.SetMaxLetters = function(self, n)
		st(self).maxLetters = n
	end
	impl.EditBox.GetMaxLetters = function(self)
		return st(self).maxLetters or 0
	end
	impl.EditBox.SetFocus = function(self)
		local was = sim.keyboardFocus
		if was == self then
			return
		end
		if was then
			impl.EditBox.ClearFocus(was)
		end
		sim.keyboardFocus = self
		fire(self, "OnEditFocusGained")
	end
	impl.EditBox.ClearFocus = function(self)
		if sim.keyboardFocus == self then
			sim.keyboardFocus = nil
			fire(self, "OnEditFocusLost")
		end
	end
	impl.EditBox.HasFocus = function(self)
		return sim.keyboardFocus == self
	end
	impl.EditBox.GetNumLetters = function(self)
		return #(Secret.unwrap(st(self).text) or "")
	end
	impl.EditBox.SetFontObject = function(self, font)
		st(self).fontObject = font
	end
	impl.EditBox.GetFontObject = function(self)
		return st(self).fontObject
	end

	-- Slider and StatusBar.
	for _, kind in ipairs({ "Slider", "StatusBar" }) do
		impl[kind].SetMinMaxValues = function(self, lo, hi)
			local s = st(self)
			s.min, s.max = lo, hi
			local v = Secret.unwrap(s.value)
			if v and not Secret.is(lo) and not Secret.is(hi) then
				local clamped = math.min(math.max(v, lo), hi)
				if clamped ~= v then
					s.value = clamped
					fire(self, "OnValueChanged", clamped, false)
				end
			end
			fire(self, "OnMinMaxChanged", lo, hi)
		end
		impl[kind].GetMinMaxValues = function(self)
			local s = st(self)
			return s.min or 0, s.max or 0
		end
		impl[kind].SetValue = function(self, value, userInput)
			local s = st(self)
			if not Secret.is(value) and type(value) == "number" then
				local lo, hi = Secret.unwrap(s.min) or 0, Secret.unwrap(s.max) or 0
				if hi >= lo then
					value = math.min(math.max(value, lo), hi)
				end
			end
			local changed = s.value ~= value
			s.value = value
			if changed then
				fire(self, "OnValueChanged", value, userInput or false)
			end
		end
		impl[kind].GetValue = function(self)
			return st(self).value or 0
		end
	end
	impl.StatusBar.SetStatusBarTexture = function(self, value)
		local s = st(self)
		if type(value) == "table" and S[value] then
			s.barTexture = value
		else
			if not s.barTexture then
				s.barTexture = sim.templates.createRegion("Texture", nil, self, nil, "ARTWORK")
				s.barTexture:SetAllPoints(self)
			end
			s.barTexture:SetTexture(value)
		end
	end
	impl.StatusBar.GetStatusBarTexture = function(self)
		local s = st(self)
		if not s.barTexture then
			impl.StatusBar.SetStatusBarTexture(self, nil)
		end
		return s.barTexture
	end
	impl.StatusBar.SetStatusBarColor = function(self, r, g, b, a)
		impl.StatusBar.GetStatusBarTexture(self):SetVertexColor(r, g, b, a)
	end
	impl.StatusBar.GetStatusBarColor = function(self)
		return impl.StatusBar.GetStatusBarTexture(self):GetVertexColor()
	end
	impl.Slider.SetThumbTexture = function(self, value)
		local s = st(self)
		if type(value) == "table" and S[value] then
			s.thumb = value
		else
			s.thumb = s.thumb or sim.templates.createRegion("Texture", nil, self, nil, "ARTWORK")
			s.thumb:SetTexture(value)
		end
	end
	impl.Slider.GetThumbTexture = function(self)
		return st(self).thumb
	end
	impl.Slider.SetValueStep = function(self, step)
		st(self).step = step
	end
	impl.Slider.GetValueStep = function(self)
		return st(self).step or 0
	end
	impl.Slider.Enable = impl.Button.Enable
	impl.Slider.Disable = impl.Button.Disable
	impl.Slider.SetEnabled = impl.Button.SetEnabled
	impl.Slider.IsEnabled = impl.Button.IsEnabled

	-- ScrollFrame.
	impl.ScrollFrame.SetScrollChild = function(self, child)
		local s = st(self)
		s.scrollChild = child
		if child and S[child] then
			impl.Region.SetParent(child, self)
		end
	end
	impl.ScrollFrame.GetScrollChild = function(self)
		return st(self).scrollChild
	end
	local function scrollRange(self, axis)
		local s = st(self)
		local child = s.scrollChild
		if not child then
			return 0
		end
		if axis == "v" then
			return math.max(0, getHeight(child) - getHeight(self))
		end
		return math.max(0, getWidth(child) - getWidth(self))
	end
	impl.ScrollFrame.GetVerticalScrollRange = function(self)
		return scrollRange(self, "v")
	end
	impl.ScrollFrame.GetHorizontalScrollRange = function(self)
		return scrollRange(self, "h")
	end
	impl.ScrollFrame.SetVerticalScroll = function(self, offset)
		st(self).vscroll = offset
		fire(self, "OnVerticalScroll", offset)
	end
	impl.ScrollFrame.GetVerticalScroll = function(self)
		return st(self).vscroll or 0
	end
	impl.ScrollFrame.SetHorizontalScroll = function(self, offset)
		st(self).hscroll = offset
		fire(self, "OnHorizontalScroll", offset)
	end
	impl.ScrollFrame.GetHorizontalScroll = function(self)
		return st(self).hscroll or 0
	end
	impl.ScrollFrame.UpdateScrollChildRect = function(self)
		fire(self, "OnScrollRangeChanged", scrollRange(self, "h"), scrollRange(self, "v"))
	end

	-- FontString and Font.
	local function copyFont(dst, src)
		local f = S[src]
		if not f then
			return
		end
		dst.fontFile, dst.fontHeight, dst.fontFlags = f.fontFile, f.fontHeight, f.fontFlags
		dst.textColor = f.textColor and { unpack(f.textColor) } or dst.textColor
		dst.justifyH = f.justifyH or dst.justifyH
		dst.justifyV = f.justifyV or dst.justifyV
		dst.spacing = f.spacing or dst.spacing
		dst.shadowColor = f.shadowColor or dst.shadowColor
		dst.shadowOffset = f.shadowOffset or dst.shadowOffset
	end
	W.copyFont = copyFont
	local function fontLookup(font)
		if type(font) == "string" then
			return G[font]
		end
		return font
	end
	local function setText(self, text)
		local s = st(self)
		if text ~= nil and not Secret.is(text) and type(text) ~= "string" then
			text = tostring(text)
		end
		s.text = text
		dirty()
	end
	impl.FontString.SetText = setText
	impl.FontString.SetFormattedText = function(self, fmt, ...)
		setText(self, G.string.format(fmt, ...))
	end
	impl.FontString.GetText = function(self)
		return st(self).text
	end
	impl.FontString.ClearText = function(self)
		local s = st(self)
		s.text = ""
		s.aspects[Secret.ASPECT_TEXT or 8] = nil
		dirty()
	end
	impl.FontString.SetTextToFit = function(self, text)
		setText(self, text)
	end
	impl.FontString.SetFont = function(self, file, height, flags)
		local s = st(self)
		s.fontFile, s.fontHeight, s.fontFlags = file, height, flags
		dirty()
		return true
	end
	impl.FontString.GetFont = function(self)
		local s = st(self)
		return s.fontFile, s.fontHeight or 12, s.fontFlags or ""
	end
	impl.FontString.SetFontObject = function(self, font)
		local s = st(self)
		font = fontLookup(font)
		s.fontObject = font
		copyFont(s, font)
		dirty()
	end
	impl.FontString.GetFontObject = function(self)
		return st(self).fontObject
	end
	impl.FontString.SetTextColor = function(self, r, g, b, a)
		st(self).textColor = { r, g, b, a or 1 }
	end
	impl.FontString.GetTextColor = function(self)
		local c = st(self).textColor or { 1, 1, 1, 1 }
		return c[1], c[2], c[3], c[4]
	end
	impl.FontString.GetStringWidth = function(self)
		return (textSize(st(self)))
	end
	impl.FontString.GetUnboundedStringWidth = function(self)
		local s = st(self)
		local saved = s.width
		s.width = nil
		local w = textSize(s)
		s.width = saved
		return w
	end
	impl.FontString.GetStringHeight = function(self)
		local _, h = textSize(st(self))
		return h
	end
	impl.FontString.GetLineHeight = function(self)
		return st(self).fontHeight or 12
	end
	impl.FontString.GetNumLines = function(self)
		local s = st(self)
		local _, h = textSize(s)
		return math.max(1, math.floor(h / (s.fontHeight or 12) + 0.5))
	end
	impl.FontString.IsTruncated = function(self)
		local s = st(self)
		local w = Secret.unwrap(s.width)
		if not w or w == 0 then
			local r = rect(self)
			w = r and r[3] / effectiveScale(self)
		end
		if not w or w == 0 then
			return false
		end
		local saved = s.width
		s.width = nil
		local tw = textSize(s)
		s.width = saved
		return tw > w + 0.5 and (s.wordWrap == false or (s.maxLines or 0) == 1)
	end
	impl.FontString.SetWordWrap = function(self, on)
		st(self).wordWrap = not not on
		dirty()
	end
	impl.FontString.CanWordWrap = function(self)
		return st(self).wordWrap ~= false
	end
	impl.FontString.SetMaxLines = function(self, n)
		st(self).maxLines = n
		dirty()
	end
	impl.FontString.GetMaxLines = function(self)
		return st(self).maxLines or 0
	end
	impl.FontString.SetSpacing = function(self, n)
		st(self).spacing = n
	end
	impl.FontString.GetSpacing = function(self)
		return st(self).spacing or 0
	end
	impl.FontString.SetJustifyH = function(self, j)
		st(self).justifyH = j
	end
	impl.FontString.GetJustifyH = function(self)
		return st(self).justifyH or "CENTER"
	end
	impl.FontString.SetJustifyV = function(self, j)
		st(self).justifyV = j
	end
	impl.FontString.GetJustifyV = function(self)
		return st(self).justifyV or "MIDDLE"
	end
	impl.FontString.SetTextHeight = function(self, h)
		st(self).fontHeight = h
		dirty()
	end
	impl.FontString.SetFontHeight = impl.FontString.SetTextHeight
	impl.FontString.GetFontHeight = impl.FontString.GetLineHeight
	impl.Font.SetFont = function(self, file, height, flags)
		local s = st(self)
		s.fontFile, s.fontHeight, s.fontFlags = file, height, flags
		return true
	end
	impl.Font.GetFont = impl.FontString.GetFont
	impl.Font.SetFontObject = function(self, font)
		copyFont(st(self), fontLookup(font))
	end
	impl.Font.CopyFontObject = impl.Font.SetFontObject
	impl.Font.GetFontObject = function()
		return nil
	end
	impl.Font.SetTextColor = impl.FontString.SetTextColor
	impl.Font.GetTextColor = impl.FontString.GetTextColor
	impl.Font.SetJustifyH = impl.FontString.SetJustifyH
	impl.Font.GetJustifyH = impl.FontString.GetJustifyH
	impl.Font.SetJustifyV = impl.FontString.SetJustifyV
	impl.Font.GetJustifyV = impl.FontString.GetJustifyV
	impl.Font.SetSpacing = impl.FontString.SetSpacing
	impl.Font.GetSpacing = impl.FontString.GetSpacing
	impl.Font.GetName = impl.Object.GetName

	-- Textures.
	impl.TextureBase.SetTexture = function(self, file)
		local s = st(self)
		s.file, s.atlas, s.color = file, nil, nil
		return true
	end
	impl.TextureBase.GetTexture = function(self)
		return st(self).file
	end
	impl.TextureBase.GetTextureFilePath = impl.TextureBase.GetTexture
	impl.TextureBase.GetTextureFileID = function(self)
		local f = st(self).file
		return type(f) == "number" and f or nil
	end
	impl.TextureBase.SetAtlas = function(self, atlas, useAtlasSize)
		local s = st(self)
		s.atlas, s.file, s.color = atlas, nil, nil
		if useAtlasSize then
			local info = sim.atlasInfo and sim.atlasInfo(atlas)
			if info then
				s.width, s.height = info.width, info.height
				dirty()
			end
		end
		return true
	end
	impl.TextureBase.GetAtlas = function(self)
		return st(self).atlas
	end
	impl.TextureBase.SetColorTexture = function(self, r, g, b, a)
		local s = st(self)
		s.color, s.file, s.atlas = { r, g, b, a or 1 }, nil, nil
	end
	impl.TextureBase.SetTexCoord = function(self, ...)
		st(self).texCoord = { ... }
	end
	impl.TextureBase.GetTexCoord = function(self)
		local c = st(self).texCoord
		if not c or #c == 0 then
			return 0, 0, 0, 1, 1, 0, 1, 1
		end
		if #c == 4 then
			return c[1], c[3], c[1], c[4], c[2], c[3], c[2], c[4]
		end
		return unpack(c)
	end
	impl.TextureBase.SetRotation = function(self, r)
		st(self).rotation = r
	end
	impl.TextureBase.GetRotation = function(self)
		return st(self).rotation or 0
	end
	impl.TextureBase.AddMaskTexture = function(self, mask)
		local s = st(self)
		s.masks = s.masks or {}
		table.insert(s.masks, mask)
	end
	impl.TextureBase.RemoveMaskTexture = function(self, mask)
		local s = st(self)
		for i, m in ipairs(s.masks or {}) do
			if m == mask then
				table.remove(s.masks, i)
				return
			end
		end
	end
	impl.TextureBase.GetNumMaskTextures = function(self)
		return #(st(self).masks or {})
	end
	impl.TextureBase.GetMaskTexture = function(self, i)
		return (st(self).masks or {})[i]
	end
	impl.Line.SetStartPoint = function(self, ...)
		st(self).startPoint = { ... }
	end
	impl.Line.SetEndPoint = function(self, ...)
		st(self).endPoint = { ... }
	end
	impl.Line.GetStartPoint = function(self)
		return unpack(st(self).startPoint or {})
	end
	impl.Line.GetEndPoint = function(self)
		return unpack(st(self).endPoint or {})
	end

	-- Animations.
	impl.FrameScriptObject.GetParent = impl.Object.GetParent
	impl.AnimationGroup.CreateAnimation = function(self, kind, name, template)
		return sim.templates.createAnimation(self, kind, name, template)
	end
	impl.AnimationGroup.GetAnimations = function(self)
		return unpack(st(self).animations or {})
	end
	local function groupDuration(self)
		local orders = {}
		for _, a in ipairs(st(self).animations or {}) do
			local as = S[a]
			local o = as.order or 1
			local d = (Secret.unwrap(as.startDelay) or 0)
				+ (Secret.unwrap(as.duration) or 0)
				+ (Secret.unwrap(as.endDelay) or 0)
			orders[o] = math.max(orders[o] or 0, d)
		end
		local total = 0
		for _, d in pairs(orders) do
			total = total + d
		end
		return total
	end
	impl.AnimationGroup.GetDuration = function(self)
		return groupDuration(self)
	end
	impl.AnimationGroup.Play = function(self, reverse, offset)
		local s = st(self)
		s.playing, s.paused, s.elapsed, s.reverse = true, false, offset or 0, reverse
		sim.animations[self] = true
		fire(self, "OnPlay")
		for _, a in ipairs(s.animations or {}) do
			fire(a, "OnPlay")
		end
	end
	impl.AnimationGroup.Restart = function(self, reverse, offset)
		impl.AnimationGroup.Play(self, reverse, offset)
	end
	impl.AnimationGroup.Stop = function(self)
		local s = st(self)
		if s.playing then
			s.playing = false
			sim.animations[self] = nil
			fire(self, "OnStop", true)
		end
	end
	impl.AnimationGroup.Finish = function(self)
		local s = st(self)
		if s.playing then
			s.playing = false
			sim.animations[self] = nil
			fire(self, "OnFinished", false)
		end
	end
	impl.AnimationGroup.Pause = function(self)
		st(self).paused = true
	end
	impl.AnimationGroup.IsPlaying = function(self)
		local s = st(self)
		return s.playing == true and not s.paused
	end
	impl.AnimationGroup.IsPaused = function(self)
		return st(self).paused == true
	end
	impl.AnimationGroup.IsDone = function(self)
		return not st(self).playing
	end
	impl.AnimationGroup.SetLooping = function(self, mode)
		st(self).looping = mode
	end
	impl.AnimationGroup.GetLooping = function(self)
		return st(self).looping or "NONE"
	end
	impl.AnimationGroup.SetToFinalAlpha = function(self, on)
		st(self).toFinalAlpha = on
	end
	impl.AnimationGroup.GetProgress = function(self)
		local s = st(self)
		local d = groupDuration(self)
		return d > 0 and math.min(1, (s.elapsed or 0) / d) or 0
	end
	function W.tickAnimations(dt)
		local finished = {}
		for group in pairs(sim.animations) do
			local s = S[group]
			if s.playing and not s.paused then
				s.elapsed = (s.elapsed or 0) + dt
				local d = groupDuration(group)
				if s.elapsed >= d then
					if s.looping and s.looping ~= "NONE" then
						s.elapsed = 0
						W.dispatch(group, "OnLoop", "FORWARD")
					else
						finished[#finished + 1] = group
					end
				end
			end
		end
		for _, group in ipairs(finished) do
			local s = S[group]
			s.playing = false
			sim.animations[group] = nil
			for _, a in ipairs(s.animations or {}) do
				W.dispatch(a, "OnFinished", false)
			end
			W.dispatch(group, "OnFinished", false)
		end
	end
	impl.Animation.GetRegionParent = function(self)
		local group = st(self).parent
		return group and S[group] and S[group].parent
	end
	impl.Animation.SetTarget = function(self, target)
		st(self).target = target
	end
	impl.Animation.GetTarget = function(self)
		local s = st(self)
		return s.target or impl.Animation.GetRegionParent(self)
	end
	impl.Animation.SetChildKey = function(self, key)
		st(self).childKey = key
	end
	impl.Animation.SetTargetKey = impl.Animation.SetChildKey
	impl.Animation.SetTargetName = function(self, name)
		st(self).target = G[name]
	end
	impl.Animation.SetDuration = function(self, d)
		st(self).duration = d
	end
	impl.Animation.GetDuration = function(self)
		return st(self).duration or 0
	end
	impl.Animation.SetStartDelay = function(self, d)
		st(self).startDelay = d
	end
	impl.Animation.GetStartDelay = function(self)
		return st(self).startDelay or 0
	end
	impl.Animation.SetEndDelay = function(self, d)
		st(self).endDelay = d
	end
	impl.Animation.GetEndDelay = function(self)
		return st(self).endDelay or 0
	end
	impl.Animation.SetOrder = function(self, o)
		st(self).order = o
	end
	impl.Animation.GetOrder = function(self)
		return st(self).order or 1
	end
	impl.Animation.IsPlaying = function(self)
		local group = st(self).parent
		return group and impl.AnimationGroup.IsPlaying(group) or false
	end
	impl.Animation.Play = function(self)
		local group = st(self).parent
		if group then
			impl.AnimationGroup.Play(group)
		end
	end
	impl.Animation.Stop = function(self)
		local group = st(self).parent
		if group then
			impl.AnimationGroup.Stop(group)
		end
	end

	---------------------------------------------------------------------------
	-- Method tables from the documentation, each method wrapped with its secret and protection rules.
	---------------------------------------------------------------------------
	local docs = sim.docs
	local ASPECT = {}
	for _, f in ipairs(docs.enums.SecretAspect and docs.enums.SecretAspect.Fields or {}) do
		ASPECT[f.Name] = f.EnumValue
	end
	Secret.ASPECT_TEXT = ASPECT.Text
	W.ASPECT = ASPECT

	local function docAspects(fdoc, key)
		local out = {}
		for _, n in ipairs(require("docs").enumNames(fdoc[key])) do
			out[#out + 1] = ASPECT[n]
		end
		return out
	end

	local function wrapMethod(kind, name, fdoc, body)
		if not fdoc then
			return body
		end
		local addAspects = fdoc.SecretArgumentsAddAspect and docAspects(fdoc, "SecretArgumentsAddAspect")
		local returnAspects = fdoc.SecretReturnsForAspect and docAspects(fdoc, "SecretReturnsForAspect")
		local whenAnchoring = fdoc.SecretWhenAnchoringSecret
		local secretArgs = fdoc.SecretArguments
		local protected = fdoc.IsProtectedFunction
		local nargs = fdoc.Arguments and #fdoc.Arguments or 0
		local plainBody = not addAspects and not returnAspects and not whenAnchoring and not protected
		if plainBody and secretArgs ~= "NotAllowed" and secretArgs ~= "AllowedWhenUntainted" then
			return body
		end
		return function(self, ...)
			local s = S[self]
			if not s then
				error(string.format("%s:%s(): bad self (call with ':')", kind, name), 2)
			end
			if secretArgs == "NotAllowed" or (secretArgs == "AllowedWhenUntainted" and Taint.current) then
				for i = 1, math.max(nargs, select("#", ...)) do
					if Secret.is((select(i, ...))) then
						error(
							string.format(
								"bad argument #%d to '%s' (secret values are not allowed%s)",
								i,
								name,
								Taint.current and string.format("; execution tainted by '%s'", Taint.current) or ""
							),
							2
						)
					end
				end
			end
			if protected and s.protected and Taint.current and sim.inCombat then
				sim.blocked(self, name)
				return
			end
			if addAspects then
				for i = 1, select("#", ...) do
					if Secret.is((select(i, ...))) then
						for _, a in ipairs(addAspects) do
							s.aspects[a] = true
						end
						dirty()
						break
					end
				end
			end
			local secret = false
			if whenAnchoring and anchoringSecret(self) then
				secret = true
			end
			if returnAspects and not secret then
				for _, a in ipairs(returnAspects) do
					if s.aspects[a] then
						secret = true
						break
					end
				end
			end
			if not secret then
				return body(self, ...)
			end
			local out = { body(self, ...) }
			for i = 1, table.maxn(out) do
				out[i] = Secret.wrap(out[i])
			end
			return unpack(out, 1, table.maxn(out))
		end
	end

	local function genericMethod(name, fdoc)
		-- A documented method nothing here implements: a setter stores its arguments for the matching getter.
		local rest = name:match("^Set(.+)$")
		if rest then
			return function(self, ...)
				st(self).props[rest] = { n = select("#", ...), ... }
			end
		end
		local getRest = name:match("^Get(.+)$") or name:match("^Is(.+)$") or name:match("^Has(.+)$")
		local returns = fdoc and fdoc.Returns or {}
		return function(self)
			local s = st(self)
			local stored = getRest and s.props[getRest]
			if stored then
				return unpack(stored, 1, stored.n)
			end
			local out, n = {}, 0
			for i, r in ipairs(returns) do
				if r.StrideIndex then
					break
				end
				out[i] = zeroOf(r)
				n = i
			end
			return unpack(out, 1, n)
		end
	end

	local function docMethods(kind)
		local out = {}
		for _, sys in ipairs(TYPES[kind][2]) do
			local d = docs.widgets[sys]
			for _, f in ipairs(d and d.Functions or {}) do
				out[f.Name] = f
			end
		end
		return out
	end

	local function flatten(kind)
		local chain = {}
		local t = kind
		while t do
			table.insert(chain, 1, t)
			t = TYPES[t][1]
		end
		-- The most derived implementation and documentation entry win.
		local bodies, fdocs, owner = {}, {}, {}
		for _, t2 in ipairs(chain) do
			for name, fdoc in pairs(docMethods(t2)) do
				fdocs[name] = fdoc
				owner[name] = owner[name] or t2
			end
			for name, body in pairs(impl[t2]) do
				bodies[name] = body
				owner[name] = owner[name] or t2
			end
		end
		local methods = {}
		for name, t2 in pairs(owner) do
			local fdoc = fdocs[name]
			methods[name] = wrapMethod(t2, name, fdoc, bodies[name] or genericMethod(name, fdoc))
		end
		return methods
	end
	W.flatten = flatten

	local lastSize = setmetatable({}, { __mode = "k" })
	function W.sizePass()
		for _, obj in ipairs(W.all) do
			local s = S[obj]
			if s.scripts and (s.scripts.OnSizeChanged or (s.hooks and s.hooks.OnSizeChanged)) then
				local w, h = getWidth(obj), getHeight(obj)
				local last = lastSize[obj]
				if not last then
					lastSize[obj] = { w, h }
				elseif math.abs(last[1] - w) > 0.01 or math.abs(last[2] - h) > 0.01 then
					last[1], last[2] = w, h
					W.dispatch(obj, "OnSizeChanged", w, h)
				end
			end
		end
	end

	function W.finalize()
		for kind in pairs(TYPES) do
			local methods = flatten(kind)
			W.methods[kind] = methods
			W.metas[kind] = { __index = methods }
		end
	end

	return W
end

return M
