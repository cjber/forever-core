-- Contract for the shared Forever Leaderboards window (UI/Leaderboards.lua), against a mocked client.
local PATH = "UI/Leaderboards.lua"
local DATA_PATH = "Core/LeaderboardsData.lua"

local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end

local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

-- Client mock ----------------------------------------------------------------------------------------------------
local frames, named = {}, {}
local unitNames, unitClasses, guildMembers = {}, {}, {}
local guildCalls = 0
local Create
local function noop() end

local Widget = {}
Widget.__index = function(_, key)
	return Widget[key] or noop
end

function Widget:SetScript(event, handler)
	self.scripts[event] = handler
end

function Widget:GetScript(event)
	return self.scripts[event]
end

function Widget:HookScript(event, handler)
	self.hooks[event] = self.hooks[event] or {}
	self.hooks[event][#self.hooks[event] + 1] = handler
end

function Widget:Show()
	self.shown = true
	if self.scripts.OnShow then
		self.scripts.OnShow(self)
	end
end

function Widget:Hide()
	self.shown = false
end

function Widget:IsShown()
	return self.shown ~= false
end

function Widget:SetShown(shown)
	if shown then
		self:Show()
	else
		self:Hide()
	end
end

function Widget:SetText(text)
	self.text = text
end

function Widget:GetText()
	return self.text
end

function Widget:SetTextColor(r, g, b)
	self.textColor = { r, g, b }
end

function Widget:SetChecked(checked)
	self.checked = checked and true or false
end

function Widget:GetChecked()
	return self.checked == true
end

function Widget:SetEnabled(enabled)
	self.enabled = enabled
end

function Widget:SetWidth(width)
	self.width = width
end

function Widget:GetWidth()
	return self.width or 0
end

function Widget:SetHeight(height)
	self.height = height
end

function Widget:GetHeight()
	return self.height or 0
end

function Widget:SetSize(width, height)
	self.width, self.height = width, height
end

function Widget:SetPoint(point)
	self.points[point] = true
end

function Widget:GetParent()
	return self.parent
end

function Widget:SetAtlas(atlas)
	self.atlas = atlas
end

function Widget:SetTexture(texture)
	self.texture = texture
end

function Widget:SetAllPoints()
	self.allPoints = true
end

function Widget:SetTitle(title)
	self.title = title
end

function Widget:GetPortrait()
	return self.portrait
end

function Widget:SetDefaultText(text)
	self.defaultText = text
end

function Widget:SetupMenu(generator)
	self.menu = generator
end

function Widget:SetCustomOnMouseUpHandler(handler)
	self.mouseUp = handler
end

function Widget:SetDataProvider(provider)
	self.provider = provider
	self.buttons = {}
	local view = rawget(self, "view")
	if view and view.initializer then
		for _, entry in ipairs(provider and provider.entries or {}) do
			local button = Create("Button", self)
			self.buttons[#self.buttons + 1] = button
			view.initializer(button, entry)
		end
	end
end

function Widget:GetUnit()
	return self.unitName, self.unit
end

function Widget:AddLine(text, r, g, b)
	local lines = rawget(self, "lines")
	if not lines then
		lines = {}
		self.lines = lines
	end
	lines[#lines + 1] = { text = text, r = r, g = g, b = b }
end

function Widget:Click()
	if self.scripts.OnClick then
		self.scripts.OnClick(self)
	end
end

function Widget:ClickTab()
	if self.mouseUp then
		self.mouseUp(self, "LeftButton", true)
	end
end

function Widget:CreateFontString()
	return Create("FontString", self)
end

function Widget:CreateTexture()
	return Create("Texture", self)
end

function Create(kind, parent, template)
	local widget = setmetatable({
		kind = kind,
		parent = parent,
		template = template,
		scripts = {},
		hooks = {},
		children = {},
		points = {},
		shown = true,
	}, Widget)
	if parent then
		parent.children[#parent.children + 1] = widget
	end
	if template == "PortraitFrameTemplate" then
		widget.portrait = Create("Texture", widget)
	end
	if template == "LargeSideTabButtonTemplate" then
		widget.Icon = Create("Texture", widget)
	end
	if kind == "CheckButton" then
		widget.checked = false
	end
	frames[#frames + 1] = widget
	return widget
end

local env
local serverTime, weekRemaining = 1700000000, 100000
local function Client()
	frames, named, unitNames = {}, {}, { player = { "Me" } }
	unitClasses, guildMembers, guildCalls = { player = "HUNTER" }, {}, 0
	serverTime, weekRemaining = 1700000000, 100000
	env = setmetatable({
		UIParent = Create("Frame"),
		UISpecialFrames = {},
		tContains = function(list, item)
			for _, value in ipairs(list) do
				if value == item then
					return true
				end
			end
			return false
		end,
		CreateFrame = function(kind, name, parent, template)
			local widget = Create(kind, parent, template)
			if name then
				named[name] = widget
			end
			return widget
		end,
		UnitName = function(unit)
			local found = unitNames[unit]
			if found then
				return found[1], found[2]
			end
			return "Me"
		end,
		UnitClass = function(unit)
			local class = unitClasses[unit]
			if class then
				return class, class
			end
		end,
		IsInRaid = function()
			return false
		end,
		Ambiguate = function(name, context)
			if type(name) ~= "string" then
				return name
			end
			if context == "short" then
				return name:match("^([^%-]+)") or name
			end
			return name
		end,
		GetNumGuildMembers = function()
			return #guildMembers
		end,
		GetGuildRosterInfo = function(index)
			guildCalls = guildCalls + 1
			local member = guildMembers[index]
			if not member then
				return nil
			end
			-- name, rank, rankIndex, level, class, zone, note, officerNote, online, status, classFileName
			return member.name, nil, nil, nil, nil, nil, nil, nil, nil, nil, member.class
		end,
		GetNormalizedRealmName = function()
			return "MyRealm"
		end,
		GetServerTime = function()
			return serverTime
		end,
		C_DateAndTime = {
			GetSecondsUntilWeeklyReset = function()
				return weekRemaining
			end,
		},
		CreateDataProvider = function(entries)
			return { entries = entries }
		end,
		CreateScrollBoxListLinearView = function()
			return {
				SetElementInitializer = function(self, _, initializer)
					self.initializer = initializer
				end,
				SetPadding = noop,
			}
		end,
		ScrollUtil = {
			InitScrollBoxListWithScrollBar = function(box, _, view)
				box.view = view
			end,
		},
		ScrollBoxConstants = { RetainScrollPosition = 1 },
		SlashCmdList = {},
		RAID_CLASS_COLORS = {
			HUNTER = {
				GetRGB = function()
					return 0.67, 0.83, 0.45
				end,
			},
			MAGE = {
				GetRGB = function()
					return 0.25, 0.78, 0.92
				end,
			},
			PRIEST = {
				GetRGB = function()
					return 1, 1, 1
				end,
			},
			ROGUE = {
				GetRGB = function()
					return 1, 0.96, 0.41
				end,
			},
			WARRIOR = {
				GetRGB = function()
					return 0.78, 0.61, 0.43
				end,
			},
		},
		NORMAL_FONT_COLOR = {
			GetRGB = function()
				return 1, 0.82, 0
			end,
		},
		GRAY_FONT_COLOR = {
			GetRGB = function()
				return 0.5, 0.5, 0.5
			end,
		},
		GREEN_FONT_COLOR = {
			GetRGB = function()
				return 0.12, 1, 0
			end,
		},
		HIGHLIGHT_FONT_COLOR = {
			GetRGB = function()
				return 1, 1, 1
			end,
		},
	}, { __index = _G })
	env._G = env
	env.GameTooltip = Create("GameTooltip")
	return env
end

local function PhraseLocale()
	return setmetatable({}, {
		__index = function(_, phrase)
			return phrase
		end,
	})
end

local function Load()
	local ns = { L = PhraseLocale() }
	setfenv(assert(loadfile(DATA_PATH)), env)("Test", ns)
	setfenv(assert(loadfile(PATH)), env)("Test", ns)
	return ns.Leaderboards
end

local function row(name, value, extra, you, class)
	return { name = name, value = value, extra = extra, you = you, class = class }
end

local ICON = "Interface\\Icons\\INV_Misc_Trophy_Argent"
local function spec(key, week, all, extra)
	return {
		title = key,
		metric = "Metric " .. key,
		icon = ICON,
		board = function(scope)
			return scope == "week" and week or all
		end,
		sharing = function()
			return not extra or extra.shared ~= false
		end,
		setSharing = function(value)
			if extra then
				extra.shared = value
			end
		end,
	}
end

-- Registration, the window and its rows --------------------------------------------------------------------------
do
	Client()
	local api = Load()
	check(api ~= nil and api.VERSION == 1, "the first copy publishes a versioned global")
	check(env.ForeverLeaderboards == api, "the global is the same table")
	check(type(api.Register) == "function" and type(api.Open) == "function", "the API is there")
	check(api.window == nil, "loading builds no window")
	check(api:Register("bad key", spec("x", {}, {})) == false, "a key with a space is refused")
	check(api:Register("overall", spec("x", {}, {})) == false, "overall is reserved")
	check(api:Register("guide", { title = "Guide" }) == false, "a spec without a board is refused")
	check(api:Register("guide", { title = "Guide", icon = ICON, board = noop }) == false, "no metric heading")
	check(api:Register("guide", { title = "Guide", metric = "M", icon = ICON }) == false, "no board callback")

	local shared = { shared = true }
	check(
		api:Register(
			"guide",
			spec("guide", {
				row("Abe-OtherRealm", 12, "30 total", false, "MAGE"),
				row("Me", 4, "10 total", true, "HUNTER"),
			}, {
				row("Abe-OtherRealm", 40, "40 total", false, "MAGE"),
				row("Me", 10, "10 total", true, "HUNTER"),
			}, shared)
		),
		"a valid board registers"
	)
	check(api:Register("paths", spec("paths", { row("Abe-OtherRealm", 3, nil, false, "MAGE") }, {})) == true, "second")
	local boards = api:Boards()
	equal(#boards, 2, "two boards")
	equal(boards[1].key, "guide", "registration order")
	equal(boards[2].key, "paths", "registration order")
	check(api:Register("paths", spec("paths", { row("Zed", 1, nil, false, "MAGE") }, {})) == true, "re-register")
	equal(#api:Boards(), 2, "re-registering keeps one board")
	equal(api:Boards()[2].metric, "Metric paths", "the new spec replaces the old one")

	check(api:Open("guide"), "Open builds the window")
	local window = api.window
	check(window ~= nil, "the window exists")
	for _, widget in ipairs(frames) do
		equal(widget:GetScript("OnUpdate"), nil, "no frame runs an OnUpdate")
	end
	equal(named.ForeverLeaderboardsFrame, window, "the window has its name")
	equal(window.title, "Forever Leaderboards", "the title")
	equal(window.portrait.texture, ICON, "the trophy portrait")
	equal(#window.tabs, 3, "Overall plus both boards")
	equal(window.tabs[1].key, "overall", "Overall first")
	equal(window.tabs[1].Icon.texture, ICON, "Overall's trophy")
	equal(window.tabs[2].key, "guide", "board tabs follow")
	equal(window.heading.text, "Metric guide", "the metric is the heading")
	equal(window.subtitle.text, "Your guild and group", "the scope note")
	equal(window.valueHeader.text, "This week", "the default scope")
	equal(window.note.text, "Others' values are player-reported.", "the footer note")
	check(window.share:IsShown(), "an addon board offers sharing")
	check(window.share:GetChecked(), "sharing reads the addon's switch")

	local first = window.scroll.buttons[1]
	equal(first.rankMedal.atlas, "challenges-medal-gold", "first place medal")
	equal(first.classIcon.atlas, "groupfinder-icon-class-mage", "round class icon")
	equal(first.nameText.text, "Abe-OtherRealm", "the player name")
	equal(first.nameText.textColor[1], 0.25, "the name is class-coloured")
	equal(first.extra.text, "30 total", "the grey second value")
	equal(first.value.text, "+12", "weekly values are signed")
	equal(first.value.textColor[1], 0.12, "weekly values are green")
	check(first.highlight:IsShown() == false, "a peer row is not highlighted")
	local own = window.scroll.buttons[2]
	check(own.highlight:IsShown(), "the player's row is highlighted")
	equal(own.nameText.text, "Me (you)", "the player's row says so")
	equal(own.rankMedal.atlas, "challenges-medal-silver", "second place medal")
	equal(own.value.text, "+4", "the player's weekly value")

	window.share:SetChecked(false)
	window.share:Click()
	equal(shared.shared, false, "the checkbox saves the addon's switch")
	equal(window.share:GetChecked(), false, "and reads it back")

	-- The scope dropdown says what it shows and swaps the board's callback.
	local radios = {}
	local root = {
		SetScrollMode = noop,
		CreateRadio = function(_, text, _, onClick)
			radios[#radios + 1] = { text = text, onClick = onClick }
		end,
	}
	window.dropdown.menu(window.dropdown, root)
	equal(#radios, 2, "two scopes")
	radios[2].onClick()
	equal(window.valueHeader.text, "All time", "the dropdown changes scope")
	equal(window.scroll.buttons[1].value.text, "40", "all-time values are not signed")
	equal(window.scroll.buttons[1].value.textColor[1], 1, "and not green")
	radios[1].onClick()
	equal(window.valueHeader.text, "This week", "back to the week")

	-- Overall: points, its own heading and note, and no addon sharing switch.
	api:Open("overall")
	equal(api.window.heading.text, "Forever standing", "the overall heading")
	equal(api.window.note.text, "Points for placing on each addon's board.", "the overall note")
	check(api.window.share:IsShown(), "Overall offers the combined switch")
	check(api.window.share:GetChecked() == false, "off while one board is off")
	api.window.share:SetChecked(true)
	api.window.share:Click()
	check(shared.shared, "the combined switch turns every board on")
	check(api.window.share:GetChecked(), "and reads back on")
	check(api.window.tabs[1].checked, "Overall is selected")

	-- Toggle and the slash commands.
	check(api:IsShown(), "shown")
	api:Toggle()
	check(api:IsShown() == false, "Toggle hides")
	api:Toggle()
	check(api:IsShown(), "Toggle shows again")
	equal(env.SLASH_FOREVERLEADERBOARDS1, "/forever", "/forever is claimed when free")
	equal(env.SLASH_FOREVERLEADERBOARDS2, "/flb", "/flb is always there")
	env.SlashCmdList.FOREVERLEADERBOARDS("")
	check(api:IsShown() == false, "the slash command toggles")
	env.SlashCmdList.FOREVERLEADERBOARDS("paths")
	check(api:IsShown(), "a slash argument opens a board")
	equal(api.window.heading.text, "Metric paths", "the named board")

	-- The dropdown scope callback runs after the selected board is the one refreshed.
	api:Open("guide")
	radios = {}
	api.window.dropdown.menu(api.window.dropdown, root)
	radios[2].onClick()
	equal(api.window.heading.text, "Metric guide", "scope keeps the selected board")
	radios[1].onClick()
end

-- Tab order ------------------------------------------------------------------------------------------------------
do
	Client()
	local api = Load()
	local late = spec("late", {}, {})
	late.order = 2
	api:Register("late", late)
	local early = spec("early", {}, {})
	early.order = 1
	api:Register("early", early)
	equal(api:Boards()[1].key, "early", "an explicit order wins")
	equal(api:Boards()[2].key, "late", "and the rest follow")
	local first = spec("first", {}, {})
	first.order = 0
	api:Register("first", first)
	equal(api:Boards()[1].key, "first", "lower orders come first")
	api:Register("late", spec("late", {}, {}))
	equal(api:Boards()[3].key, "late", "re-registering keeps the board's place")
end

-- A consumer that already owns /forever keeps it -----------------------------------------------------------------
do
	Client()
	env.SLASH_FOREVER1 = "/forever"
	local api = Load()
	equal(env.SLASH_FOREVERLEADERBOARDS1, nil, "/forever stays with its owner")
	equal(env.SLASH_FOREVERLEADERBOARDS2, "/flb", "/flb still opens the window")
	check(api ~= nil, "the window still loads")
end

-- The pinned own row ---------------------------------------------------------------------------------------------
do
	Client()
	local api = Load()
	local rows = {}
	for index = 1, 14 do
		rows[index] = row("Peer" .. index, 100 - index, index .. " total", false, "MAGE")
	end
	rows[14] = row("Me", 2, "240 total", true, "HUNTER")
	api:Register("long", spec("long", rows, rows))
	api:Open("long")
	local window = api.window
	check(window.pinned:IsShown(), "a row below the visible list is pinned")
	check(window.pinnedSpacer:IsShown(), "with the ... spacer")
	equal(#window.scroll.buttons, 13, "and the own row leaves the list")
	equal(window.pinned.nameText.text, "Me (you)", "the pinned row is the player")
	equal(window.pinned.rankText.text, "14", "with their place")
	equal(window.pinned.value.text, "+2", "and their value")
	check(window.scroll.buttons[13].nameText.text == "Peer13", "the list keeps its neighbours")

	api:Register(
		"short",
		spec("short", {
			row("Abe", 9, nil, false, "MAGE"),
			row("Me", 8, nil, true, "HUNTER"),
			row("Zed", 7, nil, false, "MAGE"),
		}, {})
	)
	api:Open("short")
	check(window.pinned:IsShown() == false, "an own row in view is not pinned")
	check(window.pinnedSpacer:IsShown() == false, "and the spacer is hidden")
	check(window.scroll.buttons[2].highlight:IsShown(), "it stays highlighted in the list")
end

-- Overall points across boards -----------------------------------------------------------------------------------
do
	Client()
	local api = Load()
	local cache = {}
	local function board(key, week, all)
		cache[key] = { week = week, all = all }
		api:Register(key, {
			title = key,
			metric = "Metric " .. key,
			icon = ICON,
			board = function(scope)
				return scope == "week" and cache[key].week or cache[key].all
			end,
		})
	end
	board("one", {
		row("Abe-OtherRealm", 100, nil, false, "MAGE"),
		row("Me", 90, nil, true, "HUNTER"),
		row("Bea", 80, nil, false, "MAGE"),
	}, {
		row("Bea", 100, nil, false, "MAGE"),
		row("Abe-OtherRealm", 90, nil, false, "MAGE"),
		row("Me", 80, nil, true, "HUNTER"),
	})
	board("two", {
		row("Abe-OtherRealm", 100, nil, false, "MAGE"),
		row("Me", 90, nil, true, "HUNTER"),
	}, {
		row("Bea", 100, nil, false, "MAGE"),
		row("Me", 90, nil, true, "HUNTER"),
		row("Abe-OtherRealm", 80, nil, false, "MAGE"),
	})
	local week = api:Overall("week")
	equal(#week, 3, "only players who placed")
	equal(week[1].name, "Abe-OtherRealm", "first overall")
	equal(week[1].value, 20, "10 + 10 points")
	equal(week[1].extra, "2 boards", "the second column")
	equal(week[2].name, "Me", "second overall")
	equal(week[2].value, 16, "8 + 8 points")
	check(week[2].you, "the player's overall row is theirs")
	equal(week[3].value, 6, "6 + 0 points")
	equal(week[3].extra, "1 board", "one board reads singular")

	local standing = api:Standing("Me", "week")
	check(standing.found, "the player is found")
	equal(standing.rank, 2, "their overall place")
	equal(standing.points, 16, "their points")
	equal(standing.boards, 2, "their boards")
	equal(#standing.places, 2, "their per-addon places")
	equal(standing.places[1].title, "one", "in tab order")
	equal(standing.places[1].rank, 2, "their place there")
	equal(standing.places[2].rank, 2, "and on the second board")

	local all = api:Overall("all")
	equal(all[1].name, "Bea", "the all-time order is the boards' own order")
	equal(all[1].value, 20, "10 + 10 points")
	equal(api:Standing("Absent", "week").found, false, "an absent player is not found")

	-- Ties sort by identity, and a ninth place scores nothing but is still found.
	board("three", {
		row("Abe-OtherRealm", 9, nil, false, "MAGE"),
		row("Bea", 8, nil, false, "MAGE"),
		row("Cy", 7, nil, false, "MAGE"),
		row("Dee", 6, nil, false, "MAGE"),
		row("Eve", 5, nil, false, "MAGE"),
		row("Fay", 4, nil, false, "MAGE"),
		row("Gus", 3, nil, false, "MAGE"),
		row("Hal", 2, nil, false, "MAGE"),
		row("Ninth", 1, nil, false, "MAGE"),
	}, {})
	local rows = api:Overall("week")
	local ninth
	for _, entry in ipairs(rows) do
		if entry.name == "Ninth" then
			ninth = entry
		end
	end
	equal(ninth, nil, "a ninth place is not on the overall board")
	equal(api:Standing("Ninth", "week").found, true, "but is still known")
	equal(api:Standing("Ninth", "week").points, 0, "with no points")
end

-- The overall cache ---------------------------------------------------------------------------------------------
do
	Client()
	local api = Load()
	local builds, revision = 0, 0
	local list = {
		row("Abe-OtherRealm", 100, nil, false, "MAGE"),
		row("Me", 90, nil, true, "HUNTER"),
	}
	api:Register("one", {
		title = "one",
		metric = "Metric one",
		icon = ICON,
		board = function()
			builds = builds + 1
			return list
		end,
		revision = function()
			return revision
		end,
	})
	equal(#api:Overall("week"), 2, "the first overall build")
	equal(builds, 1, "one board build")
	equal(#api:Overall("week"), 2, "the second overall")
	equal(builds, 1, "the window and a hover reuse the cache")
	equal(api:Standing("Me", "week").rank, 2, "standing reads the same players map")
	equal(builds, 1, "without another build")

	revision = revision + 1
	api:Overall("week")
	equal(builds, 2, "a revision rebuilds")

	api:Overall("all")
	equal(builds, 3, "the other scope builds once")
	api:Overall("week")
	equal(builds, 3, "and each scope keeps its own cache")

	weekRemaining = 200000
	api:Overall("week")
	equal(builds, 4, "a new week start rebuilds")

	api:Register("two", {
		title = "two",
		metric = "Metric two",
		icon = ICON,
		board = function()
			builds = builds + 1
			return list
		end,
		revision = function()
			return revision
		end,
	})
	api:Overall("week")
	equal(builds, 6, "registering a board rebuilds and calls both")
end

-- Classes the client already knows --------------------------------------------------------------------------------
do
	Client()
	unitClasses.party1 = "MAGE"
	unitNames.party1 = { "Groupie", "OtherRealm" }
	guildMembers = {
		{ name = "Guilder-OtherRealm", class = "ROGUE" },
		{ name = "Second", class = "PRIEST" },
	}
	local api = Load()
	api:Register(
		"classes",
		spec("classes", {
			row("Me", 40, nil, true),
			row("Groupie-OtherRealm", 30, nil, false),
			row("Guilder", 20, nil, false),
			row("Nobody-X", 10, nil, false),
		}, {})
	)
	api:Open("classes")

	equal(api.ClassOf("Me"), "HUNTER", "the player's own class comes from UnitClass('player')")
	equal(api.ClassOf("Groupie-OtherRealm"), "MAGE", "a group member matches regardless of the realm spelling")
	equal(api.ClassOf("guilder"), "ROGUE", "a guild member comes from the roster's classFileName")
	equal(api.ClassOf("Nobody"), nil, "an unknown player has no class")

	local window = api.window
	equal(window.scroll.buttons[1].classIcon.atlas, "groupfinder-icon-class-hunter", "the own row's icon")
	equal(window.scroll.buttons[2].classIcon.atlas, "groupfinder-icon-class-mage", "the group row's icon")
	equal(window.scroll.buttons[3].classIcon.atlas, "groupfinder-icon-class-rogue", "the guild row's icon")
	equal(window.scroll.buttons[3].nameText.textColor[2], 0.96, "and its class colour")
	check(window.scroll.buttons[4].classIcon:IsShown() == false, "an unknown row has no icon")
	equal(window.scroll.buttons[4].nameText.textColor[1], 1, "and keeps the neutral colour")

	-- Refreshing the rows repeatedly must not read the guild roster again.
	local built = guildCalls
	api:Select("classes")
	api:Select("overall")
	api:Select("classes")
	equal(guildCalls, built, "a refresh reuses the cached classes")

	-- A roster event while the window is closed only marks the cache stale.
	api:Toggle()
	check(api:IsShown() == false, "the window is closed")
	guildMembers[#guildMembers + 1] = { name = "Newbie-OtherRealm", class = "PRIEST" }
	local before = guildCalls
	local function RosterEvent(event)
		for _, widget in ipairs(frames) do
			local handler = widget.scripts and widget.scripts.OnEvent
			if handler then
				handler(widget, event)
				return
			end
		end
		error("no roster event frame")
	end
	RosterEvent("GUILD_ROSTER_UPDATE")
	equal(guildCalls, before, "a closed window does not read the roster")
	equal(api.ClassOf("Newbie"), "PRIEST", "but the next lookup rebuilds the guild part")
	equal(guildCalls, before + #guildMembers, "once, over the whole roster")

	-- While the window is shown the event rebuilds at once, and a group event leaves the guild part alone.
	api:Open("classes")
	guildMembers[#guildMembers + 1] = { name = "Shown-OtherRealm", class = "MAGE" }
	before = guildCalls
	RosterEvent("GUILD_ROSTER_UPDATE")
	equal(guildCalls, before + #guildMembers, "an open window rebuilds the guild part on the event")
	equal(api.ClassOf("Shown"), "MAGE", "and the new member resolves")
	unitNames.party2 = { "Latish", "OtherRealm" }
	unitClasses.party2 = "WARRIOR"
	before = guildCalls
	RosterEvent("GROUP_ROSTER_UPDATE")
	equal(guildCalls, before, "a group event does not read the guild roster")
	equal(api.ClassOf("Latish-OtherRealm"), "WARRIOR", "the new group member resolves")
	equal(api.ClassOf("Second"), "PRIEST", "and the guild part is still there")
end

-- Sharing is opt-out ---------------------------------------------------------------------------------------------
do
	Client()
	local api = Load()
	local saved = {}
	local function shareSpec(key, value)
		return {
			title = key,
			metric = "Metric " .. key,
			icon = ICON,
			board = function()
				return { row("Me", 1, nil, true, "HUNTER") }
			end,
			sharing = function()
				if value == "error" then
					error("no saved setting")
				end
				return value
			end,
			setSharing = function(flag)
				saved[key] = flag
			end,
		}
	end

	api:Register("missing", shareSpec("missing", nil))
	api:Open("missing")
	check(api.window.share:IsShown(), "a board with a switch shows it")
	check(api.window.share:GetChecked(), "a missing setting reads as on")
	api.window.share:SetChecked(false)
	api.window.share:Click()
	equal(saved.missing, false, "unchecking still saves an explicit false")

	api:Register("off", shareSpec("off", false))
	api:Open("off")
	check(api.window.share:GetChecked() == false, "an explicit false reads as off")

	api:Register("off", shareSpec("off", nil))
	api:Register("on", shareSpec("on", true))
	api:Open("overall")
	check(api.window.share:GetChecked(), "Overall is on when no board is off")
	api:Open("overall")
	check(api.window.share:GetChecked(), "a missing setting does not uncheck Overall")
	api:Register("errors", shareSpec("errors", "error"))
	api:Open("overall")
	check(api.window.share:GetChecked(), "a share callback that errors reads as on")
	api:Register("off", shareSpec("off", false))
	api:Open("overall")
	check(api.window.share:GetChecked() == false, "one explicit false unchecks Overall")
end

-- The tooltip ----------------------------------------------------------------------------------------------------
do
	Client()
	local api = Load()
	api:Register(
		"one",
		spec("one", {
			row("Abe-OtherRealm", 100, nil, false, "MAGE"),
			row("Me", 90, nil, true, "HUNTER"),
		}, {
			row("Abe-OtherRealm", 100, nil, false, "MAGE"),
			row("Me", 90, nil, true, "HUNTER"),
		})
	)
	api:Register(
		"two",
		spec("two", {
			row("Abe-OtherRealm", 100, nil, false, "MAGE"),
			row("Me", 90, nil, true, "HUNTER"),
		}, {
			row("Abe-OtherRealm", 100, nil, false, "MAGE"),
			row("Me", 90, nil, true, "HUNTER"),
		})
	)
	api:Register(
		"wide",
		spec(
			"wide",
			(function()
				local list = {}
				for index = 1, 9 do
					list[index] =
						row(index == 9 and "Ninth-OtherRealm" or ("Peer" .. index), 100 - index, nil, false, "MAGE")
				end
				return list
			end)(),
			{}
		)
	)
	unitNames.target = { "Abe", "OtherRealm" }
	unitNames.ninth = { "Ninth", "OtherRealm" }
	unitNames.nobody = { "Nobody", "OtherRealm" }

	local hook = env.GameTooltip.hooks.OnTooltipSetUnit
	equal(#hook, 1, "one unit-tooltip hook")
	local tip = Create("GameTooltip")
	tip.unit = "target"
	hook[1](tip)
	equal(#tip.lines, 2, "an overall leader gets two lines")
	check(tip.lines[1].text:find("Forever: 1st overall this week", 1, true), "the gold line")
	check(tip.lines[1].text:find("|A:challenges-medal-gold:14:14|a", 1, true), "with the medal")
	equal(tip.lines[1].r, 1, "gold colour")
	equal(tip.lines[2].text, "one 1st, two 1st", "the per-addon places")

	tip = Create("GameTooltip")
	tip.unit = "ninth"
	hook[1](tip)
	equal(#tip.lines, 1, "a player placing nowhere gets one line")
	equal(tip.lines[1].text, "Uses Forever addons", "and it says so")
	equal(tip.lines[1].r, 0.5, "in grey")

	tip = Create("GameTooltip")
	tip.unit = "nobody"
	hook[1](tip)
	equal(rawget(tip, "lines"), nil, "an unknown player adds nothing")

	api.scope = "all"
	tip = Create("GameTooltip")
	tip.unit = "target"
	hook[1](tip)
	check(tip.lines[1].text:find("Forever: 1st overall", 1, true), "all-time wording")
	check(not tip.lines[1].text:find("this week", 1, true), "and no week note")
end

-- The modern tooltip hook ----------------------------------------------------------------------------------------
do
	Client()
	local calls = {}
	env.Enum = { TooltipDataType = { Unit = 7 } }
	env.TooltipDataProcessor = {
		AddTooltipPostCall = function(_, kind, handler)
			calls[#calls + 1] = { kind = kind, handler = handler }
		end,
	}
	local api = Load()
	equal(#calls, 1, "TooltipDataProcessor gets the unit hook")
	equal(calls[1].kind, 7, "for unit tooltips only")
	check(api.tooltipHooked, "the hook is marked installed")
	equal(env.GameTooltip.hooks.OnTooltipSetUnit, nil, "the widget script is not also hooked")
	api:Register("guide", spec("guide", { row("Me", 1, nil, true, "HUNTER") }, {}))
	local tip = Create("GameTooltip")
	tip.unit = "player"
	calls[1].handler(tip)
	equal(#tip.lines, 2, "the processor handler reaches the board")
	check(tip.lines[1].text:find("Forever: 1st overall this week", 1, true), "with the place")

	api.VERSION = 0
	local fresh = Load()
	equal(#calls, 1, "a newer copy takes the hook without installing another")
	check(fresh.tooltipHooked, "the flag is handed over")
end

-- Version takeover -----------------------------------------------------------------------------------------------
do
	Client()
	local api = Load()
	api:Register("guide", spec("guide", { row("Me", 1, nil, true, "HUNTER") }, {}))
	api:Open("guide")
	local oldWindow = api.window
	check(oldWindow:IsShown(), "the old window is open")

	-- An older copy in the same environment is replaced by this one, which keeps its registrations.
	api.VERSION = 0
	local fresh = Load()
	check(fresh ~= api, "a newer copy replaces an older global")
	equal(env.ForeverLeaderboards, fresh, "the new global is published")
	equal(api.window, oldWindow, "the old API keeps its own window reference")
	check(oldWindow:IsShown() == false, "the old window is put away")
	equal(#fresh:Boards(), 1, "registrations survive the takeover")
	equal(fresh:Boards()[1].key, "guide", "with their keys")
	check(fresh.tooltipHooked, "the one tooltip hook is handed over")
	equal(#env.GameTooltip.hooks.OnTooltipSetUnit, 1, "and is not installed twice")

	-- The older copy's own call sites reach the newer window.
	fresh.VERSION = 2
	api:Register("late", spec("late", { row("Me", 1, nil, true, "HUNTER") }, {}))
	equal(#fresh:Boards(), 2, "an old copy's Register joins the new API")
	api:Open("late")
	equal(fresh.window.heading.text, "Metric late", "an old copy's Open reaches the new window")
	api:Toggle()
	check(fresh.window:IsShown() == false, "an old copy's Toggle reaches the new window")

	-- A copy older than the published global joins it instead of replacing it.
	fresh.VERSION = 9
	local joined = Load()
	equal(env.ForeverLeaderboards, fresh, "a newer global is kept")
	equal(joined, fresh, "the older file adopts it")
end

print(("leaderboards_spec: %d checks passed"):format(checks))
