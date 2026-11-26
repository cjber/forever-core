-- EllesmereUI's Custom Quest Tracker draws the filtered list the player reads in EUI_CustomQuestTracker, while the
-- game's tracker stays shown at alpha 0 holding every watched quest (#332). The shared column follows the visible list
-- rather than the muted native content, keeps the corner it last saw while EllesmereUI's own rules hide the list, and
-- falls back to the game's tracker when this session never saw it. The harness's tracker fails the spec on any read but
-- its place and its line, and on every write or hook, so a placement that anchored to something would fail here.
local harness = dofile("tests/tracker_host_harness.lua")

local function UnderList(ctx, list)
	local point = ctx.host.point
	return point[1] == "TOPLEFT"
		and point[2] == ctx.parent
		and point[3] == "BOTTOMLEFT"
		and point[4] == list.left
		and point[5] == list.top - list.height
end

-- The attached column sits under EllesmereUI's list, not on the muted native tracker at its top.
local t = harness.new({ hostSettings = { attached = true, placement = "under" } })
local list = t.env.CreateFrame("Frame", "EUI_CustomQuestTracker", t.parent)
list.left, list.top, list.height = 900, 860, 200
t.showTracker(false)
t.env.EUI_CustomQuestTracker = list
-- EllesmereUI builds its frame on PLAYER_LOGIN through a zero-delay timer, after the column's first layout.
t.tickDelayed()
t.check(UnderList(t, list), "the attached column sits under EllesmereUI's filtered list")
t.check(t.host.point[4] ~= t.nativeRect.left, "and not at the muted game tracker's place")

-- The frame's height is its filtered content's height, so a new quest grows the line the column follows.
local updates = t.first.updates
list.height = 320
t.recheck("QUEST_LOG_UPDATE")
t.check(UnderList(t, list), "and follows its last line as the list grows")
t.check(t.first.updates == updates, "following it lays out no section")

-- EllesmereUI renders on its own zero-delay timer, so folding the list, hiding it or filtering it resizes the frame
-- with no client event to hear: QUEST_LOG_UPDATE returned before the render. The column never hooks the list, so it
-- samples the rect from its own frame and lays out when the sample differs. Advancing our own OnUpdate is the only
-- signal there is.
local function Sample(ctx)
	ctx.stepUpdates()
	ctx.drain()
end
local before = t.host.point[5]
list.height = 180
Sample(t)
t.check(UnderList(t, list), "a resize with no client event moves the column")
t.check(t.host.point[5] ~= before, "and it really moved")
-- The list never hooks: a frame of ours may run OnUpdate, another addon's may not.
t.check(
	list.scripts.OnSizeChanged == nil and list.scripts.OnShow == nil and list.scripts.OnHide == nil,
	"nothing is hooked onto EllesmereUI's frame"
)
list.shown = false
Sample(t)
t.check(t.ns.TrackerHost.Debug():find("list=ellesmere", 1, true) ~= nil, "a fold keeps the source")
list.shown = true
Sample(t)
t.check(UnderList(t, list), "unfolding puts the column back under it")

-- A scale change makes the remembered corner wrong, so it is dropped rather than converted: the game's tracker is
-- read again, as it was before EllesmereUI was a list source.
local scaled = harness.new({ hostSettings = { attached = true, placement = "under" } })
local scaledList = scaled.env.CreateFrame("Frame", "EUI_CustomQuestTracker", scaled.parent)
scaledList.left, scaledList.top, scaledList.height = 900, 860, 200
scaled.showTracker(false)
scaled.env.EUI_CustomQuestTracker = scaledList
scaled.tickDelayed()
scaled.check(UnderList(scaled, scaledList), "the column follows a placed list")
scaledList.shown = false
scaledList.scale = 1.5
scaled.tickDelayed()
scaled.check(
	scaled.host.point[4] == scaled.nativeRect.left,
	"a rescaled list that hides drops its corner and the game's tracker is read again"
)

-- The cached rect is stored in the host's units, so the host's scale is part of what it means. Changing the column's
-- own scale while the list is hidden leaves the numbers in the old units, so they are dropped too, not reused: the
-- source falls back to the game's tracker instead of a corner measured at the old scale.
local rescaledHost = harness.new({ hostSettings = { attached = true, placement = "under" } })
local rescaledList = rescaledHost.env.CreateFrame("Frame", "EUI_CustomQuestTracker", rescaledHost.parent)
rescaledList.left, rescaledList.top, rescaledList.height = 900, 860, 200
rescaledHost.showTracker(false)
rescaledHost.env.EUI_CustomQuestTracker = rescaledList
rescaledHost.tickDelayed()
rescaledHost.check(UnderList(rescaledHost, rescaledList), "the column follows the list before any rescale")
rescaledHost.check(
	rescaledHost.ns.TrackerHost.Debug():find("list=ellesmere", 1, true) ~= nil,
	"and names it as the source"
)
rescaledList.shown = false
rescaledHost.host.scale = 2
rescaledHost.tickDelayed()
rescaledHost.check(
	rescaledHost.ns.TrackerHost.Debug():find("list=ellesmere", 1, true) == nil,
	"a column rescale while the list is hidden drops its corner instead of reusing it in the old units"
)

