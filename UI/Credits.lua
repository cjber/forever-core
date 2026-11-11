---@type string, ForeverCreditsNamespace
local _, ns = ...

-- The players behind the Forever addons, in one place in the game. Each addon ships a `Data/Credits.lua`, generated
-- from its THIRD_PARTY.md by tools/forever_tools/credits.py, and hands it to Register once it loads. This file merges
-- the lists by player name for the Thanks window and gives an addon the short line its own settings page shows.
-- Nothing here is protected, hooks Blizzard code or runs in combat: a credit is a string, and the window is made of
-- the client's own templates. The addon's author is never listed (WFA-33).

---@class ForeverCreditEntry
---@field name string
---@field what string what the player did, in one line

---@class ForeverCreditsData
---@field players? ForeverCreditEntry[]
---@field inspired? ForeverCreditEntry[]

---@class ForeverCreditHelped
---@field addon string the addon's title
---@field what string what the player did for that addon, in one line

---@class ForeverCreditRow
---@field name string
---@field helped ForeverCreditHelped[] every contribution, in registration order
---@field count integer how many rows carry this name across the shown addons

---@class ForeverCreditsRecord
---@field title string
---@field players ForeverCreditEntry[]
---@field inspired ForeverCreditEntry[]

---@alias ForeverCreditsMenuGenerator fun(owner: Region, root: ForeverMenuDescription)

---@class ForeverCreditsNamespace
---@field L? table<string, string>
---@field SafeCall? ForeverSafeCall
---@field ContextMenu? fun(owner: Region, generator: ForeverCreditsMenuGenerator): ForeverMenuDescription?
---@field CreditsPage? ForeverCreditsAPI

---@class ForeverCreditsRowWidget
---@field holder Frame
---@field name FontString
---@field count FontString
---@field detail FontString
---@field row? ForeverCreditRow

---@class ForeverCreditsDropdown : Button
---@field OpenMenu fun(self: ForeverCreditsDropdown)

---@class ForeverCreditsWindow : Frame
---@field SetTitle fun(self: ForeverCreditsWindow, title: string)
---@field GetPortrait fun(self: ForeverCreditsWindow): Texture
---@field contents Frame
---@field subtitle FontString
---@field inset Frame
---@field headers FontString[]
---@field rows ForeverCreditsRowWidget[]
---@field filterDropdown ForeverCreditsDropdown
---@field emptyText? FontString
---@field rendered? boolean

---@class ForeverCreditsAPI
---@field minor integer raised with each member the module adds
---@field Register fun(addonTitle: string, data: ForeverCreditsData?): boolean
---@field Line fun(addonTitle: string): string?
---@field Players fun(): ForeverCreditRow[]
---@field Inspired fun(): ForeverCreditRow[]
---@field Open fun(addonTitle?: string): boolean
---@field Toggle fun()
---@field IsShown fun(): boolean
---@field window? ForeverCreditsWindow the Thanks window once it is built
local credits = { minor = 1 }
local Build, Refresh, SetFilter

-- Every phrase reads from core's L, and as itself where that L has no entry, so a line is never half translated.
local strings
---@return table<string, string>
local function Strings()
	if not strings then
		local source = type(ns.L) == "table" and ns.L or {}
		strings = setmetatable({}, {
			__index = function(_, phrase)
				local text = rawget(source, phrase)
				return type(text) == "string" and text or phrase
			end,
		})
	end
	return strings
end

