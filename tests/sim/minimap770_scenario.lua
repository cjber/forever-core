-- luacheck: read globals scenario
local function setup(sim, placement, savedPosition)
	local G = sim.G
	sim.screenWidth = 1920
	G.UIParent:SetSize(1920, 768)
	local settings = savedPosition or { placement = placement }
	sim:login({ savedVariables = { ForeverCoreDB = { trackerHost = settings } } })
	local tracker = sim:openObjectiveTracker()
	G.EditModeManagerFrame:UnregisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
	tracker:ClearAllPoints()
	tracker:SetPoint("TOPLEFT", G.UIParent, "TOPLEFT", placement == "left" and 1805 or 1545, 0)
	tracker:SetSize(110, 500)

	local cluster = G.MinimapCluster or G.CreateFrame("Frame", "MinimapCluster", G.UIParent)
	cluster:ClearAllPoints()
	cluster:SetPoint("TOPRIGHT", G.UIParent, "TOPRIGHT", 0, 0)
	cluster:SetSize(280, 220)
	cluster:SetScale(1.24)
	cluster:Show()

	local section = G.ForeverCore.TrackerSection.Create("Minimap770", {
		LayoutContents = function(module)
			module:SetHeader("Quests 3/28")
			for index = 1, 40 do
				local block = module:GetBlock("quest" .. index)
				block:SetHeader("Quest " .. index)
				block:AddObjective(1, "0/8 things")
				module:LayoutBlock(block)
			end
		end,
	}, { maxHeight = "remaining" })
	G.ForeverCore.TrackerHost.Attach(section)
	sim:event("EDIT_MODE_LAYOUTS_UPDATED")
	sim:advance(0.2)
	return G, G.ForeverTrackerCompanion, cluster, section
end

local function clearOfMinimap(column, cluster)
	local bottom = cluster:GetBottom() * cluster:GetEffectiveScale() / column:GetEffectiveScale()
	assert(
		column:GetTop() <= bottom + 0.01,
		("column overlaps the minimap: top %.2f, cluster bottom %.2f"):format(column:GetTop(), bottom)
	)
	assert(math.abs(column:GetTop() - bottom) < 0.01, "the column uses the full space below the cluster")
	assert(column:GetHeight() <= column:GetTop() + 0.01, "the sections lay out within the reduced screen height")
end

for _, placement in ipairs({ "under", "left" }) do
	scenario("minimap770: " .. placement .. " clears the enlarged minimap on a short screen", function(sim)
		local G, column, cluster, section = setup(sim, placement)
		assert(math.abs(column:GetLeft() - 1545) < 0.01, "the column shares the reported horizontal span")
		clearOfMinimap(column, cluster)
		assert(section.trackerOverflow, "long content scrolls in the reduced room")
		for index, event in ipairs({ "DISPLAY_SIZE_CHANGED", "UI_SCALE_CHANGED", "EDIT_MODE_LAYOUTS_UPDATED" }) do
			cluster:SetScale(1.24 + index / 10)
			sim:event(event)
			sim:advance(0.1)
			clearOfMinimap(column, cluster)
		end
		cluster:ClearAllPoints()
		cluster:SetPoint("TOPLEFT", G.UIParent, "TOPLEFT", 0, 0)
		sim:event("EDIT_MODE_LAYOUTS_UPDATED")
		sim:advance(0.1)
		assert(math.abs(column:GetTop() - 768) < 0.01, "a minimap outside the column's span leaves its top alone")

		cluster:ClearAllPoints()
		cluster:SetPoint("TOPRIGHT", G.UIParent, "TOPRIGHT", 0, 0)
		cluster:Hide()
		sim:event("EDIT_MODE_LAYOUTS_UPDATED")
		sim:advance(0.1)
		assert(math.abs(column:GetTop() - 768) < 0.01, "a hidden minimap releases the top of the screen")
		sim:expectNoErrors("ForeverCore")
	end)
end

scenario("minimap770: a saved free position stays where the player put it", function(sim)
	local _, column = setup(sim, "under", { placement = "under", x = 1545, y = 0 })
	assert(
		math.abs(column:GetLeft() - 1545) < 0.01 and math.abs(column:GetTop() - 768) < 0.01,
		"free position stays put"
	)
	sim:expectNoErrors("ForeverCore")
end)
