---@type string, ForeverLeaderboardsNamespace
local _, ns = ...

-- One Forever Leaderboards window for every Forever addon. This file is byte-identical in every consumer: each addon
-- registers its own board with ForeverLeaderboards:Register, and this file draws them. The first copy to load publishes
-- the `ForeverLeaderboards` global; later copies join it unless one is newer (a higher VERSION), which takes over with
-- the registrations already made. Nothing here is protected, hooks Blizzard frames beyond one unit-tooltip hook, or
-- writes to chat: a board is a callback, a row is a table, and the window is made of the client's own templates.
--
-- Core/LeaderboardsData.lua, loaded first, owns overall points, a player's standing, the per-scope cache and the
-- tooltip text; this file owns the window and the registration.

---@class ForeverLeaderboardsNamespace
---@field Leaderboards? ForeverLeaderboardsAPI
---@field LeaderboardsData? ForeverLeaderboardsData
---@field L? table<string, string>

---@alias ForeverLeaderboardsScope "week"|"all"

---@class ForeverLeaderboardsRow
---@field name string the player's display name
---@field identity? string the compacted key the row was ranked under, when the board supplies one
---@field class? string a RAID_CLASS_COLORS key, e.g. "HUNTER"
---@field value number the number in the right-hand column
---@field extra? string the grey value before it, e.g. "377 total" or "5 boards"
---@field you? boolean the player's own row

---@class ForeverLeaderboardsSpec
---@field key? string the registered key, filled in by Register
---@field seq? number registration order within the same `order`
---@field title string the addon's name, on its tab and in its tooltip place
---@field icon string the addon's own icon for its side tab
---@field metric string the heading above the list, e.g. "Quests turned in"
---@field order? number tab order after Overall; registration order when omitted
---@field board fun(scope: ForeverLeaderboardsScope): ForeverLeaderboardsRow[] rows, sorted by the caller
---@field revision? fun(): number a counter bumped when the board's data changes; the cache rebuilds when it moves
---@field sharing? fun(): boolean the addon's saved sharing switch; only an explicit false means off
---@field setSharing? fun(shared: boolean) saves the switch and syncs the addon's rows

---@class ForeverLeaderboardsPlace
---@field key string the board's registered key
---@field title string the addon's name
---@field rank integer the place on that board
---@field points integer points that place is worth

---@class ForeverLeaderboardsPlayer
---@field identity string
---@field name string
---@field class? string
---@field you? boolean
---@field found boolean
---@field points integer
---@field rank integer
---@field boards integer
---@field places ForeverLeaderboardsPlace[]

---@class ForeverLeaderboardsStanding
---@field found boolean the player is on at least one registered board
---@field points integer the summed points across boards
---@field rank integer the overall place, or 0 without points
---@field boards integer boards on which the player placed
---@field places ForeverLeaderboardsPlace[] the per-addon places, in tab order

---@class ForeverLeaderboardsDisplayRow
---@field name string
---@field class? string
---@field value number
---@field extra? string
---@field you boolean
---@field rank integer
---@field weekly boolean

local LEADERBOARDS_VERSION = 1
local OVERALL = "overall"
local TROPHY = "Interface\\Icons\\INV_Misc_Trophy_Argent"
local ROW_HEIGHT = 30
local SPACER_HEIGHT = 16
local WINDOW_WIDTH, WINDOW_HEIGHT = 460, 560
local VISIBLE_ROWS = 12
local FRAME_NAME = "ForeverLeaderboardsFrame"
local DROPDOWN_TEMPLATE = "WowStyle1DropdownTemplate"

-- A newer copy builds its own window rather than reusing the name an older copy's hidden window still holds, so a
-- takeover never leaves two layouts on one frame.
---@return string
local function WindowName()
	if LEADERBOARDS_VERSION == 1 then
		return FRAME_NAME
	end
	return FRAME_NAME .. LEADERBOARDS_VERSION
end
local data = ns.LeaderboardsData
if type(data) ~= "table" or type(data.Overall) ~= "function" then
	return
