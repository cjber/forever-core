-- The Forever quest list is a section of the Forever column and leaves the client's own tracker modules alone. It used
-- to take the game's Quests and Campaign sections out of the tracker, which wrote the container's dirty flag and
-- module list from addon code and tainted the client's next layout (issue #608). This spec loads
-- UI/TrackerQuests.lua against a tracker whose AddModule and RemoveModule and native modules whose Update and
-- MarkDirty raise, so turning the list on, off, in combat and back on must never touch them.
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end

-- The client's tracker collection: it holds the modules it lays out, as Blizzard's ObjectiveTrackerContainerMixin does.
-- Every call the list must never make raises, so a failure names the call.
local tracker = { modules = {} }
function tracker:HasModule(module)
	for _, held in ipairs(self.modules) do
		if held == module then
			return true
		end
	end
	return false
end
function tracker.AddModule()
	error("the Forever quest list must never add a module to the client's tracker")
end
function tracker.RemoveModule()
	error("the Forever quest list must never remove a module from the client's tracker")
end

-- A native quest module: the client's own layout drives it, and the list must never update, dirty, collapse, reparent
-- or hide it.
local function nativeModule(name)
	local module = { name = name, shown = true }
	function module.Update()
		error(name .. " must not be updated by the quest list")
	end
	function module.MarkDirty()
		error(name .. " must not be marked dirty by the quest list")
	end
	function module.SetCollapsed()
		error(name .. " must not be collapsed by hand")
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
}, { __index = _G })
env._G = env
setfenv(assert(loadfile("UI/TrackerQuests.lua")), env)("Test", ns)
local TrackerQuests = assert(ns.TrackerQuests, "the list registers itself on the namespace")
check(type(ready) == "function", "the list waits for the client's own load events")

-- The list is on: it draws its own section, and the client's tracker and its modules are untouched.
local function CheckNativeModulesUntouched(note)
	check(tracker:HasModule(quests), note .. " keeps the game's quest module in the tracker")
	check(tracker:HasModule(campaign), note .. " keeps the game's campaign module in the tracker")
	check(#tracker.modules == 2, note .. " leaves the tracker's module list alone")
end
ready()
check(section.marked ~= nil, "the Forever list is laid out")
CheckNativeModulesUntouched("turning the list on")

-- Turning the list off and back on only redraws the Forever section; the client's own modules stay where the client
-- left them.
local marked = section.marked
TrackerQuests.SetEnabled(false)
check(section.marked > marked, "turning the list off redraws the Forever section")
CheckNativeModulesUntouched("turning the list off")
TrackerQuests.SetEnabled(true)
CheckNativeModulesUntouched("turning the list on again")

-- In combat, and through the client's own PLAYER_REGEN_ENABLED pass, the list still touches no client module.
combat = true
TrackerQuests.SetEnabled(false)
TrackerQuests.SetEnabled(true)
combat = false
section:OnEvent("PLAYER_REGEN_ENABLED")
CheckNativeModulesUntouched("a change asked for in combat")

-- Another tracker owning the quest list only changes the Forever section's own layout.
addons["!KalielsTracker"] = true
section:OnEvent("PLAYER_ENTERING_WORLD")
CheckNativeModulesUntouched("another tracker owning the list")
addons["!KalielsTracker"] = nil
section:OnEvent("PLAYER_ENTERING_WORLD")
CheckNativeModulesUntouched("the list taking over again")

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
