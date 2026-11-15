-- The Forever quest list owns the game's Quests and Campaign sections while it is on. Collapsing them was not enough:
-- a collapsed module still draws its header, so an empty "Quests" header stayed above the Forever list's own
-- "Quests 11/30". The list now takes the two modules out of the client's tracker collection and asks each to lay out in
-- no room, which is how the client hides a module with no contents, and gives them back when the list is off. This
-- spec loads UI/TrackerQuests.lua against a tracker that records those calls, and fails if the list ever collapses,
-- hides or reparents a module by hand instead.
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end

-- The client's tracker collection: it holds the modules it lays out, as Blizzard's ObjectiveTrackerContainerMixin does.
local tracker = { modules = {} }
function tracker:HasModule(module)
	for _, held in ipairs(self.modules) do
		if held == module then
			return true
		end
	end
	return false
end
function tracker:AddModule(module)
	if not self:HasModule(module) then
		self.modules[#self.modules + 1] = module
	end
	self.added = (self.added or 0) + 1
end
function tracker:RemoveModule(module)
	for index, held in ipairs(self.modules) do
		if held == module then
			table.remove(self.modules, index)
			break
		end
	end
	self.removed = (self.removed or 0) + 1
end
-- The container's own update: every module it holds is laid out in the room left. A module it does not hold is never
-- laid out, which is why a removed module cannot draw its header again.
function tracker:Layout(available)
	for _, module in ipairs(self.modules) do
		module:Update(available)
	end
end

-- A native quest module: its own Update draws it, and its EndLayout hides it when it has no room. SetCollapsed,
-- SetParent and Hide are traps: the list must reach the module through Update and the container instead.
local function nativeModule(name)
	local module = { name = name, shown = true }
	function module:Update(available)
		self.available = available
		self.shown = available ~= 0
	end
	function module:MarkDirty()
		self.dirty = true
	end
	function module.SetCollapsed()
		error(name .. " must not be collapsed: a collapsed module keeps drawing its header")
	end
	function module.SetParent()
		error(name .. " must not be reparented")
	end
	function module.Hide()
		error(name .. " must not be hidden by hand")
	end
	return module
end
local quests = nativeModule("QuestObjectiveTracker")
local campaign = nativeModule("CampaignQuestObjectiveTracker")
tracker.modules = { campaign, quests }

-- The section the list builds, standing in for UI/TrackerSection.Create. The list only registers its events, marks it
-- dirty and runs its own OnEvent through it here.
local section = { shown = true }
function section.RegisterEvent() end
function section.SetHeader() end
function section:MarkDirty()
	self.marked = (self.marked or 0) + 1
end
function section:IsShown()
	return self.shown
end

local ready
local function continueAfterAllEvents(fn)
	ready = fn
end
local combat = false
local addons = {}
local ns = {
	L = setmetatable({}, {
		__index = function(_, key)
			return key
		end,
	}),
	TrackerHost = {
		IsAttached = function()
			return true
		end,
	},
	TrackerSection = {
		Create = function()
			return section
		end,
	},
}
local env = setmetatable({
	_G = nil,
	ObjectiveTrackerFrame = tracker,
	QuestObjectiveTracker = quests,
	CampaignQuestObjectiveTracker = campaign,
	QuestObjectiveTrackerMixin = {},
	CampaignQuestObjectiveTrackerMixin = {},
	TRACKER_HEADER_QUESTS = "Quests",
	ForeverCoreDB = { questList = true },
	EventUtil = { ContinueAfterAllEvents = continueAfterAllEvents },
	C_AddOns = {
		IsAddOnLoaded = function(name)
			return addons[name] == true
		end,
	},
	C_Timer = {},
	Mixin = function(target, mixin)
		for key, value in pairs(mixin) do
			target[key] = value
		end
	end,
	InCombatLockdown = function()
		return combat
	end,
	-- A table method post-hook: the original runs first, then the hook, with the same arguments, as hooksecurefunc does
	-- on an instance method in the client.
	hooksecurefunc = function(target, name, post)
		local original = target[name]
		target[name] = function(...)
			local result = original(...)
			post(...)
			return result
		end
	end,
}, { __index = _G })
env._G = env
setfenv(assert(loadfile("UI/TrackerQuests.lua")), env)("Test", ns)
local TrackerQuests = assert(ns.TrackerQuests, "the list registers itself on the namespace")
check(type(ready) == "function", "the list waits for the client's own load events")

-- The list is on: both game modules leave the tracker and are asked to lay out in no room, so the client's own layout
-- hides them and no empty header is left above the Forever list's header.
ready()
check(tracker:HasModule(quests) == false, "the game's quest module leaves the tracker")
check(tracker:HasModule(campaign) == false, "the game's campaign module leaves the tracker")
check(quests.available == 0 and quests.shown == false, "the game's quest module is laid out in no room and hidden")
check(campaign.available == 0 and campaign.shown == false, "the campaign module is hidden the same way")
check(section.marked ~= nil, "and the Forever list is laid out")

-- The list is off: the modules come back to the tracker and are marked dirty, so the client's next layout draws the
-- game's own quests again, exactly as they were.
TrackerQuests.SetEnabled(false)
check(tracker:HasModule(quests) == true, "turning the list off gives the game's quest module back")
check(tracker:HasModule(campaign) == true, "and the campaign module")
check(quests.dirty == true and campaign.dirty == true, "the returned modules are marked for the client's next layout")
tracker:Layout(100)
check(quests.shown == true, "the client's next layout draws the game's own Quests section again")

-- In combat nothing is taken out or given back: the change waits for the client's own PLAYER_REGEN_ENABLED pass, the
-- same deferred pass every other layout change of the column waits for.
combat = true
TrackerQuests.SetEnabled(true)
check(tracker:HasModule(quests) == true, "a change asked for in combat takes nothing out yet")
check(quests.available == 100, "and the game's module keeps its layout through the fight")
-- A second change in the same fight wins, as the column records only the latest state the player asked for.
TrackerQuests.SetEnabled(false)
TrackerQuests.SetEnabled(true)
combat = false
section:OnEvent("PLAYER_REGEN_ENABLED")
check(tracker:HasModule(quests) == false, "the deferred pass takes the game's module out")
check(quests.available == 0 and quests.shown == false, "and hides it")
check(tracker:HasModule(campaign) == false, "and the campaign module with it")

-- Another tracker owning the quest list gives the game's modules back, the same as turning the list off.
addons["!KalielsTracker"] = true
quests.dirty = nil
section:OnEvent("PLAYER_ENTERING_WORLD")
check(quests.dirty == true, "another tracker owning the list gives the game's quest module back")
check(tracker:HasModule(quests) == true, "and it is in the tracker again")
addons["!KalielsTracker"] = nil
section:OnEvent("PLAYER_ENTERING_WORLD")
check(tracker:HasModule(quests) == false, "the list takes the game's module back once no other tracker owns it")

-- The client's own ObjectiveTrackerManager adds the game's modules through the container's AddModule, and the tracker
-- keeps the fixed height Edit Mode gave it, so modules join with no size change at all. The list's one secure
-- post-hook on AddModule takes a native module as it joins while the list is ready and on.
tracker.modules = {}
check(TrackerQuests.Enabled() and #tracker.modules == 0, "the list is on and ready before the tracker holds a module")
tracker:AddModule(campaign)
tracker:AddModule(quests)
check(tracker:HasModule(quests) == false, "a quest module that joins is taken by the AddModule post-hook")
check(tracker:HasModule(campaign) == false, "and the campaign module with it")
check(quests.available == 0 and quests.shown == false, "the joined quest module is laid out in no room and hidden")
check(campaign.available == 0 and campaign.shown == false, "and so is the joined campaign module")

-- Turning the list off gives both modules back through AddModule; the list's own give-back is marked, so the hook
-- does not take them again, and they stay in the tracker.
TrackerQuests.SetEnabled(false)
check(tracker:HasModule(quests) == true, "turning the list off gives the game's quest module back")
check(tracker:HasModule(campaign) == true, "and the campaign module")
tracker:Layout(100)
check(quests.shown == true, "the client's next layout draws the game's own Quests section again")

-- With the list off a module the client adds stays put; turning the list on then takes what the tracker holds.
tracker.modules = {}
tracker:AddModule(quests)
check(tracker:HasModule(quests) == true, "a module the client adds while the list is off stays in the tracker")
TrackerQuests.SetEnabled(true)
check(tracker:HasModule(quests) == false, "turning the list on takes the module the tracker holds")

-- Private records and rendering must not populate Blizzard's shared lazy QuestCache.
env.QuestCache = {
	Get = function()
		error("private quest rendering entered native QuestCache")
	end,
}
env.Enum = { QuestClassification = { Campaign = 2 } }
local infos = {
	{ questID = 101, title = "Normal", isOnMap = true },
	{ questID = 102, title = "Campaign", isTask = true },
	{ questID = 103, title = "Task", isTask = true },
	{ questID = 104, title = "Bounty", isBounty = true },
	{ questID = 105, title = "Disabled" },
}
env.C_QuestLog = {
	GetNumQuestLogEntries = function()
		return #infos
	end,
	GetInfo = function(index)
		return infos[index]
	end,
	GetNumQuestWatches = function()
		return #infos
	end,
	GetQuestIDForQuestWatchIndex = function(index)
		return infos[index].questID
	end,
	GetLogIndexForQuestID = function(id)
		return id - 100
	end,
	GetTitleForQuestID = function(id)
		return infos[id - 100].title
	end,
	GetDistanceSqToQuest = function()
		return 400
	end,
	ReadyForTurnIn = function()
		return false
	end,
	IsComplete = function(id)
		return id == 101
	end,
	IsQuestDisabledForSession = function(id)
		return id == 105
	end,
}
env.C_QuestInfoSystem = {
	GetQuestClassification = function(id)
		return id == 102 and 2 or 1
	end,
}
local records = section:Records()
check(#records == 2, "normal and campaign quests survive task, bounty and disabled filtering")
check(records[1].questID == 101 and records[1].ready, "completion comes from the direct quest API")
check(records[2].questID == 102, "campaign eligibility wins over the normal task filter")
env.UnitFullName = function()
	return "Spec"
end
env.GetRealmName = function()
	return "Realm"
end
env.ForeverCoreDB.questListFold = { ["Realm/Spec"] = { quests = { [101] = true }, zones = {} } }
env.C_SuperTrack = {
	GetSuperTrackedQuestID = function()
		return 0
	end,
}
env.QuestMapFrame_GetFocusedQuestID = function()
	return 0
end
env.IsQuestSequenced = function()
	return false
end
env.SetQuestTitleLevelAndDifficultyColor = function(_, title)
	return title
end
local block = {}
function block:SetHeader(title)
	self.title = title
end
function block:SetPOIInfo(id, complete)
	self.id, self.complete = id, complete
end
function section.GetBlock()
	return block, false
end
function section.GetQuestTagText() end
function section.LayoutBlock()
	return true
end
check(section:UpdateQuest(records[1]), "a private folded quest renders without native cache access")
check(block.id == 101 and block.complete, "the rendered POI receives direct completion data")

print("tracker_quests_spec: " .. checks .. " checks passed")
