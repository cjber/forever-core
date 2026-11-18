-- luacheck: read globals scenario
-- #850: the column sits under the game's quest tracker, on its last visible line, with the real tracker and Edit Mode
-- loaded. A quest accepted, completed or collapsed moves that line; the column follows it with no layout of its own
-- sections, sits left of the tracker when it does not fit under the list, and holds still through combat.

-- The game's quest list, as Blizzard's own tracker lays it out: the sim has no quests, so one stand-in module lists
-- `height` units of them, and the container's real Update anchors the tracker's NineSlice under its last line.
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

-- A quest accepted, completed or collapsed leaves the list `height` units tall.
local function listEnds(sim, tracker, height)
	tracker.questList.height = height
	tracker:MarkDirty()
	sim:advance(0.1)
end

local function run(sim, trackerHost)
	local G = sim.G
	sim:login({ savedVariables = { ForeverCoreDB = { trackerHost = trackerHost } } })
	sim:advance(3)
	local layouts = 0
	local section = G.ForeverCore.TrackerSection.Create("Placement850", {
		LayoutContents = function(module)
			layouts = layouts + 1
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
	return G, assert(G.ForeverTrackerCompanion), tracker, function()
		return layouts
	end
end

local function near(a, b)
	return a and b and math.abs(a - b) < 0.01
end

scenario("placement850: the column follows the quest list's last line with no layout", function(sim)
	local G, column, tracker, layouts = run(sim, {})
	listEnds(sim, tracker, 120)
	assert(near(column:GetTop(), tracker.NineSlice:GetBottom()), "the column's top is on the list's last line")
	assert(near(column:GetLeft(), tracker:GetLeft()), "and its left edge on the tracker's")
	local before, height = layouts(), column:GetHeight()
	for _, below in ipairs({ 160, 100, 220, 40, 120 }) do
		listEnds(sim, tracker, below)
		assert(near(column:GetTop(), tracker.NineSlice:GetBottom()), "the column follows the line to " .. below)
	end
	assert(layouts() == before, "following the line laid out no section, got " .. (layouts() - before))
	assert(column:GetHeight() == height, "and the column's height did not change")

	-- A list that leaves no room under it puts the column left of the tracker, and room coming back returns it.
	listEnds(sim, tracker, tracker:GetTop() - column:GetHeight() + 10)
	assert(
		near(column:GetRight(), tracker:GetLeft()) and near(column:GetTop(), tracker:GetTop()),
		"a long list puts it left"
	)
	listEnds(sim, tracker, 120)
	assert(near(column:GetTop(), tracker.NineSlice:GetBottom()), "a short list puts it back under")
	assert(layouts() == before, "neither move laid out a section")

	-- Combat holds the column where it is; it catches up when combat ends.
	sim:enterCombat()
	local top = column:GetTop()
	listEnds(sim, tracker, 200)
	assert(column:GetTop() == top, "a list change in combat leaves the column where it was")
	sim:leaveCombat()
	sim:advance(0.5)
	assert(near(column:GetTop(), tracker.NineSlice:GetBottom()), "the column catches up when combat ends")

	-- An Edit Mode move carries the column with the tracker.
	tracker:ClearAllPoints()
	tracker:SetPoint("TOPRIGHT", G.UIParent, "TOPRIGHT", -300, -150)
	sim:event("EDIT_MODE_LAYOUTS_UPDATED")
	sim:advance(0.5)
	assert(near(column:GetLeft(), tracker:GetLeft()), "an Edit Mode move carries the column's left edge")
	assert(near(column:GetTop(), tracker.NineSlice:GetBottom()), "and its top stays on the line")
	sim:expectNoErrors("ForeverCore")
end)

scenario("placement850: with no quests the tracker hides and the column's next layout takes its top", function(sim)
	local _, column, tracker = run(sim, {})
	tracker:RemoveModule(tracker.questList)
	sim:advance(0.1)
	assert(not tracker:IsShown(), "the game's tracker hides with nothing to list")
	column:MarkDirty()
	sim:advance(0.5)
	assert(
		near(column:GetTop(), tracker:GetTop()) and near(column:GetLeft(), tracker:GetLeft()),
		"the column sits at its top"
	)
	sim:expectNoErrors("ForeverCore")
end)

scenario("placement850: a dragged column ignores the quest list", function(sim)
	local _, column, tracker = run(sim, { attached = false, x = 700, y = -200 })
	local left, top = column:GetLeft(), column:GetTop()
	listEnds(sim, tracker, 300)
	assert(column:GetLeft() == left and column:GetTop() == top, "a dragged column stays where it was dropped")
	sim:expectNoErrors("ForeverCore")
end)
