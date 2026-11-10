---@type string, ForeverFamilyNamespace
local _, ns = ...

-- The Forever addons, and the quiet hints one shows for another the player doesn't have. This file loads once, in
-- ForeverCore, and reads core's own L for every word it draws. It holds no addon's own code: each addon passes in its
-- saved variables (`db`) and its own folder. Nothing here is protected, hooks Blizzard code, runs in combat or
-- reaches the network: a hint is a grey line, a menu entry or a settings row that shows a link. The settings page
-- ends with one more row, the Ko-fi address, shown only when the player clicks its Copy link button.

-- The client's gamepad switch, read by Family.Register.
-- luacheck: read globals InputUtil

---@class ForeverFamilyNamespace
---@field L? ForeverFamilyL
---@field SafeCall? ForeverSafeCall
---@field Family? ForeverFamilyAPI

---@class ForeverFamilyDB
---@field suggestFamily? boolean false when the player turned the hints off; on by default
---@field familyDismissed? table<string, boolean> hints the player chose never to see again, by key

---@class ForeverFamilyLink
---@field name string
---@field folder? string the addon's folder; the Ko-fi link has none
---@field url string
---@field line string what it is, in one line, in English: also its key in each addon's L

---@class ForeverFamilyAddon : ForeverFamilyLink
---@field folder string

---@alias ForeverFamilyState "on"|"off"|"missing"
---@alias ForeverFamilyL table<string, string>
---@alias ForeverFamilySaved ForeverFamilyDB|fun(): ForeverFamilyDB?

---@class ForeverFamilyPanel : Frame
---@field Refresh fun(self: ForeverFamilyPanel)
---@field OnRefresh fun(self: ForeverFamilyPanel)
---@field OnDefault fun(self: ForeverFamilyPanel)
---@field foreverSafeCall? ForeverSafeCall|false

-- PortraitFrameTemplate's own members this file uses (Mainline/SharedUIPanelTemplates.xml).
---@class ForeverFamilyLinkWindow : Frame
---@field SetTitle fun(self: ForeverFamilyLinkWindow, title: string)
---@field GetPortrait fun(self: ForeverFamilyLinkWindow): Texture

local QUESTION = "Interface\\Icons\\INV_Misc_QuestionMark"
local COIN = "Interface\\Icons\\INV_Misc_Coin_01"
-- One window name for every client, so Escape always knows it.
local LINK_NAME = "ForeverFamilyLink"
local NO_STRINGS = {}

---@class ForeverFamilyAPI
---@field ADDONS ForeverFamilyAddon[] the five addons, in order
---@field SUPPORT ForeverFamilyLink where a player can support the addons
---@field window? ForeverFamilyLinkWindow the link window once built
---@field Register fun(category: table, db: ForeverFamilySaved, current?: string, safeCall?: ForeverSafeCall): table
local Family = {}

-- Every phrase reads from core's L, and as itself where that L has no entry, so a line is never half translated.
-- A phrase counts only as the L's own entry (rawget), never through its metatable.
local strings
---@return ForeverFamilyL
local function Strings()
	if not strings then
		local source = type(ns.L) == "table" and ns.L or NO_STRINGS
		strings = setmetatable({}, {
			__index = function(_, phrase)
				local text = rawget(source, phrase)
				return type(text) == "string" and text or phrase
			end,
		})
	end
	return strings
end

---@param name string
---@param folder string
---@param slug string the CurseForge project's address
---@param line string
---@return ForeverFamilyAddon
local function Addon(name, folder, slug, line)
	return { name = name, folder = folder, url = "https://www.curseforge.com/wow/addons/" .. slug, line = line }
end

