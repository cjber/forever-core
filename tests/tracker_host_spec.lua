-- The host must never enter Blizzard's tracker manager, including through pooled lines.
local harness = dofile("tests/tracker_host_harness.lua")
local t = harness.new({ deferReady = true, headerShown = true })
local check, drain = t.check, t.drain
local host, grip, native, parent = t.host, t.grip, t.native, t.parent
local first, second = t.first, t.second
-- The native tracker is protected: the host reads it and never writes it. Blizzard's own moves set `point` directly.
for _, method in ipairs({ "SetPoint", "ClearAllPoints", "SetClampedToScreen" }) do
	native[method] = function()
		error("the host wrote the protected native tracker: " .. method)
	end
end
local function MoveNative(...)
	native.point = { ... }
end

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
check(first.point[5] == 0 and second.point[5] == -90, "sections follow uiOrder")
check(t.nativeHeader.point[2] == native, "native header stays anchored to its native parent")
check(first.point[5] == 0, "visible native header reserves no top gap")
check(native.point[1] == "TOPRIGHT" and native.point[5] == -100, "the native tracker keeps its own slot")
check(
	host.point[1] == "TOP" and host.point[2] == native.NineSlice and host.point[3] == "BOTTOM" and host.point[5] == 0,
	"the column hangs from the bottom of the native quests"
)
t.native.headerWanted = false
t.updateOrder()
check(not t.headerShown(), "client update hides the native header")
check(t.nativeHeader.point[2] == native, "hidden header remains anchored to native parent")
t.native.headerWanted = true
t.updateOrder()
check(t.headerShown(), "client update shows the native header")
check(t.nativeHeader.point[2] == native, "client update re-anchors header to native parent")
host:MarkDirty()
drain()
check(t.nativeHeader.point[2] == native, "layouts leave header anchored to native parent")
-- The first section's 80 and the gap under it, then the gap the second section leaves under itself.
check(
	math.abs(second.available - (540 - 24 / 1.25 - 90 - 10)) < 1e-9,
	"remaining space runs from the quests to the screen, less each section's gap"
)
check(native:GetHeight() == 300, "native viewport preserves an externally sized height before clamping")
native:SetHeight(420)
native.scripts.OnSizeChanged(native)
drain()
check(native:GetHeight() == 420, "native viewport adopts an external resize before clamping")
native:SetHeight(700)
native.scripts.OnSizeChanged(native)
drain()
check(native:GetHeight() == 700, "native container keeps its externally sized height")
MoveNative("TOPRIGHT", parent, "TOPRIGHT", 0, 0)
t.eventRegistry:TriggerEvent("EditMode.SavedLayouts")
drain()
check(
	native.point[5] == 0 and host.point[2] == native.NineSlice,
	"a saved layout moves the tracker and the column follows it"
)
-- The managed frame layout or a UI addon can put the native frame back in its saved slot with no event at all.
local probe = t.probe()
check(probe ~= nil and probe ~= host, "an addon-owned probe follows the native frame's top left corner")
MoveNative("TOPRIGHT", parent, "TOPRIGHT", 0, -100)
probe.scripts.OnSizeChanged(probe)
check(t.pending() == 1, "a silent native reanchor reflows the column")
drain()
check(
	native.point[5] == -100 and host.point[2] == native.NineSlice,
	"the silent reanchor leaves the tracker where it was put"
)
t.editMode.active, t.editMode.shown = true, true
t.eventRegistry:TriggerEvent("EditMode.Enter")
check(host.shown == false, "private tracker hides while Edit Mode owns native slot")
check(native.clamped == true, "the native frame keeps its screen clamp")
check(probe.point == nil, "Edit Mode disconnects the native geometry probe")
check(host.point[2] == parent, "hidden companion no longer depends on the native tracker's anchors")
drain()
check(native.point[1] == "TOPRIGHT", "queued layouts leave the native slot to Edit Mode")
probe.scripts.OnSizeChanged(probe)
check(t.pending() == 0, "a disconnected probe cannot queue a layout")
-- CheckHideAndLockEditMode hides the manager without exiting it: active stays true and no EditMode.Exit runs.
check(t.editMode.scripts.OnHide ~= nil, "private tracker follows the Edit Mode manager's own hide")
t.editMode.shown = false
t.editMode.scripts.OnHide(t.editMode)
drain()
check(host.shown == true, "private tracker returns when a locked Edit Mode hides its manager")
t.editMode.active, t.editMode.shown = false, false
t.eventRegistry:TriggerEvent("EditMode.Exit")
drain()
check(host.shown == true, "private tracker returns after Edit Mode")
check(probe.point[2] == native, "leaving Edit Mode reconnects the native geometry probe")
check(native.clamped == true and native.point[1] == "TOPRIGHT", "leaving Edit Mode leaves the native tracker alone")
check(t.ns.TrackerHost.IsAttached(first) and not t.ns.TrackerHost.IsAttached(nil), "ownership lookup")
local attachmentChanges = 0
t.ns.TrackerHost.OnAttachmentChanged(function(value)
	attachmentChanges = attachmentChanges + 1
	check(value == false or value == true, "attachment callback receives desired state")
end)
local updatesBeforeDuplicateAttach = first.updates
t.ns.TrackerHost.Attach(first)
host:MarkDirty()
host:MarkDirty()
check(t.pending() == 1, "dirty updates coalesce")
drain()
check(first.updates == updatesBeforeDuplicateAttach + 1, "duplicate attach must not duplicate sections")
check(first:GetContextMenuParent() == host, "menus use private container")
check(grip ~= nil, "the grip is shown by the detached layout")
first.contentHeight, second.contentHeight = 0, 0
host:MarkDirty()
drain()
check(host.shown == false, "host hides when no section draws")
check(first.point[5] == 0 and second.point[5] == 0, "no header gap is reserved without section content")
check(t.nativeHeader.point[2] == native, "empty layout leaves native header in its parent")
local empty = harness.new({ headerShown = true })
empty.first.contentHeight, empty.second.contentHeight = 0, 0
empty.host:MarkDirty()
empty.drain()
empty.check(empty.host.shown == false, "host hides when visible header has no section content")
empty.check(empty.first.point[5] == 0, "visible header reserves no gap without drawn content")
empty.check(empty.nativeHeader.point[2] == empty.native, "visible header remains in native parent")

