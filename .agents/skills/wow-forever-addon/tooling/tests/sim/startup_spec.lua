-- No-addon startup and settings parity against the pinned client UI and data.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")

local function eq(actual, expected)
	assert(actual == expected, string.format("expected %s, got %s", tostring(expected), tostring(actual)))
end

for _, gamepad in ipairs({ false, true }) do
	local sim = Sim.new()
	sim:expectNoErrors()
	sim:login()
	sim:expectNoErrors()
	sim:setGamepad(gamepad)
	sim:expectNoErrors()
	local G = sim.G
	sim:input(function()
		G.ShowUIPanel(G.SettingsPanel)
	end)
	eq(G.SettingsPanel:IsShown(), true)
	sim:input(function()
		G.SettingsPanel:Close()
	end)
	sim:advance(0.1)
	eq(G.SettingsPanel:IsShown(), false)
	sim:expectNoErrors()
end

local sim = Sim.new()
local G = sim.G
-- The pinned SpellFlyout and SpellFlyoutItem tables define Warrior stances even before any are learned.
local name, description, count, known = G.GetFlyoutInfo(269)
eq(name, "Stances")
eq(type(description), "string")
eq(count, 3)
eq(known, false)
local spellID, overrideSpellID, slotKnown = G.GetFlyoutSlotInfo(269, 1)
eq(spellID, 2457)
eq(overrideSpellID, 2457)
eq(slotKnown, false)
sim.world.spells[2457] = { name = "Battle Stance" }
local _, _, _, cached = G.GetFlyoutInfo(269)
eq(cached, false)
sim.world.knownSpells[2457] = true
local _, _, _, learned = G.GetFlyoutInfo(269)
eq(learned, true)
local _, _, learnedSlot, spellName = G.GetFlyoutSlotInfo(269, 1)
eq(learnedSlot, true)
eq(spellName, "Battle Stance")
eq(G.GetFlyoutInfo(-1), nil)
eq(G.GetFlyoutSlotInfo(269, 0), nil)
eq(G.GetFlyoutSlotInfo(269, count + 1), nil)
eq(G.GetFlyoutSlotInfo(-1, 1), nil)
sim:expectNoErrors()
-- QUEST_ACCEPTED must reach the real top-banner manager rather than its falsey API fallback.
assert(G.TopBannerMgr, "default startup loads the native top-banner manager")
sim.impl["C_QuestLog.IsQuestTask"] = function(id)
	return id == 608001
end
sim.impl["C_QuestLog.GetTitleForQuestID"] = function(id)
	return id == 608001 and "Bonus banner startup fixture" or nil
end
sim:login()
sim:event("QUEST_ACCEPTED", 608001)
sim:advance(0.1)
eq(G.ObjectiveTrackerTopBannerFrame:GetQuestID(), 608001)
eq(G.TopBannerMgr.currentBanner.frame, G.ObjectiveTrackerTopBannerFrame)
sim:expectNoErrors()
eq(G.ObjectiveTrackerTopBannerFrame:IsShown(), true)
print("startup_spec: bare boot, login and SettingsPanel pass with mouse and gamepad; native flyout metadata passes")
