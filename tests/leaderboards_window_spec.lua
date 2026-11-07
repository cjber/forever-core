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

print(("leaderboards_window_spec: %d checks passed"):format(harness.checks()))
