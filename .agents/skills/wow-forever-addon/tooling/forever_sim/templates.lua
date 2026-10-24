-- FrameXML: loads Blizzard's and addons' XML (Script, Include, Font, FontFamily, frames, regions, animations),
-- keeps virtual and intrinsic templates, and instantiates them for XML and CreateFrame the way the client does:
-- templates in order, then the element; mixins first, then KeyValues, regions, child frames, animations and
-- scripts; anchors once the tree exists; OnLoad children first.
local XML = require("xml")
local Widgets = require("widgets")
local Instrument = require("instrument")

local M = {}

-- Parsed XML and compiled bytecode, shared by every sim in the process, so a suite of scenarios parses and
-- compiles the UI source once.
local xmlCache, chunkCache = {}, {}

-- Inline handler parameter names, as the client declares them.
local SCRIPT_ARGS = {
	OnEvent = "self, event, ...",
	OnUpdate = "self, elapsed",
	OnClick = "self, button, down",
	PreClick = "self, button, down",
	PostClick = "self, button, down",
	OnDoubleClick = "self, button",
	OnMouseDown = "self, button",
	OnMouseUp = "self, button, upInside",
	OnMouseWheel = "self, delta",
	OnEnter = "self, motion",
	OnLeave = "self, motion",
	OnValueChanged = "self, value, userInput",
	OnMinMaxChanged = "self, min, max",
	OnTextChanged = "self, userInput",
	OnChar = "self, text",
	OnKeyDown = "self, key",
	OnKeyUp = "self, key",
	OnSizeChanged = "self, width, height",
	OnAttributeChanged = "self, name, value",
	OnDragStart = "self, button",
	OnReceiveDrag = "self",
	OnVerticalScroll = "self, offset",
	OnHorizontalScroll = "self, offset",
	OnScrollRangeChanged = "self, xrange, yrange",
	OnHyperlinkClick = "self, link, text, button",
	OnHyperlinkEnter = "self, link, text, region, left, bottom, width, height",
	OnHyperlinkLeave = "self",
	OnFinished = "self, requested",
	OnStop = "self, requested",
	OnLoop = "self, loopState",
	OnTooltipSetItem = "self",
	OnTooltipAddMoney = "self, cost, maxcost",
	OnCursorChanged = "self, x, y, w, h",
	OnArrowPressed = "self, key",
	OnTabPressed = "self",
	OnEnterPressed = "self",
	OnEscapePressed = "self",
	OnEditFocusGained = "self",
	OnEditFocusLost = "self",
	OnInputLanguageChanged = "self, language",
	OnGamePadButtonDown = "self, button",
	OnGamePadButtonUp = "self, button",
	OnGamePadStick = "self, stick, x, y, len",
}

local CHILD_ELEMENTS = {
	Size = true,
	Anchors = true,
	Layers = true,
	Frames = true,
	Scripts = true,
	KeyValues = true,
	Animations = true,
	Attributes = true,
	HitRectInsets = true,
	ResizeBounds = true,
	TexCoords = true,
	Color = true,
	Shadow = true,
	Gradient = true,
	Backdrop = true,
	TextInsets = true,
	FontHeight = true,
	PushedTextOffset = true,
	ScrollChild = true,
	BarColor = true,
	Offset = true,
	MaxResize = true,
	MinResize = true,
	ButtonText = true,
	NormalFont = true,
	HighlightFont = true,
	DisabledFont = true,
	NormalTexture = true,
	PushedTexture = true,
	DisabledTexture = true,
	HighlightTexture = true,
	CheckedTexture = true,
	DisabledCheckedTexture = true,
	ThumbTexture = true,
	BarTexture = true,
	ColorWheelTexture = true,
	ColorWheelThumbTexture = true,
	ColorValueTexture = true,
	ColorValueThumbTexture = true,
	ColorAlphaTexture = true,
	ColorAlphaThumbTexture = true,
	SwipeTexture = true,
	EdgeTexture = true,
	BlingTexture = true,
	FontString = false,
	Texture = false,
	MaskTexture = false,
	Line = false,
	FontStringHeader1 = true,
	FontStringHeader2 = true,
	FontStringHeader3 = true,
}

local function bool(v)
	return v == "true"
end

local function num(v)
	return v and tonumber(v)
end

