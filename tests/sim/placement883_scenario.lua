-- luacheck: read globals scenario
-- #883, #885: where the column sits under the game's quest tracker is one read of what the tracker shows: its list's
-- last line, its header alone when the player collapses it, or its top when it hides with nothing to list. The column
-- takes that place whenever it changes, with no layout of its own sections, and a login or reload puts it in the same
-- place as the session that changed it.

local function questList(G, tracker, height)
	local list = G.CreateFrame("Frame", nil, tracker)
	list.uiOrder, list.leftMargin, list.height = 1, 0, height
	list.SetContainer = function() end
	list.Update = function(module)
		if module.parentContainer and module.parentContainer:IsCollapsed() then
			module:Hide()
		else
			module:SetSize(240, module.height)
			module:Show()
		end
		return module.height, false
	end
	list.GetContentsHeight = function(module)
		return module.height
	end
	list.IsTruncated = function()
		return false
	end
	list.parentContainer = tracker
	tracker:AddModule(list)
	return list
end

local function near(a, b)
	return a and b and math.abs(a - b) < 0.01
end

-- A sim from sim:reload() has already logged in with the saved state; a new one logs in here.
local function login(sim, height, reloaded)
	local G = sim.G
	if not reloaded then
		sim:login({ savedVariables = { ForeverCoreDB = { trackerHost = {} } } })
	end
	sim:advance(3)
	local layouts = 0
	local section
	section = G.ForeverCore.TrackerSection.Create("Placement883", {
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
	if height then
		tracker.questList = questList(G, tracker, height)
	end
	tracker:ClearAllPoints()
	tracker:SetPoint("TOPRIGHT", G.UIParent, "TOPRIGHT", -100, -200)
	tracker:SetSize(260, 600)
	G.EditModeManagerFrame:UnregisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
	sim:event("EDIT_MODE_LAYOUTS_UPDATED")
	sim:advance(3)
	return G, assert(G.ForeverTrackerCompanion), tracker, function()
		return layouts
	end, section
end

-- The player clicks the tracker's collapse button: the client fires GLOBAL_MOUSE_UP for the click.
local function toggle(sim, tracker)
	sim:click(tracker.Header.MinimizeButton)
	sim:event("GLOBAL_MOUSE_UP", "LeftButton")
	sim:advance(0.1)
end

local function underHeader(column, tracker)
	return near(column:GetTop(), tracker.Header:GetBottom()) and near(column:GetLeft(), tracker:GetLeft())
end

local function left(column, tracker)
	return near(column:GetRight(), tracker:GetLeft()) and near(column:GetTop(), tracker:GetTop())
end

scenario("placement883: a collapsed tracker puts the column under its header, and expanding puts it back", function(sim)
	local _, column, tracker, layouts = login(sim, 520)
	assert(left(column, tracker), "a long list leaves no room under it: the column is left of the tracker")
	local before = layouts()
	toggle(sim, tracker)
	assert(tracker:IsCollapsed(), "the click collapsed the tracker")
	assert(underHeader(column, tracker), "the collapsed tracker's header has room under it: the column moves there")
	toggle(sim, tracker)
	assert(not tracker:IsCollapsed(), "the second click expanded it")
	assert(left(column, tracker), "the long list is back: the column is left again")
	assert(layouts() == before, "neither move laid out a section")
	sim:expectNoErrors("ForeverCore")
end)

scenario("placement883: a collapsed tracker at login places the column as the session did", function(sim)
	local _, column, tracker = login(sim, 520)
	toggle(sim, tracker)
	local top, x = column:GetTop(), column:GetLeft()
	column:MarkDirty()
	sim:advance(0.5)
	assert(near(column:GetTop(), top) and near(column:GetLeft(), x), "a layout keeps the collapsed place")
	sim:expectNoErrors("ForeverCore")
end)

scenario("placement885: the tracker hiding moves the column to its top at once, as a login does", function(sim)
	local _, column, tracker, layouts, section = login(sim, 520)
	assert(left(column, tracker), "a long list: the column is left of the tracker")
	-- A section the player collapsed stays collapsed through every move below.
	sim:click(section.Header.MinimizeButton)
	sim:advance(0.5)
	assert(section:IsCollapsed(), "the click collapsed the section")
	local before = layouts()
	-- The last tracked quest leaves the list (an untrack, or a journey taking the watches): the tracker hides.
	tracker:RemoveModule(tracker.questList)
	sim:advance(0.1)
	assert(not tracker:IsShown(), "the game's tracker hides with nothing to list")
	sim:event("QUEST_WATCH_LIST_CHANGED")
	sim:advance(0.1)
	local top, x = column:GetTop(), column:GetLeft()
	assert(near(top, tracker:GetTop()) and near(x, tracker:GetLeft()), "the column takes the hidden tracker's top")
	assert(layouts() == before, "with no layout of its sections")
	assert(section:IsCollapsed(), "the tracker hiding leaves the section collapsed")
	-- A login with nothing to list puts it in the same place.
	local fresh = sim:reload()
	local _, column2, tracker2 = login(fresh, nil, true)
	assert(not tracker2:IsShown(), "after the reload the tracker is still hidden")
	assert(
		near(column2:GetTop(), tracker2:GetTop()) and near(column2:GetLeft(), tracker2:GetLeft()),
		("the reload places the column where the session did: top %s vs %s, left %s vs %s"):format(
			tostring(column2:GetTop()),
			tostring(top),
			tostring(column2:GetLeft()),
			tostring(x)
		)
	)
	fresh:expectNoErrors("ForeverCore")
	-- Back in the first session, a quest tracked again brings the list back and the column follows its line, or its
	-- left place.
	tracker:AddModule(tracker.questList)
	sim:advance(0.1)
	sim:event("QUEST_WATCH_LIST_CHANGED")
	sim:advance(0.1)
	assert(left(column, tracker), "the list back: the column is left again")
	assert(section:IsCollapsed(), "the list coming back leaves it collapsed too")
	sim:expectNoErrors("ForeverCore")
end)

scenario("placement885: a quest turned in that empties the tracker moves the column too", function(sim)
	local _, column, tracker = login(sim, 120)
	assert(near(column:GetTop(), tracker.NineSlice:GetBottom()), "a short list: the column is under it")
	tracker:RemoveModule(tracker.questList)
	sim:event("QUEST_LOG_UPDATE")
	sim:advance(0.1)
	assert(not tracker:IsShown(), "the game's tracker hides with nothing to list")
	assert(
		near(column:GetTop(), tracker:GetTop()) and near(column:GetLeft(), tracker:GetLeft()),
		"the column takes the hidden tracker's top"
	)
	sim:expectNoErrors("ForeverCore")
end)

scenario(
	"placement883: collapsing the column's own sections lets it fit under the tracker, and opening them puts it back",
	function(sim)
		local _, column, tracker, _, section = login(sim, 400)
		assert(
			left(column, tracker),
			"a long list leaves no room under it for the open column: it is left of the tracker"
		)
		sim:click(section.Header.MinimizeButton)
		sim:advance(0.5)
		assert(section:IsCollapsed(), "the click collapsed the section")
		assert(
			near(column:GetTop(), tracker.NineSlice:GetBottom()) and near(column:GetLeft(), tracker:GetLeft()),
			("the collapsed column fits under the list: top %s vs %s"):format(
				tostring(column:GetTop()),
				tostring(tracker.NineSlice:GetBottom())
			)
		)
		sim:click(section.Header.MinimizeButton)
		sim:advance(0.5)
		assert(left(column, tracker), "the open column no longer fits: it is left again")
		sim:expectNoErrors("ForeverCore")
	end
)
