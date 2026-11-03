-- Fixture for the combat transition boundary: PLAYER_REGEN_DISABLED fires before lockdown,
-- while loss-of-control data remains readable for the player but not for other units.
-- luacheck: globals UnitAffectingCombat InCombatLockdown C_LossOfControl
SimCombatResults = {}

local function onCombatStart()
	SimCombatResults.affectingCombat = UnitAffectingCombat("player")
	SimCombatResults.lockdown = InCombatLockdown()
	SimCombatResults.playerLossOfControl = C_LossOfControl.GetActiveLossOfControlDataByUnit("player", 1)
	SimCombatResults.otherLossOfControl = C_LossOfControl.GetActiveLossOfControlDataByUnit("target", 1)
end

local frame = CreateFrame("Frame")
frame:RegisterEvent("PLAYER_REGEN_DISABLED")
frame:SetScript("OnEvent", onCombatStart)
