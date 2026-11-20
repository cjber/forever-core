local _, ns = ...

-- The settings page every Forever addon draws, and only the page. This file loads once, in ForeverCore: a panel with
-- a title, rows that stack down it, and the category registration. It holds no addon's options -- which rows exist,
-- what they read and write, and every phrase are the addon's, passed in here. Register takes the caller's L, and
-- every label and tooltip on that page reads through it.

---@class ForeverSettingsPanel : Frame
---@field name? string
---@field foreverL? table<string, string>
---@field foreverSafeCall? ForeverSafeCall|false
---@field settingsRowY? number
---@field settingsRows? table[]
---@field title? FontString
---@field category? table
---@field foreverAttach? CheckButton the shared tracker's attach tick box, once added

---@class ForeverSettingsPage
local Page = {}
-- Raised with each member the module adds. AddTrackerAttach arrived in minor 1.
Page.minor = 1
ns.SettingsPage = Page
-- The shared tracker's attach row's tooltip, one phrase for the canvas tick box here and SettingsSections' native row.
ns.TRACKER_ATTACH_TOOLTIP = "The shared Forever tracker sits under the quest tracker when this is on, "
	.. "and left of it when it is off. Every Forever addon shows this same setting."

-- A row's callback runs in the registering addon's SafeCall, so a failure lands in that addon's journal.
---@param panel ForeverSettingsPanel
---@param label string
---@param fn function
---@return boolean ok, any ...
local function Run(panel, label, fn, ...)
	local safe = panel.foreverSafeCall
	if safe then
		return safe(label, fn, ...)
	end
	if ns.SafeCall then
		return ns.SafeCall(label, fn, ...)
	end
	return pcall(fn, ...)
end

-- A phrase through the page's own L, English when that L has no translation for it. `panel.foreverL` is the L the
-- page was registered with.
---@param panel ForeverSettingsPanel
---@param phrase string
---@return string
local function Text(panel, phrase)
	local L = panel.foreverL
	local translated = type(L) == "table" and L[phrase] or nil
	return translated or phrase
end

-- How far down the panel the next row goes, and how much room each kind of row takes. A canvas has no layout engine, so
-- the page keeps one cursor and every row claims its height.
local TITLE = 16
local CHECK, SLIDER, BUTTON = 28, 56, 36

---@param panel ForeverSettingsPanel
---@param height number
---@return number
local function Next(panel, height)
	-- The first row starts below the title; every row after it starts below the one before.
	local y = panel.settingsRowY or -(TITLE + 32)
	panel.settingsRowY = y - height
	return y
end

-- Keep canvas rows in order so a width change can remeasure wrapped headings and move every later row together.
---@param panel ForeverSettingsPanel
local function Layout(panel)
	panel.settingsRowY = nil
	for _, row in ipairs(panel.settingsRows or {}) do
		local y = Next(panel, 0)
		row.widget:SetPoint("TOPLEFT", row.x, y)
		local height = row.height
		if row.header then
			row.widget:SetPoint("TOPRIGHT", panel, "TOPRIGHT", -16, y)
			height = math.max(45, 16 + row.widget.Title:GetStringHeight() + 10)
			row.widget:SetHeight(height)
		end
		Next(panel, height)
	end
end

---@param panel ForeverSettingsPanel
---@param widget Region
---@param x number
---@param height number
---@param header? boolean
local function Place(panel, widget, x, height, header)
	panel.settingsRows = panel.settingsRows or {}
	table.insert(panel.settingsRows, { widget = widget, x = x, height = height, header = header })
	widget:SetPoint("TOPLEFT", x, Next(panel, height))
end

-- Register `build` as the addon's settings page under the category `name` (a phrase, read through L).
-- `build` is called once with the panel and this table, and adds the addon's own rows through AddCheck and the rest.
-- Returns the category and the panel, or nil on a client with no Settings API, where the addon keeps its options off
-- the interface rather than erroring on load.
---@param name string
---@param build fun(panel: Frame, page: table)
---@param L? table<string, string> the calling addon's phrases, used for this page's labels and tooltips
---@param safeCall? ForeverSafeCall the addon's SafeCall for its own rows
---@return table?, Frame?
function Page.Register(name, build, L, safeCall)
	if not Settings or not Settings.RegisterCanvasLayoutCategory then
		return nil
	end
	local panel = CreateFrame("Frame") --[[@as ForeverSettingsPanel]]
	panel.foreverL = L
	panel.foreverSafeCall = type(safeCall) == "function" and safeCall or false
	panel.name = Text(panel, name)
	local title = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlightHuge")
	title:SetPoint("TOPLEFT", 16, -TITLE)
	title:SetText(Text(panel, name))
	panel.title = title
	-- While debug capture is on, the page says so beside its title. It takes no row, so a page's options sit where they
	-- always do whether the capture is on or off. Built only when core's capture module is loaded, so a spec that loads
	-- the chrome alone needs no extra client API.
	local notice = ns.DebugCaptureShortNotice
	if type(notice) == "function" then
		local line = panel:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
		line:SetPoint("LEFT", title, "RIGHT", 12, 0)
		line:SetPoint("RIGHT", -16, 0)
		line:SetJustifyH("RIGHT")
		line:SetWordWrap(false)
		local function RefreshNotice()
			local text = notice()
			line:SetText(text or "")
			line:SetShown(text ~= nil)
		end
		panel:HookScript("OnShow", RefreshNotice)
		RefreshNotice()
	end
	Run(panel, "settings page", build, panel, Page)
	panel:HookScript("OnSizeChanged", function()
		Layout(panel)
	end)
	Layout(panel)
	local category = Settings.RegisterCanvasLayoutCategory(panel, Text(panel, name))
	Settings.RegisterAddOnCategory(category)
	panel.category = category
	return category, panel
