-- Shared stubs for the tracker host specs: one private host on a stubbed UIParent, and a native tracker it only names
-- as an anchor.
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
	-- The native tracker's geometry, which only the spec reads and moves. A frame anchored to the native tracker
	-- resolves through it, as the engine resolves an anchor, so the host never has to read the tracker itself.
	local native
	-- `line` is the bottom of its last visible line, where its NineSlice ends; `shown` false hides it.
	local nativeRect = { left = 1200 - 260, top = 880, width = 260, height = 300, line = 880 - 120, shown = true }
	local function Along(name, low, size)
		if name:find("LEFT") or name:find("BOTTOM") then
			return low
		elseif name:find("RIGHT") or name:find("TOP") then
			return low + size
		end
		return low + size / 2
	end
	-- The frame's left and top when its one point names the native tracker, nil otherwise.
	local function Anchored(self)
		local p = self.point
		if not p or p[2] ~= native then
			return nil
		end
		local x = Along(p[3]:gsub("TOP", ""):gsub("BOTTOM", ""), nativeRect.left, nativeRect.width) + (p[4] or 0)
		local y = Along(p[3]:gsub("LEFT", ""):gsub("RIGHT", ""), nativeRect.top - nativeRect.height, nativeRect.height)
			+ (p[5] or 0)
		local horizontal = p[1]:gsub("TOP", ""):gsub("BOTTOM", "")
		local vertical = p[1]:gsub("LEFT", ""):gsub("RIGHT", "")
		local left = x - (Along(horizontal, 0, self:GetWidth()))
		local top = y + self:GetHeight() - Along(vertical, 0, self:GetHeight())
		return left, top
	end
	local function frame()
		local f = { width = 250, height = 0, scripts = {} }
		function f:SetPoint(...)
			self.point = { ... }
			self.points = self.points or {}
			self.points[(...)] = self.point
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
			local _, top = Anchored(self)
			return self.top or top or 640
		end
		-- As in the client, a scroll child has no rect in the frame its ScrollFrame takes it, and a frame hung by its
		-- top alone (`topOnly`) has none at height 0, which the client reads as no height (#795).
		local function Unplaced(self)
			return self.unplaced or (self.topOnly and (self.height or 0) == 0)
		end
		function f.GetLeft(self)
			if Unplaced(self) then
				return nil
			end
			return self.left or Anchored(self) or 0
		end
		function f.GetRight(self)
			if Unplaced(self) then
				return nil
			end
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
			self.point, self.points = nil, nil
		end
		function f:GetNumPoints()
			return self.point and 1 or 0
		end
		function f:SetAlpha(value)
			self.alpha = value
		end
		-- As the client: a scroll child has no rect in the frame it is set, even after UpdateScrollChildRect (#795).
		function f:SetScrollChild(child)
			self.scrollChild = child
			child.parent = self
			child.unplaced = true
		end
		function f:SetClipsChildren(value)
			self.clipsChildren = value
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
		f.SetMovable = noop
		function f:RegisterForDrag(button)
			self.dragButton = button
		end
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
	-- The client's tracker exists, which says its section template loaded, and the column may name it as an anchor. The
	-- host may read where it is and where its last line ends, and nothing else: any other field, a write or a hook (its
	-- HookScript, SetPoint or any setter) fails the spec.
	local function ReadOnly(name, reads)
		return setmetatable({}, {
			__index = function(_, key)
				local value = reads[key]
				if value == nil then
					error("the host read the native " .. name .. ": " .. tostring(key))
				end
				return value
			end,
			__newindex = function(_, key)
				error("the host wrote the native " .. name .. ": " .. tostring(key))
			end,
		})
	end
	local function NativeScale()
		return nativeRect.scale or 1
	end
	local nineSlice = ReadOnly("tracker NineSlice", {
		GetBottom = function()
			return nativeRect.line
		end,
		GetEffectiveScale = NativeScale,
	})
	native = ReadOnly("tracker", {
		NineSlice = nineSlice,
		GetLeft = function()
			return nativeRect.left
		end,
		GetTop = function()
			return nativeRect.top
		end,
		GetEffectiveScale = NativeScale,
		IsShown = function()
			return nativeRect.shown
		end,
		IsCollapsed = function()
			return nativeRect.collapsed == true
		end,
		Header = ReadOnly("tracker header", {
			GetBottom = function()
				return nativeRect.header
			end,
			GetEffectiveScale = NativeScale,
		}),
	})
	parent = frame()
	parent.width = 1200
	parent:SetHeight(1080)
	parent.effectiveScale = 1
	local ns = options.ns or {
		L = setmetatable({}, {
			__index = function(_, key)
				return key
			end,
		}),
	}
	-- A table already past the one-time move off the quest tracker, pinned left of it; a spec covers the migration and
	-- the place under the tracker.
	local hostSettings = options.hostSettings or { attached = false, placement = "left" }
	function ns.TrackerHostSettings()
		return hostSettings
	end
	local forbidden = setmetatable({}, {
		__index = function(_, key)
			error("native manager accessed: " .. key)
		end,
	})
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
	local env
	env = setmetatable({
		ObjectiveTrackerManager = forbidden,
		InCombatLockdown = function()
			return combat
		end,
		ObjectiveTrackerFrame = native,
		UIParent = parent,
		CreateFrame = function(kind, _, owner, template)
			local f = frame()
			f.kind, f.template, f.createdParent = kind, template, owner
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
		EventRegistry = { RegisterCallback = noop },
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
		nativeRect = nativeRect,
		parent = parent,
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
		-- The game's quest list ends at `line`, as a quest added, completed or collapsed leaves it: the host's probe,
		-- which spans from the screen's bottom to that line, changes size.
		moveLine = function(line)
			nativeRect.line = line
			for _, f in ipairs(frames) do
				if f.createdParent == parent and f.scripts.OnSizeChanged then
					f.scripts.OnSizeChanged(f)
				end
			end
		end,
		-- The game's tracker shows or hides, which its child frames hear.
		showTracker = function(shown)
			nativeRect.shown = shown
			for _, f in ipairs(frames) do
				local handler = f.createdParent == native and f.scripts[shown and "OnShow" or "OnHide"]
				if handler then
					handler(f)
				end
			end
		end,
		inCombat = function()
			return combat
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
		-- Start work runs at once, as in the unwrapped standalone.
		namespace.AtStart = namespace.AtStart or function(work)
			work()
		end
		setfenv(assert(loadfile("Core/Open.lua")), env)("Test", namespace)
		path = path or "UI/TrackerHost.lua"
		setfenv(assert(loadfile("UI/ContextMenu.lua")), env)("Test", namespace)
		namespace.ContextMenu = captureMenu
		setfenv(assert(loadfile("UI/TrackerLock.lua")), env)("Test", namespace) -- the header drag, before the host
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
	-- A left-button press on a section header that drags, as the client sends it; `release` lets go.
	function ctx.drag(header, release)
		header.scripts.OnMouseDown(header, "LeftButton")
		header.scripts.OnDragStart(header)
		if release then
			release()
			header.scripts.OnDragStop(header)
			header.scripts.OnMouseUp(header, "LeftButton")
		end
	end
	-- Where the frame's top right corner resolves, with its anchors.
	function ctx.topRight(target)
		return target:GetRight(), target:GetTop()
	end
	-- Saves a dragged position that leaves exactly `room` units for the sections under the column's top.
	function ctx.room(room)
		hostSettings.x, hostSettings.y = 0, room - parent:GetHeight()
		ctx.host:MarkDirty()
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
		m.ContentsFrame.topOnly = true
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
			if self.firstContentsLeft == nil then
				self.firstContentsLeft = self.ContentsFrame:GetLeft() or false
			end
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
	-- Globals a spec needs before the host file runs, such as a loader that already saw the world events.
	for key, value in pairs(options.env or {}) do
		env[key] = value
	end
	ctx.loadHost(ns)
	ctx.host = frames[2]
	ctx.first, ctx.second = ctx.module(1), ctx.module(2)
	if not options.deferReady then
		ctx.ready()
		ctx.drain()
	end
	return ctx
end

return harness
