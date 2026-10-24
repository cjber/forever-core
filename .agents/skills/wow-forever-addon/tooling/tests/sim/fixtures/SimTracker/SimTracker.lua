-- Fixture: a tracker column at the native tracker's place, optionally moved clear of Questie's quest list, and a
-- saved setting a broken saved state can leave unset.
local column = CreateFrame("Frame", "SimTrackerColumn", UIParent)
column:SetSize(240, 200)
column:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -80, -260)

local function Place()
	local list = rawget(_G, "Questie_BaseFrame")
	column:ClearAllPoints()
	if SimTrackerDB.avoidQuestie and list and list:IsShown() then
		column:SetPoint("TOPRIGHT", list, "TOPLEFT", -8, 0)
	else
		column:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -80, -260)
	end
end

local events = CreateFrame("Frame")
events:RegisterEvent("ADDON_LOADED")
events:RegisterEvent("PLAYER_ENTERING_WORLD")
events:SetScript("OnEvent", function(_, event, name)
	if event == "ADDON_LOADED" and name == "SimTracker" then
		SimTrackerDB = SimTrackerDB or { avoidQuestie = true }
		-- A saved state from an older version has no route table; the column must still draw.
		SimTrackerDB.route = SimTrackerDB.route or {}
	elseif event == "PLAYER_ENTERING_WORLD" then
		C_Timer.After(5, Place)
	end
end)
