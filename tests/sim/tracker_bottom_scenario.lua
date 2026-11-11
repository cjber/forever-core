-- luacheck: read globals scenario ADDON
-- The quests reach the bottom of the screen, so no Forever section fits below them. Laying the sections out below to
-- measure the room is not free: Blizzard's EndLayout hides a section that fits nothing and FreeUnusedBlocks releases
-- every block, so the pass above or beside the tracker replays each header's add animation and rebuilds every block.
-- Issue #438: a QUEST_LOG_UPDATE must not do that every time.
scenario("the tracker column moves aside once when the quests reach the bottom", function(sim)
	local G = sim.G
	local Enum = G.Enum
	local NORMAL = Enum.QuestClassification.Normal
	local entries, byID = {}, {}

	local function add(entry)
		entries[#entries + 1] = entry
		if entry.questID then
			byID[entry.questID] = entry
		end
	end

	local function quest(questID, title)
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
			isOnMap = true,
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

	-- Two watched quests fill the native tracker with its own content.
	add(quest(101, "One"))
	add(quest(102, "Two"))
	local watches = { 101, 102 }
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
	sim.impl["C_QuestLog.IsComplete"] = function()
		return false
	end
	sim.impl["C_QuestLog.ReadyForTurnIn"] = function()
		return false
	end
	sim.impl["C_QuestLog.IsFailed"] = function()
		return false
	end
	sim.impl["C_QuestLog.IsQuestDisabledForSession"] = function()
		return false
	end
	sim.impl["C_QuestLog.GetDistanceSqToQuest"] = function()
		return 400, true
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

	-- The client places the native tracker in its Edit Mode slot; the sim's managed-frame layout leaves it unplaced
	-- until a UI addon or Edit Mode does, so give it the slot and the height its modules lay their blocks out in.
	local tracker, ui = G.ObjectiveTrackerFrame, G.UIParent
	tracker:SetPoint("TOPRIGHT", ui, "TOPRIGHT", 0, -100)
	tracker:SetHeight(400)

	sim:login({ savedVariables = { ForeverCoreDB = {} } })
	sim:advance(0.5)

	-- Drop the native tracker until its own content ends at the screen's bottom: the room below it is then the 24 px
	-- layout margin and nothing else.
	assert(tracker:IsShown(), "the native tracker shows its quests")
	local slice = assert(tracker.NineSlice, "the native tracker has its content background")
	local offset = tracker:GetTop() - slice:GetBottom() - ui:GetHeight()
	tracker:ClearAllPoints()
	tracker:SetPoint("TOPRIGHT", ui, "TOPRIGHT", 0, offset)
	sim:event("QUEST_LOG_UPDATE")
	sim:advance(0.2)
	assert(
		slice:GetBottom() <= 24,
		"the native content ends at the screen's bottom, got " .. tostring(slice:GetBottom())
	)

	-- One section with Blizzard's own module mixin, so EndLayout does its real work: the header's add animation and
	-- FreeUnusedBlocks releasing the block.
	local section = G.CreateFrame("Frame", nil, ui, "ObjectiveTrackerModuleTemplate")
	section.uiOrder = -99
	function section:LayoutContents()
		local block = self:GetBlock("objective")
		block.height = 80
		self:LayoutBlock(block)
	end

	local animations = 0
	local restart = section.Header.AddAnim.Restart
	function section.Header.AddAnim:Restart(...)
		animations = animations + 1
		return restart(self, ...)
	end
	local releases = 0
	G.ForeverCore.TrackerHost.Attach(section)
	local freeBlock = section.FreeBlock
	function section.FreeBlock(self, block)
		releases = releases + 1
		return freeBlock(self, block)
	end
	sim:advance(0.2)

	local function Block()
		local blocks = section.usedBlocks and section.usedBlocks["ObjectiveTrackerBlockTemplate"]
		return blocks and blocks["objective"]
	end

	-- The one real move above or beside the tracker pays the replay once.
	assert(animations == 1, "the move aside plays the header's add animation once, got " .. animations)
	assert(Block() ~= nil, "the section drew its block")
	assert(releases == 0, "the first layout released no block, got " .. releases)
	local block = Block()

	local function ExpectKept(note)
		assert(animations == 1, note .. " replays no header animation, got " .. animations)
		assert(releases == 0, note .. " releases no block, got " .. releases)
		assert(Block() == block and block.used, note .. " keeps the section's block")
	end

	local function ExpectHeld(note)
		assert(slice:GetBottom() <= 24, note .. " still leaves no room below the native content")
		ExpectKept(note)
	end

	for update = 1, 3 do
		sim:event("QUEST_LOG_UPDATE")
		sim:advance(0.2)
		ExpectHeld("update " .. update)
	end

	sim:enterCombat()
	sim:event("QUEST_LOG_UPDATE")
	sim:advance(0.2)
	ExpectHeld("an update in combat")
	sim:leaveCombat()
	sim:event("QUEST_LOG_UPDATE")
	sim:advance(0.2)
	ExpectHeld("the update after combat")

	-- The quests leave room for the whole column below again: it moves back without a second layout pass.
	local roomBelow = slice:GetBottom()
	tracker:ClearAllPoints()
	tracker:SetPoint("TOPRIGHT", ui, "TOPRIGHT", 0, 0)
	sim:event("QUEST_LOG_UPDATE")
	sim:advance(0.2)
	assert(slice:GetBottom() > roomBelow, "the native quests shrank away from the bottom")
	ExpectKept("the move back below")
end)
