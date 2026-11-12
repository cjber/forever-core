-- luacheck: read globals scenario ADDON
-- The shared Professions tabs: two registered pages, a client side tab, a profession change and a switch back, with
-- the client's own window and side tabs really loaded. Blizzard's window keeps its width and anchor throughout and
-- no page of ours stays shown when the client takes the window back. The same walk runs with the gamepad interface
-- off and on, then under combat lockdown, where the frame work waits for PLAYER_REGEN_ENABLED.
--
-- A window method hook or a read of a page's own Lua would either widen the window or taint the client's own frame
-- work (WFA-38); the module now reads the engine's width and only hooks scripts and events.
scenario("the shared Professions tabs keep one page and one window", function(sim)
	local G = sim.G
	sim.world.professions = {
		{
			skillLineID = 164,
			name = "Blacksmithing",
			skill = 30,
			max = 75,
			categories = { { id = 1, name = "Materials" } },
			recipes = { { id = 2660, name = "Rough Sharpening Stone", category = 1, itemID = 2862 } },
		},
		{
			skillLineID = 333,
			name = "Enchanting",
			skill = 20,
			max = 75,
			categories = { { id = 1, name = "Materials" } },
			recipes = { { id = 7421, name = "Runed Copper Rod", category = 1, itemID = 6218 } },
		},
	}
	sim:login()
	local pf = sim:openProfessions(164)
	assert(pf and pf:IsShown(), "the client's Professions window is open")

	local ns
	for _, entry in ipairs(sim.loader.addons) do
		if entry.name == ADDON then
			ns = entry.ns
		end
	end
	assert(ns and ns.ProfessionTabs, "the shared ProfessionTabs module is loaded")
	local api = ns.ProfessionTabs

	-- The engine's own width and anchor for its crafting window, before any tab is registered, and the client's own
	-- methods, which the module must leave exactly as it found them (WFA-38).
	local width, point = pf:GetWidth(), { pf:GetPoint(1) }
	local expectedWidth = width
	assert(width > 1, "the client gave its window a width")
	local clientMethods = {
		SetWidth = pf.SetWidth,
		ApplyDesiredWidth = pf.ApplyDesiredWidth,
		RefreshRightTabs = pf.RefreshRightTabs,
	}
	local overviewClick = pf.ProfessionsOverviewTab.OnClick

	-- Register two pages as an addon does, after Blizzard_Professions has loaded.
	local registered = sim:runAs(
		ADDON,
		[[
		local ns = ...
		local pageA = CreateFrame("Frame", "ProfessionTabsScenarioPageA", _G.ProfessionsFrame)
		local pageB = CreateFrame("Frame", "ProfessionTabsScenarioPageB", _G.ProfessionsFrame)
		pageA:SetAllPoints(_G.ProfessionsFrame)
		pageB:SetAllPoints(_G.ProfessionsFrame)
		pageA:EnableMouse(true)
		pageB:EnableMouse(true)
		local tabA = ns.ProfessionTabs.Register("a", {
			icon = "Interface\\Icons\\INV_Misc_Note_01",
			tooltip = "Scenario A",
			page = pageA,
		})
		local tabB = ns.ProfessionTabs.Register("b", {
			icon = "Interface\\Icons\\INV_Scroll_03",
			tooltip = "Scenario B",
			page = pageB,
		})
		ns.ProfessionTabsScenario = { pageA = pageA, pageB = pageB, tabA = tabA, tabB = tabB }
	]],
		ns
	)
	assert(registered, "the scenario's two tabs registered without an error")
	local scenario = ns.ProfessionTabsScenario
	local pageA, pageB = scenario.pageA, scenario.pageB
	local tabA, tabB = scenario.tabA, scenario.tabB
	assert(pageA and pageB and tabA and tabB, "both pages and tabs were registered")
	for name, method in pairs(clientMethods) do
		assert(pf[name] == method, "the module replaced ProfessionsFrame:" .. name)
	end
	assert(pf.ProfessionsOverviewTab.OnClick == overviewClick, "the module replaced a native side tab's OnClick")

	local function stable(label)
		assert(pf:GetWidth() == expectedWidth, label .. ": the window width changed to " .. tostring(pf:GetWidth()))
		local now = { pf:GetPoint(1) }
		assert(#now == #point, label .. ": the window anchor changed")
		for index = 1, #point do
			assert(now[index] == point[index], label .. ": the window anchor changed at " .. index)
		end
	end

	local function shown()
		local count, page = 0, nil
		for _, candidate in ipairs({ pageA, pageB }) do
			if candidate:IsShown() then
				count, page = count + 1, candidate
			end
		end
		return count, page
	end

	-- The native page owns the search, rank and recipe controls. If it remains shown below a custom page, those
	-- controls are still visible and their hit regions overlap the addon surface.
	local function nativeShown()
		for _, name in ipairs({ "CraftingPage", "BookPage", "SpecPage", "OrdersPage" }) do
			local native = pf[name]
			if native and native:IsShown() and native:GetAlpha() > 0 then
				return true, name
			end
		end
		return false
	end

	-- Tab art is how a check reads: the template shows its selected texture when SetChecked is true.
	local function checked(tab)
		return tab.SelectedTexture and tab.SelectedTexture:IsShown()
	end

	local function selectTab(tab)
		sim.widgets.dispatch(tab, "OnMouseUp", "LeftButton", true)
		sim:advance(0.05)
	end

	local function selectNative(tab)
		sim.widgets.dispatch(tab, "OnMouseUp", "LeftButton", true)
		sim:advance(0.05)
	end

	-- The full walk, as the player makes it. In combat the checked tab changes at once and the pages and the width
	-- wait; the state is asserted when the client leaves combat.
	local function walk(label, inCombat)
		if not inCombat then
			api.ShowNative()
		end

		if not inCombat then
			expectedWidth = 850
		end
		selectTab(tabA)
		assert(api.Selected() == "a", label .. ": tab A is not the selected tab")
		assert(checked(tabA), label .. ": tab A is not checked")
		if not inCombat then
			local count, page = shown()
			assert(count == 1 and page == pageA, label .. ": selecting A did not show exactly its own page")
			local native, name = nativeShown()
			assert(not native, label .. ": native " .. tostring(name) .. " controls remained visible under page A")
		end
		stable(label .. " after A")

		selectTab(tabB)
		assert(api.Selected() == "b", label .. ": tab B is not the selected tab")
		assert(checked(tabB), label .. ": tab B is not checked")
		if not inCombat then
			local count, page = shown()
			assert(count == 1 and page == pageB, label .. ": selecting B did not show exactly its own page")
			local native, name = nativeShown()
			assert(not native, label .. ": native " .. tostring(name) .. " controls remained visible under page B")
		end
		stable(label .. " after B")

		selectNative(pf.ProfessionsOverviewTab)
		assert(api.Selected() == nil, label .. ": a client side tab did not take the window back")
		assert(not checked(tabA) and not checked(tabB), label .. ": a registered tab stayed checked")
		if not inCombat then
			local count = shown()
			assert(count == 0, label .. ": a registered page stayed shown after a client side tab")
			local native, name = nativeShown()
			assert(native, label .. ": native " .. tostring(name) .. " controls were not restored")
		end
		if not inCombat then
			expectedWidth = 673
		end
		stable(label .. " after a client side tab")

		sim:openProfessions(333)
		sim:advance(0.2)
		assert(api.Selected() == nil, label .. ": a profession change did not hand the window back")
		if not inCombat then
			expectedWidth = 673
		end
		stable(label .. " after a profession change")

		if not inCombat then
			expectedWidth = 850
		end
		selectTab(tabA)
		assert(api.Selected() == "a", label .. ": tab A did not select again after a profession change")
		if not inCombat then
			local count, page = shown()
			assert(count == 1 and page == pageA, label .. ": switching back did not show exactly A's page")
		end
		stable(label .. " after A again")
	end

	walk("gamepad off", false)

	sim:setGamepad(true)
	assert(G.InputUtil.IsGamepadUIEnabled(), "the gamepad interface is on")
	sim:gamepadNavigate()
	walk("gamepad on", false)

	-- A registration can raise its minWidth after it registered and lower it again. The window takes the new width at
	-- once, keeps it across a tab switch and a profession change, and goes back to the client's width when cleared.
	local raised = sim:runAs(
		ADDON,
		[[
		local ns = ...
		local raisedWidth = _G.ProfessionsFrame:GetWidth() + 120
		ns.ProfessionTabsScenario.raisedWidth = raisedWidth
		ns.ProfessionTabs.SetMinWidth("a", raisedWidth)
	]],
		ns
	)
	assert(raised, "raising a registration's minWidth failed")
	expectedWidth = scenario.raisedWidth
	assert(
		pf:GetWidth() == expectedWidth,
		"raising a registration's minWidth did not widen the window: " .. tostring(pf:GetWidth())
	)
	stable("after raising a minWidth")
	selectTab(tabB)
	stable("after a tab switch at the raised width")
	sim:openProfessions(333)
	sim:advance(0.2)
	stable("after a profession change at the raised width")

	-- The client's book and crafting pages keep the client's own width after handback; a selected registered page alone
	-- takes the raised width.
	selectNative(pf.ProfessionsOverviewTab)
	assert(pf.BookPage:IsShown(), "the overview tab did not show the client's book page")
	expectedWidth = 673
	stable("on the book page at the raised width")
	selectTab(tabB)
	expectedWidth = scenario.raisedWidth
	stable("a registered page over the book page")
	sim:openProfessions(333)
	sim:advance(0.2)
	expectedWidth = 673
	stable("the crafting page after the book page")

	local lowered = sim:runAs(
		ADDON,
		[[
		local ns = ...
		ns.ProfessionTabs.SetMinWidth("a", nil)
	]],
		ns
	)
	assert(lowered, "clearing a registration's minWidth failed")
	expectedWidth = 673
	assert(
		pf:GetWidth() == expectedWidth,
		"clearing a registration's minWidth did not restore the client width: " .. tostring(pf:GetWidth())
	)
	stable("after clearing the minWidth")

	-- In combat only the checked state changes; leaving combat applies the page and the width.
	api.ShowNative()
	sim:enterCombat()
	walk("in combat", true)
	assert(checked(tabA), "the combat walk lost tab A's checked state")
	sim:leaveCombat()
	sim:advance(0.2)
	local count, page = shown()
	assert(count == 1 and page == pageA, "leaving combat did not show exactly tab A's page")
	expectedWidth = 850
	stable("after combat")

	sim:expectNoErrors(ADDON)
	sim:expectNoGamepadTaint(ADDON)
end)
