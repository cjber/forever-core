-- luacheck: read globals scenario ADDON
-- Where the shared side-tab column sits when other things share the space outside the Professions window's right edge
-- (skillup-forever#807: players report the SkillUp tab gone, or moved to the window bottom on Cooking).
local function profession(id, name)
	return {
		skillLineID = id,
		name = name,
		skill = 30,
		max = 75,
		categories = { { id = 1, name = "Materials" } },
		recipes = { { id = 2660 + id, name = name .. " Recipe", category = 1, itemID = 2862 } },
	}
end

local function setup(sim, professions)
	sim.world.professions = professions
	sim:login()
	local pf = sim:openProfessions(professions[1].skillLineID)
	local ns
	for _, entry in ipairs(sim.loader.addons) do
		if entry.name == ADDON then
			ns = entry.ns
		end
	end
	assert(
		sim:runAs(
			ADDON,
			[[
		local ns = ...
		local page = CreateFrame("Frame", nil, _G.ProfessionsFrame)
		page:SetAllPoints(_G.ProfessionsFrame)
		ns.ColumnScenarioTab = ns.ProfessionTabs.Register("col", {
			icon = "Interface\\Icons\\INV_Misc_Note_01",
			tooltip = "Col",
			page = page,
		})
	]],
			ns
		),
		"registering the tab failed"
	)
	sim:advance(0.1)
	return pf, ns.ColumnScenarioTab
end

local function lastNative(pf)
	local last = pf.ProfessionsOverviewTab
	for _, native in ipairs(pf.rightProfessionTabs or {}) do
		if native:IsShown() then
			last = native
		end
	end
	return last
end

-- The tab is placed, on screen, and starts at most one tab height under the last client tab.
local function placed(label, pf, tab)
	local top, bottom, left = tab:GetTop(), tab:GetBottom(), tab:GetLeft()
	assert(top and bottom and left, label .. ": the tab has no position")
	local native = lastNative(pf)
	local gap = native:GetBottom() - top
	assert(gap >= 0 and gap < 60, label .. ": the tab sits " .. tostring(gap) .. " under the last client tab")
	assert(bottom > 0, label .. ": the tab is below the screen")
end

scenario("the side tab sits under seven client profession tabs", function(sim)
	local pf, tab = setup(sim, {
		profession(164, "Blacksmithing"),
		profession(186, "Mining"),
		profession(393, "Skinning"),
		profession(129, "First Aid"),
		profession(356, "Fishing"),
		profession(185, "Cooking"),
		profession(182, "Herbalism"),
	})
	local shown = 0
	for _, native in ipairs(pf.rightProfessionTabs or {}) do
		if native:IsShown() then
			shown = shown + 1
		end
	end
	assert(shown >= 6, "the client showed only " .. shown .. " profession tabs")
	placed("seven professions", pf, tab)
	sim:openProfessions(185)
	sim:advance(0.2)
	placed("seven professions, Cooking", pf, tab)
	sim:expectNoErrors(ADDON)
end)

scenario("another addon stacking two tabs under ours does not take the column away", function(sim)
	local pf, tab = setup(sim, { profession(164, "Blacksmithing"), profession(185, "Cooking") })
	-- Another addon places its first tab under the last tab it sees, ours, and its second under its first.
	local G = sim.G
	local x1 = G.CreateFrame("Button", nil, pf, "LargeSideTabButtonTemplate")
	local x2 = G.CreateFrame("Button", nil, pf, "LargeSideTabButtonTemplate")
	x1:SetPoint("TOPLEFT", tab, "BOTTOMLEFT", 0, -2)
	x2:SetPoint("TOPLEFT", x1, "BOTTOMLEFT", 0, -2)
	x1:Show()
	x2:Show()
	sim:openProfessions(185)
	sim:advance(0.2)
	placed("two stacked tabs, Cooking", pf, tab)
	sim:openProfessions(164)
	sim:advance(0.2)
	placed("two stacked tabs, back", pf, tab)
	sim:expectNoErrors(ADDON)
end)

scenario("a frame docked at the window's bottom right does not pull the column down", function(sim)
	local pf, tab = setup(sim, { profession(164, "Blacksmithing"), profession(185, "Cooking") })
	local G = sim.G
	local dock = G.CreateFrame("Frame", nil, pf)
	dock:SetSize(120, 40)
	dock:SetPoint("BOTTOMLEFT", pf, "BOTTOMRIGHT", -20, 0)
	dock:Show()
	G.HideUIPanel(pf)
	sim:advance(0.1)
	sim:openProfessions(185)
	sim:advance(0.2)
	assert(pf:IsShown(), "the window reopened")
	placed("docked frame, Cooking", pf, tab)
	sim:expectNoErrors(ADDON)
end)

scenario("a foreign tab in the second slot is not covered by our second tab", function(sim)
	local pf, tab = setup(sim, { profession(164, "Blacksmithing"), profession(185, "Cooking") })
	local ns
	for _, entry in ipairs(sim.loader.addons) do
		if entry.name == ADDON then
			ns = entry.ns
		end
	end
	assert(
		sim:runAs(
			ADDON,
			[[
		local ns = ...
		local page = CreateFrame("Frame", nil, _G.ProfessionsFrame)
		page:SetAllPoints(_G.ProfessionsFrame)
		ns.ColumnScenarioTab2 = ns.ProfessionTabs.Register("col2", {
			icon = "Interface\\Icons\\INV_Scroll_03",
			tooltip = "Col2",
			page = page,
		})
	]],
			ns
		),
		"registering the second tab failed"
	)
	local second = ns.ColumnScenarioTab2
	assert(second, "the second tab registered")
	local G = sim.G
	local native = lastNative(pf)
	-- Another addon anchors its tab to the window, one free slot under the client's last tab.
	local foreign = G.CreateFrame("Button", nil, pf, "LargeSideTabButtonTemplate")
	local slot = 2 + tab:GetHeight()
	local offset = pf:GetTop() - native:GetBottom() + slot + 2
	foreign:SetPoint("TOPLEFT", pf, "TOPRIGHT", native:GetLeft() - pf:GetRight(), -offset)
	foreign:Show()
	G.HideUIPanel(pf)
	sim:advance(0.1)
	sim:openProfessions(164)
	sim:advance(0.2)
	for label, ours in pairs({ first = tab, second = second }) do
		local overlaps = ours:GetTop() > foreign:GetBottom() and ours:GetBottom() < foreign:GetTop()
		assert(not overlaps, "our " .. label .. " tab covers the foreign tab")
	end
	sim:expectNoErrors(ADDON)
end)
