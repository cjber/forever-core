-- luacheck: read globals scenario ADDON
scenario("outdated standalone notice", function(sim)
	local G = sim.G
	-- The checkout publishes the legacy facade at file load. Register the newer copy as a packaged
	-- consumer's Begin/End files would, with a chunk that must never run beside that facade.
	assert(sim.loader.load(ADDON))
	sim:runAs(
		"NoticeConsumer",
		[[
		local copy = ForeverCoreLoader.Begin("NoticeConsumer", 1015004)
		copy:Define(function()
			error("the embedded copy must not boot beside the legacy standalone")
		end)
		assert(copy:Seal())
	]]
	)
	assert(G.ForeverCoreLoader.Selected().mode == "legacy", "the standalone is adopted")
	sim:setGamepad(true)
	sim:login()
	sim:advance(0.05)
	sim:gamepadNavigate()

	local warning = G.ForeverCoreLoader.Warning()
	assert(warning and warning:find("is older than the ForeverCore 1.15.4", 1, true), "expected the outdated text")
	local function visibleText(frame)
		if frame:IsVisible() then
			for _, region in ipairs({ frame:GetRegions() }) do
				if region:IsObjectType("FontString") and region:IsVisible() and region:GetText() == warning then
					return true
				end
			end
		end
	end
	local frame = G.EnumerateFrames()
	while frame and not visibleText(frame) do
		frame = G.EnumerateFrames(frame)
	end
	assert(frame, "the outdated notice is visible")

	sim:expectNoGamepadTaint(ADDON)
	for _, action in ipairs(sim.errors) do
		assert(action.event ~= "ADDON_ACTION_BLOCKED", action.message)
	end
	for owner, slots in pairs(sim.taint.slots) do
		if sim.taint.owners[owner] == "blizzard" then
			for field, writer in pairs(slots) do
				assert(
					writer.addon ~= ADDON and writer.addon ~= "NoticeConsumer",
					("Blizzard state written by %s: %s[%s]"):format(
						writer.addon,
						sim.taint.tablePath(owner) or writer.file or "?",
						tostring(field)
					)
				)
			end
		end
	end

	local button, extra = frame:GetChildren()
	assert(button and not extra and button:GetText() == (G.OKAY or "OK"), "the notice has one OK button")
	sim:click(button)
	assert(not frame:IsVisible(), "OK hides the notice")
end)
