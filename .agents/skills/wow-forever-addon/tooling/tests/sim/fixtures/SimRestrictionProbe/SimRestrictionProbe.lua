-- luacheck: ignore 131 (the spec calls these by name)
-- luacheck: read globals C_Map C_FriendList CopyToClipboard
-- Fixture for the restriction classes: one call per class, run by the spec as this addon so the call is tainted.
function SimRestrictionProbeWorldMap()
	C_Map.OpenWorldMap(1454)
end

function SimRestrictionProbeWho()
	C_FriendList.SendWho("probe")
end

function SimRestrictionProbeAlways()
	CopyToClipboard("probe")
end
