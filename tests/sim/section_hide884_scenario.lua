-- luacheck: read globals scenario
-- #884: a section's own show switch, the one its "Hide this section" entry turns off, hides the section whether the
-- player has it open or collapsed.

local function section(sim, name)
	local G = sim.G
	local shown = true
	local module
	local show = {
		get = function()
			return shown
		end,
		set = function(value)
			shown = value
			module:MarkDirty()
		end,
		where = "Test settings",
	}
	module = G.ForeverCore.TrackerSection.Create(name, {
		LayoutContents = function(self)
			if not shown then
				return
			end
			self:SetHeader(name)
			for index = 1, 3 do
				local block = self:GetBlock("row" .. index)
				block:SetHeader("Step " .. index)
				self:LayoutBlock(block)
			end
		end,
	}, { show = show })
	-- The section is made after login here, so it attaches itself as its own load would.
	G.ForeverCore.TrackerHost.Attach(module, show)
	return module, show
end

scenario("section884: hiding a collapsed section hides it", function(sim)
	sim:login({ savedVariables = { ForeverCoreDB = { trackerHost = {} } } })
	sim:advance(3)
	local module, show = section(sim, "Hide884")
	sim:advance(1)
	assert(module:IsShown(), "the section shows its rows")
	sim:click(module.Header.MinimizeButton)
	sim:advance(0.5)
	assert(module:IsCollapsed(), "the header button collapsed it")
	assert(module:IsShown(), "a collapsed section still shows its header")
	-- The player's own way: right-click the collapsed header and pick the entry.
	sim:input(function()
		sim.widgets.dispatch(module.Header, "OnMouseUp", "RightButton")
	end)
	local hide
	for _, row in ipairs(sim.G.ForeverCoreContextMenu.rows) do
		if row:IsShown() and row:GetText() == "Hide this section" then
			hide = row
		end
	end
	sim:click(assert(hide, "the collapsed section's menu offers Hide this section"))
	sim:advance(0.5)
	assert(show.get() == false, "the entry turned the switch off")
	assert(not module:IsShown(), "the switch off hides the collapsed section")
	show.set(true)
	sim:advance(0.5)
	assert(module:IsShown(), "the switch on brings it back, still collapsed")
	sim:expectNoErrors("ForeverCore")
end)
