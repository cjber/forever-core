-- `/forever profile` shows this character's profile link, built by Core/ProfileCode.lua, selected in a copyable box.
-- An addon cannot open a browser, so the player copies the link themselves; nothing is sent anywhere and nothing new
-- is saved. The window is core's usual portrait frame, so it looks like the report window beside it.

local _, ns = ...

local L = ns.L
local WIDTH, HEIGHT = 520, 200
local ICON = "Interface\\AddOns\\ForeverCore\\media\\Icon"

local Profile = {}

-- PortraitFrameTemplate's own members this file uses (Mainline/SharedUIPanelTemplates.xml).
---@class ForeverProfileWindow : Frame
---@field SetTitle fun(self: ForeverProfileWindow, title: string)
---@field GetPortrait fun(self: ForeverProfileWindow): Texture

---@type ForeverProfileWindow?
local window
---@type EditBox
local editBox
---@type string
local shown = ""

---@param edit EditBox
local function Select(edit)
	edit:SetFocus()
	edit:HighlightText()
end

-- The window is built once, on the first command, so a player who never asks for a profile pays nothing for it.
---@return ForeverProfileWindow
local function Window()
	if window then
		return window
	end
	local frameName = "ForeverCoreProfile"
	local frame = CreateFrame("Frame", frameName, UIParent, "PortraitFrameTemplate") --[[@as ForeverProfileWindow]]
	-- Escape closes it like any panel, with or without the edit box's focus.
	table.insert(UISpecialFrames, frameName)
	frame:SetSize(WIDTH, HEIGHT)
	frame:SetPoint("CENTER")
	frame:SetFrameStrata("DIALOG")
	frame:SetToplevel(true)
	frame:SetClampedToScreen(true)
	frame:SetMovable(true)
	frame:EnableMouse(true)
	frame:RegisterForDrag("LeftButton")
	frame:SetScript("OnDragStart", function(self)
		self:StartMoving()
	end)
	frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
	frame:SetTitle(L["Your Forever profile"])
	ns.Art.Icon(frame:GetPortrait(), ICON, 62)

	local hint = frame:CreateFontString(nil, "ARTWORK", "GameFontNormal")
	hint:SetPoint("TOPLEFT", 70, -32)
	hint:SetPoint("RIGHT", -16, 0)
	hint:SetJustifyH("LEFT")
	hint:SetText(L["The link is selected. Press Ctrl+C (Cmd+C on a Mac), then open it in a browser. Nothing is sent."])

	local inset = CreateFrame("Frame", nil, frame, "InsetFrameTemplate")
	inset:SetPoint("TOPLEFT", 10, -84)
	inset:SetPoint("BOTTOMRIGHT", -10, 10)

	local scroll = CreateFrame("ScrollFrame", nil, inset, "ScrollFrameTemplate")
	scroll:SetPoint("TOPLEFT", 8, -8)
	scroll:SetPoint("BOTTOMRIGHT", -28, 8)

	local edit = CreateFrame("EditBox", nil, scroll)
	edit:SetMultiLine(true)
	edit:SetAutoFocus(false)
	edit:SetFontObject("ChatFontNormal")
	edit:SetWidth(WIDTH - 66)
	edit:SetMaxLetters(0)
	-- Read-only: typing puts the link back, still selected, so a stray key never changes what is copied.
	edit:SetScript("OnTextChanged", function(self, userInput)
		if userInput then
			self:SetText(shown)
			Select(self)
		end
	end)
	edit:SetScript("OnEditFocusGained", function(self)
		self:HighlightText()
	end)
	edit:SetScript("OnEscapePressed", function()
		frame:Hide()
	end)
	scroll:SetScrollChild(edit)
	editBox, window = edit, frame
	return frame
end

-- Show the link, all of it selected for Ctrl+C. A character none of the addons has recorded yet gets a line saying
-- so instead of an empty card.
function Profile.Show()
	local record = ns.ProfileCode.Read()
	if next(record.stats) == nil then
		print(L["No Forever addon has recorded anything for this character yet."])
		return
	end
	local frame = Window()
	shown = ns.ProfileCode.Link(record)
	editBox:SetText(shown)
	frame:Show()
	Select(editBox)
end

ns.Profile = Profile