-- #383: a replacement UI may hide or shrink Blizzard's tracker, so the column follows only a frame it can see.
local hidden = harness.new({ hostSettings = { attached = false } })
hidden.native.effectiveScale, hidden.native.shown = 0.01, false
hidden.ready()
hidden.drain()
hidden.check(math.abs(hidden.host:GetScale() - 1) < 1e-9, "a detached column ignores the hidden native tracker's scale")
-- IsShown is true for a frame under a hidden parent; only effective visibility says the tracker is really gone.
local hiddenParent = harness.new({ hostSettings = { attached = true } })
hiddenParent.native.effectiveScale, hiddenParent.native.shown, hiddenParent.parent.shown = 0.01, true, false
hiddenParent.ready()
hiddenParent.drain()
hiddenParent.check(
	math.abs(hiddenParent.host:GetScale() - 1) < 1e-9,
	"a shown native tracker under a hidden parent is not the source"
)
local transparent = harness.new({ hostSettings = { attached = true } })
transparent.native.effectiveScale, transparent.native.alpha = 0.01, 0
transparent.ready()
transparent.drain()
transparent.check(math.abs(transparent.host:GetScale() - 1) < 1e-9, "a transparent native tracker is not the source")
local visible = harness.new({ hostSettings = { attached = true } })
visible.native.effectiveScale = 0.8
visible.ready()
visible.drain()
visible.check(math.abs(visible.host:GetScale() - 0.8) < 1e-9, "a visible native tracker still sets the column's scale")
local userScaled = harness.new({ hostSettings = { attached = true, scale = 1.5 } })
userScaled.native.effectiveScale = 0.8
userScaled.ready()
userScaled.drain()
userScaled.check(math.abs(userScaled.host:GetScale() - 1.2) < 1e-9, "the user's scale multiplies the source scale")

