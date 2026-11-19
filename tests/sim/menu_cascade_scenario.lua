-- luacheck: read globals scenario ADDON
-- The suite's context menu under the client: resting on a submenu row opens its level beside the row while the
-- parent stays shown, as Blizzard_Menu's submenus do, and a leaf closes every level.
scenario("menu cascade: a submenu opens beside its row and the parent stays open", function(sim)
	local G = sim.G
	sim:login()
	local picked = 0
	G.ForeverCoreMenuCascadeSpec = function()
		picked = picked + 1
	end
	sim:runAs(
		ADDON,
		[[
		ForeverCore.ContextMenu(UIParent, function(_, root)
			root:CreateTitle("Journey")
			root:CreateButton("Go", function() end)
			local tracker = root:CreateButton("Tracker")
			tracker:CreateButton("Tracker position"):CreateButton("Left", ForeverCoreMenuCascadeSpec)
			tracker:CreateButton("Tracker background")
		end)
	]]
	)
	sim:advance(0.1)
	local root = assert(G.ForeverCoreContextMenu, "the root level exists")
	assert(root:IsShown(), "the root level opens")
	local trackerRow = root.rows[3]
	assert(trackerRow:GetText() == "Tracker", "the submenu row is the third")
	sim:hover(trackerRow)
	sim:advance(0.5)
	local second = assert(G.ForeverCoreContextMenu2, "hovering the row builds the next level")
	assert(second:IsShown(), "the submenu opens on hover")
	assert(root:IsShown(), "the parent level stays open")
	assert(second.rows[1]:GetText() == "Tracker position", "the submenu starts with its own first entry, no Back row")
	local point, relative, relativePoint = second:GetPoint(1)
	assert(relative == trackerRow, "the submenu is anchored to its row")
	assert(
		(point == "TOPLEFT" and relativePoint == "TOPRIGHT") or (point == "TOPRIGHT" and relativePoint == "TOPLEFT"),
		"beside the row, not in place of the menu"
	)
	sim:hover(second.rows[1])
	sim:advance(0.5)
	local third = assert(G.ForeverCoreContextMenu3, "a nested submenu cascades")
	assert(third:IsShown() and second:IsShown() and root:IsShown(), "all three levels are open together")
	sim:click(third.rows[1])
	sim:advance(0.1)
	assert(picked == 1, "the leaf runs once")
	assert(not root:IsShown() and not second:IsShown() and not third:IsShown(), "a leaf closes every level")
	sim:expectNoErrors(ADDON)
end)
