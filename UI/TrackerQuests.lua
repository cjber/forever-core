---@type string, ForeverTrackerNamespace
local _, ns = ...

-- The optional Forever quest list: the watched quests, campaign quests included, grouped ready-to-turn-in first, then
-- this zone, then every other zone, each nearest first. It is a section of the shared Forever column, built from the
-- game's own ObjectiveTrackerModuleTemplate and QuestObjectiveTrackerMixin so its header, lines, POI button, fonts,
-- colours, completed fade and progress bars are the game's. The game's own Quests and Campaign modules are only
-- collapsed while this list is on, through their own SetCollapsed, never moved, hidden, reparented or hooked.
local L = ns.L

---@class ForeverTrackerQuestsAPI
---@field Enabled fun(): boolean
---@field SetEnabled fun(value: boolean)
---@field Toggle fun()

-- The list's own refresh, set once the section exists. The setting can be written before saved variables arrive, so
-- this is nil until the file has built the section.
---@type (fun())?
local apply

---@return boolean
local function Enabled()
	return type(ForeverCoreDB) == "table" and ForeverCoreDB.questList == true
end

---@param value boolean
local function SetEnabled(value)
	value = not not value
	if type(ForeverCoreDB) ~= "table" then
		ForeverCoreDB = {}
	end
	if ForeverCoreDB.questList == value then
		return
	end
	ForeverCoreDB.questList = value
	if apply then
		apply()
	end
end

local function Toggle()
	SetEnabled(not Enabled())
end

---@type ForeverTrackerQuestsAPI
local TrackerQuests = { Enabled = Enabled, SetEnabled = SetEnabled, Toggle = Toggle }
ns.TrackerQuests = TrackerQuests

-- The settings page is registered after saved variables arrive, so its tick box shows the saved choice rather than
-- the false a file loaded too early would read.
local settingsRegistered = false
local TOOLTIP = "Lists your tracked quests in the Forever column, ready to turn in first, then this zone, then the "
	.. "rest by zone, nearest first. The game's own quest list is collapsed while this is on."
local function RegisterSettings()
	if settingsRegistered or not ns.SettingsPage then
		return
	end
	settingsRegistered = true
	ns.SettingsPage.Register(L["Forever Core"], function(panel, page)
		page.AddCheck(panel, L["Forever quest list"], TrackerQuests.Enabled, TrackerQuests.SetEnabled, L[TOOLTIP])
	end, L)
end

if not ObjectiveTrackerFrame then
	EventUtil.ContinueAfterAllEvents(RegisterSettings, "PLAYER_ENTERING_WORLD", "VARIABLES_LOADED")
	return
end

-- Core's own list is a section of core's own column. A host that loaded before ForeverCore owns this game session, so
-- the section stays out of it and no switch is offered that could not draw anything.
if ns.TrackerHostForeign then
	return
end

local host = ns.TrackerHost
if not host then
	EventUtil.ContinueAfterAllEvents(RegisterSettings, "PLAYER_ENTERING_WORLD", "VARIABLES_LOADED")
	return
end

-- Another tracker owns the quest list: Questie's, EQOT's, or Kaliel's Tracker. Their names are the compatibility
-- matrix, so detecting them by name is deliberate. The list modules read the host frame, the same one the host itself
-- passes, not the published API table.
---@return boolean
local function OtherOwner()
	local companion = rawget(_G, "ForeverTrackerCompanion")
	if companion then
		local eqot = ns.TrackerEqot
		if eqot and eqot.List and eqot.List(companion, companion.MarkDirty) then
			return true
		end
		local questie = ns.TrackerQuestie
		if questie and questie.List and questie.List(companion, companion.MarkDirty) then
			return true
		end
	end
	return C_AddOns.IsAddOnLoaded("!KalielsTracker") == true
end

---@param collapsed boolean
local function SetNativeCollapsed(collapsed)
	local quests = rawget(_G, "QuestObjectiveTracker")
	if quests and quests.SetCollapsed then
		quests:SetCollapsed(collapsed)
	end
	local campaign = rawget(_G, "CampaignQuestObjectiveTracker")
	if campaign and campaign.SetCollapsed then
		campaign:SetCollapsed(collapsed)
	end
end

local ready = false
local ownedByOther = false
local collapsedByUs = false
---@type boolean?
local pendingCollapse

---@param active boolean
local function ApplyNativeCollapse(active)
	if InCombatLockdown() then
		pendingCollapse = active
		return
	end
	if pendingCollapse ~= nil then
		active = pendingCollapse
	end
	pendingCollapse = nil
	if active then
		if not collapsedByUs then
			SetNativeCollapsed(true)
			collapsedByUs = true
		end
	elseif collapsedByUs then
		SetNativeCollapsed(false)
		collapsedByUs = false
	end
