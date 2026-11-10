-- ForeverCore's TrackerSection and TrackerLine: the section plumbing every tracker addon shares. The host spec's
-- frame stubs are the client here, so each scenario builds a real host and section over them.
local harness = dofile("tests/tracker_host_harness.lua")

local function LoadSection(t)
	setfenv(assert(loadfile("UI/TrackerSection.lua")), t.env)("Test", t.ns)
	return t.ns.TrackerSection, t.ns.TrackerLine
end

local function RecordErrors(t)
	local errors = {}
	t.ns.SafeCall = function(label, fn, ...)
		local ok, message = pcall(fn, ...)
		if not ok then
			errors[#errors + 1] = { label = label, message = tostring(message) }
		end
		return ok, message
	end
	return errors
end

-- Create attaches once, moves the section's settings through, and clears the old table. The host is ready from its
-- first layout before the section exists, as an addon's section is created after the world has loaded.
do
	local t = harness.new({ deferReady = true })
	local check = t.check
	t.ready()
	t.drain()
	local TrackerSection = LoadSection(t)
	local saved = { trackerHost = { scale = 0.8 } }
	local old = saved.trackerHost
	local show = { get = function() end, set = function() end, where = "Spec settings" }
	local attaches = 0
	local attach = t.ns.TrackerHost.Attach
	t.ns.TrackerHost.Attach = function(module, setting)
		attaches = attaches + 1
		return attach(module, setting)
	end
	local module = TrackerSection.Create("SpecSection", {
		SetHeader = function(self, text)
			self.headerText = text
		end,
	}, {
		order = 7,
		lineTemplate = "SpecLine",
		header = "Spec header",
		show = show,
		legacy = saved,
		legacyKey = "trackerHost",
	})
	check(module ~= nil, "Create returns the section")
	check(module.uiOrder == 7, "Create sets the section's order")
	check(module.lineTemplate == "SpecLine", "Create sets the line template")
	check(module.headerText == "Spec header", "Create sets the header")
	t.ready()
	t.drain()
	t.drain()
	check(attaches == 1, "Create attaches exactly once")
	check(t.ns.TrackerHost.IsAttached(module) == true, "the section is attached")
	check(module.show == show, "the show switch passes straight through")
	check(module.legacySettings == old, "the old tracker table is offered to the host")
	check(saved.trackerHost == nil, "the old tracker key is cleared after the offer")
end

-- No host: the section is refused and the reason is in core's journal.
do
	local t = harness.new({ deferReady = true })
	local check = t.check
	local TrackerSection = LoadSection(t)
	local errors = RecordErrors(t)
	t.ns.TrackerHost = nil
	local module = TrackerSection.Create("NoHostSection", {}, {})
	check(module == nil, "Create returns nil without a host")
	check(#errors == 1, "Create records one reason")
	check(errors[1].message:find("shared tracker host", 1, true) ~= nil, "the reason names the missing host")
end

-- The world loaded but the host refused the section: the addon hears about it a few seconds later.
do
	local t = harness.new({ deferReady = true })
	local check = t.check
	local TrackerSection = LoadSection(t)
	t.ns.TrackerHost.Attach = function() end
	local unattached = 0
	local module = TrackerSection.Create("UnattachedSection", {}, {
		onUnattached = function(section)
			unattached = unattached + 1
			check(section ~= nil, "onUnattached receives the section")
		end,
	})
	t.ready()
	t.drain()
	check(module ~= nil, "Create still returns the section")
	check(unattached == 1, "onUnattached fires once when attaching fails")
end

-- The default CanUpdate holds the layout in combat, and a mixin's own CanUpdate wins.
do
	local t = harness.new({ deferReady = true })
	local check = t.check
	local TrackerSection = LoadSection(t)
	local module = TrackerSection.Create("CombatSection", {}, {})
	local own = TrackerSection.Create("OwnCombatSection", {
		CanUpdate = function()
			return true
		end,
	}, {})
	check(module.CanUpdate() == true, "a fresh section may update out of combat")
	t.setCombat(true)
	check(module.CanUpdate() == false, "the default CanUpdate refuses a layout in combat")
	check(own.CanUpdate() == true, "a mixin's own CanUpdate is kept")
end

-- AddMore draws exactly one line, carrying the count of what did not fit.
do
	local t = harness.new({ deferReady = true })
	local check = t.check
	local TrackerSection = LoadSection(t)
	local lines = {}
	local block = {
		AddObjective = function(_, key, text)
			local line = { key = key, text = text }
			lines[#lines + 1] = line
			return line
		end,
	}
	local line = TrackerSection.AddMore(block, "more", 3)
	check(#lines == 1, "AddMore adds one line")
	check(line == lines[1], "AddMore answers the line it added")
	check(line.key == "more", "the line keeps the caller's key")
	check(line.text:find("3", 1, true) ~= nil and line.text:find("more", 1, true) ~= nil, "the line counts the rest")
end

-- SetInteractive wires the left click and the tooltip, and leaves other buttons alone.
do
	local t = harness.new({ deferReady = true })
	local check = t.check
	local _, TrackerLine = LoadSection(t)
	local line = t.env.CreateFrame("Frame")
	local clicks, tips, hides = 0, 0, 0
	t.env.GameTooltip = {
		Hide = function()
			hides = hides + 1
		end,
	}
	check(line.scripts.OnMouseUp == nil, "the line starts without mouse scripts")
	TrackerLine.SetInteractive(line, {
		onClick = function(clicked, button)
			clicks = clicks + 1
			check(clicked == line and button == "LeftButton", "the click receives the line and the button")
		end,
		tooltip = function(owner)
			tips = tips + 1
			check(owner == line, "the tooltip receives the line")
		end,
	})
	check(line.mouse == true, "the line takes the mouse")
	line.scripts.OnMouseUp(line, "LeftButton")
	line.scripts.OnMouseUp(line, "RightButton")
	check(clicks == 1, "only a left click runs onClick")
	line.scripts.OnEnter(line)
	check(tips == 1, "a hover draws the tooltip")
	line.scripts.OnLeave(line)
	check(hides == 1, "leaving the line hides the tooltip")
end

-- A header click other than the host's right-click menu reaches the section.
do
	local t = harness.new({ deferReady = true })
	local check = t.check
	t.ready()
	t.drain()
	local TrackerSection = LoadSection(t)
	local clicked
	local module = TrackerSection.Create("HeaderSection", {
		SetHeader = function() end,
	}, { header = "Header" })
	module.Header = t.env.CreateFrame("Frame")
	module.OnHeaderClick = function(_, button)
		clicked = button
	end
	t.ready()
	t.drain()
	t.drain()
	module.Header.scripts.OnMouseUp(module.Header, "LeftButton")
	check(clicked == "LeftButton", "the host calls OnHeaderClick for a left click")
	clicked = nil
	module.Header.scripts.OnMouseUp(module.Header, "RightButton")
	check(clicked == nil, "the right click still opens the column's menu instead")
	check(#t.menus > 0, "the right click opened the shared menu")
end

-- One section's layout error is recorded, and the section after it still lays out.
do
	local t = harness.new()
	local check = t.check
	local errors = RecordErrors(t)
	local before = t.second.updates
	t.first.Update = function()
		error("layout exploded")
	end
	t.host:MarkDirty()
	t.drain()
	check(#errors == 1, "the failing section's error is recorded")
	check(errors[1].label == "tracker section update", "the error names the layout it broke")
	check(errors[1].message:find("layout exploded", 1, true) ~= nil, "the recorded message is the section's")
	check(t.second.updates > before, "the next section still lays out")
end

print("tracker_section_spec: checks passed")