local MAX_LINE_NAMES = 3
local WINDOW_WIDTH = 460
local WINDOW_HEIGHT = 380
-- The title row, then the subtitle line, then the filter's own row, then the inset.
local HEADER_HEIGHT = 112
local INSET_MARGIN = 14
local BOTTOM = 14
-- The inset is INSET_MARGIN from each side, and the page 8 from its left and 28 from its right.
local CONTENT_WIDTH = WINDOW_WIDTH - INSET_MARGIN - INSET_MARGIN - 8 - 28
local SECTION_HEIGHT = 22
local SECTION_GAP = 8
local ROW_HEIGHT = 20
local NAME_COUNT_GAP = 4
local NAME_DETAIL_GAP = 8
-- Fits the suite's longest title ("Adventure Guide Forever") in GameFontHighlight; a longer one is cut with "...".
local DROPDOWN_WIDTH = 190
local DROPDOWN_HEIGHT = 22
-- The inset's right edge, so the dropdown lines up with the page below it, on the row under the subtitle.
local DROPDOWN_RIGHT = INSET_MARGIN
local DROPDOWN_TOP = 74
local MENU_EXTENT = 400
local DROPDOWN_TEMPLATE = "WowStyle1DropdownTemplate"
local ICON = "Interface\\Icons\\INV_Misc_Note_01"
local FRAME_NAME = "ForeverCreditsFrame"

---@type ForeverCreditsRecord[]
local records = {}
---@type table<string, ForeverCreditsRecord>
local byTitle = {}
-- The addon whose rows the page shows, in registration order; nil is every addon.
---@type string?
local filterTitle
-- Set by Register or a filter change, cleared by a render: a page that is already drawn is never drawn again.
local dirty = true

-- A phrase as a clean string, or nil when it is empty or not a string.
---@param value any
---@return string?
local function Text(value)
	if type(value) ~= "string" then
		return nil
	end
	local text = value:match("^%s*(.-)%s*$")
	return text ~= "" and text or nil
end

