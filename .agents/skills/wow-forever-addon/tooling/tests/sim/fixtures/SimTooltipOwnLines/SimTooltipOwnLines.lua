-- Fixture: the same tooltip with the frame placed on blank lines it adds itself, never reading the tooltip's
-- geometry, which can be secret while addon code runs.
local bar
local function OnRecipeEnter(_, row)
	bar = bar or CreateFrame("Frame", nil, UIParent)
	bar:SetSize(160, 24)
	GameTooltip:SetOwner(row, "ANCHOR_RIGHT")
	GameTooltip_SetTitle(GameTooltip, "Recipe")
	GameTooltip_AddNormalLine(GameTooltip, "Range")
	GameTooltip:AddLine(" ")
	GameTooltip:AddLine(" ")
	bar:SetParent(GameTooltip)
	bar:ClearAllPoints()
	bar:SetPoint("TOPLEFT", _G["GameTooltipTextLeft3"], "TOPLEFT", 0, -4)
	bar:Show()
	GameTooltip:Show()
end

EventUtil.ContinueOnAddOnLoaded("Blizzard_Professions", function()
	EventRegistry:RegisterCallback("Professions.RecipeListOnEnter", OnRecipeEnter, {})
end)
