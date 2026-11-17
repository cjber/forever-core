-- Legacy quest reward and sharing natives preserve fixture arguments and all return slots.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
local sim = Sim.new()
local defaults = {
	GetNumQuestLogRewards = 0,
	GetNumQuestLogChoices = 0,
	GetQuestLogRewardMoney = 0,
	GetQuestLogRewardXP = 0,
	GetQuestLogChoiceInfoLootType = 0,
	GetQuestLogRewardHonor = 0,
	GetQuestLogRewardArtifactXP = 0,
}
for _, name in ipairs({
	"GetNumQuestLogRewards",
	"GetNumQuestLogChoices",
	"GetQuestLogRewardInfo",
	"GetQuestLogChoiceInfo",
	"GetQuestLogRewardMoney",
	"GetQuestLogRewardXP",
	"GetQuestLogChoiceInfoLootType",
	"QuestLogPushQuest",
	"GetQuestLogRewardSkillPoints",
	"GetQuestLogRewardArtifactXP",
	"GetQuestLogRewardHonor",
	"GetQuestLogRewardTitle",
	"GetQuestLogItemLink",
}) do
	assert(type(sim.G[name]) == "function", name .. " missing")
	assert(sim.G[name]() == defaults[name], name .. " empty default")
	local marker = {}
	sim.impl[name] = function(...)
		assert(select("#", ...) == 3)
		local a, b, c = ...
		assert(a == 125 and b == nil and c == marker, name .. " exact arguments")
		return marker, nil, 7, nil
	end
	local function check(...)
		assert(select("#", ...) == 4, name .. " return count")
		local a, b, c = ...
		assert(a == marker and b == nil and c == 7, name .. " exact returns")
	end
	check(sim.G[name](125, nil, marker))
end
sim:expectNoErrors()
print("quest_rewards_spec: passed")
