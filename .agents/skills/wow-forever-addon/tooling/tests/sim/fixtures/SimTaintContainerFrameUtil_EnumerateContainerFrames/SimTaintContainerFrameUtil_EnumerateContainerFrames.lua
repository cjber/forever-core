-- luacheck: ignore
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function()
	for _ in ContainerFrameUtil_EnumerateContainerFrames() do
		break
	end
end)
