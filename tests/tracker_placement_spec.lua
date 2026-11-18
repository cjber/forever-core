-- #850: the column sits under the game's quest tracker by default, on the tracker's last visible line, and left of it
-- when it does not fit between that line and the screen's bottom. Following the line is one SetPoint on UIParent and
-- never a layout. The harness's tracker fails the spec on a write or hook, and on any read but its place and its line.
local harness = dofile("tests/tracker_host_harness.lua")

local function Under(ctx, line)
	local point, rect = ctx.host.point, ctx.nativeRect
	return point[1] == "TOPLEFT"
		and point[2] == ctx.parent
		and point[3] == "BOTTOMLEFT"
		and point[4] == rect.left
		and point[5] == (line or rect.line)
end
local function Pinned(ctx)
	local point = ctx.host.point
	return point[1] == "TOPRIGHT" and point[2] == ctx.native and point[3] == "TOPLEFT"
end
-- How many times the sections laid out, so a spec can say a move was not a layout.
local function Updates(ctx)
	return (ctx.first.updates or 0) + (ctx.second.updates or 0)
end

local t = harness.new({ hostSettings = { attached = false } })
local check = t.check
check(t.hostSettings.placement == "under", "a column with no saved place goes under the game tracker")
check(Under(t), "its top left corner is on the tracker's last line")
check(t.first.available == 880 - 10, "the sections lay out in the room from the tracker's top, wherever its list ends")

-- A quest accepted, completed or collapsed moves the tracker's last line. The column follows with one SetPoint.
local updates = Updates(t)
t.moveLine(600)
check(Under(t, 600), "the column follows the last line down")
check(t.pending() == 0 and Updates(t) == updates, "and following it queues no layout and lays out no section")
t.moveLine(820)
check(Under(t, 820), "and back up")
check(t.pending() == 0 and Updates(t) == updates, "with no layout either way")

-- A list that leaves less room under it than the column needs puts the column left of the tracker, and room coming
-- back returns it, both without a layout: the column's height never depends on where the list ends.
local height = t.host:GetHeight()
t.moveLine(height - 1)
check(Pinned(t), "a column taller than the room under the list sits left of the tracker")
check(t.pending() == 0 and Updates(t) == updates, "moving there is not a layout")
t.moveLine(height)
check(Under(t, height), "it returns under the list once the whole column fits")
check(t.pending() == 0 and Updates(t) == updates, "and returning is not a layout")

-- The column's own growth is measured by its layout, which places it again.
t.moveLine(400)
t.first.contentHeight = 500
t.host:MarkDirty()
t.drain()
check(t.host:GetHeight() > 400 and Pinned(t), "a column that grows past the room under the list moves left")
t.first.contentHeight = 80
t.host:MarkDirty()
t.drain()
check(Under(t, 400), "and comes back when it shrinks")

-- A tracker with nothing to show hides, which moves no line: core adds no frame to the tracker to hear it, so the
-- column holds its place until its own next layout puts it at the tracker's top.
t.showTracker(false)
check(Under(t, 400), "a tracker hiding leaves the column where it was")
t.host:MarkDirty()
t.drain()
check(Under(t, t.nativeRect.top), "and its next layout puts it at the hidden tracker's top")
t.showTracker(true)
t.moveLine(400)
check(Under(t, 400), "the line moving again puts the column under it")

-- A tracker the client has not placed yet has no line, which says nothing about room: the column keeps its place.
t.moveLine(nil)
check(Under(t, 400), "an unplaced tracker line leaves the column under the list")
t.moveLine(400)

-- An Edit Mode move of the tracker moves its line and its left edge; the column follows both.
t.nativeRect.left = 300
t.moveLine(500)
check(Under(t, 500) and t.host.point[4] == 300, "an Edit Mode move carries the column with the tracker")

-- In combat the column holds still, since it holds protected quest item buttons. Combat ending lays it out again,
-- under the line where it has gone meanwhile.
t.setCombat(true)
t.moveLine(450)
check(Under(t, 500), "a quest line moving in combat leaves the column where it was")
t.setCombat(false)
t.fire("PLAYER_REGEN_ENABLED")
t.drain()
check(Under(t, 450), "and the column catches up when combat ends")

-- A drag wins over the place: the column stays where it was dropped while the list moves.
t.ns.TrackerHost.SavePosition(100, -200)
t.drain()
t.moveLine(300)
check(t.host.point[2] == t.parent and t.host.point[4] == 100 and t.host.point[5] == -200, "a dragged column stays put")

-- Picking a place releases the drag and moves the column there.
local api = t.ns.TrackerHost
api.SetPlacement("left")
t.drain()
check(t.hostSettings.x == nil and t.hostSettings.y == nil, "picking a place releases the dragged position")
check(api.GetPlacement() == "left" and Pinned(t), "Left pins the column beside the tracker")
t.moveLine(700)
check(Pinned(t), "a pinned column ignores the tracker's line")
api.SetPlacement("under")
t.drain()
check(Under(t, 700), "Under puts it back on the line")
api.SetPlacement("above")
check(api.GetPlacement() == "under", "an unknown place is ignored")

-- Lock wins: a locked column holds its place while the list moves, and picking a place still moves it.
api.SetLocked(true)
t.moveLine(650)
check(Under(t, 700), "a locked column holds its place while the list moves")
t.moveLine(100)
check(Under(t, 700), "even when the list grows past it")
api.SetPlacement("under")
t.drain()
check(Under(t, 100) or Pinned(t), "picking a place moves a locked column once")
t.moveLine(650)
check(not Under(t, 650), "and it holds again after")
api.SetLocked(false)
t.moveLine(650)
check(Under(t, 650), "unlocked, it follows the line again")

-- Every section's menu offers the two places, and picking one sets it.
local function Entry(entries, text)
	for _, entry in ipairs(entries) do
		if entry.text == text then
			return entry
		end
	end
end
t.host.shown = true
t.first.Header.scripts.OnMouseUp(t.first.Header, "RightButton")
local position = Entry(t.menus[#t.menus].entries, "Tracker position")
check(position ~= nil, "the section menu offers Tracker position")
local left = Entry(position.entries, "Left of the quest tracker")
local under = Entry(position.entries, "Under the quest tracker")
check(left and under, "with Under and Left")
check(under.isSelected() and not left.isSelected(), "Under is ticked while the column sits under the tracker")
left.callback()
t.drain()
check(Pinned(t) and left.isSelected(), "picking Left moves the column and ticks Left")
api.SavePosition(10, -10)
t.drain()
check(not left.isSelected() and not under.isSelected(), "neither is ticked while the column sits where it was dragged")

-- A column whose first layout finds no tracker line yet waits at the pin, and goes under once the line exists.
local early = harness.new({ hostSettings = { attached = false }, deferReady = true })
early.nativeRect.line = nil
early.ready()
early.drain()
early.check(Pinned(early), "with no tracker line yet the column waits at its pin")
early.moveLine(700)
early.check(Under(early, 700), "and goes under the line once the tracker has one")

-- The host scale applies to the line: a tracker at a different scale is converted into the column's units.
local scaled = harness.new({ hostSettings = { attached = false } })
scaled.nativeRect.scale, scaled.nativeRect.left = 2, 100
scaled.moveLine(300)
local point = scaled.host.point
scaled.check(point[4] == 200 and point[5] == 600, "the line is read in the column's units")

print(("tracker_placement_spec: %d checks passed"):format(t.checks() + early.checks() + scaled.checks()))
