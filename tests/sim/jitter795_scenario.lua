-- luacheck: read globals scenario
-- #795: a journey section swaps between its full route and one "Finding the fastest way" row, as Shortest Path's
-- Journey does while it searches, above a long section that takes the rest of the column. The sections' heights swing
-- every cycle; the column itself must not move by a single unit, pinned or dragged.
local ROWS, LONG = 10, 14

local function run(sim, trackerHost)
	local G = sim.G
	sim:login({ savedVariables = { ForeverCoreDB = { trackerHost = trackerHost } } })
	local tracker = sim:openObjectiveTracker()
	tracker:SetSize(260, 600)
	tracker:ClearAllPoints()
	tracker:SetPoint("TOPRIGHT", G.UIParent, "TOPRIGHT", -100, -200)
	G.EditModeManagerFrame:UnregisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
	sim:event("EDIT_MODE_LAYOUTS_UPDATED")
	sim:advance(3)
	local rows = ROWS
	local Section = G.ForeverCore.TrackerSection
	local journey = Section.Create("Jitter795Journey", {
		LayoutContents = function(module)
			module:SetHeader("Journey")
			for index = 1, rows do
				local block = module:GetBlock("row" .. index)
				block:SetHeader(rows == 1 and "Finding the fastest way" or ("Step " .. index))
				module:LayoutBlock(block)
			end
		end,
	}, { order = -3, maxHeight = 200 })
	local long = Section.Create("Jitter795Long", {
		LayoutContents = function(module)
			module:SetHeader("Long list")
			for index = 1, LONG do
				local block = module:GetBlock("entry" .. index)
				block:SetHeader("Entry " .. index)
				block:AddObjective(1, "0/8 things")
				module:LayoutBlock(block)
			end
		end,
	}, { order = 1, maxHeight = "remaining" })
	G.ForeverCore.TrackerHost.Attach(journey)
	G.ForeverCore.TrackerHost.Attach(long)
	sim:advance(3)
	local column = assert(G.ForeverTrackerCompanion)
	local function where()
		return ("%.2f,%.2f"):format(column:GetRight() or -1, column:GetTop() or -1)
	end
	local start, moves, swings = where(), 0, 0
	local height = journey:GetHeight()
	for _ = 1, 4 do
		for _, n in ipairs({ 1, ROWS }) do
			rows = n
			journey:MarkDirty()
			for _ = 1, 5 do
				sim:advance(0.02)
				if where() ~= start then
					moves = moves + 1
				end
				if journey:GetHeight() ~= height then
					swings, height = swings + 1, journey:GetHeight()
				end
			end
		end
	end
	sim:expectNoErrors("ForeverCore")
	print(("jitter795 column_moves=%d section_height_swings=%d"):format(moves, swings))
	assert(swings >= 8, "the journey section's height swings every time its route changes")
	assert(moves == 0, "the column moves 0 times while the section heights swing, got " .. moves)
	return column
end

scenario("jitter795: the pinned column holds still while section heights swing", function(sim)
	local column = run(sim, { placement = "left" })
	local G = sim.G
	local tracker = G.ObjectiveTrackerFrame
	assert(
		tracker:GetLeft() and math.abs(column:GetRight() - tracker:GetLeft()) < 0.01,
		"the pinned column's right edge is on the game tracker's left edge"
	)
	assert(math.abs(column:GetTop() - tracker:GetTop()) < 0.01, "and the two tops are level")
end)

scenario("jitter795: a dragged column holds still while section heights swing", function(sim)
	run(sim, { attached = false, x = 700, y = -200 })
end)
