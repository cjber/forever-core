-- luacheck: ignore
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	WorldMapFrame:SetMaskTexture(WorldMapFrame:CreateTexture())
	WorldMapFrame:AddMaskableTexture(WorldMapFrame:CreateTexture())
end)
