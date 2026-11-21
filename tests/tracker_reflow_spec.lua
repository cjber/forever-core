-- Issue #795: a client event, another frame moving or a section's own change never moves the column, and rebuilds only
-- the section whose data changed. Each section here runs Blizzard's own module mixin, so a rebuild is a real
-- LayoutContents call between BeginLayout and EndLayout.
local harness = dofile("tests/tracker_host_harness.lua")
local probe = harness.new({ deferReady = true })
if not probe.env.ObjectiveTrackerModuleMixin then
	print("tracker_reflow_spec: skipped, TRACKER_UI_ROOT is not set")
	return
end

-- A font string as SetStringText uses it: one line of 12 units whatever the text.
local function FontString()
	local text = { value = "" }
	function text:SetText(value)
		self.value = value
	end
	function text:GetText()
		return self.value
	end
	function text.GetHeight()
		return 12
	end
	text.SetMaxLines, text.SetHeight, text.SetTextColor, text.SetPoint =
		function() end, function() end, function() end, function() end
	return text
end

local t = harness.new({ deferReady = true })
local check = t.check
t.env.OBJECTIVE_TRACKER_COLOR = { Header = { r = 1, g = 1, b = 1 }, Normal = { r = 1, g = 1, b = 1 } }
setfenv(assert(loadfile("UI/TrackerSection.lua")), t.env)("Test", t.ns)
local TrackerSection = t.ns.TrackerSection
t.first.contentHeight, t.second.contentHeight = 0, 0

