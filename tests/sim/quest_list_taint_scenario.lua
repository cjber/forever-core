-- luacheck: read globals scenario ADDON
-- Issue #608: native Show/Hide scripts also update the shared managed-frame layout. With Edit Mode initialised,
-- hiding the native tracker from addon code taints that layout and the next secure pass reaches the scenario
-- tracker's secret Maw aura read under ForeverCore's taint. Exercise the real managed-frame and driver scripts.
local function ExpectAuraReadIsUntainted(sim, reads, before)
	assert(reads > before, "the client's scenario tracker reached the aura reader")
	sim:expectNoErrors(ADDON)
end

local function Run(sim, mode)
	-- Keep one watched quest so Blizzard has content to show when suppression is released.
	local quest = {
		questID = 101,
		questLogIndex = 1,
		title = "Watched quest",
		level = 10,
		isHeader = false,
		isTask = false,
		isBounty = false,
		isHidden = false,
		questClassification = sim.G.Enum.QuestClassification.Normal,
	}
	sim.impl["C_QuestLog.GetNumQuestLogEntries"] = function()
		return 1, 1
	end
	sim.impl["C_QuestLog.GetInfo"] = function(index)
		return index == 1 and quest or nil
	end
	sim.impl["C_QuestLog.GetNumQuestWatches"] = function()
		return 1
	end
	sim.impl["C_QuestLog.GetQuestIDForQuestWatchIndex"] = function()
		return 101
	end
	sim.impl["C_QuestLog.GetLogIndexForQuestID"] = function()
		return 1
	end
	sim.impl["C_QuestLog.GetQuestIDForLogIndex"] = function()
		return 101
	end
	sim.impl["C_QuestLog.GetTitleForQuestID"] = function()
		return "Watched quest"
	end
	sim.impl["C_QuestLog.GetDistanceSqToQuest"] = function()
		return 400, true
	end
	local reads = 0
	sim.impl["C_UnitAuras.GetAuraDataByIndex"] = function()
		reads = reads + 1
		assert(sim.taint.current == nil, "aura reader tainted by " .. tostring(sim.taint.current))
		return nil
	end
	local tracker = sim.G.ObjectiveTrackerFrame
	local db = mode == "disabled" and { questList = false } or mode == "enabled" and { questList = true } or {}
	-- A fresh database draws the Forever list only with Adventure Guide loaded (#776), so this player has it.
	local loaded = sim.impl["C_AddOns.IsAddOnLoaded"]
	sim.impl["C_AddOns.IsAddOnLoaded"] = function(name)
		return name == "AdventureGuideForever" or loaded(name)
	end
	if mode == "ellesmere" then
		sim.G.EllesmereUIQuestTracker = {}
		local custom = sim.G.CreateFrame("Frame", "EUI_CustomQuestTracker", sim.G.UIParent)
		custom:SetPoint("TOPRIGHT", sim.G.UIParent, "TOPRIGHT", -40, -100)
		custom:SetSize(250, 300)
		tracker:SetAlpha(0)
		tracker:Show()
	end
	local nativeAlpha, nativeShown = tracker:GetAlpha(), tracker:IsShown()
	sim:login({ savedVariables = { ForeverCoreDB = db } })
	local layouts = { layouts = {}, activeLayout = 1 }
	sim.impl["C_EditMode.GetLayouts"] = function()
		return layouts
	end
	sim:event("EDIT_MODE_LAYOUTS_UPDATED", layouts, false)
	-- Discard only the known missing player-frame and layout-dialog pieces of the simulated Edit Mode UI.
	for _, err in ipairs(sim:takeErrors()) do
		local trace = tostring(err.traceback)
		assert(
			trace:find("Blizzard_EditMode/Shared/EditModeSystemTemplates.lua:2453", 1, true)
				or trace:find("Blizzard_EditMode/Shared/EditModeSystemTemplates.lua:1844", 1, true)
				or trace:find("Blizzard_EditMode/Shared/EditModeManager.lua:729", 1, true),
			err.message
		)
	end
	sim:advance(0.5)
	assert(sim.G.ObjectiveTrackerFrame:IsInDefaultPosition(), "tracker participates in managed layout")
	local function ExpectManagedLayoutSecure()
		for _, object in ipairs({
			sim.G.RightManagedFrameContainer,
			sim.G.RightManagedFrameContainer.showingFrames,
			sim.G.ObjectiveTrackerFrame,
		}) do
			for key, info in pairs(sim.taint.slots[object] or {}) do
				assert(info.addon ~= ADDON, "managed slot tainted: " .. tostring(key))
			end
		end
		local frame = sim.G.CreateFrame("Frame", nil, sim.G.UIParent, "RightManagedFrameTemplate")
		frame:SetSize(50, 50)
		frame:Hide()
		frame:Show()
		sim:advance(0.5)
		for _, hit in ipairs(sim.taint.hits) do
			local managed = hit.table == sim.G.RightManagedFrameContainer
				or hit.table == sim.G.RightManagedFrameContainer.showingFrames
				or hit.table == sim.G.ObjectiveTrackerFrame
			assert(not managed or hit.addon ~= ADDON, "secure layout read a ForeverCore-tainted slot")
		end
	end
	-- A scenario update makes the client's own scenario module lay out, which reaches the Maw buff check. With the
	-- list on, nothing the list did may have tainted that pass.
	local function NativeUpdate()
		assert(sim.taint.current == nil, "native container update starts secure")
		tracker:Update()
	end
	if mode == "ellesmere" then
		assert(
			tracker:GetAlpha() == nativeAlpha and tracker:IsShown() == nativeShown,
			"core leaves Ellesmere's native tracker untouched at login"
		)
		assert(not sim.G.ForeverCoreQuestTracker:IsShown(), "the Forever section defers to Ellesmere")
	end
	local before = reads
	sim:event("QUEST_LOG_UPDATE")
	sim:event("SCENARIO_CRITERIA_UPDATE")
	NativeUpdate()
	sim:advance(0.5)
	ExpectAuraReadIsUntainted(sim, reads, before)
	ExpectManagedLayoutSecure()
	if mode == "disabled" or mode == "ellesmere" then
		assert(tracker:IsShown(), "native tracker stays shown with the column attached")
		assert(sim.G.ForeverCore.TrackerHost.IsAttachedToQuestTracker(), "the column stays attached")
		if mode == "ellesmere" then
			assert(tracker:GetAlpha() == 0, "Ellesmere's native alpha stays untouched")
		end
		return
	end
	assert(not tracker:IsShown(), "login with the Forever list hides the whole native tracker")

	-- Turning the list off and on changes only native frame visibility, leaving every module untouched.
	before = reads
	sim:slash("/fcore quests")
	assert(tracker:IsShown(), "turning the list off restores the native tracker")
	sim:advance(0.5)
	sim:event("QUEST_LOG_UPDATE")
	sim:event("SCENARIO_CRITERIA_UPDATE")
	NativeUpdate()
	sim:advance(0.5)
	ExpectAuraReadIsUntainted(sim, reads, before)
	ExpectManagedLayoutSecure()

	before = reads
	sim:slash("/fcore quests")
	assert(not tracker:IsShown(), "turning the list on hides the native tracker")
	sim:advance(0.5)
	sim:event("QUEST_LOG_UPDATE")
	sim:event("SCENARIO_CRITERIA_UPDATE")
	NativeUpdate()
	sim:advance(0.5)
	ExpectAuraReadIsUntainted(sim, reads, before)
	ExpectManagedLayoutSecure()
	tracker:Show()
	assert(tracker:GetAlpha() == 0, "a native OnShow attempt stays invisible")
	sim:advance(0.3)
	assert(not tracker:IsShown(), "the secure driver re-hides a native OnShow")
	before = reads
	NativeUpdate()
	sim:advance(0.5)
	ExpectAuraReadIsUntainted(sim, reads, before)
	ExpectManagedLayoutSecure()

	-- #686: Blizzard's container Update calls Show when it has content, including when a quest progresses in
	-- combat. The registered driver must re-hide it securely even while the frame is protected.
	local protectedChild = sim.G.CreateFrame("Button", nil, tracker, "SecureActionButtonTemplate")
	assert(protectedChild:IsProtected() and tracker:IsProtected(), "the native tracker is protected")
	sim:enterCombat()
	NativeUpdate()
	assert(tracker:IsShown() and tracker:GetAlpha() == 0, "a protected native combat layout stays invisible")
	sim:advance(0.3)
	assert(not tracker:IsShown(), "the secure driver re-hides the protected tracker during combat")
	ExpectManagedLayoutSecure()
	sim:leaveCombat()
	sim:advance(0.5)
	assert(not tracker:IsShown(), "combat ending finishes the native hide")

	sim:enterCombat()
	sim:slash("/fcore quests")
	assert(not tracker:IsShown(), "restore requested in combat waits")
	sim:slash("/fcore quests")
	sim:leaveCombat()
	sim:advance(0.5)
	assert(not tracker:IsShown(), "combat retry keeps the latest enabled request")

	sim:enterCombat()
	sim:slash("/fcore quests")
	assert(not tracker:IsShown(), "second combat restore waits")
	sim:leaveCombat()
	sim:advance(0.5)
	assert(tracker:IsShown(), "latest disabled request restores after combat")
	before = reads
	NativeUpdate()
	sim:advance(0.5)
	ExpectAuraReadIsUntainted(sim, reads, before)
	ExpectManagedLayoutSecure()
end

for _, mode in ipairs({ "enabled", "fresh", "disabled", "ellesmere" }) do
	scenario("native scenario aura reads stay untainted with quest list " .. mode, function(sim)
		Run(sim, mode)
	end)
end
