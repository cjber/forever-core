-- A fixture with nothing wrong: one button the exercise has to click, whose click does harmless work.
local button = CreateFrame("Button", "SimExerciseCleanButton", UIParent)
button:SetSize(100, 20)
button:SetPoint("CENTER")
button:SetScript("OnClick", function(self)
	self.clicks = (self.clicks or 0) + 1
end)
