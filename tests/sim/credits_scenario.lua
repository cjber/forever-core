-- luacheck: read globals scenario ADDON
-- The Thanks page: two addons hand core their generated credits, a player who helped both is listed once with both
-- addons, the short line names only that addon's players, and the window opens, closes and survives combat and the
-- gamepad interface without tainting it.
scenario("the Thanks page credits every addon's players once", function(sim)
	sim:login()
	local ns
	for _, entry in ipairs(sim.loader.addons) do
		if entry.name == ADDON then
			ns = entry.ns
		end
	end
	assert(ns and ns.CreditsPage, "the credits module is loaded")

	sim:runAs(
		ADDON,
		[[
		local ns = ...
		ns.CreditsPage.Register("SkillUp Forever", {
			players = {
				{ name = "Brainc3ll", what = "The French translation" },
				{ name = "Alex", what = "The cheapest route idea" },
			},
			inspired = {
				{ name = "Questie", what = "The tracker layout" },
			},
		})
		ns.CreditsPage.Register("Legacy Forever", {
			players = {
				{ name = "Brainc3ll", what = "" },
				{ name = "Sam", what = "The map notes" },
			},
		})
		assert(ns.CreditsPage.Line("SkillUp Forever") == "Thanks to Brainc3ll and Alex", "the addon's own line")
		assert(ns.CreditsPage.Line("No Such Addon") == nil, "an addon with no credits has no line")
		local players = ns.CreditsPage.Players()
		local brainc3ll, listed = nil, 0
		for _, row in ipairs(players) do
			if row.name == "Brainc3ll" then
				brainc3ll, listed = row, listed + 1
			end
		end
		assert(listed == 1, "the player who helped both addons is listed once")
		assert(brainc3ll and #brainc3ll.helped == 2, "both addons keep their own line")
		assert(brainc3ll.count == 2, "the row counts both contributions")
		assert(brainc3ll.helped[1].addon == "SkillUp Forever" and brainc3ll.helped[1].what == "The French translation",
			"the first addon's line is kept")
		assert(brainc3ll.helped[2].addon == "Legacy Forever" and brainc3ll.helped[2].what == "",
			"then the second addon's, even when its line is empty")
		local inspired, questie = ns.CreditsPage.Inspired(), nil
		for _, row in ipairs(inspired) do
			if row.name == "Questie" then
				questie = row
			end
		end
		assert(questie ~= nil and #questie.helped >= 1, "the inspired entry is there")
	]],
		ns
	)

	sim:enterCombat()
	sim:input(function()
		assert(ns.CreditsPage.Open(), "the Thanks page opens in combat")
	end)
	sim:advance(0.2)
	assert(ns.CreditsPage.IsShown(), "the Thanks page is shown")
	sim:input(function()
		assert(ns.CreditsPage.Open("Legacy Forever"), "the Thanks page filters to one addon")
		assert(ns.CreditsPage.window.filterDropdown:GetText() == "Legacy Forever", "the dropdown names it")
		assert(ns.CreditsPage.Open(), "reopening with no title keeps that filter")
		assert(ns.CreditsPage.window.filterDropdown:GetText() == "Legacy Forever", "and it is still there")
		assert(ns.CreditsPage.Open(nil), "an explicit nil opens every addon")
		assert(ns.CreditsPage.window.filterDropdown:GetText() == "All addons", "the dropdown says All addons")
	end)
	sim:leaveCombat()
	sim:input(function()
		ns.CreditsPage.Toggle()
	end)
	assert(not ns.CreditsPage.IsShown(), "Toggle closes it")

	sim:setGamepad(true)
	sim:input(function()
		assert(ns.CreditsPage.Open(), "the Thanks page opens with the gamepad interface on")
	end)
	sim:advance(0.2)
	sim:gamepadNavigate()
	sim:input(function()
		ns.CreditsPage.Toggle()
	end)
	assert(not ns.CreditsPage.IsShown(), "and closes again")
	sim:expectNoGamepadTaint(ADDON)
	sim:expectNoErrors(ADDON)
end)
