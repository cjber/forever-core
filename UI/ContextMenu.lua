---@type string, ForeverTrackerNamespace
local _, ns = ...

-- Forever 70009 can assert in Blizzard_Menu.AcquireMenu, so the suite draws its context menus in frames of its own.
-- This is the one menu every Forever addon opens, with the same generator shape as MenuUtil.CreateContextMenu, and its
-- submenus cascade as Blizzard's do: each opens beside its row on hover and the levels above it stay open.
local Description = {}
Description.__index = Description

---@param kind ForeverMenuEntryKind
---@param text? string
---@return ForeverMenuDescription
local function New(kind, text)
	return setmetatable({ kind = kind, text = text, entries = {} }, Description) --[[@as ForeverMenuDescription]]
end

-- Shared description construction lets tracker slots remain detached until their order is final.
ns.NewMenuDescription = New

---@param text string
---@param action? fun()
---@return ForeverMenuDescription
function Description:CreateButton(text, action)
	local entry = New("button", text)
	entry.onClick = action
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

-- Blizzard's radio contract: setSelected gets the entry's data.
---@param text string
---@param selected fun(data: any): boolean
---@param action fun(data: any)
---@param data? any
---@return ForeverMenuDescription
function Description:CreateRadio(text, selected, action, data)
	local entry = self:CreateCheckbox(text, function()
		return selected(data)
	end, function()
		action(data)
	end)
	entry.kind = "radio"
	return entry
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

-- Blizzard_Menu's MenuStyle1 (Mainline MenuStyle1Mixin and MenuVariants), the look of the game's own context menus:
-- common-dropdown-bg reaching 10 units past the frame's sides and 3 past its top and bottom at alpha 0.925, rows inset
-- 8/8/8/15, each level as wide as its widest row plus 20, rows 20 high and dividers 13. The popup is as wide as its
-- longest entry: a fixed row width cut titles such as a step's "Complete objectives, ..." with no way to read them. The
-- body width is capped so one very long line cannot run off the screen; a row cut at the cap carries its whole text in
-- a tooltip, unless the entry already has one of its own.
local INSET_LEFT, INSET_TOP, INSET_RIGHT, INSET_BOTTOM = 8, 8, 8, 15
local BACKGROUND_X, BACKGROUND_Y, BACKGROUND_ALPHA = 10, 3, 0.925
local CHILD_PAD, ROW_HEIGHT, DIVIDER_HEIGHT, BODY_MAX = 20, 20, 13, 600
-- A level scrolls past its SetScrollMode extent, or past this one; its scroll bar takes this much room on the right.
local SCROLL_EXTENT, SCROLL_BAR = 406, 20
-- Blizzard_Menu's selection art at its native size: a tick square and a radio, each with its label gap, and the
-- client's 16-unit submenu arrow (MenuVariants.CreateSubmenuArrow).
local CHECK_SIZE, RADIO_SIZE, ARROW_SIZE = 12, 18, 16
local CHECK_GAP, RADIO_GAP = 7, 1
local ARROW = "Interface\\ChatFrame\\ChatFrameExpandArrow"
local DIVIDER = "Interface\\Common\\UI-TooltipDivider-Transparent"
local HIGHLIGHT = "Interface\\QuestFrame\\UI-QuestTitleHighlight"

---@class ForeverContextMenuRow : Button
---@field indicator Texture
---@field tick Texture
---@field arrow Texture
---@field divider Texture
---@field highlight Texture
---@field label FontString

---@class ForeverMenuScrollFrame : ScrollFrame
---@field ScrollBar Frame

---@class ForeverContextPopup : Frame
---@field rows ForeverContextMenuRow[]
---@field owner? Region
---@field body Frame
---@field scroll ForeverMenuScrollFrame
---@field background Texture
---@field depth integer
---@field description? ForeverMenuDescription
---@field opener? ForeverContextMenuRow

