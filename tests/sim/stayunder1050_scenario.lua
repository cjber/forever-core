-- luacheck: read globals scenario
-- #1050: an optional "Always stay under the quest tracker" setting keeps the column under the tracker when room is
-- short instead of falling back to the left pin, laying out its sections in the room left.

local function near(a, b)
	return a and b and math.abs(a - b) < 0.01
end

local function questList(G, tracker, height)
	local list = G.CreateFrame("Frame", nil, tracker)
	list.uiOrder, list.leftMargin, list.height = 1, 0, height
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

local function listEnds(sim, tracker, height)
	tracker.questList.height = height
	tracker:MarkDirty()
	sim:event("QUEST_WATCH_LIST_CHANGED")
	sim:advance(0.2)
end

local function setup(sim, trackerHost, listHeight)
	local G = sim.G
	sim.screenWidth = 1920
	G.UIParent:SetSize(1920, 768)
	sim:login({ savedVariables = { ForeverCoreDB = { trackerHost = trackerHost } } })
	sim:advance(1)
	local section = G.ForeverCore.TrackerSection.Create("StayUnder1050", {
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
	local tracker = sim:openObjectiveTracker()
	tracker.questList = questList(G, tracker, listHeight)
	tracker:ClearAllPoints()
	tracker:SetPoint("TOPRIGHT", G.UIParent, "TOPRIGHT", -100, -100)
	tracker:SetSize(260, 600)
	G.EditModeManagerFrame:UnregisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
	sim:event("EDIT_MODE_LAYOUTS_UPDATED")
	sim:advance(0.5)
	return G, assert(G.ForeverTrackerCompanion), tracker, section
end

local function assertUnder(column, tracker, label)
	assert(
		near(column:GetLeft(), tracker:GetLeft()),
		("%s: expected column left %.2f to match tracker %.2f"):format(label, column:GetLeft(), tracker:GetLeft())
	)
	assert(
		near(column:GetTop(), tracker.NineSlice:GetBottom()),
		("%s: expected column top %.2f to match list bottom %.2f"):format(
			label,
			column:GetTop(),
			tracker.NineSlice:GetBottom()
		)
	)
	assert(
		column:GetHeight() <= column:GetTop() + 0.01,
		("%s: column height %.2f runs past screen bottom from top %.2f"):format(
			label,
			column:GetHeight(),
			column:GetTop()
		)
	)
end

local function assertLeft(column, tracker, label)
	assert(
		near(column:GetRight(), tracker:GetLeft()) and near(column:GetTop(), tracker:GetTop()),
		("%s: expected column pinned left of tracker (right %.2f vs %.2f, top %.2f vs %.2f)"):format(
			label,
			column:GetRight(),
			tracker:GetLeft(),
			column:GetTop(),
			tracker:GetTop()
		)
	)
end

scenario("stayunder1050: off by default, a short screen still moves the column left", function(sim)
	local G, column, tracker = setup(sim, { placement = "under" }, 460)
	local host = G.ForeverCore.TrackerHost
	assert(type(host.GetStayUnder) == "function" and type(host.SetStayUnder) == "function", "exposes getter and setter")
	assert(host.GetStayUnder() == false, "stayUnder is off by default")
	assertLeft(column, tracker, "default off")
	sim:expectNoErrors("ForeverCore")
end)

scenario("stayunder1050: stays under the tracker, lays out in the room left, and responds to toggles", function(sim)
	local G, column, tracker, section = setup(sim, { placement = "under", stayUnder = true }, 460)
	local host = G.ForeverCore.TrackerHost
	assertUnder(column, tracker, "initial long list")
	assert(host.GetStayUnder() == true, "saved stayUnder is read on login")
	assert(section.trackerOverflow, "long content scrolls in the room left below the tracker")

	-- A longer quest list shrinks the column's viewport instead of moving it left.
	local beforeHeight = column:GetHeight()
	listEnds(sim, tracker, 520)
	assertUnder(column, tracker, "longer list")
	assert(column:GetHeight() < beforeHeight, "the column shrinks to fit the smaller room")
	assert(section.trackerOverflow, "the section still scrolls")

	-- A shorter quest list gives the room back.
	listEnds(sim, tracker, 120)
	assertUnder(column, tracker, "shorter list")
	assert(column:GetHeight() > beforeHeight, "the column expands when more room opens below the tracker")

	-- Turning stayUnder off restores the left fallback on a long list; turning it back on returns under.
	listEnds(sim, tracker, 460)
	assertUnder(column, tracker, "long list before toggle off")
	host.SetStayUnder(false)
	sim:advance(0.2)
	assert(host.GetStayUnder() == false, "setter clears stayUnder")
	assertLeft(column, tracker, "toggled off")

	host.SetStayUnder(true)
	sim:advance(0.2)
	assert(host.GetStayUnder() == true, "setter enables stayUnder")
	assertUnder(column, tracker, "toggled back on")

	-- Explicit Left placement still puts the column left without losing the stayUnder preference.
	host.SetPlacement("left")
	sim:advance(0.2)
	assertLeft(column, tracker, "explicit left placement")
	assert(host.GetStayUnder() == true, "switching to left keeps stayUnder saved")
	host.SetPlacement("under")
	sim:advance(0.2)
	assertUnder(column, tracker, "returning to under")

	-- Toggling in combat defers the move until combat ends.
	sim:enterCombat()
	host.SetStayUnder(false)
	sim:advance(0.2)
	assertUnder(column, tracker, "held in combat")
	sim:leaveCombat()
	sim:advance(0.2)
	assertLeft(column, tracker, "applies after combat")

	-- Setting persists across a reload.
	host.SetStayUnder(true)
	sim:advance(0.2)
	assertUnder(column, tracker, "before reload")
	local reloaded = sim:reload()
	assert(reloaded.G.ForeverCore.TrackerHost.GetStayUnder() == true, "stayUnder survives a reload")
	reloaded:expectNoErrors("ForeverCore")
	sim:expectNoErrors("ForeverCore")
end)

scenario("stayunder1050: locked column and right-click menu checkbox", function(sim)
	local G, column, tracker, section = setup(sim, { placement = "under", locked = true, stayUnder = false }, 460)
	local host = G.ForeverCore.TrackerHost
	assertLeft(column, tracker, "locked with stayUnder off pins left")

	-- Right-click the section header and toggle the checkbox inside Tracker position.
	local handler = section.Header:GetScript("OnMouseUp")
	handler(section.Header, "RightButton")
	sim:advance(0.1)

	local function findRow(menuFrame, text)
		for _, row in ipairs(menuFrame.rows or {}) do
			if row:IsShown() and row:GetText() == text then
				return row
			end
		end
	end

	local root = assert(G.ForeverCoreContextMenu, "context menu opens")
	local positionRow = assert(findRow(root, "Tracker position"), "Tracker position menu entry exists")
	sim:hover(positionRow)
	sim:advance(0.5)
	local submenu = assert(G.ForeverCoreContextMenu2, "Tracker position submenu opens")
	local stayRow = assert(
		findRow(submenu, "Always stay under the quest tracker"),
		"stay-under checkbox appears in Tracker position"
	)
	sim:click(stayRow)
	sim:advance(0.2)
	assert(host.GetStayUnder() == true, "menu checkbox enables stayUnder")
	assertUnder(column, tracker, "locked column moves under when stayUnder is enabled")

	-- Growing the quest list while locked with stayUnder on keeps the column under instead of moving left.
	listEnds(sim, tracker, 520)
	assertUnder(column, tracker, "locked column stays under when list grows")
	sim:expectNoErrors("ForeverCore")
end)

scenario("stayunder1050: stayUnder still clears an overlapping enlarged minimap", function(sim)
	local G, column, tracker, section = setup(sim, { placement = "under", stayUnder = true }, 40)
	tracker:ClearAllPoints()
	tracker:SetPoint("TOPLEFT", G.UIParent, "TOPLEFT", 1545, 0)
	local cluster = G.MinimapCluster or G.CreateFrame("Frame", "MinimapCluster", G.UIParent)
	cluster:ClearAllPoints()
	cluster:SetPoint("TOPRIGHT", G.UIParent, "TOPRIGHT", 0, 0)
	cluster:SetSize(280, 220)
	cluster:SetScale(1.24)
	cluster:Show()
	sim:event("EDIT_MODE_LAYOUTS_UPDATED")
	sim:advance(0.2)
	local bottom = cluster:GetBottom() * cluster:GetEffectiveScale() / column:GetEffectiveScale()
	assert(near(column:GetLeft(), 1545), "stays at the tracker's horizontal span")
	assert(column:GetTop() <= bottom + 0.01, "clears the overlapping minimap")
	assert(column:GetHeight() <= column:GetTop() + 0.01, "lays out in the room below the minimap")
	assert(section.trackerOverflow, "long content scrolls below the minimap")
	sim:expectNoErrors("ForeverCore")
end)
