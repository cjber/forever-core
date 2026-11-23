---@type string, ForeverTrackerNamespace
local _, ns = ...

---@class ForeverTrackerModule : Frame
---@field uiOrder? number
---@field parentContainer? Frame
---@field Header? Frame
---@field headerMenu? boolean
---@field show? ForeverTrackerShowSetting the section's own show switch, when it has one
---@field GetContextMenuParent fun(self: ForeverTrackerModule): Frame
---@field SetContainer fun(self: ForeverTrackerModule, container: Frame)
---@field IsTruncated fun(self: ForeverTrackerModule): boolean
---@field trackerMenu? fun(target: ForeverTrackerTarget, menu: ForeverTrackerMenuBuilder) the declarative menu contract
---@field trackerClick? fun(target: ForeverTrackerTarget, button: string) the declarative click contract
---@field trackerClickHint? fun(target: ForeverTrackerTarget): string? the localized click action
---@field trackerClickHint? fun(target: ForeverTrackerTarget): string? the localized action name shown in the block
-- tooltip
---@field OnBlockHeaderClick? fun(self: ForeverTrackerModule, block: any, button: string)

---@class ForeverTrackerSettings
---@field stayUnder? boolean keep the column under the tracker instead of moving left when space is short

---@class ForeverTrackerHostAPI
---@field GetStayUnder fun(): boolean
---@field SetStayUnder fun(value: boolean)

-- The client's own objective tracker. Its presence says Blizzard_ObjectiveTracker loaded, which defines the section
-- template every Forever section is built from, and the column sits under its last line or pins left of it. The column
-- reads its position, visibility, collapse and drag state, and the bottom of its NineSlice or header.
---@class ForeverNativeTrackerFrame : Frame
---@field NineSlice Frame?
---@field Header Frame?
---@field isDragging boolean?

-- Keep our sections and their frame pools entirely outside the native module collection and its Edit Mode path.
if not ObjectiveTrackerFrame then
	return
end

-- A consumer's old tracker settings, offered once by the first module that attaches with a `legacySettings` table.
-- Saved variables are not there while the files load, so the copy waits for ForeverCore's ADDON_LOADED.
local pendingLegacy

-- The runtime store when Core.lua publishes one; an older consumer's spec can still supply ForeverCoreDB directly.
---@return table?
local function Database()
	if type(ns.Store) == "function" then
		return ns.Store()
	end
	return ForeverCoreDB
end

-- Copy the first legacy table offered into the runtime store's trackerHost, once. Each field is taken only when it
-- has the shape the host reads; the rest keep the fresh defaults. Later offers are ignored. True when it copied.
---@return boolean
local function CopyLegacy()
	local db = Database()
	if type(db) ~= "table" or pendingLegacy == nil then
		return false
	end
	local legacy = pendingLegacy
	pendingLegacy = nil
	local settings = ns.TrackerHostSettings()
	if settings.migrated == true then
		return false
	end
	for field, kind in pairs({
		locked = "boolean",
		scale = "number",
		backdropOpacity = "number",
	}) do
		if type(legacy[field]) == kind then
			settings[field] = legacy[field]
		end
	end
	-- The legacy table predates placement: only a detached one (attached false) holds a spot the player dragged to,
	-- and an attached one (true or missing) drops it, the same as Settings migrates the store's own table. A place
	-- the store already has is kept, and setting one marks the store migrated, so the store's own flag is not read.
	if legacy.attached == false and type(legacy.x) == "number" and type(legacy.y) == "number" then
		settings.x, settings.y = legacy.x, legacy.y
	end
	settings.placement = settings.placement or "under"
	settings.migrated = true
	return true
end
ns.MigrateTrackerSettings = CopyLegacy

---@param module ForeverTrackerModule
local function OfferLegacy(module)
	if pendingLegacy == nil and type(module.legacySettings) == "table" then
		pendingLegacy = module.legacySettings
		return true
	end
	return false
end

