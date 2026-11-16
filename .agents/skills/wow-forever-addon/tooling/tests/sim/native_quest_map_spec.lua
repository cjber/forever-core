-- The native world map's quest provider against quest fixture data: with questPOI on, the map asks HaveQuestData
-- about each quest it holds and draws without an error, and the quest blob pin records the quest area it draws.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")

local function pinsByTemplate(sim, template)
	local found = {}
	for _, frame in ipairs(sim.widgets.all) do
		if frame.pinTemplate == template then
			found[#found + 1] = frame
		end
	end
	return found
end

local sim = Sim.new()
local G = sim.G
local questID = 645001
sim.world.maps[1454] = { name = "Orgrimmar", mapType = 3 }
sim:login()
sim:expectNoErrors()

sim.impl["C_QuestLog.GetQuestsOnMap"] = function()
	return { { questID = questID, x = 0.5, y = 0.5, isMapIndicatorQuest = false } }
end
sim.impl["C_TaskQuest.DoesMapShowTaskQuestObjectives"] = function()
	return false
end
-- The map asks whether the client holds the quest's data before it draws a quest or its area.
sim.impl.HaveQuestData = function(id)
	return id == questID
end
sim.impl["C_SuperTrack.GetSuperTrackedQuestID"] = function()
	return questID
end
G.SetCVar("questPOI", "1")
sim:openWorldMap(1454)
sim:expectNoErrors()

local questPins = pinsByTemplate(sim, "QuestPinTemplate")
assert(#questPins > 0, "the quest the fixture holds has a map pin")
for _, pin in ipairs(questPins) do
	assert(pin.questID == questID, "the quest pin carries the fixture quest, got " .. tostring(pin.questID))
end
local blobPins = pinsByTemplate(sim, "QuestBlobPinTemplate")
assert(#blobPins == 1, "the quest blob pin is acquired once, got " .. #blobPins)
assert(sim.widgets.state[blobPins[1]].blobQuestIDs[questID], "the quest blob pin records the area it draws")
sim:closeWorldMap()
sim:expectNoErrors()
print("native_quest_map_spec: passed")
