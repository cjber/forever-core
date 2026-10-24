-- Fixture: draws on the world map with its own frame over the canvas, writing nothing into the map's tables.
local overlay
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	overlay = CreateFrame("Frame", nil, WorldMapFrame.ScrollContainer)
	overlay:SetAllPoints(WorldMapFrame.ScrollContainer)
	overlay:SetFrameLevel(WorldMapFrame.ScrollContainer:GetFrameLevel() + 10)
	local dot = overlay:CreateTexture(nil, "OVERLAY")
	dot:SetSize(8, 8)
	dot:SetPoint("CENTER")
end)
