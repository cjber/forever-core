---@type string, table
local _, ns = ...

-- A shared side tab for the addon panels that live in the world map's quest log. Each addon registers a key, its
-- panel and a tab name; selecting one shows that panel and hides the quest log's own content frames, and ShowQuests
-- puts them back exactly as displayMode says. The module never resizes QuestMapFrame or a panel and never touches a
-- panel's children, so switching only shows and hides and each panel's ScrollFrame keeps its offset.

---@class ForeverQuestLogTabEntry
---@field key string
---@field spec ForeverQuestLogTabSpec
---@field tab ForeverQuestLogTab

-- Each Forever addon with a quest log panel vendors this file, so each loads its own copy. They share one
-- registry, published by the first copy to load, so every addon's tab stacks in the one column. The registry is
-- addon state: nothing of Blizzard's reads it.
if ForeverQuestLogTabs then
	ns.QuestLogTabs = ForeverQuestLogTabs
	return
end

---@class ForeverQuestLogTabsAPI
local api = {}

---@type table<string, ForeverQuestLogTabEntry>
local tabs = {}
local selectedKey
---@type ForeverQuestLogTab?
local questsTab
local tabOffsetY = 0
local installed = false

---@param name string
---@return ForeverQuestLogTab
local function NewTab(name)
	return CreateFrame("Frame", name, QuestMapFrame, "LargeSideTabButtonTemplate") --[[@as ForeverQuestLogTab]]
end

---@return ForeverQuestLogTabEntry[]
local function Sorted()
	---@type ForeverQuestLogTabEntry[]
	local list = {}
	for _, entry in pairs(tabs) do
		list[#list + 1] = entry
	end
	table.sort(list, function(a, b)
		if a.spec.order ~= b.spec.order then
			return a.spec.order < b.spec.order
		end
		return a.key < b.key
	end)
	return list
end

local function Anchor()
	local map = QuestMapFrame
	---@type Button?
	local previous = questsTab
	if questsTab then
		questsTab:ClearAllPoints()
		questsTab:SetPoint("TOPLEFT", map, "TOPRIGHT", 0, tabOffsetY)
	end
	for _, entry in ipairs(Sorted()) do
		local tab = entry.tab
		tab:ClearAllPoints()
		if not previous then
			previous = map.MapLegendTab:IsShown() and map.MapLegendTab or map.QuestsTab
		end
		tab:SetPoint("TOP", previous, "BOTTOM", 0, -3)
		previous = tab
	end
end

local function Install()
	if installed then
		return
	end
	installed = true
	if QuestMapFrameOverrides.questTabHidden then
		local tab = NewTab("ForeverQuestLogQuestsTab")
		questsTab = tab
		tab.tooltipText = QUESTS_LABEL
		tab.activeAtlas = "questlog-tab-icon-quest"
		tab.inactiveAtlas = "questlog-tab-icon-quest-inactive"
		tab:SetCustomOnMouseUpHandler(function(_, mouseButton, upInside)
			if mouseButton == "LeftButton" and upInside then
				api.ShowQuests()
			end
		end)
		tab:SetChecked(true)
		-- The client's offset is tuned for the Camelot tab art, which Forever hides and never draws, so
		-- against Forever's own frame it leaves a dark strip between the map frame and the tab (#447).
		-- Keep the client's vertical offset and pin the tab flush to the frame's right edge.
		local _, offsetY = QuestMapFrameOverrides.GetQuestsTabAnchorOffset()
		tabOffsetY = offsetY
	end
	EventRegistry:RegisterCallback("QuestLog.SetDisplayMode", function()
		if selectedKey then
			api.ShowQuests()
		end
	end, api)
	-- Opening a tracked quest asks for Quests mode, but SetDisplayMode returns early when the mode is unchanged,
	-- so the callback above never fires for it.
	hooksecurefunc("QuestMapFrame_ShowQuestDetails", function()
		if selectedKey then
			api.ShowQuests()
		end
	end)
end

---@param key string
---@param spec ForeverQuestLogTabSpec
---@return ForeverQuestLogTab
function api.Register(key, spec)
	if type(key) ~= "string" or key == "" then
		error("ForeverQuestLogTabs.Register: key must be a non-empty string", 2)
	end
	if tabs[key] then
		error("ForeverQuestLogTabs.Register: key already registered: " .. key, 2)
	end
	Install()
	local tab = NewTab(spec.name)
	tab.tooltipText = spec.tooltip
	tab:SetCustomOnMouseUpHandler(function(_, mouseButton, upInside)
		if mouseButton == "LeftButton" and upInside then
			api.Select(key)
		end
	end)
	tab:SetChecked(false)
	tabs[key] = { key = key, spec = spec, tab = tab }
	Anchor()
	return tab
end

---@param key string
function api.Select(key)
	local entry = tabs[key]
	if not entry then
		return
	end
	selectedKey = key
	for _, other in pairs(tabs) do
		other.spec.panel:SetShown(other == entry)
		other.tab:SetChecked(other == entry)
	end
	for _, frame in ipairs(QuestMapFrame.ContentFrames) do
		frame:Hide()
	end
	if questsTab then
		questsTab:SetChecked(false)
	end
end

function api.ShowQuests()
	selectedKey = nil
	for _, entry in pairs(tabs) do
		entry.spec.panel:Hide()
		entry.tab:SetChecked(false)
	end
	local map = QuestMapFrame
	for _, frame in ipairs(map.ContentFrames) do
		frame:SetShown(frame.displayMode == map.displayMode)
	end
	if questsTab then
		questsTab:SetChecked(true)
	end
end

---@return string?
function api.Selected()
	return selectedKey
end

ForeverQuestLogTabs = api -- taint-ok: addon-owned quest log tab registry
ns.QuestLogTabs = api
