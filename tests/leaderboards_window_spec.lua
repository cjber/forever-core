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

	api.VERSION = 0
	local fresh = Load()
	equal(#calls, 1, "a newer copy takes the hook without installing another")
	check(fresh.tooltipHooked, "the flag is handed over")
end

-- Version takeover -----------------------------------------------------------------------------------------------
do
	Client()
	local env = harness.env
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
	fresh.VERSION = api.LEADERBOARDS_VERSION + 1
	api:Register("late", spec("late", { row("Me", 1, nil, true, "HUNTER") }, {}))
	equal(#fresh:Boards(), 2, "an old copy's Register joins the new API")
	api:Open("late")
	equal(fresh.window.heading.text, "Metric late", "an old copy's Open reaches the new window")
	api:Toggle()
	check(fresh.window:IsShown() == false, "an old copy's Toggle reaches the new window")

	-- A copy older than the published global joins it instead of replacing it.
	fresh.VERSION = api.LEADERBOARDS_VERSION + 8
	local joined = Load()
	equal(env.ForeverLeaderboards, fresh, "a newer global is kept")
	equal(joined, fresh, "the older file adopts it")
end

-- The reach choice includes relayed peers -------------------------------------------------------------------------
do
	Client()
	local env = harness.env
	local manager = { includeRelayed = false }
	env.ForeverPeerStats = manager
	local function board()
		local include = manager.includeRelayed == true
		local list = { row("Abe", 10, nil, false, "MAGE"), row("Me", 1, nil, true, "HUNTER") }
		if include then
			list[#list + 1] = row("Met-OtherRealm", 5, nil, false, "MAGE")
		end
		return list
	end
	local api = Load()
	api:Register("guide", { title = "guide", metric = "Metric guide", icon = ICON, board = board })
	api:Open("guide")
	local window = api.window
	equal(window.subtitle.text, "Your guild and group", "the default reach")
	equal(manager.includeRelayed, false, "the flag is false after the board call")
	local root = harness.MenuRoot()
	window.dropdown.menu(window.dropdown, root)
	equal(root.dividers, 1, "one divider between scopes and reaches")
	equal(#root.radios, 4, "two scopes and two reaches")
	equal(root.radios[1].text, "This week", "the first scope")
	equal(root.radios[2].text, "All time", "the second scope")
	equal(root.radios[3].text, "Your guild and group", "the direct reach")
	equal(root.radios[4].text, "Players you've met", "the met reach")
	equal(root.radios[3].getter(), true, "the direct reach is selected by default")

	local names = {}
	for _, button in ipairs(window.scroll.buttons) do
		names[button.nameText.text] = true
	end
	equal(names["Met-OtherRealm"], nil, "the board hides relayed peers by default")

	root.radios[4].onClick()
	equal(api.reach, "met", "the reach changes")
	equal(window.subtitle.text, "Players you've met", "the subtitle follows the reach")
	equal(manager.includeRelayed, false, "the flag is false again after the board call")
	names = {}
	for _, button in ipairs(window.scroll.buttons) do
		names[button.nameText.text] = true
	end
	equal(names["Met-OtherRealm"], true, "the board shows relayed peers")

	local found = false
	for _, entry in ipairs(api:Overall("week")) do
		if entry.name == "Met-OtherRealm" then
			found = true
		end
	end
	equal(found, true, "Overall includes relayed peers")
	equal(manager.includeRelayed, false, "the flag is false again after Overall")

	root.radios[3].onClick()
	equal(api.reach, "group", "switching back")
	equal(window.subtitle.text, "Your guild and group", "restores the subtitle")
	names = {}
	for _, button in ipairs(window.scroll.buttons) do
		names[button.nameText.text] = true
	end
	equal(names["Met-OtherRealm"], nil, "and hides relayed peers again")

	-- A board that raises still restores the flag.
	api:Register("boom", {
		title = "boom",
		metric = "Boom",
		icon = ICON,
		board = function()
			error("boom")
		end,
	})
	api.reach = "met"
	manager.includeRelayed = false
	local ok = pcall(function()
		return api:Overall("week")
	end)
	check(ok, "a raising board does not escape")
	equal(manager.includeRelayed, false, "the flag is restored when a board raises")
end

-- The period dropdown under the gamepad interface: a press steps through the four choices instead of opening a menu,
-- which would taint the gamepad focus (#267).
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
	api:Register("one", spec("one", { row("Me", 1, nil, true, "HUNTER") }, {}))
	api:Open("one")
	return api.window.dropdown
end

-- A gamepad press steps to the next choice and opens no menu -----------------------------------------------------
do
	GamepadClient(true)
	local api = Load()
	local dropdown = OpenBoard(api)
	local window = api.window
	equal(api.scope, "week", "a fresh window starts at this week")
	equal(api.reach, "group", "for the guild and group")
	equal(dropdown.openedMenus, 0, "no menu opens before a press")

	dropdown:OpenMenu()
	equal(dropdown.openedMenus, 0, "the first press opens no menu")
	equal(api.scope, "all", "the first press moves to all time")
	equal(api.reach, "group", "staying on the guild and group")
	equal(window.valueHeader.text, "All time", "the header follows the scope")
	equal(window.subtitle.text, "Your guild and group", "the subtitle follows the reach")

	dropdown:OpenMenu()
	equal(dropdown.openedMenus, 0, "the second press opens no menu")
	equal(api.scope, "week", "the second press moves back to this week")
	equal(api.reach, "met", "and on to the players you've met")
	equal(window.valueHeader.text, "This week", "the header shows this week")
	equal(window.subtitle.text, "Players you've met", "the subtitle shows the wider reach")

	dropdown:OpenMenu()
	equal(dropdown.openedMenus, 0, "the third press opens no menu")
	equal(api.scope, "all", "the third press moves to all time again")
	equal(api.reach, "met", "still for the players you've met")
	equal(window.valueHeader.text, "All time", "the header shows all time")
	equal(window.subtitle.text, "Players you've met", "the subtitle keeps the reach")

	dropdown:OpenMenu()
	equal(dropdown.openedMenus, 0, "the fourth press opens no menu")
	equal(api.scope, "week", "the fourth press wraps to this week")
	equal(api.reach, "group", "and back to the guild and group")
	equal(window.valueHeader.text, "This week", "the header is back to this week")
	equal(window.subtitle.text, "Your guild and group", "the subtitle is back to the guild and group")
end

-- A disabled dropdown does nothing --------------------------------------------------------------------------------
do
	GamepadClient(true)
	local api = Load()
	local dropdown = OpenBoard(api)
	dropdown:SetEnabled(false)
	check(dropdown:IsEnabled() == false, "the harness can disable the dropdown")
	dropdown:OpenMenu()
	equal(dropdown.openedMenus, 0, "a disabled press opens no menu")
	equal(api.scope, "week", "and keeps the scope")
	equal(api.reach, "group", "and the reach")
end

-- With the gamepad interface off the client's own OpenMenu runs ---------------------------------------------------
do
	GamepadClient(false)
	local api = Load()
	local dropdown = OpenBoard(api)
	dropdown:OpenMenu()
	equal(dropdown.openedMenus, 1, "the client's OpenMenu runs once")
	equal(api.scope, "week", "and the scope is unchanged")
	equal(api.reach, "group", "and the reach is unchanged")
end

-- With no InputUtil at all the menu opens as before -----------------------------------------------------------------
do
	Client()
	local api = Load()
	local dropdown = OpenBoard(api)
	dropdown:OpenMenu()
	equal(dropdown.openedMenus, 1, "a press with no gamepad switch opens the menu")
	equal(api.scope, "week", "and leaves the scope alone")
	equal(api.reach, "group", "and the reach alone")
end

print(("leaderboards_window_spec: %d checks passed"):format(harness.checks()))