-- One frame per open level: levels[1] is the root, each deeper level a submenu cascading beside its parent's row.
---@type ForeverContextPopup[]
local levels = {}
local Draw
---@type table<Frame, boolean>
local watchedOwners = setmetatable({}, { __mode = "k" })
-- Blizzard_Menu's mouse event timer (MenuManagerMixin:RestartMouseEventTimer): the pointer's last enter and leave are
-- acted on once it has rested this long, so a diagonal move toward an open submenu does not swap it for a row it
-- crosses, and a submenu the pointer left without entering closes (ProcessMouseEventLeaveData).
local SUBMENU_DELAY = 0.33
---@type { token: integer, retain: integer, leave?: boolean, enter?: table }
local pointer = { token = 0, retain = 1 }
local RestartPointerTimer

---@param depth integer
local function HideFrom(depth)
	for index = #levels, depth, -1 do
		if levels[index]:IsShown() then
			levels[index]:Hide()
		end
	end
end

---@param owner Frame
local function OwnerHidden(owner)
	local menu = levels[1]
	if menu and menu.owner == owner then
		C_Timer.After(0, function()
			if menu.owner == owner and not owner:IsVisible() then
				menu:Hide()
			end
		end)
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
	local menu = levels[1]
	if menu and menu.owner and Inside(menu.owner, frame) then
		menu:Hide()
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
---@param frame Frame?
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

-- Whether the pointer is over any open level: a click there keeps the whole cascade open.
---@return boolean
local function OverMenu()
	for _, level in ipairs(levels) do
		if level:IsShown() and level:IsMouseOver() then
			return true
		end
	end
	return false
end

---@param depth integer
---@return ForeverContextPopup
local function Ensure(depth)
	if levels[depth] then
		return levels[depth]
	end
	local frame =
		CreateFrame("Frame", depth == 1 and "ForeverCoreContextMenu" or "ForeverCoreContextMenu" .. depth, UIParent)
	local popup = frame --[[@as ForeverContextPopup]]
	popup.rows, popup.depth = {}, depth
	popup:SetFrameStrata("FULLSCREEN_DIALOG")
	popup:SetClampedToScreen(true)
	-- The background reaches past the frame, so the clamp keeps that overhang on screen too.
	popup:SetClampRectInsets(-BACKGROUND_X, BACKGROUND_X, BACKGROUND_Y, -BACKGROUND_Y)
	popup:EnableMouse(true)
	popup:SetScript("OnEnter", function()
		pointer.retain = depth
	end)
	popup:SetScript("OnLeave", function()
		pointer.leave = true
		RestartPointerTimer()
	end)
	local background = popup:CreateTexture(nil, "BACKGROUND")
	-- art-ok: common-dropdown-bg supplies native nine-slice margins for a resizing menu.
	background:SetAtlas("common-dropdown-bg")
	background:SetPoint("TOPLEFT", -BACKGROUND_X, BACKGROUND_Y)
	background:SetPoint("BOTTOMRIGHT", BACKGROUND_X, -BACKGROUND_Y)
	background:SetAlpha(BACKGROUND_ALPHA)
	popup.background = background
	local scroll = CreateFrame("ScrollFrame", nil, popup, "ScrollFrameTemplate") --[[@as ForeverMenuScrollFrame]]
	local body = CreateFrame("Frame", nil, scroll)
	scroll:SetScrollChild(body)
	popup.body, popup.scroll = body, scroll
	if depth == 1 then
		popup:SetScript("OnShow", function(self)
			self:RegisterEvent("GLOBAL_MOUSE_DOWN")
		end)
		popup:SetScript("OnEvent", function(self)
			if not OverMenu() and not (self.owner and self.owner:IsMouseOver()) then
				self:Hide()
			end
		end)
		table.insert(UISpecialFrames, "ForeverCoreContextMenu")
	end
	-- A level closes every level past it, and gives back its parent row's held highlight.
	popup:SetScript("OnHide", function(self)
		if self:IsShown() then
			self:Hide()
		end
		HideFrom(depth + 1)
		if self.opener then
			self.opener:UnlockHighlight()
			self.opener = nil
		end
		self.description = nil
		if depth == 1 then
			pointer.token, pointer.enter, pointer.leave, pointer.retain = pointer.token + 1, nil, nil, 1
			self:UnregisterEvent("GLOBAL_MOUSE_DOWN")
			self.owner = nil
			GameTooltip_Hide()
		end
	end)
	popup:Hide()
	levels[depth] = popup
	return popup
