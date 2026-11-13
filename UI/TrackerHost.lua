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
---@field AddHeaderMenuEntries? fun(self: ForeverTrackerModule, root: any) a section's own entries, after the column's
---@field trackerMenu? fun(target: ForeverTrackerTarget, menu: ForeverTrackerMenuBuilder) the declarative menu contract
---@field trackerClick? fun(target: ForeverTrackerTarget, button: string) the declarative click contract
---@field trackerClickHint? fun(target: ForeverTrackerTarget): string? the localized click action
---@field trackerClickHint? fun(target: ForeverTrackerTarget): string? the localized action name shown in the block
-- tooltip
---@field trackerBlockMenuWrapped? boolean
---@field OnBlockHeaderClick? fun(self: ForeverTrackerModule, block: any, button: string)

---@class ForeverNativeTrackerHeader : Frame
---@field Text FontString
---@field MinimizeButton Button

-- The client's own objective tracker is the module container its Quests and Campaign sections belong to, so taking a
-- module out of it and giving it back are the container's own methods (UI/TrackerQuests.lua calls both).
---@class ForeverNativeTrackerFrame : Frame
---@field Header ForeverNativeTrackerHeader
---@field NineSlice Frame?
---@field isCollapsed? boolean
---@field AddModule fun(self: ForeverNativeTrackerFrame, module: any)
---@field RemoveModule fun(self: ForeverNativeTrackerFrame, module: any)
---@field HasModule fun(self: ForeverNativeTrackerFrame, module: any): boolean

-- Sharing the native tracker collection also shares its Edit Mode execution path.
-- Keep our sections and their frame pools entirely outside that collection.
if not ObjectiveTrackerFrame then
	return
end

-- A consumer's old tracker settings, offered once by the first module that attaches with a `legacySettings` table.
-- Saved variables are not there while the files load, so the copy waits for ForeverCore's ADDON_LOADED.
local pendingLegacy

-- Copy the first legacy table offered into ForeverCoreDB.trackerHost, once. Each field is taken only when it has the
-- shape the host reads; the rest keep the fresh defaults. Later offers are ignored. True when it copied.
---@return boolean
local function CopyLegacy()
	if type(ForeverCoreDB) ~= "table" or pendingLegacy == nil then
		return false
	end
	local legacy = pendingLegacy
	pendingLegacy = nil
	local settings = ns.TrackerHostSettings()
	if settings.migrated == true then
		return false
	end
	for field, kind in pairs({
		attached = "boolean",
		locked = "boolean",
		scale = "number",
		backdropOpacity = "number",
		x = "number",
		y = "number",
	}) do
		if type(legacy[field]) == kind then
			settings[field] = legacy[field]
		end
	end
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
		"GetScale",
		"GetSettings",
		"IsAttached",
		"IsAttachedToQuestTracker",
		"IsLocked",
		"OnAttachmentChanged",
		"SavePosition",
		"SetAttached",
		"SetLocked",
		"SetScale",
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
	-- The consumer drops its own tracker table once it attaches, so keep the first one offered for ForeverCoreDB,
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
	-- Core's own tracker files must not run against a column core did not build; UI/TrackerQuests.lua reads this.
	ns.TrackerHostForeign = true
	return
end

local host = CreateFrame("Frame", "ForeverTrackerCompanion", UIParent)
---@class ForeverTrackerHostAPI
local api = {}
local MIN_SCALE, MAX_SCALE = 0.5, 2
local fallbackSettings = { attached = true, scale = 1, backdropOpacity = 0 }
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
---@return ForeverTrackerSettings
local function Settings()
	local settings = ns.TrackerHostSettings and ns.TrackerHostSettings() or fallbackSettings
	if type(settings.attached) ~= "boolean" then
		settings.attached = true
	end
	settings.locked = settings.locked == true
	local scale = settings.scale
	if type(scale) ~= "number" or scale ~= scale then
		settings.scale = 1
	else
		settings.scale = math.max(MIN_SCALE, math.min(MAX_SCALE, scale))
	end
	settings.backdropOpacity = Opacity(settings.backdropOpacity)
	settings.x, settings.y = Coordinate(settings.x), Coordinate(settings.y)
	return settings
end
local attached
local dragging = false
local attachmentCallbacks = {}
-- The native tracker is protected and keeps the slot Blizzard, Edit Mode or a UI addon gave it: this host never moves
-- it, in combat or out. The private column reads below it, so the header and the game's quests come first and the
-- Forever sections follow, and the same placement runs in and out of combat, so entering or leaving combat moves
-- nothing. The sections stay outside Blizzard's secure module collection.
local function StackPoints(point)
	if point == "CENTER" or point == "TOP" or point == "BOTTOM" then
		return "TOP", "BOTTOM"
	end
	local horizontal = point:find("RIGHT", 1, true) and "RIGHT" or "LEFT"
	return "TOP" .. horizontal, "BOTTOM" .. horizontal
