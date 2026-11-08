-- Dev addon for tools/headless/forever_client.py. The launcher links this folder into AddOns only for its own session
-- and removes it on stop, so a player's login never loads it.
-- Each time the world loads (login and every /reload) it closes any chat box the launcher's Enter key opened, then
-- calls Screenshot(): the file appears in Screenshots/ at once, and that is the launcher's sign the world is up.
local frame = CreateFrame("Frame")
frame:RegisterEvent("PLAYER_ENTERING_WORLD")
frame:SetScript("OnEvent", function()
	C_Timer.After(2, function()
		local box = ChatEdit_GetActiveWindow and ChatEdit_GetActiveWindow()
		if box then
			ChatEdit_DeactivateChat(box)
		end
		Screenshot()
	end)
end)
