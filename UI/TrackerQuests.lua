-- luacheck: globals C_QuestInfoSystem CreateFramePool ObjectiveTrackerAnimBlockMixin
-- luacheck: globals RegisterStateDriver UnregisterStateDriver
---@type string, ForeverTrackerNamespace
local _, ns = ...

-- The default Forever quest list: the watched quests, campaign quests included, grouped ready-to-turn-in first, then
-- this zone, then every other zone, each nearest first. It is a section of the shared Forever column, built from the
-- game's own ObjectiveTrackerModuleTemplate and QuestObjectiveTrackerMixin so its header, lines, POI button, fonts,
-- colours, completed fade and layout are the game's. This file never touches the client's own tracker modules: the
-- whole native tracker is hidden while this list is active, as Questie does. Only frame visibility changes; no
-- addon code writes the native tracker's state or schedules its layout.
--
-- The list adds the parts a player misses from a third-party tracker: a thin progress fill under every unfinished
-- count, one fold per quest and per zone saved for the character, a height cap with scrolling, the game's quest item
-- buttons from a fixed pool, the full quest menu on every title, and a tracked count on the header.
local L = ns.L

---@class ForeverTrackerQuestsAPI
---@field Enabled fun(): boolean
---@field SetEnabled fun(value: boolean)
---@field Toggle fun()

-- The list's own refresh, set once the section exists. The setting can be written before saved variables arrive, so
-- this is nil until the file has built the section.
---@type (fun())?
local apply

-- The runtime store when Core.lua publishes one; an older consumer's spec can still supply ForeverCoreDB directly.
---@return table?
local function Database()
	if type(ns.Store) == "function" then
		return ns.Store()
	end
	return ForeverCoreDB
end

---@return boolean
local function Enabled()
	local db = Database()
	return type(db) == "table" and db.questList ~= false
end

---@param value boolean
local function SetEnabled(value)
	value = not not value
	local db = Database()
	if type(db) ~= "table" then
		return
	end
	-- A player who turns the list off has found the switch, so the one-time hint that points at it is answered too.
	if not value then
		db.questListHintDone = true
	end
	if db.questList == value then
		return
	end
	db.questList = value
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
	.. "rest by zone, nearest first. The game's own objective tracker is hidden while this is on."
