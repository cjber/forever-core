---@type string, ForeverLeaderboardsNamespace
local _, ns = ...

-- One Forever Leaderboards window for every Forever addon. This file loads once, in ForeverCore: each addon registers
-- its own board with ns.Leaderboards:Register, and this file draws them. Nothing here is protected, hooks Blizzard
-- frames beyond one unit-tooltip hook, or writes to chat: a board is a callback, a row is a table, and the window is
-- made of the client's own templates.
--
-- Core/LeaderboardsData.lua, loaded first, owns overall points, a player's standing, the per-scope cache and the
-- tooltip text; this file owns the window and the registration.

---@class ForeverLeaderboardsNamespace
---@field Leaderboards? ForeverLeaderboardsAPI
---@field LeaderboardsData? ForeverLeaderboardsData
---@field PeerStats? ForeverPeerStatsNamespace
---@field DebugCommand? fun(argument?: string): boolean
---@field SafeCall? ForeverSafeCall
---@field L? table<string, string>

---@alias ForeverLeaderboardsScope "week"|"all"

---@alias ForeverLeaderboardsReach "group"|"met"

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
---@field safeCall? fun(label: string, fn: function, ...: any): boolean, any the addon's SafeCall for its own callbacks

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

local OVERALL = "overall"
local TROPHY = "Interface\\Icons\\INV_Misc_Trophy_Argent"
local ROW_HEIGHT = 30
local VISIBLE_ROWS = 10
local MIN_VISIBLE_ROWS = 3
local HEADER_HEIGHT = 112
local LIST_HEADER_HEIGHT = 26
local LIST_PADDING = 8
local PINNED_HEIGHT = ROW_HEIGHT + 14
local FOOTER_HEIGHT = 70
local PINNED_BOTTOM = 8
local WINDOW_WIDTH = 460
local WINDOW_HEIGHT = HEADER_HEIGHT + LIST_HEADER_HEIGHT + MIN_VISIBLE_ROWS * ROW_HEIGHT + LIST_PADDING + FOOTER_HEIGHT
local FRAME_NAME = "ForeverLeaderboardsFrame"
local DROPDOWN_TEMPLATE = "WowStyle1DropdownTemplate"
local DROPDOWN_PADDING = 56
local DROPDOWN_MINIMUM = 120
local BAR_LEFT = 70
local BAR_RIGHT = 140

local data = ns.LeaderboardsData
if type(data) ~= "table" or type(data.Overall) ~= "function" then
	return
end
local MEDALS = data.MEDALS

---@class ForeverLeaderboardsAPI
---@field scope ForeverLeaderboardsScope the selected scope
---@field reach ForeverLeaderboardsReach rows heard directly ("group") or every row heard ("met")
---@field selected? string the board the window shows
---@field window? ForeverLeaderboardsWindow the window once built
---@field tooltipHooked? boolean the one unit-tooltip hook is already installed
---@field ClassOf fun(name: string): string? the client's class token for a player name, when it knows one
---@field registration integer raised with every successful Register, so the data cache notices the board list
local api = {
	boards = {},
	order = {},
	scope = "week",
	reach = "met",
	registration = 0,
}
local sequence = 0
local BuildTabs, Refresh

ns.Leaderboards = api

local function Strings()
	return data.Strings()
end

-- The widest reach is the one a player sees first; a saved choice is kept in ForeverCoreDB and restored when the
-- window is first built, after the saved variables have arrived.
local DEFAULT_REACH = "met"
local reachRestored = false

---@return ForeverLeaderboardsReach
local function SavedReach()
	local saved = type(ForeverCoreDB) == "table"
		and type(ForeverCoreDB.leaderboards) == "table"
		and ForeverCoreDB.leaderboards.reach
	return saved == "group" and "group" or DEFAULT_REACH
end

---@param reach ForeverLeaderboardsReach
local function SaveReach(reach)
	if type(ForeverCoreDB) ~= "table" then
		return
	end
	local saved = ForeverCoreDB.leaderboards
	if type(saved) ~= "table" then
		saved = {}
		ForeverCoreDB.leaderboards = saved
	end
	saved.reach = reach
end

