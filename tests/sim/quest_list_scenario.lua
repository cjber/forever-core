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
	sim.G.GetQuestProgressBarPercent = function()
		return 50
	end
	-- One quest with a count line and a finished line, and a quest item, so the thin progress fill and the item
	-- button have something real to draw.
	local objectives = {
		[102] = {
			{
				text = "1/5 Current Objective",
				type = "progressbar",
				finished = false,
				numFulfilled = 1,
				numRequired = 5,
			},
			{
				text = "2/2 Finished Objective",
				type = "progressbar",
				finished = true,
				numFulfilled = 2,
				numRequired = 2,
			},
		},
	}
	sim.impl["C_QuestLog.GetQuestObjectives"] = function(questID)
		return objectives[questID] or {}
	end
	-- Quest 103 reads like a count in its line text, but the client answers no objective record for it, so it must
	-- not draw a progress fill.
	local lines = {
		[102] = {
			{ text = "1/5 Current Objective", kind = "progressbar", finished = false },
			{ text = "2/2 Finished Objective", kind = "progressbar", finished = true },
		},
		[103] = {
			{ text = "3/5 Text Only", kind = "progressbar", finished = false },
		},
	}
	sim.impl["GetNumQuestLeaderBoards"] = function(questLogIndex)
		for questID, rows in pairs(lines) do
			if byID[questID] and byID[questID].questLogIndex == questLogIndex then
				return #rows
			end
		end
		return 0
	end
	sim.impl["GetQuestLogLeaderBoard"] = function(index, questLogIndex)
		for questID, rows in pairs(lines) do
			if byID[questID] and byID[questID].questLogIndex == questLogIndex then
				local row = rows[index]
				if row then
					return row.text, row.kind, row.finished
				end
			end
		end
	end
	sim.G.GetQuestLogSpecialItemInfo = function(questLogIndex)
		if byID[102] and byID[102].questLogIndex == questLogIndex then
			return "item:5512", 5512, 1, true
		end
	end
	-- Shortest Path's public API and the client's quest POI point, so the Objectives submenu has a real route to
	-- offer for the unfinished count.
	local routed
	sim.G.ShortestPathForever = {
		API = {
			Navigate = function(owner, map, x, y, title, kind)
				routed = { owner = owner, map = map, x = x, y = y, title = title, kind = kind }
				return true
			end,
		},
	}
	sim.impl["C_QuestLog.GetMapForQuestPOIs"] = function()
		return 1
	end
	sim.impl["C_QuestLog.GetQuestsOnMap"] = function()
		return { { questID = 102, mapID = 1, x = 0.5, y = 0.5 } }
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
	assert(section.trackerOverflow == false and section.scrollRange == 0, "a short list does not scroll")
	assert(section.scrollBar:IsShown() == false, "a short list shows no scrollbar")

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

	-- The game's own quest modules leave the client's tracker collection while the Forever list draws: a collapsed
	-- module still drew its own empty "Quests" header above this list's header, so they are taken out and asked to lay
	-- out in no room, and the client's own layout hides them. They come back when the list is off.
	local tracker = sim.G.ObjectiveTrackerFrame
	local function NativeDrawn()
		return tracker:HasModule(sim.G.QuestObjectiveTracker) and sim.G.QuestObjectiveTracker:IsShown()
	end
	assert(NativeDrawn() == false, "the game's quest module is not in the tracker and draws nothing")
	assert(
		tracker:HasModule(sim.G.CampaignQuestObjectiveTracker) == false,
		"the game's campaign module leaves the tracker too"
	)
	assert(
		sim.G.QuestObjectiveTracker.Header:IsVisible() == false,
		"the game's own Quests header is off screen, so only the Forever list's header shows"
	)
	assert(section.Header:IsVisible() == true, "the Forever list's own Quests header is the one that shows")

	local questBlock
	for _, block in pairs(section.usedBlocks["ObjectiveTrackerQuestPOIBlockTemplate"] or {}) do
		if block.id == 102 then
			questBlock = block
		end
	end
	assert(questBlock ~= nil and questBlock.HeaderButton ~= nil, "the current zone quest has its header button")
	sim:click(questBlock.HeaderButton, "LeftButton")
	assert(superTracked == 102, "left-click super-tracks the quest")

	-- Progress style B: one thin fill under the unfinished count, none under the finished line, and no full template
	-- progress bar.
	local thin = questBlock.thinBars and questBlock.thinBars[1]
	assert(thin ~= nil, "the unfinished count line has its thin fill")
	assert(math.abs(thin.fraction - 0.2) < 1e-9, "the thin fill carries 1/5")
	assert(questBlock.thinBars[2] == nil, "the finished line has no fill")
	assert(questBlock.thinBars[1]:GetParent() == questBlock, "the fill belongs to the quest block")
	assert(next(section.usedProgressBars or {}) == nil, "no full ObjectiveTrackerProgressBarTemplate was built")

	-- The quest item button comes from the fixed secure pool, sits on its quest and leaves the title room.
	assert(questBlock.hasItem == true, "the quest with a special item is marked for a button")
	assert(#section.itemButtons == 40, "the item pool is fixed at 40 frames")
	local itemButton = section.itemButtons[1]
	assert(itemButton:IsShown() and itemButton:GetParent() == questBlock, "the visible item quest has its button")
	assert(itemButton.questLogIndex == byID[102].questLogIndex, "the button holds the quest log index")
	-- It is the client's secure item action, not the plain tracker button whose OnClick calls the protected
	-- UseQuestLogSpecialItem from addon code.
	assert(itemButton:GetAttribute("type") == "item", "the button performs the secure item action")
	assert(itemButton:GetAttribute("item") == "item:5512", "the secure action is set from the quest item's link")
	assert(itemButton:GetAttribute("questLogIndex") == nil, "no script reads a quest log index attribute")
	assert(itemButton.icon and itemButton.icon:GetTexture() == 5512, "the client's item art draws the quest item")
	local usedItem
	sim.G.SecureCmdItemParse = function(item)
		return item
	end
	sim.G.SecureCmdUseItem = function(name)
		usedItem = name
	end
	-- The secure action then checks whether the spell is looking for a target item; the client answers both.
	sim.G.SpellCanTargetItem = function()
		return false
	end
	sim.G.SpellCanTargetItemID = function()
		return false
	end
	sim:click(itemButton)
	assert(usedItem == "item:5512", "clicking the button runs the secure item action")

	-- A line that reads like a count but has no objective record gets no fill at all.
	local textOnlyBlock
	for _, block in pairs(section.usedBlocks["ObjectiveTrackerQuestPOIBlockTemplate"] or {}) do
		if block.id == 103 then
			textOnlyBlock = block
		end
	end
	assert(textOnlyBlock ~= nil, "the text-only quest has a block")
	local textOnlyLine = textOnlyBlock:GetExistingLine(1)
	assert(textOnlyLine ~= nil and textOnlyLine.Text:GetText() == "3/5 Text Only", "the text-only count line is drawn")
	assert(
		textOnlyBlock.thinBars == nil or textOnlyBlock.thinBars[1] == nil,
		"a count with no objective record draws no progress fill"
	)

	-- The header carries the watched count out of the quests the log holds.
	assert(section.Header.Text:GetText() == "Quests 3/3", "the Quests header counts the tracked quests")

	-- Clicking a zone heading folds it, saves the fold for this character and puts the count on the heading.
	local zoneBlock
	for _, block in pairs(section.usedBlocks[section.blockTemplate] or {}) do
		if block.id == "group:Durotar" then
			zoneBlock = block
		end
	end
	assert(zoneBlock ~= nil and zoneBlock.HeaderButton ~= nil, "the zone heading has a header button")
	sim:click(zoneBlock.HeaderButton, "LeftButton")
	sim:advance(0.2)
	assert(zoneBlock.HeaderText:GetText() == "Durotar (1)", "a folded zone keeps its quest count")
	assert(questBlock:IsShown() == false or questBlock.used ~= true, "a folded zone hides its quests")
	local fold
	for _, value in pairs(sim:savedState().ForeverCoreDB.questListFold) do
		fold = value
	end
	assert(fold and fold.zones.Durotar == true, "the zone fold is saved for this character")
	sim:click(zoneBlock.HeaderButton, "LeftButton")
	sim:advance(0.2)
	assert(zoneBlock.HeaderText:GetText() == "Durotar", "clicking the heading again unfolds the zone")
	assert(questBlock.used == true, "the quest returns when its zone unfolds")

	-- The quest menu on the block header offers the Objectives submenu, and choosing one routes through Shortest
	-- Path's published API with the client's quest point.
	sim:click(questBlock.HeaderButton, "RightButton")
	local menu = sim.G.ForeverCoreContextMenu
	assert(menu ~= nil, "the quest menu opens")
	local objectivesRow
	for _, row in ipairs(menu.rows) do
		if row:GetText() == "Objectives" then
			objectivesRow = row
		end
	end
	assert(objectivesRow ~= nil, "the quest menu offers the Objectives submenu")
	sim:click(objectivesRow, "LeftButton")
	local route
	for _, row in ipairs(sim.G.ForeverCoreContextMenu.rows) do
		if row:GetText() == "1/5 Current Objective" then
			route = row
		end
	end
	assert(route ~= nil, "the submenu lists the unfinished objective")
	sim:click(route, "LeftButton")
	assert(routed and routed.owner == "ForeverCore" and routed.map == 1, "the objective routes through Shortest Path")
	assert(routed.x == 0.5 and routed.y == 0.5 and routed.kind == "objective", "the route uses the quest's map point")

	-- The menu folds one quest, and the same fold survives a layout.
	sim:click(questBlock.HeaderButton, "RightButton")
	menu = sim.G.ForeverCoreContextMenu
	local collapse
	for _, row in ipairs(menu.rows) do
		if row:GetText() == "Collapse" then
			collapse = row
		end
	end
	assert(collapse ~= nil, "the quest menu offers Collapse")
	sim:click(collapse, "LeftButton")
	sim:advance(0.2)
	assert(questBlock.used == true, "a folded quest keeps its title")
	assert(questBlock.thinBars[1] == nil, "a folded quest drops its objective lines")
	local character
	for _, value in pairs(sim:savedState().ForeverCoreDB.questListFold) do
		character = value
	end
	assert(character and character.quests[102] == true, "the quest fold is saved for this character")
	sim:click(questBlock.HeaderButton, "RightButton")
	menu = sim.G.ForeverCoreContextMenu
	local expand
	for _, row in ipairs(menu.rows) do
		if row:GetText() == "Expand" then
			expand = row
		end
	end
	assert(expand ~= nil, "the folded quest menu offers Expand")
	sim:click(expand, "LeftButton")
	sim:advance(0.2)
	assert(questBlock.thinBars[1] ~= nil, "expanding the quest draws its count line and fill again")

	local settled = Text(Blocks())
	-- The section's own OnEvent, not the game's: if Mixin copies before OnEvent is defined, the section keeps
	-- QuestObjectiveTrackerMixin:OnEvent, which only marks the module dirty. Another tracker taking the list makes
	-- our OnEvent run apply(), which gives the game's modules back and empties the Forever list; the game's does not.
	sim.loader.loaded["!KalielsTracker"] = {}
	sim:event("PLAYER_ENTERING_WORLD")
	sim:advance(0.2)
	assert(NativeDrawn() == true, "the section's own OnEvent gives the game's quest module back")
	assert(#Blocks() == 0, "and empties the Forever list when another tracker owns it")
	sim.loader.loaded["!KalielsTracker"] = nil
	sim:event("PLAYER_ENTERING_WORLD")
	sim:advance(0.2)
	assert(NativeDrawn() == false, "giving the list back takes the game's quest module out again")
	assert(Text(Blocks()) == settled, "and rebuilds the Forever list")

	sim:enterCombat()
	sim:advance(0.2)
	assert(Text(Blocks()) == settled, "combat holds the list's layout")
	sim:leaveCombat()
	sim:advance(0.2)
	assert(Text(Blocks()) == settled, "leaving combat lays the list out again")

	sim:slash("/fcore quests")
	sim:advance(0.2)
	assert(NativeDrawn() == true, "turning the list off draws the game's own quest module again")
	assert(tracker:HasModule(sim.G.CampaignQuestObjectiveTracker) == true, "and gives the campaign module back as well")
	assert(#Blocks() == 0, "and empties the Forever list")
	-- The taint check for the takeover: the game's own tracker builds its secure quest item button while the list is
	-- off, in combat, and the same with the list on and its modules taken out of the tracker by it.
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
	local nativeItemButton
	for _, frame in pairs(sim.G.QuestObjectiveTracker.usedRightEdgeFrames or {}) do
		if frame.charges == 1 then
			nativeItemButton = frame
		end
	end
	assert(nativeItemButton ~= nil, "the game's tracker built its secure quest item button")
	sim:slash("/fcore quests")
	sim:advance(0.2)
	assert(NativeDrawn() == false, "turning the list on takes the quest module out of the tracker again")
	CombatQuestRefresh()
	sim:slash("/fcore quests")
	sim:advance(0.2)
	assert(NativeDrawn() == true, "turning the list off again draws the game's own quest module")

	sim:setGamepad(true)
	sim:gamepadNavigate()
	sim:expectNoErrors(ADDON)
	sim:expectNoGamepadTaint(ADDON)
end)

-- The column's height cap and scroll: 60 item quests overflow the room under the game's tracker, the bar appears, the
-- wheel moves one block, an update keeps the top quest in place, and combat freezes the view at half alpha.
scenario("the Forever quest list scrolls one block and freezes in combat", function(sim)
	local Enum = sim.G.Enum
	local NORMAL = Enum.QuestClassification.Normal
	local entries, byID = {}, {}
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
			isOnMap = true,
			hasLocalPOI = false,
			level = 0,
			questClassification = NORMAL,
		}
	end
	local function quest(questID)
		return {
			title = "Scroll Quest " .. questID,
			questLogIndex = #entries + 1,
			questID = questID,
			isHeader = false,
			isOnMap = true,
			hasLocalPOI = false,
			level = 10,
			questClassification = NORMAL,
		}
	end
	add(header("Durotar"))
	local watches = {}
	for questID = 201, 260 do
		add(quest(questID))
		watches[#watches + 1] = questID
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
	sim.impl["C_QuestLog.IsComplete"] = function()
		return false
	end
	sim.impl["C_QuestLog.ReadyForTurnIn"] = function()
		return false
	end
	sim.impl["C_QuestLog.IsFailed"] = function()
		return false
	end
	sim.impl["C_QuestLog.GetDistanceSqToQuest"] = function(questID)
		return questID * 10
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
	-- Every quest carries the same special item, so the pool has to cover every visible item quest.
	sim.G.GetQuestLogSpecialItemInfo = function(index)
		if index and index > 1 then
			return "item:5512", 5512, 1, true
		end
	end
	sim.G.ObjectiveTrackerFrame:SetPoint("TOPRIGHT", sim.G.UIParent, "TOPRIGHT", 0, -100)
	sim.G.ObjectiveTrackerFrame:SetHeight(400)

	sim:login({ savedVariables = { ForeverCoreDB = { questList = true } } })
	sim:advance(0.5)

	local section = sim.G.ForeverCoreQuestTracker
	assert(section ~= nil, "the Forever quest section exists")
	assert(section.trackerOverflow == true and section.scrollRange > 0, "a long list overflows and scrolls")
	assert(section.scrollBar:IsShown(), "an overflowing list shows the client's minimal scrollbar")
	assert(
		section.scrollBar:IsObjectType("EventFrame") and not section.scrollBar:IsObjectType("Slider"),
		"the bar is the client's MinimalScrollBar EventFrame, not a Slider"
	)
	assert(
		type(section.scrollBar.SetScrollPercentage) == "function"
			and type(section.scrollBar.SetVisibleExtentPercentage) == "function",
		"the bar is driven by the ScrollBarMixin percentages"
	)
	assert(
		section.scrollBar:GetVisibleExtentPercentage() > 0 and section.scrollBar:GetVisibleExtentPercentage() < 1,
		"the bar shows the viewport's fraction of the list"
	)
	assert(section.ContentsFrame:GetWidth() < section:GetWidth(), "the blocks give the bar its gutter")

	local starts = section:BlockStarts()
	assert(#starts > 40, "the list laid every block out for the scroll child")
	local firstQuest = starts[2]
	assert(type(firstQuest.block.id) == "number", "the second block is the first quest")
	section:OnTrackerWheel(-1)
	sim:advance(0.1)
	assert(math.abs(section.scrollOffset - firstQuest.start) < 0.5, "one wheel step moves exactly one block")
	assert(
		math.abs(section.scrollBar:GetScrollPercentage() - firstQuest.start / section.scrollRange) < 1e-9,
		"the bar's percentage follows the block-snapped view"
	)
	-- A bar drag is a percentage callback, the one path the real MinimalScrollBar offers.
	section.scrollBar:SetScrollPercentage(0.5)
	sim:advance(0.1)
	assert(math.abs(section.scrollOffset - section.scrollRange * 0.5) < 0.5, "dragging the bar moves the view")
	section.scrollBar:SetScrollPercentage(firstQuest.start / section.scrollRange)
	sim:advance(0.1)
	assert(math.abs(section.scrollOffset - firstQuest.start) < 0.5, "the bar returns to the anchored quest")

	-- A rebuild keeps the view on the same quest, not a pixel offset.
	local anchor = firstQuest.block.id
	sim:event("QUEST_LOG_UPDATE")
	sim:advance(0.2)
	local anchored
	for _, entry in ipairs(section:BlockStarts()) do
		if entry.block.id == anchor then
			anchored = entry.start
		end
	end
	assert(
		anchored ~= nil and math.abs(section.scrollOffset - anchored) < 0.5,
		"an update keeps the top quest in place"
	)

	-- Folding the whole section keeps the view for when it opens again.
	local preserved = section.scrollOffset
	sim:click(section.Header.MinimizeButton, "LeftButton")
	sim:advance(0.2)
	assert(section:IsCollapsed() == true, "the header button folds the section")
	sim:click(section.Header.MinimizeButton, "LeftButton")
	sim:advance(0.2)
	assert(section:IsCollapsed() == false, "the header button unfolds the section")
	assert(math.abs(section.scrollOffset - preserved) < 0.5, "reopening keeps the scroll position")

	-- Only fully visible item quests have a button, and the fixed pool covers them all.
	local shown = {}
	for _, button in ipairs(section.itemButtons) do
		if button:IsShown() then
			shown[#shown + 1] = button
		end
	end
	assert(#shown > 0 and #shown <= 40, "the fixed pool covers the visible item quests")
	for _, button in ipairs(shown) do
		local block = button:GetParent()
		assert(block.hasItem == true, "a shown button belongs to an item quest")
		assert(
			block:GetTop() <= section.scrollFrame:GetTop() + 0.5
				and block:GetBottom() >= section.scrollFrame:GetBottom() - 0.5,
			"a shown button belongs to a fully visible block"
		)
	end

	local before = section.scrollOffset
	local heldButton = shown[1]
	local heldParent, heldItem = heldButton:GetParent(), heldButton:GetAttribute("item")
	sim:enterCombat()
	sim:advance(0.1)
	assert(section.scrollBar:GetAlpha() == 0.5, "a frozen scrollbar shows at half alpha")
	section:OnTrackerWheel(-1)
	assert(section.scrollOffset == before, "the wheel does nothing in combat")

	-- A layout change queued in combat survives the load and world events that also run there.
	sim:event("QUEST_LOG_UPDATE")
	sim:advance(0.1)
	assert(section.combatChangeQueued == true, "a combat quest change waits for combat to end")
	assert(section.itemButtons[1]:GetAlpha() == 0.5, "the queued change dims the item buttons")
	assert(heldButton:GetParent() == heldParent, "a protected item button keeps its parent in combat")
	assert(heldButton:GetAttribute("item") == heldItem, "a protected item button keeps its secure action in combat")
	section:OnEvent("ADDON_LOADED")
	section:OnEvent("PLAYER_ENTERING_WORLD")
	sim:advance(0.1)
	assert(section.combatChangeQueued == true, "a combat load does not clear the queued change")
	assert(section.itemButtons[1]:GetAlpha() == 0.5, "the buttons stay dimmed through those events")

	sim:leaveCombat()
	sim:advance(0.1)
	assert(section.scrollBar:GetAlpha() == 1, "the scrollbar returns to full alpha after combat")
	assert(section.combatChangeQueued == false, "combat ending clears the queued change")
	assert(section.itemButtons[1]:GetAlpha() == 1, "the item buttons return to full alpha")
	section:OnTrackerWheel(-1)
	sim:advance(0.1)
	assert(section.scrollOffset > before, "the wheel moves again after combat")

	sim:setGamepad(true)
	sim:gamepadNavigate()
	sim:expectNoErrors(ADDON)
	sim:expectNoGamepadTaint(ADDON)
end)

-- The client's own ObjectiveTrackerManager adds its modules from its own ContinueAfterAllEvents pass on the same two
-- events this file waits for, so the list's first pass can run over a tracker that holds nothing. When that Init adds
-- the game's Quests and Campaign modules later, they arrive through the container's AddModule, and the tracker's height
-- does not change: Edit Mode gives ObjectiveTrackerFrame a fixed height, so modules joining never resize it. The list's
-- one secure post-hook on AddModule must take them as they join: otherwise the native quest list stays above it and, in
-- the live client, leaves the Forever section no room and hides it, so no later pass of its own ever runs.
scenario("the Forever quest list takes native modules that join after its first pass", function(sim)
	local Enum = sim.G.Enum
	local NORMAL = Enum.QuestClassification.Normal
	local entries, byID = {}, {}
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
			isOnMap = true,
			hasLocalPOI = false,
			level = 0,
			questClassification = NORMAL,
		}
	end
	local function quest(questID)
		return {
			title = "Joined Quest " .. questID,
			questLogIndex = #entries + 1,
			questID = questID,
			isHeader = false,
			isOnMap = true,
			hasLocalPOI = false,
			level = 10,
			questClassification = NORMAL,
		}
	end
	add(header("Durotar"))
	local watches = {}
	for questID = 301, 302 do
		add(quest(questID))
		watches[#watches + 1] = questID
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
	sim.impl["C_QuestLog.IsComplete"] = function()
		return false
	end
	sim.impl["C_QuestLog.ReadyForTurnIn"] = function()
		return false
	end
	sim.impl["C_QuestLog.IsFailed"] = function()
		return false
	end
	sim.impl["C_QuestLog.GetDistanceSqToQuest"] = function(questID)
		return questID * 10
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

	-- The manager's own pass adds no module at login, so the list's first pass runs over an empty tracker, as it does
	-- when this file's ContinueAfterAllEvents callback wins the race against ObjectiveTrackerManager:Init.
	local manager = assert(sim.G.ObjectiveTrackerManager, "the sim models the client's ObjectiveTrackerManager")
	manager.canAddModules = false
	sim:login({ savedVariables = { ForeverCoreDB = { questList = true } } })
	sim:advance(0.5)

	local tracker = sim.G.ObjectiveTrackerFrame
	local section = assert(sim.G.ForeverCoreQuestTracker, "the Forever quest section exists")
	local function Blocks()
		local out = {}
		local block = section.firstBlock
		while block do
			out[#out + 1] = block
			block = block.nextBlock
		end
		return out
	end
	assert(#tracker.modules == 0, "the client's tracker holds no module when the list's first pass runs")
	assert(section:IsShown() and section.Header:IsVisible(), "the list draws over the empty tracker")
	assert(#Blocks() == 3, "the list draws its zone and both quests over the empty tracker")
	assert(sim.G.QuestObjectiveTracker.Header:IsVisible() == false, "the game's own Quests header is not drawn")

	-- Init then adds its modules, the game's Quests and Campaign among them, through the client's own AddModule path.
	-- The tracker keeps the fixed height it already had, as the client's frame does.
	local questModule, campaignModule = sim.G.QuestObjectiveTracker, sim.G.CampaignQuestObjectiveTracker
	manager.canAddModules = true
	manager:Init()
	sim:advance(0.2)

	assert(
		tracker:HasModule(questModule) == false,
		"the game's quest module that joins after the first pass is taken by the AddModule post-hook"
	)
	assert(tracker:HasModule(campaignModule) == false, "and the game's campaign module with it")
	assert(questModule.Header:IsVisible() == false, "the game's own Quests header is not left above the list")
	assert(section:IsShown() and section.Header:IsVisible(), "the Forever list draws after the modules join")
	assert(#Blocks() == 3, "and keeps its zone and both quests")

	sim:setGamepad(true)
	sim:gamepadNavigate()
	sim:expectNoErrors(ADDON)
	sim:expectNoGamepadTaint(ADDON)
end)