end

local section = ns.TrackerSection.Create("ForeverCoreQuestTracker", QuestObjectiveTrackerMixin, {
	order = -10,
	header = TRACKER_HEADER_QUESTS,
})
if not section then
	EventUtil.ContinueAfterAllEvents(RegisterSettings, "PLAYER_ENTERING_WORLD", "VARIABLES_LOADED")
	return
end
---@cast section ForeverQuestTrackerModule

---@class ForeverQuestTrackerOverrides : ForeverQuestTrackerModule
local Overrides = {}

---@param quest any
---@return boolean
function Overrides:ShouldDisplayQuest(quest)
	if not quest then
		return false
	end
	if QuestObjectiveTrackerMixin.ShouldDisplayQuest(self, quest) then
		return true
	end
	return CampaignQuestObjectiveTrackerMixin ~= nil
		and CampaignQuestObjectiveTrackerMixin.ShouldDisplayQuest(self, quest) == true
end

-- The quest log header each watched quest sits under, and whether it is on the current map, in one walk of the log.
---@return table<number, string>, table<number, boolean>
local function LogZones()
	local zones, onMap = {}, {}
	local header
	for index = 1, C_QuestLog.GetNumQuestLogEntries() do
		local info = C_QuestLog.GetInfo(index)
		if info then
			if info.isHeader then
				header = info.title
			elseif info.questID then
				zones[info.questID] = header
				onMap[info.questID] = info.isOnMap == true
			end
		end
	end
	return zones, onMap
end

---@return ForeverQuestRecord[]
function Overrides:Records()
	local zones, onMap = LogZones()
	local records = {}
	for index = 1, C_QuestLog.GetNumQuestWatches() do
		local questID = C_QuestLog.GetQuestIDForQuestWatchIndex(index)
		if questID then
			local quest = QuestCache:Get(questID)
			if self:ShouldDisplayQuest(quest) then
				local distanceSq = C_QuestLog.GetDistanceSqToQuest(questID)
				records[#records + 1] = {
					questID = questID,
					title = C_QuestLog.GetTitleForQuestID(questID) or (quest and quest.title) or "",
					zone = zones[questID] or "",
					ready = C_QuestLog.ReadyForTurnIn(questID) == true or (quest ~= nil and quest:IsComplete()),
					onMap = onMap[questID] == true,
					distanceSq = type(distanceSq) == "number" and distanceSq or nil,
				}
			end
		end
	end
	return records
end