-- One generated list, as core keeps it: a name and what the player did, with anything malformed left out.
---@param list any
---@return ForeverCreditEntry[]
local function Entries(list)
	local entries = {}
	if type(list) ~= "table" then
		return entries
	end
	for index = 1, #list do
		local entry = list[index]
		if type(entry) == "table" then
			local name = Text(entry.name)
			if name then
				entries[#entries + 1] = { name = name, what = Text(entry.what) or "" }
			end
		end
	end
	return entries
end

-- Read one addon's table without letting a broken one reach its caller. A table that is not there is no credits.
---@param title string
---@param data any
---@return ForeverCreditsRecord?
local function Record(title, data)
	local ok, players, inspired = pcall(function()
		return Entries(data and data.players), Entries(data and data.inspired)
	end)
	if not ok then
		return nil
	end
	return { title = title, players = players, inspired = inspired }
end

-- Add one addon's credits. The title is the addon's own name, as its players see it; the same title replaces its
-- earlier list rather than appearing twice. Returns false for a title that is not a non-empty string.
---@param addonTitle string
---@param data ForeverCreditsData?
---@return boolean
function credits.Register(addonTitle, data)
	local title = Text(addonTitle)
	if not title then
		return false
	end
	local record = Record(title, data)
	if not record then
		record = { title = title, players = {}, inspired = {} }
	end
	local existing = byTitle[title]
	if existing then
		for index = 1, #records do
			if records[index] == existing then
				records[index] = record
				break
			end
		end
	else
		records[#records + 1] = record
	end
	byTitle[title] = record
	dirty = true
	if credits.window then
		if type(ns.SafeCall) == "function" then
			ns.SafeCall("credits refresh", Refresh)
		else
			Refresh()
		end
	end
	return true
end

-- Players rank by how many contributions they gave, then by name; an exact-name tie cannot leave a list unstable.
---@param rows ForeverCreditRow[]
local function SortPlayers(rows)
	table.sort(rows, function(left, right)
		if left.count ~= right.count then
			return left.count > right.count
		end
		local a, b = left.name:lower(), right.name:lower()
		if a ~= b then
			return a < b
		end
		return left.name < right.name
	end)
end

-- Inspired projects stay alphabetical, as a project has no contributions to rank.
---@param rows ForeverCreditRow[]
local function SortNames(rows)
	table.sort(rows, function(left, right)
		local a, b = left.name:lower(), right.name:lower()
		if a ~= b then
			return a < b
		end
		return left.name < right.name
	end)
end

-- Merge the named list across every registered addon, one row per exact player name. Every row the tables carry is
-- one contribution, so a player credited five times keeps five lines and a count of five.
---@param field "players"|"inspired"
---@return ForeverCreditRow[]
local function Merge(field)
	local rows, index = {}, {}
	for _, record in ipairs(records) do
		for _, entry in ipairs(record[field]) do
			local row = index[entry.name]
			if not row then
				row = { name = entry.name, helped = {}, count = 0 }
				index[entry.name] = row
				rows[#rows + 1] = row
			end
			row.helped[#row.helped + 1] = { addon = record.title, what = entry.what }
			row.count = row.count + 1
		end
	end
	if field == "players" then
		SortPlayers(rows)
	else
		SortNames(rows)
	end
	return rows
end

-- Every player once, with the addons they helped.
---@return ForeverCreditRow[]
function credits.Players()
	return Merge("players")
end

-- Every inspired project once, with the addons that credit it.
---@return ForeverCreditRow[]
function credits.Inspired()
	return Merge("inspired")
end

-- The short line an addon's own settings page shows: its players' names, up to three and a count of the rest.
---@param addonTitle string
---@return string?
function credits.Line(addonTitle)
	local title = Text(addonTitle)
	local record = title and byTitle[title]
	if not record then
		return nil
	end
	local L = Strings()
	local names, counts, first = {}, {}, {}
	for _, entry in ipairs(record.players) do
		if not counts[entry.name] then
			counts[entry.name] = 0
			first[entry.name] = #names + 1
			names[#names + 1] = entry.name
		end
		counts[entry.name] = counts[entry.name] + 1
	end
	table.sort(names, function(left, right)
		if counts[left] ~= counts[right] then
			return counts[left] > counts[right]
		end
		return first[left] < first[right]
	end)
	local count = #names
	if count == 0 then
		return nil
	end
	local listed
	if count == 1 then
		listed = names[1]
	elseif count == 2 then
		listed = L["%s and %s"]:format(names[1], names[2])
	elseif count == 3 then
		listed = L["%s, %s and %s"]:format(names[1], names[2], names[3])
	else
		listed = L["%s, %s, %s and %d more"]:format(names[1], names[2], names[3], count - MAX_LINE_NAMES)
	end
	return L["Thanks to %s"]:format(listed)
end

-- The addons a row credits, in registration order, or only one when the page is filtered to it.
---@param row ForeverCreditRow
---@return string
local function AddonList(row)
	local L = Strings()
	local addons, seen = {}, {}
	for _, helped in ipairs(row.helped) do
		if not seen[helped.addon] then
			seen[helped.addon] = true
			addons[#addons + 1] = helped.addon
		end
	end
	return table.concat(addons, L[", "])
end

-- What a row says after the player's name: the addon list, or that addon's own lines when the page is filtered.
---@param row ForeverCreditRow
---@return string
local function Detail(row)
	if filterTitle then
		local what, seen = {}, {}
		for _, helped in ipairs(row.helped) do
			if helped.what ~= "" and not seen[helped.what] then
				seen[helped.what] = true
				what[#what + 1] = helped.what
			end
		end
		return table.concat(what, Strings()[", "])
	end
	return AddonList(row)
end

-- A player's contributions grouped by the exact words they gave, in registration order: one sentence is one line
-- however many addons wrote it, and an addon is named once per sentence rather than once per contribution.
---@param helped ForeverCreditHelped[]
---@return { addons: string[], what: string }[]
local function GroupedLines(helped)
	local groups, byWhat, seen = {}, {}, {}
	for _, item in ipairs(helped) do
		local group = byWhat[item.what]
		if not group then
			group = { addons = {}, what = item.what }
			byWhat[item.what] = group
			groups[#groups + 1] = group
		end
		local key = item.what .. "\0" .. item.addon
		if not seen[key] then
			seen[key] = true
			group.addons[#group.addons + 1] = item.addon
		end
	end
	return groups
end

-- Only the rows that credit `title`, each carrying just that addon's line.
---@param rows ForeverCreditRow[]
---@param title string
---@return ForeverCreditRow[]
local function View(rows, title)
	local kept = {}
	for _, row in ipairs(rows) do
		local helped = {}
		for _, item in ipairs(row.helped) do
			if item.addon == title then
				helped[#helped + 1] = item
			end
		end
		if #helped > 0 then
			kept[#kept + 1] = { name = row.name, helped = helped, count = #helped }
		end
	end
	return kept
end

-- A row's tooltip title: the player, then how many contributions they gave when there is more than one.
---@param row ForeverCreditRow
---@return string
local function Title(row)
	if row.count > 1 then
		local L = Strings()
		return L["%s (%s)"]:format(row.name, L["%d contributions"]:format(row.count))
	end
	return row.name
end

-- Change the addon the page shows. A nil title is every addon; the window's label follows it.
---@param title string?
SetFilter = function(title)
	filterTitle = title and byTitle[title] and title or nil
	local frame = credits.window
	if frame and frame.filterDropdown then
		frame.filterDropdown:SetText(filterTitle or Strings()["All addons"])
	end
	dirty = true
	Refresh()
end

-- The Thanks window: one scrollable page, players first, then a short Inspired by group.
---@return ForeverCreditsWindow
Build = function()
	if credits.window then
		return credits.window
	end
	local L = Strings()
	local frame = CreateFrame("Frame", FRAME_NAME, UIParent, "PortraitFrameTemplate") --[[@as ForeverCreditsWindow]]
	if not tContains(UISpecialFrames, FRAME_NAME) then
		-- Escape closes it like any panel (an addon-owned frame).
		table.insert(UISpecialFrames, FRAME_NAME)
	end
	frame:SetSize(WINDOW_WIDTH, WINDOW_HEIGHT)
	frame:SetPoint("CENTER")
	frame:SetFrameStrata("DIALOG")
	frame:SetToplevel(true)
	frame:SetClampedToScreen(true)
	frame:SetMovable(true)
	frame:EnableMouse(true)
	frame:RegisterForDrag("LeftButton")
	frame:SetScript("OnDragStart", frame.StartMoving)
	frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
	frame:SetTitle(L["Thanks"])
	-- art-ok: a square icon in the template's round portrait
	frame:GetPortrait():SetTexture(ICON)

	local subtitle = frame:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
	subtitle:SetPoint("TOPLEFT", 62, -54)
	-- The words stay on one line; the filter has the row below it now.
	subtitle:SetPoint("RIGHT", frame, "RIGHT", -INSET_MARGIN, 0)
	subtitle:SetJustifyH("LEFT")
	subtitle:SetText(L["The players who helped each Forever addon."])
	frame.subtitle = subtitle

	-- The addon filter: the client's own dropdown, so it is drawn and pressed as every other dropdown in the client.
	-- Its press opens the suite's context menu, which scrolls past a long suite (WFA-36), instead of Blizzard's menu.
	local dropdown = CreateFrame("DropdownButton", nil, frame, DROPDOWN_TEMPLATE) --[[@as ForeverCreditsDropdown]]
	dropdown:SetSize(DROPDOWN_WIDTH, DROPDOWN_HEIGHT)
	dropdown:SetPoint("TOPRIGHT", -DROPDOWN_RIGHT, -DROPDOWN_TOP)
	dropdown:SetText(filterTitle or L["All addons"])
	dropdown.OpenMenu = function(self)
		if type(ns.ContextMenu) ~= "function" then
			return
		end
		ns.ContextMenu(self, function(_, root)
			root:SetScrollMode(MENU_EXTENT)
			-- The page shows one addon at a time, so each choice is a radio, not a checkbox.
			root:CreateRadio(L["All addons"], function()
				return filterTitle == nil
			end, function()
				SetFilter(nil)
			end)
			for _, record in ipairs(records) do
				local title = record.title
				root:CreateRadio(title, function()
					return filterTitle == title
				end, function()
					SetFilter(title)
				end)
			end
		end)
	end
	frame.filterDropdown = dropdown

	local inset = CreateFrame("Frame", nil, frame, "InsetFrameTemplate")
	inset:SetPoint("TOPLEFT", INSET_MARGIN, -HEADER_HEIGHT)
	inset:SetPoint("BOTTOMRIGHT", -INSET_MARGIN, BOTTOM)
	frame.inset = inset --[[@as Frame]]

	local scroll = CreateFrame("ScrollFrame", nil, inset, "ScrollFrameTemplate")
	scroll:SetPoint("TOPLEFT", 8, -8)
	scroll:SetPoint("BOTTOMRIGHT", -28, 8)
	local content = CreateFrame("Frame", nil, scroll)
	content:SetWidth(CONTENT_WIDTH)
	scroll:SetScrollChild(content)

	frame.contents = content
	frame.headers = {}
	frame.rows = {}
	credits.window = frame
	frame:SetScript("OnShow", function()
		if type(ns.SafeCall) == "function" then
			ns.SafeCall("credits page", Refresh)
		else
			Refresh()
		end
	end)
	return frame
end

-- Lay the current credits out again, reusing the page's rows and hiding the ones it does not need.
---@param frame ForeverCreditsWindow
local function Render(frame)
	local L = Strings()
	local content = frame.contents
	local headers, rows, emptyText = frame.headers, frame.rows, frame.emptyText
	local usedHeaders, usedRows = 0, 0
	local y = 0

	---@param header string
	local function Section(header)
		usedHeaders = usedHeaders + 1
		local title = headers[usedHeaders]
		if not title then
			title = content:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
			headers[usedHeaders] = title
		end
		title:ClearAllPoints()
		title:SetPoint("TOPLEFT", 0, y)
		title:SetTextColor(NORMAL_FONT_COLOR:GetRGB())
		title:SetText(header)
		title:Show()
		y = y - SECTION_HEIGHT
	end

	---@param row ForeverCreditRow
	local function Row(row)
		usedRows = usedRows + 1
		local item = rows[usedRows]
		if not item then
			local holder = CreateFrame("Button", nil, content) --[[@as Button]]
			holder:SetWidth(CONTENT_WIDTH)
			holder:SetHeight(ROW_HEIGHT)
			-- The quest log's highlight bar, struck across the row, is the client's own list hover. The row's words sit
			-- above it, in the OVERLAY layer, as every highlighted list row's do.
			holder:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
			local name = holder:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
			name:SetPoint("LEFT", 0, 0)
			name:SetJustifyH("LEFT")
			name:SetJustifyV("MIDDLE")
			local count = holder:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
			count:SetPoint("LEFT", name, "RIGHT", NAME_COUNT_GAP, 0)
			count:SetJustifyH("LEFT")
			count:SetJustifyV("MIDDLE")
			count:SetTextColor(GRAY_FONT_COLOR:GetRGB())
			local detail = holder:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
			detail:SetPoint("LEFT", count, "RIGHT", NAME_DETAIL_GAP, 0)
			detail:SetPoint("RIGHT", 0, 0)
			detail:SetJustifyH("LEFT")
			detail:SetJustifyV("MIDDLE")
			detail:SetTextColor(GRAY_FONT_COLOR:GetRGB())
			-- The client cuts a long line rather than wrapping it, so every row is exactly ROW_HEIGHT tall.
			detail:SetWordWrap(false)
			detail:SetMaxLines(1)
			item = { holder = holder, name = name, count = count, detail = detail }
			holder:SetScript("OnEnter", function(self)
				local current = item.row
				if not current or not GameTooltip then
					return
				end
				GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
				if type(GameTooltip_SetTitle) == "function" then
					GameTooltip_SetTitle(GameTooltip, Title(current))
				else
					GameTooltip:SetText(Title(current), 1, 1, 1)
				end
				local red, green, blue = NORMAL_FONT_COLOR:GetRGB()
				local gold = ("|cff%02x%02x%02x"):format(
					math.floor(red * 255 + 0.5),
					math.floor(green * 255 + 0.5),
					math.floor(blue * 255 + 0.5)
				)
				-- One addon's sentence is shared by every addon that wrote the very same words, so it is drawn
				-- once, led by those addons in registration order.
				for _, group in ipairs(GroupedLines(current.helped)) do
					local line = gold .. table.concat(group.addons, L[", "]) .. "|r"
					if group.what ~= "" then
						line = line .. ": " .. group.what
					end
					GameTooltip:AddLine(line, 1, 1, 1, true)
				end
				GameTooltip:Show()
			end)
			holder:SetScript("OnLeave", GameTooltip_Hide)
			rows[usedRows] = item
		end
		item.holder:ClearAllPoints()
		item.holder:SetPoint("TOPLEFT", 0, y)
		item.holder:SetHeight(ROW_HEIGHT)
		item.row = row
		item.name:SetText(row.name)
		if row.count > 1 then
			item.count:SetText(("x%d"):format(row.count))
			item.count:Show()
		else
			item.count:SetText("")
			item.count:Hide()
		end
		item.detail:SetText(Detail(row))
		item.holder:Show()
		y = y - ROW_HEIGHT
	end

	local players = credits.Players()
	local inspired = credits.Inspired()
	if filterTitle then
		players = View(players, filterTitle)
		SortPlayers(players)
		inspired = View(inspired, filterTitle)
	end
	if #players > 0 then
		Section(L["Players"])
		for _, row in ipairs(players) do
			Row(row)
		end
		y = y - SECTION_GAP
	end
	if #inspired > 0 then
		Section(L["Inspired by"])
		for _, row in ipairs(inspired) do
			Row(row)
		end
	end
	if #players == 0 and #inspired == 0 then
		if not emptyText then
			emptyText = content:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
			emptyText:SetPoint("TOP", 0, -24)
			emptyText:SetWidth(CONTENT_WIDTH)
			emptyText:SetJustifyH("CENTER")
			emptyText:SetText(L["No one is listed yet."])
			frame.emptyText = emptyText
		end
		emptyText:Show()
		y = -50
	elseif emptyText then
		emptyText:Hide()
	end
	for index = usedRows + 1, #rows do
		rows[index].holder:Hide()
	end
	for index = usedHeaders + 1, #headers do
		headers[index]:Hide()
	end
	content:SetHeight(math.max(1, -y))
	-- The height is fixed, so the page keeps its place while the list changes rather than growing past the screen.
	frame:SetHeight(WINDOW_HEIGHT)
end

-- Draw the merged list into the open window. A page that is already up to date is left alone, so opening it twice
-- creates no frames; Register or a filter change marks it dirty and the next Refresh draws it. Safe to call before
-- the window exists.
Refresh = function()
	local frame = credits.window
	if not frame then
		return
	end
	if not dirty and frame.rendered then
		return
	end
	Render(frame)
	dirty = false
	frame.rendered = true
end

-- The latest registered data, drawn and shown. Called with no argument it reopens on the filter the page already
-- shows; called with an addon title it filters to that addon, and called with an explicit nil it shows every addon.
-- Returns false only when the client cannot build the window.
---@return boolean
function credits.Open(...)
	if select("#", ...) > 0 then
		local requested = Text((...))
		local wanted = requested and byTitle[requested] and requested or nil
		if wanted ~= filterTitle then
			filterTitle = wanted
			dirty = true
		end
	end
	local built, frame = pcall(Build)
	if not built or not frame then
		return false
	end
	local shown = pcall(function()
		frame.filterDropdown:SetText(filterTitle or Strings()["All addons"])
		Refresh()
		frame:Show()
	end)
	return shown
end

function credits.Toggle()
	local window = credits.window
	if window and window:IsShown() then
		window:Hide()
	else
		-- No argument: the filter the page already shows survives a close and reopen.
		credits.Open()
	end
end

---@return boolean
function credits.IsShown()
	return credits.window ~= nil and credits.window:IsShown() == true
end

-- The module is built, the window is not; a caller that opens it gets the client's own portrait frame. The module is
-- ns.CreditsPage, not ns.Credits: in core's own namespace ns.Credits is its generated Data/Credits.lua table, as it
-- is in every addon that hands one to Register.
ns.CreditsPage = credits
