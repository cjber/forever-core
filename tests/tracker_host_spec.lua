-- The host must never enter Blizzard's tracker manager, including through pooled lines, and never touch the native
-- tracker: the harness's ObjectiveTrackerFrame fails any read or write, so the column may only name it as an anchor.
local harness = dofile("tests/tracker_host_harness.lua")
local t = harness.new({ deferReady = true })
local check, drain = t.check, t.drain
local host = t.host
local first, second = t.first, t.second

check(t.pending() == 0, "must not render before player and saved data are ready")
check(
	t.initializationEvents()[1] == "PLAYER_ENTERING_WORLD"
		and t.initializationEvents()[2] == "VARIABLES_LOADED"
		and #t.initializationEvents() == 2,
	"first rendering waits for both native load events"
)
-- Before its first layout the column already sits at its pin and each section in it, so a reload's first pass moves
-- nothing and a section's first build measures its lines at the width it draws at (#795).
check(
	host.point[1] == "TOPRIGHT" and host.point[2] == t.native and host.point[3] == "TOPLEFT",
	"the column starts pinned"
)
check(first.point[2] == host and second.point[2] == host, "a section is placed in the column when it attaches")
t.ready()
check(t.pending() == 1, "first layout is deferred")
drain()
check(first.point[5] == 0 and second.point[5] == -90, "sections follow uiOrder from the column's top")
check(host.width == 260, "the column takes the section template's width")
-- By default the column's top right corner is pinned to the game tracker's top left corner.
local function Pinned(ctx)
	local point = ctx.host.point
	return point[1] == "TOPRIGHT"
		and point[2] == ctx.native
		and point[3] == "TOPLEFT"
		and point[4] == 0
		and point[5] == 0
end
local function CornersTouch(ctx)
	local right, top = ctx.host:GetRight(), ctx.host:GetTop()
	return right == ctx.nativeRect.left and top == ctx.nativeRect.top
end
check(Pinned(t), "the column pins its top right corner to the game tracker's top left corner")
check(CornersTouch(t), "the two top corners touch")
-- The first section's 80 and the gap under it, then the gap the second section leaves under itself.
check(second.available == 880 - 90 - 10, "remaining space runs from the pin to the screen's bottom, less each gap")

-- A section created just before combat may reach Attach from its deferred timer after combat starts. SetParent is
-- protected for the quest descendants, so the host keeps the request and applies it on the first safe event.
local combatLate = t.env.CreateFrame("Frame")
t.setCombat(true)
t.ns.TrackerHost.Attach(combatLate)
check(combatLate.parent == nil, "combat defers a late section attachment")
t.setCombat(false)
t.fire("PLAYER_REGEN_ENABLED")
check(combatLate.parent == host, "combat release applies the deferred attachment")
for _, event in ipairs({ "QUEST_LOG_UPDATE", "QUEST_WATCH_UPDATE", "ZONE_CHANGED_NEW_AREA" }) do
	check(not host.events[event], "the column watches no quest events: " .. event)
end
check(t.ns.TrackerHost.IsAttached(first) and not t.ns.TrackerHost.IsAttached(nil), "ownership lookup")
local updatesBeforeDuplicateAttach = first.updates
t.ns.TrackerHost.Attach(first)
host:MarkDirty()
host:MarkDirty()
check(t.pending() == 1, "dirty updates coalesce")
drain()
check(first.updates == updatesBeforeDuplicateAttach + 1, "duplicate attach must not duplicate sections")
check(first:GetContextMenuParent() == host, "menus use private container")
first.contentHeight, second.contentHeight = 0, 0
host:MarkDirty()
drain()
check(host.shown == false, "host hides when no section draws")
check(first.point[5] == 0 and second.point[5] == 0, "an empty column keeps its sections at its top")