-- #177: the layout takes the native tracker's top while it is hidden and its NineSlice's bottom while it is shown, so a
-- visibility change must reflow the column even though Edit Mode's fixed height means the frame's size never changes.
local visibility = harness.new({ headerShown = true })
local visibilityHost, visibilityNative = visibility.host, visibility.native
visibility.check(
	visibilityHost.point[2] == visibilityNative.NineSlice and visibilityHost.point[3] == "BOTTOM",
	"a shown native tracker holds the column under its quests"
)
local heightWhileShown = visibilityNative:GetHeight()
visibilityNative:Hide()
visibility.drain()
visibility.check(
	visibilityHost.point[1] == "TOP"
		and visibilityHost.point[2] == visibilityNative
		and visibilityHost.point[3] == "TOP",
	"hiding the native tracker moves the column to its top"
)
visibility.check(visibilityNative:GetHeight() == heightWhileShown, "the hidden tracker keeps its Edit Mode height")
visibilityNative:Show()
visibility.drain()
visibility.check(
	visibilityHost.point[1] == "TOP"
		and visibilityHost.point[2] == visibilityNative.NineSlice
		and visibilityHost.point[3] == "BOTTOM",
	"showing the native tracker moves the column back under its quests"
)
visibility.check(
	visibilityNative:GetHeight() == heightWhileShown,
	"the shown tracker still has no size change to report"
)

-- The room-below pass must not be a probe: Blizzard's EndLayout hides a section that fits nothing and
-- FreeUnusedBlocks releases every block, so a second layout would replay each header's add animation and rebuild every
-- block. Issue #438. The section uses Blizzard's own module mixin, which the native tracker source supplies.
local asideChecks = 0
if t.env.ObjectiveTrackerModuleMixin then
	local stacked = harness.new({ deferReady = true, headerShown = true })
	stacked.first.contentHeight, stacked.second.contentHeight = 0, 0
	stacked.nativeModule(3)
	stacked.ready()
	stacked.drain()
	stacked.check(stacked.host.point[2] == stacked.native.NineSlice, "the column starts below the quests")
	-- The quests reach the bottom of the screen: nothing fits below the native content bottom.
	stacked.native.NineSlice.bottom = 10
	stacked.host:MarkDirty()
	stacked.drain()
	stacked.check(stacked.host.point[2] == stacked.native, "the column moves above or beside the tracker")
	local animations, releases = stacked.headerAnimations(), stacked.blocksReleased()
	stacked.host:MarkDirty()
	stacked.drain()
	stacked.check(stacked.host.point[2] == stacked.native, "the column stays above or beside the tracker")
	stacked.check(stacked.headerAnimations() == animations, "a second layout aside replays no header animation")
	stacked.check(stacked.blocksReleased() == releases, "a second layout aside releases no block")
	-- The quests shrink so the whole laid-out column fits below again.
	stacked.native.NineSlice.bottom = 700
	animations, releases = stacked.headerAnimations(), stacked.blocksReleased()
	stacked.host:MarkDirty()
	stacked.drain()
	stacked.check(
		stacked.host.point[1] == "TOP"
			and stacked.host.point[2] == stacked.native.NineSlice
			and stacked.host.point[3] == "BOTTOM",
		"the column returns below the quests when they leave room for it"
	)
	stacked.check(stacked.headerAnimations() == animations, "the move back below replays no header animation")
	stacked.check(stacked.blocksReleased() == releases, "the move back below releases no block")
	animations, releases = stacked.headerAnimations(), stacked.blocksReleased()
	stacked.host:MarkDirty()
	stacked.drain()
	stacked.check(stacked.host.point[2] == stacked.native.NineSlice, "the column stays below the quests")
	stacked.check(stacked.headerAnimations() == animations, "a repeated layout below replays no header animation")
	stacked.check(stacked.blocksReleased() == releases, "a repeated layout below releases no block")
	asideChecks = stacked.checks()
end

-- The shared scroll wrapper: every section but the one that asks for the rest caps at 200 units, the remaining one
-- gets what the others leave, and only an overflowing section shows the minimal bar.
local scroll = harness.new({ headerShown = true })
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

print("tracker_host_spec: " .. (t.checks() + asideChecks + scroll.checks()) .. " checks passed")
