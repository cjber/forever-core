-- The host must never enter Blizzard's tracker manager, including through pooled lines.
local harness = dofile("tests/tracker_host_harness.lua")
local t = harness.new({ deferReady = true })
local check, drain = t.check, t.drain
local host, grip, native, parent = t.host, t.grip, t.native, t.parent
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
check(first.point[5] == 0 and second.point[5] == -90, "sections follow uiOrder")
check(second.available == 518, "remaining space follows screen geometry")
check(native:GetHeight() == 300, "native viewport preserves an externally sized height before clamping")
native:SetHeight(420)
native.scripts.OnSizeChanged(native)
drain()
check(native:GetHeight() == 420, "native viewport adopts an external resize before clamping")
native:SetHeight(700)
native.scripts.OnSizeChanged(native)
drain()
check(native:GetHeight() == 700, "native container keeps its externally sized height")
native:SetPoint("TOPRIGHT", parent, "TOPRIGHT", 0, 0)
t.eventRegistry:TriggerEvent("EditMode.SavedLayouts")
drain()
check(native.point[1] == "TOPLEFT" and native.point[2] == parent, "private host repairs native reanchor independently")
-- The managed frame layout or a UI addon can put the native frame back in its saved slot with no event at all.
local probe = t.probe()
check(probe ~= nil and probe ~= host, "an addon-owned probe follows the native frame's top left corner")
native:SetPoint("TOPRIGHT", parent, "TOPRIGHT", 0, -100)
probe.scripts.OnSizeChanged(probe)
check(t.pending() == 1, "a silent native reanchor reflows the column")
drain()
check(native.point[1] == "TOPLEFT" and native.point[2] == parent, "the silent reanchor is restacked below the column")
probe.scripts.OnSizeChanged(probe)
check(t.pending() == 0, "the host's own restack does not queue another reflow")
t.editMode.active, t.editMode.shown = true, true
t.eventRegistry:TriggerEvent("EditMode.Enter")
check(host.shown == false, "private tracker hides while Edit Mode owns native slot")
check(native.clamped == true, "Edit Mode gets the native frame's screen clamp back")
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
check(native.clamped == false, "restacking after Edit Mode unclamps the native frame again")
check(native.point[1] == "TOPLEFT" and native.point[2] == parent, "native objectives stay independently anchored")
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
local other = {}
t.loadHost(other)
check(other.TrackerHost == t.ns.TrackerHost, "addons share a single private host")
local hostPaths = {}
for path in (os.getenv("AGF_TRACKER_HOSTS") or "UI/TrackerHost.lua"):gmatch("[^\n]+") do
	hostPaths[#hostPaths + 1] = path
end
for index = 2, #hostPaths do
	local joining, count = {}, #t.frames
	t.loadHost(joining, hostPaths[index])
	check(joining.TrackerHost == t.ns.TrackerHost, "companion joins the first loaded host")
	check(#t.frames == count, "companion must not create a second host")
end
check(first:GetContextMenuParent() == host, "menus use private container")
check(grip ~= nil, "the grip is shown by the detached layout")
print("tracker_host_spec: " .. t.checks() .. " checks passed")
