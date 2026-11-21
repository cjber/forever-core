-- luacheck: read globals scenario
local function dependsOnTracker(frame, trackers, seen)
	if not frame or seen[frame] then
		return false
	end
	if trackers[frame] then
		return true
	end
	seen[frame] = true
	for index = 1, frame:GetNumPoints() do
		local _, relative = frame:GetPoint(index)
		if dependsOnTracker(relative, trackers, seen) then
			return true
		end
	end
	return dependsOnTracker(frame:GetParent(), trackers, seen)
end

scenario("editmode_drag: snapping a dragged objective tracker keeps the column independent", function(sim)
	local G = sim.G
	sim:login({ savedVariables = { ForeverCoreDB = { trackerHost = { placement = "left" } } } })
	local section = G.ForeverCore.TrackerSection.Create("EditModeDrag", {
		LayoutContents = function(module)
			module:SetHeader("Journey")
			local block = module:GetBlock("step")
			block:SetHeader("Step")
			module:LayoutBlock(block)
		end,
	}, { order = -3 })
	G.ForeverCore.TrackerHost.Attach(section)
	local tracker = sim:openObjectiveTracker()
	sim:advance(3)

	sim:runAs("Questie", [[CreateFrame("Frame", "Questie_BaseFrame", UIParent)]])
	local questie = assert(G.Questie_BaseFrame)
	questie:SetSize(200, 100)
	questie:SetPoint("TOPRIGHT", G.UIParent, "TOPRIGHT", -50, -50)
	sim:event("QUEST_LOG_UPDATE")
	sim:advance(0.1)

	local manager = G.EditModeManagerFrame
	local magnetism = G.EditModeMagnetismManager
	-- Enter the drag-relevant Edit Mode state without opening its settings dialog.
	manager.editModeActive = true
	tracker.Selection:Show()
	tracker.isSelected = true
	tracker:SetMovable(true)
	local candidate = G.CreateFrame("Frame", nil, G.UIParent)
	G.Mixin(candidate, G.EditModeSystemMixin)
	candidate:SetSize(60, 60)
	candidate:SetPoint("BOTTOMLEFT", G.UIParent, "BOTTOMLEFT", 60, 80)
	candidate.Selection = candidate
	tracker.isManagedFrame = false
	manager.snapEnabled = true
	magnetism.magneticFrames = { [candidate] = true }
	magnetism:UpdateTopLevelParentPoints()
	tracker.Selection:OnDragStart()
	assert(tracker.isDragging and manager.snapPreviewFrame == tracker, "the tracker started a snap-preview drag")

	local column = assert(G.ForeverTrackerCompanion)
	local trackers = { [tracker] = true, [tracker.NineSlice] = true, [questie] = true }
	local initialRight, initialTop = column:GetRight(), column:GetTop()

	-- StartMoving is a simulator stub. Move the tracker to the screen position of each synthetic drag step.
	for _, x in ipairs({ -100, -120, -140 }) do
		sim.mouseX, sim.mouseY = G.UIParent:GetRight() + x, G.UIParent:GetTop() - 200
		local mouseX, mouseY = G.GetCursorPosition()
		tracker:ClearAllPoints()
		tracker:SetPoint("TOPRIGHT", G.UIParent, "BOTTOMLEFT", mouseX, mouseY)
		manager:OnUpdate()
		local left, bottom, width, height = tracker.Selection:GetRect()
		assert(left and bottom and width and height, "the dragged tracker selection has a rect")
	end
	assert(not dependsOnTracker(column, trackers, {}), "the column depends on the tracker's anchor chain")
	sim:event("QUEST_LOG_UPDATE")
	sim:advance(0.1)
	assert(column:GetRight() == initialRight and column:GetTop() == initialTop, "the column holds during the drag")

	-- Keep the final cursor position and route the release through the real drag-stop handler.
	manager.snapEnabled = false
	tracker.Selection:OnDragStop()
	assert(not tracker.isDragging, "the tracker stopped dragging")
	sim:event("GLOBAL_MOUSE_UP", "LeftButton")
	sim:advance(0.1)
	local scale = tracker:GetEffectiveScale() / column:GetEffectiveScale()
	assert(column:GetRight() ~= initialRight or column:GetTop() ~= initialTop, "the column moved after release")
	assert(math.abs(column:GetRight() - tracker:GetLeft() * scale) < 0.01, "the column meets the tracker's left edge")
	assert(math.abs(column:GetTop() - tracker:GetTop() * scale) < 0.01, "the column meets the tracker's top edge")
	sim:expectNoErrors()

	assert(not dependsOnTracker(column, trackers, {}), "the released column stays independent")
	for _, frame in ipairs(sim.widgets.all) do
		local state = sim.widgets.state[frame]
		if state.isFrame and state.creator == "ForeverCore" then
			assert(
				not dependsOnTracker(frame, trackers, {}),
				("ForeverCore frame %s (%s) depends on a tracker"):format(tostring(frame:GetName()), state.kind)
			)
		end
	end
end)