local function RegisterSettings()
	if settingsRegistered or not ns.SettingsPage then
		return
	end
	settingsRegistered = true
	ns.SettingsPage.Register(L["ForeverCore"], function(panel, page)
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

-- Another tracker owns the quest list: Questie's, EQOT's, EllesmereUI's, or Kaliel's Tracker. Their names form the
-- matrix, so detecting them by name is deliberate. The list modules read the host frame, the same one the host itself
-- passes, not the published API table.
local hidNativeTracker = false
local coreMutedNative = false

---@return boolean
local function OtherOwner()
	if ns.TrackerEllesmere and ns.TrackerEllesmere.Owns() then
		return true
	end
	-- Before our own suppression, a muted tracker or a shown tracker under a hidden parent means another addon
	-- replaced the visible list. A plain hidden tracker can just be Blizzard's empty list; UIParent can hide globally.
	if
		not coreMutedNative
		and (
			ObjectiveTrackerFrame:GetAlpha() == 0
			or (ObjectiveTrackerFrame:IsShown() and not ObjectiveTrackerFrame:IsVisible() and UIParent:IsVisible())
		)
	then
		return true
	end
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

local ready = false
local ownedByOther = false
local section

-- Native Show/Hide scripts update the shared managed-frame layout. Only the secure visibility driver may
-- run them: an addon Hide taints that layout and the scenario tracker's subsequent secret aura reads (#608).
-- Alpha covers native Show calls between driver ticks. Driver registration waits for combat to end.
local hideNativeTracker = false
local nativeTrackerAlpha = 1
local nativeDriverRegistered = false
local visibilityFrame = CreateFrame("Frame")
local function ApplyNativeVisibility()
	if hideNativeTracker then
		if not coreMutedNative then
			nativeTrackerAlpha = ObjectiveTrackerFrame:GetAlpha()
			coreMutedNative = true
		end
		hidNativeTracker = true
		-- Blizzard's container layout can Show again on a combat quest update. Hide may be protected then, but
		-- alpha is not: suppress that Show immediately rather than exposing the tracker until combat ends.
		ObjectiveTrackerFrame:SetAlpha(0)
	end
	if InCombatLockdown() then
		visibilityFrame:RegisterEvent("PLAYER_REGEN_ENABLED")
		return
	end
	visibilityFrame:UnregisterEvent("PLAYER_REGEN_ENABLED")
	if hideNativeTracker then
		if not nativeDriverRegistered then
			nativeDriverRegistered = true
			RegisterStateDriver(ObjectiveTrackerFrame, "visibility", "hide")
		end
	elseif hidNativeTracker or coreMutedNative then
		-- Another tracker may have taken over while ours was on. Release our ownership without showing its tracker.
		local otherOwner = OtherOwner()
		hidNativeTracker = false
		if not otherOwner then
			ObjectiveTrackerFrame:SetAlpha(nativeTrackerAlpha)
			coreMutedNative = false
			nativeDriverRegistered = true
			RegisterStateDriver(ObjectiveTrackerFrame, "visibility", "show")
		end
		if nativeDriverRegistered then
			UnregisterStateDriver(ObjectiveTrackerFrame, "visibility")
			nativeDriverRegistered = false
		end
	end
end
visibilityFrame:SetScript("OnEvent", ApplyNativeVisibility)
ObjectiveTrackerFrame:HookScript("OnShow", function()
	if hideNativeTracker then
		ObjectiveTrackerFrame:SetAlpha(0)
	end
end)

-- The character the folds are saved for. ForeverCoreDB is account wide, so every saved fold lives under one key per
-- realm and character and a second character starts unfolded.
---@return string
local function CharacterKey()
	local name = UnitFullName and select(1, UnitFullName("player")) or nil
	if not name and UnitName then
		name = select(1, UnitName("player"))
	end
	local realm = GetRealmName and GetRealmName() or nil
	return tostring(realm or "realm") .. "/" .. tostring(name or "player")
end

-- One character's folded quests and zones, made on first read so the table shape is always there.
---@return table?
local function CharacterState()
	local db = Database()
	if type(db) ~= "table" then
		return nil
	end
	local all = db.questListFold
	if type(all) ~= "table" then
		all = {}
		db.questListFold = all
	end
	local key = CharacterKey()
	local state = all[key]
	if type(state) ~= "table" then
		state = {}
		all[key] = state
	end
	if type(state.quests) ~= "table" then
		state.quests = {}
	end
	if type(state.zones) ~= "table" then
		state.zones = {}
	end
	return state
end

---@param questID number
---@return boolean
local function IsQuestFolded(questID)
	local state = CharacterState()
	return state ~= nil and state.quests[questID] == true
end

---@param questID number
---@param folded boolean
local function SetQuestFolded(questID, folded)
	local state = CharacterState()
	if state ~= nil then
		state.quests[questID] = folded or nil
	end
end

---@param zone string
---@return boolean
local function IsZoneFolded(zone)
	local state = CharacterState()
	return state ~= nil and state.zones[zone] == true
end

---@param zone string
---@param folded boolean
local function SetZoneFolded(zone, folded)
	local state = CharacterState()
	if state ~= nil then
		state.zones[zone] = folded or nil
	end
end

---@param questID number
local function ToggleQuest(questID)
	SetQuestFolded(questID, not IsQuestFolded(questID))
	if section then
		section:MarkDirty()
	end
end

---@param zone string
local function ToggleZone(zone)
	SetZoneFolded(zone, not IsZoneFolded(zone))
	if section then
		section:MarkDirty()
	end
end

-- The game's own words where this client has them, so the menu reads like the native tracker. The fallback is used
-- only on a build where the global string is missing.
---@param name string
---@param fallback string
---@return string
local function GameString(name, fallback)
	return rawget(_G, name) or fallback
end

---@param reason string?
local function Report(reason)
	if reason and DEFAULT_CHAT_FRAME and DEFAULT_CHAT_FRAME.AddMessage then
		DEFAULT_CHAT_FRAME:AddMessage(reason)
	end
end

-- Shortest Path's published API, when the addon is loaded. The quest menu's Objectives submenu is offered only when
-- there is both an API and a real client map point for the quest, so a player never sees a row that cannot route.
---@return table?
local function ShortestPath()
	local addon = rawget(_G, "ShortestPathForever")
	local api = addon and addon.API
	if type(api) == "table" and type(api.Navigate) == "function" then
		return api
	end
end

-- The quest's own point on the current quest map, from the client's POI data. QuestPOIMapInfo coordinates are the
-- same 0 to 1 fractions Shortest Path takes. A quest with no pin on this map has no routable point.
---@param questID number
---@return number?, number?, number?
local function QuestPoint(questID)
	if type(C_QuestLog.GetMapForQuestPOIs) ~= "function" or type(C_QuestLog.GetQuestsOnMap) ~= "function" then
		return nil
	end
	local mapID = C_QuestLog.GetMapForQuestPOIs()
	if type(mapID) ~= "number" then
		return nil
	end
	local quests = C_QuestLog.GetQuestsOnMap(mapID)
	for _, entry in ipairs(quests or {}) do
		if entry.questID == questID and type(entry.x) == "number" and type(entry.y) == "number" then
			return entry.mapID or mapID, entry.x, entry.y
		end
	end
end

-- The objectives still to do, in the order the list shows them. GetQuestObjectives is the client's own count record,
-- so the submenu never guesses an objective's place or state.
---@param questID number
---@return { text: string, index: integer }[]
local function UnfinishedObjectives(questID)
	local out = {}
	if type(C_QuestLog.GetQuestObjectives) ~= "function" then
		return out
	end
	local objectives = C_QuestLog.GetQuestObjectives(questID)
	for index, objective in ipairs(objectives or {}) do
		if objective.text and not objective.finished then
			out[#out + 1] = { text = objective.text, index = index }
		end
	end
	return out
end

---@param questID number
---@param text string
---@return boolean?, string?
local function RouteObjective(questID, text)
	local api = ShortestPath()
	if not api then
		return false, L["Shortest Path is not loaded."]
	end
	if InCombatLockdown() then
		return false, L["Unavailable in combat"]
	end
	local map, x, y = QuestPoint(questID)
	if not map then
		return false, L["There is no map pin for this quest."]
	end
	if api.Navigate("ForeverCore", map, x, y, text, "objective") then
		return true
	end
	return false, L["Shortest Path could not plan this route."]
end

---@param questID number
---@return boolean?, string?
local function OpenQuestMap(questID)
	if InCombatLockdown() then
		return false, L["Unavailable in combat"]
	end
	if type(QuestMapFrame_OpenToQuestDetails) == "function" then
		QuestMapFrame_OpenToQuestDetails(questID)
		return true
	end
	return false, L["The world map is not available."]
end

---@param questID number
---@return boolean?, string?
local function OpenQuestDetails(questID)
	if InCombatLockdown() then
		return false, L["Unavailable in combat"]
	end
	local questUtil = rawget(_G, "QuestUtil")
	if questUtil and type(questUtil.OpenQuestDetails) == "function" then
		questUtil.OpenQuestDetails(questID)
		return true
	end
	if type(QuestMapFrame_OpenToQuestDetails) == "function" then
		QuestMapFrame_OpenToQuestDetails(questID)
		return true
	end
	return false, L["The quest log is not available."]
end

-- The Objectives submenu. Every finished objective is left out, and the whole submenu is left out when Shortest Path
-- or the quest's map point is missing.
---@param menu ForeverTrackerMenuBuilder
---@param questID number
local function AddObjectivesSubmenu(menu, questID)
	if not ShortestPath() or not QuestPoint(questID) then
		return
	end
	local objectives = UnfinishedObjectives(questID)
	if #objectives == 0 then
		return
	end
	local submenu = menu:Submenu(L["Objectives"])
	if not submenu then
		return
	end
	submenu:SetScrollMode(400)
	submenu:CreateTitle(L["Route with Shortest Path"])
	for _, objective in ipairs(objectives) do
		local entry = submenu:CreateButton(objective.text, function()
			local function Route()
				local ok, reason = RouteObjective(questID, objective.text)
				if ok == false then
					Report(reason)
				end
			end
			if section and type(section.safeCall) == "function" then
				section.safeCall("quest objective route", Route)
			else
				Route()
			end
		end)
		if entry and InCombatLockdown() then
			entry:SetEnabled(false)
			if entry.SetTooltip then
				entry:SetTooltip(function(tooltip)
					tooltip:SetText(objective.text, 1, 1, 1)
					tooltip:AddLine(L["Unavailable in combat"], nil, nil, nil, true)
				end)
			end
		end
	end
end

-- The quest's title menu, on the same slots every Forever section uses. Core adds the Tracker submenu after the end
-- row, so Attach, Lock and the background are one click away from every quest.
---@param target ForeverTrackerTarget
---@param menu ForeverTrackerMenuBuilder
local function QuestMenu(target, menu)
	if target.kind == "section" then
		menu:Action(L["Turn off the Forever quest list (use the game's tracker)"], function()
			TrackerQuests.SetEnabled(false)
		end)
		return
	end
	local id = target.id
	if type(id) == "string" then
		local zone = id:match("^group:(.*)$")
		if not zone then
			return
		end
		menu:Title(zone)
		menu:Primary(IsZoneFolded(zone) and L["Expand"] or L["Collapse"], function()
			ToggleZone(zone)
		end)
		return
	end
	if type(id) ~= "number" then
		return
	end
	local questID = id
	local block = target.block
	local title = C_QuestLog.GetTitleForQuestID(questID)
		or (block and block.HeaderText and block.HeaderText:GetText())
		or L["Quest"]
	menu:Title(title)
	if C_SuperTrack.GetSuperTrackedQuestID() ~= questID then
		menu:Primary(GameString("SUPER_TRACK_QUEST", L["Focus"]), function()
			C_SuperTrack.SetSuperTrackedQuestID(questID)
		end)
	else
		menu:Primary(GameString("STOP_SUPER_TRACK_QUEST", L["Stop focusing"]), function()
			C_SuperTrack.SetSuperTrackedQuestID(0)
		end)
	end

	AddObjectivesSubmenu(menu, questID)

	menu:Action(GameString("OBJECTIVES_SHOW_QUEST_MAP", L["Open Quest Map"]), function()
		local ok, reason = OpenQuestMap(questID)
		if ok == false then
			Report(reason)
		end
	end, { combat = true })

	menu:Action(IsQuestFolded(questID) and L["Expand"] or L["Collapse"], function()
		ToggleQuest(questID)
	end)

	local questUtil = rawget(_G, "QuestUtil")
	local canRemove = not questUtil or not questUtil.CanRemoveQuestWatch or questUtil.CanRemoveQuestWatch() == true
	if canRemove then
		menu:Action(GameString("OBJECTIVES_STOP_TRACKING", L["Untrack"]), function()
			C_QuestLog.RemoveQuestWatch(questID)
		end)
	end

	if
		C_QuestLog.IsPushableQuest(questID)
		and IsInGroup()
		and questUtil
		and type(questUtil.ShareQuest) == "function"
	then
		menu:Action(GameString("SHARE_QUEST", L["Share Quest"]), function()
			questUtil.ShareQuest(questID)
		end)
	end

	menu:Action(GameString("SHARE_IN_CHAT", L["Share in Chat"]), function()
		local link = GetQuestLink(questID)
		if not link then
			Report(L["There is no quest link to share."])
			return
		end
		if not ChatFrameUtil or not ChatFrameUtil.InsertLink or not ChatFrameUtil.InsertLink(link) then
			if ChatFrameUtil and ChatFrameUtil.OpenChat then
				ChatFrameUtil.OpenChat(link)
			end
		end
	end)

	local details = (questUtil and questUtil.IsShowingQuestDetails and questUtil.IsShowingQuestDetails(questID))
			and GameString("OBJECTIVES_HIDE_VIEW_IN_QUESTLOG", L["Hide Quest Details"])
		or GameString("OBJECTIVES_VIEW_IN_QUESTLOG", L["Open Quest Details"])
	menu:Action(details, function()
		local ok, reason = OpenQuestDetails(questID)
		if ok == false then
			Report(reason)
		end
	end, { combat = true })

	menu:End(GameString("ABANDON_QUEST_ABBREV", L["Abandon"]), function()
		if InCombatLockdown() then
			Report(L["Unavailable in combat"])
			return
		end
		if type(QuestMapQuestOptions_AbandonQuest) == "function" then
			QuestMapQuestOptions_AbandonQuest(questID)
			return
		end
		Report(L["Abandoning a quest is not available."])
	end)
end

-- Left click keeps the first slice's action: focus the quest, which drives Shortest Path's route. Shift click keeps
-- the game's own untrack, and a click while the chat box is open inserts the quest link. A group heading folds.
---@param target ForeverTrackerTarget
---@param button string
---@return boolean?, string?
local function QuestClick(target, button)
	if target.kind ~= "block" or button ~= "LeftButton" then
		return false
	end
	local id = target.id
	if type(id) == "string" then
		local zone = id:match("^group:(.*)$")
		if zone then
			ToggleZone(zone)
			return true
		end
		return false
	end
	if type(id) ~= "number" then
		return false
	end
	local questID = id
	if ChatFrameUtil and type(ChatFrameUtil.TryInsertQuestLinkForQuestID) == "function" then
		if ChatFrameUtil.TryInsertQuestLinkForQuestID(questID) then
			return true
		end
	end
	if type(IsModifiedClick) == "function" and IsModifiedClick("QUESTWATCHTOGGLE") then
		local questUtil = rawget(_G, "QuestUtil")
		if not questUtil or not questUtil.CanRemoveQuestWatch or questUtil.CanRemoveQuestWatch() == true then
			C_QuestLog.RemoveQuestWatch(questID)
		end
		return true
	end
	C_SuperTrack.SetSuperTrackedQuestID(questID)
	return true
end

---@param target ForeverTrackerTarget
---@return string?
local function QuestClickHint(target)
	if target.kind ~= "block" then
		return nil
	end
	if type(target.id) == "string" then
		local zone = target.id:match("^group:(.*)$")
		if zone then
			return IsZoneFolded(zone) and L["unfold this zone"] or L["fold this zone"]
		end
		return nil
	end
	return L["focus this quest"]
end

---@type ForeverTrackerMenuContract
local QuestContract = { menu = QuestMenu, click = QuestClick, clickHint = QuestClickHint }

section = ns.TrackerSection.Create("ForeverCoreQuestTracker", QuestObjectiveTrackerMixin, {
	order = -10,
	header = TRACKER_HEADER_QUESTS,
	maxHeight = "remaining",
	contract = QuestContract,
})
if not section then
	EventUtil.ContinueAfterAllEvents(RegisterSettings, "PLAYER_ENTERING_WORLD", "VARIABLES_LOADED")
	return
end
---@cast section ForeverQuestTrackerModule

---@class ForeverQuestTrackerOverrides : ForeverQuestTrackerModule
local Overrides = {}

-- The native quest block shares its POI pool and a lazy manager cache with other Blizzard modules. Keep the same
-- template and presentation on our blocks, but give this section its own pool and read the POI preference directly.
local PrivatePOI = {}
---@param self any
function PrivatePOI:GetPOIButton(style)
	local module = self.parentModule
	if not module.questPOIPool then
		module.questPOIPool = CreateFramePool("BUTTON", nil, "ObjectiveTrackerPOIButtonTemplate")
	end
	local button = self.poiButton
	if not button then
		button = module.questPOIPool:Acquire()
		button:SetParent(self)
		button:SetQuestID(self.poiQuestID)
		self.poiButton = button
		self:SetExtraAddAnimation(button.AddAnim)
	end
	button:SetStyle(style)
	button:SetSelected(self.poiIsSuperTracked)
	button:UpdateButtonStyle()
	button:Show()
	return button
end
---@param self any
function PrivatePOI:CheckAndReleasePOIButton()
	if self.poiButton then
		self.parentModule.questPOIPool:Release(self.poiButton)
		self.poiButton = nil
		self:SetExtraAddAnimation(nil)
		self:SetPOIInfo()
	end
end
---@param self any
function PrivatePOI:OnLayout()
	if self.poiQuestID and GetCVarBool("questPOI") then
		self:AddPOIButton()
	else
		self:CheckAndReleasePOIButton()
	end
	ObjectiveTrackerAnimBlockMixin.OnLayout(self)
end

-- GetBlock resets and anchors the section's own frame; OnLayout runs later, from LayoutBlock.
local getPrivateBlock = section.GetBlock
function Overrides:GetBlock(id, template)
	local block, existing = getPrivateBlock(self, id, template)
	Mixin(block, PrivatePOI)
	return block, existing
end

-- One thin fill under each unfinished count objective: the client's status bar fill over the template's backing
-- colour, four UI units high, with no border and no label. The bar is anchored to the line's own text column, so it
-- follows the item button and the scrollbar gutter without a second layout.
local THIN_BAR_HEIGHT = 4
local THIN_BAR_GAP = 3
local THIN_BAR_ATLAS = "widgetstatusbar-fill-blue"
local THIN_BAR_BACK = { 0.04, 0.07, 0.18, 1 }

---@param module ForeverQuestTrackerModule
---@return any
local function AcquireThinBar(module)
	local pool = module.thinBarPool or {}
	module.thinBarPool = pool
	local bar = table.remove(pool)
	if not bar then
		bar = CreateFrame("Frame", nil, module.ContentsFrame)
		bar:SetHeight(THIN_BAR_HEIGHT)
		local background = bar:CreateTexture(nil, "BACKGROUND")
		background:SetAllPoints(bar)
		background:SetColorTexture(THIN_BAR_BACK[1], THIN_BAR_BACK[2], THIN_BAR_BACK[3], THIN_BAR_BACK[4])
		local fill = bar:CreateTexture(nil, "ARTWORK")
		-- art-ok: the client's status bar fill, the same atlas the tracker's own progress bar uses
		fill:SetAtlas(THIN_BAR_ATLAS)
		fill:SetPoint("TOPLEFT")
		fill:SetPoint("BOTTOMLEFT")
		bar.background, bar.fill = background, fill
	end
	bar:Show()
	return bar
end

---@param module ForeverQuestTrackerModule
---@param bar any
local function ReleaseThinBar(module, bar)
	bar:Hide()
	bar:ClearAllPoints()
	bar.fraction = nil
	local pool = module.thinBarPool or {}
	module.thinBarPool = pool
	pool[#pool + 1] = bar
end

---@param module ForeverQuestTrackerModule
---@param block any
local function ClearThinBars(module, block)
	if type(block.thinBars) ~= "table" then
		return
	end
	for _, bar in pairs(block.thinBars) do
		ReleaseThinBar(module, bar)
	end
	block.thinBars = {}
end

---@param module ForeverQuestTrackerModule
---@param block any
---@param line any
---@param objectiveIndex integer
---@param fraction number
local function AddThinBar(module, block, line, objectiveIndex, fraction)
	local bar = AcquireThinBar(module)
	bar:SetParent(block)
	bar:SetHeight(THIN_BAR_HEIGHT)
	block:AddCustomRegion(bar, 0, -THIN_BAR_GAP)
	bar:ClearAllPoints()
	-- The region is also the next objective's anchor, so keep its left edge on the line, not its indented text.
	bar:SetPoint("TOPLEFT", line, "BOTTOMLEFT", 0, -THIN_BAR_GAP)
	bar:SetPoint("TOPRIGHT", line, "BOTTOMRIGHT", 0, -THIN_BAR_GAP)
	bar.background:ClearAllPoints()
	bar.background:SetPoint("TOPLEFT", line.Text, "BOTTOMLEFT", 0, -THIN_BAR_GAP)
	bar.background:SetPoint("BOTTOMRIGHT", bar, "BOTTOMRIGHT", 0, 0)
	bar.fill:ClearAllPoints()
	bar.fill:SetPoint("TOPLEFT", bar.background, "TOPLEFT", 0, 0)
	bar.fill:SetPoint("BOTTOMLEFT", bar.background, "BOTTOMLEFT", 0, 0)
	bar.fraction = fraction
	block.thinBars = block.thinBars or {}
	block.thinBars[objectiveIndex] = bar
	module.activeThinBars = module.activeThinBars or {}
	module.activeThinBars[#module.activeThinBars + 1] = bar
end

---@param module ForeverQuestTrackerModule
local function FitThinBars(module)
	for _, bar in ipairs(type(module.activeThinBars) == "table" and module.activeThinBars or {}) do
		local width = bar.background:GetWidth() or 0
		bar.fill:SetWidth(math.max(0, width * (bar.fraction or 0)))
	end
end

-- The fraction a count line has done. The client's own objective record is the only source: a line whose text
-- happens to read like a count but has no record gets no bar.
---@param objectives any
---@param objectiveIndex integer
---@return number?
local function CountFraction(objectives, objectiveIndex)
	local objective = objectives and objectives[objectiveIndex]
	if not objective then
		return nil
	end
	if type(objective.numFulfilled) ~= "number" or type(objective.numRequired) ~= "number" then
		return nil
	end
	local done, required = objective.numFulfilled, objective.numRequired
	if required >= 2 and not objective.finished and done < required then
		return math.max(0, math.min(1, done / required))
	end
end

-- Quest item buttons are protected in the client, so the pool is fixed, built from SecureActionButtonTemplate, and
-- given its item only out of combat. A quest that needs one takes the next free button; a button scrolled out of the
-- viewport is hidden, never only clipped.
-- The cap is the smallest pool that can never run out: the client's tallest tracker is 1000 units (Edit Mode Height),
-- and a quest with an item is at least the item button tall, 26 units, so at most 38 of them fit on screen. 40 leaves
-- room for a block boundary and the button's overhang.
local ITEM_POOL_SIZE = 40
local ITEM_SIZE = 26
local ITEM_SPACING = 2
local ITEM_ART = "UI-QuestTrackerButton-QuestItem-Frame"
local ITEM_GLOW_ART = "UI-QuestTrackerButton-QuestItem-Frame-Glow"
local ITEM_HIGHLIGHT = "Interface\\Buttons\\ButtonHilight-Square"
local ITEM_RANGE_DELAY = rawget(_G, "TOOLTIP_UPDATE_TIME") or 0.2

-- The client's quest item look and behavior on a secure button. The secure template performs the click, so no
-- script here calls UseQuestLogSpecialItem, which the client refuses from addon code.
local ItemButton = {}

function ItemButton:UpdateCooldown()
	if not self.questLogIndex or type(GetQuestLogSpecialItemCooldown) ~= "function" then
		return
	end
	local start, duration, enable = GetQuestLogSpecialItemCooldown(self.questLogIndex)
	if not start or not self.Cooldown then
		return
	end
	if type(CooldownFrame_Set) == "function" then
		CooldownFrame_Set(self.Cooldown, start, duration, enable)
	elseif self.Cooldown.SetCooldown then
		self.Cooldown:SetCooldown(start, duration)
	end
	if type(SetItemButtonTextureVertexColor) ~= "function" then
		return
	end
	if duration and duration > 0 and enable == 0 then
		SetItemButtonTextureVertexColor(self, 0.4, 0.4, 0.4)
	else
		SetItemButtonTextureVertexColor(self, 1, 1, 1)
	end
end

-- Attribute writes are protected on a secure button, so SetUp runs only from PlaceItemButtons out of combat.
function ItemButton:SetUp(questLogIndex)
	if InCombatLockdown() or type(GetQuestLogSpecialItemInfo) ~= "function" then
		return
	end
	local link, item, charges = GetQuestLogSpecialItemInfo(questLogIndex)
	self.questLogIndex = questLogIndex
	self.charges = charges
	self.rangeTimer = -1
	self:SetAttribute("item", link)
	if type(SetItemButtonTexture) == "function" then
		SetItemButtonTexture(self, item)
	end
	if type(SetItemButtonCount) == "function" then
		SetItemButtonCount(self, charges)
	end
	self:UpdateCooldown()
end

function ItemButton:OnUpdate(elapsed)
	if self.rangeTimer == nil or not self.questLogIndex then
		return
	end
	local timer = self.rangeTimer - elapsed
	if timer > 0 then
		self.rangeTimer = timer
		return
	end
	if type(GetQuestLogSpecialItemInfo) ~= "function" then
		self.rangeTimer = nil
		self.HotKey:Hide()
		return
	end
	local link, _, charges = GetQuestLogSpecialItemInfo(self.questLogIndex)
	if not link then
		self.rangeTimer = nil
		self.HotKey:Hide()
		return
	end
	if charges ~= self.charges then
		self.charges = charges
		if type(SetItemButtonCount) == "function" then
			SetItemButtonCount(self, charges)
		end
	end
	local valid = type(IsQuestLogSpecialItemInRange) == "function" and IsQuestLogSpecialItemInRange(self.questLogIndex)
	if valid == 0 then
		self.HotKey:Show()
		self.HotKey:SetVertexColor(1, 0.1, 0.1)
	elseif valid == 1 then
		self.HotKey:Show()
		self.HotKey:SetVertexColor(0.6, 0.6, 0.6)
	else
		self.HotKey:Hide()
	end
	self.rangeTimer = ITEM_RANGE_DELAY
end

function ItemButton:OnEvent(event)
	if event == "PLAYER_TARGET_CHANGED" then
		self.rangeTimer = -1
	elseif event == "BAG_UPDATE_COOLDOWN" then
		self:UpdateCooldown()
	end
end

function ItemButton:OnShow()
	self:RegisterEvent("PLAYER_TARGET_CHANGED")
	self:RegisterEvent("BAG_UPDATE_COOLDOWN")
end

function ItemButton:OnHide()
	self:UnregisterEvent("PLAYER_TARGET_CHANGED")
	self:UnregisterEvent("BAG_UPDATE_COOLDOWN")
end

function ItemButton:OnEnter()
	if not self.questLogIndex or not GameTooltip then
		return
	end
	GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
	if GameTooltip.SetQuestLogSpecialItem then
		GameTooltip:SetQuestLogSpecialItem(self.questLogIndex)
	else
		GameTooltip:SetText(self.questLogIndex)
	end
end

function ItemButton.OnLeave()
	if GameTooltip then
		GameTooltip:Hide()
	end
end

---@param parent Frame
---@param index integer
---@return any
local function CreateItemButton(parent, index)
	local button = CreateFrame("Button", nil, parent, "SecureActionButtonTemplate") --[[@as ForeverQuestItemButton]]
	button:SetSize(ITEM_SIZE, ITEM_SIZE)
	button:RegisterForClicks("AnyUp")
	button:SetAttribute("type", "item")
	button.foreverIndex = index

	local glow = button:CreateTexture(nil, "BACKGROUND")
	glow:SetAtlas(ITEM_GLOW_ART, true)
	glow:SetPoint("CENTER")
	glow:Hide()
	button.Glow = glow

	local hotKey = button:CreateFontString(nil, "ARTWORK", "NumberFontNormalSmallGray")
	hotKey:SetJustifyH("LEFT")
	hotKey:SetSize(29, 10)
	hotKey:SetPoint("TOPRIGHT", 16, -2)
	hotKey:SetText(rawget(_G, "RANGE_INDICATOR") or "")
	button.HotKey = hotKey

	local icon = button:CreateTexture(nil, "BORDER")
	icon:SetAllPoints(button)
	button.icon = icon

	local count = button:CreateFontString(nil, "BORDER", "NumberFontNormal")
	count:SetJustifyH("RIGHT")
	count:SetPoint("BOTTOMRIGHT", -3, 2)
	count:Hide()
	button.Count = count

	local cooldown = CreateFrame("Cooldown", nil, button, "CooldownFrameTemplate") --[[@as Cooldown]]
	cooldown:SetAllPoints(button)
	button.Cooldown = cooldown

	local normal = button:CreateTexture(nil, "ARTWORK")
	normal:SetAtlas(ITEM_ART, true)
	normal:SetPoint("CENTER")
	button:SetNormalTexture(normal)

	local pushed = button:CreateTexture(nil, "ARTWORK")
	pushed:SetAtlas(ITEM_ART, true)
	pushed:SetPoint("CENTER")
	button:SetPushedTexture(pushed)

	local highlight = button:CreateTexture(nil, "HIGHLIGHT")
	highlight:SetTexture(ITEM_HIGHLIGHT)
	highlight:SetBlendMode("ADD")
	highlight:SetAllPoints(button)
	button:SetHighlightTexture(highlight)

	Mixin(button, ItemButton)
	button:SetScript("OnUpdate", ItemButton.OnUpdate)
	button:SetScript("OnEvent", ItemButton.OnEvent)
	button:SetScript("OnShow", ItemButton.OnShow)
	button:SetScript("OnHide", ItemButton.OnHide)
	button:SetScript("OnEnter", ItemButton.OnEnter)
	button:SetScript("OnLeave", ItemButton.OnLeave)
	button:Hide()
	return button
end

---@param module ForeverQuestTrackerModule
local function CreateItemPool(module)
	if module.itemButtons or not module.ContentsFrame or InCombatLockdown() then
		return
	end
	local buttons = {}
	for index = 1, ITEM_POOL_SIZE do
		local ok, button = pcall(CreateItemButton, module.ContentsFrame, index)
		if not ok or not button then
			module.itemButtons = nil
			return
		end
		buttons[index] = button
	end
	module.itemButtons = buttons
end

---@param questLogIndex number
---@param isComplete boolean
---@return boolean
local function QuestShowsItem(questLogIndex, isComplete)
	local questUtil = rawget(_G, "QuestUtil")
	if questUtil and type(questUtil.QuestShowsItemByIndex) == "function" then
		return questUtil.QuestShowsItemByIndex(questLogIndex, isComplete) == true
	end
	if type(GetQuestLogSpecialItemInfo) ~= "function" then
		return false
	end
	local link, _, _, showItemWhenComplete = GetQuestLogSpecialItemInfo(questLogIndex)
	return link ~= nil and (not isComplete or showItemWhenComplete == true)
end

---@param module ForeverQuestTrackerModule
local function HideItems(module)
	if type(module.itemButtons) ~= "table" or InCombatLockdown() then
		return
	end
	for _, button in ipairs(module.itemButtons) do
		button:Hide()
		button.questLogIndex = nil
		button:SetAttribute("item", nil)
	end
end

---@param module ForeverQuestTrackerModule
local function DimItems(module)
	local alpha = module.combatChangeQueued and 0.5 or 1
	if type(module.itemButtons) ~= "table" then
		return
	end
	for _, button in ipairs(module.itemButtons) do
		button:SetAlpha(alpha)
	end
end

-- Gives each fully visible quest with an item the next free button. The rest of the pool stays hidden, which keeps a
-- button scrolled out of view from taking a click. The parent is the block, so a button follows its quest through
-- every scroll step without a second anchor.
---@param module ForeverQuestTrackerModule
local function PlaceItemButtons(module)
	local buttons = module.itemButtons
	if type(buttons) ~= "table" or InCombatLockdown() then
		return
	end
	if not TrackerQuests.Enabled() or ownedByOther then
		HideItems(module)
		return
	end
	for _, button in ipairs(buttons) do
		local old = button.foreverBlock
		if old and old.foreverItemButton == button then
			old.foreverItemButton = nil
		end
		button.foreverBlock = nil
	end
	local scroll = module.scrollFrame
	local viewTop = scroll and scroll:GetTop()
	local viewBottom = scroll and scroll:GetBottom()
	local nextButton = 1
	local block = module.firstBlock
	while block do
		local visible = true
		if viewTop and viewBottom and block.GetTop and block.GetBottom and block:GetTop() and block:GetBottom() then
			visible = block:GetTop() <= viewTop + 0.5 and block:GetBottom() >= viewBottom - 0.5
		end
		if block.hasItem and visible and nextButton <= #buttons then
			local button = buttons[nextButton]
			nextButton = nextButton + 1
			if button:GetParent() ~= block then
				button:SetParent(block)
			end
			button:ClearAllPoints()
			button:SetPoint("TOPRIGHT", block, "TOPRIGHT", 0, 0)
			if type(button.SetUp) == "function" then
				button:SetUp(block.itemQuestLogIndex)
			end
			button.foreverBlock = block
			block.foreverItemButton = button
			button.questLogIndex = block.itemQuestLogIndex
			button:Show()
			button:SetAlpha(module.combatChangeQueued and 0.5 or 1)
		end
		block = block.nextBlock
	end
	for index = nextButton, #buttons do
		local button = buttons[index]
		button:Hide()
		button.questLogIndex = nil
	end
end

---@param module ForeverQuestTrackerModule
local function QueueCombatChange(module)
	if module.combatChangeQueued then
		return
	end
	module.combatChangeQueued = true
	DimItems(module)
end

---@param module ForeverQuestTrackerModule
local function ClearCombatChange(module)
	if not module.combatChangeQueued or InCombatLockdown() then
		return
	end
	module.combatChangeQueued = false
	DimItems(module)
end

-- Read scalar quest data directly. QuestCache:Get lazily writes Blizzard's shared cache and event listener.
local function QuestData(questID)
	local index = C_QuestLog.GetLogIndexForQuestID(questID)
	local info = index and C_QuestLog.GetInfo(index)
	return {
		questID = questID,
		title = info and info.title,
		isTask = info and info.isTask,
		isBounty = info and info.isBounty,
		isAutoComplete = info and info.isAutoComplete,
	},
		index
end

---@param quest any
---@return boolean
function Overrides.ShouldDisplayQuest(_, quest)
	if not quest then
		return false
	end
	if C_QuestLog.IsQuestDisabledForSession(quest.questID) then
		return false
	end
	-- Match the native normal and campaign filters, including campaign quests marked as tasks.
	if C_QuestInfoSystem.GetQuestClassification(quest.questID) == Enum.QuestClassification.Campaign then
		return CampaignQuestObjectiveTrackerMixin ~= nil
	end
	return not quest.isTask and not quest.isBounty
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

-- The header count's second number: the quests the log holds, headers and hidden entries left out.
---@return integer
local function QuestLogCount()
	local total = 0
	for index = 1, C_QuestLog.GetNumQuestLogEntries() do
		local info = C_QuestLog.GetInfo(index)
		if info and not info.isHeader and not info.isHidden and info.questID then
			total = total + 1
		end
	end
	return total
end

---@return ForeverQuestRecord[]
function Overrides:Records()
	local zones, onMap = LogZones()
	local records = {}
	-- One record per quest: the client's watch list is read by index and can answer the same quest ID twice, and the
	-- section keeps one block per ID. Asking for that block twice in one layout pass makes Blizzard anchor it under
	-- itself, which the client refuses with "Cannot anchor to a region dependent on it" (#609).
	local seen = {}
	local count = C_QuestLog.GetNumQuestWatches()
	for index = 1, count do
		local questID = C_QuestLog.GetQuestIDForQuestWatchIndex(index)
		if questID and not seen[questID] then
			seen[questID] = true
			local quest = QuestData(questID)
			if self:ShouldDisplayQuest(quest) then
				local distanceSq = C_QuestLog.GetDistanceSqToQuest(questID)
				records[#records + 1] = {
					questID = questID,
					title = C_QuestLog.GetTitleForQuestID(questID) or (quest and quest.title) or "",
					zone = zones[questID] or "",
					ready = C_QuestLog.ReadyForTurnIn(questID) == true or C_QuestLog.IsComplete(questID),
					onMap = onMap[questID] == true,
					distanceSq = type(distanceSq) == "number" and distanceSq or nil,
				}
			end
		end
	end
	return records
end

-- Adapted from QuestObjectiveTrackerMixin:DoQuestObjectives. The native progress bar template is replaced by the thin
-- fill style B: one 4-unit bar under every unfinished count line, no per-quest bar, and no full template bar.
---@param block any
---@param questCompleted boolean
---@param questSequenced boolean
---@param isExistingBlock boolean
---@param useFullHeight boolean
---@return boolean
function Overrides:DoQuestObjectives(block, questCompleted, questSequenced, isExistingBlock, useFullHeight)
	local questID = block.id
	local objectiveCompleting = false
	local questLogIndex = C_QuestLog.GetLogIndexForQuestID(questID)
	local numObjectives = GetNumQuestLeaderBoards(questLogIndex)
	local suppressProgressPercentageInObjectiveText = true
	local objectives = type(C_QuestLog.GetQuestObjectives) == "function" and C_QuestLog.GetQuestObjectives(questID)
		or nil
	-- The third argument is the client's suppressProgressPercentageInObjectiveText, which the API annotations omit.
	---@type any
	local leaderBoard = GetQuestLogLeaderBoard
	for objectiveIndex = 1, numObjectives do
		local text, _, finished = leaderBoard(objectiveIndex, questLogIndex, suppressProgressPercentageInObjectiveText)
		if text then
			local line = block:GetExistingLine(objectiveIndex)
			if questCompleted then
				if line and line.state ~= ObjectiveTrackerAnimLineState.Faded then
					line = block:AddObjective(
						objectiveIndex,
						text,
						nil,
						useFullHeight,
						OBJECTIVE_DASH_STYLE_HIDE,
						OBJECTIVE_TRACKER_COLOR["Complete"]
					)
					if not line.state or line.state == ObjectiveTrackerAnimLineState.Present then
						line:SetState(ObjectiveTrackerAnimLineState.Completing)
					end
				end
			else
				if finished then
					if line and line.state == ObjectiveTrackerAnimLineState.Faded then
						line = nil
					elseif line then
						line = block:AddObjective(
							objectiveIndex,
							text,
							nil,
							useFullHeight,
							OBJECTIVE_DASH_STYLE_HIDE,
							OBJECTIVE_TRACKER_COLOR["Complete"]
						)
						if not line.state or line.state == ObjectiveTrackerAnimLineState.Present then
							line:SetState(ObjectiveTrackerAnimLineState.Completing)
						end
					else
						if not questSequenced then
							line = block:AddObjective(
								objectiveIndex,
								text,
								nil,
								useFullHeight,
								OBJECTIVE_DASH_STYLE_HIDE,
								OBJECTIVE_TRACKER_COLOR["Complete"]
							)
							line:SetState(ObjectiveTrackerAnimLineState.Completed)
						end
					end
				else
					local skipObjective = not line and questSequenced and objectiveCompleting
					if not skipObjective then
						if questSequenced and isExistingBlock and not line then
							line = block:AddObjective(objectiveIndex, text, nil, useFullHeight)
							line:SetState(ObjectiveTrackerAnimLineState.Adding)
							PlaySound(SOUNDKIT.UI_QUEST_ROLLING_FORWARD_01)
						else
							line = block:AddObjective(objectiveIndex, text, nil, useFullHeight)
							if line.state == ObjectiveTrackerAnimLineState.Completed then
								line:SetState(ObjectiveTrackerAnimLineState.Present)
							end
						end
						local fraction = CountFraction(objectives, objectiveIndex)
						if line and fraction ~= nil then
							AddThinBar(self, block, line, objectiveIndex, fraction)
						end
					end
				end
			end
			if line and line.state == ObjectiveTrackerAnimLineState.Completing then
				objectiveCompleting = true
			end
		end
	end
	if questCompleted and not objectiveCompleting then
		block:ForEachUsedLine(function(line)
			if line.state == ObjectiveTrackerAnimLineState.Completed then
				line:SetState(ObjectiveTrackerAnimLineState.Fading)
			end
		end)
	end
	return objectiveCompleting
end

-- Adapted from QuestObjectiveTrackerMixin:UpdateSingle. A quest with a special item reserves the button's column
-- before any line is set, so the title and objectives clear it. The button itself is attached after layout, from the
-- fixed pool, which keeps the block free of secure frames until it is drawn.
---@param record ForeverQuestRecord
---@return boolean
function Overrides:UpdateQuest(record)
	local questID = record.questID
	local quest, questLogIndex = QuestData(questID)
	local isComplete = C_QuestLog.IsComplete(questID)
	local isSuperTracked = questID == C_SuperTrack.GetSuperTrackedQuestID()
	local useFullHeight = true
	local shouldShowWaypoint = isSuperTracked or questID == QuestMapFrame_GetFocusedQuestID()
	local isSequenced = IsQuestSequenced(questID)
	local block, isExistingBlock = self:GetBlock(questID)
	local tagText = self:GetQuestTagText(questID)

	ClearThinBars(self, block)
	block.hasItem = false
	block.itemQuestLogIndex = nil
	if questLogIndex and QuestShowsItem(questLogIndex, isComplete) then
		block.hasItem = true
		block.itemQuestLogIndex = questLogIndex
		block:AdjustRightEdgeOffset(-ITEM_SIZE - ITEM_SPACING)
	end

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

	if IsQuestFolded(questID) then
		if block.hasItem then
			block.height = math.max(block.height or 0, ITEM_SIZE)
		end
		block:SetPOIInfo(questID, isComplete, isSuperTracked)
		return self:LayoutBlock(block)
	end

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

	if block.hasItem then
		block.height = math.max(block.height or 0, ITEM_SIZE)
	end
	block:SetPOIInfo(questID, isComplete, isSuperTracked)
	return self:LayoutBlock(block)
end

function Overrides:LayoutContents()
	if not TrackerQuests.Enabled() or ownedByOther then
		HideItems(self)
		return
	end
	self.activeThinBars = {}
	local records = self:Records()
	local groups = ns.QuestOrder(records)
	local header = (L["%s %d/%d"]):format(GameString("TRACKER_HEADER_QUESTS", L["Quests"]), #records, QuestLogCount())
	self:SetHeader(header)
	for _, group in ipairs(groups) do
		local folded = IsZoneFolded(group.title)
		local block = self:GetBlock("group:" .. group.title)
		block:SetHeader(folded and (L["%s (%d)"]):format(group.title, #group.quests) or group.title)
		if not self:LayoutBlock(block) then
			FitThinBars(self)
			PlaceItemButtons(self)
			return
		end
		if not folded then
			for _, record in ipairs(group.quests) do
				if not self:UpdateQuest(record) then
					FitThinBars(self)
					PlaceItemButtons(self)
					return
				end
			end
		end
	end
	FitThinBars(self)
	PlaceItemButtons(self)
end

function Overrides.CanUpdate()
	return not InCombatLockdown()
end

-- A block going back to the pool gives its bars and its item button back first; a later quest reuses both.
---@param block any
function Overrides:OnFreeBlock(block)
	ClearThinBars(self, block)
	local button = block.foreverItemButton
	if button then
		if not InCombatLockdown() then
			button:Hide()
		end
		button.foreverBlock = nil
		block.foreverItemButton = nil
	end
	block.hasItem = false
	block.itemQuestLogIndex = nil
	if QuestObjectiveTrackerMixin.OnFreeBlock then
		QuestObjectiveTrackerMixin.OnFreeBlock(self, block)
	end
end

-- The list follows the panel's scroll: a frozen view keeps each secure item button beside its quest. This is also
-- where a bar's fill gets its final width, after the block has been laid out at the column's current width.
function Overrides:OnScrollChanged()
	FitThinBars(self)
	PlaceItemButtons(self)
end

for _, event in ipairs({
	"PLAYER_ENTERING_WORLD",
	"PLAYER_REGEN_ENABLED",
	"QUEST_LOG_UPDATE",
	"QUEST_WATCH_LIST_CHANGED",
	"QUEST_WATCH_UPDATE",
	"QUEST_TURNED_IN",
	"QUEST_POI_UPDATE",
	"CVAR_UPDATE",
	"SUPER_TRACKING_CHANGED",
	"SUPER_TRACKING_PATH_UPDATED",
	"ZONE_CHANGED_NEW_AREA",
	"ADDON_LOADED",
}) do
	section:RegisterEvent(event)
end

---@param event string
function Overrides:OnEvent(event, cvar)
	if event == "CVAR_UPDATE" and cvar ~= "questPOI" then
		return
	end
	if event == "PLAYER_REGEN_ENABLED" or event == "ADDON_LOADED" or event == "PLAYER_ENTERING_WORLD" then
		ClearCombatChange(self)
		if apply then
			apply()
		end
		return
	end
	if InCombatLockdown() then
		QueueCombatChange(self)
	end
	self:MarkDirty()
end

-- Mixin copies at call time: every override, OnEvent included, must be defined before this line.
Mixin(section, Overrides)
section.OnScrollChanged = Overrides.OnScrollChanged
CreateItemPool(section)

-- The one-time hint beside the Quests header: what the list is, where its switch lives, and one click back to the
-- game's tracker. It is the client's own tutorial box (GlowBoxTemplate, art only, no Blizzard script) on a frame of
-- ours. It shows while the list is drawn in place of the game's tracker, out of combat, until the player picks either
-- button; `questListHintDone` records that choice for the account, and a missing key means not yet answered.
local HINT_TEXT = "This is the Forever quest list, shown in place of the game's quest tracker. To switch it off "
	.. "later, right-click the Quests header, or untick Forever quest list in Options > AddOns > ForeverCore."
local HINT_WIDTH = 260
local HINT_PAD = 14
local HINT_GAP = 12
---@type any
local hint

---@return boolean
local function HintDone()
	local db = Database()
	return type(db) ~= "table" or db.questListHintDone == true
end

local function AnswerHint()
	local db = Database()
	if type(db) == "table" then
		db.questListHintDone = true
	end
	if hint then
		hint:Hide()
	end
end

---@param button any
local function FitHintButton(button)
	button:SetWidth(math.max(90, math.ceil(button:GetTextWidth() or 0) + 24))
end

---@return any
local function HintFrame()
	if hint then
		return hint
	end
	local frame = CreateFrame("Frame", nil, UIParent, "GlowBoxTemplate")
	frame:SetFrameStrata("DIALOG")
	frame:SetClampedToScreen(true)
	frame:EnableMouse(true)
	frame:SetWidth(HINT_WIDTH)

	local text = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightLeft")
	text:SetPoint("TOPLEFT", HINT_PAD, -HINT_PAD)
	text:SetWidth(HINT_WIDTH - 2 * HINT_PAD)
	text:SetJustifyH("LEFT")
	text:SetJustifyV("TOP")
	text:SetText(L[HINT_TEXT])

	local off = CreateFrame("Button", nil, frame, "SharedButtonSmallTemplate")
	off:SetHeight(22)
	off:SetText(L["Use the game's tracker"])
	FitHintButton(off)
	off:SetPoint("BOTTOMLEFT", HINT_PAD, HINT_PAD)
	off:SetScript("OnClick", function()
		AnswerHint()
		TrackerQuests.SetEnabled(false)
	end)

	local keep = CreateFrame("Button", nil, frame, "SharedButtonSmallTemplate")
	keep:SetHeight(22)
	keep:SetText(L["Keep this list"])
	FitHintButton(keep)
	keep:SetPoint("LEFT", off, "RIGHT", 8, 0)
	keep:SetScript("OnClick", AnswerHint)

	-- A long translation widens the box rather than letting a button leave it.
	local buttons = off:GetWidth() + 8 + keep:GetWidth()
	local width = math.max(HINT_WIDTH, buttons + 2 * HINT_PAD)
	frame:SetWidth(width)
	text:SetWidth(width - 2 * HINT_PAD)
	frame:SetHeight((text:GetStringHeight() or 0) + 22 + 3 * HINT_PAD)

	frame.Text, frame.Off, frame.Keep = text, off, keep
	frame:Hide()
	hint = frame
	return frame
end

-- Show the hint beside the list on the side with room, or hide it. The list must be the one drawn (on, not stepped
-- aside for another tracker, and visible), and a hint never opens in combat: PLAYER_REGEN_ENABLED runs apply again.
local function RefreshHint()
	local wanted = ready
		and not HintDone()
		and TrackerQuests.Enabled()
		and not ownedByOther
		and section:IsVisible()
		and not InCombatLockdown()
	if not wanted then
		if hint then
			hint:Hide()
		end
		return
	end
	local frame = HintFrame()
	frame:ClearAllPoints()
	local x = section:GetCenter()
	local screen = UIParent:GetWidth()
	if x and screen and x < screen / 2 then
		frame:SetPoint("TOPLEFT", section, "TOPRIGHT", HINT_GAP, 0)
	else
		frame:SetPoint("TOPRIGHT", section, "TOPLEFT", -HINT_GAP, 0)
	end
	frame:Show()
end
section:HookScript("OnShow", RefreshHint)
section:HookScript("OnHide", RefreshHint)

apply = function()
	if not ready then
		return
	end
	CreateItemPool(section)
	ownedByOther = OtherOwner()
	local active = TrackerQuests.Enabled() and not ownedByOther
	hideNativeTracker = active
	ApplyNativeVisibility()
	if not active then
		HideItems(section)
	end
	section:MarkDirty()
	RefreshHint()
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
			if
				OtherOwner() ~= ownedByOther
				or (not ownedByOther and (host.IsAttached(section) ~= true or section:IsShown()))
			then
				apply()
			end
		end)
	end
end, "PLAYER_ENTERING_WORLD", "VARIABLES_LOADED")
