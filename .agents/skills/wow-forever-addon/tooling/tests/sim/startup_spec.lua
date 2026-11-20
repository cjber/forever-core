-- No-addon startup and settings parity against the pinned client UI and data.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")

local function eq(actual, expected)
	assert(actual == expected, string.format("expected %s, got %s", tostring(expected), tostring(actual)))
end

for _, gamepad in ipairs({ false, true }) do
	local sim = Sim.new()
	sim:expectNoErrors()
	sim:login()
	sim:expectNoErrors()
	sim:setGamepad(gamepad)
	sim:expectNoErrors()
	-- Native recraft callbacks use this undocumented enum from addon-owned forms too.
	sim:runAs(
		"ItemSoundEnumProbe",
		[=[
        assert(Enum.ItemSoundType.Pickup == 0)
        assert(Enum.ItemSoundType.Drop == 1)
        assert(Enum.ItemSoundType.Use == 2)
        assert(Enum.ItemSoundType.Close == 3)
    ]=]
	)
	sim:expectNoErrors()
	local G = sim.G
	sim:input(function()
		G.ShowUIPanel(G.SettingsPanel)
	end)
	eq(G.SettingsPanel:IsShown(), true)
	sim:input(function()
		G.SettingsPanel:Close()
	end)
	sim:advance(0.1)
	eq(G.SettingsPanel:IsShown(), false)
	sim:expectNoErrors()
	if gamepad then
		sim:input(function()
			local shortcuts = G.GamepadMainActionBarFrame.PageUnit.ShortcutsActionBar
			shortcuts:Show()
			shortcuts.dpadTopButton:Click("LeftButton", true)
		end)
		sim:expectNoErrors()
	end
end

do
	-- Client names loaded at startup that Forever addons call from their own code: the raid warning, the nameplate
	-- driver and the trainer kind.
	local probe = Sim.new()
	probe:login()
	probe:runAs(
		"StartupNamesProbe",
		[=[
        RaidWarningUtil.AddMessage("probe", { r = 1, g = 1, b = 1 })
        assert(RaidWarningFrame:IsShown())
        NamePlateDriverFrame:HookScript("OnEvent", function() end)
        assert(IsTradeskillTrainer() == false)
    ]=]
	)
	probe:event("DISPLAY_SIZE_CHANGED")
	probe:advance(0.1)
	probe:expectNoErrors()
end

local sim = Sim.new()
local G = sim.G
assert(
	G.ChatFrameUtil and G.ChatFrameUtil.TryInsertQuestLinkForQuestID,
	"native quest clicks have their chat dependency"
)
sim:input(function()
	G.ChatFrameUtil.TryInsertQuestLinkForQuestID(608001)
end)
sim:expectNoErrors()
-- The pinned SpellFlyout and SpellFlyoutItem tables define Warrior stances even before any are learned.
local name, description, count, known = G.GetFlyoutInfo(269)
eq(name, "Stances")
eq(type(description), "string")
eq(count, 3)
eq(known, false)
local spellID, overrideSpellID, slotKnown = G.GetFlyoutSlotInfo(269, 1)
eq(spellID, 2457)
eq(overrideSpellID, 2457)
eq(slotKnown, false)
sim.world.spells[2457] = { name = "Battle Stance" }
local _, _, _, cached = G.GetFlyoutInfo(269)
eq(cached, false)
sim.world.knownSpells[2457] = true
local _, _, _, learned = G.GetFlyoutInfo(269)
eq(learned, true)
local _, _, learnedSlot, spellName = G.GetFlyoutSlotInfo(269, 1)
eq(learnedSlot, true)
eq(spellName, "Battle Stance")
eq(G.GetFlyoutInfo(-1), nil)
eq(G.GetFlyoutSlotInfo(269, 0), nil)
eq(G.GetFlyoutSlotInfo(269, count + 1), nil)
eq(G.GetFlyoutSlotInfo(-1, 1), nil)
sim:expectNoErrors()
-- QUEST_ACCEPTED must reach the real top-banner manager rather than its falsey API fallback.
assert(G.TopBannerMgr, "default startup loads the native top-banner manager")
sim.impl["C_QuestLog.IsQuestTask"] = function(id)
	return id == 608001
