-- luacheck: read globals scenario ADDON
-- The quest list's blocks are pooled frames laid out by Blizzard's own ObjectiveTrackerModuleMixin, which anchors each
-- block to the one before it and refuses a block anchored under a block that already depends on it (#521, #609). These
-- scenarios run the real mixin, so an anchor cycle is the client's own SetPoint failure, not a shape this file guesses
-- at: a repeated watch is one block, and a zone split across on-map and off-map quests is one heading.

---@param sim any
---@return table
local function QuestFixture(sim)
	local Enum = sim.G.Enum
	local NORMAL = Enum.QuestClassification.Normal
	local entries, byID = {}, {}
	local watches, distances, ready = {}, {}, {}

	local function add(entry)
		entries[#entries + 1] = entry
		if entry.questID and entry.questID ~= 0 then
			byID[entry.questID] = entry
		end
	end
	local function header(title)
		add({
			title = title,
			questLogIndex = #entries + 1,
			questID = 0,
			isHeader = true,
			isOnMap = true,
			hasLocalPOI = false,
			level = 0,
			questClassification = NORMAL,
		})
	end
	local function quest(questID, title, onMap)
		add({
			title = title,
			questLogIndex = #entries + 1,
			questID = questID,
			isHeader = false,
			isOnMap = onMap == true,
			hasLocalPOI = false,
			level = 10,
			questClassification = NORMAL,
		})
		distances[questID] = questID * 10
		return questID
	end

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
		return distances[questID]
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
	sim.impl["C_QuestLog.GetQuestObjectives"] = function()
		return {}
	end
	sim.impl["C_QuestInfoSystem.GetQuestClassification"] = function()
		return NORMAL
	end
	sim.impl["GetNumQuestLeaderBoards"] = function()
		return 0
	end
	sim.impl["C_SuperTrack.GetSuperTrackedQuestID"] = function()
		return 0
	end
	sim.impl["C_SuperTrack.SetSuperTrackedQuestID"] = function() end
	sim.G.GetQuestProgressBarPercent = function()
		return 50
	end
	sim.G.GetQuestLogSpecialItemInfo = function()
		return nil
	end
	sim.G.ObjectiveTrackerFrame:SetPoint("TOPRIGHT", sim.G.UIParent, "TOPRIGHT", 0, -100)
	sim.G.ObjectiveTrackerFrame:SetHeight(400)

	return {
		header = header,
		quest = quest,
		watches = watches,
		distances = distances,
	}
end

---@param sim any
---@return table
local function Core(sim)
	return assert(sim.G.ForeverCore, "ForeverCore is loaded").Register("ForeverCore")
end

-- The errors this session caught, as messages. A section's layout runs under the host's SafeCall, so a client
-- SetPoint refusal lands in core's journal instead of the scenario's top level.
---@param sim any
---@return string[]
local function Caught(sim)
	local messages = {}
	for _, entry in ipairs(Core(sim).CaughtErrors()) do
		if entry.fromSession then
			messages[#messages + 1] = tostring(entry.message)
		end
	end
	return messages
end

---@param sim any
---@param label string
local function ExpectQuiet(sim, label)
	local caught = Caught(sim)
	assert(#caught == 0, label .. ": " .. table.concat(caught, " | "))
end

---@param section any
---@return any[]
local function Blocks(section)
	local out = {}
	local block = section.firstBlock
	while block do
		out[#out + 1] = block
		block = block.nextBlock
	end
	return out
end

---@param section any
---@param id any
---@return any?
local function Block(section, id)
	for _, blocks in pairs(section.usedBlocks or {}) do
		if blocks[id] ~= nil then
			return blocks[id]
		end
	end
end

-- Every block the pass laid, by id, with a check that no frame appears twice: a frame anchored twice in one pass is
-- what makes the client's anchor chain a ring.
---@param section any
---@return any[]
local function Layout(section)
	local blocks = Blocks(section)
	local seen, ids = {}, {}
	for _, block in ipairs(blocks) do
		assert(seen[block] == nil, "one block frame was laid out twice in a pass")
		seen[block] = true
		ids[#ids + 1] = block.id
	end
	return ids
end

-- The client's watch list can repeat a quest ID. The watch API answers by index, so the same quest is read twice, and
-- the section used to ask for that quest's block twice in one layout pass: Blizzard anchors a block to the block
-- before it, the second look anchored the block under itself, and the client answered
-- "Cannot anchor to a region dependent on it" while the tracker laid itself out (#609).
scenario("the Forever quest list draws a repeated watch once", function(sim)
	local fixture = QuestFixture(sim)
	fixture.header("Durotar")
	local first = fixture.quest(101, "First", true)
	local second = fixture.quest(102, "Second", true)
	local third = fixture.quest(103, "Third", false)
	fixture.watches[1], fixture.watches[2], fixture.watches[3] = first, second, third
	-- The same quest twice in the watch list, as a client can hand it back.
	fixture.watches[4] = second

	sim:login({ savedVariables = { ForeverCoreDB = { questList = true } } })
	sim:advance(0.5)

	local section = assert(sim.G.ForeverCoreQuestTracker, "the Forever quest section exists")
	ExpectQuiet(sim, "a repeated watch lays out once")
	local ids = Layout(section)
	assert(#ids == 4, "one group heading and one block per unique quest")
	assert(Block(section, second) ~= nil, "the repeated quest keeps its block")
	assert(section.Header.Text:GetText() == "Quests 3/3", "the header counts the unique watched quests")

	-- A later pass lays the same list out again, still once per quest.
	sim:event("QUEST_LOG_UPDATE")
	sim:advance(0.5)
	ExpectQuiet(sim, "a repeated watch stays one block across passes")
	assert(#Layout(section) == 4, "the later pass keeps one block per unique quest")

	sim:setGamepad(true)
	sim:gamepadNavigate()
	sim:expectNoErrors(ADDON)
	sim:expectNoGamepadTaint(ADDON)
end)

-- The current zone is titled by its quest log heading, and its on-map quests were grouped apart from the rest of the
-- zone. Both carried the same heading, so the section laid one block out twice in a pass, the second time under a
-- block that already depended on it (#521). One title now names one group.
scenario("the Forever quest list keeps one heading per zone", function(sim)
	local fixture = QuestFixture(sim)
	fixture.header("Durotar")
	local onMap = fixture.quest(201, "On the map", true)
	local offMap = fixture.quest(202, "Off the map", false)
	local other = fixture.quest(203, "Also off the map", false)
	fixture.header("Mulgore")
	local far = fixture.quest(204, "Far away", false)
	fixture.watches[1], fixture.watches[2] = onMap, offMap
	fixture.watches[3], fixture.watches[4] = other, far

	sim:login({ savedVariables = { ForeverCoreDB = { questList = true } } })
	sim:advance(0.5)

	local section = assert(sim.G.ForeverCoreQuestTracker, "the Forever quest section exists")
	ExpectQuiet(sim, "one heading per zone lays out once")
	local ids = Layout(section)
	assert(#ids == 6, "two zone headings and one block per quest")
	assert(ids[1] == "group:Durotar", "the current zone heading comes first")
	assert(ids[5] == "group:Mulgore", "the other zone heading follows its quests")
	assert(ids[6] == far, "with the Mulgore quest under it")
	local headings = 0
	for _, id in ipairs(ids) do
		if id == "group:Durotar" then
			headings = headings + 1
		end
	end
	assert(headings == 1, "the current zone draws one heading, not one per group")

	-- Reordering by distance keeps one heading for the zone and no cycle.
	fixture.distances[onMap], fixture.distances[offMap], fixture.distances[other] = 800, 100, 400
	fixture.distances[far] = 50
	sim:event("QUEST_LOG_UPDATE")
	sim:advance(0.5)
	assert(#Layout(section) == 6, "a distance change keeps one heading per zone")
	ExpectQuiet(sim, "a distance change keeps the anchor chain acyclic")

	sim:setGamepad(true)
	sim:gamepadNavigate()
	sim:expectNoErrors(ADDON)
	sim:expectNoGamepadTaint(ADDON)
end)
