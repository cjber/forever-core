---@type string, ForeverTrackerNamespace
local _, ns = ...

-- The optional Forever quest list: the watched quests, campaign quests included, grouped ready-to-turn-in first, then
-- this zone, then every other zone, each nearest first. It is a section of the shared Forever column, built from the
-- game's own ObjectiveTrackerModuleTemplate and QuestObjectiveTrackerMixin so its header, lines, POI button, fonts,
-- colours, completed fade and layout are the game's. While this list is on, the game's own Quests and Campaign modules
-- leave the client's tracker through its own RemoveModule, so no empty Quests header is left above this one, and come
-- back through its AddModule when the list is off. One secure post-hook on the tracker's AddModule, and no replaced
-- method, moved module or reparented frame, is the whole of the client code this file touches.
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
	.. "rest by zone, nearest first. The game's own quest list is hidden while this is on."
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

-- The game's own quest modules, by the names the client's tracker holds them under. The Forever list replaces them
-- while it is on and gives them back when it is off.
local NATIVE_MODULES = { "QuestObjectiveTracker", "CampaignQuestObjectiveTracker" }

-- What the game's own Quests and Campaign modules do while the Forever list is on. Collapsing them is not enough: a
-- collapsed module still draws its header over an empty contents frame, which is the bare "Quests" header a player saw
-- above the Forever list's own "Quests 11/30". So each module leaves the tracker's module list, which stops the
-- client's own layout from laying it out or showing it again, and its own Update is called with no available height:
-- it adds no block, and its EndLayout hides it, exactly as the client leaves a module with no room left in the column.
-- Giving the list back is the same pair of the client's methods in reverse, so the game's own Quests section returns
-- as it was, folded or not, just as if the Forever list had never been on.
--
-- Every call is a public method of the client's own objective tracker, made out of combat only, from the same deferred
-- pass this file already used to collapse the modules: the container's RemoveModule and AddModule, and the module's
-- Update. The one hook is a secure post-hook on ObjectiveTrackerFrame.AddModule, installed below and never a
-- replacement of the method; no protected frame is reparented or hidden by addon code, and no secure quest item button
-- is shown, hidden or moved here: the module hides itself through its own layout, so nothing the client does later
-- with its own frames is tainted.
--
-- Each module is checked against the tracker on every pass rather than remembered by one flag: the client's own
-- ObjectiveTrackerManager adds its modules at PLAYER_ENTERING_WORLD, and this file's first pass can run before that,
-- so a module is taken whenever the tracker holds it, and only a module taken here is given back.
---@type table<string, boolean>
local taken = {}
-- True only around this file's own AddModule give-back, so the AddModule post-hook below knows the join it sees is
-- the list returning a module to the client, not the client adding one to be taken.
local givingBack = false
---@param drawn boolean whether the game's own quest modules should draw
local function SetNativeModulesDrawn(drawn)
	local tracker = ObjectiveTrackerFrame
	for _, name in ipairs(NATIVE_MODULES) do
		local module = rawget(_G, name)
		if module then
			if drawn then
				if taken[name] then
					givingBack = true
					tracker:AddModule(module)
					givingBack = false
					module:MarkDirty()
					taken[name] = nil
				end
			elseif tracker:HasModule(module) then
				tracker:RemoveModule(module)
				module:Update(0)
				taken[name] = true
			end
		end
	end
end

local ready = false
local ownedByOther = false
local section
---@type boolean?
local pendingNative

-- The game's modules are taken out and given back only out of combat. A change asked for in combat is remembered and
-- applied at PLAYER_REGEN_ENABLED, which this section's own OnEvent already runs apply() from, like every other
-- deferred layout change: the secure item buttons inside the game's modules never move while the player is fighting.
---@param replace boolean whether the Forever list replaces the game's own modules
local function ApplyNativeModules(replace)
	if InCombatLockdown() then
		pendingNative = replace
		return
	end
	if pendingNative ~= nil then
		replace = pendingNative
	end
	pendingNative = nil
	SetNativeModulesDrawn(not replace)
end

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
---@return table
local function CharacterState()
	if type(ForeverCoreDB) ~= "table" then
		ForeverCoreDB = {}
	end
	local all = ForeverCoreDB.questListFold
	if type(all) ~= "table" then
		all = {}
		ForeverCoreDB.questListFold = all
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
	return state.quests[questID] == true
end

---@param questID number
---@param folded boolean
local function SetQuestFolded(questID, folded)
	CharacterState().quests[questID] = folded or nil
end

---@param zone string
---@return boolean
local function IsZoneFolded(zone)
	local state = CharacterState()
	return state.zones[zone] == true
end

---@param zone string
---@param folded boolean
local function SetZoneFolded(zone, folded)
	CharacterState().zones[zone] = folded or nil
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
		menu:Action(L["Use the game's quest list"], function()
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
	bar:SetPoint("TOPLEFT", line.Text, "BOTTOMLEFT", 0, -THIN_BAR_GAP)
	bar:SetPoint("TOPRIGHT", line.Text, "BOTTOMRIGHT", 0, -THIN_BAR_GAP)
	bar.fraction = fraction
	block.thinBars = block.thinBars or {}
	block.thinBars[objectiveIndex] = bar
	module.activeThinBars = module.activeThinBars or {}
	module.activeThinBars[#module.activeThinBars + 1] = bar
end

---@param module ForeverQuestTrackerModule
local function FitThinBars(module)
	for _, bar in ipairs(type(module.activeThinBars) == "table" and module.activeThinBars or {}) do
		local width = bar:GetWidth() or 0
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
	local quest = QuestCache:Get(questID)
	if not quest then
		return false
	end
	local isComplete = quest:IsComplete()
	local isSuperTracked = questID == C_SuperTrack.GetSuperTrackedQuestID()
	local useFullHeight = true
	local shouldShowWaypoint = isSuperTracked or questID == QuestMapFrame_GetFocusedQuestID()
	local isSequenced = IsQuestSequenced(questID)
	local questLogIndex = quest:GetQuestLogIndex() or C_QuestLog.GetLogIndexForQuestID(questID)
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

apply = function()
	if not ready then
		return
	end
	CreateItemPool(section)
	ownedByOther = OtherOwner()
	local active = TrackerQuests.Enabled() and not ownedByOther
	if not active then
		HideItems(section)
	end
	section:MarkDirty()
	ApplyNativeModules(active)
end

-- The client's own ObjectiveTrackerManager adds the game's quest modules from its own ContinueAfterAllEvents pass on
-- the same two events this file waits for, so this file's first pass can run before the tracker holds a module to
-- take. A module joining the tracker is the signal that matters, and the tracker's height never follows it: Edit Mode
-- gives ObjectiveTrackerFrame a fixed height, so modules can join without a size change. This one secure post-hook on
-- the container's own ObjectiveTrackerFrame.AddModule, never a replacement of the method, takes a native module as it
-- joins while the list is ready and active. ApplyNativeModules defers in combat and checks every module against the
-- tracker, so a pass that finds nothing costs nothing and a module that joined later is still taken. The give-back in
-- SetNativeModulesDrawn runs with givingBack set so the list's own AddModule call is not taken again.
---@param _ any the container, passed through unchanged by the post-hook
---@param module any the module the container just accepted
local function NativeModuleJoined(_, module)
	if givingBack or not ready or not TrackerQuests.Enabled() or ownedByOther then
		return
	end
	for _, name in ipairs(NATIVE_MODULES) do
		if rawget(_G, name) == module then
			ApplyNativeModules(true)
			return
		end
	end
end
hooksecurefunc(ObjectiveTrackerFrame, "AddModule", NativeModuleJoined)

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
