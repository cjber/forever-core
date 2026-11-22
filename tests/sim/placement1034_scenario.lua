-- luacheck: read globals scenario
-- #1034: with no quest tracked the game's tracker is hidden, and nothing keeps its frame in step with the screen: its
-- container stops laying it out, so its rect drifts or goes away while the column's events keep placing it. The column
-- reads the tracker's rect only while the tracker shows, and holds that place while it is hidden, so zero quests leave
-- the column in one place through every event.

local function questList(G, tracker)
	local list = G.CreateFrame("Frame", nil, tracker)
	list.uiOrder, list.leftMargin, list.height = 1, 0, 120
	list.SetContainer = function() end
	list.Update = function(module)
		module:SetSize(240, module.height)
		return module.height, false
	end
	list.GetContentsHeight = function(module)
		return module.height
	end
	list.IsTruncated = function()
		return false
	end
	tracker:AddModule(list)
	return list
end

local function near(a, b)
	return a and b and math.abs(a - b) < 0.01
end

local EVENTS = {
	"QUEST_WATCH_LIST_CHANGED",
	"QUEST_LOG_UPDATE",
	"ZONE_CHANGED_NEW_AREA",
	"PLAYER_ENTERING_WORLD",
	"QUEST_POI_UPDATE",
}

local function setup(sim)
	local G = sim.G
	sim:login({ savedVariables = { ForeverCoreDB = { trackerHost = {} } } })
	sim:advance(3)
	local section = G.ForeverCore.TrackerSection.Create("Placement1034", {
		LayoutContents = function(module)
			module:SetHeader("Journey")
			for index = 1, 4 do
				local block = module:GetBlock("row" .. index)
				block:SetHeader("Step " .. index)
				module:LayoutBlock(block)
			end
		end,
	}, { order = -3 })
	G.ForeverCore.TrackerHost.Attach(section)
	local tracker = sim:openObjectiveTracker()
	tracker.questList = questList(G, tracker)
	tracker:ClearAllPoints()
	tracker:SetPoint("TOPRIGHT", G.UIParent, "TOPRIGHT", -100, -200)
	tracker:SetSize(260, 600)
	G.EditModeManagerFrame:UnregisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
	sim:event("EDIT_MODE_LAYOUTS_UPDATED")
	sim:advance(3)
	local column = assert(G.ForeverTrackerCompanion)
	-- The last tracked quest leaves: the tracker hides.
	tracker:RemoveModule(tracker.questList)
	sim:event("QUEST_WATCH_LIST_CHANGED")
	sim:advance(0.5)
	assert(not tracker:IsShown(), "the game's tracker hides with nothing to list")
	return G, column, tracker
end

-- Every event relayouts; the column must stay where the first one left it.
local function holds(sim, column, what)
	local top, x = column:GetTop(), column:GetLeft()
	assert(top and x, "the column has a place")
	for _, event in ipairs(EVENTS) do
		sim:event(event)
		sim:advance(0.5)
		assert(
			near(column:GetTop(), top) and near(column:GetLeft(), x),
			("%s: %s moved the column to %s,%s from %s,%s"):format(
				what,
				event,
				tostring(column:GetLeft()),
				tostring(column:GetTop()),
				tostring(x),
				tostring(top)
			)
		)
	end
end

scenario("placement1034: a hidden tracker whose rect drifts leaves the column in one place", function(sim)
	local G, column, tracker = setup(sim)
	local top, x = column:GetTop(), column:GetLeft()
	assert(near(top, tracker:GetTop()), "the column sits at the hidden tracker's top, got " .. tostring(top))
	-- The container no longer lays the hidden tracker out: its anchor drifts.
	for step = 1, 3 do
		tracker:ClearAllPoints()
		tracker:SetPoint("TOPRIGHT", G.UIParent, "TOPRIGHT", -100 - step * 40, -200 - step * 55)
		sim:event("QUEST_WATCH_LIST_CHANGED")
		sim:advance(0.5)
		assert(near(column:GetTop(), top) and near(column:GetLeft(), x), "the drift " .. step .. " moved the column")
		holds(sim, column, "drift " .. step)
	end
	sim:expectNoErrors("ForeverCore")
end)

scenario("placement1034: a hidden tracker with no rect leaves the column in one place", function(sim)
	local _, column, tracker = setup(sim)
	local top, x = column:GetTop(), column:GetLeft()
	tracker:ClearAllPoints()
	sim:event("QUEST_WATCH_LIST_CHANGED")
	sim:advance(0.5)
	assert(near(column:GetTop(), top) and near(column:GetLeft(), x), "losing the rect moved the column")
	holds(sim, column, "no rect")
	sim:expectNoErrors("ForeverCore")
end)

scenario("placement1034: a quest tracked again follows the shown tracker", function(sim)
	local _, column, tracker = setup(sim)
	tracker:ClearAllPoints()
	tracker:SetPoint("TOPRIGHT", sim.G.UIParent, "TOPRIGHT", -100, -300)
	tracker:AddModule(tracker.questList)
	sim:event("QUEST_WATCH_LIST_CHANGED")
	sim:advance(0.5)
	assert(tracker:IsShown(), "the list brings the tracker back")
	assert(near(column:GetTop(), tracker.NineSlice:GetBottom()), "the column follows the shown tracker's line")
	sim:expectNoErrors("ForeverCore")
end)
