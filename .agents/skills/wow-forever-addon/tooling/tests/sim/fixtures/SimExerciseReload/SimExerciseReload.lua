-- A fixture that reloads the UI from its login handler: the client needs a hardware event for it.
function SimExerciseReloadNow()
	C_UI.Reload()
end

local frame = CreateFrame("Frame")
frame:RegisterEvent("PLAYER_ENTERING_WORLD")
frame:SetScript("OnEvent", SimExerciseReloadNow)
