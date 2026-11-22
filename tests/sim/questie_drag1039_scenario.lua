-- luacheck: read globals scenario
-- #1039: the player drags Questie's tracker with the Forever column on screen. Questie's list stays shown where it is
-- dropped, locked or unlocked, and again after a reload; the column follows it without covering it, and holds no
-- anchor to it.

local function near(a, b)
	return a and b and math.abs(a - b) < 0.01
end

local function dependsOn(frame, target, seen)
	if not frame or seen[frame] then
		return false
	end
	if frame == target then
		return true
	end
	seen[frame] = true
	for index = 1, frame:GetNumPoints() do
		local _, relative = frame:GetPoint(index)
		if dependsOn(relative, target, seen) then
			return true
		end
	end
	return dependsOn(frame:GetParent(), target, seen)
end

-- Whether two frames' screen rects overlap by more than a hair.
local function overlaps(a, b)
	local aScale, bScale = a:GetEffectiveScale(), b:GetEffectiveScale()
	local aLeft, aRight = a:GetLeft() * aScale, a:GetRight() * aScale
	local aTop, aBottom = a:GetTop() * aScale, a:GetBottom() * aScale
	local bLeft, bRight = b:GetLeft() * bScale, b:GetRight() * bScale
	local bTop, bBottom = b:GetTop() * bScale, b:GetBottom() * bScale
	return aLeft < bRight - 0.5 and bLeft < aRight - 0.5 and aBottom < bTop - 0.5 and bBottom < aTop - 0.5
end

local function setup(sim, locked)
	local G = sim.G
	sim:login({
		savedVariables = { ForeverCoreDB = { trackerHost = { locked = locked } } },
	})
	local section = G.ForeverCore.TrackerSection.Create("QuestieDrag1039", {
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
	sim:openObjectiveTracker()
	sim:advance(6)
	return G, assert(G.Questie_BaseFrame), assert(G.ForeverTrackerCompanion)
end

-- What Questie does: StartMoving on the press, the client moves the frame under the cursor, StopMovingOrSizing on the
-- release, then it saves the frame's point.
local function drag(sim, questie, steps)
	local G = sim.G
	questie:SetMovable(true)
	questie:StartMoving()
	for _, step in ipairs(steps) do
		sim.mouseX, sim.mouseY = step[1], step[2]
		questie:ClearAllPoints()
		questie:SetPoint("TOPLEFT", G.UIParent, "BOTTOMLEFT", step[1], step[2])
		sim:advance(0.05)
	end
	questie:StopMovingOrSizing()
	sim:event("GLOBAL_MOUSE_UP", "LeftButton")
	sim:advance(1.5)
	return { questie:GetPoint() }
end

local function check(sim, questie, column, where)
	assert(questie:IsShown(), where .. ": Questie's tracker is shown")
	assert(questie:GetLeft() and questie:GetTop(), where .. ": Questie's tracker has a place")
	assert(column:GetNumPoints() > 0, where .. ": the column is placed")
	assert(not dependsOn(column, questie, {}), where .. ": the column is anchored to Questie")
	assert(not dependsOn(questie, column, {}), where .. ": Questie is anchored to the column")
	assert(not overlaps(column, questie), where .. ": the column covers Questie's tracker")
	sim:expectNoErrors("ForeverCore")
end

for _, locked in ipairs({ false, true }) do
	local mode = locked and "locked" or "unlocked"
	scenario(
		"questie_drag1039: dragging Questie's tracker with the column " .. mode,
		{ stubs = { Questie = {} } },
		function(sim)
			local G, questie, column = setup(sim, locked)
			check(sim, questie, column, "before the drag")
			local top = G.UIParent:GetTop()
			local saved = drag(sim, questie, { { 400, top - 300 }, { 500, top - 350 }, { 600, top - 400 } })
			check(sim, questie, column, "after the drag")
			assert(
				near(questie:GetLeft(), 600) and near(questie:GetTop(), top - 400),
				"Questie stays where it was dropped"
			)
			assert(
				near(column:GetTop(), questie:GetBottom()) or near(column:GetRight(), questie:GetLeft()),
				"the column follows Questie's tracker to where it was dropped"
			)

			-- Dropped onto the column's own place, the column gives way rather than cover the list.
			drag(sim, questie, { { column:GetLeft() - 20, column:GetTop() + 60 } })
			check(sim, questie, column, "after a drop onto the column")

			-- Questie saves the point it was dropped at and sets it again after a reload.
			local reloaded = sim:reload()
			local G2 = reloaded.G
			reloaded:advance(6)
			local questie2 = assert(G2.Questie_BaseFrame)
			questie2:ClearAllPoints()
			questie2:SetPoint(saved[1], G2.UIParent, saved[3], saved[4], saved[5])
			reloaded:event("QUEST_LOG_UPDATE")
			reloaded:advance(1.5)
			check(reloaded, questie2, assert(G2.ForeverTrackerCompanion), "after the reload")
		end
	)
end
