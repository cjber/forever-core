-- luacheck: read globals scenario
-- #827: every section's height is what it last drew. Sections change the way the consumers' do: blocks come and go
-- (a story chapter line, a new step), a row's text is rewritten in place to a longer or shorter one
-- (TrackerSection.UpdateText, a ticking distance), and the header's text changes. After every change settles, each
-- shown section's drawn rows start under its header, never overlap and end at its bottom: no gap, no clipped row.

local function Check(module)
	if not module:IsShown() then
		return
	end
	local rows = {}
	for _, block in pairs(module.usedBlocks or {}) do
		for _, b in pairs(block) do
			if b.used and b:IsShown() then
				if b:GetTop() then
					-- A block ends at its lowest drawn text, which an in-place rewrite can move past the block's frame.
					local header = b.HeaderText
					local bottom = header and header:GetText() and header:GetTop() - header:GetStringHeight()
						or b:GetBottom()
					for _, line in pairs(b.usedLines or {}) do
						local text = line.Text
						if text and text:GetBottom() then
							bottom = math.min(bottom, text:GetTop() - text:GetStringHeight())
						end
					end
					rows[#rows + 1] = { top = b:GetTop(), bottom = bottom, id = tostring(b.id) }
				end
			end
		end
	end
	table.sort(rows, function(a, b)
		return a.top > b.top
	end)
	local problems = {}
	for i = 2, #rows do
		if rows[i].top > rows[i - 1].bottom + 0.5 then
			problems[#problems + 1] = ("block %s overlaps %s by %.1f"):format(
				rows[i].id,
				rows[i - 1].id,
				rows[i].top - rows[i - 1].bottom
			)
		end
	end
	local last = rows[#rows]
	if last and not module.trackerOverflow then
		local bottom = module:GetBottom() + (module.bottomSpacing or 0)
		-- Blizzard's block bottoms sit one unit under the section's bottom spacing.
		bottom = bottom - 1
		if last.bottom < bottom - 0.5 then
			problems[#problems + 1] = ("last row clipped by %.1f"):format(bottom - last.bottom)
		elseif last.bottom > bottom + 0.5 then
			problems[#problems + 1] = ("%.1f units of empty space under the last row"):format(last.bottom - bottom)
		end
	end
	return problems
end

local function run(sim, trackerHost, placeTracker)
	local G = sim.G
	sim:login({ savedVariables = { ForeverCoreDB = { trackerHost = trackerHost } } })
	sim:advance(3)
	local Section = G.ForeverCore.TrackerSection
	local story = { beat = true, step = "Tramping Paws", objectives = 2 }
	local guide = Section.Create("Heights827Guide", {
		LayoutContents = function(module)
			module:SetHeader("Wetlands story")
			if story.beat then
				local beat = module:GetBlock("beat")
				beat:SetHeader("Chapter 3 of 7: " .. story.step)
				if not module:LayoutBlock(beat) then
					return
				end
			end
			local block = module:GetBlock(story.step)
			block:SetHeader("[21] " .. story.step)
			for i = 1, story.objectives do
				block:AddObjective(i, "0/8 Gnoll Paw near the long road to Menethil Harbor " .. i)
			end
			module:LayoutBlock(block)
		end,
	}, { order = -3 })
	local route = { text = "Finding the fastest way...", rows = 1 }
	local journey = Section.Create("Heights827Journey", {
		LayoutContents = function(module)
			module:SetHeader("Journey")
			local block = module:GetBlock("journey")
			block:SetHeader("Journey to The Green Belt")
			for i = 1, route.rows do
				block:AddObjective(i, route.text)
			end
			module:LayoutBlock(block)
		end,
	}, { order = -2 })
	G.ForeverCore.TrackerHost.Attach(guide)
	G.ForeverCore.TrackerHost.Attach(journey)
	sim:advance(3)
	local failures = {}
	local function Settle(label)
		sim:advance(0.1)
		for _, module in ipairs({ guide, journey }) do
			for _, p in ipairs(Check(module) or {}) do
				failures[#failures + 1] = label .. ": " .. p
			end
		end
	end
	if placeTracker then
		-- Edit Mode places the game's tracker after the sections first built, so the pinned column had no width on
		-- screen when they measured their text.
		local tracker = G.ObjectiveTrackerFrame
		tracker:ClearAllPoints()
		tracker:SetPoint("TOPRIGHT", G.UIParent, "TOPRIGHT", -100, -200)
		tracker:SetSize(260, 600)
		-- The sim loads none of the top frames Edit Mode's own handler places, so only the addons hear the event.
		G.EditModeManagerFrame:UnregisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
		sim:event("EDIT_MODE_LAYOUTS_UPDATED")
	end
	Settle("login")
	story.beat, story.step, story.objectives = false, "Daily Delivery", 1
	guide:MarkDirty()
	Settle("step changes, chapter line goes")
	story.beat, story.step, story.objectives = true, "Tramping Paws", 3
	guide:MarkDirty()
	Settle("chapter line returns")
	route.text = "Take the boat from Menethil Harbor to Theramore Isle, then ride south past the Shady Rest Inn"
	Section.UpdateText(journey, { { key = "journey", rows = { { key = 1, text = route.text } } } })
	Settle("row text grows in place")
	route.text = "Finding the fastest way..."
	Section.UpdateText(journey, { { key = "journey", rows = { { key = 1, text = route.text } } } })
	Settle("row text shrinks in place")
	guide:SetHeader("Wetlands story with a much longer title")
	guide:MarkDirty()
	Settle("header text changes")
	sim:expectNoErrors("ForeverCore")
	assert(#failures == 0, "sections drew rows that do not match their height:\n" .. table.concat(failures, "\n"))
end

scenario("heights827: a dragged column's sections match the rows they draw after every refresh path", function(sim)
	run(sim, { attached = false, x = 700, y = -200 })
end)

scenario("heights827: a pinned column's sections match their rows once the game's tracker is placed", function(sim)
	run(sim, {}, true)
end)