-- The addons in order, with the English phrase as each line's key in every locale.
---@return ForeverFamilyAddon[]
local function List()
	return {
		Addon(
			"Shortest Path Forever",
			"ShortestPathForever",
			"shortest-path-forever",
			"Plans the quickest way anywhere and guides you there, with live boat and zeppelin times."
		),
		Addon(
			"Adventure Guide Forever",
			"AdventureGuideForever",
			"adventure-guide-forever",
			"Picks quests for your level and plans them into one journey."
		),
		Addon(
			"SkillUp Forever",
			"SkillUpForever",
			"skillup-forever",
			"Plans the cheapest route to your next profession rank."
		),
		Addon(
			"Legacy Forever",
			"LegacyForever",
			"legacy-forever",
			"Shows the Legacy challenges you can advance in each zone."
		),
		Addon(
			"Tweaks Forever",
			"TweaksForever",
			"tweaks-forever",
			"Quest automation, rare alerts and merchant handling for the default UI."
		),
	}
end
Family.ADDONS = List()

-- The Ko-fi page, written through the same English phrase keys.
---@return ForeverFamilyLink
local function Support()
	return {
		name = "Ko-fi",
		url = "https://ko-fi.com/cjber",
		line = "The Forever addons are free, with nothing locked behind them. If they help, you can buy me a coffee.",
	}
end
Family.SUPPORT = Support()

-- An installed addon's own icon; files load from a folder whether or not its addon is switched on.
---@param folder string
---@param state ForeverFamilyState
---@return string
local function Icon(folder, state)
	return state == "missing" and QUESTION or ("Interface\\AddOns\\" .. folder .. "\\media\\Icon")
end

---@param folder string
---@return ForeverFamilyAddon?
local function Find(folder)
	for _, addon in ipairs(Family.ADDONS) do
		if addon.folder == folder then
			return addon
		end
	end
end

-- A button as wide as its label, so a translated one fits.
---@param button Button
---@param minimum number
local function Fit(button, minimum)
	local label = button:GetFontString()
	button:SetWidth(math.max(minimum, label and label:GetStringWidth() + 24 or 0))
end

-- The client may answer with a secret value in a restricted state; testing one raises, so the test happens
-- inside the pcall and a failed read means "don't know".
---@param question fun(): boolean
---@return boolean?
local function Ask(question)
	local ok, answer = pcall(question)
	if ok then
		return answer
	end
end

-- "off" covers every installed copy that isn't running: switched off, out of date or failed to load. An answer
-- the client won't give also reads as "off", so no hint shows for an addon the player may have.
---@param folder string
---@return ForeverFamilyState
function Family.State(folder)
	local api = C_AddOns
	if type(api) ~= "table" then
		return "off"
	end
	local loaded = Ask(function()
		return api.IsAddOnLoaded(folder) and true or false
	end)
	if loaded ~= false then
		return loaded and "on" or "off"
	end
	local exists = Ask(function()
		if api.DoesAddOnExist then
			return api.DoesAddOnExist(folder) and true or false
		end
		local _, _, _, _, reason = api.GetAddOnInfo(folder)
		return reason ~= "MISSING"
	end)
	return exists == false and "missing" or "off"
end

-- Whether the hint `key` for `folder` may show: hints are on, the addon isn't installed at all (one the player
-- switched off was their choice), and they haven't dismissed this hint. Passive places ask on every show.
---@param db? ForeverFamilyDB
---@param key string
---@param folder string
---@return boolean
function Family.Hint(db, key, folder)
	if type(db) ~= "table" or db.suggestFamily == false then
		return false
	end
	local dismissed = db.familyDismissed
	if type(dismissed) == "table" and dismissed[key] then
		return false
	end
	return Family.State(folder) == "missing"
end

local claimed = {}
-- True the first time `key` asks this session, for the places that draw attention (the tracker footer). Keys are
-- shared by every Forever addon, so each starts with its own addon's name.
---@param key string
---@return boolean
function Family.Once(key)
	if claimed[key] then
		return false
	end
	claimed[key] = true
	return true
end

