-- luacheck: read globals scenario ADDON
-- With the gamepad interface on, the Forever addons settings page built its rows in addon execution. Blizzard's
-- secure row build read that data, and the gamepad fields it wrote tainted the binding stack, so closing the page
-- had the game refuse a controller action and blame ForeverCore (cjber/tweaks-forever#446). The page now builds its
-- checkbox and button rows through CreateSecureDelegate, as the client's own settings code does.
--
-- The page is registered as the client's own vertical rows with the gamepad interface on, as Family.Register does,
-- then every row is selected the way one cursor move does: scroll it into view and select its target. Backing out
-- with B and closing the panel writes the binding stack; a target change then makes the action bar's protected call.
scenario("the Forever addons settings page leaves the gamepad binding stack to the game", function(sim)
	local G = sim.G
	local W = sim.widgets

	-- The client opens the panel itself: a C function that calls SettingsPanel:OpenToCategory.
	sim.impl["C_SettingsUtil.OpenSettingsPanel"] = function(categoryID, scrollTo)
		return G.SettingsPanel:OpenToCategory(categoryID, scrollTo)
	end

	-- SmartNavigation runs the cursor target's enter and leave scripts through FocusEnter/FocusExit, native methods
	-- the sim leaves empty. The client runs them as the frame's OnEnter/OnLeave in the caller's execution, including
	-- the hover region over a row's label, so a tooltip of ours there runs in the same call.
	local function hoverRegion(frame)
		local region = frame.Tooltip
		return region and region.smartNavigationProxyTarget == frame and region or nil
	end
	for _, methods in pairs(W.methods) do
		methods.FocusEnter = function(self)
			W.fire(self, "OnEnter", true)
			if hoverRegion(self) then
				W.fire(hoverRegion(self), "OnEnter", true)
			end
		end
		methods.FocusExit = function(self)
			W.fire(self, "OnLeave", false)
			if hoverRegion(self) then
				W.fire(hoverRegion(self), "OnLeave", false)
			end
		end
	end

	-- Natives the gamepad frame manager calls as a panel hides, which the sim does not define.
	G.SpellCanTargetItem = G.SpellCanTargetItem or function()
		return false
	end
	G.SpellStopTargeting = G.SpellStopTargeting or function() end
	-- The gamepad interface is on before the addon loads, as after a reload with it enabled.
	sim:setGamepad(true)
	sim:login()
	assert(G.InputUtil.IsGamepadUIEnabled(), "the gamepad interface is on")

	-- Every write to the binding stack, and the taint it ran under.
	local IBM = G.GamepadSharedUtility.InputBindingManager
	local writes, tainted = 0, {}
	for _, method in ipairs({ "AddBindingSet", "RemoveSet", "SetCoreBindingSet", "ClearBindings" }) do
		local original = IBM[method]
		IBM[method] = function(self, ...)
			writes = writes + 1
			local by = sim.taint.current
			if by then
				tainted[#tainted + 1] = method .. " by " .. by
			end
			return original(self, ...)
		end
	end

	-- Register the page as Family.Register does with the gamepad interface on: the client's own vertical rows.
	local ns = sim.loader.addons[ADDON].ns
	local category
	sim:runAs(
		ADDON,
		[[
		local ns = ...
		local category = Settings.RegisterVerticalLayoutCategory("Forever Family Test")
		Settings.RegisterAddOnCategory(category)
		ns.Family.Register(category, {}, "LegacyForever")
		return category
	]],
		ns
	)
	for _, candidate in ipairs(G.SettingsPanel:GetAllCategories()) do
		if candidate:GetName() == "Forever Family Test" then
			category = candidate
		end
	end
	assert(category, "the Forever addons page is under Options > AddOns")

	-- The shared opener asks the client's restricted function through its secure delegate (cjber/forever-core#333).
	-- Open the page itself, so the client builds its rows.
	assert(ns and ns.OpenSettingsPanel, "the shared settings opener is loaded")
	sim:input(function()
		ns.OpenSettingsPanel(category:GetID())
	end)
	sim:advance(0.2)
	assert(G.SettingsPanel:IsShown(), "the settings panel is open")

	-- The cursor's target on a row: its checkbox or button when it has one, else the row itself.
	local function target(row)
		return row.Tooltip and row.Tooltip.smartNavigationProxyTarget or row
	end

	local rows = 0
	for _, sub in ipairs(category:GetSubcategories()) do
		sim:input(function()
			G.SettingsPanel:SelectCategory(sub)
		end)
		sim:advance(0.1)
		local first = G.SettingsPanel:GetFirstSmartNavFocusableSettingFrame()
		assert(first and first:IsVisible(), sub:GetName() .. ": the cursor's first target is hidden")
		local box = G.SettingsPanel:GetSettingsList().ScrollBox
		local count = box:GetDataProvider():GetSize()
		assert(count > 0, sub:GetName() .. " has rows")
		for index = 1, count do
			local row
			-- One D-pad press: scroll the next row into view, then select it.
			sim:input(function()
				box:ScrollToElementDataIndex(index, nil, nil, true)
				row = box:FindFrame(box:GetDataProvider():Find(index))
				G.SmartNavigation:SelectButton(target(row))
			end)
			sim:advance(0.05)
			assert(row, sub:GetName() .. ": row " .. index .. " has a frame")
			rows = rows + 1
		end
	end
	-- The hint setting, the Thanks row, a row per other addon and the Ko-fi row, with LegacyForever's own row
	-- left out.
	assert(rows == #ns.Family.ADDONS + 2, "the walk reached every row of the page")

	-- B out of the rows, then out of the panel.
	sim:input(function()
		G.SmartNavigation:AttemptClose()
	end)
	sim:input(function()
		G.SettingsPanel:Close()
	end)
	sim:advance(0.2)
	assert(not G.SettingsPanel:IsShown(), "the settings panel closed")

	-- A target change: the action bar reads the binding stack, then makes its protected call. A tainted entry taints
	-- that read, and the client blocks the call.
	sim:input(function()
		G.SetPreferredGamepadInteractTarget(nil)
	end)
	sim:advance(0.05)

	sim:expectNoErrors(ADDON)
	sim:expectNoGamepadTaint(ADDON)
	assert(writes > 0, "the walk reached the binding stack")
	assert(#tainted == 0, "the binding stack was written under the addon's taint:\n" .. table.concat(tainted, "\n"))
end)
