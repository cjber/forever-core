-- Fixture: draws on the world map through Blizzard's data provider and pin pools, which writes into the map's own
-- tables from addon code (gamepad-interface taint).
local provider = CreateFromMixins(MapCanvasDataProviderMixin)
function provider:RefreshAllData()
	self:GetMap():RemoveAllPinsByTemplate("SimMapProviderPinTemplate")
end

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	WorldMapFrame:AddDataProvider(provider)
end)