---@type ForeverFamilyLinkWindow?
local window
local parts = {}
local shownURL = ""
---@type { db?: ForeverFamilyDB, key?: string, onDismiss?: fun(), safeCall?: ForeverSafeCall }
local showing = {}

---@param edit EditBox
local function Select(edit)
	edit:SetFocus()
	edit:HighlightText()
end

-- A consumer callback runs in that addon's SafeCall, so its failure lands in its own journal.
---@param safe? ForeverSafeCall
---@param label string
---@param fn function
---@return boolean ok, any ...
local function RunSafe(safe, label, fn, ...)
	if safe then
		return safe(label, fn, ...)
	end
	if ns.SafeCall then
		return ns.SafeCall(label, fn, ...)
	end
	return pcall(fn, ...)
end

---@return ForeverFamilyLinkWindow
local function Window()
	if window then
		return window
	end
	local frame = CreateFrame("Frame", LINK_NAME, UIParent, "PortraitFrameTemplate") --[[@as ForeverFamilyLinkWindow]]
	if not tContains(UISpecialFrames, LINK_NAME) then
		-- Escape closes it like any panel (an addon-owned frame).
		table.insert(UISpecialFrames, LINK_NAME)
	end
	frame:SetSize(400, 186)
	frame:SetPoint("CENTER")
	frame:SetFrameStrata("DIALOG")
	frame:SetToplevel(true)
	frame:SetClampedToScreen(true)
	frame:SetMovable(true)
	frame:EnableMouse(true)
	frame:RegisterForDrag("LeftButton")
	frame:SetScript("OnDragStart", frame.StartMoving)
	frame:SetScript("OnDragStop", frame.StopMovingOrSizing)

	local line = frame:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
	line:SetPoint("TOPLEFT", 70, -32)
	line:SetPoint("RIGHT", -16, 0)
	line:SetJustifyH("LEFT")

	local edit = CreateFrame("EditBox", nil, frame, "InputBoxTemplate") --[[@as EditBox]]
	edit:SetPoint("TOPLEFT", line, "BOTTOMLEFT", 6, -12)
	edit:SetPoint("RIGHT", -20, 0)
	edit:SetHeight(24)
	edit:SetAutoFocus(false)
	-- Read-only: typing puts the address back, still selected, so a stray key never changes what is copied.
	edit:SetScript("OnTextChanged", function(self, userInput)
		if userInput then
			self:SetText(shownURL)
			Select(self)
		end
	end)
	edit:SetScript("OnEditFocusGained", function(self)
		self:HighlightText()
	end)
	edit:SetScript("OnEscapePressed", function()
		frame:Hide()
	end)

	local hint = frame:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
	hint:SetPoint("TOPLEFT", edit, "BOTTOMLEFT", -6, -6)
	hint:SetPoint("RIGHT", -16, 0)
	hint:SetJustifyH("LEFT")

	local close = CreateFrame("Button", nil, frame, "SharedButtonSmallTemplate") --[[@as Button]]
	close:SetHeight(22)
	close:SetPoint("BOTTOMRIGHT", -14, 14)
	close:SetScript("OnClick", function()
		frame:Hide()
	end)

	local never = CreateFrame("Button", nil, frame, "SharedButtonSmallTemplate") --[[@as Button]]
	never:SetHeight(22)
	never:SetPoint("RIGHT", close, "LEFT", -8, 0)
	never:SetScript("OnClick", function()
		local db, key, onDismiss = showing.db, showing.key, showing.onDismiss
		if db and key then
			db.familyDismissed = type(db.familyDismissed) == "table" and db.familyDismissed or {}
			db.familyDismissed[key] = true
		end
		frame:Hide()
		if onDismiss then
			RunSafe(showing.safeCall, "family dismiss", onDismiss)
		end
	end)

	parts.line, parts.edit, parts.hint, parts.close, parts.never = line, edit, hint, close, never
	window = frame
	Family.window = frame
	return frame