local function split(list)
	local out = {}
	for item in tostring(list or ""):gmatch("[^,%s]+") do
		out[#out + 1] = item
	end
	return out
end

local function childrenNamed(node, tag)
	local out = {}
	for _, c in ipairs(node.children) do
		if c.tag == tag then
			out[#out + 1] = c
		end
	end
	return out
end

local function firstChild(node, tag)
	for _, c in ipairs(node.children) do
		if c.tag == tag then
			return c
		end
	end
end

local function dimensions(node)
	if not node then
		return nil
	end
	local x, y = num(node.attr.x), num(node.attr.y)
	local abs = firstChild(node, "AbsDimension")
	if abs then
		x, y = num(abs.attr.x) or x, num(abs.attr.y) or y
	end
	return x, y
end

function M.build(sim)
	local G, W, Taint = sim.G, sim.widgets, sim.taint
	local S = W.state
	local T =
		{ templates = {}, intrinsics = {}, files = {}, errors = {}, handlers = setmetatable({}, { __mode = "k" }) }
	sim.templates = T

	local function warn(msg)
		T.errors[#T.errors + 1] = msg
	end

	local function readFile(path)
		local f = io.open(path, "rb")
		if not f then
			return nil
		end
		local text = f:read("*a")
		f:close()
		return text
	end

	-- Compiles a script chunk with a chunk name the taint tracker reads ("@Folder/path/file.lua").
	function T.compile(code, chunkName, firstLine)
		if firstLine and firstLine > 1 then
			code = string.rep("\n", firstLine - 1) .. code
		end
		local folder = chunkName:match("^([^/\\]+)[/\\]")
		local addon = folder and Taint.addonFolders[folder]
		local key = (addon and "+" or "-") .. chunkName .. "\0" .. code
		local chunk
		local bytecode = chunkCache[key]
		if bytecode then
			chunk = loadstring(bytecode, "@" .. chunkName)
		else
			if addon then
				code = Instrument.rewrite(code, addon)
			end
			local err
			chunk, err = loadstring(code, "@" .. chunkName)
			if not chunk then
				return nil, err
			end
			-- Bytecode, not the function: a cached function would keep the first sim's environment alive.
			chunkCache[key] = string.dump(chunk)
		end
		setfenv(chunk, sim.env)
		return chunk
	end

	---------------------------------------------------------------------------
	-- Handlers
	---------------------------------------------------------------------------
	local function handlerFor(node, ctx)
		local fname, method = node.attr["function"], node.attr.method
		if fname then
			local f = G[fname]
			if type(f) ~= "function" then
				warn(string.format('%s: %s function="%s" is not defined', ctx.file, node.tag, fname))
				return nil
			end
			return f
		elseif method then
			return function(self, ...)
				local m = self[method]
				if type(m) ~= "function" then
					error(string.format("%s: method %s not found on %s", node.tag, method, tostring(self)), 2)
				end
				return m(self, ...)
			end
		elseif node.text and node.text:find("%S") then
			local cacheKey = node
			ctx.compiled = ctx.compiled or {}
			local f = T.handlers[node]
			if not f then
				local args = SCRIPT_ARGS[node.tag] or "self, ..."
				local chunk, err =
					T.compile("return function(" .. args .. ") " .. node.text .. "\nend", ctx.chunk, node.textLine)
				if not chunk then
					warn(err)
					return nil
				end
				f = chunk()
				T.handlers[node] = f
			end
			local _ = cacheKey
			return f
		end
	end

	local function combine(prev, nextf, order)
		if not prev then
			return nextf
		end
		if not nextf then
			return prev
		end
		if order == "prepend" or order == "precall" then
			return function(...)
				nextf(...)
				return prev(...)
			end
		elseif order == "append" or order == "postcall" then
			return function(...)
				prev(...)
				return nextf(...)
			end
		end
		return nextf
	end

	---------------------------------------------------------------------------
	-- Templates
	---------------------------------------------------------------------------
	local function templateNode(name)
		return T.templates[name]
	end

	-- The template chain (outermost first) for a node: each inherited template's own chain, in order.
	local function chain(node, out, seen)
		out = out or {}
		seen = seen or {}
		for _, name in ipairs(split(node.attr.inherits)) do
			local t = templateNode(name)
			if t and not seen[t] then
				seen[t] = true
				chain(t.node, out, seen)
				out[#out + 1] = t
			elseif not t and not (G[name] and S[G[name]] and S[G[name]].kind == "Font") then
				warn(string.format('Couldn\'t find inherited node "%s"', name))
			end
		end
		return out
	end

	local function kindOf(node)
		local intrinsic = T.intrinsics[node.tag]
		if intrinsic then
			return intrinsic.kind, intrinsic
		end
		return Widgets.ALIASES[node.tag] or node.tag, nil
	end

	local apply -- forward

	local function applyAnchors(obj, node, ctx, parent)
		local anchors = firstChild(node, "Anchors")
		if not anchors then
			return
		end
		for _, a in ipairs(childrenNamed(anchors, "Anchor")) do
			ctx.anchors[#ctx.anchors + 1] = { obj = obj, node = a, parent = parent, file = ctx.file }
		end
	end

	local function resolveRelative(obj, a, parent)
		local key, to = a.attr.relativeKey, a.attr.relativeTo
		if key then
			local target = obj
			for part in key:gmatch("[^%.]+") do
				if part == "$parent" or part == "$Parent" then
					target = target and S[target] and S[target].parent
				elseif part == "$Root" then
					local p = obj
					while p and S[p] and S[p].parent do
						p = S[p].parent
					end
					target = p
				else
					target = target and target[part]
				end
			end
			return target
		elseif to then
			if to == "$parent" or to == "$Parent" then
				return parent
			end
			return G[W.resolveName(to, parent)]
		end
		return nil
	end

	local function finishAnchors(ctx)
		for _, item in ipairs(ctx.anchors) do
			local a = item.node
			local point = a.attr.point
			local relative = resolveRelative(item.obj, a, S[item.obj].parent)
			local x, y = num(a.attr.x) or 0, num(a.attr.y) or 0
			local offset = firstChild(a, "Offset")
			if offset then
				local ox, oy = dimensions(offset)
				x, y = ox or x, oy or y
			end
			local ok, err =
				pcall(W.setPoint, item.obj, point, relative or S[item.obj].parent, a.attr.relativePoint or point, x, y)
			if not ok then
				warn(string.format("%s: anchor %s: %s", item.file, tostring(point), tostring(err)))
			end
		end
		ctx.anchors = {}
	end

	local function keyValue(kv)
		local v, t = kv.attr.value, kv.attr.type
		if t == "number" then
			v = tonumber(v)
		elseif t == "boolean" then
			v = v == "true"
		elseif t == "global" then
			v = G[v]
		end
		local k = kv.attr.key
		if kv.attr.keyType == "number" then
			k = tonumber(k)
		end
		return k, v
	end

	local function setFontAttributes(obj, node)
		local a = node.attr
		local s = S[obj]
		if a.font then
			local font = G[a.font]
			if font and S[font] then
				W.copyFont(s, font)
				s.fontObject = font
			else
				s.fontFile = a.font
			end
		end
		if a.height then
			s.fontHeight = num(a.height)
		end
		local fh = firstChild(node, "FontHeight")
		if fh then
			local abs = firstChild(fh, "AbsValue")
			s.fontHeight = abs and num(abs.attr.val) or s.fontHeight
		end
		if a.outline then
			s.fontFlags = a.outline
		end
		if a.justifyH then
			s.justifyH = a.justifyH
		end
		if a.justifyV then
			s.justifyV = a.justifyV
		end
		if a.spacing then
			s.spacing = num(a.spacing)
		end
		if a.maxLines then
			s.maxLines = num(a.maxLines)
		end
		if a.wordwrap then
			s.wordWrap = bool(a.wordwrap)
		end
		local color = firstChild(node, "Color")
		if color then
			s.textColor =
				{ num(color.attr.r) or 1, num(color.attr.g) or 1, num(color.attr.b) or 1, num(color.attr.a) or 1 }
		end
	end

	local function createChildRegion(node, obj, ctx, layer, sublevel)
		local kind = node.tag
		local region = apply(node, obj, ctx, kind, layer, sublevel)
		return region
	end

	local SPECIAL_REGIONS = {
		NormalTexture = "SetNormalTexture",
		PushedTexture = "SetPushedTexture",
		DisabledTexture = "SetDisabledTexture",
		HighlightTexture = "SetHighlightTexture",
		CheckedTexture = "SetCheckedTexture",
		DisabledCheckedTexture = "SetDisabledCheckedTexture",
		ThumbTexture = "SetThumbTexture",
		BarTexture = "SetStatusBarTexture",
	}

	-- Applies one XML node (a template or the element itself) to obj.
	local function applyNode(obj, node, ctx, parent)
		local s = S[obj]
		local a = node.attr
		if a.mixin then
			for _, m in ipairs(split(a.mixin)) do
				local mixin = G[m]
				if type(mixin) == "table" then
					G.Mixin(obj, mixin)
				else
					warn(string.format("%s: mixin %s is not defined", ctx.file, m))
				end
			end
		end
		if a.secureMixin then
			for _, m in ipairs(split(a.secureMixin)) do
				local mixin = G[m]
				if type(mixin) == "table" then
					G.Mixin(obj, mixin)
				end
			end
		end
		for _, kvs in ipairs(childrenNamed(node, "KeyValues")) do
			for _, kv in ipairs(childrenNamed(kvs, "KeyValue")) do
				local k, v = keyValue(kv)
				if k ~= nil then
					rawset(obj, k, v)
				end
			end
		end
		if a.hidden then
			s.shown = not bool(a.hidden)
		end
		if a.protected == "true" then
			s.protected = true
		end
		if a.alpha then
			s.alpha = num(a.alpha)
		end
		if a.scale then
			s.scale = num(a.scale)
		end
		if a.id then
			s.frameID = num(a.id)
		end
		if a.frameStrata then
			s.strata = a.frameStrata
		end
		if a.frameLevel then
			s.level = num(a.frameLevel)
		end
		if a.enableMouse then
			s.mouseClick, s.mouseMotion = bool(a.enableMouse), bool(a.enableMouse)
		end
		if a.toplevel then
			s.toplevel = bool(a.toplevel)
		end
		if a.movable then
			s.movable = bool(a.movable)
		end
		if a.clampedToScreen then
			s.clamped = bool(a.clampedToScreen)
		end
		if a.ignoreParentScale then
			s.ignoreParentScale = bool(a.ignoreParentScale)
		end
		if a.text then
			if s.kind == "FontString" then
				s.text = G[a.text] or a.text
			elseif s.isFrame and obj.SetText then
				ctx.post[#ctx.post + 1] = function()
					obj:SetText(G[a.text] or a.text)
				end
			end
		end
		if s.kind == "FontString" or s.kind == "Font" then
			setFontAttributes(obj, node)
		end
		if s.kind == "Texture" or s.kind == "MaskTexture" or s.kind == "Line" then
			if a.file then
				s.file = a.file
			end
			if a.atlas then
				obj:SetAtlas(a.atlas, bool(a.useAtlasSize))
			end
			local color = firstChild(node, "Color")
			if color then
				s.color =
					{ num(color.attr.r) or 1, num(color.attr.g) or 1, num(color.attr.b) or 1, num(color.attr.a) or 1 }
			end
			local tc = firstChild(node, "TexCoords")
			if tc then
				s.texCoord = {
					num(tc.attr.left) or 0,
					num(tc.attr.right) or 1,
					num(tc.attr.top) or 0,
					num(tc.attr.bottom) or 1,
				}
			end
		end
		local size = firstChild(node, "Size")
		if size then
			local x, y = dimensions(size)
			if x then
				s.width = x
			end
			if y then
				s.height = y
			end
		end
		if a.setAllPoints == "true" then
			ctx.post[#ctx.post + 1] = function()
				obj:SetAllPoints(s.parent)
			end
		end
		applyAnchors(obj, node, ctx, parent)
		local attrs = firstChild(node, "Attributes")
		if attrs and s.attributes then
			for _, at in ipairs(childrenNamed(attrs, "Attribute")) do
				local v = at.attr.value
				if at.attr.type == "number" then
					v = tonumber(v)
				elseif at.attr.type == "boolean" then
					v = v == "true"
				end
				s.attributes[at.attr.name] = v
			end
		end
		-- Regions.
		for _, layers in ipairs(childrenNamed(node, "Layers")) do
			for _, layer in ipairs(childrenNamed(layers, "Layer")) do
				local level = layer.attr.level or "ARTWORK"
				for _, child in ipairs(layer.children) do
					createChildRegion(child, obj, ctx, level, num(layer.attr.textureSubLevel))
				end
			end
		end
		for tag, setter in pairs(SPECIAL_REGIONS) do
			local child = firstChild(node, tag)
			if child and obj[setter] then
				local region = apply(child, obj, ctx, "Texture", tag == "HighlightTexture" and "HIGHLIGHT" or "ARTWORK")
				if #S[region].points == 0 then
					ctx.post[#ctx.post + 1] = function()
						if #S[region].points == 0 then
							region:SetAllPoints(obj)
						end
					end
				end
				obj[setter](obj, region)
			end
		end
		local buttonText = firstChild(node, "ButtonText")
		if buttonText and obj.SetFontString then
			local fs = apply(buttonText, obj, ctx, "FontString", "ARTWORK")
			if #S[fs].points == 0 then
				fs:SetPoint("CENTER")
			end
			obj:SetFontString(fs)
		end
		for _, tag in ipairs({ "NormalFont", "HighlightFont", "DisabledFont" }) do
			local f = firstChild(node, tag)
			if f and f.attr.style and obj["Set" .. tag .. "Object"] then
				local font = G[f.attr.style]
				if font then
					obj["Set" .. tag .. "Object"](obj, font)
				end
			end
		end
		if s.kind == "EditBox" then
			local fs = firstChild(node, "FontString")
			if fs and fs.attr.inherits then
				s.fontObject = G[fs.attr.inherits]
			end
		end
		-- Child frames.
		for _, frames in ipairs(childrenNamed(node, "Frames")) do
			for _, child in ipairs(frames.children) do
				apply(child, obj, ctx)
			end
		end
		local scrollChild = firstChild(node, "ScrollChild")
		if scrollChild then
			for _, child in ipairs(scrollChild.children) do
				local c = apply(child, obj, ctx)
				if c and obj.SetScrollChild then
					ctx.post[#ctx.post + 1] = function()
						obj:SetScrollChild(c)
					end
				end
			end
		end
		-- Animations.
		for _, anims in ipairs(childrenNamed(node, "Animations")) do
			for _, group in ipairs(childrenNamed(anims, "AnimationGroup")) do
				apply(group, obj, ctx, "AnimationGroup")
			end
		end
		if s.kind == "AnimationGroup" then
			for _, child in ipairs(node.children) do
				if Widgets.TYPES[child.tag] and Widgets.isA(child.tag, "Animation") or child.tag == "Animation" then
					apply(child, obj, ctx, child.tag)
				end
			end
			if a.looping then
				s.looping = a.looping
			end
		end
		if s.kind and Widgets.isA(s.kind, "Animation") then
			s.duration = num(a.duration) or s.duration
			s.order = num(a.order) or s.order
			s.startDelay = num(a.startDelay) or s.startDelay
			s.endDelay = num(a.endDelay) or s.endDelay
			s.childKey = a.childKey or a.targetKey or s.childKey
			for k, v in pairs(a) do
				if k ~= "parentKey" then
					s.props[k] = { n = 1, v }
				end
			end
		end
		-- Scripts.
		for _, scripts in ipairs(childrenNamed(node, "Scripts")) do
			for _, sn in ipairs(scripts.children) do
				local f = handlerFor(sn, ctx)
				if f and ctx.intrinsic then
					-- An intrinsic's handlers always run, before (default) or after the frame's own.
					s.intrinsic = s.intrinsic or {}
					s.intrinsic[sn.tag] = s.intrinsic[sn.tag] or {}
					local slot = sn.attr.intrinsicOrder == "postcall" and "post" or "pre"
					s.intrinsic[sn.tag][slot] = combine(s.intrinsic[sn.tag][slot], f, "append")
				elseif f or sn.attr.inherit then
					local name = sn.tag
					s.scripts = s.scripts or {}
					s.scriptTaint = s.scriptTaint or {}
					s.hooks = s.hooks or {}
					s.scripts[name] = combine(s.scripts[name], f, sn.attr.inherit or sn.attr.intrinsicOrder)
					s.scriptTaint[name] = ctx.taint
				end
			end
		end
	end

	-- Builds obj for an element node under parent: creates it, applies its templates and itself, and queues its
	-- OnLoad. kindOverride is used for region tags that carry a role (NormalTexture -> Texture).
	apply = function(node, parent, ctx, kindOverride, layer, sublevel)
		local kind, intrinsic = kindOf(node)
		kind = kindOverride or kind
		if node.tag == "Animation" then
			kind = "Animation"
		end
		if not Widgets.TYPES[kind] then
			if CHILD_ELEMENTS[node.tag] == nil and not T.templates[node.tag] then
				warn(string.format("%s:%s: unknown element <%s>", ctx.file, tostring(node.line), node.tag))
			end
			return nil
		end
		local templates = chain(node)
		if intrinsic then
			table.insert(templates, 1, intrinsic)
		end
		local name = node.attr.name
		local extra = { source = ctx.file }
		local obj = W.new(kind, name, parent, extra)
		local s = S[obj]
		if s.isRegion then
			s.layer, s.sublevel = layer or "ARTWORK", sublevel or 0
		end
		if kind == "AnimationGroup" and parent then
			local ps = S[parent]
			ps.animationGroups = ps.animationGroups or {}
			table.insert(ps.animationGroups, obj)
		elseif Widgets.isA(kind, "Animation") and parent then
			local ps = S[parent]
			ps.animations = ps.animations or {}
			table.insert(ps.animations, obj)
		end
		local parentKey, parentArray = node.attr.parentKey, node.attr.parentArray
		for _, t in ipairs(templates) do
			parentKey = parentKey or t.node.attr.parentKey
			parentArray = parentArray or t.node.attr.parentArray
		end
		if parent and parentKey then
			rawset(parent, parentKey, obj)
			s.parentKey = parentKey
		end
		if parent and parentArray then
			local arr = rawget(parent, parentArray) or {}
			rawset(parent, parentArray, arr)
			arr[#arr + 1] = obj
		end
		if kind == "FontString" then
			-- A font string's inherits may name a Font object rather than a template.
			for _, fname in ipairs(split(node.attr.inherits)) do
				local font = G[fname]
				if font and S[font] and S[font].kind == "Font" then
					W.copyFont(s, font)
					s.fontObject = font
				end
			end
		end
		for _, t in ipairs(templates) do
			local tctx = setmetatable({
				file = t.file,
				chunk = t.chunk,
				taint = t.taint,
				intrinsic = T.intrinsics[t.node.attr.name or ""] == t,
			}, { __index = ctx })
			applyNode(obj, t.node, tctx, parent)
		end
		applyNode(obj, node, ctx, parent)
		if (s.scripts and s.scripts.OnLoad) or (s.intrinsic and s.intrinsic.OnLoad) then
			ctx.loads[#ctx.loads + 1] = obj
		end
		return obj
	end

	local function newContext(file, chunk, taint)
		return { file = file, chunk = chunk, taint = taint, anchors = {}, loads = {}, post = {} }
	end

	local function finish(ctx)
		for _, f in ipairs(ctx.post) do
			local ok, err = pcall(f)
			if not ok then
				warn(err)
			end
		end
		ctx.post = {}
		finishAnchors(ctx)
		local loads = ctx.loads
		ctx.loads = {}
		for _, obj in ipairs(loads) do
			W.fire(obj, "OnLoad")
		end
	end

	-- Instantiates element `node` (from a loaded file) under parent and runs its OnLoads.
	local function instantiate(node, parent, file, chunk, taint)
		local ctx = newContext(file, chunk, taint)
		local obj = apply(node, parent, ctx)
		finish(ctx)
		return obj
	end

	---------------------------------------------------------------------------
	-- Public: CreateFrame, regions, animations.
	---------------------------------------------------------------------------
	local function inheritFrom(obj, templateList, parent)
		if not templateList or templateList == "" then
			return
		end
		local ctx = newContext("CreateFrame", "CreateFrame", Taint.current)
		for _, name in ipairs(split(templateList)) do
			local t = templateNode(name)
			if not t then
				error(string.format('CreateFrame(): Couldn\'t find inherited node "%s"', name), 3)
			end
			local list = chain(t.node)
			list[#list + 1] = t
			for _, tt in ipairs(list) do
				local tctx = setmetatable({
					file = tt.file,
					chunk = tt.chunk,
					taint = tt.taint,
					intrinsic = T.intrinsics[tt.node.attr.name or ""] == tt,
				}, { __index = ctx })
				applyNode(obj, tt.node, tctx, parent)
				local pk = tt.node.attr.parentKey
				if pk and parent then
					rawset(parent, pk, obj)
				end
			end
		end
		local s = S[obj]
		if (s.scripts and s.scripts.OnLoad) or (s.intrinsic and s.intrinsic.OnLoad) then
			ctx.loads[#ctx.loads + 1] = obj
		end
		finish(ctx)
	end

	function T.createFrame(kind, name, parent, templateList, id)
		if type(kind) ~= "string" then
			error("CreateFrame(): bad frame type", 3)
		end
		local resolved = Widgets.ALIASES[kind] or kind
		if not Widgets.TYPES[resolved] then
			-- The client accepts any capitalisation ("FRAME", "button").
			for typeName in pairs(Widgets.TYPES) do
				if typeName:lower() == kind:lower() then
					resolved = typeName
				end
			end
			for aliasName, alias in pairs(Widgets.ALIASES) do
				if aliasName:lower() == kind:lower() then
					resolved = alias
				end
			end
		end
		local intrinsic = T.intrinsics[kind]
		if not intrinsic then
			for iname, entry in pairs(T.intrinsics) do
				if iname:lower() == kind:lower() then
					intrinsic = entry
				end
			end
		end
		if intrinsic then
			resolved = intrinsic.kind
		end
		if not Widgets.TYPES[resolved] or not Widgets.isA(resolved, "Frame") then
			error(string.format("CreateFrame(): Unknown frame type '%s'", kind), 3)
		end
		if type(parent) == "string" then
			parent = G[parent]
		end
		local obj = W.new(resolved, name, parent, { source = "CreateFrame" })
		if id then
			S[obj].frameID = id
		end
		if intrinsic then
			templateList = intrinsic.name .. (templateList and ("," .. templateList) or "")
		end
		inheritFrom(obj, templateList, parent)
		return obj
	end

	function T.createRegion(kind, name, parent, templateList, layer, sublevel)
		local obj = W.new(kind, name, parent, { source = "Create" .. kind })
		local s = S[obj]
		s.layer, s.sublevel = layer or "ARTWORK", sublevel or 0
		if templateList then
			for _, tname in ipairs(split(templateList)) do
				local font = G[tname]
				if kind == "FontString" and font and S[font] and S[font].kind == "Font" then
					W.copyFont(s, font)
					s.fontObject = font
				elseif templateNode(tname) then
					inheritFrom(obj, tname, parent)
				else
					error(string.format('Create%s(): Couldn\'t find inherited node "%s"', kind, tname), 3)
				end
			end
		end
		return obj
	end

	function T.createAnimationGroup(parent, name, templateList)
		local obj = W.new("AnimationGroup", name, parent, { source = "CreateAnimationGroup" })
		local ps = S[parent]
		ps.animationGroups = ps.animationGroups or {}
		table.insert(ps.animationGroups, obj)
		if templateList then
			inheritFrom(obj, templateList, parent)
		end
		return obj
	end

	function T.createAnimation(group, kind, name, templateList)
		kind = kind or "Animation"
		if not Widgets.TYPES[kind] then
			kind = "Animation"
		end
		local obj = W.new(kind, name, group, { source = "CreateAnimation" })
		local gs = S[group]
		gs.animations = gs.animations or {}
		table.insert(gs.animations, obj)
		if templateList then
			inheritFrom(obj, templateList, group)
		end
		return obj
	end

	-- C_XMLUtil.GetTemplateInfo: a template's widget type, size (its own, else its templates') and KeyValues.
	function T.templateInfo(name)
		local t = templateNode(name)
		if not t then
			return nil
		end
		local list = chain(t.node)
		list[#list + 1] = t
		local width, height = 0, 0
		local keyValues = {}
		for _, tt in ipairs(list) do
			local size = firstChild(tt.node, "Size")
			if size then
				local x, y = dimensions(size)
				width, height = x or width, y or height
			end
			for _, kvs in ipairs(childrenNamed(tt.node, "KeyValues")) do
				for _, kv in ipairs(childrenNamed(kvs, "KeyValue")) do
					keyValues[#keyValues + 1] = {
						key = kv.attr.key,
						keyType = kv.attr.keyType or "string",
						type = kv.attr.type or "string",
						value = kv.attr.value,
					}
				end
			end
		end
		return {
			type = t.kind,
			width = width,
			height = height,
			keyValues = keyValues,
			inherits = t.node.attr.inherits,
			sourceLocation = t.file,
		}
	end
	sim.impl["C_XMLUtil.GetTemplateInfo"] = function(name)
		return T.templateInfo(name)
	end

	function T.createFont(name)
		local obj = W.new("Font", name, nil, { source = "CreateFont" })
		S[obj].shown = true
		return obj
	end

	---------------------------------------------------------------------------
	-- Loading files.
	---------------------------------------------------------------------------
	-- Loads a Lua file as part of addon `folder` (chunk name "<folder>/<relative path>"), passing (name, ns).
	function T.loadLua(path, chunkName, ...)
		local text = readFile(path)
		if not text then
			warn("missing file " .. path)
			return false
		end
		local chunk, err = T.compile(text, chunkName)
		if not chunk then
			sim.reportError(err, "", nil)
			return false
		end
		local args = { ... }
		local n = select("#", ...)
		local ok = sim.run(function()
			local result = chunk(unpack(args, 1, n))
			if result ~= nil then
				-- A file that returns a value is a module import() can find.
				local folder, file = chunkName:match("^([^/]+)/(.-)%.lua$")
				if folder then
					sim.modules[folder] = sim.modules[folder] or {}
					sim.modules[folder][file:match("([^/]+)$")] = result
				end
			end
		end)
		return ok
	end

	local function loadFont(node, ctx)
		local name = node.attr.name
		if not name then
			return
		end
		local font = G[name]
		if not (font and S[font] and S[font].kind == "Font") then
			font = T.createFont(name)
		end
		for _, iname in ipairs(split(node.attr.inherits)) do
			local parentFont = G[iname]
			if parentFont and S[parentFont] then
				W.copyFont(S[font], parentFont)
			end
		end
		setFontAttributes(font, node)
		local shadow = firstChild(node, "Shadow")
		if shadow then
			S[font].shadowOffset = { dimensions(firstChild(shadow, "Offset")) }
		end
		local _ = ctx
	end

	local function loadFontFamily(node, ctx)
		local name = node.attr.name
		local roman
		for _, member in ipairs(childrenNamed(node, "Member")) do
			if member.attr.alphabet == "roman" then
				roman = firstChild(member, "Font")
			end
		end
		if name and roman then
			roman.attr.name = name
			loadFont(roman, ctx)
		end
	end

	-- Loads an XML file of addon `folder`. `dir` is the file's directory on disk and `rel` its path in the addon.
	function T.loadXML(path, folder, rel, ...)
		local text = readFile(path)
		if not text then
			warn("missing file " .. path)
			return false
		end
		local root = xmlCache[text]
		if not root then
			local ok
			ok, root = pcall(XML.parse, text, path)
			if not ok then
				warn(root)
				return false
			end
			xmlCache[text] = root
		end
		if not root then
			return true
		end
		local dir = path:match("^(.*)[/\\]") or "."
		local relDir = rel:match("^(.*)[/\\]")
		local chunk = folder .. "/" .. rel:gsub("\\", "/")
		local addonArgs = { ... }
		local nargs = select("#", ...)
		local function relative(file)
			file = file:gsub("\\", "/")
			return dir .. "/" .. file, (relDir and (relDir .. "/") or "") .. file
		end
		for _, node in ipairs(root.children) do
			local tag = node.tag
			if tag == "Script" then
				if node.attr.file then
					local p, r = relative(node.attr.file)
					T.loadLua(p, folder .. "/" .. r:gsub("\\", "/"), unpack(addonArgs, 1, nargs))
				elseif node.text then
					local f, err = T.compile(node.text, chunk, node.textLine)
					if f then
						sim.run(function()
							f(unpack(addonArgs, 1, nargs))
						end)
					else
						sim.reportError(err, "", nil)
					end
				end
			elseif tag == "Include" then
				local p, r = relative(node.attr.file)
				T.loadXML(p, folder, r, unpack(addonArgs, 1, nargs))
			elseif tag == "Font" then
				loadFont(node, { file = path })
			elseif tag == "FontFamily" then
				loadFontFamily(node, { file = path })
			else
				local kind = kindOf(node)
				if Widgets.TYPES[kind] then
					local entry = { node = node, file = path, chunk = chunk, taint = Taint.current, kind = kind }
					if node.attr.intrinsic == "true" then
						entry.name = node.attr.name
						T.intrinsics[node.attr.name] = entry
						T.templates[node.attr.name] = entry
					elseif node.attr.virtual == "true" then
						if node.attr.name then
							T.templates[node.attr.name] = entry
						end
					else
						local parent = node.attr.parent and G[node.attr.parent]
						sim.run(function()
							instantiate(node, parent, path, chunk, Taint.current)
						end)
					end
				elseif tag ~= "Ui" then
					warn(string.format("%s: unknown top-level <%s>", path, tag))
				end
			end
		end
		return true
	end

	return T
end

return M
