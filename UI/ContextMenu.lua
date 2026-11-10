---@type string, ForeverTrackerNamespace
local _, ns = ...

-- Forever 70009 can assert in Blizzard_Menu.AcquireMenu, so the suite draws its context menus in frames of its own.
-- This is the one menu every Forever addon opens, with the same generator shape as MenuUtil.CreateContextMenu.
local Description = {}
Description.__index = Description

---@param kind ForeverMenuEntryKind
---@param text? string
---@return ForeverMenuDescription
local function New(kind, text)
	return setmetatable({ kind = kind, text = text, entries = {} }, Description) --[[@as ForeverMenuDescription]]
end

---@param text string
---@param action? fun()
---@return ForeverMenuDescription
function Description:CreateButton(text, action)
	local entry = New("button", text)
	entry.onClick, entry.parent = action, self --[[@as ForeverMenuDescription]]
	self.entries[#self.entries + 1] = entry
	return entry
end

function Description:CreateTitle(text)
	local entry = self:CreateButton(text)
	entry.kind = "title"
	return entry
end

function Description:CreateDivider()
	local entry = self:CreateButton("")
	entry.kind, entry.text = "divider", nil
	return entry
end

function Description:CreateCheckbox(text, selected, action)
	local entry = self:CreateButton(text, action)
	entry.kind, entry.isSelected = "checkbox", selected
	return entry
end

-- Blizzard's radio contract: setSelected gets the entry's data. The suite's text rows mark a radio as a checkbox.
---@param text string
---@param selected fun(data: any): boolean
---@param action fun(data: any)
---@param data? any
---@return ForeverMenuDescription
function Description:CreateRadio(text, selected, action, data)
	return self:CreateCheckbox(text, function()
		return selected(data)
	end, function()
		action(data)
	end)
end

function Description:SetEnabled(enabled)
	self.isEnabled = enabled
end

function Description:IsEnabled()
	if type(self.isEnabled) == "function" then
		return self.isEnabled()
	end
	return self.isEnabled ~= false
end

function Description:SetTooltip(tooltip)
	self.tooltip = tooltip
end

-- Blizzard's Menu API contract: this level's rows scroll past `extent` pixels (BaseMenuDescriptionMixin:SetScrollMode).
---@param extent number
function Description:SetScrollMode(extent)
	self.scrollExtent = extent
end

-- The popup is as wide as its longest entry: a fixed row width cut titles such as a step's "Complete objectives,
-- ..." with no way to read them. The body width is capped so one very long line cannot run off the screen; a row cut
-- at the cap carries its whole text in a tooltip, unless the entry already has one of its own.
local BODY_MIN, FRAME_PAD, ROW_INSET, TEXT_PADDING, BODY_MAX = 180, 24, 12, 20, 600
-- A level scrolls past its SetScrollMode extent, or past this one; the popup's frame adds 14 px around the rows.
local SCROLL_EXTENT, FRAME_HEIGHT_PAD = 406, 14

---@class ForeverMenuScrollFrame : ScrollFrame
---@field ScrollBar Frame

---@class ForeverContextPopup : Frame
---@field rows Button[]
---@field owner? Region
---@field body Frame
---@field scroll ForeverMenuScrollFrame
---@type ForeverContextPopup?
local popup
local Draw
---@type table<Frame, boolean>
local watchedOwners = setmetatable({}, { __mode = "k" })

---@param owner Frame
local function OwnerHidden(owner)
	if popup and popup.owner == owner then
		popup:Hide()
	end
end

-- Whether `frame` is `owner` or one of its ancestors: a menu made from a card on the world map closes with the panel.
---@param owner Region
---@param frame Frame
---@return boolean
local function Inside(owner, frame)
	local current = owner
	while current do
		if current == frame then
			return true
		end
		current = current:GetParent()
	end
	return false
end

-- The panel manager's own callback: a script on a frame under the map would run inside its hide, before the gamepad
-- binding stack is cleared, and this addon's taint blocks the controller's interact action (#493).
---@param _ table
---@param frame Frame
local function PanelHidden(_, frame)
	if popup and popup.owner and Inside(popup.owner, frame) then
		popup:Hide()
	end
end

local watchingPanels
local function WatchPanels()
	if watchingPanels then
		return
	end
	watchingPanels = true
	EventRegistry:RegisterCallback("UIParentPanelManager.HideUIPanel", PanelHidden, ns)
	EventRegistry:RegisterCallback("UIParentPanelManager.ForcePanelHide", PanelHidden, ns)
end

-- Whether the owner sits under the world map, where the panel manager rather than a frame script closes the menu.
---@param frame Frame
---@return boolean
local function UnderMap(frame)
	local map = WorldMapFrame
	while frame do
		if frame == map then
			return true
		end
		frame = frame:GetParent()
	end
	return false
end

---@return ForeverContextPopup
local function Ensure()
	if popup then
		return popup
	end
	local frame = CreateFrame("Frame", "ForeverCoreContextMenu", UIParent)
	popup = frame --[[@as ForeverContextPopup]]
	popup.rows = {}
	popup:SetFrameStrata("FULLSCREEN_DIALOG")
	popup:SetClampedToScreen(true)
	popup:EnableMouse(true)
	local background = popup:CreateTexture(nil, "BACKGROUND")
	-- art-ok: common-dropdown-bg supplies native nine-slice margins for a resizing menu.
	background:SetAtlas("common-dropdown-bg")
	background:SetAllPoints()
	local scroll = CreateFrame("ScrollFrame", nil, popup, "ScrollFrameTemplate") --[[@as ForeverMenuScrollFrame]]
	scroll:SetPoint("TOPLEFT", 0, -4)
	scroll:SetPoint("BOTTOMRIGHT", -24, 4)
	local body = CreateFrame("Frame", nil, scroll)
	body:SetWidth(BODY_MIN)
	scroll:SetScrollChild(body)
	popup.body, popup.scroll = body, scroll
	popup:SetScript("OnShow", function(self)
		self:RegisterEvent("GLOBAL_MOUSE_DOWN")
	end)
	popup:SetScript("OnHide", function(self)
		if self:IsShown() then
			self:Hide()
		end
		self:UnregisterEvent("GLOBAL_MOUSE_DOWN")
		self.owner = nil
		GameTooltip_Hide()
	end)
	popup:SetScript("OnEvent", function(self)
		if not self:IsMouseOver() and not (self.owner and self.owner:IsMouseOver()) then
			self:Hide()
		end
	end)
	popup:Hide()
	table.insert(UISpecialFrames, "ForeverCoreContextMenu")
	return popup
end

---@param root ForeverMenuDescription
function Draw(root)
	local frame = Ensure()
	local entries = {}
	if root.parent then
		local back = New("button", ns.L.MENU_BACK)
		back.back = root.parent
		entries[1] = back
	end
	for _, entry in ipairs(root.entries) do
		entries[#entries + 1] = entry
	end
	local y, bodyWidth = 6, BODY_MIN
	for index, entry in ipairs(entries) do
		local row = frame.rows[index]
		if not row then
			row = CreateFrame("Button", nil, frame.body) --[[@as Button]]
			local text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
			text:SetPoint("LEFT", 8, 0)
			text:SetPoint("RIGHT", -8, 0)
			text:SetJustifyH("LEFT")
			row:SetFontString(text)
			row:SetNormalFontObject("GameFontHighlightSmall")
			row:SetDisabledFontObject("GameFontDisableSmall")
			local highlight = row:CreateTexture(nil, "HIGHLIGHT")
			highlight:SetAllPoints()
			highlight:SetColorTexture(1, 1, 1, 0.08)
			frame.rows[index] = row
		end
		local height = entry.kind == "divider" and 6 or 20
		row:ClearAllPoints()
		row:SetPoint("TOPLEFT", 6, -y)
		local selected = entry.isSelected and entry.isSelected()
		local label = entry.text or ""
		if entry.kind == "checkbox" then
			label = (selected and ns.L.MENU_CHECKED or ns.L.MENU_UNCHECKED):format(label)
		elseif #entry.entries > 0 then
			label = ns.L.MENU_SUBMENU:format(label)
		end
		row:SetDisabledFontObject(entry.kind == "title" and "GameFontNormalSmall" or "GameFontDisableSmall")
		row:SetText(label)
		local width = math.min(math.max(BODY_MIN - ROW_INSET, row:GetTextWidth() + TEXT_PADDING), BODY_MAX - ROW_INSET)
		row:SetSize(width, height)
		bodyWidth = math.max(bodyWidth, width + ROW_INSET)
		-- A row cut at the cap cannot show its whole line, so its tooltip does.
		local truncated = entry.tooltip == nil and row:GetTextWidth() > width - TEXT_PADDING
		row:SetEnabled(entry.kind ~= "title" and entry.kind ~= "divider" and entry:IsEnabled())
		row:SetMotionScriptsWhileDisabled(true)
		row:SetScript("OnClick", function()
			if entry.back then
				Draw(entry.back)
			elseif #entry.entries > 0 then
				Draw(entry)
			else
				frame:Hide()
				if entry.onClick then
					entry.onClick()
				end
			end
		end)
		row:SetScript("OnEnter", function(self)
			if entry.tooltip then
				GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
				entry.tooltip(GameTooltip)
				GameTooltip:Show()
			elseif truncated then
				GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
				GameTooltip_SetTitle(GameTooltip, label)
				GameTooltip:Show()
			end
		end)
		row:SetScript("OnLeave", GameTooltip_Hide)
		row:SetShown(entry.kind ~= "divider")
		y = y + height
	end
	for index = #entries + 1, #frame.rows do
		frame.rows[index]:Hide()
	end
	frame.body:SetWidth(bodyWidth)
	frame.body:SetHeight(y + 6)
	local extent = root.scrollExtent or SCROLL_EXTENT
	frame:SetSize(bodyWidth + FRAME_PAD, math.min(y, extent) + FRAME_HEIGHT_PAD)
	frame.scroll.ScrollBar:SetShown(y > extent)
	frame.scroll:SetVerticalScroll(0)
end

-- The suite's one context menu: `generator` fills the root just as it would for MenuUtil.CreateContextMenu. It is
-- drawn in our own frames, so unlike Blizzard's menu it does not taint the gamepad interface's focus.
---@param owner Region
---@param generator fun(owner: Region, root: ForeverMenuDescription)
---@return ForeverMenuDescription
function ns.ContextMenu(owner, generator)
	local root = New("root")
	generator(owner, root)
	local frame = Ensure()
	frame:Hide()
	frame.owner = owner
	WatchPanels()
	-- Card owners can be inside a ScrollFrame; parenting to them clips the popup's rows. An owner under the map hears
	-- its close through the panel manager instead, so no show or hide script sits on a frame there (#493).
	local ownerFrame = owner --[[@as Frame]]
	if ownerFrame.HookScript and not watchedOwners[ownerFrame] and not UnderMap(ownerFrame) then
		ownerFrame:HookScript("OnHide", OwnerHidden)
		watchedOwners[ownerFrame] = true
	end
	frame:ClearAllPoints()
	frame:SetPoint("TOPRIGHT", owner, "BOTTOMRIGHT", 0, -2)
	Draw(root)
	frame:Show()
	return root
end
