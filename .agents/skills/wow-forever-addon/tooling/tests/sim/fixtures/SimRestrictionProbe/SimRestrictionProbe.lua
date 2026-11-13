-- luacheck: ignore 131 (the spec calls these by name)
-- luacheck: read globals C_Map C_FriendList C_TradeSkillUI C_UI CopyToClipboard CreateFrame UIParent
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

-- The live client refused these from shipped builds (cjber/forever-core#538).
function SimRestrictionProbeTradeSkill()
	C_TradeSkillUI.OpenTradeSkill(164)
end

function SimRestrictionProbeReload()
	C_UI.Reload()
end

local probeFrame = CreateFrame("Frame", "SimRestrictionProbeFrame", UIParent)

-- The live client refused a widget method's call too; the override table keys that by the method's own name.
function SimRestrictionProbePassThrough()
	probeFrame:SetPassThroughButtons("RightButton")
end
