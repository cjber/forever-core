-- luacheck: read globals scenario ADDON
-- Issue #608: the Forever quest list used to take the game's own Quests and Campaign modules out of the client's
-- objective tracker. That wrote the container's dirty flag and module list from addon code, so the client's next
-- layout ran tainted and Blizzard_ScenarioObjectiveTracker's aura read for the Maw buffs raised "Auras cannot be
-- accessed when secret while tainted by 'ForeverCore'". The list now leaves the client's own modules alone, so the
-- aura read stays secure with the list on, and after the list is turned off and on again.
local function ExpectAuraReadIsUntainted(sim, reads, before)
	assert(reads > before, "the client's scenario tracker reached the aura reader")
	sim:expectNoErrors(ADDON)
end

scenario("the Forever quest list leaves the native scenario tracker's aura read untainted", function(sim)
	local reads = 0
	sim.impl["C_UnitAuras.GetAuraDataByIndex"] = function()
		reads = reads + 1
		assert(sim.taint.current == nil, "aura reader tainted by " .. tostring(sim.taint.current))
		return nil
	end
	-- The client places the native tracker in its Edit Mode slot; the sim's managed-frame layout leaves it unplaced
	-- until a UI addon or Edit Mode does, so give it the slot and the height its own modules lay their blocks out in.
	sim.G.ObjectiveTrackerFrame:SetPoint("TOPRIGHT", sim.G.UIParent, "TOPRIGHT", 0, -100)
	sim.G.ObjectiveTrackerFrame:SetHeight(400)

	sim:login({ savedVariables = { ForeverCoreDB = { questList = true } } })
	sim:advance(0.5)
	-- A scenario update makes the client's own scenario module lay out, which reaches the Maw buff check. With the
	-- list on, nothing the list did may have tainted that pass.
	local before = reads
	sim:event("QUEST_LOG_UPDATE")
	sim:event("SCENARIO_CRITERIA_UPDATE")
	sim:advance(0.5)
	ExpectAuraReadIsUntainted(sim, reads, before)

	-- Turning the list off and on again through the public slash command leaves the client's tracker alone too.
	before = reads
	sim:slash("/fcore quests")
	sim:advance(0.5)
	sim:event("QUEST_LOG_UPDATE")
	sim:event("SCENARIO_CRITERIA_UPDATE")
	sim:advance(0.5)
	ExpectAuraReadIsUntainted(sim, reads, before)

	before = reads
	sim:slash("/fcore quests")
	sim:advance(0.5)
	sim:event("QUEST_LOG_UPDATE")
	sim:event("SCENARIO_CRITERIA_UPDATE")
	sim:advance(0.5)
	ExpectAuraReadIsUntainted(sim, reads, before)
end)
