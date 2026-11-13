-- A fixture that would fail the automatic exercise; its own exercise scenario allows the error, so the run passing
-- proves the runner used that declared exercise and did not also run its own.
function SimExerciseOptionsOpen()
	C_Map.OpenWorldMap(1454)
end

local button = CreateFrame("Button", "SimExerciseOptionsButton", UIParent)
button:SetSize(100, 20)
button:SetPoint("CENTER")
button:SetScript("OnClick", SimExerciseOptionsOpen)
