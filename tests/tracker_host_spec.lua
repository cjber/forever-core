-- The host must never enter Blizzard's tracker manager, including through pooled lines, and never touch the native
-- tracker: the harness's ObjectiveTrackerFrame fails any read or write.
local harness = dofile("tests/tracker_host_harness.lua")
local t = harness.new({ deferReady = true })
local check, drain = t.check, t.drain
local host, grip, parent = t.host, t.grip, t.parent
local first, second = t.first, t.second

check(t.pending() == 0, "must not render before player and saved data are ready")
check(
	t.initializationEvents()[1] == "PLAYER_ENTERING_WORLD"
		and t.initializationEvents()[2] == "VARIABLES_LOADED"
		and #t.initializationEvents() == 2,
	"first rendering waits for both native load events"
)
t.ready()
check(t.pending() == 1, "first layout is deferred")
drain()
check(first.point[5] == -24 and second.point[5] == -114, "sections follow uiOrder under the grip")
check(host.width == 260, "the column takes the section template's width")
-- With the minimap hidden the column's default spot is the screen's top right corner.
check(
	host.point[1] == "TOPLEFT" and host.point[2] == parent and host.point[3] == "TOPLEFT",
	"the column is a free frame on UIParent"
)
check(host.point[4] == 1200 - 260 and host.point[5] == 0, "the default spot is the top right of the screen")
check(grip.shown == true, "the grip is always shown")
-- The first section's 80 and the gap under it, then the gap the second section leaves under itself.
check(second.available == 1080 - 24 - 90 - 10, "remaining space runs to the screen's bottom, less each gap")

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
check(first.point[5] == 0 and second.point[5] == 0, "no grip gap is reserved without section content")

-- The column's default spot sits under a shown minimap, in the minimap's own scale.
local under = harness.new({ deferReady = true })
under.minimap.shown, under.minimap.effectiveScale = true, 1.25
under.ready()
under.drain()
under.check(under.host.point[5] == 500 * 1.25 - 1080, "the default spot starts under the minimap")
under.check(under.host.point[4] == 1200 - 260, "the default spot keeps to the right edge")

-- A saved attached or beside placement moves once to the default spot and keeps the player's Lock choice.
local migrated = harness.new({
	deferReady = true,
	hostSettings = { attached = true, locked = true, x = 10, y = -20 },
})
migrated.minimap.shown = true
migrated.ready()
migrated.drain()
local settings = migrated.hostSettings
migrated.check(settings.attached == false, "an attached placement migrates to a free one")
migrated.check(settings.x == 1200 - 260 and settings.y == 500 - 1080, "the old placement gives way to the default spot")
migrated.check(settings.locked == true, "the player's Lock choice survives the migration")
migrated.check(
	migrated.host.point[4] == 1200 - 260 and migrated.host.point[5] == 500 - 1080,
	"a migrated column sits at the default spot"
)
-- A missing attached flag was the old default, so it migrates too.
local unset = harness.new({ hostSettings = { x = 30, y = -40 } })
unset.check(
	unset.hostSettings.attached == false and unset.hostSettings.x == 1200 - 260 and unset.hostSettings.y == 0,
	"an unset flag migrates as attached"
)
-- The move is one-time: a position saved afterwards sticks.
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

-- The default spot is saved once, so the column never follows the minimap, another tracker or the native tracker
-- showing, hiding or moving afterwards (#795).
under.minimap.shown = false
under.host:MarkDirty()
under.drain()
under.check(under.host.point[5] == 500 * 1.25 - 1080, "a minimap hidden later moves nothing")

-- A layout during a drag leaves the column where the drag holds it.
local dragged = harness.new({ hostSettings = { attached = false, x = 100, y = -200 } })
dragged.grip.scripts.OnDragStart(dragged.grip)
dragged.host.point = { "TOPLEFT", dragged.parent, "TOPLEFT", 300, -300 }
dragged.host:MarkDirty()
dragged.drain()
dragged.check(dragged.host.point[4] == 300 and dragged.host.point[5] == -300, "a layout mid-drag moves nothing")

-- A saved free position is kept as it is.
local free = harness.new({ hostSettings = { attached = false, x = 100, y = -200 } })
free.check(free.host.point[4] == 100 and free.host.point[5] == -200, "a saved free position is kept")

-- The column's scale is only the player's own.
local userScaled = harness.new({ hostSettings = { attached = false, scale = 1.5 } })
userScaled.check(math.abs(userScaled.host:GetScale() - 1.5) < 1e-9, "the user's scale sets the column's scale")
userScaled.check(
	math.abs(userScaled.host.point[4] - (1200 / 1.5 - 260)) < 1e-9,
	"a scaled column's default spot keeps its right edge on screen"
)

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
-- The gutter changes the contents width after the first measure, so a second pass settles the text at the new width.
scroll.drain()
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
scroll.check(capped.firstContentsWidth == 250, "the first pass measured in the width set at creation")
scroll.check(capped.updates >= 2, "the gutter's width change asks for another measuring pass")
scroll.check(rest.available > 200 and rest:GetContentsHeight() == 125, "the remaining section takes the room left")
scroll.check(rest.trackerOverflow == false and rest.scrollBar:IsShown() == false, "a short section has no bar")
scroll.check(rest.ContentsFrame:GetWidth() == rest:GetWidth(), "a short section keeps the full block width")

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
scroll.check(capped.scrollFrame:GetVerticalScroll() == capped.scrollOffset, "the scroll child follows the bar")
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
scroll.check(capped.scrollFrame:GetVerticalScroll() == 0, "the scroll child returns to the top")
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
for _, run in ipairs({ t, under, migrated, unset, dragged, free, userScaled, scroll, floors, cramped, paging }) do
	total = total + run.checks()
end
print("tracker_host_spec: " .. total .. " checks passed")
