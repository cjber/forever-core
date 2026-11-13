-- A fixture whose button anchors a frame to its own child: the child is already anchored to the frame, so the
-- client refuses the cycle.
function SimExerciseAnchorCycle()
	local parent = CreateFrame("Frame", nil, UIParent)
	local child = CreateFrame("Frame", nil, parent)
	child:SetPoint("TOPLEFT", parent, "TOPLEFT", 0, 0)
	parent:SetPoint("TOPLEFT", child, "TOPLEFT", 0, 0)
end

local button = CreateFrame("Button", "SimExerciseAnchorButton", UIParent)
button:SetSize(100, 20)
button:SetPoint("CENTER")
button:SetScript("OnClick", SimExerciseAnchorCycle)
