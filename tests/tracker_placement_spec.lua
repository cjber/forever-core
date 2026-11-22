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
	return point[1] == "TOPRIGHT" and point[2] == ctx.parent and point[3] == "BOTTOMLEFT"
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

-- Lock wins: a locked column holds its place while the list moves, except for Under's no-room fallback to Left, and
-- picking a place still moves it.
api.SetLocked(true)
t.moveLine(650)
check(Under(t, 700), "a locked column holds its place while the list moves")
t.moveLine(100)
check(Pinned(t), "but a list that leaves no room under it moves the column left, as Under does unlocked")
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

-- The "Attach to quest tracker" checkbox addons still ship (#850's report: toggling it did nothing). It reads
-- GetSettings().attached and writes SetAttached; off picks Left, on picks Under, and its callback hears each change.
local box = harness.new({ hostSettings = { attached = false } })
local boxApi = box.ns.TrackerHost
local heard = {}
boxApi.OnAttachmentChanged(function(attached)
	heard[#heard + 1] = attached
end)
box.check(
	boxApi.GetSettings().attached == true and boxApi.IsAttachedToQuestTracker(),
	"the checkbox shows attached while under"
)
boxApi.SetAttached(false)
box.drain()
box.check(Pinned(box) and boxApi.GetPlacement() == "left", "turning it off moves the column left of the tracker")
box.check(boxApi.GetSettings().attached == false and heard[#heard] == false, "and the checkbox hears it is off")
boxApi.SetAttached(true)
box.drain()
box.check(Under(box) and boxApi.GetSettings().attached == true, "turning it on puts the column back under")
box.check(heard[#heard] == true, "and the checkbox hears it is on")
boxApi.SavePosition(10, -10)
box.check(boxApi.GetSettings().attached == false and heard[#heard] == false, "a drag shows as not attached")
boxApi.SetAttached(true)
box.drain()
box.check(Under(box), "and turning it on releases the drag")

-- Each change is announced once: a repeated pick, or a drag of a column already off the tracker, calls back nothing,
-- and a callback that writes the value it hears back through SetAttached ends there instead of recursing.
local once = harness.new({ hostSettings = { attached = false } })
local onceApi, calls = once.ns.TrackerHost, 0
onceApi.OnAttachmentChanged(function(attached)
	calls = calls + 1
	onceApi.SetAttached(attached)
end)
onceApi.SetAttached(false)
once.check(calls == 1, "one toggle is one callback, even when the callback writes it back")
onceApi.SetAttached(false)
onceApi.SavePosition(10, -10)
onceApi.SavePosition(20, -20)
once.check(calls == 1, "a repeated pick and a drag of a detached column call back nothing")

-- A locked column placed under a short list holds there, but growing past the screen's bottom moves it left (#851's
-- in-game check: after a reload the sections filled in under a long list and ran off the screen).
local grown = harness.new({ hostSettings = { attached = true, placement = "under", locked = true } })
grown.first.contentHeight = 40
grown.host:MarkDirty()
grown.drain()
grown.check(Under(grown), "a locked column goes under a list it fits under")
local heldAt = grown.nativeRect.line
grown.moveLine(650)
grown.check(Under(grown, heldAt), "and holds there while the list moves")
-- #851's in-game check: a locked column placed under the list as it loaded after a reload sat over the list once the
-- list grew in under it. A list that leaves the column no room under it puts it left, Lock on or off.
local longList = harness.new({ hostSettings = { attached = true, placement = "under", locked = true } })
longList.check(Under(longList), "a locked column goes under a short list")
longList.moveLine(longList.host:GetHeight() - 1)
longList.check(Pinned(longList), "and moves left once the list leaves it no room under it")
longList.moveLine(800)
longList.check(Pinned(longList), "and stays left, locked, when room comes back")
grown.first.contentHeight = 800
grown.host:MarkDirty()
grown.drain()
grown.check(Pinned(grown), "but moves left once it would run off the screen")

-- A column the player dragged never moves, locked or not, however the tracker grows.
local pinnedDrag =
	harness.new({ hostSettings = { attached = false, placement = "under", locked = true, x = 40, y = -300 } })
pinnedDrag.first.contentHeight = 800
pinnedDrag.host:MarkDirty()
pinnedDrag.drain()
pinnedDrag.moveLine(100)
local dragPoint = pinnedDrag.host.point
pinnedDrag.check(
	dragPoint[2] == pinnedDrag.parent and dragPoint[4] == 40 and dragPoint[5] == -300,
	"a dragged, locked column stays at its spot when the tracker grows"
)

-- A reload keeps the choice: saved settings with a placement are not migrated again.
local saved = box.hostSettings
saved.attached, saved.placement = true, "left"
local reloaded = harness.new({ hostSettings = saved })
reloaded.check(Pinned(reloaded) and reloaded.ns.TrackerHost.GetSettings().attached == false, "Left survives a reload")
local savedUnder = harness.new({ hostSettings = { attached = true, placement = "under", x = 5, y = -5 } })
savedUnder.check(savedUnder.hostSettings.x == 5, "a dragged spot saved with a placement survives a reload")
local old = harness.new({ hostSettings = { attached = true, x = 5, y = -5 } })
old.check(old.hostSettings.x == nil and Under(old), "a pre-placement attached table drops its spot and goes under")

-- The host scale applies to the line: a tracker at a different scale is converted into the column's units.
local scaled = harness.new({ hostSettings = { attached = false } })
scaled.nativeRect.scale, scaled.nativeRect.left = 2, 100
scaled.moveLine(300)
local point = scaled.host.point
scaled.check(point[4] == 200 and point[5] == 600, "the line is read in the column's units")

-- #987/#1139: the column keeps clear of the action bars. It reads the bars the player's own layout put on screen: a bar
-- lying across the column's width caps how far down it reaches, and a bar standing at its side caps how far right, so
-- the column stops at the bars rather than laying out into them.
local bars = harness.new({ hostSettings = { attached = false } })
local function Bar(name, barLeft, barTop, barWidth, barHeight, shown)
	bars.env[name] = {
		IsShown = function()
			return shown ~= false
		end,
		GetLeft = function()
			return barLeft
		end,
		GetTop = function()
			return barTop
		end,
		GetWidth = function()
			return barWidth
		end,
		GetHeight = function()
			return barHeight
		end,
		GetEffectiveScale = function()
			return 1
		end,
	}
end
local room = bars.first.available
-- A bar across the bottom of the screen, under the column.
Bar("MainMenuBar", 0, 100, 1200, 60)
bars.host:MarkDirty()
bars.drain()
bars.check(bars.first.available == room - 100, "a bar under the column takes its room off the layout")
Bar("MainMenuBar", 0, 100, 1200, 60, false)
bars.host:MarkDirty()
bars.drain()
bars.check(bars.first.available == room, "a hidden bar takes none")
-- The same bar parked at the far left, where the column is not: it is in nobody's way.
Bar("MainMenuBar", 0, 100, 300, 60)
bars.host:MarkDirty()
bars.drain()
bars.check(bars.first.available == room, "a bar the column never reaches takes none")
-- A bar that leaves less room than the column is tall moves it left, as a short list does.
Bar("MainMenuBar", 0, 750, 1200, 60)
bars.host:MarkDirty()
bars.drain()
bars.check(Pinned(bars), "a bar leaving no room under it moves the column left")
bars.env.MainMenuBar = nil
-- A bar standing at the right of the screen, beside the column, moves it left of that bar.
Bar("MultiBarRight", 1150, 880, 40, 800)
bars.host:MarkDirty()
bars.drain()
bars.check(bars.host.point[4] == 890, "a right-hand bar moves the column left of it")
bars.check(bars.first.available == room, "and takes no room from below")

print(
	("tracker_placement_spec: %d checks passed"):format(
		t.checks()
			+ early.checks()
			+ scaled.checks()
			+ box.checks()
			+ reloaded.checks()
			+ savedUnder.checks()
			+ old.checks()
			+ once.checks()
			+ grown.checks()
			+ pinnedDrag.checks()
			+ longList.checks()
			+ bars.checks()
	)
)