-- EllesmereUI hides its list in arenas, in raids and on an empty log, all with the native frame still shown behind it:
-- the column holds the corner it last saw instead of dropping onto quests the player cannot see.
list.shown = false
t.recheck("QUEST_LOG_UPDATE")
t.check(UnderList(t, list), "a hidden EllesmereUI list leaves the column where it was")
t.check(t.ns.TrackerHost.Debug():find("list=ellesmere", 1, true) ~= nil, "and the diagnostic still names its source")

-- The list comes back at a new place after a profile load, and the column follows it there.
list.left, list.top, list.height = 700, 820, 120
list.shown = true
t.recheck("QUEST_LOG_UPDATE")
t.check(UnderList(t, list), "a moved list carries the column with it")

-- With EllesmereUI's custom tracker off, its frame is gone and the game's tracker is the one on screen again.
t.env.EUI_CustomQuestTracker = nil
t.showTracker(true)
t.recheck("QUEST_LOG_UPDATE")
t.check(
	t.host.point[1] == "TOPLEFT" and t.host.point[4] == t.nativeRect.left and t.host.point[5] == t.nativeRect.line,
	"with the custom tracker off the column returns under the game's tracker"
)
t.check(t.ns.TrackerHost.Debug():find("list=list", 1, true) ~= nil, "and the diagnostic says so")

-- A list this session never saw placed says nothing about the room: the column reads the game's tracker as it did
-- before EllesmereUI was a list source, even while the custom frame exists but is hidden.
local unseen = harness.new({ hostSettings = { attached = true, placement = "under" } })
local hidden = unseen.env.CreateFrame("Frame", "EUI_CustomQuestTracker", unseen.parent)
hidden.left, hidden.top, hidden.height = 900, 860, 200
hidden.shown = false
unseen.env.EUI_CustomQuestTracker = hidden
unseen.tickDelayed()
unseen.check(
	unseen.host.point[1] == "TOPLEFT"
		and unseen.host.point[4] == unseen.nativeRect.left
		and unseen.host.point[5] == unseen.nativeRect.line,
	"a list never seen placed leaves the native tracker in charge"
)

-- The sampler runs only while the column follows a list. A column the player dragged holds a free position, so nothing
-- can move it and six reads four times a second would be pure cost for the rest of the session (#1019).
local idle = harness.new({ hostSettings = { attached = false, x = 100, y = -200 } })
local idleList = idle.env.CreateFrame("Frame", "EUI_CustomQuestTracker", idle.parent)
idleList.left, idleList.top, idleList.height = 900, 860, 200
idle.env.EUI_CustomQuestTracker = idleList
idle.tickDelayed()
-- Let the settle burst that follows an event finish: it stops itself, so anything still armed after it is a sampler.
local function Settle(ctx)
	for _ = 1, 120 do
		ctx.stepUpdates()
		ctx.drain()
	end
	return #ctx.updateFrames()
end
idle.check(Settle(idle) == 0, "a dragged column runs no sampler")
-- Picking a place puts it back under the list, and the sampler starts again from that layout.
idle.ns.TrackerHost.SetPlacement("under")
idle.drain()
idle.check(Settle(idle) == 1, "picking a place starts the sampler again")

-- The left placement pins beside the visible list, not beside the muted native tracker.
local side = harness.new({ hostSettings = { placement = "left" } })
local visible = side.env.CreateFrame("Frame", "EUI_CustomQuestTracker", side.parent)
visible.left, visible.top, visible.height = 640, 840, 260
side.env.EUI_CustomQuestTracker = visible
side.tickDelayed()
side.check(
	side.host.point[1] == "TOPRIGHT" and side.host.point[4] == 640,
	"the left placement pins to EllesmereUI's left edge"
)

-- Both a custom EllesmereUI list and Questie's on screen: EllesmereUI is the slot the player chose, read first, as it
-- was when the column followed it (#332).
local both = harness.new({ hostSettings = { attached = true, placement = "under" } })
local eui = both.env.CreateFrame("Frame", "EUI_CustomQuestTracker", both.parent)
eui.left, eui.top, eui.height = 900, 860, 200
local questie = both.env.CreateFrame("Frame", nil, both.parent)
questie.left, questie.top, questie.height = 900, 700, 100
both.showTracker(false)
both.env.EUI_CustomQuestTracker, both.env.Questie_BaseFrame = eui, questie
both.tickDelayed()
both.check(UnderList(both, eui), "EllesmereUI's list is read before Questie's")