-- Runs `callback` once the world is entered and saved variables are loaded. Defined before the foreign-column branch
-- below, since core's tracker sections wait on it with either column. A copy the loader boots after one of those
-- events has fired (Loader.Seen) waits only for the rest: EventUtil.ContinueAfterAllEvents never completes for an
-- event that came before it was registered. The one wait starts as this file runs, so a section created after login
-- (in an unwrapped load no loader saw the events) joins it instead of waiting on an event already past.
local worldReady, worldWaiting = false, {}
do
	local loader = rawget(_G, "ForeverCoreLoader")
	local seen = type(loader) == "table" and type(loader.Seen) == "function" and loader.Seen or nil
	local pending = {}
	for _, event in ipairs({ "PLAYER_ENTERING_WORLD", "VARIABLES_LOADED" }) do
		if not (seen and seen(event)) then
			pending[#pending + 1] = event
		end
	end
	local function Ready()
		worldReady = true
		local waiting = worldWaiting
		worldWaiting = {}
		-- One failing section must not strand the rest; without the client's handler (offline specs) errors raise.
		local getHandler = rawget(_G, "geterrorhandler")
		for _, callback in ipairs(waiting) do
			if getHandler then
				xpcall(callback, getHandler())
			else
				callback()
			end
		end
	end
	if #pending == 0 then
		worldReady = true
	else
		EventUtil.ContinueAfterAllEvents(Ready, unpack(pending))
	end
end
---@param callback fun()
function ns.AfterWorldEvents(callback)
	if worldReady then
		callback()
	else
		worldWaiting[#worldWaiting + 1] = callback
	end
end

-- A store build that still vendors UI/TrackerHost.lua can load before ForeverCore (Adventure Guide, Commissions and
-- Field Guide load before it alphabetically). That copy registers the one companion column in ForeverTrackerHost and
-- reuses whatever is already there, so adopt the existing column instead of drawing a second one over it: every call
-- the old API has is forwarded, and the backdrop calls it predates answer without drawing anything.
local existing = ForeverTrackerHost
if type(existing) == "table" then
	local api = {}
	for _, name in ipairs({
		"Attach",
		"Debug",
		"GetPlacement",
		"GetScale",
		"GetSettings",
		"GetStayUnder",
		"IsAttached",
		"IsAttachedToQuestTracker",
		"IsLocked",
		"OnAttachmentChanged",
		"SavePosition",
		"SetAttached",
		"SetLocked",
		"SetPlacement",
		"SetScale",
		"SetSectionMaxHeight",
		"SetStayUnder",
	}) do
		local method = existing[name]
		if type(method) == "function" then
			api[name] = method
		end
	end
	if type(api.GetBackdropOpacity) ~= "function" then
		function api.GetBackdropOpacity()
			return 0
		end
	end
	if type(api.SetBackdropOpacity) ~= "function" then
		function api.SetBackdropOpacity(_) end
	end
	if type(api.GetStayUnder) ~= "function" then
		function api.GetStayUnder()
			return false
		end
	end
	if type(api.SetStayUnder) ~= "function" then
		function api.SetStayUnder(_) end
	end
	-- The consumer drops its own tracker table once it attaches, so keep the first one offered for the runtime store,
	-- the same as core's own host does: the settings are not lost while the older column is the one drawing.
	local attach = api.Attach
	function api.Attach(module, show)
		if OfferLegacy(module) then
			CopyLegacy()
		end
		return attach(module, show)
	end
	---@cast api ForeverTrackerHostAPI
	ns.TrackerHost = api
	-- Core's own tracker files must not run against a column core did not build.
	ns.TrackerHostForeign = true
	return
end

-- The column frame, its pools and its events are made at Start (end of file): defining the runtime touches nothing.
---@class ForeverTrackerColumn: Frame
---@field MarkDirty fun(self: ForeverTrackerColumn)
---@field IsCollapsed fun(self: ForeverTrackerColumn): boolean
---@field ForceExpand fun(self: ForeverTrackerColumn)
---@type ForeverTrackerColumn
local host
---@class ForeverTrackerHostAPI
local api = {}
local MIN_SCALE, MAX_SCALE = 0.5, 2
local fallbackSettings = { attached = false, scale = 1, backdropOpacity = 0, stayUnder = false }
local ready = false
local function Coordinate(value)
	if type(value) == "number" and value == value and math.abs(value) ~= math.huge then
		return value
	end
end
-- The saved backdrop opacity is a fraction, so the value the slider writes and the value the texture reads are the
-- same number. It is not a separate on/off switch: 0 is off, and every value above it is the texture's opacity.
local function Opacity(value)
	if type(value) ~= "number" or value ~= value then
		return 0
	end
	return math.max(0, math.min(1, value))
end
-- The column sits at its placement until the player drags it, and saved x and y mean a dragged position. Settings with
-- no placement predate it: an old attached placement (`attached` true or missing) drops its saved spot once, so it
-- follows its place, and a free position the player dragged (attached false with x and y) is kept. The player's Lock
-- choice stays either way. `attached` then mirrors whether the column follows the quest tracker under it, which is
-- what an addon's "Attach to quest tracker" checkbox reads.
---@return ForeverTrackerSettings
local function Settings()
	local settings = ns.TrackerHostSettings and ns.TrackerHostSettings() or fallbackSettings
	if settings.placement == nil and settings.attached ~= false then
		settings.x, settings.y = nil, nil
	end
	settings.locked = settings.locked == true
	settings.stayUnder = settings.stayUnder == true
	local scale = settings.scale
	if type(scale) ~= "number" or scale ~= scale then
		settings.scale = 1
	else
		settings.scale = math.max(MIN_SCALE, math.min(MAX_SCALE, scale))
	end
	settings.backdropOpacity = Opacity(settings.backdropOpacity)
	settings.x, settings.y = Coordinate(settings.x), Coordinate(settings.y)
	if settings.placement ~= "left" then
		settings.placement = "under"
	end
	settings.attached = settings.placement == "under" and not (settings.x and settings.y)
	return settings
end
-- The column's width in its own units: the 260 of the client's ObjectiveTrackerContainer header template, so a Forever
-- section reads at the width its template was drawn for.
local WIDTH = 260
-- The column is a child of UIParent, so its scale is only the player's own tracker scale.
local function MatchScale()
	-- Saved variables, and with them the user's scale, are not ready while the files load.
	host:SetScale(ready and Settings().scale or 1)
end
-- A header drag moves the column, and the Lock switch stops it; both live in UI/TrackerLock.lua, which the TOC loads
-- before this one.
local Drag
-- The optional backdrop spans the whole private column, so every Forever section sits on it at once. It is one
-- texture on the host rather than chrome each addon draws, and it uses the game's own tooltip background art, tinted
-- the way the tooltip tints it. Off is simply opacity 0; drawing it only changes a texture, never a frame, so the
-- slider is safe to move in combat.
local BACKDROP_ATLAS = "Tooltip-NineSlice-Center"
local BACKDROP_INSET = 6
local backdrop

local function BackdropTint()
	local color = rawget(_G, "TOOLTIP_DEFAULT_BACKGROUND_COLOR")
	if color then
		local getter = color.GetRGB
		if type(getter) == "function" then
			local r, g, b = getter(color)
			if type(r) == "number" and type(g) == "number" and type(b) == "number" then
				return r, g, b
			end
		end
		if type(color.r) == "number" and type(color.g) == "number" and type(color.b) == "number" then
			return color.r, color.g, color.b
		end
	end
	-- The tooltip's saved default when the client's colour object is not available (tests, and a stripped client).
	return 0.09, 0.09, 0.19
end

local function ApplyBackdrop(settings)
	local opacity = settings.backdropOpacity or 0
	backdrop:SetShown(opacity > 0)
	if opacity > 0 then
		local r, g, b = BackdropTint()
		backdrop:SetVertexColor(r, g, b, opacity)
	end
end
local function IsLocked()
	return Settings().locked
end
local modules, queued = {}, false
local pendingAttachments = {}
local pools

local function Acquire(parent, template)
	local info = C_XMLUtil.GetTemplateInfo(template)
	local pool = pools:GetOrCreatePool(info and info.type or "Frame", parent, template)
	---@class ForeverTrackerPooledFrame : Frame
	---@field GetLine? function
	---@field FreeLine? function
	---@field OnAnimFinished? function
	local frame, isNew = pool:Acquire(template)
	frame.template = template
	return frame, isNew
end

local function GetLine(block, key, template)
	template = template or block.parentModule.lineTemplate
	local line = block:GetExistingLine(key)
	if line and line.template ~= template then
		block:FreeLine(line)
		line = nil
	end
	if not line then
		line = Acquire(block, template)
		line:SetParent(block)
		line:Show()
	end
	block.usedLines[key] = line
	line.objectiveKey, line.parentBlock, line.used = key, block, true
	return line
end

local function FreeLine(block, line)
	block.usedLines[line.objectiveKey] = nil
	pools:Release(line)
	line:Hide()
	if line.OnFree then
		line:OnFree(block)
	end
end

local function FreeResources(resources, onFree)
	for key, frame in pairs(resources or {}) do
		if not frame.used then
			resources[key] = nil
			if onFree and frame.OnFree then
				frame:OnFree()
			end
			pools:Release(frame)
		end
	end
end

-- Our blocks have no native reward toasts; their animations stay in the private cache.
local function OnAnimFinished(block)
	if block.activeAnim ~= block.AddAnim then
		block.parentModule:RemoveBlockFromCache(block)
		block.parentModule:MarkDirty()
		block:SetAlpha(0)
	end
	block.activeAnim = nil
	if block.pendingAnim then
		local anim = block.pendingAnim
		block.pendingAnim = nil
		block:TryPlayAnim(anim)
	end
end

-- Every section but the one that fills the rest of the column caps at this many UI units. A section that asks for the
-- room the others leave scrolls in it, while Legacy's zone and SkillUp's reagents stay in view.
local SECTION_MAX_HEIGHT = 200
-- The bar's track plus the item frame's overhang and its spacing. Every section keeps it whether or not it scrolls,
-- so its text width never depends on how tall its blocks turn out: a list that starts or stops scrolling keeps its
-- wrapping and needs no second build at another width (#795).
local SCROLL_GUTTER = 18
local SCROLL_BAR_GAP = 10 -- the space between the blocks and the bar
local SCROLL_HEADER_GAP = 4 -- the bar starts this far under the header's rule

-- A section taller than its cap scrolls under its header instead of being cut off. Only core's own frames move: the
-- ScrollFrame takes the module's ContentsFrame as its scroll child, blocks keep their anchors to it, and the module's
-- header stays outside the viewport. Every section uses the same wrapper, so a consumer never writes a scrollbar.
-- The blocks contain the quest item buttons, which are secure in the client, and those buttons are protected with
-- every ancestor up to the column. The column therefore lays nothing out in combat: MarkDirty holds the pass until
-- PLAYER_REGEN_ENABLED, so no SetPoint, SetHeight, SetParent, Show or Hide can touch a button or its ancestors.
local Module = {}
function Module:SetContainer(container)
	self.parentContainer = container
	self:SetParent(container)
	-- A section needs a place before its first build: the client wraps and measures each line at the width its anchors
	-- resolve to, and a clean section keeps that build. The layout pass moves it to its slot.
	self:ClearAllPoints()
	self:SetPoint("TOPLEFT", container, "TOPLEFT", 0, 0)
	if self.trackerScrollable then
		self:CreateTrackerScroll()
	end
end
function Module:AcquireFrame(template)
	local frame, isNew = Acquire(self, template)
	frame:SetParent(self.ContentsFrame)
	if frame.GetLine then
		frame.GetLine, frame.FreeLine = GetLine, FreeLine
		if frame.OnAnimFinished then
			frame.OnAnimFinished = OnAnimFinished
		end
	end
	return frame, isNew
end
function Module:FreeBlock(block)
	self:RemoveBlockFromCache(block, true)
	block:Free()
	self.usedBlocks[block.template][block.id] = nil
	pools:Release(block)
	self:OnFreeBlock(block)
end
function Module:FreeUnusedTimerBars()
	FreeResources(self.usedTimerBars)
end
function Module:FreeUnusedProgressBars()
	FreeResources(self.usedProgressBars, true)
end
function Module:FreeUnusedRightEdgeFrames()
	FreeResources(self.usedRightEdgeFrames)
end
function Module.GetContextMenuParent(_)
	return host
end

-- Every block's offset from the top of the scroll child, in the same order the module laid them out. The arithmetic
-- mirrors ObjectiveTrackerModuleMixin's anchors: the first block hangs fromHeaderOffsetY under the header, and every
-- later block hangs fromBlockOffsetY under the one before it.
---@return { block: any, start: number }[]
function Module:BlockStarts()
	local starts = {}
	local offset = -(tonumber(self.fromHeaderOffsetY) or -10)
	local block = self.firstBlock
	while block do
		starts[#starts + 1] = { block = block, start = offset }
		offset = offset + (block.height or block:GetHeight() or 0) - (tonumber(self.fromBlockOffsetY) or -10)
		block = block.nextBlock
	end
	return starts
end

-- The block whose top is at or above the view: the block the player is reading, which the next layout keeps in place.
---@param starts { block: any, start: number }[]
---@return number
function Module:TopBlockIndex(starts)
	local offset = self.scrollOffset or 0
	local index = 1
	for position, entry in ipairs(starts) do
		if entry.start <= offset + 0.5 then
			index = position
		else
			break
		end
	end
	return index
end

-- Remember the quest at the top before a layout rebuilds the list, so a quest finishing or a distance changing cannot
-- jump the view. The index is the fallback for a block whose quest left the list entirely.
function Module:CaptureScrollAnchor()
	if not self.trackerScrollable then
		return
	end
	if type(self.IsCollapsed) == "function" and self:IsCollapsed() then
		return
	end
	local starts = self:BlockStarts()
	if #starts == 0 then
		return
	end
	local index = self:TopBlockIndex(starts)
	local entry = starts[index]
	self.scrollAnchorID = entry and entry.block.id
	self.scrollAnchorIndex = entry and index
end

-- The offset the remembered quest has after the layout. The first block keeps the module's own gap under the header,
-- so its offset is zero; a later block starts at its own top edge.
---@param starts { block: any, start: number }[]
---@return number
function Module:ApplyScrollAnchor(starts)
	local index
	if self.scrollAnchorID ~= nil then
		for position, entry in ipairs(starts) do
			if entry.block.id == self.scrollAnchorID then
				index = position
				break
			end
		end
	end
	index = index or self.scrollAnchorIndex or 1
	if #starts == 0 then
		return 0
	end
	index = math.max(1, math.min(#starts, index))
	if index == 1 then
		return 0
	end
	return starts[index].start
end

-- The contents hang from the header at the scroll offset, not from the viewport: a viewport with no room has a height
-- of 0, which the client treats as no height at all, so it has no rect, and nothing anchored to it would either.
function Module:PlaceTrackerContents()
	self.ContentsFrame:SetPoint("TOPLEFT", self.Header, "BOTTOMLEFT", 0, self.scrollOffset or 0)
end

---@param offset number
function Module:SetScrollOffset(offset)
	if InCombatLockdown() then
		return
	end
	local range = self.scrollRange or 0
	offset = math.max(0, math.min(range, tonumber(offset) or 0))
	self.scrollOffset = offset
	if self.scrollFrame then
		self:PlaceTrackerContents()
	end
	if self.scrollBar then
		self.updatingScrollBar = true
		self.scrollBar:SetScrollPercentage(range > 0 and offset / range or 0, true)
		self.updatingScrollBar = false
	end
	self:CaptureScrollAnchor()
	if self.OnScrollChanged then
		self:OnScrollChanged()
	end
end

---@param delta number
function Module:OnTrackerWheel(delta)
	if InCombatLockdown() or not self.trackerOverflow then
		return
	end
	local starts = self:BlockStarts()
	if #starts == 0 then
		return
	end
	local offset = self.scrollOffset or 0
	local viewport = self.trackerViewport or 0
	if viewport <= 0 then
		return
	end
	-- Keep a line of overlap on a full page, and half the view when less than two lines fit.
	local page = viewport - math.min(16, viewport / 2)
	local target = delta > 0 and 0 or (self.scrollRange or 0)
	for index, entry in ipairs(starts) do
		local start = index == 1 and 0 or entry.start
		if delta > 0 then
			if start < offset then
				target = start
			else
				break
			end
		elseif start > offset then
			target = start
			break
		end
	end
	if delta > 0 then
		target = math.max(target, offset - page)
	else
		target = math.min(target, offset + page)
	end
	self:SetScrollOffset(target)
end

---@param percentage number
function Module:OnScrollBarPercentage(percentage)
	if InCombatLockdown() or self.updatingScrollBar then
		return
	end
	local range = self.scrollRange or 0
	self:SetScrollOffset((tonumber(percentage) or 0) * range)
end

-- A frozen view keeps every secure item button beside its quest. The client has no disabled minimal scrollbar art, so
-- the bar stays visible at half alpha and the wheel does nothing until combat ends.
---@param frozen boolean
function Module:SetScrollFrozen(frozen)
	self.scrollFrozen = frozen
	if not self.scrollBar then
		return
	end
	self.scrollBar:SetScrollAllowed(not frozen)
	self.scrollBar:SetAlpha(frozen and 0.5 or 1)
	if self.scrollFrame then
		self.scrollFrame:EnableMouseWheel(not frozen)
	end
	self:EnableMouseWheel(not frozen)
end

-- Builds the viewport once, on the first attach, out of core's own frames: a frame that clips its children, holding the
-- module's own ContentsFrame, so every block and every pooled line keeps its parent and its anchors. It is not a
-- ScrollFrame: the client places a scroll child only when its ScrollFrame next draws, so a section built in the frame
-- it attached would wrap and measure its lines with no width, each counting as one row (#795). Plain anchors resolve
-- at once, and scrolling moves the contents' anchor.
function Module:CreateTrackerScroll()
	if self.scrollFrame or not self.ContentsFrame or not self.Header then
		return
	end
	local scroll = CreateFrame("Frame", nil, self)
	scroll:SetClipsChildren(true)
	scroll:SetPoint("TOPLEFT", self.Header, "BOTTOMLEFT", 0, 0)
	scroll:SetPoint("TOPRIGHT", self.Header, "BOTTOMRIGHT", 0, 0)
	scroll:SetHeight(0)
	scroll:EnableMouseWheel(true)
	scroll:SetScript("OnMouseWheel", function(_, delta)
		self:OnTrackerWheel(delta)
	end)
	local contents = self.ContentsFrame
	contents:SetParent(scroll)
	contents:ClearAllPoints()
	-- The blocks take the column's width less the gutter from the start, so the first build measures its text there.
	contents:SetHeight(0)
	self.scrollFrame = scroll
	self:PlaceTrackerContents()
	self:SetTrackerContentsWidth()

	-- The client's minimal scrollbar is an EventFrame on ScrollBarMixin, not a Slider. Its percentage drives the
	-- viewport; the wheel above moves one block.
	local bar = CreateFrame("EventFrame", nil, self, "MinimalScrollBar")
	bar:SetPoint("TOPLEFT", scroll, "TOPRIGHT", SCROLL_BAR_GAP, -SCROLL_HEADER_GAP)
	bar:SetPoint("BOTTOMLEFT", scroll, "BOTTOMRIGHT", SCROLL_BAR_GAP, 0)
	bar:RegisterCallback("OnScroll", function(_, percentage)
		self:OnScrollBarPercentage(percentage)
	end, self)
	bar:SetVisibleExtentPercentage(0)
	bar:Hide()
	self.scrollBar = bar

	self:EnableMouseWheel(true)
	self:SetScript("OnMouseWheel", function(_, delta)
		self:OnTrackerWheel(delta)
	end)
	self:SetScrollFrozen(InCombatLockdown())
end

-- The blocks' width: the section's, less the gutter the bar sits in.
function Module:SetTrackerContentsWidth()
	local width = math.max(0, (self:GetWidth() or 0) - SCROLL_GUTTER)
	if self.scrollFrame and self.scrollContentsWidth ~= width then
		self.scrollContentsWidth = width
		self.ContentsFrame:SetWidth(width)
	end
	return width
end

-- A native quest POI sits left of its block, and an item hotkey may extend right. A ScrollFrame clips both
-- axes, even when it is only used to scroll vertically. Read our visible descendants' actual horizontal edges,
-- expand just the viewport, and counter-offset its child so text keeps its original width and screen position.
local function HorizontalOverflow(contents, width)
	if not contents.GetChildren then
		return 0, 0
	end
	local origin = contents:GetLeft()
	if not origin then
		return 0, 0
	end
	local scale = contents:GetEffectiveScale()
	local left, right = origin, origin + width
	local function Include(region)
		if not region:IsShown() then
			return
		end
		local first, last = region:GetLeft(), region:GetRight()
		if first and last then
			local ratio = region:GetEffectiveScale() / scale
			left, right = math.min(left, first * ratio), math.max(right, last * ratio)
		end
		if region.GetRegions then
			for _, child in ipairs({ region:GetRegions() }) do
				Include(child)
			end
		end
		if region.GetChildren then
			for _, child in ipairs({ region:GetChildren() }) do
				Include(child)
			end
		end
	end
	for _, child in ipairs({ contents:GetChildren() }) do
		Include(child)
	end
	return origin - left, right - origin - width
end

-- Mouse-wheel input is delivered to the deepest mouse-enabled descendant, not bubbled to its scroll frame. Keep the
-- existing descendant handlers, but hook every pooled content frame so scrolling works over text, icons and buttons.
local trackerWheelModules = setmetatable({}, { __mode = "k" })
local function BindTrackerWheel(frame, handler, seen)
	if not frame then
		return
	end
	local fresh = not seen[frame]
	seen[frame] = true
	if frame ~= handler.owner then
		trackerWheelModules[frame] = handler.module
	end
	if fresh and frame ~= handler.owner and frame.EnableMouseWheel and frame.HookScript then
		frame:EnableMouseWheel(true)
		frame:HookScript("OnMouseWheel", handler.callback)
	end
	if frame.GetChildren then
		for _, child in ipairs({ frame:GetChildren() }) do
			BindTrackerWheel(child, handler, seen)
		end
	end
end

-- Sizes the viewport to the cap the column gave this section, shows the bar only when the blocks pass it, and holds
-- the view on the quest at the top. `headerHeight` and `contentsHeight` are Blizzard's own numbers.
local UsableHeight
function Module:LayoutTrackerScroll()
	if not self.scrollFrame or InCombatLockdown() then
		return
	end
	local header = self.headerHeight or 0
	local body = math.max(0, (self.contentsHeight or 0) - header)
	local cap = self.trackerCap or body
	local viewport = math.min(body, math.max(0, cap - header))
	local usable = UsableHeight(self)
	if header + viewport < usable then
		viewport = 0
	end
	self.scrollFrame:SetShown(viewport > 0)
	local range = viewport > 0 and math.max(0, body - viewport) or 0
	self.trackerBody, self.trackerViewport, self.scrollRange = body, viewport, range
	self.trackerOverflow = range > 0

	local width = self:SetTrackerContentsWidth()
	local contents = self.ContentsFrame
	local seen = self.trackerWheelFrames or {}
	self.trackerWheelFrames = seen
	local handler = self.trackerWheelHandler
	if not handler then
		handler = {
			owner = contents,
			module = self,
			callback = function(frame, delta)
				if trackerWheelModules[frame] == self then
					self:OnTrackerWheel(delta)
				end
			end,
		}
		self.trackerWheelHandler = handler
	end
	BindTrackerWheel(contents, handler, seen)
	contents:SetHeight(body)
	self.scrollFrame:SetHeight(viewport)
	local clipLeft, clipRight = HorizontalOverflow(contents, width)
	self.scrollFrame:SetPoint("TOPLEFT", self.Header, "BOTTOMLEFT", -clipLeft, 0)
	self.scrollFrame:SetPoint("TOPRIGHT", self.Header, "BOTTOMRIGHT", -SCROLL_GUTTER + clipRight, 0)
	self:PlaceTrackerContents()
	-- The bar belongs in the section's gutter, independent of the viewport's clipping expansion.
	self.scrollBar:SetPoint("TOPLEFT", self.Header, "BOTTOMRIGHT", -SCROLL_GUTTER + SCROLL_BAR_GAP, -SCROLL_HEADER_GAP)
	self.scrollBar:SetPoint("BOTTOMLEFT", self.Header, "BOTTOMRIGHT", -SCROLL_GUTTER + SCROLL_BAR_GAP, -viewport)

	-- The bar's thumb is its visible fraction of the whole body; the scroll percentage below positions it.
	self.scrollBar:SetVisibleExtentPercentage(body > 0 and viewport / body or 0)
	if range > 0 then
		self.scrollBar:Show()
		self.scrollBar:SetAlpha(self.scrollFrozen and 0.5 or 1)
	else
		self.scrollBar:Hide()
	end

	-- A collapsed or empty section keeps the view it had, so reopening it or giving the list back returns to the
	-- same quest. A section merely shorter than its cap has nothing left to scroll, so it starts at the top through
	-- the same setter as every other move, which also resets the scroll child and redraws the item buttons.
	local collapsed = type(self.IsCollapsed) == "function" and self:IsCollapsed()
	if range > 0 then
		local offset = math.min(self:ApplyScrollAnchor(self:BlockStarts()), range)
		self:SetScrollOffset(offset)
	elseif not collapsed and body > 0 and viewport > 0 then
		self.scrollAnchorID = nil
		self.scrollAnchorIndex = nil
		self:SetScrollOffset(0)
	end

	local modifiers = 0
	for _, value in pairs(self.heightModifiers or {}) do
		modifiers = modifiers + value
	end
	self:SetHeight(header + viewport + (self.bottomSpacing or 0) + modifiers)
end

-- The module's own UpdateHeight still runs, so Blizzard's height modifiers and bottom spacing stay in one place.
function Module:UpdateHeight()
	if type(self.baseUpdateHeight) == "function" then
		self.baseUpdateHeight(self)
	end
	if self.trackerScrollable then
		self:LayoutTrackerScroll()
	end
end

-- The first block is the smallest useful expanded viewport: a shorter one shows its header and a clipped objective
-- row, which makes the section unusable even though its scrollbar is visible. This derives the floor from Blizzard's
-- measured header and pooled block metrics, rather than a display-size threshold.
function Module:GetMinimumHeight()
	if not self.trackerScrollable or type(self.IsCollapsed) == "function" and self:IsCollapsed() then
		return 0
	end
	local block = self.firstBlock
	if not block then
		return 0
	end
	local header = self.headerHeight or 0
	local offset = tonumber(self.fromHeaderOffsetY) or -10
	return header + math.max(0, (block.height or block:GetHeight() or 0) - offset)
end

-- Prefer a whole first block, but under screen pressure a title and its first objective still make a readable page.
UsableHeight = function(module)
	local minimum = module:GetMinimumHeight()
	local block = module.firstBlock
	if minimum == 0 or not block then
		return minimum
	end
	for _, line in pairs(block.usedLines or {}) do
		local _, anchor, _, _, y = line:GetPoint(1)
		if block.HeaderText and anchor == block.HeaderText or anchor == block then
			local title = block.HeaderText and block.HeaderText:GetHeight() or 0
			return math.min(
				minimum,
				(module.headerHeight or 0) - (module.fromHeaderOffsetY or -10) + title - (y or 0) + line:GetHeight()
			)
		end
	end
	return minimum
end

-- A scrollable section lays every block out, even the ones past the cap: they live in the scroll child, not in the
-- room the column gave the section. The viewport, not CanFitBlock, decides what the player sees.
function Module:CanFitBlock(block)
	if self.trackerScrollable then
		return true
	end
	if type(self.baseCanFitBlock) == "function" then
		return self.baseCanFitBlock(self, block)
	end
	return true
end

function Module:GetContentsHeight()
	if self.trackerScrollable and self.trackerViewport ~= nil then
		if type(self.IsDisplayable) == "function" and not self:IsDisplayable() then
			return 0
		end
		return (self.headerHeight or 0) + self.trackerViewport
	end
	if type(self.baseGetContentsHeight) == "function" then
		return self.baseGetContentsHeight(self)
	end
	return 0
end

function Module:IsTruncated()
	if self.trackerScrollable and self.trackerOverflow ~= nil and self.trackerOverflow then
		return true
	end
	if type(self.baseIsTruncated) == "function" then
		return self.baseIsTruncated(self)
	end
	return false
end

-- A section from Blizzard's template rebuilds its blocks only when its own data marked it dirty or the column's width
-- changed under it, as the client's own container does. A new cap only resizes its viewport: a scrollable section lays
-- every block out whatever its cap. So a host pass for another section's change, combat ending or a new cap leaves
-- every other section's blocks and header alone (#795). A section with no room keeps its blocks and stays dirty until
-- it has some, since Blizzard's Update with no room would free them. A frame without IsDirty cannot say what changed,
-- so it rebuilds on every pass.
function Module:Update(availableHeight, dirtyUpdate)
	self.trackerCap = availableHeight
	if type(self.baseUpdate) ~= "function" then
		return
	end
	if not self.trackerScrollable then
		return self.baseUpdate(self, availableHeight, dirtyUpdate)
	end
	local width = self:SetTrackerContentsWidth()
	if type(self.IsDirty) == "function" then
		local stale = self:IsDirty() or self.trackerBuiltWidth ~= width
		if not stale or availableHeight <= 0 then
			self:UpdateHeight()
			return self:GetContentsHeight(), self:IsTruncated()
		end
		-- A section that cannot update now (combat) keeps its blocks, and its last build width with them. Text wraps at the
		-- width its block resolves to on screen, so a build while the column has no rect yet (the game's tracker not
		-- placed at login) measured unwrapped text: it records no width, and the first pass with a rect builds again.
		if self:CanUpdate() then
			self.trackerBuiltWidth = self.ContentsFrame:GetLeft() and width or nil
		end
	end
	-- Blizzard wraps and measures each line at the width its block resolves to, and a frame of height 0 resolves to
	-- none: the client reads 0 as no height. The contents start at 0 and keep the last body's height, 0 for a section
	-- that has shown nothing yet, so they take the cap while the blocks are built; LayoutTrackerScroll sets the body.
	if availableHeight > 0 then
		self.ContentsFrame:SetHeight(availableHeight)
	end
	return self.baseUpdate(self, availableHeight, dirtyUpdate)
end

function Module:BeginLayout()
	self:CaptureScrollAnchor()
	if type(self.baseBeginLayout) == "function" then
		self.baseBeginLayout(self)
	end
end

-- The space under each section that draws.
local GAP = 10

-- A section's own callback runs in that addon's SafeCall, so its failure lands in its journal; core's is the fallback.
local function RunSafe(safe, label, fn, ...)
	if safe then
		return safe(label, fn, ...)
	end
	if ns.SafeCall then
		return ns.SafeCall(label, fn, ...)
	end
	return pcall(fn, ...)
end

local function ReportRefusal(reason)
	ns.ReportRefusal(reason)
end

-- The cap a section gets from the column. A scrollable section never takes more than 200 units, except the one that
-- asks for the rest of the column, which is measured after the others have laid themselves out.
---@param module ForeverTrackerModule
---@param available number
---@return number
local function SectionCap(module, available)
	if not module.trackerScrollable then
		return available
	end
	local maximum = module.trackerMaxHeight
	if type(maximum) ~= "number" then
		maximum = SECTION_MAX_HEIGHT
	end
	local minimum = type(module.GetMinimumHeight) == "function" and module:GetMinimumHeight() or 0
	return math.min(available, math.max(minimum, maximum))
end

-- Lays every section out from the host's top, each in the room the ones above it left, less the gap under it, so the
-- column never runs past `available`. Returns whether any section drew. One section's layout error is recorded in its
-- own journal and leaves the sections below it to lay out, instead of breaking the whole column.
--
-- A section with `trackerMaxHeight == "remaining"` gets what the capped sections above and below it leave, so that
-- long section is the one that scrolls. It is laid out after the others so their real heights are known first.
local function LayoutPass(width, available)
	local restIndex
	for index, module in ipairs(modules) do
		if module.trackerScrollable and module.trackerMaxHeight == "remaining" then
			restIndex = restIndex or index
		end
	end
	local heights, total = {}, 0
	local minimums, headers = {}, {}
	local preferred, usable = 0, 0
	for index, module in ipairs(modules) do
		local minimum = type(module.GetMinimumHeight) == "function" and module:GetMinimumHeight() or 0
		minimums[index] = minimum
		headers[index] = minimum > 0 and (module.headerHeight or 0) or 0
		if minimum > 0 then
			preferred = preferred + minimum + GAP
			usable = usable + UsableHeight(module) + GAP
		end
	end
	if preferred > available then
		for index, module in ipairs(modules) do
			if minimums[index] > 0 then
				minimums[index] = usable <= available and UsableHeight(module) or headers[index]
			end
		end
	end
	local floorsMoved = false
	local function LayOut(index, cap)
		local module = modules[index]
		local laterMinimum = 0
		for later = index + 1, #modules do
			laterMinimum = laterMinimum + (minimums[later] or 0) + ((minimums[later] or 0) > 0 and GAP or 0)
		end
		local room = math.max(0, available - total - GAP)
		if laterMinimum > 0 then
			cap = math.min(cap, math.max(0, room - laterMinimum))
		end
		module:SetWidth(width)
		-- The native header template starts at 260 units; it does not stretch with its module. The viewport
		-- follows that header, so give both the same width before measuring any scroll contents.
		if module.Header then
			module.Header:SetWidth(width)
		end
		local previousMinimum = type(module.GetMinimumHeight) == "function" and module:GetMinimumHeight() or 0
		local previousUsable = module.trackerScrollable and UsableHeight(module) or 0
		local ok = RunSafe(module.safeCall, "tracker section update", module.Update, module, cap)
		local minimum = 0
		if ok and type(module.GetMinimumHeight) == "function" then
			minimum = module:GetMinimumHeight()
		end
		if
			ok
			and module.trackerScrollable
			and (minimum ~= previousMinimum or UsableHeight(module) ~= previousUsable)
		then
			floorsMoved = true
		end
		if cap > 0 and minimum > cap then
			-- The cap is the room left after sections above this one. Never borrow from their accounting or make the
			-- column taller than the room it was given. A later layout reserves this measured floor before earlier caps.
			module.trackerCap = cap
			module:UpdateHeight()
		end
		local used = ok and module:GetContentsHeight() or 0
		if module.trackerScrollable then
			if cap < (module.headerHeight or 0) then
				used = 0
			end
			module:SetShown(used > 0)
		end
		heights[index] = used
		if used > 0 then
			total = total + used + GAP
		end
	end
	for index, module in ipairs(modules) do
		if index ~= restIndex then
			LayOut(index, SectionCap(module, math.max(0, available - total - GAP)))
		end
	end
	if restIndex then
		LayOut(restIndex, math.max(0, available - total - GAP))
	end
	local hasSections = total > 0
	local height = 0
	for index, module in ipairs(modules) do
		module:ClearAllPoints()
		module:SetPoint("TOPLEFT", host, "TOPLEFT", 0, -height)
		local used = heights[index]
		if used > 0 then
			height = height + used + GAP
		end
	end
	host:SetHeight(math.max(1, height))
	return hasSections, floorsMoved
end

-- Every cap is measured from the floors the sections' last builds left. A section that rebuilds in a pass can move its
-- own floor, so the caps the sections above it got are stale, and the pass runs again in this frame, before anything
-- is drawn. A repeat rebuilds no section: each one the first pass built is clean at this width, and a cap alone only
-- resizes a viewport. It can build a dirty section the first pass gave no room, which can move one more floor, so a
-- third pass settles that; a column still unsettled after it lays out again in the next frame.
local MAX_PASSES = 3
local function LayoutModules(width, available)
	ns.TrackerOrder.Sort(modules)
	local hasSections, floorsMoved
	for _ = 1, MAX_PASSES do
		hasSections, floorsMoved = LayoutPass(width, available)
		if not floorsMoved then
			return hasSections
		end
	end
	host:MarkDirty()
	return hasSections
end
-- Questie's quest tracker, when it is the one on screen. Questie hides the game's tracker and draws its own list in
-- Questie_BaseFrame, built a few seconds after login at the game's tracker's place and sized to its lines (#866). No
-- client API names a replacement tracker, so the column knows this one by its frame's name; the column reads only
-- where it is, as it does the game's tracker.
---@return Frame?
local function QuestieList()
	local list = rawget(_G, "Questie_BaseFrame")
	if type(list) == "table" and list.IsShown and list:IsShown() then
		return list
	end
	return nil
end
-- What the quest tracker on screen shows, which decides its last visible line: "questie" for Questie's list, or for
-- the game's tracker "hidden" with nothing to list, "collapsed" to its header, or "list". Reads only.
---@return "questie"|"hidden"|"collapsed"|"list"
local function TrackerShows()
	if QuestieList() then
		return "questie"
	end
	if not ObjectiveTrackerFrame:IsShown() then
		return "hidden"
	end
	if ObjectiveTrackerFrame:IsCollapsed() then
		return "collapsed"
	end
	return "list"
end
-- Where the game's tracker's top left corner is, in its own units, as the column places itself by it: the frame's own
-- rect while the tracker shows. A hidden tracker (nothing tracked) is not laid out by its container any more, so its
-- rect drifts or goes away with whatever else the screen does; the column holds the corner the tracker had when it
-- last showed, which is where an empty tracker would sit, and reads the frame only for a tracker it never saw show.
-- Reads only.
local shownCorner
---@return number? left, number? top, number scale
local function TrackerRect()
	local left, top = Coordinate(ObjectiveTrackerFrame:GetLeft()), Coordinate(ObjectiveTrackerFrame:GetTop())
	local scale = ObjectiveTrackerFrame:GetEffectiveScale()
	if ObjectiveTrackerFrame:IsShown() then
		if left and top then
			shownCorner = { left, top, scale }
		end
	elseif shownCorner then
		return shownCorner[1], shownCorner[2], shownCorner[3]
	end
	return left, top, scale
end
-- Where the column goes under the game's quest tracker: its top left corner on the tracker's last visible line. That is
-- the bottom of the tracker's NineSlice, which Blizzard anchors under its last shown section; the bottom of its header
-- while the player has it collapsed, since its sections hide then but the NineSlice keeps their old anchor; or the
-- tracker's top while it is hidden with nothing to show. Returns that x and y in the host's own units, nil before the
-- client has placed the tracker. These are reads only; nothing here writes to the tracker or hooks it.
---@param shows "questie"|"hidden"|"collapsed"|"list"
---@return number? x, number? top
local function TrackerEdge(shows)
	local hostScale = host:GetEffectiveScale()
	local list = shows == "questie" and QuestieList()
	if list then
		local listLeft, listBottom = Coordinate(list:GetLeft()), Coordinate(list:GetBottom())
		if not (listLeft and listBottom) then
			return nil
		end
		local listScale = list:GetEffectiveScale()
		return listLeft * listScale / hostScale, listBottom * listScale / hostScale
	end
	local left, top, trackerScale = TrackerRect()
	local edge = shows == "list" and ObjectiveTrackerFrame.NineSlice
		or shows == "collapsed" and ObjectiveTrackerFrame.Header
		or nil
	local bottom, scale
	if edge then
		bottom, scale = edge:GetBottom(), edge:GetEffectiveScale()
	else
		bottom, scale = top, trackerScale
	end
	bottom = Coordinate(bottom)
	if not (left and bottom) then
		return nil
	end
	return left * trackerScale / hostScale, bottom * scale / hostScale
end
local AddPlacementMenu
-- The bars the column keeps clear of: the main bar and the extra bars parked at the bottom of the screen, then the two
-- parked on its right. A bar the player has not got, has hidden, or has parked elsewhere takes no room, so this reads
-- whatever the player's own layout put on screen rather than assuming the default one.
local ACTION_BARS = {
	"MainMenuBar",
	"MultiBarBottomLeft",
	"MultiBarBottomRight",
	"MultiBar5",
	"MultiBar6",
	"MultiBar7",
	"MultiBarRight",
	"MultiBarLeft",
}
-- How far down and how far right the column may reach from `top` without covering an action bar, both in the host's own
-- units: `floor` is the top of the highest bar under the column's width, so the column stops above the bars the way
-- TrackerEdge stops it at the tracker's line, and `right` is the left edge of the nearest bar beside the column's
-- height, so a right-hand bar is never grown over. No bar in the way leaves `floor` at 0 and `right` at the screen's
-- width, which is the room the column had before it read them. Bars are read through their own scale, as the tracker
-- is, and nothing here anchors to one or hooks one: the column holds protected quest item buttons, so an anchor to a
-- bar would bring the bar into the column's protected chain.
---@param left number the column's left edge
---@param width number
---@param top number the column's top edge
---@param height number
---@return number floor, number right
local function BarRoom(left, width, top, height)
	local hostScale = host:GetEffectiveScale()
	local floor, right = 0, UIParent:GetWidth() / (hostScale / UIParent:GetEffectiveScale())
	-- A column the client has not placed yet has no rect to measure against, and takes no room from itself.
	if type(left) ~= "number" or type(width) ~= "number" or type(top) ~= "number" or type(height) ~= "number" then
		return floor, right
	end
	local low = top - height
	for _, name in ipairs(ACTION_BARS) do
		local bar = rawget(_G, name)
		if type(bar) == "table" and bar.IsShown and bar:IsShown() then
			local barLeft, barTop = bar:GetLeft(), bar:GetTop()
			local barWidth, barHeight = bar:GetWidth(), bar:GetHeight()
			if barLeft and barTop and barWidth and barHeight and barWidth > 0 and barHeight > 0 then
				local scale = bar:GetEffectiveScale() / hostScale
				local barLeftHost, barTopHost = barLeft * scale, barTop * scale
				local barRightHost, barBottomHost = barLeftHost + barWidth * scale, barTopHost - barHeight * scale
				-- A bar wider than it is tall lies across the screen and takes room from below; a taller one stands at a
				-- side and takes room from beside. Orientation is the whole test, so a bar the player parked anywhere,
				-- at the top, the bottom or either side, is judged by the shape it has rather than by where the default
				-- layout would have put it.
				if barWidth >= barHeight then
					if barTopHost < top and barRightHost > left and barLeftHost < left + width then
						floor = math.max(floor, barTopHost)
					end
				elseif barBottomHost < top and barTopHost > low and barLeftHost >= left then
					right = math.min(right, barLeftHost)
				end
			end
		end
	end
	return floor, right
end
-- The whole cluster includes the zone name bar. Compare its edges in the column's units.
local function MinimapTop(left, width, top)
	local cluster = rawget(_G, "MinimapCluster")
	if type(cluster) ~= "table" or type(cluster.IsShown) ~= "function" or not cluster:IsShown() then
		return top
	end
	local mapLeft, mapRight, bottom =
		Coordinate(cluster:GetLeft()), Coordinate(cluster:GetRight()), Coordinate(cluster:GetBottom())
	if mapLeft and mapRight and bottom then
		local scale = cluster:GetEffectiveScale() / host:GetEffectiveScale()
		if left < mapRight * scale and left + width > mapLeft * scale then
			return math.min(top, bottom * scale)
		end
	end
	return top
end

local function UnderX(x, width, right)
	return math.max(0, math.min(x, right - width))
end

---@param shows "questie"|"hidden"|"collapsed"|"list"
---@param width number
---@param height number
---@return number? x, number? top, number? floor
local function UnderPosition(shows, width, height)
	local edge, line = TrackerEdge(shows)
	if not (edge and line) then
		return nil
	end
	local floor, right = BarRoom(edge, width, line, height)
	local x = UnderX(edge, width, right)
	local top = MinimapTop(x, width, line)
	if top < line or x ~= edge then
		floor = BarRoom(x, width, top, height)
	end
	return x, top, floor
end

-- Whether the column now sits under the quest tracker rather than at its pin to the left.
local under = false
-- The vertical room the last layout pass gave the column's sections.
local lastAvailable
local function SetColumnPoint(point, relativePoint, x, y)
	local current, relative, anchor, offsetX, offsetY = host:GetPoint()
	if current ~= point or relative ~= UIParent or anchor ~= relativePoint or offsetX ~= x or offsetY ~= y then
		host:ClearAllPoints()
		host:SetPoint(point, UIParent, relativePoint, x, y)
	end
end

---@param tracker Frame
---@return number? left, number? top
local function TrackerCorner(tracker)
	local left, top, scale
	if tracker == ObjectiveTrackerFrame then
		left, top, scale = TrackerRect()
	else
		left, top, scale = Coordinate(tracker:GetLeft()), Coordinate(tracker:GetTop()), tracker:GetEffectiveScale()
	end
	scale = scale / host:GetEffectiveScale()
	return left and left * scale, top and top * scale
end

local function PinLeft()
	local left, top = TrackerCorner(QuestieList() or ObjectiveTrackerFrame)
	if left and top then
		local width = host:GetWidth() or 0
		SetColumnPoint("TOPRIGHT", "BOTTOMLEFT", left, MinimapTop(left - width, width, top))
		under = false
	end
end
-- Puts a column placed under the quest tracker on the tracker's last line when the whole column, as its last layout
-- measured it, fits between that line and the screen's bottom, and at its pin to the left when it does not. When
-- stayUnder is on, the column stays under the tracker and lays out its sections in the room left instead of pinning
-- left. It is one SetPoint on UIParent and never a layout unless stayUnder needs to resize sections to a new room.
-- The column holds protected quest item buttons, so it is placed at coordinates rather than anchored to the tracker:
-- an anchor would bring the tracker's own frames into the column's protected chain, which the engine moves in combat.
-- Combat runs none of this, and PLAYER_REGEN_ENABLED's layout puts the column where the tracker's line has gone.
-- A locked column holds the place it has, as a dragged one does, until the player picks a place again, except that it
-- never runs off the screen.
local placeAgain = false
-- Whether this session has placed the column by the tracker's line at least once.
local followed = false
-- Whether the column's rect and Questie's list overlap, which a player dragging the list onto a column that holds its
-- place brings about. The column never covers the list it sits beside.
---@param list Frame?
---@return boolean
local function CoversList(list)
	if not list then
		return false
	end
	local scale = list:GetEffectiveScale() / host:GetEffectiveScale()
	local listLeft, listRight = Coordinate(list:GetLeft()), Coordinate(list:GetRight())
	local listTop, listBottom = Coordinate(list:GetTop()), Coordinate(list:GetBottom())
	local left, right = Coordinate(host:GetLeft()), Coordinate(host:GetRight())
	local top, bottom = Coordinate(host:GetTop()), Coordinate(host:GetBottom())
	if not (listLeft and listRight and listTop and listBottom and left and right and top and bottom) then
		return false
	end
	listLeft, listRight, listTop, listBottom = listLeft * scale, listRight * scale, listTop * scale, listBottom * scale
	return left < listRight and listLeft < right and bottom < listTop and listBottom < top
end
-- A locked column keeps its position until a growing list or the minimap takes that space.
local function LockedUnderPosition(shows, width, height)
	local x = host:GetLeft() or 0
	local heldTop = host:GetTop() or 0
	if CoversList(QuestieList()) then
		local underX, underTop, underFloor = UnderPosition(shows, width, height)
		if underX and underTop and underFloor then
			return underX, underTop, underFloor
		end
	end
	local _, line = TrackerEdge(shows)
	local top = MinimapTop(x, width, line and math.min(heldTop, line) or heldTop)
	local floor = BarRoom(x, width, top, height)
	return x, top, floor
end

local function AvailableHeight(top, floor)
	return math.max(24, top - (floor or 0))
end

-- With no section to show, the column hides until the next layout finds content.
local function FitSections(width, available)
	host:Show()
	lastAvailable = available
	host:SetShown(LayoutModules(width, available))
end

local function PlaceUnder(settings, x, top, floor, allowLayout)
	if settings.stayUnder and allowLayout then
		local available = AvailableHeight(top, floor)
		if available ~= lastAvailable then
			FitSections(host:GetWidth(), available)
		end
	end
	SetColumnPoint("TOPLEFT", "BOTTOMLEFT", x, top)
	under = true
	followed = true
end

---@param settings ForeverTrackerSettings
---@param allowLayout? boolean
local function FollowTracker(settings, allowLayout)
	if (settings.x and settings.y) or Drag.Dragging() or InCombatLockdown() then
		return
	end
	if settings.placement == "left" then
		PinLeft()
		return
	end
	-- Lock holds the place the column has, except for Under's no-room fallback: a locked column under the tracker that no
	-- longer fits under the list's last line, or would run past the screen's bottom from where it is, takes the left
	-- place, as an unlocked one would. With stayUnder on, it stays under the tracker and lays out in the room left.
	local shows = TrackerShows()
	if settings.locked and followed and not placeAgain then
		if not under then
			PinLeft()
		elseif settings.stayUnder then
			local x, top, floor = LockedUnderPosition(shows, host:GetWidth(), host:GetHeight())
			PlaceUnder(settings, x, top, floor, allowLayout)
		else
			local _, line = TrackerEdge(shows)
			local x, width = host:GetLeft() or 0, host:GetWidth() or 0
			local heldTop = host:GetTop() or 0
			local top = MinimapTop(x, width, heldTop)
			local height = host:GetHeight() or 0
			local floor = BarRoom(x, width, top, height)
			if height > (line or math.huge) - floor or height > top - floor or CoversList(QuestieList()) then
				PinLeft()
			elseif top < heldTop then
				SetColumnPoint("TOPLEFT", "BOTTOMLEFT", x, top)
			end
		end
		return
	end
	local width = host:GetWidth() or 0
	local height = host:GetHeight() or 0
	local x, top, floor = UnderPosition(shows, width, height)
	-- A tracker the client has not placed yet says nothing about room: the column waits at the pin until it has a line,
	-- and once placed keeps its place.
	if not (x and top and floor) then
		if not followed then
			PinLeft()
		end
		return
	end
	placeAgain = false
	if not settings.stayUnder and height > top - floor then
		PinLeft()
		return
	end
	PlaceUnder(settings, x, top, floor, allowLayout)
end
-- Layout measures the room from the tracker's top, capped by the minimap when they overlap, or from the tracker's last
-- line when stayUnder is on. Once the column's height is known, FollowTracker places it below the last line or left.
-- Both placements use screen coordinates so the column has no anchor to the tracker.
---@param settings ForeverTrackerSettings
---@return number width, number top, number? floor
local function Anchor(settings)
	local scale = host:GetEffectiveScale() / UIParent:GetEffectiveScale()
	local screenWidth, screenHeight = UIParent:GetWidth() / scale, UIParent:GetHeight() / scale
	local width = math.min(WIDTH, screenWidth)
	host:SetWidth(width)
	-- Keep the column in place while our own header is being dragged. Blizzard's Edit Mode drag is followed above.
	if Drag.Dragging() then
		return width, host:GetTop() or screenHeight
	end
	if settings.x and settings.y then
		host:ClearAllPoints()
		local x = math.max(0, math.min(settings.x / scale, math.max(0, screenWidth - width)))
		local y = math.min(0, math.max(settings.y / scale, 24 - screenHeight))
		host:SetPoint("TOPLEFT", UIParent, "TOPLEFT", x, y)
		under = false
		return width, screenHeight + y
	end
	if settings.placement == "under" then
		local height = host:GetHeight() or screenHeight
		if settings.stayUnder then
			local shows = TrackerShows()
			if settings.locked and followed and under and not placeAgain then
				local _, top, floor = LockedUnderPosition(shows, width, height)
				return width, top, floor
			end
			local _, top, floor = UnderPosition(shows, width, height)
			if top then
				return width, top, floor
			end
		end
		local left, top = TrackerCorner(QuestieList() or ObjectiveTrackerFrame)
		if top then
			local layoutLeft = left or 0
			local capped = MinimapTop(layoutLeft - width, width, top)
			if MinimapTop(0, screenWidth, top) < top then
				local x
				if settings.locked and followed and under and not placeAgain then
					x = host:GetLeft() or layoutLeft
				else
					local edge, line = TrackerEdge(TrackerShows())
					local _, right = BarRoom(edge or layoutLeft, width, line or top, height)
					x = UnderX(edge or layoutLeft, width, right)
				end
				-- Fit both Under and its Left fallback if the quest list is too long.
				capped = math.min(capped, MinimapTop(x, width, top))
			end
			local floor = BarRoom(layoutLeft, width, capped, height)
			return width, capped, floor
		end
	end
	PinLeft()
	local pinnedLeft = host:GetLeft() or 0
	local pinnedTop = MinimapTop(pinnedLeft, width, host:GetTop() or screenHeight)
	local pinnedFloor = BarRoom(pinnedLeft, width, pinnedTop, host:GetHeight() or screenHeight)
	return width, pinnedTop, pinnedFloor
end

local function Place(settings)
	host:Show()
	local width, top, floor = Anchor(settings)
	FitSections(width, AvailableHeight(top, floor))
	FollowTracker(settings)
end

local function Layout()
	queued = false
	-- A queued pass that found combat holds the whole column exactly as it was. The client marks every item button
	-- protected, and their ancestors up to the host are protected with them, so no layout may move or show anything.
	-- PLAYER_REGEN_ENABLED marks the host dirty again for the pass this one could not run.
	if InCombatLockdown() then
		return
	end
	local settings = Settings()
	ApplyBackdrop(settings)
	MatchScale()
	Place(settings)
end

-- The column's own methods, given to the frame when Start makes it.
---@class ForeverTrackerColumnMethods
local column = {}
function column.MarkDirty(_)
	-- Combat queues nothing: the column holds its last layout until PLAYER_REGEN_ENABLED runs the deferred pass.
	-- The protected quest item buttons, and every ancestor that moves with them, stay where the player last saw them.
	if ready and not queued and not InCombatLockdown() then
		queued = true
		C_Timer.After(0, Layout)
	end
end
-- The column has no collapse of its own; each section folds itself.
function column.IsCollapsed(_)
	return false
end
function column:ForceExpand()
	self:MarkDirty()
end

function api.GetSettings()
	return Settings()
end
---@return number
function api.GetScale()
	return Settings().scale or 1
end
-- Only the host scales, so a change applies at the next layout, in combat too.
---@param value number
function api.SetScale(value)
	if type(value) ~= "number" or value ~= value then
		return
	end
	local settings = Settings()
	local scale = math.max(MIN_SCALE, math.min(MAX_SCALE, value))
	if settings.scale == scale then
		return
	end
	settings.scale = scale
	host:MarkDirty()
end
-- The tracker background, from 0 (off) to 1 (opaque as the tooltip draws it). A change only recolours the texture, so
-- it applies at once in combat as well.
---@return number
function api.GetBackdropOpacity()
	return Settings().backdropOpacity
end
---@param value number
function api.SetBackdropOpacity(value)
	if type(value) ~= "number" or value ~= value then
		return
	end
	local settings = Settings()
	local opacity = Opacity(value)
	if settings.backdropOpacity == opacity then
		return
	end
	settings.backdropOpacity = opacity
	ApplyBackdrop(settings)
end
---@return boolean
function api.IsLocked()
	return IsLocked()
end
---@param value boolean
function api.SetLocked(value)
	Settings().locked = not not value
end
-- Addons' attach checkboxes, told when the column starts or stops following the tracker so they show its state.
---@type (fun(attached: boolean))[]
local attachmentCallbacks = {}
-- Called with the state before a change, and calls back only when it changed, so a callback that writes the same
-- value back through SetAttached ends there instead of recursing.
---@param before boolean
local function NotifyAttachment(before)
	local attached = Settings().attached
	if attached == before then
		return
	end
	for _, callback in ipairs(attachmentCallbacks) do
		RunSafe(nil, "OnAttachmentChanged", callback, attached)
	end
end
-- "under" (the default) or "left" of the game's quest tracker. A dragged column keeps its saved choice, which applies
-- again once the player picks a place.
---@return "under"|"left"
function api.GetPlacement()
	return Settings().placement
end
-- Picking a place releases a dragged position, so the column goes there. It only writes the setting, so it is safe in
-- combat; the move waits for the next layout, which combat defers.
---@param value "under"|"left"
function api.SetPlacement(value)
	if value ~= "under" and value ~= "left" then
		return
	end
	local settings = Settings()
	local before = settings.attached
	settings.placement = value
	settings.x, settings.y = nil, nil
	placeAgain = true
	host:MarkDirty()
	NotifyAttachment(before)
end
-- When true and placement is "under", the column stays under the quest tracker instead of falling back to the left pin
-- when space is short, and its sections lay out in the room left below the tracker's last line.
---@return boolean
function api.GetStayUnder()
	return Settings().stayUnder == true
end
---@param value boolean
function api.SetStayUnder(value)
	local settings = Settings()
	local enabled = not not value
	if settings.stayUnder == enabled then
		return
	end
	settings.stayUnder = enabled
	placeAgain = true
	host:MarkDirty()
end
-- Whether the column follows a place, rather than a position the player dragged it to.
---@return boolean
local function Placed()
	local settings = Settings()
	return not (settings.x and settings.y)
end
-- The "Attach to quest tracker" checkbox addons still ship: attached is the Under placement with no dragged position,
-- and turning it off picks Left.
function api.IsAttachedToQuestTracker()
	return Settings().attached
end
---@param value boolean
function api.SetAttached(value)
	api.SetPlacement(value and "under" or "left")
end
---@param callback fun(attached: boolean)
function api.OnAttachmentChanged(callback)
	if type(callback) == "function" then
		attachmentCallbacks[#attachmentCallbacks + 1] = callback
	end
end
-- A drag saves a free position, which releases the pin.
function api.SavePosition(x, y)
	if type(x) ~= "number" or type(y) ~= "number" then
		return
	end
	local settings = Settings()
	local before = settings.attached
	settings.x, settings.y = x, y
	host:MarkDirty()
	NotifyAttachment(before)
end

-- The Tracker position choice, the same in every section's menu. Neither radio is ticked while the column sits where it
-- was dragged; picking one moves it there.
---@param menu table
AddPlacementMenu = function(menu)
	local L = ns.L
	local position = menu:CreateButton(L["Tracker position"])
	for _, choice in ipairs({ { "under", L["Under the quest tracker"] }, { "left", L["Left of the quest tracker"] } }) do
		position:CreateRadio(choice[2], function()
			return Placed() and api.GetPlacement() == choice[1]
		end, function()
			api.SetPlacement(choice[1])
		end)
	end
	position:CreateDivider()
	position:CreateCheckbox(L["Always stay under the quest tracker"], api.GetStayUnder, function()
		api.SetStayUnder(not api.GetStayUnder())
	end)
end

-- Declarative menu slots keep every section and block shaped alike. The wrapper deliberately exposes only the small
-- contract, so a consumer cannot put an action after Tracker or accidentally omit the end action.
local function NewTrackerMenu(root, module, target)
	---@class ForeverTrackerMenuSlots
	---@field title? string
	---@field primary? ForeverMenuDescription
	---@field actions ForeverMenuDescription[]
	---@field open? ForeverMenuDescription
	---@field ending? ForeverMenuDescription
	local slots = { actions = {} }
	local menu = {}
	local function Entry(text, fn, opts)
		local entry = ns.NewMenuDescription("button", text)
		if type(fn) ~= "function" then
			return entry
		end
		entry.onClick = function()
			local ok, accepted, reason = RunSafe(module.safeCall, "tracker menu action", fn)
			if ok and accepted == false and not (opts and opts.reported) then
				ReportRefusal(reason or text)
			end
			return accepted, reason
		end
		if opts and opts.combat then
			entry:SetEnabled(not InCombatLockdown())
			entry.onClick = function()
				if InCombatLockdown() then
					local reason = ns.L["Unavailable in combat"]
					ReportRefusal(reason)
					return false, reason
				end
				local ok, accepted, reason = RunSafe(module.safeCall, "tracker menu action", fn)
				if ok and accepted == false and not (opts and opts.reported) then
					ReportRefusal(reason or text)
				end
				return accepted, reason
			end
			entry:SetTooltip(function(tooltip)
				tooltip:SetText(text, 1, 1, 1)
				if InCombatLockdown() then
					tooltip:AddLine(ns.L["Unavailable in combat"], nil, nil, nil, true)
				end
			end)
		end
		return entry
	end
	function menu.Title(_, text)
		slots.title = slots.title or text
	end
	function menu.Primary(_, text, fn)
		slots.primary = slots.primary or Entry(text, fn)
		return slots.primary
	end
	function menu.Action(_, text, fn, opts)
		local entry = Entry(text, fn, opts)
		slots.actions[#slots.actions + 1] = entry
		return entry
	end
	function menu:Submenu(text)
		return self:Action(text)
	end
	function menu.Open(_, text, fn, where)
		if type(fn) == "string" then
			local addon = fn
			slots.open = slots.open
				or Entry(text, function()
					return ns.Open(addon, where)
				end, { combat = true, reported = true })
			return slots.open
		end
		slots.open = slots.open or Entry(text, fn, { combat = true })
		return slots.open
	end
	function menu.End(_, text, fn)
		if type(fn) == "function" then
			slots.ending = slots.ending or Entry(text, fn)
		end
		return slots.ending
	end
	local finished = false
	local function Finish()
		if finished then
			return
		end
		finished = true
		local block = target.block
		root:CreateTitle(
			slots.title
				or (block and block.HeaderText and block.HeaderText:GetText())
				or (module.Header and module.Header.Text and module.Header.Text:GetText())
				or ns.L["Tracker"]
		)
		local function Append(entry)
			if entry then
				root.entries[#root.entries + 1] = entry
			end
		end
		Append(slots.primary)
		for _, entry in ipairs(slots.actions) do
			Append(entry)
		end
		Append(slots.open)
		Append(slots.ending)
		root:CreateDivider()
		-- Lock sits on the menu itself, not in the Tracker submenu, so a locked column is unlocked from any right-click.
		if api.IsLocked and api.SetLocked then
			root:CreateCheckbox(ns.L["Lock the tracker"], api.IsLocked, function()
				api.SetLocked(not api.IsLocked())
			end)
		end
		local tracker = root:CreateButton(ns.L["Tracker"] or "Tracker")
		AddPlacementMenu(tracker)
		local background = tracker:CreateButton(ns.L["Tracker background"])
		background:CreateRadio(rawget(_G, "OFF") or "Off", function()
			return api.GetBackdropOpacity() == 0
		end, function()
			api.SetBackdropOpacity(0)
		end)
		for _, percent in ipairs({ 25, 50, 75, 100 }) do
			local value = percent / 100
			background:CreateRadio(percent .. "%", function()
				return api.GetBackdropOpacity() == value
			end, function()
				api.SetBackdropOpacity(value)
			end)
		end
		local show = module.show
		if type(show) == "table" and type(show.get) == "function" and type(show.set) == "function" then
			tracker:CreateButton(ns.L["Hide this section"], function()
				if show.get() then
					show.set(false)
				end
			end)
		end
	end
	return menu, Finish
end

-- A consumer can forward a block title click to its tracker menu contract here.
function api.HandleBlockHeaderClick(module, block, button)
	if type(module) ~= "table" or type(module.trackerMenu) ~= "function" then
		return false
	end
	local target = { kind = "block", id = block and block.id, block = block, module = module }
	if button == "LeftButton" and type(module.trackerClick) == "function" then
		local ok, accepted, reason =
			RunSafe(module.safeCall, "tracker block click", module.trackerClick, target, button)
		if ok and accepted == false then
			ReportRefusal(reason)
		end
		return true
	end
	if button == "RightButton" then
		ns.ContextMenu(module:GetContextMenuParent(), function(_, root)
			local builder, finish = NewTrackerMenu(root, module, target)
			RunSafe(module.safeCall, "tracker block menu", module.trackerMenu, target, builder)
			finish()
		end)
		return true
	end
	return false
end

-- Open the declarative section menu or show the column controls for a section without one.
---@param module ForeverTrackerModule
local function AddHeaderMenu(module)
	local header = module.Header
	if not header or module.headerMenu then
		return
	end
	module.headerMenu = true
	local L = ns.L
	local lock = L["Lock the tracker"]
	local background = L["Tracker background"]
	local hide = L["Hide this section"]
	header:EnableMouse(true)
	Drag.Attach(header)
	header:HookScript("OnMouseUp", function(_, button)
		local target = { kind = "section", module = module }
		if button ~= "RightButton" then
			-- Letting go of a drag is not a click.
			if Drag.Dragged() then
				return
			end
			if type(module.trackerClick) == "function" then
				local ok, accepted, reason =
					RunSafe(module.safeCall, "tracker section click", module.trackerClick, target, button)
				if ok and accepted == false then
					ReportRefusal(reason)
				end
			elseif type(module.OnHeaderClick) == "function" then
				RunSafe(module.safeCall, "tracker section header", module.OnHeaderClick, module, button)
			end
			return
		end
		ns.ContextMenu(module:GetContextMenuParent(), function(_, root)
			if module.trackerMenu then
				local builder, finish = NewTrackerMenu(root, module, target)
				RunSafe(module.safeCall, "tracker section menu", module.trackerMenu, target, builder)
				finish()
				return
			end
			if api.IsLocked and api.SetLocked then
				root:CreateCheckbox(lock, api.IsLocked, function()
					api.SetLocked(not api.IsLocked())
				end)
			end
			AddPlacementMenu(root)
			-- Every section's menu offers the same background choices, so no addon has to wire a settings row of its
			-- own. The values are the saved fractions the host draws, and picking one only recolours the texture.
			local backgroundMenu = root:CreateButton(background)
			backgroundMenu:CreateRadio(rawget(_G, "OFF") or "Off", function()
				return api.GetBackdropOpacity() == 0
			end, function()
				api.SetBackdropOpacity(0)
			end)
			for _, percent in ipairs({ 25, 50, 75, 100 }) do
				local value = percent / 100
				backgroundMenu:CreateRadio(percent .. "%", function()
					return api.GetBackdropOpacity() == value
				end, function()
					api.SetBackdropOpacity(value)
				end)
			end
			-- A section with its own show switch offers hiding itself here, and the entry's tooltip names where the
			-- switch lives. Only the addon's own setting is written, so this is safe in combat like the switches above.
			local show = module.show
			if
				type(show) == "table"
				and type(show.get) == "function"
				and type(show.set) == "function"
				and type(show.where) == "string"
			then
				local showSafe = show.safeCall or module.safeCall
				local entry = root:CreateButton(hide, function()
					local ok, visible = RunSafe(showSafe, "tracker section show", show.get)
					if ok and visible then
						RunSafe(showSafe, "tracker section show", show.set, false)
					end
				end)
				entry:SetTooltip(function(tooltip)
					tooltip:SetText(hide, 1, 1, 1)
					tooltip:AddLine(show.where, nil, nil, nil, true)
				end)
			end
		end)
	end)
end

-- The store exists from here on, before any section attaches, so the column takes its saved scale and place now. The
-- first layout pass only lays the sections out, and a reload never moves the column (#795).
local function Migrate()
	CopyLegacy()
	-- The host's own repair settles a bad scale, opacity or coordinate the way every other read does.
	local settings = Settings()
	if not InCombatLockdown() then
		host:SetScale(settings.scale)
		Anchor(settings)
	end
	host:MarkDirty()
end

-- Core.lua's Start (converted copies) or its one ADDON_LOADED handler (transitional unwrapped standalone) calls this
-- after the runtime store exists, so a first install completes the copy.
ns.MigrateTrackerSettings = Migrate

---@param module ForeverTrackerModule
---@param show? ForeverTrackerShowSetting the section's own show switch, when it has one
function api.Attach(module, show, contract)
	---@cast module ForeverTrackerModule
	if InCombatLockdown() then
		pendingAttachments[module] = { show = show, contract = contract }
		return
	end
	if show ~= nil then
		module.show = show
	end
	if type(contract) == "table" then
		module.trackerMenu = contract.menu
		module.trackerClick = contract.click
		module.trackerClickHint = contract.clickHint
	end
	if OfferLegacy(module) then
		Migrate()
	end
	if module.parentContainer == host then
		return
	end
	-- A module from Blizzard's own template has the header and contents model the scroll wrapper needs. A test double
	-- or an addon's hand-built frame keeps its own Update and GetContentsHeight.
	module.trackerScrollable = type(module.headerHeight) == "number" and module.ContentsFrame ~= nil
	module.baseUpdate = module.Update
	module.baseUpdateHeight = module.UpdateHeight
	module.baseGetContentsHeight = module.GetContentsHeight
	module.baseIsTruncated = module.IsTruncated
	module.baseCanFitBlock = module.CanFitBlock
	module.baseBeginLayout = module.BeginLayout
	Mixin(module, Module)
	modules[#modules + 1] = module
	module:SetContainer(host)
	AddHeaderMenu(module)
	host:MarkDirty()
end
-- Only the registered section's cap changes here. Geometry stays in the host's queued layout, including combat.
---@param module ForeverTrackerModule
---@param value? number nil restores the default 200-unit cap
---@return boolean accepted
function api.SetSectionMaxHeight(module, value)
	if not api.IsAttached(module) then
		return false
	end
	if value ~= nil and (Coordinate(value) == nil or value < 0) then
		return false
	end
	module.trackerMaxHeight = value
	host:MarkDirty()
	return true
end
function api.IsAttached(module)
	---@cast module ForeverTrackerModule?
	return module ~= nil and module.parentContainer == host
end
-- From the pinned Blizzard_ObjectiveTracker event registrations.
-- Each event can cause a Blizzard tracker module to mark its layout dirty.
-- Cooldown, quest blob, death count and proving grounds score updates only change existing controls.
local TRACKER_LAYOUT_EVENTS = {
	["ACHIEVEMENT_EARNED"] = true,
	["ACTIVE_DELVE_DATA_UPDATE"] = true,
	["BAG_UPDATE_DELAYED"] = true,
	["CHALLENGE_MODE_START"] = true,
	["CONTENT_TRACKING_UPDATE"] = true,
	["CRITERIA_COMPLETE"] = true,
	["CURRENCY_DISPLAY_UPDATE"] = true,
	["HOUSE_DECOR_ADDED_TO_CHEST"] = true,
	["INITIATIVE_TASKS_TRACKED_LIST_CHANGED"] = true,
	["INITIATIVE_TASKS_TRACKED_UPDATED"] = true,
	["NEIGHBORHOOD_INITIATIVE_UPDATED"] = true,
	["PERKS_ACTIVITIES_TRACKED_LIST_CHANGED"] = true,
	["PERKS_ACTIVITIES_TRACKED_UPDATED"] = true,
	["PERKS_ACTIVITY_COMPLETED"] = true,
	["QUEST_ACCEPTED"] = true,
	["QUEST_AUTOCOMPLETE"] = true,
	["QUEST_LOG_UPDATE"] = true,
	["QUEST_POI_UPDATE"] = true,
	["QUEST_REMOVED"] = true,
	["QUEST_TURNED_IN"] = true,
	["QUEST_WATCH_LIST_CHANGED"] = true,
	["SCENARIO_BONUS_VISIBILITY_UPDATE"] = true,
	["SCENARIO_COMPLETED"] = true,
	["SCENARIO_CRITERIA_SHOW_STATE_UPDATE"] = true,
	["SCENARIO_CRITERIA_UPDATE"] = true,
	["SCENARIO_SPELL_UPDATE"] = true,
	["SCENARIO_UPDATE"] = true,
	["SUPER_TRACKING_CHANGED"] = true,
	["SUPER_TRACKING_PATH_UPDATED"] = true,
	["TRACKABLE_INFO_UPDATE"] = true,
	["TRACKED_ACHIEVEMENT_LIST_CHANGED"] = true,
	["TRACKED_ACHIEVEMENT_UPDATE"] = true,
	["TRACKED_RECIPE_UPDATE"] = true,
	["TRACKING_TARGET_INFO_UPDATE"] = true,
	["TRANSMOG_COLLECTION_SOURCE_ADDED"] = true,
	["UNIT_AURA"] = true,
	["WORLD_STATE_TIMER_START"] = true,
	["WORLD_STATE_TIMER_STOP"] = true,
	["ZONE_CHANGED"] = true,
	["ZONE_CHANGED_NEW_AREA"] = true,
}
-- Combat ending attaches the sections combat held back. Combat starting freezes every section's scrollbar, so
-- each secure item button stays beside its quest.
local function Listen()
	-- A separate frame can settle even when the column is hidden. It has no script between events.
	local settle = CreateFrame("Frame")
	local watching, needsLayout, needsPlacement = false, false, false
	local elapsed, frames, quiet = 0, 0, 0
	local lastShows, lastLeft, lastLine
	local function StopSettling()
		settle:SetScript("OnUpdate", nil)
		watching, needsLayout, needsPlacement = false, false, false
	end
	local function Sample(_, delta)
		if InCombatLockdown() then
			StopSettling()
			return
		end
		elapsed, frames = elapsed + delta, frames + 1
		local shows = TrackerShows()
		local left, line = TrackerEdge(shows)
		if shows ~= lastShows or left ~= lastLeft or line ~= lastLine then
			lastShows, lastLeft, lastLine = shows, left, line
			needsPlacement, quiet = true, 0
		else
			quiet = quiet + 1
		end

		if needsPlacement and (frames >= 2 or elapsed >= 1) and not ObjectiveTrackerFrame.isDragging then
			if not queued then
				if needsLayout then
					Layout()
				else
					FollowTracker(Settings(), true)
				end
			end
			needsLayout, needsPlacement = false, false
		end
		-- Questie may start rebuilding half a second after the event. Cap each burst at one second
		-- so ongoing layout changes cannot keep the frame script running indefinitely.
		if elapsed >= 1 or (quiet >= 3 and (shows ~= "questie" or elapsed >= 0.6)) then
			StopSettling()
		end
	end

	-- A Blizzard Edit Mode nudge moves the tracker without a layout event, so while Edit Mode is open one frame follows
	-- the edge when it changes. A drag holds the column where it is, and the frame follows once the drag ends. It stops
	-- when Edit Mode exits and in combat, so no OnUpdate outlives Edit Mode.
	local watch = CreateFrame("Frame")
	local dragWatching, dragHeld, watchShows, watchLeft, watchLine
	local function WatchMove()
		if InCombatLockdown() then
			dragWatching = false
			watch:SetScript("OnUpdate", nil)
			return
		end
		local dragging = ObjectiveTrackerFrame.isDragging
		local shows = TrackerShows()
		local left, line = TrackerEdge(shows)
		if not dragging and (dragHeld or shows ~= watchShows or left ~= watchLeft or line ~= watchLine) then
			if not queued then
				FollowTracker(Settings(), true)
			end
		end
		dragHeld, watchShows, watchLeft, watchLine = dragging, shows, left, line
	end
	local function StartWatching()
		if dragWatching or InCombatLockdown() then
			return
		end
		dragWatching = true
		dragHeld, watchShows, watchLeft, watchLine = false, nil, nil, nil
		watch:SetScript("OnUpdate", WatchMove)
	end
	local function StopWatching()
		dragWatching = false
		watch:SetScript("OnUpdate", nil)
	end

	local function Recheck(layout)
		if not ready or InCombatLockdown() then
			return
		end
		needsLayout, needsPlacement = needsLayout or layout, true
		quiet = 0
		if not watching then
			watching, elapsed, frames = true, 0, 0
			settle:SetScript("OnUpdate", Sample)
		end
	end
	EventRegistry:RegisterCallback("EditMode.Enter", StartWatching, host)
	EventRegistry:RegisterCallback("EditMode.Exit", function()
		StopWatching()
		Recheck(true)
	end, host)

	-- Questie can build its list asynchronously after login. Stop sampling once it has geometry or the
	-- discovery window ends. Subsequent movement and visibility changes are handled by events.
	local discovering, remaining = false, 0
	local function DiscoverQuestie()
		remaining = 8
		if discovering then
			return
		end
		discovering = true
		local function Discover()
			local list = QuestieList()
			if list and list:GetLeft() and list:GetTop() and list:GetBottom() then
				discovering = false
				if not queued then
					Recheck(true)
				end
			elseif remaining > 0 then
				remaining = remaining - 1
				C_Timer.After(1, Discover)
			else
				discovering = false
			end
		end
		Discover()
	end

	host:RegisterEvent("PLAYER_REGEN_ENABLED")
	host:RegisterEvent("PLAYER_REGEN_DISABLED")
	host:RegisterEvent("DISPLAY_SIZE_CHANGED")
	host:RegisterEvent("UI_SCALE_CHANGED")
	host:RegisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
	host:RegisterEvent("PLAYER_ENTERING_WORLD")
	host:RegisterEvent("GLOBAL_MOUSE_UP")
	for event in pairs(TRACKER_LAYOUT_EVENTS) do
		if event == "UNIT_AURA" then
			host:RegisterUnitEvent(event, "player")
		else
			host:RegisterEvent(event)
		end
	end
	host:RegisterEvent("ADDON_LOADED")
	host:SetScript("OnEvent", function(_, event, addon)
		if event == "ADDON_LOADED" then
			if addon == "Questie" and ready then
				DiscoverQuestie()
			end
			return
		end
		if event == "PLAYER_ENTERING_WORLD" and ready then
			DiscoverQuestie()
		end
		if event == "PLAYER_REGEN_ENABLED" then
			for module, attachment in pairs(pendingAttachments) do
				pendingAttachments[module] = nil
				api.Attach(module, attachment.show, attachment.contract)
			end
		end
		if event == "PLAYER_REGEN_DISABLED" or event == "PLAYER_REGEN_ENABLED" then
			local frozen = event == "PLAYER_REGEN_DISABLED"
			for _, module in ipairs(modules) do
				if module.SetScrollFrozen then
					module:SetScrollFrozen(frozen)
				end
			end
		end
		if event == "PLAYER_REGEN_ENABLED" then
			host:MarkDirty()
		elseif event == "PLAYER_REGEN_DISABLED" then
			StopSettling()
			StopWatching()
		else
			Recheck(event ~= "GLOBAL_MOUSE_UP" and not TRACKER_LAYOUT_EVENTS[event])
		end
	end)
	return DiscoverQuestie
end
-- A developer diagnostic for the tracker stack (/agf tracker). The combat overlap is otherwise invisible headlessly: it
-- prints both frames' anchors, heights and who each is anchored to.
---@return string
function api.Debug()
	-- Raw literals on purpose: this host is shared with the companion addons, whose ns.L has no AGF keys, and
	-- lint_copy only rejects literals passed straight to Print/SetText (this returns a string instead).
	local function point(frame)
		local p = { frame:GetPoint() }
		local relative = p[2] == host and "host" or tostring(p[2])
		return ("%s rel %s %s %.1f,%.1f"):format(
			tostring(p[1]),
			relative,
			tostring(p[3]),
			tonumber(p[4]) or 0,
			tonumber(p[5]) or 0
		)
	end
	local function geometry(frame)
		return ("%.1f,%.1f-%.1f,%.1f s%.2f"):format(
			frame:GetLeft() or -1,
			frame:GetTop() or -1,
			frame:GetRight() or -1,
			frame:GetBottom() or -1,
			frame:GetEffectiveScale()
		)
	end
	return ("combat=%s shown=%s under=%s hostH=%.1f host[%s] g[%s] uiS%.2f"):format(
		tostring(InCombatLockdown()),
		tostring(host:IsShown()),
		tostring(under),
		host:GetHeight() or -1,
		point(host),
		geometry(host),
		UIParent:GetEffectiveScale()
	)
end

ns.TrackerHost = api

ns.AtStart(function()
	host = CreateFrame("Frame", "ForeverTrackerCompanion", UIParent) --[[@as ForeverTrackerColumn]]
	for key, method in pairs(column) do
		host[key] = method
	end
	-- The column starts at its pin, so it never shows anywhere else before the store's anchor (#795).
	MatchScale()
	host:SetWidth(WIDTH)
	host:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", 0, 0)
	PinLeft()
	host:SetHeight(1)
	host:SetMovable(true)
	host:SetClampedToScreen(true)
	Drag = ns.TrackerLock.Drag(host, api)
	backdrop = host:CreateTexture(nil, "BACKGROUND")
	-- art-ok: the tooltip's own centre fill, a tiling texture stretched to the column by design
	backdrop:SetAtlas(BACKDROP_ATLAS)
	backdrop:SetPoint("TOPLEFT", host, "TOPLEFT", -BACKDROP_INSET, BACKDROP_INSET)
	backdrop:SetPoint("BOTTOMRIGHT", host, "BOTTOMRIGHT", BACKDROP_INSET, -BACKDROP_INSET)
	backdrop:Hide()
	pools = CreateFramePoolCollection()
	local discoverQuestie = Listen()
	ns.AfterWorldEvents(function()
		ready = true
		host:MarkDirty()
		discoverQuestie()
	end)
	ForeverTrackerHost = api -- taint-ok: addon-owned companion tracker registry
end)