-- An Edit Mode move of the game tracker carries the column with it: the engine keeps the anchor, so the host runs no
-- layout and sets no point of its own.
local pinned = harness.new()
local pinPoint = pinned.host.point
local nativeRect = pinned.nativeRect
nativeRect.left, nativeRect.top = 400, 700
pinned.check(pinned.pending() == 0, "a move of the game tracker queues no layout")
pinned.check(pinned.host.point == pinPoint, "and sets no point")
pinned.check(CornersTouch(pinned), "the corners stay together after an Edit Mode move")
-- The pin holds whether the game tracker is shown or hidden: the host never asks which, and the harness's tracker
-- would fail the spec if it did. A layout after the tracker hides keeps the same anchor.
pinned.host:MarkDirty()
pinned.drain()
pinned.check(Pinned(pinned) and CornersTouch(pinned), "a later layout keeps the pin")

-- A drag on a section header gives the column a free position and releases the pin. Letting go is not a click.
local settings = pinned.hostSettings
local headerClicks = 0
pinned.first.OnHeaderClick = function()
	headerClicks = headerClicks + 1
end
pinned.drag(pinned.first.Header, function()
	pinned.host.left, pinned.host.top = 100, 1080 - 200
end)
pinned.host.left, pinned.host.top = nil, nil
pinned.check(headerClicks == 0, "letting go of a header drag runs no header click")
pinned.first.Header.scripts.OnMouseDown(pinned.first.Header, "LeftButton")
pinned.first.Header.scripts.OnMouseUp(pinned.first.Header, "LeftButton")
pinned.check(headerClicks == 1, "a plain header click still runs")
pinned.drain()
pinned.check(settings.x == 100 and settings.y == -200, "a drag saves a free position")
local point = pinned.host.point
pinned.check(
	point[1] == "TOPLEFT" and point[2] == pinned.parent and point[4] == 100 and point[5] == -200,
	"a dragged column sits where it was dropped, on UIParent"
)
nativeRect.left = 300
pinned.host:MarkDirty()
pinned.drain()
pinned.check(pinned.host.point[2] == pinned.parent, "a dragged column no longer follows the game tracker")
local function Entry(entries, text)
	for _, entry in ipairs(entries) do
		if entry.text == text then
			return entry
		end
	end