end
sim.impl["C_QuestLog.GetTitleForQuestID"] = function(id)
	return id == 608001 and "Bonus banner startup fixture" or nil
end
sim:login()
sim:event("QUEST_ACCEPTED", 608001)
sim:advance(0.1)
eq(G.ObjectiveTrackerTopBannerFrame:GetQuestID(), 608001)
eq(G.TopBannerMgr.currentBanner.frame, G.ObjectiveTrackerTopBannerFrame)
sim:expectNoErrors()
eq(G.ObjectiveTrackerTopBannerFrame:IsShown(), true)
-- The native completion events must reach real alert systems and lazy-loaded Achievement UI.
local worldAchievementInfo = sim.impl.GetAchievementInfo
sim.impl.GetAchievementInfo = function(id)
	return id, "Completion fixture", 10, true, 1, 1, 2026, "Completed", 0, 134400, "", false, true
end
sim.impl["C_PerksActivities.GetPerksActivityInfo"] = function(id)
	return { ID = id, activityName = "Monthly completion fixture", completed = true }
end
sim:event("ACHIEVEMENT_EARNED", 608002, false)
sim:event("PERKS_ACTIVITY_COMPLETED", 608003)
sim:advance(0.1)
sim:expectNoErrors()
assert(G.AchievementFrame, "native achievement UI loaded from the completion event")
assert(G.AchievementAlertSystem, "native achievement alert system initialized")
assert(G.MonthlyActivityAlertSystem, "native monthly alert system initialized")
-- Exercise an active Camelot category, not the no-renown early return.
sim.impl.GetAchievementInfo = worldAchievementInfo
sim.world.achievements.categories = {
	{ id = 1, name = "Challenges", achievements = { { id = 608002, name = "Completion fixture" } } },
}
sim.impl["C_MajorFactions.GetCurrentRenownLevel"] = function()
	return 1
end
sim.impl["C_AchievementInfo.IsValidAchievement"] = function(id)
	return id == 608002
end
local searched, focused
sim.impl.SetFocusedAchievement = function(id)
	focused = id
end
sim.impl.SetAchievementSearchString = function(text)
	searched = text
end
sim.impl.GetNumFilteredAchievements = function()
	return 1
end
sim.impl.GetFilteredAchievementID = function(index)
	return index == 1 and 608002 or nil
end
sim:loadBlizzard("Blizzard_LegacySystem/Blizzard_LegacySystem_Bootstrap.lua")
for _, shown in ipairs({ true, false }) do
	sim:input(function()
		G.ToggleAchievementFrame()
		if shown then
			G.AchievementFrame_SelectAchievement(608002)
		end
	end)
	sim:advance(0.1)
	sim:expectNoErrors()
	eq(G.LegacySystemFrame:IsShown(), shown)
	if shown then
		eq(searched, "")
		eq(focused, 608002)
		local selected = G.AchievementFrameAchievements_GetSelectedElementData()
		assert(selected and selected.id == 608002, "native detail selection reaches the requested achievement")
	end
end
-- Native recipe continuations must register the item's identity, rather than a generated zero default.
sim.world.items[9001] = { name = "Delayed ore", count = 2 }
local itemCached, requested, loaded = false, nil, 0
sim.impl["C_Item.IsItemDataCachedByID"] = function(id)
	return id ~= 9001 or itemCached
end
sim.impl["C_Item.RequestLoadItemDataByID"] = function(id)
	requested = id