-- Two capped sections above the long list, which takes the rest of the column and overflows it.
local sections = {}
for order = 3, 5 do
	local m = t.nativeModule(order)
	m.rebuilds, m.blocks, m.title = 0, order == 5 and 30 or 1, "Stop 1"
	if order == 5 then
		m.trackerMaxHeight = "remaining"
	end
	m.LayoutContents = function(self)
		self.rebuilds = self.rebuilds + 1
		for index = 1, self.blocks do
			local block = self:GetBlock("objective" .. index)
			block.HeaderText = block.HeaderText or FontString()
			block.HeaderText:SetText(self.title)
			block.headerHeight = 12
			block.height = 40
			self:LayoutBlock(block)
		end
	end
	sections[#sections + 1] = m
end
local list = sections[3]

-- Where the host sits: its one point and the top right corner that point resolves to.
local function Where()
	local point = t.host.point
	return table.concat({ point[1], tostring(point[2]), point[3], point[4], point[5] }, " "),
		("%s,%s"):format(t.host:GetRight(), t.host:GetTop())
end

-- Runs every queued frame until nothing is pending. Returns the frames that ran and how often the host's position
-- changed from the previous frame.
local function Settle()
	local x, y = Where()
	local frames, moves = 0, 0
	while t.pending() > 0 or t.isSettling() do
		frames = frames + 1
		assert(frames < 20, "the column never settles")
		t.drain()
		t.advanceSettling()
		local nx, ny = Where()
		if nx ~= x or ny ~= y then
			moves = moves + 1
			x, y = nx, ny
		end
	end
	return frames, moves
end

local function Rebuilds()
	local counts = {}
	for index, m in ipairs(sections) do
		counts[index] = m.rebuilds
	end
	return counts
end

-- No section rebuilt and no header replayed its add animation since `before` and `animations`.
local function Untouched(before, animations, label)
	for index, m in ipairs(sections) do
		check(m.rebuilds == before[index], label .. " rebuilds no section")
	end
	check(t.headerAnimations() == animations, label .. " flashes no header")
end

t.ready()
local frames = Settle()
check(frames == 1, "a /reload settles in one frame")
for index, m in ipairs(sections) do
	check(m.rebuilds == 1, "a /reload builds section " .. index .. " once")
end
check(list.trackerOverflow == true, "the long list overflows and scrolls")
local x0, y0 = Where()

-- Zone, quest and taxi events leave the column and its sections alone when tracker geometry stays the same.
local events = {
	"ZONE_CHANGED",
	"ZONE_CHANGED_INDOORS",
	"ZONE_CHANGED_NEW_AREA",
	"QUEST_LOG_UPDATE",
	"QUEST_WATCH_LIST_CHANGED",
	"PLAYER_CONTROL_LOST",
	"PLAYER_CONTROL_GAINED",
}
for _, event in ipairs(events) do
	local before, animations = Rebuilds(), t.headerAnimations()
	t.fire(event)
	local _, moves = Settle()
	check(moves == 0, event .. " moves the column 0 px")
	Untouched(before, animations, event)
end

-- A host pass with nothing dirty, as combat ending runs, resizes viewports and rebuilds nothing.
do
	local before, animations = Rebuilds(), t.headerAnimations()
	t.fire("PLAYER_REGEN_ENABLED")
	local passes, moves = Settle()
	check(passes == 1 and moves == 0, "a clean host pass keeps the column in place")
	Untouched(before, animations, "a clean host pass")
end

-- The right action bars moving or resizing: the host never reads them, so nothing follows. An Edit Mode move of the
-- game's tracker carries the pinned column through the engine's anchor alone: the host sets no point and rebuilds
-- nothing, and the two top corners stay together.
do
	local frame = t.parent
	local function Bar()
		local bar = {}
		for key, value in pairs(frame) do
			bar[key] = value
		end
		bar.point = nil
		return bar
	end
	local before, animations = Rebuilds(), t.headerAnimations()
	for _, name in ipairs({ "MultiBarRight", "MultiBarLeft" }) do
		local moved = Bar()
		moved:SetPoint("TOPRIGHT", t.parent, "TOPRIGHT", -300, -50)
		moved:SetHeight(900)
		moved.left, moved.top = 700, 1000
		t.env[name] = moved
	end
	t.fire("UI_SCALE_CHANGED")
	local _, moves = Settle()
	check(moves == 0, "the action bars moving move the column 0 px")
	Untouched(before, animations, "the action bars moving")
	local point = t.host.point
	t.nativeRect.left, t.nativeRect.top = 600, 700
	check(t.pending() == 0 and t.host.point == point, "a tracker move alone leaves the column still")
	t.fire("EDIT_MODE_LAYOUTS_UPDATED")
	local _, trackerMoves = Settle()
	check(trackerMoves == 1, "the column resamples the tracker once after the Edit Mode event")
	check(t.host:GetRight() == 600 and t.host:GetTop() == 700, "the corners stay together after the move")
	Untouched(before, animations, "an Edit Mode move of the game tracker")
	t.nativeRect.left, t.nativeRect.top = 940, 880
	t.fire("EDIT_MODE_LAYOUTS_UPDATED")
	Settle()
end

-- One section's change rebuilds that section alone, in one frame.
do
	local before = Rebuilds()
	sections[2]:MarkDirty()
	local passes, moves = Settle()
	check(passes == 1 and moves == 0, "one section's change lays out once without moving the column")
	check(sections[2].rebuilds == before[2] + 1, "the changed section rebuilds")
	check(sections[1].rebuilds == before[1] and list.rebuilds == before[3], "the other sections keep their blocks")
end

-- A section above the long list growing, as a journey does when its route arrives, moves the list once and leaves
-- its blocks alone: the list only gets a smaller viewport.
do
	local listTop = list.point[5]
	local before = Rebuilds()
	sections[1].blocks = 3
	sections[1]:MarkDirty()
	local passes, moves = Settle()
	check(passes == 1 and moves == 0, "a section above growing lays the column out once")
	check(list.point[5] < listTop, "the long list moves down under the taller section")
	check(list.rebuilds == before[3] and sections[2].rebuilds == before[2], "the sections below keep their blocks")
	check(list.trackerOverflow == true, "the long list still scrolls in its smaller room")
end

-- Shortest Path's guidance while the player walks: the section rewrites its text through UpdateText on every
-- movement tick, which neither rebuilds a section nor queues a layout.
do
	local before, animations = Rebuilds(), t.headerAnimations()
	for tick = 1, 50 do
		local text = ("Stop 1: %d yd"):format(200 - tick)
		local resized = TrackerSection.UpdateText(sections[1], { { key = "objective1", title = text } })
		check(not resized, "a distance tick keeps the line's height")
		check(sections[1]:GetExistingBlock("objective1").HeaderText:GetText() == text, "the tick shows its text")
		check(t.pending() == 0, "a distance tick queues no layout")
	end
	Untouched(before, animations, "walking with guidance")
	local x, y = Where()
	check(x == x0 and y == y0, "walking with guidance moves the column 0 px")
end

print(("tracker_reflow_spec: %d checks passed"):format(t.checks()))
