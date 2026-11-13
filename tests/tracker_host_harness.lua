-- Shared stubs for the tracker host specs: one private host over a stubbed native tracker.
local harness = {}

function harness.new(options)
	options = options or {}
	local checks = 0
	local function check(value, message)
		assert(value, message)
		checks = checks + 1
	end
	local function noop() end
	local timers, readyFn, frames, releases, menus = {}, nil, {}, {}, {}
	local animations, released = 0, 0
	local textures = {}
	local initializationEvents
	local combat = false
	local parent
	local nativeAnchorPoint = options.nativeAnchorPoint or "TOPRIGHT"
	local function frame()
		local f = { width = 250, height = 0, scripts = {} }
		function f:SetPoint(...)
			self.point = { ... }
		end
		function f.GetPoint(self)
			return unpack(self.point or { nativeAnchorPoint, parent, nativeAnchorPoint, 0, -100 })
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
		function f:GetBottom()
			return (self:GetTop() or 0) - self:GetHeight()
		end
		function f:GetEffectiveScale()
			return self.effectiveScale or (self.scale or 1)
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
			return self.right or self:GetLeft() + self:GetWidth()
		end
		function f.GetBottom(self)
			return self.bottom or self:GetTop() - self:GetHeight()
		end
		function f.GetCenter(self)
			return (self:GetLeft() + self:GetRight()) / 2, (self:GetTop() + self:GetBottom()) / 2
		end
		function f:IsShown()
			return self.shown ~= false
		end
		function f:GetAlpha()
			return self.alpha or 1
		end
		function f:SetScript(event, fn)
			self.scripts[event] = fn
		end
		-- As the client's HookScript: the frame's own handler runs first, then the hook.
		function f:HookScript(event, fn)
			local original = self.scripts[event]
			if not original then
				self.scripts[event] = fn
				return
			end
			self.scripts[event] = function(...)
				original(...)
				fn(...)
			end
		end
		function f:EnableMouse(value)
			self.mouse = value
		end
		function f:SetParent(owner)
			self.parent = owner
		end
		-- Effective visibility, the way the client reports it: the frame and every ancestor shown.
		function f:IsVisible()
			local owner = self
			while owner do
				if not owner:IsShown() then
					return false
				end
				owner = owner.GetParent and owner:GetParent() or owner.parent
			end
			return true
		end
		function f:GetParent()
			return self.parent
		end
		function f:ClearAllPoints()
			self.point = nil
		end
		function f:SetAlpha(value)
			self.alpha = value
		end
		function f:SetScrollChild(child)
			self.scrollChild = child
			child.parent = self
		end
		function f:GetScrollChild()
			return self.scrollChild
		end
		function f:SetVerticalScroll(value)
			self.verticalScroll = value
		end
		function f:GetVerticalScroll()
			return self.verticalScroll or 0
		end
		function f:EnableMouseWheel(value)
			self.mouseWheel = value
		end
		-- The client's MinimalScrollBar is an EventFrame on ScrollBarMixin: percentages and a callback, never a
		-- Slider value. A stub that still offered SetValue would hide exactly the mistake this harness checks.
		function f:RegisterCallback(event, callback, owner)
			self.callbacks = self.callbacks or {}
			self.callbacks[event] = { callback = callback, owner = owner }
		end
		function f:SetVisibleExtentPercentage(value)
			self.visibleExtent = value
		end
		function f:GetVisibleExtentPercentage()
			return self.visibleExtent or 0
		end
		function f:SetScrollPercentage(value)
			self.scrollPercentage = value
			local entry = self.callbacks and self.callbacks.OnScroll
			if entry then
				entry.callback(entry.owner, value)
			end
		end
		function f:GetScrollPercentage()
			return self.scrollPercentage or 0
		end
		function f:SetScrollAllowed(value)
			self.scrollAllowed = value
		end
		function f:IsScrollAllowed()
			return self.scrollAllowed ~= false
		end
		function f:RegisterEvent(event)
			self.events = self.events or {}
			self.events[event] = true
		end
		f.SetMovable, f.RegisterForDrag = noop, noop
		f.clamped = true
		function f:SetClampedToScreen(value)
			self.clamped = value
		end
		function f:IsClampedToScreen()
			return self.clamped
		end
		function f.CreateFontString(_)
			return { SetPoint = noop, SetText = noop, SetShown = noop }
		end
		function f.CreateTexture(_)
			local texture = { points = {} }
			function texture:SetPoint(...)
				self.points[#self.points + 1] = { ... }
			end
			function texture:SetAtlas(name)
				self.atlas = name
			end
			function texture:SetVertexColor(r, g, b, a)
				self.r, self.g, self.b, self.a = r, g, b, a
			end
			function texture:SetShown(value)
				self.shown = value
			end
			texture.Show = function(self)
				self.shown = true
			end
			texture.Hide = function(self)
				self.shown = false
			end
			texture.IsShown = function(self)
				return self.shown ~= false
			end
			textures[#textures + 1] = texture
			return texture
		end
		function f:SetShown(value)
			if value then
				self:Show()
			else
				self:Hide()
			end
		end
		function f:StartMoving()
			self.moving = true
		end
		function f:StopMovingOrSizing()
			self.moving = false
		end
		f.Show = function(self)
			self.shown = true
			local handler = self.scripts.OnShow
			if handler then
				handler(self)
			end
		end
		f.Hide = function(self)
			self.shown = false
			local handler = self.scripts.OnHide
			if handler then
				handler(self)
			end
		end
		frames[#frames + 1] = f
		return f
	end
	local native = frame()
	local minimap = frame()
	minimap.left, minimap.right, minimap.top, minimap.bottom, minimap.shown = 900, 1100, 700, 500, false
	parent = frame()
	native.parent = parent
	parent.width = 1200
	native.point = { nativeAnchorPoint, parent, nativeAnchorPoint, 0, -100 }
	native.height = 300
	parent:SetHeight(1080)
	native.effectiveScale, parent.effectiveScale = 1.25, 1
	local nativeHeader = frame()
	nativeHeader.shown = options.headerShown == true
	nativeHeader.parent = native
	nativeHeader.point = { "TOPLEFT", native, "TOPLEFT", 0, 0 }
	local minimizeButton = frame()
	nativeHeader.MinimizeButton = minimizeButton
	native.Header = nativeHeader
	native.headerWanted = options.headerShown == true
	-- The native container anchors this to the bottom of its last shown module: here 100 px of quests below its top.
	native.NineSlice = {
		bottom = 540,
		GetBottom = function(self)
			return self.bottom
		end,
		GetCenter = function()
			return native:GetCenter()
		end,
		GetEffectiveScale = function()
			return native:GetEffectiveScale()
		end,
	}
	-- Blizzard's tracker re-anchors its header at the end of every update.
	function native.UpdateHeaderPosition()
		nativeHeader:SetPoint("TOPLEFT", native, "TOPLEFT", 0, 0)
	end
	function native:ShouldShowHeader()
		return self.headerWanted and self:IsShown()
	end
	-- Mirrors the client update order: header visibility, objective layout, then unconditional header re-anchor.
	function native:UpdateOrder()
		if not self:ShouldShowHeader() then
			nativeHeader:Hide()
		else
			nativeHeader:Show()
		end
		self:UpdateHeaderPosition()
		return self:ShouldShowHeader()
	end
	-- The managed-frame layout calls this after it re-anchors the frame to its saved slot.
	function native.UpdateHeight() end
	-- A native tracker update re-anchors the frame to its saved slot and finishes at the header.
	function native.RestoreSavedAnchor()
		native:SetPoint("TOPRIGHT", parent, "TOPRIGHT", 0, -100)
		native:UpdateHeaderPosition()
	end
	local ns = options.ns or {
		L = setmetatable({}, {
			__index = function(_, key)
				return key
			end,
		}),
	}
	local hostSettings = options.hostSettings or { attached = true }
	function ns.TrackerHostSettings()
		return hostSettings
	end
	local forbidden = setmetatable({}, {
		__index = function(_, key)
			error("native manager accessed: " .. key)
		end,
	})
	local callbacks = {}
	local eventRegistry = {
		RegisterCallback = function(_, event, callback, owner)
			callbacks[event] = callbacks[event] or {}
			callbacks[event][#callbacks[event] + 1] = { callback = callback, owner = owner }
		end,
		TriggerEvent = function(_, event, ...)
			for _, entry in ipairs(callbacks[event] or {}) do
				entry.callback(entry.owner, ...)
			end
		end,
	}
	-- The shared context menu, recorded so a spec can read back what a click offered. An entry with no callback and
	-- entries of its own is a submenu, as inserting elements into an element description makes one in the client.
	local function captureMenu(owner, generator)
		local root = ns.NewMenuDescription("root")
		generator(owner, root)
		local function Adapt(description)
			for _, entry in ipairs(description.entries) do
				entry.callback, entry.setSelected = entry.onClick, entry.onClick
				if #entry.entries > 0 then
					entry.submenu = entry
					Adapt(entry)
				end
			end
		end
		Adapt(root)
		local menu = { owner = owner, entries = {} }
		for _, entry in ipairs(root.entries) do
			if entry.kind == "title" then
				menu.title = entry.text
			else
				menu.entries[#menu.entries + 1] = entry
			end
		end
		menus[#menus + 1] = menu
		return menu
	end
	ns.ContextMenu = captureMenu
	local editMode = { active = false, shown = false, scripts = {} }
	function editMode:IsEditModeActive()
		return self.active
	end
	function editMode:IsShown()
		return self.shown
	end
	function editMode:HookScript(kind, fn)
		self.scripts[kind] = fn
	end
	local env
	env = setmetatable({
		ObjectiveTrackerManager = forbidden,
		InCombatLockdown = function()
			return combat
		end,
		ObjectiveTrackerFrame = native,
		Minimap = minimap,
		UIParent = parent,
		CreateFrame = function(kind, _, _, template)
			local f = frame()
			f.kind, f.template = kind, template
			return f
		end,
		C_Timer = {
			After = function(_, fn)
				timers[#timers + 1] = fn
			end,
		},
		EventUtil = {
			ContinueAfterAllEvents = function(fn, ...)
				initializationEvents = { ... }
				readyFn = fn
			end,
		},
		EventRegistry = eventRegistry,
		EditModeManagerFrame = editMode,
		C_XMLUtil = {
			GetTemplateInfo = function()
				return { type = "Frame" }
			end,
		},
		-- The client's menu API is never used: the shared context menu is what a section opens. A spec that still calls
		-- MenuUtil would catch the old path here.
		MenuUtil = {
			CreateContextMenu = function()
				error("native menu acquisition can assert on this client build")
			end,
		},
		Mixin = function(target, mixin)
			for key, value in pairs(mixin) do
				target[key] = value
			end
		end,
		hooksecurefunc = function(target, name, callback)
			assert(target ~= env.ObjectiveTrackerFrame, "native tracker methods must remain secure")
			local original = target[name]
			target[name] = function(...)
				local result = original(...)
				callback(...)
				return result
			end
		end,
		CreateFramePoolCollection = function()
			return {
				GetOrCreatePool = function(_, _, _, template)
					return {
						Acquire = function()
							local f = frame()
							if template == "AnimBlock" and env.ObjectiveTrackerAnimBlockMixin then
								env.Mixin(f, env.ObjectiveTrackerAnimBlockMixin)
							end
							if template == "Block" then
								if env.ObjectiveTrackerBlockMixin then
									env.Mixin(f, env.ObjectiveTrackerBlockMixin)
								end
								f.usedLines = {}
								f.GetLine = function()
									error("native GetLine retained")
								end
								function f:GetExistingLine(key)
									return self.usedLines[key]
								end
							end
							return f, true
						end,
					},
						true
				end,
				Release = function(_, f)
					releases[f] = true
					released = released + 1
				end,
			}
		end,
	}, { __index = _G })
	env._G = env
	local nativeRoot = os.getenv("TRACKER_UI_ROOT")
	if nativeRoot then
		env.CreateFromMixins = function(...)
			local result = {}
			for _, mixin in ipairs({ ... }) do
				env.Mixin(result, mixin)
			end
			return result
		end
		env.ObjectiveTrackerSlidingMixin, env.ObjectiveTrackerLineMixin = {}, {}
		env.EnumUtil = {
			MakeEnum = function(...)
				local result = {}
				for i, name in ipairs({ ... }) do
					result[name] = i
				end
				return result
			end,
		}
		env.table = setmetatable({
			wipe = function(t)
				for k in pairs(t) do
					t[k] = nil
				end
			end,
		}, { __index = table })
		for _, name in ipairs({ "Module", "Block", "AnimTemplates" }) do
			setfenv(assert(loadfile(nativeRoot .. "/Blizzard_ObjectiveTracker" .. name .. ".lua")), env)()
		end
	end

	local ctx = {
		env = env,
		ns = ns,
		hostSettings = hostSettings,
		frames = frames,
		textures = textures,
		releases = releases,
		native = native,
		parent = parent,
		minimap = minimap,
		nativeHeader = nativeHeader,
		updateOrder = function()
			return native:UpdateOrder()
		end,
		headerShown = function()
			return native:ShouldShowHeader()
		end,
		minimizeButton = minimizeButton,
		eventRegistry = eventRegistry,
		editMode = editMode,
		menus = menus,
		check = check,
		checks = function()
			return checks
		end,
		ready = function()
			readyFn()
		end,
		initializationEvents = function()
			return initializationEvents
		end,
		pending = function()
			return #timers
		end,
		drain = function()
			local pending = timers
			timers = {}
			for _, fn in ipairs(pending) do
				fn()
			end
		end,
		setCombat = function(value)
			combat = value
		end,
		inCombat = function()
			return combat
		end,
		setNativeAnchorPoint = function(value)
			nativeAnchorPoint = value
		end,
	}
	-- Delivers a client event to the host only when the host registered it, as the client does.
	function ctx.fire(event)
		local host = ctx.host
		if host.events and host.events[event] then
			host.scripts.OnEvent(host, event)
		end
	end
	function ctx.loadHost(namespace, path)
		path = path or "UI/TrackerHost.lua"
		setfenv(assert(loadfile("UI/ContextMenu.lua")), env)("Test", namespace)
		namespace.ContextMenu = captureMenu
		setfenv(assert(loadfile("UI/TrackerLock.lua")), env)("Test", namespace) -- the grip, before the host
		setfenv(assert(loadfile("UI/TrackerOrder.lua")), env)("Test", namespace) -- the section order
		setfenv(assert(loadfile(path)), env)("Test", namespace)
	end
	function ctx.module(order, headerClick, show)
		local m = frame()
		m.uiOrder, m.ContentsFrame, m.lineTemplate = order, frame(), "Line"
		m.contentHeight = 80
		m.Header = frame()
		m.Header.Text = {
			text = "",
			SetText = function(self, value)
				self.text = value
			end,
			GetText = function(self)
				return self.text
			end,
		}
		if headerClick then
			m.Header:SetScript("OnMouseUp", headerClick)
		end
		function m:SetContainer(container)
			-- Blizzard's template method registers modules with the native tracker manager.
			env.ObjectiveTrackerManager:SetModuleContainer(self, container)
		end
		function m:Update(available)
			self.available, self.updates = available, (self.updates or 0) + 1
			self.availableHeight = available
		end
		function m.GetContentsHeight(self)
			return math.min(self.contentHeight, self.availableHeight or self.contentHeight)
		end
		function m.IsTruncated(self)
			return self.contentHeight > (self.availableHeight or math.huge)
		end
		ctx.ns.TrackerHost.Attach(m, show)
		return m
	end
	-- A section driven by Blizzard's own module mixin, so a spec sees EndLayout's real work: the header's add
	-- animation and FreeUnusedBlocks releasing the block. Only available when the native tracker source is loaded.
	function ctx.nativeModule(order)
		local moduleMixin = env.ObjectiveTrackerModuleMixin
		if not moduleMixin then
			return nil
		end
		local m = frame()
		env.Mixin(m, moduleMixin)
		m.uiOrder, m.ContentsFrame = order, frame()
		m.blockTemplate, m.lineTemplate = "Block", "Line"
		m.Header = frame()
		env.Mixin(m.Header, env.ObjectiveTrackerModuleHeaderMixin)
		m.Header.MinimizeButton = frame()
		m.Header.AddAnim = {
			Restart = function()
				animations = animations + 1
			end,
		}
		function m:LayoutContents()
			local block = self:GetBlock("objective")
			block.height = 80
			self:LayoutBlock(block)
		end
		m:OnLoad()
		ctx.ns.TrackerHost.Attach(m)
		return m
	end
	function ctx.headerAnimations()
		return animations
	end
	function ctx.blocksReleased()
		return released
	end
	function ctx.probe()
		for _, f in ipairs(frames) do
			if f.point and f.point[2] == native and f.scripts.OnSizeChanged then
				return f
			end
		end
	end
	-- A module shaped like Blizzard's own, with a real block chain, so a spec can see the shared scroll wrapper: the
	-- cap, the viewport, the bar and the block-snapped offsets. It does not load Blizzard's source.
	function ctx.scrollModule(order, count, blockHeight, maxHeight)
		local m = frame()
		m.uiOrder = order
		m.headerHeight = 25
		m.fromHeaderOffsetY = -10
		m.fromBlockOffsetY = -10
		m.bottomSpacing = 0
		m.heightModifiers = {}
		m.trackerMaxHeight = maxHeight
		m.Header = frame()
		m.ContentsFrame = frame()
		m.lineTemplate = "Line"
		m.count, m.scrollChanges = count, 0
		function m:OnScrollChanged()
			self.scrollChanges = self.scrollChanges + 1
		end
		function m.MarkDirty()
			ctx.host:MarkDirty()
		end
		function m.Update(self, available)
			self.available, self.updates = available, (self.updates or 0) + 1
			self.firstContentsWidth = self.firstContentsWidth or self.ContentsFrame:GetWidth()
			self:BeginLayout()
			self.contentsHeight = self.headerHeight
			local first, last
			for index = 1, self.count do
				local block = frame()
				block.id, block.height = index, blockHeight
				if last then
					last.nextBlock = block
				else
					first = block
				end
				last = block
				self.contentsHeight = self.contentsHeight + blockHeight + 10
			end
			self.firstBlock, self.lastBlock = first, last
			self:UpdateHeight()
		end
		function m.UpdateHeight(self)
			self:SetHeight(self.contentsHeight)
		end
		function m.GetContentsHeight(self)
			return self.contentsHeight
		end
		function m.IsTruncated()
			return false
		end
		function m.CanFitBlock()
			return true
		end
		function m.BeginLayout() end
		ctx.ns.TrackerHost.Attach(m)
		return m
	end
	ctx.loadHost(ns)
	ctx.host, ctx.grip = frames[6], frames[7]
	ctx.first, ctx.second = ctx.module(1), ctx.module(2)
	if not options.deferReady then
		ctx.ready()
		ctx.drain()
	end
	return ctx
end

return harness
