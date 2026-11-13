-- A fixture whose TOC depends on ForeverCore: the runner has to load the checkout FOREVER_CORE names, or this file
-- stops with ForeverRequire's guard and the exercise would click nothing. With core loaded, its button opens the world
-- map, which combat refuses, so the run fails for the addon's own call.
if not ForeverCore then
	error("ForeverCore was not registered before the dependent addon")
end

local button = CreateFrame("Button", "SimExerciseCoreButton", UIParent)
button:SetSize(100, 20)
button:SetPoint("CENTER")
button:SetScript("OnClick", function()
	C_Map.OpenWorldMap(1454)
end)
