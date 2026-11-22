-- luacheck: read globals scenario
local function near(actual, expected)
	return actual and expected and math.abs(actual - expected) < 0.01
end

local function move(G, frame, x, y)
	frame:ClearAllPoints()
	frame:SetPoint("TOPLEFT", G.UIParent, "TOPLEFT", x, y)
end

local function dependents(sim, ...)
	local targets = {}
	for index = 1, select("#", ...) do
		local target = select(index, ...)
		targets[target] = true
	end
	local result = {}
	for _, object in ipairs(sim.widgets.all) do
		local state = sim.widgets.state[object]
		if state.creator == "ForeverCore" then
			for _, point in ipairs(state.points) do
				if targets[point.relativeTo] then
					result[#result + 1] = state.name or state.kind
				end
			end
			if targets[state.parent] then
				result[#result + 1] = state.name or state.kind
			end
		end
	end
	return table.concat(result, ", ")
end

local function setup(sim, placement)
	local G = sim.G
	sim:login({ savedVariables = { ForeverCoreDB = { trackerHost = { placement = placement } } } })
	local tracker = sim:openObjectiveTracker()
	move(G, tracker, 520, -200)
	tracker:SetSize(260, 600)
	local list = G.CreateFrame("Frame", nil, tracker)
	list.uiOrder, list.leftMargin = 1, 0
	list.SetContainer = function() end
	list.Update = function(module)
		module:SetSize(240, 120)
		return 120, false
	end
	list.GetContentsHeight = function()
		return 120
	end
	list.IsTruncated = function()
		return false
	end
	tracker:AddModule(list)
	local section = G.ForeverCore.TrackerSection.Create("Anchor926", {
		LayoutContents = function(module)
			module:SetHeader("Journey")
			local block = module:GetBlock("row")
			block:SetHeader("Step")
			module:LayoutBlock(block)
		end,
	})
	G.ForeverCore.TrackerHost.Attach(section)
	sim:event("EDIT_MODE_LAYOUTS_UPDATED")
	sim:advance(0.1)
	return G, G.ForeverTrackerCompanion, tracker
end

local function checkPlacement(column, tracker, placement, line)
	if placement == "left" then
		assert(near(column:GetRight(), tracker:GetLeft()), "Left follows the selected tracker's left edge")
		assert(near(column:GetTop(), tracker:GetTop()), "Left follows the selected tracker's top")
	else
		assert(
			near(column:GetLeft(), tracker:GetLeft()),
			("Under follows the selected tracker's left edge: %s vs %s"):format(
				tostring(column:GetLeft()),
				tostring(tracker:GetLeft())
			)
		)
		assert(
			near(column:GetTop(), line),
			("Under follows the selected tracker's last line: %s vs %s"):format(
				tostring(column:GetTop()),
				tostring(line)
			)
		)
	end
end

for _, placement in ipairs({ "under", "left" }) do
	scenario(
		"anchor926: Edit Mode moves the native tracker with independent " .. placement .. " placement",
		function(sim)
			local G, column, tracker = setup(sim, placement)
			local previousTop = tracker:GetTop()
			move(G, tracker, 640, -250)
			sim:event("EDIT_MODE_LAYOUTS_UPDATED")
			sim:advance(0.1)
			assert(tracker:IsShown() and near(tracker:GetLeft(), 640), "the native tracker stays shown at the new x")
			assert(near(tracker:GetTop(), previousTop - 50), "the new native tracker y is preserved")
			checkPlacement(column, tracker, placement, tracker.NineSlice:GetBottom())
			local anchors = dependents(sim, tracker, tracker.NineSlice, tracker.Header)
			assert(anchors == "", "ForeverCore must leave the native tracker's anchor family: " .. anchors)
			sim:expectNoErrors("ForeverCore")
		end
	)
end

for _, placement in ipairs({ "under", "left" }) do
	scenario(
		"anchor926: Questie drag keeps the list shown with independent " .. placement .. " placement",
		function(sim)
			local G, column, tracker = setup(sim, placement)
			local list = G.CreateFrame("Frame", "Questie_BaseFrame", G.UIParent)
			list:SetSize(260, 120)
			list:SetMovable(true)
			move(G, list, 540, -170)
			sim:event("QUEST_LOG_UPDATE")
			sim:advance(0.1)
			local previousTop = list:GetTop()
			list:StartMoving()
			-- The simulator leaves cursor-driven movement to the scenario.
			move(G, list, 660, -220)
			list:StopMovingOrSizing()
			sim:event("GLOBAL_MOUSE_UP", "LeftButton")
			sim:advance(0.1)
			assert(list:IsShown() and near(list:GetLeft(), 660), "Questie stays shown at the dropped x")
			assert(near(list:GetTop(), previousTop - 50), "the dropped Questie y is preserved")
			checkPlacement(column, list, placement, list:GetBottom())
			local anchors = dependents(sim, list)
			assert(anchors == "", "ForeverCore must leave Questie's anchor family: " .. anchors)
			list:Hide()
			sim:event("GLOBAL_MOUSE_UP", "LeftButton")
			sim:advance(0.1)
			checkPlacement(column, tracker, placement, tracker.NineSlice:GetBottom())
			sim:expectNoErrors("ForeverCore")
		end
	)
end

scenario("anchor926: Questie's list appears without a quest event after login", function(sim)
	local G, column = setup(sim, "under")
	sim:advance(2)
	local list = G.CreateFrame("Frame", "Questie_BaseFrame", G.UIParent)
	list:SetSize(260, 120)
	move(G, list, 650, -160)
	sim:advance(2)
	checkPlacement(column, list, "under", list:GetBottom())
	sim:expectNoErrors("ForeverCore")
end)

scenario("anchor926: the protected column holds until combat ends", function(sim)
	local G, column, tracker = setup(sim, "left")
	local item = G.CreateFrame("Button", nil, column, "SecureActionButtonTemplate")
	assert(item:IsProtected(), "the secure item button is protected")
	assert(column:IsProtected(), "the item button protects the column")
	local right, top = column:GetRight(), column:GetTop()
	sim:enterCombat()
	move(G, tracker, 660, -250)
	sim:event("EDIT_MODE_LAYOUTS_UPDATED")
	sim:event("GLOBAL_MOUSE_UP", "LeftButton")
	sim:advance(0.1)
	assert(near(tracker:GetLeft(), 660), "the native tracker moves in combat")
	assert(near(column:GetRight(), right) and near(column:GetTop(), top), "the protected column holds during lockdown")
	sim:leaveCombat()
	sim:advance(0.1)
	checkPlacement(column, tracker, "left")
	sim:expectNoErrors("ForeverCore")
end)