-- A board's callback runs in the registering addon's SafeCall, so its failure lands in that addon's journal.
local function RunSafe(spec, label, fn, ...)
	local safe = spec and spec.safeCall
	if safe then
		return safe(label, fn, ...)
	end
	if ns.SafeCall then
		return ns.SafeCall(label, fn, ...)
	end
	return pcall(fn, ...)
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
		safeCall = type(spec.safeCall) == "function" and spec.safeCall or nil,
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
	return data.Overall(self, scope or self.scope)
end

---@param name string
---@param scope? ForeverLeaderboardsScope
---@return ForeverLeaderboardsStanding
function api:Standing(name, scope)
	return data.Standing(self, name, scope or self.scope)
end

-- The client's own class for a player name, so a board does not need a ClassOf helper of its own. A name the client has
-- not heard of returns nil, and the row draws without an icon in the neutral colour.
---@param name string
---@return string?
function api.ClassOf(name)
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
	local list = data.BoardRows(api, spec, scope)
	if type(list) ~= "table" then
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
---@field stripe Texture
---@field bar Texture
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
---@field OpenMenu fun(self: ForeverLeaderboardsDropdown)
---@field IsEnabled fun(self: ForeverLeaderboardsDropdown): boolean

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
---@field totalHeader FontString
---@field periodHeader FontString
---@field measure FontString
---@field inset Frame
---@field periodDropdown ForeverLeaderboardsDropdown
---@field reachDropdown ForeverLeaderboardsDropdown
---@field scroll ForeverLeaderboardsScrollBox
---@field scrollBar Frame
---@field topValue number
---@field pinned ForeverLeaderboardsRowButton
---@field pinnedSeparator Texture
---@field share CheckButton
---@field shareSetter? fun(shared: boolean)
---@field shareLabel FontString
---@field note FontString
---@field emptyFrame Frame
---@field emptyIcon Texture
---@field empty FontString
---@field emptyBody FontString
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

	-- The alternate row stripe, drawn under the row's text and above the inset's own background.
	button.stripe = button:CreateTexture(nil, "BACKGROUND")
	button.stripe:SetAllPoints()
	button.stripe:SetColorTexture(1, 1, 1, 0.035)
	button.stripe:Hide()

	button.rankMedal = button:CreateTexture(nil, "ARTWORK")
	button.rankMedal:SetSize(24, 24)
	button.rankMedal:SetPoint("LEFT", 10, 0)

	button.rankText = button:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
	button.rankText:SetPoint("LEFT", 10, 0)
	button.rankText:SetWidth(24)
	button.rankText:SetJustifyH("CENTER")

	button.classIcon = button:CreateTexture(nil, "ARTWORK")
	button.classIcon:SetSize(22, 22)
	button.classIcon:SetPoint("LEFT", 42, 0)

	button.bar = button:CreateTexture(nil, "ARTWORK")
	button.bar:SetHeight(2)
	button.bar:SetPoint("BOTTOMLEFT", BAR_LEFT, 4)
	button.bar:SetColorTexture(0.91, 0.74, 0.39, 0.55)
	button.bar:Hide()

	button.nameText = button:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
	button.nameText:SetPoint("LEFT", BAR_LEFT, 0)
	button.nameText:SetJustifyH("LEFT")

	button.value = button:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
	button.value:SetPoint("RIGHT", -10, 0)
	button.value:SetWidth(60)
	button.value:SetJustifyH("RIGHT")

	button.extra = button:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
	button.extra:SetPoint("RIGHT", button.value, "LEFT", 0, 0)
	button.extra:SetWidth(90)
	button.extra:SetJustifyH("RIGHT")
	button.nameText:SetPoint("RIGHT", button.extra, "LEFT", -10, 0)
end

-- The leader bar runs from the name's left edge up to the Total column, so its full width is what the widest bar may
-- be. A bare Button has no width until the scroll view sizes it; the fallback keeps a fresh row sane.
---@param button ForeverLeaderboardsRowButton
---@return number
local function BarWidth(button)
	local width = button:GetWidth()
	if not width or width <= 0 then
		-- The inset's width less the scroll box's left inset and the scroll bar's column.
		width = WINDOW_WIDTH - 28 - 28
	end
	return math.max(0, width - BAR_LEFT - BAR_RIGHT)
end

