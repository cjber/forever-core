-- luacheck: ignore
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	for _ in ContainerFrame1:EnumerateValidItems() do
		break
	end
end)