end

-- The window for `link`, with `icon` in its portrait, out of combat.
---@param link ForeverFamilyLink
---@param icon string
---@param db? ForeverFamilyDB
---@param key? string
---@param onDismiss? fun()
---@param safeCall? ForeverSafeCall
local function Open(link, icon, db, key, onDismiss, safeCall)
	local frame = Window()
	local L = Strings()
	showing.db, showing.key, showing.onDismiss, showing.safeCall = db, key, onDismiss, safeCall
	shownURL = link.url
	frame:SetTitle(link.name)
	-- art-ok: a square icon in the template's round portrait
	frame:GetPortrait():SetTexture(icon)
	parts.line:SetText(L[link.line])
	parts.hint:SetText(L["Copy the address, then open it in your browser."])
	parts.close:SetText(L["Close"])
	parts.never:SetText(L["Don't suggest this again"])
	local dismissable = db ~= nil and key ~= nil
	Fit(parts.close, 96)
	Fit(parts.never, 140)
	parts.never:SetShown(dismissable)
	-- The window grows for a long translation rather than letting a button leave it or the line run over the box:
	-- the title band, the line, the box, the hint and the buttons, each with its gap.
	local buttons = parts.close:GetWidth() + (dismissable and parts.never:GetWidth() + 8 or 0)
	frame:SetWidth(math.max(400, buttons + 102))
	local text = (parts.line:GetStringHeight() or 0) + (parts.hint:GetStringHeight() or 0)
	frame:SetHeight(math.max(186, text + 124))
	parts.edit:SetText(link.url)
	frame:Show()
	Select(parts.edit)
end

-- A small window with `folder`'s name, line and store address, selected for Ctrl+C. With a hint `key` it also
-- offers "Don't suggest this again", which dismisses that hint in `db` and then calls `onDismiss`. Never opens in
-- combat; returns whether it opened.
---@param db? ForeverFamilyDB
---@param key? string
---@param folder string
---@param onDismiss? fun()
---@param safeCall? ForeverSafeCall
---@return boolean
function Family.ShowLink(db, key, folder, onDismiss, safeCall)
	local addon = Find(folder)
	if not addon or InCombatLockdown() then
		return false
	end
	Open(addon, Icon(folder, Family.State(folder)), db, key, onDismiss, safeCall)
	return true
end

-- The same window with the Ko-fi address, for the settings page's last row. Never opens in combat; returns whether
-- it opened.
---@return boolean
function Family.ShowSupport()
	if InCombatLockdown() then
		return false
	end
	Open(Family.SUPPORT, COIN, nil, nil, nil)
	return true
end

local ROW_HEIGHT = 52
-- The page has a global name built from its addon's folder: the templates it uses name their regions from $parent,
-- so a named page keeps UICheckButtonTemplate's Text at ForeverFamilyPanel<folder>Text instead of the bare global
-- `Text`. A caller that names no addon still gets its own name, so two pages never share one.
local pages = 0

-- The page's own name, or a fresh one for a caller that names no addon.
---@param current? string
---@return string
local function Owner(current)
	pages = pages + 1
	return type(current) == "string" and current ~= "" and current or "Unnamed" .. pages
end

-- An addon's saved variables, or the function that returns them once they load.
---@param db ForeverFamilySaved
---@return ForeverFamilyDB?
local function Resolve(db)
	if type(db) == "function" then
		return db()
	end
	return db
end

-- The addon's saved table, read through its SafeCall, or nil when it is not loaded or its reader failed.
---@param safe? ForeverSafeCall
---@param db ForeverFamilySaved
---@return ForeverFamilyDB?
local function ReadDb(safe, db)
	local ok, saved = RunSafe(safe, "family saved variables", Resolve, db)
	if ok and type(saved) == "table" then
		return saved
	end
end

