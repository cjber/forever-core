-- luacheck: read globals scenario ADDON
-- Forever's OpenRecipe, as recorded live (cjber/forever-core#831): from a hardware event it closes the open Professions
-- window (three TRADE_SKILL_CLOSE) and answers OPEN_RECIPE_RESPONSE(recipe, base, child); from tainted code outside a
-- hardware event the client refuses it and blames the addon, yet still answers. A recipe reports its child skill line
-- with the base line as parent, and GetProfessionChildSkillLineID is 0. The work counter measures each event's handlers
-- and each wrapped path's API calls.
scenario("OpenRecipe closes the Professions window and the work counter measures it", function(sim)
	local G = sim.G
	sim.world.professions = {
		{
			skillLineID = 185,
			childSkillLineID = 2939,
			name = "Cooking",
			skill = 40,
			max = 75,
			categories = { { id = 1, name = "Cooking" } },
			recipes = { { id = 2538, name = "Charred Wolf Meat", category = 1, itemID = 2679 } },
		},
	}
	sim:login()
	sim:runAs(
		ADDON,
		[[
		local seen = { closes = 0, responses = {} }
		_G.OpenRecipeScenarioSeen = seen
		local f = CreateFrame("Frame")
		f:RegisterEvent("TRADE_SKILL_CLOSE")
		f:RegisterEvent("OPEN_RECIPE_RESPONSE")
		f:SetScript("OnEvent", function(_, event, ...)
			if event == "TRADE_SKILL_CLOSE" then
				seen.closes = seen.closes + 1
			else
				seen.responses[#seen.responses + 1] = { ... }
			end
		end)
	]]
	)
	local seen = G.OpenRecipeScenarioSeen

	local info = G.C_TradeSkillUI.GetProfessionInfoByRecipeID(2538)
	assert(info.professionID == 2939 and info.parentProfessionID == 185, "a recipe reports its child skill line")
	assert(G.C_TradeSkillUI.GetProfessionChildSkillLineID() == 0, "no child line is reported")

	-- Outside a hardware event: refused and blamed, the window stays open, the response still arrives.
	local pf = sim:openProfessions(185)
	assert(pf and pf:IsShown(), "the Professions window is open")
	sim.work.reset()
	sim:runAs(ADDON, "C_TradeSkillUI.OpenRecipe(2538)")
	sim:advance(0.1)
	sim:expectError("tried to call the protected function 'C_TradeSkillUI.OpenRecipe()'")
	sim:takeErrors()
	assert(seen.closes == 0, "a refused OpenRecipe leaves the window open")
	local response = seen.responses[1]
	assert(
		response and response[1] == 2538 and response[2] == 185 and response[3] == 2939,
		"the response names base and child"
	)
	assert(sim.work.paths.OPEN_RECIPE_RESPONSE.runs == 1, "the counter saw the response event")

	-- From a hardware event: the window closes with three TRADE_SKILL_CLOSE, then the response.
	sim:input(function()
		sim:runAs(ADDON, "C_TradeSkillUI.OpenRecipe(2538)")
	end)
	sim:advance(0.1)
	sim:expectNoErrors(ADDON)
	assert(seen.closes == 3, "three TRADE_SKILL_CLOSE, got " .. seen.closes)
	assert(#seen.responses == 2, "a second response arrived")
	assert(not sim.world.openProfession, "the window's profession is closed")
	local closes = sim.work.paths.TRADE_SKILL_CLOSE
	assert(closes.runs == 3 and closes.maxHandlers >= 1, "each close dispatched our handler")

	-- A wrapped path counts the API calls tainted code made inside it, nested events included.
	local counts, value = sim.work.measure("click:info", function()
		sim:runAs(ADDON, "C_TradeSkillUI.GetProfessionChildSkillLineID()")
		return 7
	end)
	assert(value == 7, "measure returns the path's results")
	assert(counts.apiCalls == 1 and sim.work.paths["click:info"].maxApiCalls == 1, "one API call was counted")
end)
