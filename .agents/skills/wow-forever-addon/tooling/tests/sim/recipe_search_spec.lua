local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
local sim = Sim.new({ addon = false })
sim.world.professions = {
	{
		skillLineID = 164,
		name = "Blacksmithing",
		skill = 30,
		max = 75,
		categories = { { id = 1, name = "Materials" } },
		recipes = {
			{ id = 2660, name = "Rough Sharpening Stone", category = 1, itemID = 2862 },
			{ id = 3115, name = "Rough Weightstone", category = 1, itemID = 3239 },
			{ id = 2737, name = "Copper Mace", category = 1, itemID = 2844 },
		},
	},
}
sim:login()
local frame = sim:openProfessions()
local api = sim.G.C_TradeSkillUI
local updates = 0
local listener = sim.G.CreateFrame("Frame")
listener:RegisterEvent("TRADE_SKILL_LIST_UPDATE")
listener:SetScript("OnEvent", function()
	updates = updates + 1
end)
local function check(expected)
	local ids = api.GetFilteredRecipeIDs()
	assert(table.concat(ids, ",") == expected, "filtered IDs: " .. table.concat(ids, ","))
	local visible = {}
	for _, row in ipairs(sim:recipeRows()) do
		assert(row.frame:IsShown(), "recipe row is shown")
		visible[#visible + 1] = row.recipeInfo.recipeID
	end
	table.sort(visible)
	table.sort(ids)
	assert(table.concat(visible, ",") == table.concat(ids, ","), "visible rows: " .. table.concat(visible, ","))
	assert(#sim.impl["C_TradeSkillUI.GetAllRecipeIDs"]() == 3, "all recipes remain available")
end
check("2660,3115,2737")
frame.CraftingPage.RecipeList.SearchBox:SetText("wEiGhTsToNe")
sim:advance(0.2)
check("3115")
assert(api.GetRecipeItemNameFilter() == "wEiGhTsToNe")
assert(updates == 1, "search emits one list update")
api.SetRecipeItemNameFilter("wEiGhTsToNe")
sim:advance(0.1)
assert(updates == 1, "unchanged filter emits no update")
frame.CraftingPage.RecipeList.SearchBox:SetText("")
sim:advance(0.2)
assert(api.GetRecipeItemNameFilter() == "")
assert(updates == 2, "clearing emits a list update")
check("2660,3115,2737")
api.SetRecipeItemNameFilter("%")
assert(updates == 2, "list update is asynchronous")
sim:advance(0.1)
check("")
api.SetRecipeItemNameFilter(nil)
sim:advance(0.1)
assert(api.GetRecipeItemNameFilter() == "", "nil clears the filter")
check("2660,3115,2737")
sim:expectNoErrors()
print("recipe_search_spec: passed")