---@param button ForeverLeaderboardsRowButton
---@param row ForeverLeaderboardsDisplayRow
---@param top number the first row's value, which a bar is a fraction of
local function RenderRow(button, row, top)
	local L = Strings()
	button.highlight:SetShown(row.you)
	button.stripe:SetShown(not row.you and row.rank % 2 == 0)
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
	-- An unknown class keeps the icon's space: the name is anchored independently, so it never shifts.
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
	local value = tonumber(row.value) or 0
	if row.weekly then
		button.value:SetText("+" .. value)
		button.value:SetTextColor(GREEN_FONT_COLOR:GetRGB())
	else
		button.value:SetText(tostring(value))
		button.value:SetTextColor(HIGHLIGHT_FONT_COLOR:GetRGB())
	end
	if top > 0 and value > 0 then
		button.bar:SetWidth(BarWidth(button) * math.min(1, value / top))
		button.bar:Show()
	else
		button.bar:Hide()
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
		-- A Button, so the gamepad's SmartNavigation scan never reads this frame's mouse scripts (cjber/skillup-forever#398).
		local tab = CreateFrame("Button", nil, frame, "LargeSideTabButtonTemplate") --[[@as ForeverLeaderboardsTab]]
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

-- The window grows with the board, so its top-left corner stays put while the height changes.
---@param frame ForeverLeaderboardsWindow
---@param height number
local function FitHeight(frame, height)
	if frame:GetHeight() == height then
		return
	end
	local left, top = frame:GetLeft(), frame:GetTop()
	frame:SetHeight(height)
	if left and top then
		local parentLeft = UIParent:GetLeft() or 0
		local parentTop = UIParent:GetTop() or 0
		frame:ClearAllPoints()
		frame:SetPoint("TOPLEFT", UIParent, "TOPLEFT", left - parentLeft, top - parentTop)
	end
end

-- The subtitle says where the rows come from and, when there are any, how many.
---@param count integer
---@return string
local function ReachLine(count)
	local L = Strings()
	local met = api.reach == "met"
	if count == 0 then
		return met and L["Players you've met"] or L["Your guild and group"]
	end
	local phrase
	if met then
		phrase = count == 1 and L["%d player you've met"] or L["%d players you've met"]
	else
		phrase = count == 1 and L["%d player from your guild and group"] or L["%d players from your guild and group"]
	end
	return string.format(phrase, count)
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
	frame.periodHeader:SetText(api.scope == "week" and L["This week"] or L["All time"])
	frame.periodDropdown:SetDefaultText(api.scope == "week" and L["This week"] or L["All time"])
	frame.reachDropdown:SetDefaultText(api.reach == "met" and L["Players you've met"] or L["Guild and group"])
	RefreshTabs(frame)

	local rows = Rows(key, api.scope)
	frame.subtitle:SetText(ReachLine(#rows))
	local ownIndex
	for index, row in ipairs(rows) do
		if row.you then
			ownIndex = index
			break
		end
	end
	local pinned = ownIndex ~= nil and ownIndex > VISIBLE_ROWS
	local visible = math.min(#rows, VISIBLE_ROWS)
	local listHeight = LIST_HEADER_HEIGHT
		+ math.max(visible, MIN_VISIBLE_ROWS) * ROW_HEIGHT
		+ (pinned and PINNED_HEIGHT or 0)
		+ LIST_PADDING
	FitHeight(frame, HEADER_HEIGHT + listHeight + FOOTER_HEIGHT)

	frame.pinned:SetShown(pinned)
	frame.pinnedSeparator:SetShown(pinned)
	local bottom = pinned and (PINNED_HEIGHT + LIST_PADDING) or LIST_PADDING
	local right = #rows > VISIBLE_ROWS and -24 or -4
	frame.scroll:ClearAllPoints()
	frame.scroll:SetPoint("TOPLEFT", frame.inset, "TOPLEFT", 4, -LIST_HEADER_HEIGHT)
	frame.scroll:SetPoint("BOTTOMRIGHT", frame.inset, "BOTTOMRIGHT", right, bottom)
	local top = rows[1] and tonumber(rows[1].value) or 0
	frame.topValue = top
	if pinned then
		RenderRow(frame.pinned, rows[ownIndex], top)
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
	local empty = #rows == 0
	frame.empty:SetShown(empty)
	frame.emptyBody:SetShown(empty)
	frame.emptyIcon:SetShown(empty)
	frame.emptyBody:SetText(
		api.reach == "met" and L["Players you've met who use a Forever addon show up here."]
			or L["Guild and group members who use a Forever addon show up here."]
	)
	frame.scroll:SetDataProvider(
		CreateDataProvider(list),
		ScrollBoxConstants and ScrollBoxConstants.RetainScrollPosition
	)
	frame.scrollBar:SetShown(#rows > VISIBLE_ROWS)

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
					local ok, shared = RunSafe(board, "leaderboard sharing", board.sharing)
					if ok and shared == false then
						return false
					end
				end
				return true
			end
			setSharing = function(value)
				for _, board in ipairs(shareable) do
					RunSafe(board, "leaderboard sharing", board.setSharing, value)
				end
			end
		end
	end
	frame.shareSetter = setSharing
	frame.share:SetShown(sharing ~= nil and setSharing ~= nil)
	frame.shareLabel:SetShown(sharing ~= nil and setSharing ~= nil)
	if sharing then
		-- Sharing is opt-out: only an explicit false unchecks it, so a missing saved setting reads as on.
		local ok, shared = RunSafe(spec, "leaderboard sharing", sharing)
		frame.share:SetChecked(not ok or shared ~= false)
	end
	frame.note:SetText(
		key == OVERALL and L["Points for placing on each addon's board."] or L["Others' values are player-reported."]
	)
end

-- Each dropdown's choices, in the order a press steps through them.
local PERIOD_CHOICES = { "week", "all" }
local REACH_CHOICES = { "group", "met" }

-- The client's gamepad switch. Read through _G because not every consumer's pinned WoW API annotations declare
-- InputUtil, and this file has to typecheck unchanged in each of them.
---@return boolean
local function GamepadUI()
	local input = rawget(_G, "InputUtil")
	return type(input) == "table"
		and type(input.IsGamepadUIEnabled) == "function"
		and input.IsGamepadUIEnabled() == true
end

-- With the gamepad interface on, the client's gamepad frame manager takes every menu that shows into its focus in the
-- same call, under the taint of whoever opened it, and the next secure window call then has its protected
-- SetPreferredGamepadInteractTarget refused. No addon code can open a Blizzard menu untainted, so a press steps to
-- the dropdown's next choice instead (cjber/forever-core#267, cjber/skillup-forever#398).
---@param dropdown ForeverLeaderboardsDropdown
---@param choices string[]
---@param current fun(): string
---@param choose fun(choice: string)
local function HookGamepad(dropdown, choices, current, choose)
	local openMenu = dropdown.OpenMenu
	function dropdown:OpenMenu()
		if not GamepadUI() then
			return openMenu(self)
		end
		if not self:IsEnabled() then
			return
		end
		local index = 1
		for position, choice in ipairs(choices) do
			if choice == current() then
				index = position % #choices + 1
				break
			end
		end
		choose(choices[index])
		Refresh()
	end
end

---@param parent Frame
---@return ForeverLeaderboardsDropdown
local function NewDropdown(parent)
	return CreateFrame("DropdownButton", nil, parent, DROPDOWN_TEMPLATE) --[[@as ForeverLeaderboardsDropdown]]
end

---@return ForeverLeaderboardsWindow
local function Window()
	if api.window then
		return api.window
	end
	if not reachRestored then
		api.reach = SavedReach()
		reachRestored = true
	end
	local L = Strings()
	local name = FRAME_NAME
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
	frame:SetScript("OnDragStart", function(self)
		self:StartMoving()
	end)
	frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
	frame:SetTitle(L["Forever Leaderboards"])
	frame:GetPortrait():SetTexture(TROPHY)

	frame.heading = frame:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
	frame.heading:SetPoint("TOPLEFT", 62, -34)
	frame.heading:SetTextColor(NORMAL_FONT_COLOR:GetRGB())

	frame.subtitle = frame:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
	frame.subtitle:SetPoint("TOPLEFT", 62, -54)
	frame.subtitle:SetText(api.reach == "met" and L["Players you've met"] or L["Your guild and group"])

	-- A scratch line measures each dropdown's longest option in the client's font, so a translated option is never
	-- cut short however long it is.
	frame.measure = frame:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
	frame.measure:Hide()

	local periodDropdown = NewDropdown(frame)
	periodDropdown:SetHeight(24)
	periodDropdown:SetPoint("TOPLEFT", 48, -80)
	periodDropdown:SetupMenu(function(_, root)
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
	HookGamepad(periodDropdown, PERIOD_CHOICES, function()
		return api.scope
	end, function(choice)
		api.scope = choice
	end)
	periodDropdown:SetDefaultText(L["This week"])
	frame.periodDropdown = periodDropdown

	local reachDropdown = NewDropdown(frame)
	reachDropdown:SetHeight(24)
	reachDropdown:SetPoint("LEFT", periodDropdown, "RIGHT", 8, 0)
	reachDropdown:SetupMenu(function(_, root)
		root:SetScrollMode(300)
		root:CreateRadio(L["Guild and group"], function()
			return api.reach == "group"
		end, function()
			api.reach = "group"
			SaveReach(api.reach)
			Refresh()
		end)
		root:CreateRadio(L["Players you've met"], function()
			return api.reach == "met"
		end, function()
			api.reach = "met"
			SaveReach(api.reach)
			Refresh()
		end)
	end)
	HookGamepad(reachDropdown, REACH_CHOICES, function()
		return api.reach
	end, function(choice)
		api.reach = choice
		SaveReach(choice)
	end)
	reachDropdown:SetDefaultText(api.reach == "met" and L["Players you've met"] or L["Guild and group"])
	frame.reachDropdown = reachDropdown

	local function FitDropdown(dropdown, labels)
		local longest = 0
		for _, text in ipairs(labels) do
			frame.measure:SetText(text)
			local width = frame.measure:GetStringWidth()
			if not width or width <= 0 then
				width = #text * 7
			end
			longest = math.max(longest, width)
		end
		dropdown:SetWidth(math.max(DROPDOWN_MINIMUM, math.ceil(longest) + DROPDOWN_PADDING))
	end
	FitDropdown(periodDropdown, { L["This week"], L["All time"] })
	FitDropdown(reachDropdown, { L["Guild and group"], L["Players you've met"] })

	local inset = CreateFrame("Frame", nil, frame, "InsetFrameTemplate")
	inset:SetPoint("TOPLEFT", 14, -HEADER_HEIGHT)
	inset:SetPoint("BOTTOMRIGHT", -14, FOOTER_HEIGHT)
	frame.inset = inset --[[@as Frame]]

	local divider = inset:CreateTexture(nil, "ARTWORK")
	divider:SetAtlas("_UI-Frame-InnerTopTile")
	divider:SetPoint("TOPLEFT", 4, -24)
	divider:SetPoint("RIGHT", -4, 0)
	divider:SetHeight(3)

	local scroll = CreateFrame("Frame", nil, inset, "WowScrollBoxList") --[[@as ForeverLeaderboardsScrollBox]]
	scroll:SetPoint("TOPLEFT", 4, -LIST_HEADER_HEIGHT)
	scroll:SetPoint("BOTTOMRIGHT", -4, LIST_PADDING)
	local scrollBar = CreateFrame("EventFrame", nil, inset, "MinimalScrollBar") --[[@as Frame]]
	scrollBar:SetPoint("TOPLEFT", scroll, "TOPRIGHT", 4, 0)
	scrollBar:SetPoint("BOTTOMLEFT", scroll, "BOTTOMRIGHT", 4, 0)
	local view = CreateScrollBoxListLinearView()
	-- A bare Button has no XML template for the view to read a height from, so the row height is set here.
	view:SetElementExtent(ROW_HEIGHT)
	view:SetElementInitializer("Button", function(button, entry)
		local rowButton = button --[[@as ForeverLeaderboardsRowButton]]
		InitRow(rowButton)
		RenderRow(rowButton, entry, frame.topValue or 0)
	end)
	ScrollUtil.InitScrollBoxListWithScrollBar(scroll, scrollBar, view)
	frame.scroll = scroll
	frame.scrollBar = scrollBar

	local rankHeader = inset:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
	rankHeader:SetPoint("TOPLEFT", 12, -8)
	rankHeader:SetTextColor(NORMAL_FONT_COLOR:GetRGB())
	rankHeader:SetText(L["Rank"])
	local playerHeader = inset:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
	playerHeader:SetPoint("TOPLEFT", 74, -8)
	playerHeader:SetTextColor(NORMAL_FONT_COLOR:GetRGB())
	playerHeader:SetText(L["Player"])
	frame.totalHeader = inset:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
	frame.totalHeader:SetPoint("TOPRIGHT", -74, -8)
	frame.totalHeader:SetWidth(80)
	frame.totalHeader:SetJustifyH("RIGHT")
	frame.totalHeader:SetTextColor(NORMAL_FONT_COLOR:GetRGB())
	frame.totalHeader:SetText(L["Total"])
	frame.periodHeader = inset:CreateFontString(nil, "ARTWORK", "GameFontNormalSmall")
	frame.periodHeader:SetPoint("TOPRIGHT", -14, -8)
	frame.periodHeader:SetWidth(80)
	frame.periodHeader:SetJustifyH("RIGHT")
	frame.periodHeader:SetTextColor(NORMAL_FONT_COLOR:GetRGB())

	local pinned = CreateFrame("Button", nil, inset) --[[@as ForeverLeaderboardsRowButton]]
	InitRow(pinned)
	pinned:SetPoint("BOTTOMLEFT", 4, PINNED_BOTTOM)
	pinned:SetPoint("BOTTOMRIGHT", -24, PINNED_BOTTOM)
	pinned:Hide()
	frame.pinned = pinned

	frame.pinnedSeparator = inset:CreateTexture(nil, "ARTWORK")
	frame.pinnedSeparator:SetColorTexture(0.91, 0.74, 0.39, 0.35)
	frame.pinnedSeparator:SetPoint("BOTTOMLEFT", pinned, "TOPLEFT", 8, 7)
	frame.pinnedSeparator:SetPoint("BOTTOMRIGHT", pinned, "TOPRIGHT", -8, 7)
	frame.pinnedSeparator:SetHeight(1)
	frame.pinnedSeparator:Hide()

	frame.emptyFrame = CreateFrame("Frame", nil, inset)
	frame.emptyFrame:SetPoint("TOPLEFT", inset, "TOPLEFT", 0, -LIST_HEADER_HEIGHT)
	frame.emptyFrame:SetPoint("BOTTOMRIGHT", inset, "BOTTOMRIGHT", 0, 0)

	frame.emptyIcon = inset:CreateTexture(nil, "ARTWORK")
	frame.emptyIcon:SetSize(40, 40)
	frame.emptyIcon:SetPoint("CENTER", frame.emptyFrame, "CENTER", 0, 32)
	frame.emptyIcon:SetAlpha(0.55)
	frame.emptyIcon:SetTexture(TROPHY)
	frame.emptyIcon:Hide()

	frame.empty = inset:CreateFontString(nil, "ARTWORK", "GameFontNormal")
	frame.empty:SetPoint("TOP", frame.emptyFrame, "CENTER", 0, 2)
	frame.empty:SetTextColor(NORMAL_FONT_COLOR:GetRGB())
	frame.empty:SetText(L["No one has shared yet"])
	frame.empty:Hide()

	frame.emptyBody = inset:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
	frame.emptyBody:SetPoint("TOP", frame.emptyFrame, "CENTER", 0, -20)
	frame.emptyBody:SetWidth(WINDOW_WIDTH - 28 - 80)
	frame.emptyBody:SetJustifyH("CENTER")
	frame.emptyBody:SetTextColor(GRAY_FONT_COLOR:GetRGB())
	frame.emptyBody:Hide()

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
	if key ~= OVERALL and not self.boards[key] then
		key = OVERALL
	end
	self.selected = key
	Refresh()
end

function api:Toggle()
	if self.window and self.window:IsShown() then
		self.window:Hide()
	else
		self:Open()
	end
end

---@return boolean shown
function api:IsShown()
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

-- The tooltip's two lines live in Core/LeaderboardsData.lua beside the standing they read; this wrapper keeps the
-- one hook's call.
---@param tooltip GameTooltip
function api:AddTooltip(tooltip)
	return data.AddTooltip(self, tooltip)
end

-- One hook, installed when this file loads. The modern client delivers unit tooltips through TooltipDataProcessor;
-- the widget script remains the fallback.
---@param tooltip GameTooltip
local function TooltipHandler(tooltip)
	api:AddTooltip(tooltip)
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

-- A consumer that already owns /forever keeps it; /flb always opens this window. `debug` is the shared log's
-- subcommand, routed here so every copy of this file answers it; the log shows its answer on screen, never in chat.
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
	local command, rest = key:match("^(%S+)%s*(.-)$")
	if command == "debug" then
		if type(ns.DebugCommand) == "function" then
			ns.DebugCommand(rest)
		end
		return
	end
	if key == "" then
		api:Toggle()
	else
		api:Open(key)
	end
end