-- Adapted from QuestObjectiveTrackerMixin:UpdateSingle. There are no quest item or group finder buttons: they are
-- secure frames, and a secure child would make the column protected in combat (issue #177's decision 3 is open).
---@param record ForeverQuestRecord
---@return boolean
function Overrides:UpdateQuest(record)
	local questID = record.questID
	local quest = QuestCache:Get(questID)
	if not quest then
		return false
	end
	local isComplete = quest:IsComplete()
	local isSuperTracked = questID == C_SuperTrack.GetSuperTrackedQuestID()
	local useFullHeight = true
	local shouldShowWaypoint = isSuperTracked or questID == QuestMapFrame_GetFocusedQuestID()
	local isSequenced = IsQuestSequenced(questID)
	local questLogIndex = quest:GetQuestLogIndex()
	local block, isExistingBlock = self:GetBlock(questID)
	local tagText = self:GetQuestTagText(questID)

	local title = record.title or ""
	if tagText then
		title = title .. " " .. tagText
	end
	title = SetQuestTitleLevelAndDifficultyColor(questID, title)
	if record.distanceSq then
		local yards = math.floor(math.sqrt(record.distanceSq) + 0.5)
		title = title .. " (" .. L["%d yd"]:format(yards) .. ")"
	end
	block:SetHeader(title)

	if isComplete then
		local objectiveCompleting =
			self:DoQuestObjectives(block, isComplete, isSequenced, isExistingBlock, useFullHeight)
		if not objectiveCompleting then
			if quest.isAutoComplete then
				block:AddObjective("QuestComplete", QUEST_WATCH_QUEST_COMPLETE)
				block:AddObjective("ClickComplete", QUEST_WATCH_CLICK_TO_COMPLETE)
			else
				local completionText = questLogIndex and GetQuestLogCompletionText(questLogIndex)
				if completionText then
					if shouldShowWaypoint then
						local waypointText = C_QuestLog.GetNextWaypointText(questID)
						if waypointText ~= nil then
							block:AddObjective(
								"Waypoint",
								WAYPOINT_OBJECTIVE_FORMAT_OPTIONAL:format(waypointText),
								nil,
								useFullHeight
							)
						end
					end
					block:AddObjective("QuestComplete", completionText, nil, true, OBJECTIVE_DASH_STYLE_HIDE)
				else
					local waypointText = C_QuestLog.GetNextWaypointText(questID)
					if waypointText then
						block:AddObjective("Waypoint", waypointText, nil, useFullHeight)
					else
						block:AddObjective(
							"QuestComplete",
							QUEST_WATCH_QUEST_READY,
							nil,
							useFullHeight,
							OBJECTIVE_DASH_STYLE_HIDE,
							OBJECTIVE_TRACKER_COLOR["Complete"]
						)
					end
				end
			end
		end
	elseif C_QuestLog.IsFailed(questID) then
		block:AddObjective(
			"Failed",
			FAILED,
			nil,
			useFullHeight,
			OBJECTIVE_DASH_STYLE_HIDE,
			OBJECTIVE_TRACKER_COLOR["Failed"]
		)
	else
		if shouldShowWaypoint then
			local waypointText = C_QuestLog.GetNextWaypointText(questID)
			if waypointText ~= nil then
				block:AddObjective(
					"Waypoint",
					WAYPOINT_OBJECTIVE_FORMAT_OPTIONAL:format(waypointText),
					nil,
					useFullHeight
				)
			end
		end
		self:DoQuestObjectives(block, isComplete, isSequenced, isExistingBlock, useFullHeight)
	end

	block:SetPOIInfo(questID, isComplete, isSuperTracked)
	return self:LayoutBlock(block)
end

function Overrides:LayoutContents()
	if not TrackerQuests.Enabled() or ownedByOther then
		return
	end
	for _, group in ipairs(ns.QuestOrder(self:Records())) do
		local block = self:GetBlock("group:" .. group.title)
		block:SetHeader(group.title)
		if not self:LayoutBlock(block) then
			return
		end
		for _, record in ipairs(group.quests) do
			if not self:UpdateQuest(record) then
				return
			end
		end
	end
end

function Overrides.CanUpdate()
	return not InCombatLockdown()
end

---@param block any
---@param mouseButton string
function Overrides:OnBlockHeaderClick(block, mouseButton)
	if type(block.id) ~= "number" then
		return
	end
	if mouseButton == "LeftButton" and not IsShiftKeyDown() then
		C_SuperTrack.SetSuperTrackedQuestID(block.id)
		return
	end
	QuestObjectiveTrackerMixin.OnBlockHeaderClick(self, block, mouseButton)
end

-- The host adds the column's own switches; this section adds the way back to the game's list.
---@param _ ForeverQuestTrackerModule
---@param root any
function Overrides.AddHeaderMenuEntries(_, root)
	root:CreateButton(L["Use the game's quest list"], function()
		TrackerQuests.SetEnabled(false)
	end)
end

for _, event in ipairs({
	"PLAYER_ENTERING_WORLD",
	"PLAYER_REGEN_ENABLED",
	"PLAYER_REGEN_DISABLED",
	"QUEST_LOG_UPDATE",
	"QUEST_WATCH_LIST_CHANGED",
	"QUEST_WATCH_UPDATE",
	"QUEST_TURNED_IN",
	"QUEST_POI_UPDATE",
	"SUPER_TRACKING_CHANGED",
	"SUPER_TRACKING_PATH_UPDATED",
	"ZONE_CHANGED_NEW_AREA",
	"ADDON_LOADED",
}) do
	section:RegisterEvent(event)
end

---@param event string
function Overrides:OnEvent(event)
	if event == "PLAYER_REGEN_ENABLED" or event == "ADDON_LOADED" or event == "PLAYER_ENTERING_WORLD" then
		if apply then
			apply()
		end
		return
	end
	self:MarkDirty()
end

-- Mixin copies at call time: every override, OnEvent included, must be defined before this line.
Mixin(section, Overrides)

apply = function()
	if not ready then
		return
	end
	ownedByOther = OtherOwner()
	local active = TrackerQuests.Enabled() and not ownedByOther
	section:MarkDirty()
	ApplyNativeCollapse(active)
end

EventUtil.ContinueAfterAllEvents(function()
	ready = true
	RegisterSettings()
	apply()
	if C_Timer.NewTicker then
		-- One ticker refreshes the distances, and notices another tracker taking or giving back the quest list. It does
		-- nothing in combat and nothing while the list is off; the section's own events redraw the rest.
		C_Timer.NewTicker(2, function()
			if InCombatLockdown() or not TrackerQuests.Enabled() then
				return
			end
			if host.IsAttached(section) ~= true or section:IsShown() then
				apply()
			end
		end)
	end
end, "PLAYER_ENTERING_WORLD", "VARIABLES_LOADED")
