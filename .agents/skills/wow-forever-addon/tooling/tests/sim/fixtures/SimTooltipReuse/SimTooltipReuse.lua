-- Fixture: inserts one reused frame into GameTooltip with Blizzard's GameTooltip_InsertFrame from the recipe list's
-- OnEnter callback, the pattern behind SkillUp Forever 0.15.0's secret-number error.
local bar
local function OnRecipeEnter(_, row)
	bar = bar or CreateFrame("Frame", nil, UIParent)
	bar:SetSize(160, 24)
	GameTooltip:SetOwner(row, "ANCHOR_RIGHT")
	GameTooltip_SetTitle(GameTooltip, "Recipe")
	GameTooltip_AddNormalLine(GameTooltip, "Range")
	GameTooltip_InsertFrame(GameTooltip, bar, 4)
	GameTooltip:Show()
end

EventUtil.ContinueOnAddOnLoaded("Blizzard_Professions", function()
	EventRegistry:RegisterCallback("Professions.RecipeListOnEnter", OnRecipeEnter, {})
end)
