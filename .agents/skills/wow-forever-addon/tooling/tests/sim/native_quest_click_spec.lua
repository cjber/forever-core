-- Boot the default client and click its actual quest tracker, using only public quest API fixtures.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
local sim = Sim.new()
local G = sim.G
local questID = 630001
local quest = {
	questID = questID,
	title = "Native header fixture",
	questLogIndex = 1,
	level = 10,
	difficultyLevel = 10,
	isOnMap = true,
	questClassification = G.Enum.QuestClassification.Normal,
}
local answers = {
	["C_QuestLog.GetNumQuestLogEntries"] = function()
		return 1, 1
	end,
	["C_QuestLog.GetInfo"] = function(index)
		return index == 1 and quest or nil
	end,
	["C_QuestLog.GetNumQuestWatches"] = function()
		return 1
	end,
	["C_QuestLog.GetQuestIDForQuestWatchIndex"] = function(index)
		return index == 1 and questID or nil
	end,
	["C_QuestLog.GetLogIndexForQuestID"] = function(id)
		return id == questID and 1 or nil
	end,
	["C_QuestLog.GetQuestIDForLogIndex"] = function(index)
		return index == 1 and questID or nil
	end,
	["C_QuestLog.GetTitleForQuestID"] = function()
		return quest.title
	end,
	["C_QuestLog.GetQuestObjectives"] = function()
		return {}
	end,
	["C_QuestLog.GetQuestDifficultyLevel"] = function()
		return 10
	end,
	["C_QuestLog.GetDistanceSqToQuest"] = function()
		return 100, true
	end,
}
for name, fn in pairs(answers) do
	sim.impl[name] = fn
end
local linked
sim.impl.GetQuestLink = function(id)
	linked = id
	return "|cffffff00|Hquest:630001:10|h[Native header fixture]|h|r"
end
G.ObjectiveTrackerFrame:SetPoint("TOPRIGHT", G.UIParent, "TOPRIGHT", 0, -100)
G.ObjectiveTrackerFrame:SetHeight(400)
sim:login()
sim:event("QUEST_LOG_UPDATE")
sim:advance(0.2)
sim:expectNoErrors()
local block = G.QuestObjectiveTracker:GetExistingBlock(questID)
assert(block and block.HeaderButton, "watched quest creates the actual native header")
sim:input(function()
	block.HeaderButton:Click("RightButton")
end)
sim:expectNoErrors()
assert(linked == questID, "native header reaches the fixture-backed GetQuestLink")
print("native_quest_click_spec: native watched quest header click passed")
