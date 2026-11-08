-- Takeover from a real v1 copy of the shared Forever Leaderboards window by the current file, with one mocked client
-- and one namespace per addon.
local harness = dofile("tests/leaderboards_harness.lua")
local check, equal = harness.check, harness.equal
local Client = harness.Client
local row, spec, Create = harness.row, harness.spec, harness.Create

local DATA = "Core/LeaderboardsData.lua"
local V1 = "tests/fixtures/leaderboards_v1.lua"
local CURRENT = "UI/Leaderboards.lua"

local function LoadInto(env, path, ns)
	setfenv(assert(loadfile(path)), env)("Test", ns)
	return ns.Leaderboards
end

do
	Client()
	local env = harness.env

	-- The older addon loads first and publishes the window, its slash handler and the tooltip hook.
	local old = { L = harness.PhraseLocale() }
	setfenv(assert(loadfile(DATA)), env)("Test", old)
	local v1 = LoadInto(env, V1, old)
	equal(v1.VERSION, 1, "the fixture is the v1 copy")
	equal(env.ForeverLeaderboards, v1, "v1 publishes the global")
	local shared = { shared = true }
	check(
		v1:Register(
			"guide",
			spec("guide", {
				row("Me", 4, "10 total", true, "HUNTER"),
				row("Abe-OtherRealm", 3, "7 total", false, "MAGE"),
			}, {}, shared)
		),
		"a board registers before the takeover"
	)
	check(v1:Open("guide"), "the v1 window opens")
	local oldWindow = v1.window
	check(oldWindow:IsShown(), "the v1 window is shown")
	equal(harness.named.ForeverLeaderboardsFrame, oldWindow, "with the v1 frame name")
	equal(#env.GameTooltip.hooks.OnTooltipSetUnit, 1, "v1 installed one tooltip hook")
	old.LeaderboardsData.AddTooltip = function()
		error("the v1 data half answered")
	end

	-- The newer addon loads second and takes over.
	local new = { L = harness.PhraseLocale() }
	setfenv(assert(loadfile(DATA)), env)("Test", new)
	local current = LoadInto(env, CURRENT, new)
	equal(current.VERSION, 4, "the current file is v4")
	equal(current.LEADERBOARDS_VERSION, 4, "and names the version it compares")
	equal(env.ForeverLeaderboards, current, "the current file publishes the global")
	check(oldWindow:IsShown() == false, "the v1 window is put away")
	equal(#env.GameTooltip.hooks.OnTooltipSetUnit, 1, "the tooltip hook is not installed twice")
	check(current.tooltipHooked, "the current copy takes the v1 hook's flag")

	-- Every registration made before the takeover is on the current window.
	local boards = current:Boards()
	equal(#boards, 1, "the board registered before the takeover survives")
	equal(boards[1].key, "guide", "with its key")
	equal(boards[1].metric, "Metric guide", "and its spec")
	equal(#v1:Boards(), 1, "the v1 API reads the current board list")
	check(v1:Open("guide"), "the v1 copy's Open answers")
	equal(v1.window, oldWindow, "without building a second window")
	local window = current.window
	check(window ~= nil, "the current file builds its own window")
	check(window:IsShown(), "and shows it")
	check(oldWindow:IsShown() == false, "while the v1 window stays away")
	equal(harness.named.ForeverLeaderboardsFrame4, window, "the current frame name")
	equal(#window.tabs, 2, "Overall plus the pre-takeover board")
	equal(window.tabs[2].key, "guide", "the board tab is still listed")
	equal(window.heading.text, "Metric guide", "and its metric is the heading")

	-- The v1 names still point at the handlers the current copy now owns.
	equal(env.SLASH_FOREVERLEADERBOARDS1, "/forever", "/forever is still claimed")
	equal(env.SLASH_FOREVERLEADERBOARDS2, "/flb", "/flb is still registered")
	local seen
	new.DebugCommand = function(argument)
		seen = argument
		return true
	end
	env.SlashCmdList.FOREVERLEADERBOARDS("debug show")
	equal(seen, "show", "/forever debug reaches the current namespace")
	check(window:IsShown(), "and does not open or close the window")
	env.SlashCmdList.FOREVERLEADERBOARDS("")
	check(window:IsShown() == false, "an empty /forever toggles the current window")
	env.SlashCmdList.FOREVERLEADERBOARDS("guide")
	check(window:IsShown(), "a board name opens the current window")
	equal(window.heading.text, "Metric guide", "on the named board")

	-- The one tooltip hook follows the published global to the current data half and board list.
	harness.unitNames.player = { "Me" }
	local tip = Create("GameTooltip")
	tip.unit = "player"
	env.GameTooltip.hooks.OnTooltipSetUnit[1](tip)
	check(rawget(tip, "lines") ~= nil, "the tooltip hook reaches the current data")
	check(tip.lines[1].text:find("Forever: 1st overall this week", 1, true), "with the pre-takeover board's place")
end

print(("leaderboards_takeover_spec: %d checks passed"):format(harness.checks()))
