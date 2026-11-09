-- luacheck: read globals scenario ADDON
scenario("the Forever quest list groups, sorts and collapses the game's quests", function(sim)
	local Enum = sim.G.Enum
	local NORMAL = Enum.QuestClassification.Normal
	local entries = {}
	local byID = {}

	local function add(entry)
		entries[#entries + 1] = entry
		if entry.questID then
			byID[entry.questID] = entry
		end
	end

	local function header(title)
		return {
			title = title,
			questLogIndex = #entries + 1,
			questID = 0,
			isHeader = true,
			useMinimalHeader = false,
			sortAsNormalQuest = false,
			isCollapsed = false,
			startEvent = false,
			isTask = false,
			isBounty = false,
			isStory = false,
			isScaling = false,
			isOnMap = true,
			hasLocalPOI = false,
			isHidden = false,
			isAutoComplete = false,
			overridesSortOrder = false,
			readyForTranslation = true,
			isInternalOnly = false,
			isAbandonOnDisable = false,
			level = 0,
			difficultyLevel = 0,
			suggestedGroup = 0,
			questClassification = NORMAL,
		}
	end

	local function quest(questID, title, onMap)
		return {
			title = title,
			questLogIndex = #entries + 1,
			questID = questID,
			isHeader = false,
			useMinimalHeader = false,
			sortAsNormalQuest = false,
			isCollapsed = false,
			startEvent = false,
			isTask = false,
			isBounty = false,
			isStory = false,
			isScaling = false,
			isOnMap = onMap,
			hasLocalPOI = false,
			isHidden = false,
			isAutoComplete = false,
			overridesSortOrder = false,
			readyForTranslation = true,
			isInternalOnly = false,
			isAbandonOnDisable = false,
			level = 10,
			difficultyLevel = 10,
			suggestedGroup = 0,
			questClassification = NORMAL,
		}
	end

	-- Three watched quests in two zones: one ready in Durotar, one current in Durotar, one in The Barrens.
	add(header("Durotar"))
	add(quest(101, "Ready One", false))
	add(quest(102, "Current One", true))
	add(header("The Barrens"))
	add(quest(103, "Other One", false))

	local watches = { 101, 102, 103 }
	local distances = { [101] = 400, [102] = 900, [103] = 100 }
	local ready = { [101] = true }
	local superTracked = 0

	sim.impl["C_QuestLog.GetNumQuestLogEntries"] = function()
		return #entries, #watches
	end
	sim.impl["C_QuestLog.GetInfo"] = function(index)
		return entries[index]
	end
	sim.impl["C_QuestLog.GetLogIndexForQuestID"] = function(questID)
		local entry = byID[questID]
		return entry and entry.questLogIndex
	end
	sim.impl["C_QuestLog.GetQuestIDForLogIndex"] = function(index)
		for _, entry in ipairs(entries) do
			if entry.questLogIndex == index then
				return entry.questID
			end
		end
	end
	sim.impl["C_QuestLog.GetNumQuestWatches"] = function()
		return #watches
	end
	sim.impl["C_QuestLog.GetQuestIDForQuestWatchIndex"] = function(index)
		return watches[index]
	end
	sim.impl["C_QuestLog.IsComplete"] = function(questID)
		return ready[questID] == true
	end
	sim.impl["C_QuestLog.ReadyForTurnIn"] = function(questID)
		return ready[questID] == true
	end
	sim.impl["C_QuestLog.IsFailed"] = function()
		return false
	end
	sim.impl["C_QuestLog.IsQuestDisabledForSession"] = function()
		return false
	end
	sim.impl["C_QuestLog.GetDistanceSqToQuest"] = function(questID)
		return distances[questID], true
	end
	sim.impl["C_QuestLog.GetTitleForQuestID"] = function(questID)
		local entry = byID[questID]
		return entry and entry.title
	end
	sim.impl["C_QuestLog.GetQuestDifficultyLevel"] = function()
		return 10
	end
	sim.impl["C_QuestLog.IsEliteQuest"] = function()
		return false
	end
	sim.impl["C_QuestLog.GetQuestTagInfo"] = function()
		return nil
	end
	sim.impl["C_QuestLog.GetNextWaypointText"] = function()
		return nil
	end
	sim.impl["C_QuestInfoSystem.GetQuestClassification"] = function()
		return NORMAL
	end
	sim.impl["C_SuperTrack.GetSuperTrackedQuestID"] = function()
		return superTracked
	end
	sim.impl["C_SuperTrack.SetSuperTrackedQuestID"] = function(questID)
		superTracked = questID
	end
	-- The client places the native tracker in its Edit Mode slot; the sim's managed-frame layout leaves it unplaced
	-- until a UI addon or Edit Mode does, so give it the slot and the height the host reads and the game's own
	-- modules lay their blocks out in.
	sim.G.ObjectiveTrackerFrame:SetPoint("TOPRIGHT", sim.G.UIParent, "TOPRIGHT", 0, -100)
	sim.G.ObjectiveTrackerFrame:SetHeight(400)

	sim:login({ savedVariables = { ForeverCoreDB = { questList = true } } })
	sim:advance(0.5)

	local section = sim.G.ForeverCoreQuestTracker
	assert(section ~= nil, "the Forever quest section exists")

	local function Blocks()
		local out = {}
		local block = section.firstBlock
		while block do
			out[#out + 1] = { id = block.id, text = block.HeaderText:GetText() }
			block = block.nextBlock
		end
		return out
	end

	local function Text(blocks)
		local out = {}
		for index, block in ipairs(blocks) do
			out[index] = tostring(block.id) .. "=" .. tostring(block.text)
		end
		return table.concat(out, "|")
	end

	local function ProtectedActions()
		local raised = {}
		for _, action in ipairs(sim.actions) do
			if action.event == "ADDON_ACTION_BLOCKED" or action.event == "ADDON_ACTION_FORBIDDEN" then
				raised[#raised + 1] = action.event .. " " .. tostring(action.func)
			end
		end
		return raised
	end

	local function ExpectNoProtectedActions()
		local raised = ProtectedActions()
		assert(#raised == 0, "no ADDON_ACTION_BLOCKED or ADDON_ACTION_FORBIDDEN, got " .. table.concat(raised, ", "))
	end

	local blocks = Blocks()
	assert(#blocks == 6, "six blocks: three group titles and three quests, got " .. Text(blocks))
	assert(blocks[1].text == "Ready to turn in", "ready group first, got " .. tostring(blocks[1].text))
	assert(blocks[2].id == 101 and blocks[2].text:find("Ready One", 1, true), "the ready quest follows")
	assert(blocks[2].text:find("(20 yd)", 1, true), "the ready quest shows its distance")
	assert(blocks[3].text == "Durotar", "the current zone follows, got " .. tostring(blocks[3].text))
	assert(blocks[4].id == 102 and blocks[4].text:find("Current One", 1, true), "the current zone quest follows")
	assert(blocks[4].text:find("(30 yd)", 1, true), "the current zone quest shows its distance")
	assert(blocks[5].text == "The Barrens", "the other zone follows, got " .. tostring(blocks[5].text))
	assert(blocks[6].id == 103 and blocks[6].text:find("Other One", 1, true), "the other zone quest follows")
	assert(blocks[6].text:find("(10 yd)", 1, true), "the other zone quest shows its distance")

	assert(sim.G.QuestObjectiveTracker:IsCollapsed() == true, "the game's quest module is collapsed")
	assert(sim.G.CampaignQuestObjectiveTracker:IsCollapsed() == true, "the game's campaign module is collapsed")

	local questBlock
	for _, block in pairs(section.usedBlocks["ObjectiveTrackerQuestPOIBlockTemplate"] or {}) do
		if block.id == 102 then
			questBlock = block
		end
	end
	assert(questBlock ~= nil and questBlock.HeaderButton ~= nil, "the current zone quest has its header button")
	sim:click(questBlock.HeaderButton, "LeftButton")
	assert(superTracked == 102, "left-click super-tracks the quest")

	local settled = Text(Blocks())
	-- The section's own OnEvent, not the game's: if Mixin copies before OnEvent is defined, the section keeps
	-- QuestObjectiveTrackerMixin:OnEvent, which only marks the module dirty. Another tracker taking the list makes
	-- our OnEvent run apply(), which expands the game's modules and empties the Forever list; the game's does not.
	sim.loader.loaded["!KalielsTracker"] = {}
	sim:event("PLAYER_ENTERING_WORLD")
	sim:advance(0.2)
	assert(sim.G.QuestObjectiveTracker:IsCollapsed() == false, "the section's own OnEvent applies the new owner")
	assert(#Blocks() == 0, "and empties the Forever list when another tracker owns it")
	sim.loader.loaded["!KalielsTracker"] = nil
	sim:event("PLAYER_ENTERING_WORLD")
	sim:advance(0.2)
	assert(sim.G.QuestObjectiveTracker:IsCollapsed() == true, "giving the list back collapses the quest module again")
	assert(Text(Blocks()) == settled, "and rebuilds the Forever list")

	sim:enterCombat()
	sim:advance(0.2)
	assert(Text(Blocks()) == settled, "combat holds the list's layout")
	sim:leaveCombat()
	sim:advance(0.2)
	assert(Text(Blocks()) == settled, "leaving combat lays the list out again")

	sim:slash("/fcore quests")
	sim:advance(0.2)
	assert(sim.G.QuestObjectiveTracker:IsCollapsed() == false, "turning the list off expands the quest module")
	assert(sim.G.CampaignQuestObjectiveTracker:IsCollapsed() == false, "and the campaign module")
	assert(#Blocks() == 0, "and empties the Forever list")
	-- The taint check for the collapse: the game's own tracker builds its secure quest item button while the list is
	-- off, in combat, and again with the list on and the game's modules collapsed by it.
	sim.impl["GetQuestLogSpecialItemInfo"] = function(questLogIndex)
		if questLogIndex == 3 then
			return "item:5512", 5512, 1, true
		end
	end

	local function CombatQuestRefresh()
		sim:enterCombat()
		sim:event("QUEST_LOG_UPDATE")
		sim:event("QUEST_WATCH_UPDATE", 102)
		sim:advance(1)
		sim:expectNoErrors(ADDON)
		ExpectNoProtectedActions()
		sim:leaveCombat()
		sim:advance(0.2)
	end

	CombatQuestRefresh()
	local itemButton
	for _, frame in pairs(sim.G.QuestObjectiveTracker.usedRightEdgeFrames or {}) do
		if frame.charges == 1 then
			itemButton = frame
		end
	end
	assert(itemButton ~= nil, "the game's tracker built its secure quest item button")
	sim:slash("/fcore quests")
	sim:advance(0.2)
	assert(sim.G.QuestObjectiveTracker:IsCollapsed() == true, "turning the list on collapses the quest module again")
	CombatQuestRefresh()
	sim:slash("/fcore quests")
	sim:advance(0.2)
	assert(sim.G.QuestObjectiveTracker:IsCollapsed() == false, "turning the list off again expands the quest module")

	sim:setGamepad(true)
	sim:gamepadNavigate()
	sim:expectNoErrors(ADDON)
	sim:expectNoGamepadTaint(ADDON)
end)
