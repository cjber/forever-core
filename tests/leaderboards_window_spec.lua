-- Sharing, tooltips and version takeover for the shared Forever Leaderboards window (UI/Leaderboards.lua), against a
-- mocked client.
local harness = dofile("tests/leaderboards_harness.lua")
local check, equal = harness.check, harness.equal
local Client, Load = harness.Client, harness.Load
local row, ICON, spec = harness.row, harness.ICON, harness.spec
local Create = harness.Create

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

-- Tabs are Buttons -----------------------------------------------------------------------------------------------
do
	Client()
	local api = Load()
	api:Register("guide", spec("guide", { row("Me", 1, nil, true, "HUNTER") }, {}))
	api:Open("guide")
	local tabs = api.window.tabs
	equal(#tabs, 2, "Overall plus the registered board")
	for _, tab in ipairs(tabs) do
		equal(tab.kind, "Button", "a side tab was not created as a Button")
	end
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
	harness.unitNames.target = { "Abe", "OtherRealm" }
	harness.unitNames.ninth = { "Ninth", "OtherRealm" }
	harness.unitNames.nobody = { "Nobody", "OtherRealm" }

	local env = harness.env
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

-- A tooltip finds a player by their full Forever name -------------------------------------------------------------
do
	Client()
	local env = harness.env
	env.Constants = { CharacterNameSeparatorConsts = { CHARACTERNAME_SURNAME_SEPARATOR = " " } }
	local api = Load()
	api:Register(
		"one",
		spec("one", { row("Hel Io", 100, nil, false, "MAGE") }, { row("Hel Io", 100, nil, false, "MAGE") })
	)
	harness.unitNames.target = { "Hel", "Io" }
	local hook = env.GameTooltip.hooks.OnTooltipSetUnit
	local tip = Create("GameTooltip")
	tip.unit = "target"
	hook[1](tip)
	equal(#tip.lines, 2, "the name and surname reach the shared standing")
	check(tip.lines[1].text:find("Forever: 1st overall this week", 1, true), "with their place")
end

-- The modern tooltip hook ----------------------------------------------------------------------------------------
do
	Client()
	local calls = {}
	local env = harness.env
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
end

-- The reach choice defaults to the widest reach and includes relayed peers -----------------------------------------
do
	Client()
	local manager = { includeRelayed = false }
	local api, ns = Load()
	ns.PeerStats = {
		Manager = function()
			return manager
		end,
	}
	local function board()
		local include = manager.includeRelayed == true
		local list = { row("Abe", 10, nil, false, "MAGE"), row("Me", 1, nil, true, "HUNTER") }
		if include then
			list[#list + 1] = row("Met-OtherRealm", 5, nil, false, "MAGE")
		end
		return list
	end
	api:Register("guide", { title = "guide", metric = "Metric guide", icon = ICON, board = board })
	api:Open("guide")
	local window = api.window
	equal(window.subtitle.text, "3 players you've met", "the default reach and count")
	equal(manager.includeRelayed, false, "the flag is false after the board call")
	local period = harness.MenuRoot()
	window.periodDropdown.menu(window.periodDropdown, period)
	equal(period.dividers, 0, "the period has no divider")
	equal(#period.radios, 2, "two periods")
	equal(period.radios[1].text, "This week", "the first period")
	equal(period.radios[2].text, "All time", "the second period")
	local root = harness.MenuRoot()
	window.reachDropdown.menu(window.reachDropdown, root)
	equal(root.dividers, 0, "the reach has no divider")
	equal(#root.radios, 2, "two reaches")
	equal(root.radios[1].text, "Guild and group", "the direct reach")
	equal(root.radios[2].text, "Players you've met", "the met reach")
	equal(root.radios[2].getter(), true, "the widest reach is selected by default")

	local names = {}
	for _, button in ipairs(window.scroll.buttons) do
		names[button.nameText.text] = true
	end
	equal(names["Met-OtherRealm"], true, "the board shows relayed peers by default")

	local found = false
	for _, entry in ipairs(api:Overall("week")) do
		if entry.name == "Met-OtherRealm" then
			found = true
		end
	end
	equal(found, true, "Overall includes relayed peers")
	equal(manager.includeRelayed, false, "the flag is false again after Overall")

	root.radios[1].onClick()
	equal(api.reach, "group", "the reach changes to the direct one")
	equal(window.subtitle.text, "2 players from your guild and group", "the subtitle follows the reach and count")
	equal(manager.includeRelayed, false, "the flag is false again after the board call")
	names = {}
	for _, button in ipairs(window.scroll.buttons) do
		names[button.nameText.text] = true
	end
	equal(names["Met-OtherRealm"], nil, "the board hides relayed peers on the direct reach")

	root.radios[2].onClick()
	equal(api.reach, "met", "switching back")
	equal(window.subtitle.text, "3 players you've met", "restores the subtitle")
	names = {}
	for _, button in ipairs(window.scroll.buttons) do
		names[button.nameText.text] = true
	end
	equal(names["Met-OtherRealm"], true, "and shows relayed peers again")

	-- A board that raises still restores the flag.
	api:Register("boom", {
		title = "boom",
		metric = "Boom",
		icon = ICON,
		board = function()
			error("boom")
		end,
	})
	manager.includeRelayed = false
	local ok = pcall(function()
		return api:Overall("week")
	end)
	check(ok, "a raising board does not escape")
	equal(manager.includeRelayed, false, "the flag is restored when a board raises")
end

-- A saved reach is kept, and an unknown saved value still opens on the widest reach --------------------------------
do
	Client()
	harness.env.ForeverCoreDB = { leaderboards = { reach = "group" } }
	local manager = { includeRelayed = false }
	local api, ns = Load()
	ns.PeerStats = {
		Manager = function()
			return manager
		end,
	}
	api:Register("one", {
		title = "one",
		metric = "One",
		icon = ICON,
		board = function()
			return { row("Me", 1, nil, true, "HUNTER") }
		end,
	})
	api:Open("one")
	equal(api.reach, "group", "a saved direct reach is restored")
	local root = harness.MenuRoot()
	api.window.reachDropdown.menu(api.window.reachDropdown, root)
	root.radios[2].onClick()
	equal(harness.env.ForeverCoreDB.leaderboards.reach, "met", "a chosen reach is saved")

	Client()
	harness.env.ForeverCoreDB = { leaderboards = { reach = "unknown" } }
	local fresh = Load()
	fresh:Register("one", spec("one", { row("Me", 1, nil, true, "HUNTER") }, {}))
	fresh:Open("one")
	equal(fresh.reach, "met", "an unknown saved value opens on the widest reach")
end

-- Elected mode: the namespace store is the only store. A poisoned global must never be read or written, even when the
-- player changes the saved reach.
do
	Client()
	local store = { leaderboards = { reach = "group" } }
	harness.env.ForeverCoreDB = setmetatable({}, {
		__index = function()
			error("read global ForeverCoreDB")
		end,
		__newindex = function()
			error("wrote global ForeverCoreDB")
		end,
	})
	local manager = { includeRelayed = false }
	local elected, ns = Load(nil, nil, store)
	ns.PeerStats = {
		Manager = function()
			return manager
		end,
	}
	elected:Register("one", spec("one", { row("Me", 1, nil, true, "HUNTER") }, {}))
	elected:Open("one")
	equal(elected.reach, "group", "elected mode restores the namespace store reach")
	local root = harness.MenuRoot()
	elected.window.reachDropdown.menu(elected.window.reachDropdown, root)
	root.radios[2].onClick()
	equal(store.leaderboards.reach, "met", "elected mode saves into the namespace store")
	check(rawget(harness.env.ForeverCoreDB, "leaderboards") == nil, "elected mode writes no global store")
end

-- Each dropdown under the gamepad interface: a press steps to its next choice instead of opening a menu, which would
-- taint the gamepad focus (#267).
---@param gamepad boolean
---@return table env
local function GamepadClient(gamepad)
	local env = Client()
	env.InputUtil = {
		IsGamepadUIEnabled = function()
			return gamepad
		end,
	}
	return env
end

---@param api ForeverLeaderboardsAPI
local function OpenBoard(api)
	local list = { row("Me", 1, nil, true, "HUNTER") }
	api:Register("one", spec("one", list, list))
	api:Open("one")
	return api.window
end

-- A gamepad press steps each dropdown and opens no menu ----------------------------------------------------------
do
	GamepadClient(true)
	local api = Load()
	local window = OpenBoard(api)
	local period, reach = window.periodDropdown, window.reachDropdown
	equal(api.scope, "week", "a fresh window starts at this week")
	equal(api.reach, "met", "and on the widest reach")
	equal(period.openedMenus, 0, "no menu opens before a press")

	period:OpenMenu()
	equal(period.openedMenus, 0, "the period press opens no menu")
	equal(api.scope, "all", "the period press moves to all time")
	equal(api.reach, "met", "leaving the reach alone")
	equal(window.periodHeader.text, "All time", "the header follows the period")
	equal(window.subtitle.text, "1 player you've met", "the subtitle follows the reach")

	reach:OpenMenu()
	equal(reach.openedMenus, 0, "the reach press opens no menu")
	equal(api.scope, "all", "leaving the period alone")
	equal(api.reach, "group", "the reach press moves to the guild and group")
	equal(window.periodHeader.text, "All time", "the header keeps the period")
	equal(window.subtitle.text, "1 player from your guild and group", "the subtitle shows the narrower reach")

	period:OpenMenu()
	equal(period.openedMenus, 0, "the next period press opens no menu")
	equal(api.scope, "week", "the period wraps to this week")
	equal(api.reach, "group", "still for the guild and group")
	equal(window.periodHeader.text, "This week", "the header shows this week")
	equal(window.subtitle.text, "1 player from your guild and group", "the subtitle keeps the reach")

	reach:OpenMenu()
	equal(reach.openedMenus, 0, "the next reach press opens no menu")
	equal(api.scope, "week", "the period stays at this week")
	equal(api.reach, "met", "and the reach wraps back to the players you've met")
	equal(window.subtitle.text, "1 player you've met", "the subtitle is back to the players you've met")
end

-- A disabled dropdown does nothing --------------------------------------------------------------------------------
do
	GamepadClient(true)
	local api = Load()
	local window = OpenBoard(api)
	local period = window.periodDropdown
	period:SetEnabled(false)
	check(period:IsEnabled() == false, "the harness can disable the dropdown")
	period:OpenMenu()
	equal(period.openedMenus, 0, "a disabled press opens no menu")
	equal(api.scope, "week", "and keeps the scope")
	equal(api.reach, "met", "and the reach")
end

-- With the gamepad interface off the client's own OpenMenu runs ---------------------------------------------------
do
	GamepadClient(false)
	local api = Load()
	local window = OpenBoard(api)
	local period, reach = window.periodDropdown, window.reachDropdown
	period:OpenMenu()
	reach:OpenMenu()
	equal(period.openedMenus, 1, "the client's OpenMenu runs once for the period")
	equal(reach.openedMenus, 1, "and once for the reach")
	equal(api.scope, "week", "and the scope is unchanged")
	equal(api.reach, "met", "and the reach is unchanged")
end

-- With no InputUtil at all the menu opens as before -----------------------------------------------------------------
do
	Client()
	local api = Load()
	local window = OpenBoard(api)
	window.periodDropdown:OpenMenu()
	equal(window.periodDropdown.openedMenus, 1, "a press with no gamepad switch opens the menu")
	equal(api.scope, "week", "and leaves the scope alone")
	equal(api.reach, "met", "and the reach alone")
end

print(("leaderboards_window_spec: %d checks passed"):format(harness.checks()))