end
local MEDALS = data.MEDALS

local previous = ForeverLeaderboards
if type(previous) == "table" and (tonumber(previous.VERSION) or 0) >= LEADERBOARDS_VERSION then
	ns.Leaderboards = previous
	return
end

---@class ForeverLeaderboardsAPI
---@field VERSION integer raised with every change to this file
---@field LEADERBOARDS_VERSION integer the same version, under the name the file compares
---@field scope ForeverLeaderboardsScope the selected scope
---@field selected? string the board the window shows
---@field window? ForeverLeaderboardsWindow the window once built, for a newer copy to put away
---@field tooltipHooked? boolean the one unit-tooltip hook is already installed
---@field ClassOf fun(name: string): string? the client's class token for a player name, when it knows one
---@field registration integer raised with every successful Register, so the data cache notices the board list
local api = {
	VERSION = LEADERBOARDS_VERSION,
	LEADERBOARDS_VERSION = LEADERBOARDS_VERSION,
	boards = {},
	order = {},
	scope = "week",
	registration = 0,
}
local sequence = 0
local BuildTabs, Refresh

if type(previous) == "table" then
	for _, key in ipairs(previous.order or {}) do
		local spec = type(previous.boards) == "table" and previous.boards[key]
		if type(spec) == "table" then
			sequence = sequence + 1
			spec.seq = type(spec.seq) == "number" and spec.seq == spec.seq and spec.seq or sequence
			sequence = math.max(sequence, spec.seq)
			api.boards[key], api.order[#api.order + 1] = spec, key
		end
	end
	if type(previous.window) == "table" and previous.window.Hide then
		previous.window:Hide()
	end
	api.tooltipHooked = previous.tooltipHooked == true
	if previous.scope == "all" or previous.scope == "week" then
		api.scope = previous.scope
	end
	if type(previous.selected) == "string" then
		api.selected = previous.selected
	end
end

ForeverLeaderboards = api -- taint-ok: addon-owned registry shared by the Forever addons
ns.Leaderboards = api

-- The copy now in charge when a newer version has taken over the global since this one loaded: an addon still holding
-- this copy is then served by the newer one, so there is only ever one window and one tooltip hook.
---@return ForeverLeaderboardsAPI?
local function Newer()
	local current = ForeverLeaderboards
	if current ~= api and type(current) == "table" and (tonumber(current.VERSION) or 0) > LEADERBOARDS_VERSION then
		return current --[[@as ForeverLeaderboardsAPI]]
	end
end

local function Strings()
	return data.Strings()
end

local function Identity(name, realm)
	return data.Identity(name, realm)
end

local function OwnName()
	return data.OwnName()
end

--------------------------------------------------------------------------------------------------------------------
-- Boards

-- The registered boards in tab order: `order` when the caller supplied one, then registration order.
---@return ForeverLeaderboardsSpec[]
function api:Boards()
	local list = {}
	for _, key in ipairs(self.order) do
		list[#list + 1] = self.boards[key]
	end
	table.sort(list, function(a, b)
		local left, right = tonumber(a.order) or 0, tonumber(b.order) or 0
		if left ~= right then
			return left < right
		end
		return (tonumber(a.seq) or 0) < (tonumber(b.seq) or 0)
	end)
	return list
end

---@param key string
---@param spec ForeverLeaderboardsSpec
---@return boolean registered
function api:Register(key, spec)
	local newer = Newer()
	if newer then
		return newer:Register(key, spec)
	end
	if type(key) ~= "string" or key == "" or #key > 32 or key == OVERALL or not key:find("^[%w_%-]+$") then
		return false
	end
	if
		type(spec) ~= "table"
		or type(spec.title) ~= "string"
		or spec.title == ""
		or type(spec.metric) ~= "string"
		or spec.metric == ""
		or type(spec.icon) ~= "string"
		or spec.icon == ""
		or type(spec.board) ~= "function"
	then
		return false
	end
	local old = self.boards[key]
	if not old then
		sequence = sequence + 1
		self.order[#self.order + 1] = key
	end
	local order = tonumber(spec.order)
	if not order or order ~= order then
		order = old and old.order or #self.order
	end
	self.boards[key] = {
		key = key,
		title = spec.title,
		metric = spec.metric,
		icon = spec.icon,
		order = order,
		seq = old and old.seq or sequence,
		board = spec.board,
		revision = type(spec.revision) == "function" and spec.revision or nil,
		sharing = type(spec.sharing) == "function" and spec.sharing or nil,
		setSharing = type(spec.setSharing) == "function" and spec.setSharing or nil,
	}
	self.registration = (tonumber(self.registration) or 0) + 1
	if self.window then
		BuildTabs(self.window)
		Refresh()
	end
	return true
end

-- The overall board for the window and the standing of one player. Both read Core/LeaderboardsData.lua's cache, so
-- the open window and a tooltip hover share one build until a revision, the scope, the board list or the week moves.
---@param scope? ForeverLeaderboardsScope
---@return ForeverLeaderboardsRow[]
function api:Overall(scope)
	local newer = Newer()
	if newer then
		return newer:Overall(scope)
	end
	return data.Overall(self, scope or self.scope)
end

---@param name string
---@param scope? ForeverLeaderboardsScope
---@return ForeverLeaderboardsStanding
function api:Standing(name, scope)
	local newer = Newer()
	if newer then
		return newer:Standing(name, scope)
	end
	return data.Standing(self, name, scope or self.scope)
end

-- The client's own class for a player name, so a board does not need a ClassOf helper of its own. A name the client has
-- not heard of returns nil, and the row draws without an icon in the neutral colour.
---@param name string
---@return string?
function api.ClassOf(name)
	local newer = Newer()
	if newer then
		return newer.ClassOf(name)
	end
	return data.ClassOf(name)
end

-- One board's display rows: the caller's order, with the weekly flag for the value column and a rank for the medal.
---@param key string
---@param scope ForeverLeaderboardsScope
---@return ForeverLeaderboardsDisplayRow[]
local function Rows(key, scope)
	local L = Strings()
	local rows = {}
	if key == OVERALL then
		for _, row in ipairs(api:Overall(scope)) do
			rows[#rows + 1] = {
				name = row.name,
				identity = row.identity,
				class = type(row.class) == "string" and row.class or data.ClassOf(row.name),
				value = row.value,
				extra = row.extra,
				you = row.you == true,
				rank = #rows + 1,
				weekly = false,
			}
		end
		local placed = false
		local own = Identity(OwnName())
		for _, row in ipairs(rows) do
			if not row.you and own and (row.identity or Identity(row.name)) == own then
				row.you = true
			end
			placed = placed or row.you
		end
		if not placed then
			local name = OwnName()
			local identity = Identity(name)
			if name and identity then
				local standing = api:Standing(name, scope)
				if standing.found then
					rows[#rows + 1] = {
						name = name,
						class = data.ClassOf(name),
						value = 0,
						extra = "0 " .. L["boards"],
						you = true,
						rank = #rows + 1,
						weekly = false,
					}
				end
			end
		end
		return rows
	end
	local spec = api.boards[key]
	if not spec then
		return rows
	end
	local ok, list = pcall(spec.board, scope)
	if not ok or type(list) ~= "table" then
		return rows
	end
	local weekly = scope == "week"
	for _, row in ipairs(list) do
		local name = type(row) == "table" and row.name
		if type(name) == "string" and name ~= "" then
			local value = tonumber(row.value)
			rows[#rows + 1] = {
				name = name,
				class = type(row.class) == "string" and row.class or data.ClassOf(name),
				value = value and value == value and value or 0,
				extra = type(row.extra) == "string" and row.extra or nil,
				you = row.you == true,
				rank = #rows + 1,
				weekly = weekly,
			}
		end
	end
	return rows
end

--------------------------------------------------------------------------------------------------------------------
-- Window

---@class ForeverLeaderboardsRowButton : Button
---@field highlight Texture
---@field rankMedal Texture
---@field rankText FontString
---@field classIcon Texture
---@field nameText FontString
---@field extra FontString
---@field value FontString

---@class ForeverLeaderboardsScrollBox : Frame
---@field SetDataProvider fun(self: ForeverLeaderboardsScrollBox, provider: any, scrollContext?: any)

---@class ForeverLeaderboardsDropdown : Frame
---@field SetDefaultText fun(self: ForeverLeaderboardsDropdown, text: string)
---@field SetupMenu fun(self: ForeverLeaderboardsDropdown, generator: fun(owner: Frame, root: any))

---@alias ForeverLeaderboardsTabMouseUp fun(self: Frame, button: string, upInside: boolean)

---@class ForeverLeaderboardsTab : Frame
---@field Icon Texture
---@field key string
---@field tooltipText? string
---@field SetChecked fun(self: ForeverLeaderboardsTab, checked: boolean)
---@field SetCustomOnMouseUpHandler fun(self: ForeverLeaderboardsTab, handler: ForeverLeaderboardsTabMouseUp)

---@class ForeverLeaderboardsWindow : Frame
---@field SetTitle fun(self: ForeverLeaderboardsWindow, title: string)
---@field GetPortrait fun(self: ForeverLeaderboardsWindow): Texture
---@field heading FontString
---@field subtitle FontString
---@field valueHeader FontString
---@field inset Frame
---@field dropdown ForeverLeaderboardsDropdown
---@field scroll ForeverLeaderboardsScrollBox
---@field pinned ForeverLeaderboardsRowButton
---@field pinnedSpacer FontString
---@field share CheckButton
---@field shareSetter? fun(shared: boolean)
---@field shareLabel FontString
---@field note FontString
---@field empty FontString
---@field tabs ForeverLeaderboardsTab[]

---@param button ForeverLeaderboardsRowButton
local function InitRow(button)
	if rawget(button, "nameText") then
		return
	end
	button:SetHeight(ROW_HEIGHT)
	button.highlight = button:CreateTexture(nil, "BACKGROUND")
	button.highlight:SetAtlas("auctionhouse-ui-row-select")
	button.highlight:SetAllPoints()
	button.highlight:Hide()

	button.rankMedal = button:CreateTexture(nil, "ARTWORK")
	button.rankMedal:SetSize(24, 24)
	button.rankMedal:SetPoint("LEFT", 12, 0)

	button.rankText = button:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
	button.rankText:SetPoint("LEFT", 12, 0)
	button.rankText:SetWidth(24)
	button.rankText:SetJustifyH("CENTER")

	button.classIcon = button:CreateTexture(nil, "ARTWORK")
	button.classIcon:SetSize(22, 22)
	button.classIcon:SetPoint("LEFT", 45, 0)

	button.nameText = button:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
	button.nameText:SetPoint("LEFT", 76, 0)
	button.nameText:SetJustifyH("LEFT")

	button.value = button:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
	button.value:SetPoint("RIGHT", -12, 0)
	button.value:SetWidth(80)
	button.value:SetJustifyH("RIGHT")

	button.extra = button:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
	button.extra:SetPoint("RIGHT", button.value, "LEFT", -10, 0)
	button.extra:SetWidth(90)
	button.extra:SetJustifyH("RIGHT")
	button.nameText:SetPoint("RIGHT", button.extra, "LEFT", -10, 0)
end

---@param button ForeverLeaderboardsRowButton
---@param row ForeverLeaderboardsDisplayRow
local function RenderRow(button, row)
	local L = Strings()
	button.highlight:SetShown(row.you)
	if row.rank <= 3 then
		button.rankMedal:SetAtlas(MEDALS[row.rank])
		button.rankMedal:Show()
		button.rankText:Hide()
	else
		button.rankMedal:Hide()
		button.rankText:SetText(tostring(row.rank))
		button.rankText:Show()
	end
	local class = type(row.class) == "string" and row.class:upper() or nil
	if class and class ~= "" then
		button.classIcon:SetAtlas("groupfinder-icon-class-" .. class:lower())
		button.classIcon:Show()
	else
		button.classIcon:Hide()
	end
	local color = class and RAID_CLASS_COLORS and RAID_CLASS_COLORS[class]
	button.nameText:SetText(row.you and (row.name .. " " .. L["(you)"]) or row.name)
	local r, g, b = HIGHLIGHT_FONT_COLOR:GetRGB()
	if color then
		r, g, b = color:GetRGB()
	end
	button.nameText:SetTextColor(r, g, b)
	button.extra:SetText(row.extra or "")
	button.extra:SetTextColor(GRAY_FONT_COLOR:GetRGB())
	if row.weekly then
		button.value:SetText("+" .. row.value)
		button.value:SetTextColor(GREEN_FONT_COLOR:GetRGB())
	else
		button.value:SetText(tostring(row.value))
		button.value:SetTextColor(HIGHLIGHT_FONT_COLOR:GetRGB())
	end
end

---@param frame ForeverLeaderboardsWindow
function BuildTabs(frame)
	local L = Strings()
	for _, tab in ipairs(frame.tabs or {}) do
		tab:Hide()
	end
	frame.tabs = {}
	local list = { { key = OVERALL, title = L["Overall"], icon = TROPHY } }
	for _, spec in ipairs(api:Boards()) do
		list[#list + 1] = spec
	end
	local last
	for index, entry in ipairs(list) do
		local tab = CreateFrame("Frame", nil, frame, "LargeSideTabButtonTemplate") --[[@as ForeverLeaderboardsTab]]
		if last then
			tab:SetPoint("TOP", last, "BOTTOM", 0, -3)
		else
			tab:SetPoint("TOPLEFT", frame, "TOPRIGHT", -4, -30)
		end
		tab.Icon:SetTexture(entry.icon)
		tab.key = entry.key
		tab.tooltipText = entry.title
		tab:EnableMouse(true)
		tab:SetCustomOnMouseUpHandler(function(_, button, upInside)
			if button == "LeftButton" and upInside then
				api:Select(entry.key)
			end
		end)
		tab:SetChecked(false)
		frame.tabs[index] = tab
		last = tab
	end
end

---@param frame ForeverLeaderboardsWindow
local function RefreshTabs(frame)
	for _, tab in ipairs(frame.tabs or {}) do
		tab:SetChecked(tab.key == api.selected)
	end
end

function Refresh()
	local L = Strings()
	local frame = api.window
	if not frame then
		return
	end
	local key = api.selected or OVERALL
	if key ~= OVERALL and not api.boards[key] then
		key = OVERALL
	end
	api.selected = key
	local spec = key ~= OVERALL and api.boards[key] or nil
	frame.heading:SetText(spec and spec.metric or L["Forever standing"])
	frame.subtitle:SetText(L["Your guild and group"])
	frame.valueHeader:SetText(api.scope == "week" and L["This week"] or L["All time"])
	frame.dropdown:SetDefaultText(api.scope == "week" and L["This week"] or L["All time"])
	RefreshTabs(frame)

	local rows = Rows(key, api.scope)
	local ownIndex
	for index, row in ipairs(rows) do
		if row.you then
			ownIndex = index
			break
		end
	end
	local pinned = ownIndex ~= nil and ownIndex > VISIBLE_ROWS
	frame.pinned:SetShown(pinned)
	frame.pinnedSpacer:SetShown(pinned)
	local bottom = pinned and (4 + ROW_HEIGHT + SPACER_HEIGHT) or 4
	frame.scroll:ClearAllPoints()
	frame.scroll:SetPoint("TOPLEFT", frame.inset, "TOPLEFT", 4, -26)
	frame.scroll:SetPoint("BOTTOMRIGHT", frame.inset, "BOTTOMRIGHT", -24, bottom)
	if pinned then
		RenderRow(frame.pinned, rows[ownIndex])
	end

	local list = rows
	if pinned then
		list = {}
		for _, row in ipairs(rows) do
			if not row.you then
				list[#list + 1] = row
			end
		end
	end
	frame.empty:SetShown(#rows == 0)
	frame.scroll:SetDataProvider(
		CreateDataProvider(list),
		ScrollBoxConstants and ScrollBoxConstants.RetainScrollPosition
	)

	local sharing, setSharing
	if spec then
		sharing = type(spec.sharing) == "function" and spec.sharing or nil
		setSharing = type(spec.setSharing) == "function" and spec.setSharing or nil
	else
		-- Overall has no board of its own: its switch reads and writes every registered board that offers one.
		local shareable = {}
		for _, board in ipairs(api:Boards()) do
			if type(board.sharing) == "function" and type(board.setSharing) == "function" then
				shareable[#shareable + 1] = board
			end
		end
		if #shareable > 0 then
			sharing = function()
				for _, board in ipairs(shareable) do
					local ok, shared = pcall(board.sharing)
					if ok and shared == false then
						return false
					end
				end
				return true
			end
			setSharing = function(value)
				for _, board in ipairs(shareable) do
					pcall(board.setSharing, value)
				end
			end
		end
	end
	frame.shareSetter = setSharing
	frame.share:SetShown(sharing ~= nil and setSharing ~= nil)
	frame.shareLabel:SetShown(sharing ~= nil and setSharing ~= nil)
	if sharing then
		-- Sharing is opt-out: only an explicit false unchecks it, so a missing saved setting reads as on.
		local ok, shared = pcall(sharing)
		frame.share:SetChecked(not ok or shared ~= false)
	end
	frame.note:SetText(
		key == OVERALL and L["Points for placing on each addon's board."] or L["Others' values are player-reported."]
	)
end

---@return ForeverLeaderboardsWindow
local function Window()
	if api.window then
		return api.window
	end
	local older = type(previous) == "table" and previous.window
	if type(older) == "table" and type(older.Hide) == "function" then
		older:Hide()
	end
	local L = Strings()
	local name = WindowName()
	local frame = CreateFrame("Frame", name, UIParent, "PortraitFrameTemplate") --[[@as ForeverLeaderboardsWindow]]
	if not tContains(UISpecialFrames, name) then
		-- Escape closes it like any panel (an addon-owned frame).
		table.insert(UISpecialFrames, name)
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
	frame:SetTitle(L["Forever Leaderboards"])
	frame:GetPortrait():SetTexture(TROPHY)

	frame.heading = frame:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
	frame.heading:SetPoint("TOPLEFT", 62, -34)
	frame.heading:SetTextColor(NORMAL_FONT_COLOR:GetRGB())

	frame.subtitle = frame:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
	frame.subtitle:SetPoint("TOPLEFT", 62, -54)
	frame.subtitle:SetText(L["Your guild and group"])

	local dropdown = CreateFrame("DropdownButton", nil, frame, DROPDOWN_TEMPLATE) --[[@as ForeverLeaderboardsDropdown]]
	dropdown:SetSize(140, 24)
	dropdown:SetPoint("TOPRIGHT", -16, -60)
	dropdown:SetupMenu(function(_, root)
		root:SetScrollMode(300)
		root:CreateRadio(L["This week"], function()
			return api.scope == "week"
		end, function()
			api.scope = "week"
			Refresh()
		end)
		root:CreateRadio(L["All time"], function()
			return api.scope == "all"
		end, function()
			api.scope = "all"
			Refresh()
		end)
	end)
	dropdown:SetDefaultText(L["This week"])
	frame.dropdown = dropdown

	local inset = CreateFrame("Frame", nil, frame, "InsetFrameTemplate")
	inset:SetPoint("TOPLEFT", 14, -92)
	inset:SetPoint("BOTTOMRIGHT", -14, 74)
	frame.inset = inset --[[@as Frame]]

	local rankHeader = inset:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
	rankHeader:SetPoint("TOPLEFT", 12, -8)
	rankHeader:SetText(L["Rank"])
	local playerHeader = inset:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
	playerHeader:SetPoint("TOPLEFT", 76, -8)
	playerHeader:SetText(L["Player"])
	frame.valueHeader = inset:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
	frame.valueHeader:SetPoint("TOPRIGHT", -12, -8)
	frame.valueHeader:SetWidth(80)
	frame.valueHeader:SetJustifyH("RIGHT")

	local divider = inset:CreateTexture(nil, "ARTWORK")
	divider:SetAtlas("_UI-Frame-InnerTopTile")
	divider:SetPoint("TOPLEFT", 4, -24)
	divider:SetPoint("RIGHT", -4, 0)
	divider:SetHeight(3)

	local scroll = CreateFrame("Frame", nil, inset, "WowScrollBoxList") --[[@as ForeverLeaderboardsScrollBox]]
	scroll:SetPoint("TOPLEFT", 4, -26)
	scroll:SetPoint("BOTTOMRIGHT", -24, 4)
	local scrollBar = CreateFrame("EventFrame", nil, inset, "MinimalScrollBar")
	scrollBar:SetPoint("TOPLEFT", scroll, "TOPRIGHT", 4, 0)
	scrollBar:SetPoint("BOTTOMLEFT", scroll, "BOTTOMRIGHT", 4, 0)
	local view = CreateScrollBoxListLinearView()
	-- A bare Button has no XML template for the view to read a height from, so the row height is set here.
	view:SetElementExtent(ROW_HEIGHT)
	view:SetElementInitializer("Button", function(button, entry)
		local rowButton = button --[[@as ForeverLeaderboardsRowButton]]
		InitRow(rowButton)
		RenderRow(rowButton, entry)
	end)
	ScrollUtil.InitScrollBoxListWithScrollBar(scroll, scrollBar, view)
	frame.scroll = scroll

	local pinned = CreateFrame("Button", nil, inset) --[[@as ForeverLeaderboardsRowButton]]
	InitRow(pinned)
	pinned:SetPoint("BOTTOMLEFT", 4, 4)
	pinned:SetPoint("BOTTOMRIGHT", -24, 4)
	pinned:Hide()
	frame.pinned = pinned

	frame.pinnedSpacer = inset:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
	frame.pinnedSpacer:SetPoint("BOTTOM", pinned, "TOP", 0, 2)
	frame.pinnedSpacer:SetText("...")
	frame.pinnedSpacer:Hide()

	frame.empty = inset:CreateFontString(nil, "ARTWORK", "GameFontDisable")
	frame.empty:SetPoint("CENTER", 0, 0)
	frame.empty:SetText(L["No one has reported yet."])
	frame.empty:Hide()

	local share = CreateFrame("CheckButton", nil, frame, "UICheckButtonTemplate") --[[@as CheckButton]]
	share:SetPoint("BOTTOMLEFT", 16, 34)
	---@param self CheckButton
	share:SetScript("OnClick", function(self)
		if frame.shareSetter then
			frame.shareSetter(self:GetChecked() == true)
		end
		Refresh()
	end)
	frame.share = share

	frame.shareLabel = frame:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
	frame.shareLabel:SetPoint("LEFT", share, "RIGHT", 2, 0)
	frame.shareLabel:SetText(L["Share my progress"])

	frame.note = frame:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
	frame.note:SetPoint("BOTTOMLEFT", 18, 14)
	frame.note:SetText(L["Others' values are player-reported."])

	frame.tabs = {}
	BuildTabs(frame)
	api.window = frame
	frame:SetScript("OnShow", function()
		Refresh()
	end)
	return frame
end

---@param key? string
---@return boolean opened
function api:Open(key)
	local newer = Newer()
	if newer then
		return newer:Open(key)
	end
	local frame = Window()
	if type(key) == "string" and key ~= "" then
		local found = key == OVERALL and OVERALL or self.boards[key]
		if found then
			self.selected = key
		end
	end
	self.selected = self.selected or OVERALL
	Refresh()
	frame:Show()
	return true
end

---@param key string
function api:Select(key)
	local newer = Newer()
	if newer then
		return newer:Select(key)
	end
	if key ~= OVERALL and not self.boards[key] then
		key = OVERALL
	end
	self.selected = key
	Refresh()
end

function api:Toggle()
	local newer = Newer()
	if newer then
		return newer:Toggle()
	end
	if self.window and self.window:IsShown() then
		self.window:Hide()
	else
		self:Open()
	end
end

---@return boolean shown
function api:IsShown()
	local newer = Newer()
	if newer then
		return newer:IsShown()
	end
	return self.window ~= nil and self.window:IsShown() == true
end

--------------------------------------------------------------------------------------------------------------------
-- Roster classes

-- The client's roster is the only way a stored name gets a class: the group and guild parts live in
-- Core/LeaderboardsData.lua, built on first need. A roster change rebuilds its part and repaints an open window; while
-- the window is closed it only marks the part stale, so no event reads the roster for a window nobody is looking at.
local rosterEvents = CreateFrame("Frame")
rosterEvents:RegisterEvent("GUILD_ROSTER_UPDATE")
rosterEvents:RegisterEvent("GROUP_ROSTER_UPDATE")
rosterEvents:SetScript("OnEvent", function(_, event)
	local newer = Newer()
	if newer then
		return
	end
	local part = event == "GUILD_ROSTER_UPDATE" and "guild" or "group"
	if api:IsShown() then
		data.RefreshClasses(part)
		Refresh()
	else
		data.InvalidateClasses(part)
	end
end)

--------------------------------------------------------------------------------------------------------------------
-- Tooltip

-- The tooltip's two lines live in Core/LeaderboardsData.lua beside the standing they read; this wrapper keeps one
-- hook and hands a newer copy the call.
---@param tooltip GameTooltip
function api:AddTooltip(tooltip)
	local current = ForeverLeaderboards
	if current ~= self and type(current) == "table" and type(current.AddTooltip) == "function" then
		return current:AddTooltip(tooltip)
	end
	return data.AddTooltip(self, tooltip)
end

-- One hook, installed by the copy that publishes the global. The modern client delivers unit tooltips through
-- TooltipDataProcessor; the widget script remains the fallback. A newer copy takes the hook's flag and the handler
-- follows the published global, so an addon updated first never runs two tooltip hooks.
---@param tooltip GameTooltip
local function TooltipHandler(tooltip)
	local current = ForeverLeaderboards
	if type(current) == "table" and type(current.AddTooltip) == "function" then
		current:AddTooltip(tooltip)
	end
end

if not api.tooltipHooked then
	local processor = rawget(_G, "TooltipDataProcessor")
	local unitType = Enum and Enum.TooltipDataType and Enum.TooltipDataType.Unit
	local hooked = false
	if processor and unitType and type(processor.AddTooltipPostCall) == "function" then
		hooked = pcall(processor.AddTooltipPostCall, processor, unitType, TooltipHandler)
	end
	if not hooked and GameTooltip and type(GameTooltip.HookScript) == "function" then
		hooked = pcall(GameTooltip.HookScript, GameTooltip, "OnTooltipSetUnit", TooltipHandler)
	end
	api.tooltipHooked = hooked or api.tooltipHooked
end

--------------------------------------------------------------------------------------------------------------------
-- Slash commands

-- A consumer that already owns /forever keeps it; /flb always opens this window. Neither prints anything.
local foreverTaken = false
for index = 1, 9 do
	if rawget(_G, "SLASH_FOREVER" .. index) ~= nil then
		foreverTaken = true
		break
	end
end
SLASH_FOREVERLEADERBOARDS1 = not foreverTaken and "/forever" or nil
SLASH_FOREVERLEADERBOARDS2 = "/flb"
SlashCmdList["FOREVERLEADERBOARDS"] = function(message)
	local key = type(message) == "string" and message:match("^%s*(.-)%s*$") or ""
	if key == "" then
		api:Toggle()
	else
		api:Open(key)
	end
end
