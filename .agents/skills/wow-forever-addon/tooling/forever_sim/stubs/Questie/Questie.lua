-- luacheck: globals Questie, read globals FOREVER_SIM_STUBS CreateFrame UIParent ObjectiveTrackerFrame C_Timer
-- A stand-in for Questie as the Forever addons see it, written for forever_sim from Questie's public behaviour
-- (no Questie code): the Questie global, and the tracker's quest list Questie_BaseFrame, a MEDIUM strata frame on
-- UIParent built a few seconds after login at the native tracker's place, with the native tracker hidden.
-- FOREVER_SIM_STUBS.Questie may set: trackerEnabled (default true), width, height, delay (seconds).
local options = (FOREVER_SIM_STUBS and FOREVER_SIM_STUBS.Questie) or {}

Questie = { API = { isReady = false }, db = { profile = { trackerEnabled = options.trackerEnabled ~= false } } }

local function BuildTracker()
	if not Questie.db.profile.trackerEnabled then
		return
	end
	local base = CreateFrame("Frame", "Questie_BaseFrame", UIParent)
	base:SetFrameStrata("MEDIUM")
	base:SetSize(options.width or 280, options.height or 320)
	local point, relativeTo, relativePoint, x, y
	if ObjectiveTrackerFrame and ObjectiveTrackerFrame:GetNumPoints() > 0 then
		point, relativeTo, relativePoint, x, y = ObjectiveTrackerFrame:GetPoint()
	end
	base:SetPoint(point or "TOPRIGHT", relativeTo or UIParent, relativePoint or "TOPRIGHT", x or -80, y or -260)
	if ObjectiveTrackerFrame then
		ObjectiveTrackerFrame:Hide()
	end
	base:Show()
end

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_ENTERING_WORLD")
events:SetScript("OnEvent", function(self)
	self:UnregisterAllEvents()
	C_Timer.After(options.delay or 3, function()
		BuildTracker()
		Questie.API.isReady = true
	end)
end)