end

-- The native settings heading is 45 units tall with a 16-unit top inset. Keep that rhythm, expanding for wrapped
-- consumer phrases so the next row always clears the title. The template owns its font, tooltip and narration.
---@class ForeverSettingsHeader : Frame
---@field Title FontString
---@field Init fun(self: ForeverSettingsHeader, initializer: table)

---@param panel ForeverSettingsPanel
---@param label string a phrase, read through the page's L
---@param tooltip? string a phrase, read through the page's L
---@return ForeverSettingsHeader
function Page.AddHeader(panel, label, tooltip)
	local header = CreateFrame("Frame", nil, panel, "SettingsListSectionHeaderTemplate") --[[@as ForeverSettingsHeader]]
	Place(panel, header, 9, 45, true)
	header:Init(CreateSettingsListSectionHeaderInitializer(Text(panel, label), tooltip and Text(panel, tooltip)))
	header.Title:SetPoint("TOPRIGHT", header, "TOPRIGHT", 0, -16)
	header.Title:SetWordWrap(true)
	return header
end

-- A tick box that reads `get()` when it is drawn and writes `set(checked)` when the player changes it. The setter is
-- where an addon refreshes whatever the setting affects; this file never calls back into the addon.
---@param panel ForeverSettingsPanel
---@param label string a phrase, read through the page's L
---@param get fun(): boolean?
---@param set fun(checked: boolean)
---@param tooltip? string a phrase, read through the page's L
---@return CheckButton
function Page.AddCheck(panel, label, get, set, tooltip)
	local check = CreateFrame("CheckButton", nil, panel, "InterfaceOptionsCheckButtonTemplate")
	Place(panel, check, 16, CHECK)
	local ok, checked = Run(panel, "settings checkbox", get)
	check:SetChecked(ok and checked == true)
	local text = check:CreateFontString(nil, "ARTWORK", "GameFontNormal")
	text:SetPoint("LEFT", check, "RIGHT", 4, 0)
	text:SetText(Text(panel, label))
	if tooltip then
		check.tooltipText = Text(panel, tooltip)
	end
	check:SetScript("OnClick", function(self)
		Run(panel, "settings checkbox", set, self:GetChecked() == true)
	end)
	return check
end

-- A slider with its own label above it; `get()` is the saved value, `set(value)` writes it.
---@param panel ForeverSettingsPanel
---@param label string a phrase, read through the page's L
---@param get fun(): number?
---@param set fun(value: number)
---@param minimum number
---@param maximum number
---@param step? number
---@param tooltip? string a phrase, read through the page's L
---@return Slider
function Page.AddSlider(panel, label, get, set, minimum, maximum, step, tooltip)
	local text = panel:CreateFontString(nil, "ARTWORK", "GameFontNormal")
	Place(panel, text, 16, SLIDER)
	text:SetText(Text(panel, label))
	local slider = CreateFrame("Slider", nil, panel, "OptionsSliderTemplate")
	slider:SetPoint("TOPLEFT", text, "BOTTOMLEFT", 0, -8)
	slider:SetWidth(240)
	slider:SetMinMaxValues(minimum, maximum)
	slider:SetValueStep(step or 1)
	slider:SetObeyStepOnDrag(true)
	local ok, savedValue = Run(panel, "settings slider", get)
	slider:SetValue((ok and savedValue) or minimum)
	if tooltip then
		slider.tooltipText = Text(panel, tooltip)
	end
	slider:SetScript("OnValueChanged", function(_, value)
		Run(panel, "settings slider", set, value)
	end)
	return slider
end

-- A button that runs `callback`; the addon does whatever it does behind it.
---@param panel ForeverSettingsPanel
---@param label string a phrase, read through the page's L
---@param callback fun()
---@param tooltip? string a phrase, read through the page's L
---@return Button
function Page.AddButton(panel, label, callback, tooltip)
	local button = CreateFrame("Button", nil, panel, "SharedButtonSmallTemplate")
	button:SetSize(180, 24)
	Place(panel, button --[[@as Button]], 16, BUTTON)
	button:SetText(Text(panel, label))
	button:SetScript("OnClick", function()
		Run(panel, "settings button", callback)
	end)
	if tooltip then
		button.tooltipText = Text(panel, tooltip)
	end
	return button --[[@as Button]]
end

-- The shared tracker's "Attach to quest tracker" tick box on a canvas page, the same setting and words
-- SettingsSections.RegisterTrackerAttach puts in a native list (#910). It ticks itself again when a drag or another
-- addon's row changes the choice.
-- Like the native row, it shows nothing while an older adopted tracker is drawing, and a panel gets one tick box.
---@param panel ForeverSettingsPanel
---@return CheckButton?
function Page.AddTrackerAttach(panel)
	local host = ns.TrackerHost
	if type(panel) ~= "table" or panel.foreverAttach then
		return panel and panel.foreverAttach
	end
	if
		ns.TrackerHostForeign
		or type(host) ~= "table"
		or type(host.GetSettings) ~= "function"
		or type(host.SetAttached) ~= "function"
		or type(host.OnAttachmentChanged) ~= "function"
	then
		return nil
	end
	local L = ns.L
	local check = Page.AddCheck(panel, L["Attach to quest tracker"], function()
		return host.GetSettings().attached == true
	end, function(checked)
		host.SetAttached(checked == true)
	end, L[ns.TRACKER_ATTACH_TOOLTIP])
	host.OnAttachmentChanged(function(attached)
		check:SetChecked(attached == true)
	end)
	panel.foreverAttach = check
	return check
end