end

-- Blizzard_Menu's GenerateSubmenuInternal: with a mouse the submenu's top-left corner meets the row's top-right one and
-- flips to the row's left when it would leave the screen; under the gamepad interface every level opens toward the
-- screen's middle from the root owner's quadrant, inset by the menu's own margins.
---@param frame ForeverContextPopup
---@param row ForeverContextMenuRow
local function PlaceSubmenu(frame, row)
	frame:ClearAllPoints()
	if InputUtil.IsGamepadUIEnabled() then
		local quadrant = FrameUtil.GetScreenQuadrant(levels[1].owner or levels[1])
		if quadrant == FrameUtilQuadrantEnum.BottomRight then
			frame:SetPoint("BOTTOMRIGHT", row, "BOTTOMLEFT", -INSET_RIGHT, -INSET_BOTTOM)
		elseif quadrant == FrameUtilQuadrantEnum.BottomLeft then
			frame:SetPoint("BOTTOMLEFT", row, "BOTTOMRIGHT", INSET_LEFT, -INSET_BOTTOM)
		elseif quadrant == FrameUtilQuadrantEnum.TopRight then
			frame:SetPoint("TOPRIGHT", row, "TOPLEFT", -INSET_RIGHT, INSET_TOP)
		else
			frame:SetPoint("TOPLEFT", row, "TOPRIGHT", INSET_LEFT, INSET_TOP)
		end
		return
	end
	-- Flipped only when the row's left has more room: Blizzard flips on any overflow, and the clamp then pulls a wide
	-- submenu back across its parent's rows.
	local rowLeft, rowRight, screenRight = row:GetLeft(), row:GetRight(), UIParent:GetRight()
	local width = frame:GetWidth() + BACKGROUND_X
	if rowLeft and rowRight and screenRight and rowRight + width > screenRight and rowLeft > screenRight - rowRight then
		frame:SetPoint("TOPRIGHT", row, "TOPLEFT")
	else
		frame:SetPoint("TOPLEFT", row, "TOPRIGHT")
	end
end

-- Blizzard_Menu's CheckForSubmenu: resting on a row closes the levels below it unless they are this row's own, and a
-- row with entries opens them as the next level beside it; the parent stays open.
---@param depth integer
---@param row ForeverContextMenuRow
---@param entry ForeverMenuDescription
local function CheckForSubmenu(depth, row, entry)
	local child = levels[depth + 1]
	if child and child:IsShown() and child.description == entry then
		return
	end
	HideFrom(depth + 1)
	if #entry.entries == 0 or not row:IsEnabled() then
		return
	end
	local frame = Ensure(depth + 1)
	frame:SetFrameLevel((levels[depth]:GetFrameLevel() or 0) + 10)
	Draw(frame, entry)
	PlaceSubmenu(frame, row)
	frame.opener = row
	row:LockHighlight()
	frame:Show()
end

local function ProcessPointer(token)
	if token ~= pointer.token then
		return
	end
	if pointer.leave then
		pointer.leave = false
		if not OverMenu() then
			HideFrom(pointer.retain + 1)
		end
	end
	local enter = pointer.enter
	pointer.enter = nil
	if enter and enter.level.description == enter.root and enter.row:IsMouseOver() then
		CheckForSubmenu(enter.level.depth, enter.row, enter.entry)
	end
end

function RestartPointerTimer()
	pointer.token = pointer.token + 1
	local token = pointer.token
	C_Timer.After(SUBMENU_DELAY, function()
		ProcessPointer(token)
	end)
end

