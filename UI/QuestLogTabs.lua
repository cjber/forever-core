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

-- Each Forever addon registers its panel here; every addon's tab stacks in the one column. The registry is addon
-- state: nothing of Blizzard's reads it.

---@class ForeverQuestLogTabsAPI
local api = {}

---@type table<string, ForeverQuestLogTabEntry>
local tabs = {}
local selectedKey
-- The key whose panel was last reported visible through `shown`, so each change is reported exactly once.
local reportedKey
---@type ForeverQuestLogTab?
local questsTab
local tabOffsetY = 0
local installed = false

---@param name string
---@return ForeverQuestLogTab
local function NewTab(name)
	-- A Button, so the gamepad's SmartNavigation scan never reads this frame's mouse scripts (cjber/skillup-forever#398).
	return CreateFrame("Button", name, QuestMapFrame, "LargeSideTabButtonTemplate") --[[@as ForeverQuestLogTab]]
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

-- Tell a panel whether the player can see it. No panel sets OnShow or OnHide: a script under WorldMapFrame runs
-- inside the map's close path, where addon taint blocks the gamepad's interact target (shortest-path-forever#158).
-- The panel's callback runs in its addon's SafeCall when one was registered, so a failure lands in that journal.
---@param entry ForeverQuestLogTabEntry
---@param visible boolean
local function NotifyShown(entry, visible)
	local spec = entry.spec
	if not spec.shown then
		return
	end
	local safe = spec.safeCall
	if safe then
		safe("quest log tab shown", spec.shown, visible)
	elseif ns.SafeCall then
		ns.SafeCall("quest log tab shown", spec.shown, visible)
	elseif securecallfunction then
		securecallfunction(spec.shown, visible)
	else
		spec.shown(visible)
	end
end

-- The one rule for what a panel is told: the selected key is reported visible only while the map and its quest log
-- side panel are both shown. Everything that can change either frame ends by calling Sync, which reports the
-- previously visible key hidden and the new one visible, each only once.
---@param mapShown boolean?
local function Sync(mapShown)
	if mapShown == nil then
		mapShown = WorldMapFrame:IsShown()
	end
	local key
	if mapShown and selectedKey and QuestMapFrame:IsShown() then
		key = selectedKey
	end
	if key == reportedKey then
		return
	end
	local previous = reportedKey
	reportedKey = nil
	if previous then
		local entry = tabs[previous]
		if entry then
			NotifyShown(entry, false)
		end
	end
	if key then
		local entry = tabs[key]
		if entry then
			reportedKey = key
			NotifyShown(entry, true)
		end
	end
end

local function PanelShown(_, frame)
	if frame == WorldMapFrame then
		Sync(true)
	end
end

local function PanelHidden(_, frame)
	if frame == WorldMapFrame then
		Sync(false)
	end
end

-- The client's own Show/Hide of the side panel, whether the toggle, a minimize or a maximize asked for it.
local function QuestLogPanelShown()
	Sync()
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
		else
			Sync()
		end
	end, api)
	-- Opening a tracked quest asks for Quests mode, but SetDisplayMode returns early when the mode is unchanged,
	-- so the callback above never fires for it.
	hooksecurefunc("QuestMapFrame_ShowQuestDetails", function()
		if selectedKey then
			api.ShowQuests()
		else
			Sync()
		end
	end)
	-- A panel must not set OnShow or OnHide under the world map, so the map's own callbacks tell it instead.
	EventRegistry:RegisterCallback("UIParentPanelManager.ShowUIPanel", PanelShown, api)
	EventRegistry:RegisterCallback("UIParentPanelManager.HideUIPanel", PanelHidden, api)
	EventRegistry:RegisterCallback("UIParentPanelManager.ForcePanelHide", PanelHidden, api)
	-- A secure post-hook: the client's own method has returned and this adds no script to any frame.
	hooksecurefunc(WorldMapFrame, "SetQuestLogPanelShown", QuestLogPanelShown)
end

---@param key string
---@param spec ForeverQuestLogTabSpec
---@return ForeverQuestLogTab
function api.Register(key, spec)
	if type(key) ~= "string" or key == "" then
		error("ForeverCore.QuestLogTabs.Register: key must be a non-empty string", 2)
	end
	if tabs[key] then
		error("ForeverCore.QuestLogTabs.Register: key already registered: " .. key, 2)
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
	Sync()
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
	Sync()
end

---@return string?
function api.Selected()
	return selectedKey
end

ns.QuestLogTabs = api