-- The "Forever addons" settings page: the hint setting, then a row per addon with its icon, line, state and a Copy link
-- button, then a last row with the Ko-fi address. `db` is the addon's saved variables, or a function that returns them
-- once they load; `current` is the addon's own folder, whose row says "This addon". The rows are built the first time
-- it shows and their states read again each time. Defaults turns the hints back on, dismissed ones included.
---@param parent? Frame
---@param db ForeverFamilySaved
---@param current? string
---@param safeCall? ForeverSafeCall
---@return ForeverFamilyPanel
function Family.CreatePanel(parent, db, current, safeCall)
	local owner = Owner(current)
	local panel = CreateFrame("Frame", "ForeverFamilyPanel" .. owner, parent) --[[@as ForeverFamilyPanel]]
	panel.foreverSafeCall = type(safeCall) == "function" and safeCall or false
	-- Hidden until the settings panel shows it, so its OnShow always fires.
	panel:Hide()
	local L = Strings()
	local states = { on = L["On"], off = L["Installed, turned off"], missing = L["Not installed"] }
	---@return ForeverFamilyDB?
	local function Saved()
		return ReadDb(panel.foreverSafeCall, db)
	end
	local check
	local rows = {}

	local function Build()
		local title = panel:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
		title:SetPoint("TOPLEFT", 16, -16)
		title:SetText(L["Forever addons"])

		check = CreateFrame("CheckButton", nil, panel, "UICheckButtonTemplate") --[[@as CheckButton]]
		check:SetPoint("TOPLEFT", 12, -44)
		check:SetScript("OnClick", function(self)
			local saved = Saved()
			if saved then
				saved.suggestFamily = self:GetChecked() and true or false
			else
				self:SetChecked(true)
			end
		end)
		local label = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
		label:SetPoint("LEFT", check, "RIGHT", 4, 0)
		label:SetText(L["Suggest my other Forever addons"])
		local about = panel:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
		about:SetPoint("TOPLEFT", check, "BOTTOMLEFT", 30, 2)
		about:SetPoint("RIGHT", -16, 0)
		about:SetJustifyH("LEFT")
		about:SetText(
			L["Show a quiet line where one of my other Forever addons would help. Only for addons you don't have."]
		)

		-- A row per addon, then Ko-fi's, which has no state and no row to refresh.
		local links = { unpack(Family.ADDONS) } ---@type ForeverFamilyLink[]
		links[#links + 1] = Family.SUPPORT
		for index, link in ipairs(links) do
			local folder = link.folder
			local top = -100 - (index - 1) * ROW_HEIGHT
			local icon = panel:CreateTexture(nil, "ARTWORK")
			icon:SetSize(32, 32)
			icon:SetPoint("TOPLEFT", 16, top)
			local button = CreateFrame("Button", nil, panel, "SharedButtonSmallTemplate") --[[@as Button]]
			button:SetHeight(22)
			button:SetPoint("TOPRIGHT", -16, top - 5)
			button:SetText(L["Copy link"])
			Fit(button, 110)
			button:SetScript("OnClick", function()
				if folder then
					Family.ShowLink(nil, nil, folder, nil)
				else
					Family.ShowSupport()
				end
			end)
			local right = button ---@type Region
			if folder then
				right = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
				right:SetPoint("RIGHT", button, "LEFT", -10, 0)
				right:SetWidth(140)
				right:SetJustifyH("RIGHT")
				rows[index] = { addon = link, icon = icon, state = right, button = button }
			else
				-- art-ok: a square icon at 32x32
				icon:SetTexture(COIN)
			end
			local name = panel:CreateFontString(nil, "ARTWORK", "GameFontNormal")
			name:SetPoint("TOPLEFT", icon, "TOPRIGHT", 10, 0)
			name:SetText(link.name)
			local line = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
			line:SetPoint("TOPLEFT", name, "BOTTOMLEFT", 0, -3)
			line:SetPoint("RIGHT", right, "LEFT", -10, 0)
			line:SetJustifyH("LEFT")
			line:SetText(L[link.line])
		end
	end

	local function Refresh()
		if not check then
			Build()
		end
		local saved = Saved()
		check:SetChecked(not (saved and saved.suggestFamily == false))
		for _, row in ipairs(rows) do
			local folder = row.addon.folder
			local state = Family.State(folder)
			local own = folder == current
			-- art-ok: square icons at 32x32
			row.icon:SetTexture(Icon(folder, state))
			row.state:SetText(own and L["This addon"] or states[state])
			row.button:SetShown(not own)
		end
	end
	panel.Refresh, panel.OnRefresh = Refresh, Refresh
	function panel.OnDefault()
		local saved = Saved()
		if saved then
			saved.suggestFamily, saved.familyDismissed = true, nil
		end
		Refresh()
	end
	panel:SetScript("OnShow", Refresh)
	return panel
end

-- Blizzard builds the settings rows its gamepad navigation reads in secure execution. This page's row data is built
-- in addon execution, so what we hand Blizzard carries our taint; the row's gamepad fields then taint the binding
-- stack and closing the page has the game refuse an action and blame the addon (cjber/tweaks-forever#446). These
-- builders run as the client through CreateSecureDelegate, or directly on a build without it
-- (cjber/adventure-guide-forever#592).
local delegates = setmetatable({}, { __mode = "k" })
---@param fn function
---@return function
local function Secure(fn)
	if type(CreateSecureDelegate) ~= "function" then
		return fn
	end
	local delegate = delegates[fn]
	if not delegate then
		delegate = CreateSecureDelegate(fn)
		delegates[fn] = delegate
	end
	return delegate
end

-- The client's settings navigation enters only a vertical page. From a canvas page it picks the first row of the
-- vertical settings list, which still holds the previous page's rows, and leaves the cursor on a hidden frame. So
-- with the gamepad interface on, this registers the page from the client's own rows, which its navigation can enter.
---@param category table
---@param db ForeverFamilySaved
---@param current? string
---@param safeCall? ForeverSafeCall
---@return table
function Family.Register(category, db, current, safeCall)
	local L = Strings()
	if not (InputUtil and InputUtil.IsGamepadUIEnabled and InputUtil.IsGamepadUIEnabled()) then
		return Settings.RegisterCanvasLayoutSubcategory(
			category,
			Family.CreatePanel(nil, db, current, safeCall),
			L["Forever addons"]
		)
	end
	local subcategory = Settings.RegisterVerticalLayoutSubcategory(category, L["Forever addons"])
	local setting = Settings.RegisterProxySetting(
		subcategory,
		"ForeverFamily_" .. Owner(current) .. "_suggestFamily",
		Settings.VarType.Boolean,
		L["Suggest my other Forever addons"],
		true,
		function()
			local saved = ReadDb(safeCall, db)
			return not (saved and saved.suggestFamily == false)
		end,
		function(value)
			local saved = ReadDb(safeCall, db)
			if saved then
				saved.suggestFamily = value and true or false
			end
		end
	)
	Secure(Settings.CreateCheckbox)(
		subcategory,
		setting,
		L["Show a quiet line where one of my other Forever addons would help. Only for addons you don't have."]
	)
	for _, addon in ipairs(Family.ADDONS) do
		if addon.folder ~= current then
			Settings.RegisterInitializer(
				subcategory,
				Secure(CreateSettingsButtonInitializer)(addon.name, L["Copy link"], function()
					Family.ShowLink(nil, nil, addon.folder, nil)
				end, L[addon.line], false)
			)
		end
	end
	Settings.RegisterInitializer(
		subcategory,
		Secure(CreateSettingsButtonInitializer)(Family.SUPPORT.name, L["Copy link"], function()
			Family.ShowSupport()
		end, L[Family.SUPPORT.line], false)
	)
	return subcategory
end

ns.Family = Family
