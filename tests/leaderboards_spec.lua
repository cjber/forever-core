-- Contract for the shared Forever Leaderboards window (UI/Leaderboards.lua), against a mocked client.
local harness = dofile("tests/leaderboards_harness.lua")
local check, equal = harness.check, harness.equal
local Client, Load = harness.Client, harness.Load
local row, ICON, spec, noop = harness.row, harness.ICON, harness.spec, harness.noop

-- Registration, the window and its rows --------------------------------------------------------------------------
do
	Client()
	local env, frames, named = harness.env, harness.frames, harness.named
	local api = Load()
	check(api ~= nil and api.VERSION == 4, "the first copy publishes a versioned global")
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
	equal(named.ForeverLeaderboardsFrame4, window, "the window has its name")
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
		CreateDivider = noop,
		CreateRadio = function(_, text, _, onClick)
			radios[#radios + 1] = { text = text, onClick = onClick }
		end,
	}
	window.dropdown.menu(window.dropdown, root)
	equal(#radios, 4, "two scopes and two reaches")
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

-- /forever debug routes to the shared log without opening a board ------------------------------------------------
do
	Client()
	local env = harness.env
	local api, ns = Load()
	local seen
	ns.DebugCommand = function(argument)
		seen = argument
		return true
	end
	check(api:IsShown() == false, "debug starts with no window")
	env.SlashCmdList.FOREVERLEADERBOARDS("debug show")
	equal(seen, "show", "the debug subcommand receives its argument")
	check(api:IsShown() == false, "debug does not open the window")
	env.SlashCmdList.FOREVERLEADERBOARDS("debug")
	equal(seen, "", "a bare debug reaches the log")
	ns.DebugCommand = nil
	env.SlashCmdList.FOREVERLEADERBOARDS("debug show")
	check(api:IsShown() == false, "a copy without the log still answers debug")
	env.SlashCmdList.FOREVERLEADERBOARDS("paths")
	check(api:IsShown(), "a board name still opens a board")
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
	local env = harness.env
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

-- Full Forever names in the overall rows --------------------------------------------------------------------------
do
	Client()
	local env = harness.env
	harness.unitNames.player = { "Hel", "Io" }
	env.Constants = { CharacterNameSeparatorConsts = { CHARACTERNAME_SURNAME_SEPARATOR = " " } }
	local api, ns = Load()
	equal(ns.LeaderboardsData.OwnName(), "Hel Io", "the own name joins both UnitName returns")

	local rows = {}
	for index = 1, 8 do
		rows[index] = row("Peer" .. index, 100 - index, nil, false, "MAGE")
	end
	rows[9] = row("HelIo", 1, nil, true, "HUNTER")
	api:Register("ninth", spec("ninth", rows, {}))
	api:Open("overall")
	local own
	for _, button in ipairs(api.window.scroll.buttons) do
		if button.nameText.text == "Hel Io (you)" then
			own = button
		end
	end
	check(own ~= nil, "the player's row is built from both returns")
	check(api:Standing("HelIo", "week").found, "the compacted key still finds the player")
end

-- A display name and its compacted key are one player -------------------------------------------------------------
do
	Client()
	local api = Load()
	api:Register("display", spec("display", { row("Dirtyjoke Lovetties", 10, nil, false, "MAGE") }, {}))
	api:Register("compact", spec("compact", { row("DirtyjokeLovetties", 9, nil, false, "MAGE") }, {}))
	local overall = api:Overall("week")
	equal(#overall, 1, "the spaced name and the compacted key are one player")
	equal(overall[1].name, "Dirtyjoke Lovetties", "the display name is what the row draws")
	equal(overall[1].value, 20, "both boards score")
	equal(overall[1].identity, "dirtyjokelovetties", "the compacted identity is kept")
end

-- Two peers whose display names match keep their own identities ---------------------------------------------------
do
	Client()
	local api = Load()
	api:Register(
		"realm",
		spec("realm", { { name = "Abe", identity = "abe-otherrealm", value = 5, class = "MAGE" } }, {})
	)
	api:Register("home", spec("home", { { name = "Abe", identity = "abe", value = 4, class = "MAGE" } }, {}))
	local rows = api:Overall("week")
	equal(#rows, 2, "two players with the same display name stay apart")
	equal(rows[1].name, "Abe", "both draw the display name")
	equal(rows[2].name, "Abe", "both draw the display name")
end

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

	harness.weekRemaining = 200000
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
	local frames = harness.frames
	local unitNames, unitClasses = harness.unitNames, harness.unitClasses
	unitClasses.party1 = "MAGE"
	unitNames.party1 = { "Groupie", "OtherRealm" }
	harness.guildMembers = {
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
	local built = harness.guildCalls
	api:Select("classes")
	api:Select("overall")
	api:Select("classes")
	equal(harness.guildCalls, built, "a refresh reuses the cached classes")

	-- A roster event while the window is closed only marks the cache stale.
	api:Toggle()
	check(api:IsShown() == false, "the window is closed")
	harness.guildMembers[#harness.guildMembers + 1] = { name = "Newbie-OtherRealm", class = "PRIEST" }
	local before = harness.guildCalls
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
	equal(harness.guildCalls, before, "a closed window does not read the roster")
	equal(api.ClassOf("Newbie"), "PRIEST", "but the next lookup rebuilds the guild part")
	equal(harness.guildCalls, before + #harness.guildMembers, "once, over the whole roster")

	-- While the window is shown the event rebuilds at once, and a group event leaves the guild part alone.
	api:Open("classes")
	harness.guildMembers[#harness.guildMembers + 1] = { name = "Shown-OtherRealm", class = "MAGE" }
	before = harness.guildCalls
	RosterEvent("GUILD_ROSTER_UPDATE")
	equal(harness.guildCalls, before + #harness.guildMembers, "an open window rebuilds the guild part on the event")
	equal(api.ClassOf("Shown"), "MAGE", "and the new member resolves")
	unitNames.party2 = { "Latish", "OtherRealm" }
	unitClasses.party2 = "WARRIOR"
	before = harness.guildCalls
	RosterEvent("GROUP_ROSTER_UPDATE")
	equal(harness.guildCalls, before, "a group event does not read the guild roster")
	equal(api.ClassOf("Latish-OtherRealm"), "WARRIOR", "the new group member resolves")
	equal(api.ClassOf("Second"), "PRIEST", "and the guild part is still there")
end

print(("leaderboards_spec: %d checks passed"):format(harness.checks()))