---@param frame ForeverContextPopup
---@param root ForeverMenuDescription
function Draw(frame, root)
	frame.description = root
	local depth = frame.depth
	local entries = root.entries
	local y, bodyWidth = 0, 0
	for index, entry in ipairs(entries) do
		local row = frame.rows[index]
		if not row then
			row = CreateFrame("Button", nil, frame.body) --[[@as ForeverContextMenuRow]]
			local text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
			text:SetJustifyH("LEFT")
			text:SetJustifyV("MIDDLE")
			text:SetMaxLines(1)
			row.label = text
			row:SetFontString(text)
			row:SetNormalFontObject("GameFontHighlight")
			local highlight = row:CreateTexture(nil, "HIGHLIGHT")
			highlight:SetAllPoints()
			-- art-ok: MenuVariants.CreateHighlight, the quest log row highlight stretched to the row as the game does.
			highlight:SetTexture(HIGHLIGHT)
			highlight:SetBlendMode("ADD")
			row.highlight = highlight
			row.indicator = row:CreateTexture(nil, "ARTWORK")
			row.tick = row:CreateTexture(nil, "ARTWORK")
			row.tick:SetDrawLayer("ARTWORK", 1)
			row.arrow = row:CreateTexture(nil, "ARTWORK")
			-- art-ok: MenuVariants.CreateSubmenuArrow at its 16-unit size.
			row.arrow:SetTexture(ARROW)
			row.arrow:SetSize(ARROW_SIZE, ARROW_SIZE)
			row.arrow:SetPoint("RIGHT")
			row.divider = row:CreateTexture(nil, "ARTWORK")
			-- art-ok: MenuVariants.CreateDivider, the tooltip divider stretched across the row as the game does.
			row.divider:SetTexture(DIVIDER)
			row.divider:SetHeight(DIVIDER_HEIGHT)
			row.divider:SetPoint("LEFT")
			row.divider:SetPoint("RIGHT")
			frame.rows[index] = row
		end
		local divider = entry.kind == "divider"
		local height = divider and DIVIDER_HEIGHT or ROW_HEIGHT
		row:ClearAllPoints()
		row:SetPoint("TOPLEFT", 0, -y)
		local selected = entry.isSelected and entry.isSelected() and true or false
		local submenu = #entry.entries > 0
		local label = entry.text or ""
		-- A title is MenuUtil.CreateTitle: the row's own font in NORMAL_FONT_COLOR, which is GameFontNormal.
		row:SetDisabledFontObject(entry.kind == "title" and "GameFontNormal" or "GameFontDisable")
		row:SetText(label)
		row.divider:SetShown(divider)

		-- Checkbox and radio rows use the art Blizzard_Menu draws, left of the label and at its native size.
		local indicatorAtlas = (entry.kind == "checkbox" and "common-dropdown-ticksquare")
			or (entry.kind == "radio" and "common-dropdown-tickradial")
		local tickAtlas = (entry.kind == "checkbox" and "common-dropdown-icon-checkmark-yellow")
			or (entry.kind == "radio" and "common-dropdown-icon-radialtick-yellow")
		local indicatorSize = entry.kind == "checkbox" and CHECK_SIZE or (entry.kind == "radio" and RADIO_SIZE or 0)
		local gap = entry.kind == "checkbox" and CHECK_GAP or (entry.kind == "radio" and RADIO_GAP or 0)
		local tickX = entry.kind == "checkbox" and 2 or 0
		local tickY = entry.kind == "checkbox" and 1 or 0
		local left = 0
		row.label:ClearAllPoints()
		if indicatorAtlas and tickAtlas then
			row.indicator:SetAtlas(indicatorAtlas, true)
			row.indicator:ClearAllPoints()
			row.indicator:SetPoint("LEFT")
			row.indicator:Show()
			row.tick:SetAtlas(tickAtlas, true)
			row.tick:ClearAllPoints()
			row.tick:SetPoint("CENTER", row.indicator, "CENTER", tickX, tickY)
			row.tick:SetShown(selected)
			row.label:SetPoint("LEFT", row.indicator, "RIGHT", gap, tickY)
			left = indicatorSize + gap
		else
			row.indicator:Hide()
			row.tick:Hide()
			row.label:SetPoint("LEFT")
		end
		local right = submenu and ARROW_SIZE or 0
		row.arrow:SetShown(submenu)
		-- Measured before the label's right edge is set, so the width is the whole line's, not what fit the row's last
		-- width (a fresh row is 0 wide).
		local textWidth = 0
		if not divider then
			textWidth = row.label.GetUnboundedStringWidth and row.label:GetUnboundedStringWidth() or row:GetTextWidth()
		end
		row.label:SetPoint("RIGHT", -right, 0)
		bodyWidth = math.max(bodyWidth, math.min(left + textWidth + right + CHILD_PAD, BODY_MAX))
		row:SetHeight(height)
		local enabled = entry.kind ~= "title" and not divider and entry:IsEnabled()
		row:SetEnabled(enabled)
		-- As Blizzard_Menu: a title and a divider never light up, and a disabled action lights up faintly.
		local passive = entry.kind == "title" or divider
		row.highlight:SetAlpha(enabled and 1 or (passive and 0 or 0.4))
		row:SetMotionScriptsWhileDisabled(true)
		-- A submenu row opens its level at once on a click or a gamepad press; any other row acts and closes the menu.
		row:SetScript("OnClick", function(self)
			if #entry.entries > 0 then
				CheckForSubmenu(depth, self, entry)
			else
				HideFrom(1)
				if entry.onClick then
					entry.onClick()
				end
			end
		end)
		-- A row cut at the cap cannot show its whole line, so its tooltip does.
		local truncated = entry.tooltip == nil and left + textWidth + right > BODY_MAX
		row:SetScript("OnEnter", function(self)
			pointer.retain = depth
			pointer.enter = { level = frame, row = self, entry = entry, root = root }
			RestartPointerTimer()
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
		row:SetScript("OnLeave", function()
			GameTooltip_Hide()
			pointer.leave = true
			RestartPointerTimer()
		end)
		row:Show()
		y = y + height
	end
	-- Every row spans the level, as Blizzard's elements do, so the highlight and the arrow reach its right edge.
	for index = 1, #entries do
		frame.rows[index]:SetWidth(bodyWidth)
	end
	for index = #entries + 1, #frame.rows do
		frame.rows[index]:Hide()
	end
	frame.body:SetSize(bodyWidth, y)
	local extent = root.scrollExtent or SCROLL_EXTENT
	local scrolls = y > extent
	local bar = scrolls and SCROLL_BAR or 0
	frame.scroll:ClearAllPoints()
	frame.scroll:SetPoint("TOPLEFT", INSET_LEFT, -INSET_TOP)
	frame.scroll:SetPoint("BOTTOMRIGHT", -(INSET_RIGHT + bar), INSET_BOTTOM)
	frame:SetSize(INSET_LEFT + bodyWidth + bar + INSET_RIGHT, INSET_TOP + math.min(y, extent) + INSET_BOTTOM)
	frame.scroll.ScrollBar:SetShown(scrolls)
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
	local frame = Ensure(1)
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
	-- Placed as MenuUtil.CreateContextMenu places its menus (Blizzard_Menu/Menu.lua, OpenContextMenu). With a mouse,
	-- at the cursor: an owner can be a whole tracker section, whose corner sits far from the click (#850), and a
	-- screen point leaves the menu put when a tracker re-plan moves the owner. Under the gamepad interface a press
	-- leaves the cursor where it was parked, so the menu opens beside the owner, toward the screen's middle.
	if InputUtil.IsGamepadUIEnabled() then
		local quadrant = FrameUtil.GetScreenQuadrant(ownerFrame)
		if quadrant == FrameUtilQuadrantEnum.BottomRight then
			frame:SetPoint("BOTTOMRIGHT", ownerFrame, "BOTTOMLEFT")
		elseif quadrant == FrameUtilQuadrantEnum.BottomLeft then
			frame:SetPoint("BOTTOMLEFT", ownerFrame, "BOTTOMRIGHT")
		elseif quadrant == FrameUtilQuadrantEnum.TopRight then
			frame:SetPoint("TOPRIGHT", ownerFrame, "TOPLEFT")
		else
			frame:SetPoint("TOPLEFT", ownerFrame, "TOPRIGHT")
		end
	else
		InputUtil.AnchorRegionToCursor(frame, "TOPLEFT")
	end
	Draw(frame, root)
	frame:Show()
	return root
end
