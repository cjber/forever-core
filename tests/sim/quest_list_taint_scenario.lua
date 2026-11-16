-- luacheck: read globals scenario ADDON
-- Issue #608: the Forever quest list used to take the game's own Quests and Campaign modules out of the client's
-- objective tracker. That wrote the container's dirty flag and module list from addon code, so the client's next
-- layout ran tainted and Blizzard_ScenarioObjectiveTracker's aura read for the Maw buffs raised "Auras cannot be
-- accessed when secret while tainted by 'ForeverCore'". The list now leaves the client's own modules alone, so the
-- whole native frame is hidden without changing its modules, and its aura reads stay secure across visibility changes.
local function ExpectAuraReadIsUntainted(sim, reads, before)
	assert(reads > before, "the client's scenario tracker reached the aura reader")
	sim:expectNoErrors(ADDON)
end

scenario("the Forever quest list leaves the native scenario tracker's aura read untainted", function(sim)
	-- Keep one watched quest so Blizzard has content to show when suppression is released.
	local quest = {
		questID = 101,
		questLogIndex = 1,
		title = "Watched quest",
		level = 10,
		isHeader = false,
		isTask = false,
		isBounty = false,
		isHidden = false,
		questClassification = sim.G.Enum.QuestClassification.Normal,
	}
	sim.impl["C_QuestLog.GetNumQuestLogEntries"] = function()
		return 1, 1
	end
	sim.impl["C_QuestLog.GetInfo"] = function(index)
		return index == 1 and quest or nil
	end
	sim.impl["C_QuestLog.GetNumQuestWatches"] = function()
		return 1
	end
	sim.impl["C_QuestLog.GetQuestIDForQuestWatchIndex"] = function()
		return 101
	end
	sim.impl["C_QuestLog.GetLogIndexForQuestID"] = function()
		return 1
	end
	sim.impl["C_QuestLog.GetQuestIDForLogIndex"] = function()
		return 101
	end
	sim.impl["C_QuestLog.GetTitleForQuestID"] = function()
		return "Watched quest"
	end
	sim.impl["C_QuestLog.GetDistanceSqToQuest"] = function()
		return 400, true
	end
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
	local tracker = sim.G.ObjectiveTrackerFrame
	local function NativeUpdate()
		assert(sim.taint.current == nil, "native container update starts secure")
		tracker:Update()
	end
	local before = reads
	sim:event("QUEST_LOG_UPDATE")
	sim:event("SCENARIO_CRITERIA_UPDATE")
	NativeUpdate()
	sim:advance(0.5)
	ExpectAuraReadIsUntainted(sim, reads, before)
	assert(not tracker:IsShown(), "login with the Forever list hides the whole native tracker")

	-- Turning the list off and on changes only native frame visibility, leaving every module untouched.
	before = reads
	sim:slash("/fcore quests")
	assert(tracker:IsShown(), "turning the list off restores the native tracker")
	sim:advance(0.5)
	sim:event("QUEST_LOG_UPDATE")
	sim:event("SCENARIO_CRITERIA_UPDATE")
	NativeUpdate()
	sim:advance(0.5)
	ExpectAuraReadIsUntainted(sim, reads, before)

	before = reads
	sim:slash("/fcore quests")
	assert(not tracker:IsShown(), "turning the list on hides the native tracker")
	sim:advance(0.5)
	sim:event("QUEST_LOG_UPDATE")
	sim:event("SCENARIO_CRITERIA_UPDATE")
	NativeUpdate()
	sim:advance(0.5)
	ExpectAuraReadIsUntainted(sim, reads, before)
	tracker:Show()
	assert(not tracker:IsShown(), "a native OnShow attempt is hidden again")
	before = reads
	NativeUpdate()
	sim:advance(0.5)
	ExpectAuraReadIsUntainted(sim, reads, before)

	sim:enterCombat()
	sim:slash("/fcore quests")
	assert(not tracker:IsShown(), "restore requested in combat waits")
	sim:slash("/fcore quests")
	sim:leaveCombat()
	sim:advance(0.5)
	assert(not tracker:IsShown(), "combat retry keeps the latest enabled request")

	sim:enterCombat()
	sim:slash("/fcore quests")
	assert(not tracker:IsShown(), "second combat restore waits")
	sim:leaveCombat()
	sim:advance(0.5)
	assert(tracker:IsShown(), "latest disabled request restores after combat")
	before = reads
	NativeUpdate()
	sim:advance(0.5)
	ExpectAuraReadIsUntainted(sim, reads, before)
end)
