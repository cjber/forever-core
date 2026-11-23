-- luacheck: read globals scenario
-- #879: a section that lays out no content must not leave its old blocks and lines drawn. A legacy section a consumer
-- built by hand, ordered above the story, empties while the column is pinned left of the game's tracker; its pooled
-- rows used to stay shown at the column's top, painted over the story's own rows and taking the mouse there. Every
-- shown section must report content and keep its rows inside its own laid-out height, and no two sections overlap.
local function questList(G, tracker, height)
	local list = G.CreateFrame("Frame", nil, tracker)
	list.uiOrder, list.leftMargin, list.height = 1, 0, height
	list.SetContainer = function() end
	list.Update = function(module)
		module:SetSize(240, module.height)
		module:Show()
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

-- A section without Blizzard's module template: the host supports a hand-built one, and its own Update draws the rows
-- from its own pool. Emptying it leaves those pooled rows as they were, which is what the host must not show.
local function Legacy(sim, name, order)
	local G = sim.G
	local module = G.CreateFrame("Frame", name, G.UIParent)
	module.uiOrder = order
	module.rows = 3
	module.blocks = {}
	function module:Update()
		self.usedHeight = self.rows * 25
		for index = 1, self.rows do
			local block = self.blocks[index]
			if not block then
				block = G.CreateFrame("Frame", nil, self)
				block:SetSize(200, 20)
				block:SetPoint("TOPLEFT", self, "TOPLEFT", 0, -(index - 1) * 25)
				block.Text = block:CreateFontString(nil, "OVERLAY", "GameFontNormal")
				block.Text:SetPoint("TOPLEFT")
				self.blocks[index] = block
			end
			block.Text:SetText("Stop " .. index .. " of 10: Sentinel Hill")
			block:Show()
		end
		self:SetHeight(math.max(1, self.usedHeight))
	end
	function module:GetContentsHeight()
		return self.usedHeight or 0
	end
	function module.IsTruncated()
		return false
	end
	function module.MarkDirty()
		G.ForeverTrackerCompanion:MarkDirty()
	end
	G.ForeverCore.TrackerHost.Attach(module)
	return module
end

local function Descendants(frame, out)
	out = out or {}
	for _, child in ipairs({ frame:GetChildren() }) do
		out[#out + 1] = child
		Descendants(child, out)
	end
	return out
end

local function Check(modules)
	local problems = {}
	for _, module in ipairs(modules) do
		local used = module.GetContentsHeight and module:GetContentsHeight() or 0
		if module:IsShown() then
			if used <= 0 then
				problems[#problems + 1] = ("a section with no content stays shown: %s"):format(tostring(module))
			end
			-- A section without the scroll wrapper draws its rows straight into the section, so every shown row must
			-- stay inside the height the section laid out for them. A scrollable one clips its overflow.
			if not module.trackerScrollable then
				local top, bottom = module:GetTop(), module:GetBottom()
				for _, frame in ipairs(Descendants(module)) do
					if frame:IsShown() and frame:GetTop() and top and bottom then
						if frame:GetTop() > top + 0.5 or (frame:GetBottom() and frame:GetBottom() < bottom - 0.5) then
							problems[#problems + 1] = ("a row is drawn outside its section's own height: %s in %s"):format(
								tostring(frame),
								tostring(module)
							)
						end
					end
				end
			end
		end
	end
	for index, module in ipairs(modules) do
		for other = index + 1, #modules do
			local each = modules[other]
			if module:IsShown() and each:IsShown() then
				local top, bottom = module:GetTop(), module:GetBottom()
				local otherTop, otherBottom = each:GetTop(), each:GetBottom()
				if top and bottom and otherTop and otherBottom then
					if math.min(top, otherTop) - math.max(bottom, otherBottom) > 0.5 then
						problems[#problems + 1] = ("%s is drawn over %s"):format(tostring(each), tostring(module))
					end
				end
			end
		end
	end
	return problems
end

local function run(sim)
	local G = sim.G
	sim:login({ savedVariables = { ForeverCoreDB = { trackerHost = {} } } })
	sim:advance(3)
	local Section = G.ForeverCore.TrackerSection
	local story = { rows = 4 }
	local top = Section.Create("Stale879Story", {
		LayoutContents = function(module)
			module:SetHeader("Westfall story")
			for index = 1, story.rows do
				local block = module:GetBlock("row" .. index)
				block:SetHeader("Chapter 1 of 6")
				block:AddObjective(1, "0/8 Messenger to Westfall " .. index)
				module:LayoutBlock(block)
			end
		end,
	}, { order = 1 })
	local long = { rows = 6 }
	local bottom = Section.Create("Stale879Long", {
		LayoutContents = function(module)
			module:SetHeader("Long list")
			for index = 1, long.rows do
				local block = module:GetBlock("row" .. index)
				block:SetHeader("Entry " .. index)
				block:AddObjective(1, "0/3 things " .. index)
				module:LayoutBlock(block)
			end
		end,
	}, { order = 2, maxHeight = "remaining" })
	local legacy = Legacy(sim, "Stale879Legacy", 0)
	local modules = { legacy, top, bottom }
	local tracker = sim:openObjectiveTracker()
	tracker.questList = questList(G, tracker, 520)
	tracker:ClearAllPoints()
	-- The game keeps its tracker under the minimap cluster; the column never climbs past that cluster.
	local underMinimap = math.min(-200, G.MinimapCluster:GetBottom() - G.UIParent:GetHeight() - 10)
	tracker:SetPoint("TOPRIGHT", G.UIParent, "TOPRIGHT", -100, underMinimap)
	tracker:SetSize(260, 600)
	G.EditModeManagerFrame:UnregisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
	sim:event("EDIT_MODE_LAYOUTS_UPDATED")
	sim:advance(3)
	local failures = {}
	local function Settle(label)
		sim:advance(0.5)
		for _, p in ipairs(Check(modules)) do
			failures[#failures + 1] = label .. ": " .. p
		end
	end
	Settle("login")
	local column = assert(G.ForeverTrackerCompanion)
	assert(
		column:GetRight() and math.abs(column:GetRight() - tracker:GetLeft()) < 0.01,
		"the tall list leaves no room under it: the column is pinned left of the tracker"
	)
	-- The journey ends and the legacy section has nothing to draw. The host lays the column out again, as a tracker
	-- move or any other relayout does.
	legacy.rows = 0
	legacy:MarkDirty()
	Settle("the legacy section empties")
	sim:event("EDIT_MODE_LAYOUTS_UPDATED")
	Settle("a later relayout")
	-- The column keeps its place, so the failure is the drawn rows, not the layout's placement.
	assert(column:IsShown(), "the column still draws the story")
	sim:expectNoErrors("ForeverCore")
	assert(#failures == 0, "stale section rows stayed drawn:\n" .. table.concat(failures, "\n"))
end

scenario("stale879: a section that lays out no content leaves no rows over the one below it", function(sim)
	run(sim)
end)
