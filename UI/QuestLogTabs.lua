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
---@field hidden? boolean true while the addon has taken its tab out of the column

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
local appliedOffset = 0
local TAB_GAP = 3
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

---@return ForeverCoreSavedVariables?
local function Saved()
	local db
	if type(ns.Store) == "function" then
		db = ns.Store()
	else
		db = rawget(_G, "ForeverCoreDB")
	end
	return type(db) == "table" and db or nil
end

local function SavedOffset()
	local db = Saved()
	return db and db.questLogTabOffsetY or 0
end

local function ClampOffset(map, stockTab, entries, offset)
	local defaultTop = tabOffsetY
	local height = questsTab and questsTab:GetHeight() or 0
	local hasTab = questsTab ~= nil
	for _, entry in ipairs(entries) do
		if not entry.hidden then
			height = height + entry.tab:GetHeight() + (hasTab and TAB_GAP or 0)
			hasTab = true
		end
	end
	if not questsTab then
		local mapTop, stockBottom = map:GetTop(), stockTab:GetBottom()
		if not mapTop or not stockBottom then
			return offset
		end
		defaultTop = stockBottom - mapTop - TAB_GAP
	end
	local bottomLimit = math.min(0, height - map:GetHeight())
	return math.max(bottomLimit, math.min(0, defaultTop + offset)) - defaultTop
end

-- A hidden entry retains its order, and the visible tabs close the gap.
---@param dragOffset number?
local function Anchor(dragOffset)
	local map = QuestMapFrame
	local entries = Sorted()
	local stockTab = map.MapLegendTab:IsShown() and map.MapLegendTab or map.QuestsTab
	appliedOffset = dragOffset or SavedOffset()
	-- Preserve the client's exact layout when no custom position is set.
	if dragOffset or appliedOffset ~= 0 then
		appliedOffset = ClampOffset(map, stockTab, entries, appliedOffset)
	end
	local previous = questsTab
	if questsTab then
		questsTab:ClearAllPoints()
		questsTab:SetPoint("TOPLEFT", map, "TOPRIGHT", 0, tabOffsetY + appliedOffset)
	end
	for _, entry in ipairs(entries) do
		local tab = entry.tab
		tab:ClearAllPoints()
		tab:SetShown(not entry.hidden)
		if not entry.hidden then
			tab:SetPoint("TOP", previous or stockTab, "BOTTOM", 0, -TAB_GAP + (previous and 0 or appliedOffset))
			previous = tab
		end
	end
end

-- The client's own Show/Hide of the side panel, whether the toggle, a minimize or a maximize asked for it.
-- Maximising or minimising the map changes its height, so a moved column is clamped again; the saved offset stays.
local function QuestLogPanelShown()
	if appliedOffset ~= 0 or SavedOffset() ~= 0 then
		Anchor()
	end
	Sync()
end

local function InCombat()
	return InCombatLockdown and InCombatLockdown()
end

---@param tab ForeverQuestLogTab
---@param selectTab fun()
local function SetTabInput(tab, selectTab)
	local dragged = false
	local cursorStart, offsetStart, lastCursorY

	local function Move()
		local _, cursorY = GetCursorPosition()
		if cursorY ~= lastCursorY then
			lastCursorY = cursorY
			Anchor(offsetStart + (cursorY - cursorStart) / tab:GetEffectiveScale())
		end
	end

	-- Keeps the column where it was last drawn.
	local function EndDrag()
		if cursorStart then
			cursorStart = nil
			tab:SetScript("OnUpdate", nil)
			local db = Saved()
			if db then
				db.questLogTabOffsetY = appliedOffset ~= 0 and appliedOffset or nil
			end
		end
	end

	-- The map can close or combat can start while the button is held, and then OnDragStop never arrives: the next
	-- update, on this frame or once the map is open again, ends the drag in place.
	local function UpdateDrag()
		if not cursorStart then
			return
		end
		if InCombat() or not IsMouseButtonDown("LeftButton") then
			EndDrag()
		else
			Move()
		end
	end

	local function StopDrag()
		if cursorStart and not InCombat() then
			Move()
		end
		EndDrag()
	end

	tab:RegisterForDrag("LeftButton")
	tab:HookScript("OnMouseDown", function(_, button)
		if button == "LeftButton" then
			EndDrag()
			dragged = false
		end
	end)
	tab:SetScript("OnDragStart", function()
		dragged = true
		if not InCombat() then
			local _, cursorY = GetCursorPosition()
			cursorStart, offsetStart, lastCursorY = cursorY, appliedOffset, cursorY
			tab:SetScript("OnUpdate", UpdateDrag)
		end
	end)
	tab:SetScript("OnDragStop", StopDrag)
	tab:SetCustomOnMouseUpHandler(function(_, button, upInside)
		if not upInside then
			return
		end
		if button == "LeftButton" and not dragged then
			selectTab()
		elseif button == "RightButton" and SavedOffset() ~= 0 and not InCombat() then
			ns.ContextMenu(tab, function(_, root)
				root:CreateButton(ns.L["Reset tab position"], function()
					local db = Saved()
					if db and not InCombat() then
						db.questLogTabOffsetY = nil
						Anchor()
					end
				end)
			end)
		end
	end)
	tab:HookScript("OnEnter", function()
		local tooltip = GetAppropriateTooltip()
		if tooltip:IsOwned(tab) then
			tooltip:AddLine(ns.L["Drag to move the tabs."], GRAY_FONT_COLOR:GetRGB())
			tooltip:Show()
		end
	end)
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
		SetTabInput(tab, api.ShowQuests)
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
	SetTabInput(tab, function()
		api.Select(key)
	end)
	tab:SetChecked(false)
	tabs[key] = { key = key, spec = spec, tab = tab }
	Anchor()
	return tab
end

-- Take an addon's own tab out of the column, or put it back. The panel keeps its state: hiding the selected tab leaves
-- its panel open until another tab or the quest log is chosen, and Select still opens a hidden tab's panel. An unknown
-- key, including one this module has not been given yet, changes nothing and answers false.
---@param key string
---@param shown boolean
---@return boolean
function api.SetTabShown(key, shown)
	local entry = tabs[key]
	if not entry then
		return false
	end
	local hidden = shown == false
	if (entry.hidden == true) ~= hidden then
		entry.hidden = hidden or nil
		Anchor()
	end
	return true
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