end
local item = G.Item:CreateFromItemID(9001)
eq(item:GetItemID(), 9001)
local continuables = G.ContinuableContainer:Create()
continuables:AddContinuable(item)
eq(
	continuables:ContinueOnLoad(function()
		loaded = loaded + 1
	end),
	false
)
eq(requested, 9001)
eq(loaded, 0)
itemCached = true
sim:event("ITEM_DATA_LOAD_RESULT", 9001, true)
eq(loaded, 1)
local canceled = item:ContinueWithCancelOnRecordLoad(function()
	loaded = loaded + 1
end)
eq(canceled(), true)
sim:event("ITEM_DATA_LOAD_RESULT", 9001, true)
eq(loaded, 1)
sim:expectNoErrors()
print("startup_spec: bare boot, login and SettingsPanel pass with mouse and gamepad; native flyout metadata passes")

-- The pinned quest XML defines Checkbox and inherits CheckBox. Template identity ignores case,
-- while Lua child fields and instance names retain their original spelling.
for _, template in ipairs({
	"QuestLogTrackCheckboxTemplate",
	"QuestLogTrackCheckBoxTemplate",
	"QUESTLOGTRACKCHECKBOXTEMPLATE",
}) do
	assert(G.CreateFrame("Frame", nil, G.UIParent, template).CheckMark, template)
end
local templateErrors = #sim.templates.errors
assert(sim.templates.loadXML(here .. "template_case.xml", "SimTests", "template_case.xml"))
eq(#sim.templates.errors, templateErrors)
for _, template in ipairs({ "CaseLeafTemplate", "cASElEAFtEMPLATE", "CASELEAFTEMPLATE" }) do
	local frame = G.CreateFrame("Frame", nil, G.UIParent, template)
	eq(frame:GetWidth(), 61)
	eq(frame:GetHeight(), 29)
	eq(frame.CaseMarker:GetWidth(), 13)
	eq(frame.casemarker, nil)
end
eq(G.CaseNonIntrinsicTag, nil)
local named = G.CreateFrame("Frame", "CaseMiXeDInstance", G.UIParent, "caseleaftemplate")
eq(named:GetName(), "CaseMiXeDInstance")
local ok, err = pcall(G.CreateFrame, "Frame", nil, G.UIParent, "CaseMiSsInGTemplate")
assert(not ok and tostring(err):find("CaseMiSsInGTemplate", 1, true))
sim:expectNoErrors()

local itemLink = "|cff0070dd|Hitem:608002:::::::::|h[Inspection output]|h|r"
sim.world.items[608002] = { name = "Inspection output", link = itemLink, quality = 3, icon = 134400, count = 8 }
for _, metadataItem in ipairs({ G.Item:CreateFromItemID(608002), G.Item:CreateFromItemLink(itemLink) }) do
	eq(metadataItem:IsItemEmpty(), false)
	eq(metadataItem:GetItemName(), "Inspection output")
	eq(metadataItem:GetItemQuality(), 3)
	eq(metadataItem:GetItemIcon(), 134400)
	eq(G.C_Item.GetItemCount(metadataItem:GetStaticBackingItem()), 8)
end
sim:expectNoErrors()

assert(sim.templates.loadXML(here .. "template_intrinsic.xml", "SimTests", "template_intrinsic.xml"))
for _, button in ipairs({
	G.CreateFrame("Button", nil, G.UIParent, "SimIntrinsicLeafTemplate"),
	G.CreateFrame("SimIntrinsicButton", nil, G.UIParent, "SimIntrinsicLeafTemplate"),
	G.SimIntrinsicParent.Direct,
}) do
	eq(button.intrinsicLoads, 1, "intrinsic OnLoad runs once through implicit and explicit inheritance")
	button:Click("LeftButton")
	eq(button.intrinsicClicks, 1, "intrinsic click runs once")
end
G.C_AddOns.LoadAddOn("Blizzard_Professions")
local flyoutTemplate = "ProfessionsFlyoutItemButtonTemplate"
local flyoutInfo = G.C_XMLUtil.GetTemplateInfo(flyoutTemplate)
local flyoutButton = G.CreateFrame(flyoutInfo.type, nil, G.UIParent, flyoutTemplate)
eq(
	type(flyoutButton.SetItemLocation),
	"function",
	"native pooled item-button intrinsic methods survive template construction"
)
sim:expectNoErrors()
