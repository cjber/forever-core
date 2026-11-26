-- luacheck: read globals scenario
-- #1110: a route and gathering tour extend under the right gryphon on a 1920x804 screen.

local function applyPresetAnchor(G, frame, prefix)
	frame:ClearAllPoints()
	frame:SetPoint(
		G[prefix .. "_POINT"],
		G[G[prefix .. "_RELATIVE_TO"]],
		G[prefix .. "_RELATIVE_POINT"],
		G[prefix .. "_OFFSET_X"],
		G[prefix .. "_OFFSET_Y"]
	)
end

local function placeBars(G)
	local bar, bags, menu = assert(G.MainActionBar), assert(G.BagsBar), assert(G.MicroMenuContainer)
	local caps = assert(bar.EndCaps)
	local left, right = assert(caps.LeftEndCap), assert(caps.RightEndCap)
	-- These are the scenario's anchors. The sim applies Edit Mode anchors only to the objective tracker.
	-- Follow Blizzard_EditMode/Mainline/EditModePresetLayouts.lua with the Camelot preset constants.
	-- Give the unpopulated micromenu space between the main bar and bags as in the reported layout.
	menu:SetSize(380, 45)
	applyPresetAnchor(G, menu, "MICRO_MENU_ANCHOR")
	applyPresetAnchor(G, bar, "MAIN_ACTION_BAR")
	applyPresetAnchor(G, bags, "BAGS_ANCHOR")
	left:ClearAllPoints()
	left:SetPoint("RIGHT", bar, "LEFT", 30, 5)
	right:ClearAllPoints()
	right:SetPoint("LEFT", bags, "RIGHT", -30, 5)
	return bar, caps, left, right
end

local function trackQuests(G, tracker)
	local list = G.CreateFrame("Frame", nil, tracker)
	list.uiOrder, list.leftMargin = 1, 0
	list.SetContainer = function() end
	list.Update = function(self)
		self:SetSize(240, 120)
		return 120, false
	end
	list.GetContentsHeight = function()
		return 120
	end
	list.IsTruncated = function()
		return false
	end
	tracker:AddModule(list)
end

local function startSections(G)
	local Section, Host = G.ForeverCore.TrackerSection, G.ForeverCore.TrackerHost
	local journey = Section.Create("ActionBar1110Journey", {
		LayoutContents = function(module)
			module:SetHeader("Journey")
			local block = module:GetBlock("journey")
			block:SetHeader("Copper Vein")
			block:AddObjective(1, "Walk to Copper Vein")
			module:LayoutBlock(block)
		end,
	}, { order = 1 })
	local tour = Section.Create("ActionBar1110Tour", {
		LayoutContents = function(module)
			module:SetHeader("Gathering Tour")
			for index = 1, 40 do
				local block = module:GetBlock("stop" .. index)
				block:SetHeader("Stop " .. index)
				block:AddObjective(1, "Gather Copper Ore")
				module:LayoutBlock(block)
			end
		end,
	}, { order = 2, maxHeight = "remaining" })
	Host.Attach(journey)
	Host.Attach(tour)
	return journey, tour
end

scenario("actionbar1110: a long tracker column clears the action bar and its gryphons", {
	stubs = { Questie = { height = 120 } },
}, function(sim)
	local G = sim.G
	sim.screenWidth, sim.screenHeight = 1920, 804
	G.UIParent:SetSize(1920, 804)
	sim:loadBlizzard("Blizzard_ActionBar")
	sim:loadBlizzard("Blizzard_MainMenuBarBagButtons")
	sim:login({ savedVariables = { ForeverCoreDB = { trackerHost = { placement = "under", stayUnder = true } } } })
	sim:advance(3)
	local bar, caps, left, right = placeBars(G)
	for _, obstacle in ipairs({ bar, left, right }) do
		local x, _, width, height = sim:rect(obstacle)
		assert(
			obstacle:IsVisible() and x and width > 0 and height > 0,
			obstacle:GetDebugName() .. " has a visible rect"
		)
	end

	local questie = assert(G.Questie_BaseFrame)
	questie:Hide()
	local tracker = assert(sim:openObjectiveTracker())
	trackQuests(G, tracker)
	G.EditModeManagerFrame:UnregisterEvent("EDIT_MODE_LAYOUTS_UPDATED")

	local journey, tour = startSections(G)
	local column = assert(G.ForeverTrackerCompanion)
	local function checkColumn()
		sim:expectOnScreen(column)
		assert(journey:IsVisible() and tour:IsVisible() and tour.trackerOverflow, "the long tour fills the column")
		for _, obstacle in ipairs({ bar, left, right }) do
			sim:expectNoOverlap(column, obstacle)
		end
	end
	local function layout()
		sim:event("EDIT_MODE_LAYOUTS_UPDATED")
		sim:advance(0.5)
		checkColumn()
	end
	local function placeUnder(frame, x)
		frame:ClearAllPoints()
		frame:SetPoint("TOPLEFT", G.UIParent, "TOPLEFT", x, -235)
		layout()
		assert(frame:IsVisible(), "the tracked quest list is visible")
		assert(math.abs(sim:rect(column) - x) < 0.5, "the column follows " .. frame:GetDebugName())
	end

	-- Under the right gryphon as in the report, then under each other obstacle in isolation.
	local rightX = sim:rect(right) + 10
	placeUnder(tracker, rightX)
	local _, visibleBottom = sim:rect(column)

	caps:Hide()
	assert(right:IsShown() and not right:IsVisible(), "the parent hides the gryphon")
	layout()
	local _, hiddenBottom = sim:rect(column)
	assert(hiddenBottom < visibleBottom, "hidden gryphons give the section more room")
	local _, capBottom, _, capHeight = sim:rect(right)
	assert(hiddenBottom < capBottom + capHeight, "the column can use the hidden gryphon's space")

	caps:Show()
	right:SetScale(1.5)
	layout()
	local _, scaledBottom = sim:rect(column)
	assert(scaledBottom > visibleBottom, "the scaled gryphon needs more room")
	right:SetScale(1)

	placeUnder(tracker, sim:rect(bar) + 50)
	placeUnder(tracker, sim:rect(left) - 170)

	-- Questie's own list replaces the native tracker and changes the column's placement back to the right cap.
	tracker:Hide()
	questie:Show()
	placeUnder(questie, rightX)

	sim:setGamepad(true)
	sim:gamepadNavigate()
	layout()
	sim:enterCombat()
	tour:MarkDirty()
	sim:gamepadNavigate()
	layout()
	sim:leaveCombat()
	layout()
	sim:setGamepad(false)
	layout()
end)