end
host:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", 0, 0)
-- The column's scale follows the frame it sits beside: the native tracker when it is really visible, another
-- tracker's list frame, or UIParent when detached or the native tracker is hidden or transparent, as a replacement UI
-- may leave it.
local function NativeScaleSource()
	local frame = ObjectiveTrackerFrame
	if not frame then
		return UIParent
	end
	-- IsVisible is effective visibility: the frame and every ancestor shown. A shown tracker under a hidden parent
	-- is not visible, so it must not be the scale source. IsShown is only a fallback for a stub with no IsVisible.
	local shown
	if frame.IsVisible then
		shown = frame:IsVisible()
	elseif frame.IsShown then
		shown = frame:IsShown()
	end
	local alpha = 1
	if frame.GetEffectiveAlpha then
		alpha = frame:GetEffectiveAlpha()
	elseif frame.GetAlpha then
		alpha = frame:GetAlpha()
	end
	if shown and (alpha or 0) > 0 then
		return frame
	end
	return UIParent
end
local function MatchScale(source)
	if not (source and source.GetEffectiveScale) then
		source = UIParent
	end
	local parentScale = UIParent:GetEffectiveScale()
	local sourceScale = source:GetEffectiveScale()
	if parentScale and sourceScale and parentScale > 0 then
		-- Saved variables, and with them the user's scale, are not ready while the files load.
		local userScale = ready and Settings().scale or 1
		host:SetScale(sourceScale / parentScale * userScale)
	end
end
MatchScale(UIParent)
host:SetWidth(ObjectiveTrackerFrame:GetWidth())
host:SetHeight(1)
host:SetMovable(true)
host:SetClampedToScreen(true)
-- The grip and the Lock switch that suppresses its drag live in their own file (UI/TrackerLock.lua), which the TOC
-- loads before this one. It hands back the label redraw for a Lock change and the show switch for the attachment.
local Grip = ns.TrackerLock.Grip(host, api)
-- The optional backdrop spans the whole private column, so every Forever section sits on it at once. It is one
-- texture on the host rather than chrome each addon draws, and it uses the game's own tooltip background art, tinted
-- the way the tooltip tints it. Off is simply opacity 0; drawing it only changes a texture, never a frame, so the
-- slider is safe to move in combat.
local BACKDROP_ATLAS = "Tooltip-NineSlice-Center"
local BACKDROP_INSET = 6
local backdrop = host:CreateTexture(nil, "BACKGROUND")
-- art-ok: the tooltip's own centre fill, a tiling texture stretched to the column by design
backdrop:SetAtlas(BACKDROP_ATLAS)
-- No inset at the top: the attached column starts at the native quests' bottom edge, so the backdrop must not reach
-- up over the last quest line. It pads the sides and the bottom instead.
backdrop:SetPoint("TOPLEFT", host, "TOPLEFT", -BACKDROP_INSET, 0)
backdrop:SetPoint("BOTTOMRIGHT", host, "BOTTOMRIGHT", BACKDROP_INSET, -BACKDROP_INSET)
backdrop:Hide()

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
local pools = CreateFramePoolCollection()

local function NotifyAttachment(value)
	for _, callback in ipairs(attachmentCallbacks) do
		callback(value)
	end
end

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

-- Every section but the one that fills the rest of the column caps at this many UI units. The Quests section asks for
-- the room the others leave, so a long quest list scrolls while Legacy's zone and SkillUp's reagents stay in view.
local SECTION_MAX_HEIGHT = 200
local SCROLL_GUTTER = 18 -- the bar's track plus the item frame's overhang and its spacing
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

