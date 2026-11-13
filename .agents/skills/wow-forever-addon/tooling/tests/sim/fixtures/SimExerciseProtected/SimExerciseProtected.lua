-- A fixture whose button opens the world map: allowed out of combat, refused in combat (the pin's nocombat class).
function SimExerciseProtectedOpen()
	C_Map.OpenWorldMap(1454)
end

local button = CreateFrame("Button", "SimExerciseProtectedButton", UIParent)
button:SetSize(100, 20)
button:SetPoint("CENTER")
button:SetScript("OnClick", SimExerciseProtectedOpen)