end
pinned.host.shown = true
pinned.first.Header.scripts.OnMouseUp(pinned.first.Header, "RightButton")
-- Moving is the header drag and the Lock switch in this menu, nothing else.
local entries = pinned.menus[#pinned.menus].entries
pinned.check(Entry(entries, "Lock the tracker") ~= nil, "the section menu offers Lock")
pinned.check(Entry(entries, "Reset position") == nil, "and no Reset entry")

-- Old placements migrate once to the pin and keep the player's Lock choice: an attached one drops its saved spot, and
-- a beside one never had one.
local migrated = harness.new({ hostSettings = { attached = true, locked = true, x = 10, y = -20 } })
settings = migrated.hostSettings
migrated.check(settings.attached == false, "an attached placement is marked migrated")
migrated.check(settings.x == nil and settings.y == nil, "the attached placement's old spot is dropped")
migrated.check(settings.locked == true, "the player's Lock choice survives the migration")
migrated.check(Pinned(migrated), "a migrated attached column is pinned")
local unset = harness.new({ hostSettings = { x = 30, y = -40 } })
unset.check(unset.hostSettings.x == nil and Pinned(unset), "a missing attached flag was the old default and migrates")
local beside = harness.new({ hostSettings = { attached = false, locked = true } })
beside.check(Pinned(beside) and beside.hostSettings.locked == true, "a beside placement migrates to the pin")
-- Once the store exists, a dragged column goes straight to its saved spot, before any layout pass could move it.
local early = harness.new({ deferReady = true, hostSettings = { attached = false, x = 50, y = -60 } })
early.ns.MigrateTrackerSettings()
early.check(early.pending() == 0, "placing from the store queues no layout before ready")
early.check(
	early.host.point[1] == "TOPLEFT" and early.host.point[4] == 50 and early.host.point[5] == -60,
	"the store's dragged spot is the column's place before its first layout"
)
-- The migration is one-time: a position saved afterwards sticks.
migrated.ns.TrackerHost.SavePosition(50, -60)
migrated.drain()
migrated.check(settings.x == 50 and settings.y == -60, "a position saved after the migration is kept")
migrated.check(migrated.host.point[4] == 50 and migrated.host.point[5] == -60, "the column moves to the saved spot")
-- The retired attach switch answers false and changes nothing.
migrated.ns.TrackerHost.SetAttached(true)
migrated.drain()
migrated.check(migrated.ns.TrackerHost.IsAttachedToQuestTracker() == false, "the column never reports attached")
migrated.check(settings.attached == false and settings.x == 50, "SetAttached changes no saved setting")
migrated.check(migrated.host.point[4] == 50 and migrated.host.point[5] == -60, "SetAttached moves nothing")
local notified = false
migrated.ns.TrackerHost.OnAttachmentChanged(function()
	notified = true
end)
migrated.ns.TrackerHost.SetAttached(false)
migrated.check(not notified, "an attachment callback is never called")

-- A layout during a drag leaves the column where the drag holds it.
local dragged = harness.new({ hostSettings = { attached = false, x = 100, y = -200 } })
dragged.drag(dragged.first.Header)
dragged.host.point = { "TOPLEFT", dragged.parent, "TOPLEFT", 300, -300 }
dragged.host:MarkDirty()
dragged.drain()
dragged.check(dragged.host.point[4] == 300 and dragged.host.point[5] == -300, "a layout mid-drag moves nothing")

-- An explicit free position the player dragged is kept as it is.
local free = harness.new({ hostSettings = { attached = false, x = 100, y = -200 } })
free.check(free.host.point[4] == 100 and free.host.point[5] == -200, "a saved free position is kept")

-- The column's scale is only the player's own, and the pin keeps its corner whatever the scale.
local userScaled = harness.new({ hostSettings = { attached = false, scale = 1.5 } })
userScaled.check(math.abs(userScaled.host:GetScale() - 1.5) < 1e-9, "the user's scale sets the column's scale")
userScaled.check(Pinned(userScaled), "a scaled column stays pinned")

-- No runtime file writes to the game's quest tracker: every mention of ObjectiveTrackerFrame in a file the TOC loads is
-- a presence check or an anchor argument, never a field, a method call or an assignment.
local writes = {}
for line in io.lines("ForeverCore.toc") do
	local path = line:match("^([%w_\\/]+%.lua)%s*$")
	if path then
		path = path:gsub("\\", "/")
		local number = 0
		for source in io.lines(path) do
			number = number + 1
			local code = source:gsub("%-%-.*$", "")
			local init = 1
			while true do
				local _, finish = code:find("ObjectiveTrackerFrame", init, true)
				if not finish then
					break
				end
				local after = code:sub(finish + 1)
				if after:match("^%s*[%.:%[]") or (after:match("^%s*=") and not after:match("^%s*==")) then
					writes[#writes + 1] = path .. ":" .. number
				end
				init = finish + 1
			end
		end
	end
end
check(#writes == 0, "nothing in core touches ObjectiveTrackerFrame: " .. table.concat(writes, ", "))

-- A repeated layout must not be a probe: Blizzard's EndLayout hides a section that fits nothing and FreeUnusedBlocks
-- releases every block, so a second layout would replay each header's add animation and rebuild every block. Issue
-- #438. The section uses Blizzard's own module mixin, which the native tracker source supplies.
local stackedChecks = 0
if t.env.ObjectiveTrackerModuleMixin then
	local stacked = harness.new({ deferReady = true })
	stacked.first.contentHeight, stacked.second.contentHeight = 0, 0
	stacked.nativeModule(3)
	stacked.ready()
	stacked.drain()
	local animations, releases = stacked.headerAnimations(), stacked.blocksReleased()
	stacked.host:MarkDirty()
	stacked.drain()
	stacked.check(stacked.headerAnimations() == animations, "a repeated layout replays no header animation")
	stacked.check(stacked.blocksReleased() == releases, "a repeated layout releases no block")
	stackedChecks = stacked.checks()
end

-- The shared scroll wrapper: every section but the one that asks for the rest caps at 200 units, the remaining one
-- gets what the others leave, and only an overflowing section shows the minimal bar.
local scroll = harness.new()
local capped = scroll.scrollModule(3, 10, 40)
local rest = scroll.scrollModule(4, 2, 40, "remaining")
scroll.first.contentHeight, scroll.second.contentHeight = 0, 0
scroll.host:MarkDirty()
scroll.drain()
scroll.check(scroll.pending() == 0, "the first layout settles in one frame")
scroll.check(capped.available == 200, "a section other than Quests caps at 200 units")
scroll.check(capped.trackerOverflow == true and capped.scrollRange == 325, "the capped section scrolls its overflow")
scroll.check(capped:GetContentsHeight() == 200, "the capped section reports its visible height")
scroll.check(capped:GetMinimumHeight() == 75, "the minimum height uses the measured header, offset and first block")
scroll.check(capped.scrollBar:IsShown(), "an overflowing section shows the minimal scrollbar")
scroll.check(
	capped.scrollBar.kind == "EventFrame" and capped.scrollBar.template == "MinimalScrollBar",
	"the bar is the client's EventFrame template, not a Slider"
)
scroll.check(capped.scrollBar:GetVisibleExtentPercentage() == 175 / 500, "the bar shows the viewport's fraction")
scroll.check(capped.ContentsFrame:GetWidth() == capped:GetWidth() - 18, "the bar takes its 18-unit gutter")
scroll.check(
	capped.firstContentsWidth == capped:GetWidth() - 18,
	"the first build measures its text in the column's width less the gutter"
)
-- A section's first build must have placed contents, or Blizzard measures every wrapped line as one row and the next
-- line draws over it (#795). A ScrollFrame places its child only when it next draws, and a frame of height 0 has no
-- rect, so the viewport is a clipping frame and the contents hang from the header with the cap as their height.
scroll.check(capped.firstContentsLeft ~= false, "the first build has placed contents to wrap its lines in")
scroll.check(capped.scrollFrame.clipsChildren == true, "the viewport clips the contents")
scroll.check(select(2, capped.ContentsFrame:GetPoint()) == capped.Header, "the contents hang from the header")
scroll.check(rest.available > 200 and rest:GetContentsHeight() == 125, "the remaining section takes the room left")
scroll.check(rest.trackerOverflow == false and rest.scrollBar:IsShown() == false, "a short section has no bar")
scroll.check(
	rest.ContentsFrame:GetWidth() == rest:GetWidth() - 18,
	"a short section keeps the gutter, so its text wraps the same if it starts to scroll"
)

local scrollFrame = capped.scrollFrame
local sectionWidth = capped:GetWidth()
scroll.check(scroll.ns.TrackerHost.SetSectionMaxHeight(capped, 280), "an attached section accepts a height cap")
scroll.drain()
scroll.check(capped.available == 280, "the setter changes the normal layout cap")
scroll.check(
	capped.scrollFrame == scrollFrame and capped:GetWidth() == sectionWidth,
	"the cap reuses scrolling and shared width"
)
scroll.check(scroll.ns.TrackerHost.SetSectionMaxHeight(capped, 1), "a small cap is accepted")
scroll.drain()
scroll.check(capped.available >= capped:GetMinimumHeight(), "a requested cap preserves the measured first block")
scroll.check(not scroll.ns.TrackerHost.SetSectionMaxHeight({}, 280), "an unregistered section is rejected")
for _, invalid in ipairs({ -1, math.huge, 0 / 0, "280" }) do
	scroll.check(not scroll.ns.TrackerHost.SetSectionMaxHeight(capped, invalid), "an invalid cap is rejected")
end
scroll.setCombat(true)
local heldHeight = capped:GetHeight()
scroll.check(scroll.ns.TrackerHost.SetSectionMaxHeight(capped, 300), "combat accepts a pending cap")
scroll.drain()
scroll.check(capped:GetHeight() == heldHeight, "combat holds section geometry")
scroll.setCombat(false)
scroll.fire("PLAYER_REGEN_ENABLED")
scroll.drain()
scroll.check(capped.available == 300, "combat ending applies the pending cap")
scroll.check(scroll.ns.TrackerHost.SetSectionMaxHeight(capped, nil), "nil restores the default")
scroll.drain()
scroll.check(capped.available == 200, "the default cap is restored")

capped:OnTrackerWheel(-1)
scroll.check(capped.scrollOffset == 60, "the wheel moves one block, not a fixed step")
scroll.check(math.abs(capped.scrollBar:GetScrollPercentage() - 60 / 325) < 1e-9, "the bar follows the view")
capped.scrollBar:SetScrollPercentage(0.5)
scroll.check(math.abs(capped.scrollOffset - 162.5) < 1e-9, "dragging the bar moves the view")
scroll.check(select(5, capped.ContentsFrame:GetPoint()) == capped.scrollOffset, "the contents follow the bar")
scroll.host:MarkDirty()
scroll.drain()
scroll.check(capped.scrollOffset == 160, "a layout keeps the same block at the top of the view")

scroll.setCombat(true)
scroll.fire("PLAYER_REGEN_DISABLED")
scroll.check(capped.scrollBar:GetAlpha() == 0.5, "a frozen bar shows at half alpha")
scroll.check(capped.scrollBar:IsScrollAllowed() == false, "a frozen bar refuses scrolling")
local frozenOffset, frozenHeight, frozenWidth = capped.scrollOffset, capped:GetHeight(), capped.ContentsFrame:GetWidth()
local frozenUpdates = capped.updates
scroll.host:MarkDirty()
scroll.drain()
scroll.check(capped.updates == frozenUpdates, "combat defers the whole layout pass")
scroll.check(
	capped.scrollOffset == frozenOffset
		and capped:GetHeight() == frozenHeight
		and capped.ContentsFrame:GetWidth() == frozenWidth,
	"combat leaves every protected ancestor exactly where it was"
)
capped:OnTrackerWheel(-1)
scroll.check(capped.scrollOffset == frozenOffset, "the wheel does nothing in combat")
scroll.check(capped.scrollBar:GetAlpha() == 0.5, "a frozen bar keeps its alpha through the queue")
scroll.setCombat(false)
scroll.fire("PLAYER_REGEN_ENABLED")
scroll.drain()
scroll.check(capped.scrollBar:GetAlpha() == 1, "the bar returns to full alpha after combat")
scroll.check(capped.updates == frozenUpdates + 1, "combat ending runs the deferred layout")
capped:OnTrackerWheel(-1)
scroll.check(capped.scrollOffset == 210, "the wheel moves again after combat")

-- Content frames receive wheel input directly, so the host hooks them without replacing their own handlers.
local wheelChild = scroll.env.CreateFrame("Button")
local childWheelCalls = 0
wheelChild:SetScript("OnMouseWheel", function()
	childWheelCalls = childWheelCalls + 1
end)
capped.ContentsFrame.GetChildren = function()
	return wheelChild
end
capped.count = 10
capped.scrollOffset = 0
scroll.host:MarkDirty()
scroll.drain()
wheelChild.scripts.OnMouseWheel(wheelChild, -1)
scroll.check(wheelChild.trackerWheelModule == nil, "wheel routing adds no ownership field to descendant frames")
scroll.check(childWheelCalls == 1, "content wheel handlers remain installed")
scroll.check(capped.scrollOffset == 60, "wheel input over content scrolls the owning section")
rest.ContentsFrame.GetChildren = function()
	return wheelChild
end
-- Thirty 40 unit blocks overflow the room the free column has from the screen's top.
rest.count = 30
capped.scrollOffset, rest.scrollOffset = 0, 0
scroll.host:MarkDirty()
scroll.drain()
wheelChild.scripts.OnMouseWheel(wheelChild, -1)
scroll.check(capped.scrollOffset == 0 and rest.scrollOffset == 60, "reused content wheels only its current section")

-- A list that shrinks below its cap goes back to the top through the one setter, so the scroll child and the item
-- buttons see the new view instead of keeping the old one.
local scrollChanges = capped.scrollChanges
capped.count = 2
scroll.host:MarkDirty()
scroll.drain()
scroll.check(capped.trackerOverflow == false and capped.scrollRange == 0, "a shrunken list no longer overflows")
scroll.check(capped.scrollOffset == 0, "a shrunken list returns to the top")
scroll.check(select(5, capped.ContentsFrame:GetPoint()) == 0, "the contents return to the top")
scroll.check(capped.scrollBar:IsShown() == false, "the shrunken list hides the bar")
scroll.check(capped.scrollChanges > scrollChanges, "the shrunken list redraws its item buttons")

-- Two visible sections with little room reserve their measured floors without allowing the column to overrun it.
scroll.room(100)
scroll.drain()
scroll.check(
	capped.available > 0 and rest.trackerViewport == 0,
	"constrained layout gives the remaining section no sliver"
)
scroll.check(capped:GetHeight() + rest:GetHeight() <= 100, "constrained layout keeps section geometry within the room")

-- Two overflowing sections must reserve the later section's measured first block before spending the remaining room.
-- The first pass records the native metrics; the constrained pass then has 200 units, enough for two 75-unit floors
-- and the inter-section gap. The old allocator spent the whole cap on the first section and left the second below its
-- usable floor.
local floors = harness.new()
floors.first.contentHeight, floors.second.contentHeight = 0, 0
local tall = floors.scrollModule(3, 10, 40)
local later = floors.scrollModule(4, 2, 40)
floors.host:MarkDirty()
floors.drain()
floors.drain()
floors.room(220)
floors.drain()
floors.check(tall.available >= 75 and later.available >= 75, "measured floors fit across multiple sections")
floors.check(tall:GetHeight() + later:GetHeight() + 10 <= 220, "floor allocation keeps the constrained column bounded")

-- Three sections cannot all keep their first block in 166 units. Keep complete viewports or headers.
local cramped = harness.new()
cramped.first.contentHeight, cramped.second.contentHeight = 0, 0
local sections = {
	cramped.scrollModule(3, 10, 40),
	cramped.scrollModule(4, 1, 20),
	cramped.scrollModule(5, 1, 90),
}
cramped.host:MarkDirty()
cramped.drain()
cramped.drain()
for _, room in ipairs({ 166, 120, 105, 220 }) do
	cramped.room(room)
	cramped.drain()
	local used = 0
	for _, section in ipairs(sections) do
		local viewport = section.trackerViewport
		cramped.check(viewport == 0 or viewport >= section:GetMinimumHeight() - 25, "no unusable section sliver")
		cramped.check(section:GetContentsHeight() >= 25, "each section retains its header")
		if viewport == 0 then
			cramped.check(not section.scrollFrame:IsShown(), "header-only section hides its content")
			cramped.check(not section.scrollBar:IsShown(), "header-only section hides its arrows")
		end
		used = used + section:GetContentsHeight() + 10
	end
	cramped.check(used <= room, "three-section column stays within available room")
end

-- Real blocks can contain many objective rows. Their first row, rather than the whole block, is the fallback floor.
for _, section in ipairs(sections) do
	local baseHeight = section.baseUpdateHeight
	section.baseUpdateHeight = function(self)
		local line = cramped.env.CreateFrame("Frame")
		line:SetHeight(10)
		line:SetPoint("TOPLEFT", self.firstBlock, "TOPLEFT", 0, 0)
		self.firstBlock.usedLines = { line }
		baseHeight(self)
	end
end
cramped.room(166)
cramped.drain()
cramped.host:MarkDirty()
cramped.drain()
local rowTotal = 0
for _, section in ipairs(sections) do
	cramped.check(section.trackerViewport >= 20, "every section gets its first row when row floors fit")
	cramped.check(section.scrollFrame:IsShown(), "header-only content returns when a readable row fits")
	rowTotal = rowTotal + section:GetContentsHeight() + 10
end
cramped.check(rowTotal <= 166, "row floors keep the column bounded")

-- A constrained column can clip even its first block: content wheels must traverse that block in both directions.
local paging = harness.new()
paging.first.contentHeight, paging.second.contentHeight = 0, 0
local oversized = paging.scrollModule(3, 1, 500)
-- Model the real block's first objective independently of its many later rows.
local baseHeight = oversized.baseUpdateHeight
oversized.baseUpdateHeight = function(self)
	local line = paging.env.CreateFrame("Frame")
	line:SetHeight(20)
	line:SetPoint("TOPLEFT", self.firstBlock, "TOPLEFT", 0, 0)
	self.firstBlock.usedLines = { line }
	baseHeight(self)
end
local objective = paging.env.CreateFrame("Button")
local clicks = 0
objective:SetScript("OnClick", function()
	clicks = clicks + 1
end)
oversized.ContentsFrame.GetChildren = function()
	return objective
end
paging.room(200 - 24 / 1.25)
paging.drain()
paging.drain()
paging.check(oversized.trackerOverflow and oversized.trackerViewport < 500, "one tall block overflows its viewport")
local function ContentWheel(delta)
	objective.scripts.OnMouseWheel(objective, delta)
end
ContentWheel(-1)
paging.check(oversized.scrollOffset > 0, "content wheel moves within a single overflowing block")
paging.check(oversized.scrollOffset < oversized.trackerViewport, "a tall block scrolls with visible overlap")
for _ = 1, 20 do
	local before = oversized.scrollOffset
	ContentWheel(-1)
	paging.check(
		oversized.scrollOffset >= before and oversized.scrollOffset - before < oversized.trackerViewport,
		"downward ticks preserve overlap through a tall block and at its end"
	)
end
paging.check(oversized.scrollOffset == oversized.scrollRange, "repeated wheels reach the end of one tall block")
for _ = 1, 20 do
	local before = oversized.scrollOffset
	ContentWheel(1)
	paging.check(
		oversized.scrollOffset <= before and before - oversized.scrollOffset < oversized.trackerViewport,
		"upward ticks preserve overlap through a tall block and at its start"
	)
end
paging.check(oversized.scrollOffset == 0, "repeated upward wheels return through the tall block to the top")
objective.scripts.OnClick(objective)
paging.check(clicks == 1, "content wheel binding preserves child click actions")

-- Keep the first block tall and append a short block without asking layout to rebuild the fixture.
local short = paging.env.CreateFrame("Frame")
short.id, short.height = 2, 40
oversized.firstBlock.nextBlock = short
oversized.scrollRange = oversized.scrollRange + 50
ContentWheel(-1)
paging.check(oversized.scrollOffset < oversized.trackerViewport, "a next block does not skip unseen tall-block rows")
local previous = oversized.scrollOffset
ContentWheel(-1)
paging.check(oversized.scrollOffset > previous, "successive ticks continue through the tall first block")
ContentWheel(1)
paging.check(
	oversized.scrollOffset < previous + oversized.trackerViewport and oversized.scrollOffset > 0,
	"upward paging within a tall block preserves overlap instead of jumping to its top"
)
oversized:SetScrollOffset(oversized:BlockStarts()[2].start)
ContentWheel(1)
paging.check(oversized.scrollOffset > 0, "upward wheel from the next block pages through the tall first block")
paging.setCombat(true)
local heldOffset = oversized.scrollOffset
ContentWheel(-1)
ContentWheel(1)
paging.check(oversized.scrollOffset == heldOffset, "combat freezes tall-block content wheels in both directions")
paging.setCombat(false)
oversized.trackerOverflow = false
ContentWheel(-1)
paging.check(oversized.scrollOffset == heldOffset, "a section without overflow ignores content wheels")

local total = stackedChecks
local runs = { t, pinned, migrated, unset, beside, dragged, free, userScaled, scroll, floors, cramped, paging }
for _, run in ipairs(runs) do
	total = total + run.checks()
end
print("tracker_host_spec: " .. total .. " checks passed")