---@param offset number
function Module:SetScrollOffset(offset)
	if InCombatLockdown() then
		return
	end
	local range = self.scrollRange or 0
	offset = math.max(0, math.min(range, tonumber(offset) or 0))
	self.scrollOffset = offset
	if self.scrollFrame then
		self.scrollFrame:SetVerticalScroll(offset)
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
	local index = self:TopBlockIndex(starts)
	local target = index + (delta > 0 and -1 or 1)
	target = math.max(1, math.min(#starts, target))
	if target == index then
		return
	end
	self:SetScrollOffset(target == 1 and 0 or starts[target].start)
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

-- Builds the viewport once, on the first attach, out of core's own frames. The scroll child is the module's own
-- ContentsFrame, so every block and every pooled line keeps its parent and its anchors.
function Module:CreateTrackerScroll()
	if self.scrollFrame or not self.ContentsFrame or not self.Header then
		return
	end
	local scroll = CreateFrame("ScrollFrame", nil, self)
	scroll:SetPoint("TOPLEFT", self.Header, "BOTTOMLEFT", 0, 0)
	scroll:SetPoint("TOPRIGHT", self.Header, "BOTTOMRIGHT", 0, 0)
	scroll:SetHeight(0)
	scroll:EnableMouseWheel(true)
	scroll:SetScript("OnMouseWheel", function(_, delta)
		self:OnTrackerWheel(delta)
	end)
	local contents = self.ContentsFrame
	contents:ClearAllPoints()
	scroll:SetScrollChild(contents)
	contents:SetPoint("TOPLEFT", scroll, "TOPLEFT", 0, 0)
	-- Creation happens before the column gives the module its width, so keep a real width here: the first Update
	-- measures its text in this width, and LayoutTrackerScroll marks the module dirty when the gutter changes it.
	local contentsWidth = math.max(0, self:GetWidth() or 0)
	contents:SetWidth(contentsWidth)
	contents:SetHeight(0)
	self.scrollContentsWidth = contentsWidth
	self.scrollFrame = scroll

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

-- Sizes the viewport to the cap the column gave this section, shows the bar only when the blocks pass it, and holds
-- the view on the quest at the top. `headerHeight` and `contentsHeight` are Blizzard's own numbers.
function Module:LayoutTrackerScroll()
	if not self.scrollFrame or InCombatLockdown() then
		return
	end
	local header = self.headerHeight or 0
	local body = math.max(0, (self.contentsHeight or 0) - header)
	local cap = self.trackerCap or body
	local viewport = math.min(body, math.max(0, cap - header))
	local range = math.max(0, body - viewport)
	self.trackerBody, self.trackerViewport, self.scrollRange = body, viewport, range
	self.trackerOverflow = range > 0

	local width = math.max(0, (self:GetWidth() or 0) - (range > 0 and SCROLL_GUTTER or 0))
	local contents = self.ContentsFrame
	contents:SetPoint("TOPLEFT", self.scrollFrame, "TOPLEFT", 0, 0)
	if self.scrollContentsWidth ~= width then
		self.scrollContentsWidth = width
		contents:SetWidth(width)
		-- The text was measured in the old width, so a gutter change needs one more layout pass at the new one.
		self:MarkDirty()
	end
	contents:SetHeight(body)
	self.scrollFrame:SetHeight(viewport)
	self.scrollFrame:SetPoint("TOPRIGHT", self.Header, "BOTTOMRIGHT", range > 0 and -SCROLL_GUTTER or 0, 0)

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
	elseif not collapsed and body > 0 then
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

function Module:Update(availableHeight, dirtyUpdate)
	self.trackerCap = availableHeight
	if type(self.baseUpdate) == "function" then
		return self.baseUpdate(self, availableHeight, dirtyUpdate)
	end
end

function Module:BeginLayout()
	self:CaptureScrollAnchor()
	if type(self.baseBeginLayout) == "function" then
		self.baseBeginLayout(self)
	end
end

local function OverlapsMinimap()
	local minimap = _G.Minimap
	if not minimap or not minimap:IsShown() then
		return false
	end
	local left, right, top, bottom = host:GetLeft(), host:GetRight(), host:GetTop(), host:GetBottom()
	local ml, mr, mt, mb = minimap:GetLeft(), minimap:GetRight(), minimap:GetTop(), minimap:GetBottom()
	local hostScale = host:GetEffectiveScale()
	local mapScale = minimap:GetEffectiveScale()
	local screen = UIParent:GetEffectiveScale()
	if not (left and right and top and bottom and ml and mr and mt and mb) then
		return false
	end
	left, right, top, bottom =
		left * hostScale / screen, right * hostScale / screen, top * hostScale / screen, bottom * hostScale / screen
	ml, mr, mt, mb = ml * mapScale / screen, mr * mapScale / screen, mt * mapScale / screen, mb * mapScale / screen
	return left < mr and right > ml and bottom < mt and top > mb
end

local function AvoidMinimap(point)
	if not OverlapsMinimap() then
		return
	end
	host:ClearAllPoints()
	if point:find("LEFT", 1, true) then
		host:SetPoint("TOPLEFT", ObjectiveTrackerFrame, "TOPRIGHT", 0, 0)
	else
		host:SetPoint("TOPRIGHT", ObjectiveTrackerFrame, "TOPLEFT", 0, 0)
	end
end

local function SidePoint(point)
	local left, right = ObjectiveTrackerFrame:GetLeft(), ObjectiveTrackerFrame:GetRight()
	local screen = UIParent:GetWidth()
	local nativeScale = ObjectiveTrackerFrame:GetEffectiveScale()
	local screenScale = UIParent:GetEffectiveScale()
	if left and right and screen and nativeScale > 0 and screenScale > 0 then
		local nativeCenter = (left + right) * nativeScale / (2 * screenScale)
		return nativeCenter <= screen / 2 and "LEFT" or "RIGHT"
	end
	return point:find("LEFT", 1, true) and "LEFT" or "RIGHT"
end

-- The list's left, right and top in the host's own scale, whether it is a real frame (Questie) or the normalised
-- bounds table UI/TrackerEqot.lua returns.
local function ListEdges(list)
	if list.left then
		return list.left, list.right, list.top
	end
	-- A frame the client has not placed yet answers nil, and multiplying that would throw inside the layout.
	local left, right, top = list:GetLeft(), list:GetRight(), list:GetTop()
	if not (left and right and top) then
		return nil
	end
	local toHost = list:GetEffectiveScale() / host:GetEffectiveScale()
	return left * toHost, right * toHost, top * toHost
end

-- Where a detached column sits until the player drags it: beside the quest list (the native tracker, Questie's or
-- EQOT's) and level with its top, so neither draws over the other. To its left when the column fits there, otherwise
-- to its right. Offsets are from UIParent's top left corner in the host's own scale; the caller keeps them on screen.
local function Beside(list, width, screenHeight)
	local left, right, top = ListEdges(list)
	if not (left and right and top) then
		return 0, -40
	end
	local x = left - 8 - width
	if x < 0 then
		x = right + 8
	end
	return x, top - screenHeight
end

-- UI/TrackerEqot.lua and UI/TrackerQuestie.lua, loaded first, find the quest list another tracker draws over the
-- native slot (a host loaded without either ignores that addon). EQOT is the more specific cover, since it hides the
-- native frame, so its list is consulted before Questie's.
local TrackerEqot = ns.TrackerEqot
	or {
		List = function() end,
		Await = function() end,
		Room = function()
			return 0
		end,
		Places = function()
			return {}
		end,
	}
local TrackerQuestie = ns.TrackerQuestie or { List = function() end, Await = function() end }
-- EllesmereUI's custom quest tracker, consulted after EQOT and before Questie: its list is the one a player who chose
-- it sees, even while its own visibility rules hide the frame.
local TrackerEllesmere = ns.TrackerEllesmere or { List = function() end, Await = function() end }
-- Whether the last attached layout went round another addon's list, which one, and the room it gave the sections.
---@type boolean, boolean, boolean, boolean, number
local besideList, besideQuestie, besideEqot, besideEllesmere, displacedRoom = false, false, false, false, 0
-- Whether the last attached layout put the column above or beside the tracker instead of below the quests.
local aside = false

-- Blizzard's Edit Mode owns the native slot while its manager is on screen. The manager can also be hidden and locked
-- without exiting (CheckHideAndLockEditMode), which leaves editModeActive true with no EditMode.Exit: a hidden manager
-- is not editing, and its own show and hide reflow, or the column would stay hidden after the lock.
local managerHooked = false
local function HookEditMode()
	local manager = EditModeManagerFrame
	if managerHooked or not manager then
		return
	end
	managerHooked = true
	manager:HookScript("OnShow", host.MarkDirty)
	manager:HookScript("OnHide", host.MarkDirty)
end

local function Editing()
	local manager = EditModeManagerFrame
	return not not (manager and manager:IsEditModeActive() and manager:IsShown())
end

-- Native methods remain untouched so controller and combat paths retain their secure execution.
local nativeHeader = ObjectiveTrackerFrame.Header --[[@as ForeverNativeTrackerHeader?]]

local function NativeCollapsed()
	return ObjectiveTrackerFrame.isCollapsed == true
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
	if reason and DEFAULT_CHAT_FRAME and DEFAULT_CHAT_FRAME.AddMessage then
		DEFAULT_CHAT_FRAME:AddMessage(tostring(reason))
	end
end

-- The cap a section gets from the column. A scrollable section never takes more than 200 units, except the one that
-- asks for the rest of the column (the quest list), which is measured after the others have laid themselves out.
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
	return math.min(available, math.max(0, maximum))
end

-- Lays every section out from the host's top, each in the room the ones above it left, less the gap under it, so the
-- column never runs past `available`. Returns whether any section drew. One section's layout error is recorded in its
-- own journal and leaves the sections below it to lay out, instead of breaking the whole column.
--
-- A section with `trackerMaxHeight == "remaining"` gets what the capped sections above and below it leave, so the
-- quest list is the one that scrolls. It is laid out after the others so their real heights are known first.
local function LayoutModules(width, available, reserve)
	ns.TrackerOrder.Sort(modules)
	local restIndex
	for index, module in ipairs(modules) do
		if module.trackerScrollable and module.trackerMaxHeight == "remaining" then
			restIndex = restIndex or index
		end
	end
	local heights, total = {}, 0
	local function LayOut(index, cap)
		local module = modules[index]
		module:SetWidth(width)
		local ok = RunSafe(module.safeCall, "tracker section update", module.Update, module, cap)
		local used = ok and module:GetContentsHeight() or 0
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
	local height = hasSections and reserve or 0
	for index, module in ipairs(modules) do
		module:ClearAllPoints()
		module:SetPoint("TOPLEFT", host, "TOPLEFT", 0, -height)
		local used = heights[index]
		if used > 0 then
			height = height + used + GAP
		end
	end
	host:SetHeight(math.max(1, height))
	return hasSections
end
-- Switches the host between attached and detached when the settings or combat state allow, and returns the settings
-- that chose the mode.
local function ApplyAttachment()
	local settings = Settings()
	local desired = settings.attached ~= false
	if attached == nil or not InCombatLockdown() then
		attached = desired
	end
	return settings
end

-- Detached: the private column sits wherever the player dragged it, independent of the native tracker.
local function LayoutDetached(settings)
	aside = false
	host:Show()
	local scale = host:GetEffectiveScale() / UIParent:GetEffectiveScale()
	local screenWidth, screenHeight = UIParent:GetWidth() / scale, UIParent:GetHeight() / scale
	local width = math.min(ObjectiveTrackerFrame:GetWidth(), screenWidth)
	host:SetWidth(width)
	if dragging then
		return
	end
	local x, y
	if settings.x and settings.y then
		x, y = settings.x / scale, settings.y / scale
	else
		local list = TrackerEqot.List(host, host.MarkDirty)
			or TrackerEllesmere.List(host, host.MarkDirty)
			or TrackerQuestie.List(host, host.MarkDirty)
		x, y = Beside(list or ObjectiveTrackerFrame, width, screenHeight)
	end
	x = math.max(0, math.min(x, math.max(0, screenWidth - width)))
	y = math.min(0, math.max(y, 24 - screenHeight))
	host:ClearAllPoints()
	host:SetPoint("TOPLEFT", UIParent, "TOPLEFT", x, y)
	-- With no section to show, the column hides entirely, its title too; the next layout with content shows it again.
	if not LayoutModules(width, math.max(24, screenHeight + y - 24), 24) then
		host:Hide()
		return
	end
	y = math.min(0, math.max(y, math.min(host:GetHeight(), screenHeight) - screenHeight))
	host:ClearAllPoints()
	host:SetPoint("TOPLEFT", UIParent, "TOPLEFT", x, y)
end

-- Attached: the column reads below the native tracker's visible content, measured from its own content region, so the
-- column is the header, the game's quests, then the Forever sections. Only our frames move, and this runs only from
-- Layout, which defers in combat so the protected item buttons and their ancestors stay put. A collapsed All
-- Objectives hides the sections with it.
local function LayoutAttached()
	-- Read the global each time, not once at load: Blizzard_EditMode is load-on-demand, so it may appear later. A
	-- manager hidden while still active is a locked Edit Mode, which owns nothing on screen, so the column shows.
	HookEditMode()
	if Editing() then
		return
	end
	local point = ObjectiveTrackerFrame:GetPoint()
	if not point then
		-- The native frame is between anchors (an Edit Mode or managed-frame transition): hold the column where it is
		-- until the move that follows reflows it.
		return
	end
	if NativeCollapsed() then
		host:Hide()
		aside = false
		return
	end
	host:Show()
	local layoutScale = host:GetEffectiveScale()
	local layoutScreenScale = UIParent:GetEffectiveScale()
	local nativeScale = ObjectiveTrackerFrame:GetEffectiveScale()
	-- The column takes the native tracker's own left and right edges, converted into the host's units, so every
	-- Forever section lines up with the game's sections at any scale. The width is clamped to the screen the way the
	-- detached column's already is.
	local width = ObjectiveTrackerFrame:GetWidth() * nativeScale / layoutScale
	host:SetWidth(math.min(width, UIParent:GetWidth() * layoutScreenScale / layoutScale))
	host:ClearAllPoints()
	-- The column hangs from the bottom of the native content region (NineSlice, which Blizzard anchors to its last
	-- module), so it follows the quests as they grow or shrink with no reflow of ours. A native tracker with nothing to
	-- show hides itself, and Questie hides it too: then the column takes its slot from the top. Blizzard anchors the
	-- NineSlice's top corners to the tracker asymmetrically, so its centre is not the tracker's: the anchor's x offset is
	-- the measured gap between the two centres, in the host's units, which puts the column on the tracker's own edges.
	---@type Frame, FramePoint
	local edge, edgePoint = ObjectiveTrackerFrame, "TOP"
	if ObjectiveTrackerFrame:IsShown() then
		edge, edgePoint = ObjectiveTrackerFrame.NineSlice or ObjectiveTrackerFrame, "BOTTOM"
	end
	local nativeCentre = ObjectiveTrackerFrame:GetCenter() or 0
	local edgeCentre = edge:GetCenter() or 0
	local offsetX = (nativeCentre * nativeScale - edgeCentre * edge:GetEffectiveScale()) / layoutScale
	local function Below()
		host:ClearAllPoints()
		host:SetPoint("TOP", edge, edgePoint, offsetX, 0)
	end
	Below()
	local contentBottom = edgePoint == "TOP" and edge:GetTop() or edge:GetBottom()
	local layoutMargin = 24 * layoutScreenScale / layoutScale
	contentBottom = (contentBottom or 0) * edge:GetEffectiveScale() / layoutScale
	local roomBelow = math.max(0, contentBottom - layoutMargin)
	local screenHeight = (UIParent:GetHeight() or 0) * layoutScreenScale / layoutScale
	local screenRoom = math.max(0, screenHeight - layoutMargin)
	-- Puts the column above the tracker when there is room there, otherwise to the side away from the tracker's
	-- anchored edge, so it stays visible without overlapping the protected frame.
	local function Aside()
		local nativePoint, hostPoint = StackPoints(point)
		host:ClearAllPoints()
		local nativeTop = ObjectiveTrackerFrame:GetTop() or 0
		local screenTop = UIParent:GetHeight() or nativeTop
		local room = screenTop * layoutScreenScale - nativeTop * nativeScale
		if room >= math.max(host:GetHeight() or 0, 1) * layoutScale then
			host:SetPoint(hostPoint, ObjectiveTrackerFrame, nativePoint, 0, 0)
		elseif SidePoint(point) == "LEFT" then
			host:SetPoint("TOPLEFT", ObjectiveTrackerFrame, "TOPRIGHT", 0, 0)
		else
			host:SetPoint("TOPRIGHT", ObjectiveTrackerFrame, "TOPLEFT", 0, 0)
		end
		AvoidMinimap(point)
	end
	-- A layout pass is not a measurement: Blizzard's EndLayout hides a section that fits nothing and its
	-- FreeUnusedBlocks releases every block, so laying the sections out below just to probe the room replays each
	-- header's add animation and rebuilds every block. `aside` remembers that the column went above or beside the
	-- tracker last time, so only the real move off the room below pays that replay. A column already aside lays out
	-- once in the screen's room, and moves back below when the whole laid-out column fits there, with no second pass.
	if aside then
		if not LayoutModules(host:GetWidth(), screenRoom, 0) then
			host:Hide()
			return
		end
		if (host:GetHeight() or 0) <= roomBelow then
			Below()
			aside = false
			return
		end
		Aside()
		return
	end
	-- The sections shrink to the room below the quests: a tall section shows what fits there and never sends the
	-- column elsewhere.
	if LayoutModules(host:GetWidth(), roomBelow, 0) then
		aside = false
		return
	end
	-- No section fits below at all (quests ending at the bottom of the screen). The one pass that shows them above or
	-- beside the tracker is a real move, so it pays the replay once; the next layout stays there without one.
	if not LayoutModules(host:GetWidth(), screenRoom, 0) then
		host:Hide()
		return
	end
	aside = true
	Aside()
end

-- Attached while another addon's list covers the native slot: the column goes below, above or beside it and the
-- native tracker keeps its slot. Only our frames move, and this runs only from Layout, which defers in combat; with
-- `list` nil (the addon hid its list in combat) the column keeps its last place until the next out-of-combat pass.
---@param list ForeverTrackerEqotList|Frame?
---@param kind "eqot"|"ellesmere"|"questie"?
local function LayoutBesideList(list, kind)
	if Editing() then
		return
	end
	besideList = true
	aside = false
	besideEqot, besideEllesmere, besideQuestie = kind == "eqot", kind == "ellesmere", kind == "questie"
	if not list then
		host:SetShown(LayoutModules(host:GetWidth(), displacedRoom, 0))
		return
	end
	local module = TrackerQuestie
	if kind == "eqot" then
		module = TrackerEqot
	elseif kind == "ellesmere" then
		module = TrackerEllesmere
	end
	host:Show()
	local scale = host:GetEffectiveScale() / UIParent:GetEffectiveScale()
	local screenWidth, screenHeight = UIParent:GetWidth() / scale, UIParent:GetHeight() / scale
	local width = math.min(ObjectiveTrackerFrame:GetWidth(), screenWidth)
	host:SetWidth(width)
	displacedRoom = module.Room(list, host)
	if not LayoutModules(width, displacedRoom, 0) then
		host:Hide()
		return
	end
	local besideX = Beside(list, width, screenHeight)
	local places = module.Places(list, host, besideX, screenWidth, screenHeight)
	for index, place in ipairs(places) do
		host:ClearAllPoints()
		host:SetPoint(place[1], UIParent, place[1], place[2], place[3])
		if index == #places or not OverlapsMinimap() then
			return
		end
	end
end

local function Layout()
	queued = false
	-- A queued pass that found combat holds the whole column exactly as it was. The client marks every item button
	-- protected, and their ancestors up to the host are protected with them, so no layout may move or show anything.
	-- PLAYER_REGEN_ENABLED marks the host dirty again for the pass this one could not run.
	if InCombatLockdown() or Editing() then
		return
	end
	local settings = ApplyAttachment()
	ApplyBackdrop(settings)
	Grip.Show(not attached)
	-- Settle the host's scale before a list is normalised into it. EQOT's list is always in host units, and its
	-- source is UIParent, so this is also its final scale; the native tracker's and a Questie frame's are set below.
	MatchScale(UIParent)
	if not attached then
		besideList, besideQuestie, besideEqot, besideEllesmere = false, false, false, false
		LayoutDetached(settings)
		return
	end
	local eqot = TrackerEqot.List(host, host.MarkDirty)
	if eqot then
		LayoutBesideList(eqot, "eqot")
		return
	end
	local ellesmere = TrackerEllesmere.List(host, host.MarkDirty)
	if ellesmere then
		MatchScale(ellesmere)
		LayoutBesideList(ellesmere, "ellesmere")
		return
	end
	local questie = TrackerQuestie.List(host, host.MarkDirty)
	if questie then
		MatchScale(questie)
		LayoutBesideList(questie, "questie")
		return
	end
	-- Both lists are away, so the column lays itself out below the native tracker again.
	besideList, besideQuestie, besideEqot, besideEllesmere = false, false, false, false
	-- A hidden or transparent native tracker, as a replacement UI leaves it, is not the frame the column sits beside.
	MatchScale(NativeScaleSource())
	LayoutAttached()
end

function host.MarkDirty(_)
	-- Combat queues nothing: the column holds its last layout until PLAYER_REGEN_ENABLED runs the deferred pass.
	-- The protected quest item buttons, and every ancestor that moves with them, stay where the player last saw them.
	if ready and not queued and not InCombatLockdown() then
		queued = true
		C_Timer.After(0, Layout)
	end
end
-- Questie or EQOT hides the native tracker and its header, so a collapsed All Objectives no longer hides the sections.
function host.IsCollapsed(_)
	return attached == true and not besideList and NativeCollapsed()
end
function host:ForceExpand()
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
	Grip.SetLabel(value)
end
function api.IsAttachedToQuestTracker()
	return Settings().attached ~= false
end
function api.SetAttached(value)
	value = not not value
	local settings = Settings()
	if settings.attached == value then
		return
	end
	settings.attached = value
	NotifyAttachment(value)
	host:MarkDirty()
end
function api.OnAttachmentChanged(callback)
	attachmentCallbacks[#attachmentCallbacks + 1] = callback
end
function api.SavePosition(x, y)
	if attached or type(x) ~= "number" or type(y) ~= "number" then
		return
	end
	local settings = Settings()
	settings.x, settings.y = x, y
	host:MarkDirty()
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
		entry.parent = root
		if type(fn) ~= "function" then
			return entry
		end
		entry.onClick = function()
			local ok, accepted, reason = RunSafe(module.safeCall, "tracker menu action", fn)
			if ok and accepted == false then
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
				if ok and accepted == false then
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
	end
	function menu.Action(_, text, fn, opts)
		local entry = Entry(text, fn, opts)
		slots.actions[#slots.actions + 1] = entry
		return entry
	end
	function menu:Submenu(text)
		return self:Action(text)
	end
	function menu.Open(_, text, fn)
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
		local tracker = root:CreateButton(ns.L["Tracker"] or "Tracker")
		tracker:CreateCheckbox(ns.L["Attach to quest tracker"], api.IsAttachedToQuestTracker, function()
			api.SetAttached(not api.IsAttachedToQuestTracker())
		end)
		if api.IsLocked and api.SetLocked then
			tracker:CreateCheckbox(ns.L["Lock the tracker"], api.IsLocked, function()
				api.SetLocked(not api.IsLocked())
			end)
		end
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
		if
			target.kind == "section"
			and type(show) == "table"
			and type(show.get) == "function"
			and type(show.set) == "function"
		then
			tracker:CreateButton(ns.L["Hide this section"], function()
				if show.get() then
					show.set(false)
				end
			end)
		end
	end
	return menu, Finish
end

-- Consumers with a block implementation that has no legacy OnBlockHeaderClick can forward the title event here.
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

-- The column's own right-click menu, through core's shared context menu. A section may add its own entries after the
-- column's, without the host learning what the section is.
---@param module ForeverTrackerModule
local function AddHeaderMenu(module)
	local header = module.Header
	if not header or module.headerMenu then
		return
	end
	module.headerMenu = true
	local L = ns.L
	local attach = L["Attach to quest tracker"]
	local lock = L["Lock the tracker"]
	local background = L["Tracker background"]
	local hide = L["Hide this section"]
	header:EnableMouse(true)
	header:HookScript("OnMouseUp", function(_, button)
		local target = { kind = "section", module = module }
		if button ~= "RightButton" then
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
			root:CreateCheckbox(attach, api.IsAttachedToQuestTracker, function()
				api.SetAttached(not api.IsAttachedToQuestTracker())
			end)
			if api.IsLocked and api.SetLocked then
				root:CreateCheckbox(lock, api.IsLocked, function()
					api.SetLocked(not api.IsLocked())
				end)
			end
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
			-- A section may add its own entries after the column's, without the host learning what the section is.
			if type(module.AddHeaderMenuEntries) == "function" then
				RunSafe(module.safeCall, "tracker section menu", module.AddHeaderMenuEntries, module, root)
			end
		end)
	end)
end

local function Migrate()
	if CopyLegacy() then
		-- The host's own repair settles a bad scale, opacity or coordinate the way every other read does.
		Settings()
		host:MarkDirty()
	end
end

-- Core.lua's one ADDON_LOADED handler calls this after ForeverCoreDB exists, so a first install completes the copy.
ns.MigrateTrackerSettings = Migrate

---@param module ForeverTrackerModule
---@param show? ForeverTrackerShowSetting the section's own show switch, when it has one
function api.Attach(module, show, contract)
	---@cast module ForeverTrackerModule
	if type(contract) == "table" and contract.menu and type(module.AddHeaderMenuEntries) == "function" then
		RunSafe(module.safeCall, "tracker menu contract", function()
			error("tracker menu contract cannot be combined with deprecated AddHeaderMenuEntries")
		end)
		return
	end
	if show ~= nil then
		module.show = show
	end
	if type(contract) == "table" then
		module.trackerMenu = contract.menu
		module.trackerClick = contract.click
		module.trackerClickHint = contract.clickHint
		if
			module.trackerMenu
			and type(module.OnBlockHeaderClick) == "function"
			and not module.trackerBlockMenuWrapped
		then
			---@type fun(self: ForeverTrackerModule, block: any, button: string)
			local oldBlockClick = module.OnBlockHeaderClick
			module.trackerBlockMenuWrapped = true
			module.OnBlockHeaderClick = function(self, block, button)
				if not api.HandleBlockHeaderClick(module, block, button) then
					return oldBlockClick(self, block, button)
				end
			end
		end
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
function api.IsAttached(module)
	---@cast module ForeverTrackerModule?
	return module ~= nil and module.parentContainer == host
end
-- Combat ending applies an attachment change combat held back. Combat starting freezes every section's scrollbar, so
-- each secure item button stays beside its quest.
host:RegisterEvent("PLAYER_REGEN_ENABLED")
host:RegisterEvent("PLAYER_REGEN_DISABLED")
host:RegisterEvent("DISPLAY_SIZE_CHANGED")
host:RegisterEvent("UI_SCALE_CHANGED")
-- Native objective changes and managed-frame transitions can restore the tracker anchor.
-- Observe their events; wrapping its methods taints controller and secure layout paths.
for _, event in ipairs({
	"QUEST_LOG_UPDATE",
	"QUEST_WATCH_UPDATE",
	"QUEST_WATCH_LIST_CHANGED",
	"PLAYER_ALIVE",
	"PLAYER_DEAD",
	"PLAYER_UNGHOST",
	"ZONE_CHANGED_NEW_AREA",
}) do
	host:RegisterEvent(event)
end
host:SetScript("OnEvent", function(_, event)
	if event == "PLAYER_REGEN_DISABLED" or event == "PLAYER_REGEN_ENABLED" then
		local frozen = event == "PLAYER_REGEN_DISABLED"
		for _, module in ipairs(modules) do
			if module.SetScrollFrozen then
				module:SetScrollFrozen(frozen)
			end
		end
	end
	host:MarkDirty()
end)
ObjectiveTrackerFrame:HookScript("OnSizeChanged", function()
	host:MarkDirty()
end)
-- The layout takes the native tracker's top while it is hidden and its NineSlice's bottom while it is shown, so showing
-- or hiding it moves the column even when Edit Mode's fixed height means its size never changes and OnSizeChanged never
-- fires. Hooking the frame's own scripts leaves its Show and Hide methods, and the module layout they run, untouched.
-- MarkDirty's deferred pass runs after that layout, so the NineSlice already reads the new bottom when it is anchored.
ObjectiveTrackerFrame:HookScript("OnShow", host.MarkDirty)
ObjectiveTrackerFrame:HookScript("OnHide", host.MarkDirty)
-- The game's managed frame layout, Edit Mode and UI addons such as EllesmereUI move the native frame with no event of
-- their own. An addon-owned probe spans from the screen's bottom left corner to the native frame's top left corner, so
-- any move of the native frame resizes the probe and its OnSizeChanged reflows the column.
local probe = CreateFrame("Frame", nil, UIParent)
local probeEnabled = false
local function SetProbeEnabled(enabled)
	if probeEnabled == enabled then
		return
	end
	probeEnabled = enabled
	probe:ClearAllPoints()
	if enabled then
		probe:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", 0, 0)
		probe:SetPoint("TOPRIGHT", ObjectiveTrackerFrame, "TOPLEFT", 0, 0)
	end
end
probe:SetScript("OnSizeChanged", function()
	if probeEnabled then
		host:MarkDirty()
	end
end)
SetProbeEnabled(not Editing())
-- Collapsing "All Objectives" hides the shared sections too. Mark the host dirty on the click that flips it; the
-- native collapse method itself stays unhooked and untouched, and the native header keeps its parent so its button
-- resolves the native container normally.
if nativeHeader and nativeHeader.MinimizeButton then
	nativeHeader.MinimizeButton:HookScript("OnClick", function()
		host:MarkDirty()
	end)
end
-- Edit Mode restores Blizzard's saved anchor through its public callbacks. Reflow
-- on those events instead of polling the native frame every frame.
local function OnEditModeChanged()
	HookEditMode()
	local editing = Editing()
	SetProbeEnabled(not editing)
	if editing and attached then
		host:Hide()
		-- Hidden frames still participate in anchor dependencies; detach our column too.
		host:ClearAllPoints()
		host:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", 0, 0)
	else
		host:Show()
	end
	host:MarkDirty()
end
EventRegistry:RegisterCallback("EditMode.Enter", OnEditModeChanged, host)
EventRegistry:RegisterCallback("EditMode.Exit", OnEditModeChanged, host)
EventRegistry:RegisterCallback("EditMode.SavedLayouts", OnEditModeChanged, host)
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
	local form = "combat=%s shown=%s hostH=%.1f host[%s] g[%s] nativeH=%.1f native[%s] g[%s] uiS%.2f"
	return (form .. " questie=%s eqot=%s ellesmere=%s"):format(
		tostring(InCombatLockdown()),
		tostring(host:IsShown()),
		host:GetHeight() or -1,
		point(host),
		geometry(host),
		ObjectiveTrackerFrame:GetHeight() or -1,
		point(ObjectiveTrackerFrame),
		geometry(ObjectiveTrackerFrame),
		UIParent:GetEffectiveScale(),
		tostring(besideQuestie),
		tostring(besideEqot),
		tostring(besideEllesmere)
	)
end

EventUtil.ContinueAfterAllEvents(function()
	ready = true
	host:MarkDirty()
	TrackerEqot.Await(host.MarkDirty)
	TrackerEllesmere.Await(host.MarkDirty)
	TrackerQuestie.Await(host.MarkDirty)
end, "PLAYER_ENTERING_WORLD", "VARIABLES_LOADED")

ForeverTrackerHost = api -- taint-ok: addon-owned companion tracker registry
ns.TrackerHost = api
