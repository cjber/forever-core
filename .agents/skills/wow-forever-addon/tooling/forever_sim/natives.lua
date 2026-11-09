-- Functions the client implements natively that Blizzard's Lua relies on from the first file it loads: mixins,
-- secure call helpers, secret helpers, curves, and the generic script objects documented APIs hand back.
local Secret = require("veil")

local M = {}

function M.build(sim)
	local G, Taint = sim.G, sim.taint
	local next_ = next

	local function mixin(object, ...)
		for i = 1, select("#", ...) do
			local m = select(i, ...)
			if type(m) == "table" then
				for k, v in next_, m do
					object[k] = v
				end
			end
		end
		return object
	end
	sim.impl.Mixin = mixin
	sim.impl.CreateFromMixins = function(...)
		return mixin({}, ...)
	end
	G.Mixin = mixin
	G.CreateFromMixins = sim.impl.CreateFromMixins
	G.GetCurrentEnvironment = function()
		return sim.env
	end
	G.SwapToGlobalEnvironment = function() end
	G.RegisterStaticConstants = function() end
	sim.impl.securecallmethod = function(object, method, ...)
		local f = rawget(object, method)
		if f == nil then
			local mt = getmetatable(object)
			local index = type(mt) == "table" and mt.__index
			f = type(index) == "table" and index[method] or nil
		end
		if type(f) ~= "function" then
			return
		end
		return Taint.securecall(f, object, ...)
	end
	local function deepcopy(v, seen)
		if type(v) ~= "table" then
			return v
		end
		seen = seen or {}
		if seen[v] then
			return seen[v]
		end
		local out = {}
		seen[v] = out
		for k, x in next_, v do
			out[deepcopy(k, seen)] = deepcopy(x, seen)
		end
		return out
	end
	sim.impl.securecopy = function(v)
		return deepcopy(v)
	end
	sim.impl.hasanysecretvalues = function(...)
		for i = 1, select("#", ...) do
			if Secret.is((select(i, ...))) then
				return true
			end
		end
		return false
	end
	sim.impl.secretunwrap = function(...)
		local out = { ... }
		for i = 1, select("#", ...) do
			out[i] = Secret.unwrap(out[i])
		end
		return unpack(out, 1, (select("#", ...)))
	end
	sim.impl.dropsecretaccess = function()
		if not Taint.current then
			Taint.set("*** dropsecretaccess ***")
		end
	end
	sim.impl.settablesecurity = function() end
	sim.impl.GetCallstackHeight = function()
		local level = 1
		while debug.getinfo(level + 1, "l") do
			level = level + 1
		end
		return level
	end
	sim.impl.GetSourceLocation = function()
		return nil
	end
	sim.impl.GetCurrentEventID = function()
		return sim.currentEventID or 0
	end
	sim.impl.GetEventTime = function()
		return 0, 0, 0
	end
	-- RegisterEventCallback: a frameless event listener.
	local callbackFrames = {}
	sim.impl.RegisterEventCallback = function(event, callback)
		local f = callbackFrames[callback]
		if not f then
			f = sim.templates.createFrame("Frame")
			callbackFrames[callback] = f
			f:SetScript("OnEvent", function(_, ...)
				callback(...)
			end)
		end
		f:RegisterEvent(event)
		return true
	end
	sim.impl.RegisterUnitEventCallback = function(event, callback)
		sim.impl.RegisterEventCallback(event, callback)
		return true
	end
	sim.impl.UnregisterEventCallback = function(event, callback)
		local f = callbackFrames[callback]
		if f then
			f:UnregisterEvent(event)
		end
	end
	sim.impl.UnregisterUnitEventCallback = sim.impl.UnregisterEventCallback
	sim.impl.CreateFrameWithOptions = function(options)
		options = options or {}
		return sim.templates.createFrame(
			options.frameType or "Frame",
			options.name,
			options.parent,
			options.template,
			options.id
		)
	end

	-- The widget metatables (GetFrameMetatable and friends), for code that calls the native method directly.
	for _, kind in ipairs({ "Frame", "Button", "EditBox", "FontString", "Texture", "CheckButton", "StatusBar" }) do
		G["Get" .. kind .. "Metatable"] = function()
			return sim.widgets.metas[kind]
		end
	end
	sim.impl["C_EventUtils.IsEventValid"] = function(event)
		return sim.knownEvent(event) and true or false
	end
	-- import(".Module"): the value a file of the calling addon returned (Blizzard_GamepadSmartNavigation).
	sim.modules = {}
	G.import = function(name)
		local source = debug.getinfo(2, "S").source
		local folder, dir = source:match("^@([^/]+)/(.*/)[^/]*$")
		folder = folder or source:match("^@([^/]+)/")
		local module = name:gsub("^%.", "")
		local loaded = sim.modules[folder or ""] or {}
		local value = loaded[module]
		if value == nil and dir and dir ~= "" then
			value = loaded[dir:gsub("/", ".") .. module]
		end
		if value == nil then
			error(string.format("import(): module '%s' not found in %s", name, folder or ""), 2)
		end
		return value
	end

	-- Chat's slash command tables (native in the client) and gamepad cursor natives.
	G.SlashCmdList = G.SlashCmdList or {}
	G.hash_SlashCmdList = G.hash_SlashCmdList or {}
	G.hash_ChatTypeInfoList = G.hash_ChatTypeInfoList or {}
	G.CanAutoSetGamePadCursorControl = function()
		return false
	end
	G.SetGamePadCursorControl = function() end
	G.IsGamePadCursorControlEnabled = function()
		return false
	end
	G.IsGamePadFreelookEnabled = function()
		return false
	end
	G.SetGamePadFreeLook = function() end
	G.GetChannelList = function() end
	-- DisplayInterfaceActionBlockedMessage mirrors Blizzard_ChatFrameBase/Shared/ChatFrameUtil.lua: it adds
	-- INTERFACE_ACTION_BLOCKED as a system chat line, once, then replaces itself with a no-op. The sim keeps chat
	-- output on DEFAULT_CHAT_FRAME, as that file's ChatFrameUtil.AddSystemMessage does. Blizzard_ChatFrameBase
	-- cannot boot here (it needs the whole chat frame), so the one function the panel manager calls lives here.
	G.DisplayInterfaceActionBlockedMessage = function()
		local chat = G.DEFAULT_CHAT_FRAME
		if chat then
			chat:AddMessage(G.INTERFACE_ACTION_BLOCKED)
		end
		G.DisplayInterfaceActionBlockedMessage = function() end
	end
	-- Kiosk (event demo) mode: off. A native table the UI checks everywhere.
	G.Kiosk = G.Kiosk
		or setmetatable({}, {
			__index = function()
				return function()
					return false
				end
			end,
		})
	-- Legacy action-bar natives the gamepad action bars' OnLoad reads; the sim has no spells or actions.
	for _, entry in ipairs({
		{
			"GetActionInfo",
			function()
				return nil
			end,
		},
		{
			"GetActionTexture",
			function()
				return nil
			end,
		},
		{
			"GetActionText",
			function()
				return nil
			end,
		},
		{
			"GetActionCooldown",
			function()
				return 0, 0
			end,
		},
		{
			"GetActionCharges",
			function()
				return 0, 0
			end,
		},
		{
			"GetActionCount",
			function()
				return 0
			end,
		},
		{
			"IsActionInRange",
			function()
				return 1
			end,
		},
		{
			"IsUsableAction",
			function()
				return 1
			end,
		},
		{
			"HasAction",
			function()
				return false
			end,
		},
		{
			"ActionHasRange",
			function()
				return false
			end,
		},
		{
			"GetActionBarPage",
			function()
				return 1
			end,
		},
		{
			"GetBonusBarOffset",
			function()
				return 0
			end,
		},
		{
			"GetNumActionBars",
			function()
				return 1
			end,
		},
		{
			"GetActionLossOfControlCooldown",
			function()
				return 0, 0
			end,
		},
		{
			"GetPetActionInfo",
			function()
				return nil
			end,
		},
		{
			"GetPetActionCooldown",
			function()
				return 0, 0, 0
			end,
		},
		{
			"GetPetActionSlotUsable",
			function()
				return false
			end,
		},
		{
			"GetNumPetActionSlots",
			function()
				return 0
			end,
		},
		{
			"HasPetUI",
			function()
				return false, false
			end,
		},
		{
			"GetPetActionsEnabled",
			function()
				return false
			end,
		},
		{
			"GetFlyoutInfo",
			function()
				return nil
			end,
		},
		{
			"GetFlyoutSlotInfo",
			function()
				return nil
			end,
		},
		{
			"GetNumFlyouts",
			function()
				return 0
			end,
		},
		{
			"GetNumBindings",
			function()
				return 0
			end,
		},
		{
			"IsModifiedClick",
			function()
				return false
			end,
		},
		{
			"GetMerchantNumItems",
			function()
				return 0
			end,
		},
		{
			"GetNumSpecializations",
			function()
				return 0
			end,
		},
		{
			"GetTrainerServiceStepIndex",
			function()
				return 0
			end,
		},
		{
			"InRepairMode",
			function()
				return false
			end,
		},
		{
			"GetPlayerTradeMoney",
			function()
				return 0
			end,
		},
		{
			"GetTargetTradeMoney",
			function()
				return 0
			end,
		},
		{
			"GetNumQuestLogEntries",
			function()
				return 0
			end,
		},
		{
			"CanAffordMerchantItem",
			function()
				return true
			end,
		},
		{
			"GetMerchantFilter",
			function()
				return nil
			end,
		},
		{
			"CloseMerchant",
			function() end,
		},
		{
			"GetNumTrainerServices",
			function()
				return 0
			end,
		},
		{
			"GetTrainerServiceInfo",
			function()
				return nil
			end,
		},
		{
			"GetTrainerServiceCost",
			function()
				return nil
			end,
		},
		{
			"GetTrainerServiceSkillReq",
			function()
				return nil
			end,
		},
		{
			"GetTrainerServiceDescription",
			function()
				return nil
			end,
		},
		{
			"GetTrainerServiceTypeFilter",
			function()
				return false
			end,
		},
		{
			"GetTrainerServiceNumAbilityReq",
			function()
				return 0
			end,
		},
		{
			"GetTrainerServiceAbilityReq",
			function()
				return nil
			end,
		},
		{
			"SetTrainerServiceTypeFilter",
			function() end,
		},
		{
			"ExpandTrainerSkillLine",
			function() end,
		},
		{
			"GetTrainerTradeskillRankValues",
			function()
				return 0, 0, 0
			end,
		},
		{
			"GetTrainerSkillLineFilter",
			function()
				return false
			end,
		},
		{
			"SetTrainerSkillLineFilter",
			function() end,
		},
		{
			"GetTrainerServiceIcon",
			function()
				return nil
			end,
		},
		{
			"CloseTrainer",
			function() end,
		},
		{
			"BuyTrainerService",
			function() end,
		},
		{
			"ActionBarController_UpdateAllSpellHighlights",
			function() end,
		},
		{
			"SecureButton_GetEffectiveButton",
			function()
				return "LeftButton"
			end,
		},
		{
			"SecureButton_GetModifiedUnit",
			function()
				return nil
			end,
		},
		{
			"SecureButton_GetModifierPrefix",
			function()
				return nil
			end,
		},
		{
			"SecureButton_GetButtonSuffix",
			function()
				return nil
			end,
		},
		{
			"SecureButton_GetAttribute",
			function()
				return nil
			end,
		},
		{
			"SecureButton_GetModifiedAttribute",
			function()
				return nil
			end,
		},
		{
			"SecureButton_GetUnit",
			function()
				return nil
			end,
		},
		{
			"SecureButton_GetAction",
			function()
				return nil
			end,
		},
		{
			"SecureButton_GetSpell",
			function()
				return nil
			end,
		},
		{
			"SecureButton_GetItem",
			function()
				return nil
			end,
		},
		{
			"SecureButton_GetTarget",
			function()
				return nil
			end,
		},
		{
			"SecureButton_GetMacro",
			function()
				return nil
			end,
		},
		{
			"SecureCmdOptionParse",
			function()
				return nil
			end,
		},
		{
			"StoreFrame_IsShown",
			function()
				return false
			end,
		},
		{
			"GetGuildLogoInfo",
			function()
				return nil
			end,
		},
		{
			"GetGuildLogoTexture",
			function()
				return nil
			end,
		},
		{
			"GetGuildInfo",
			function()
				return nil
			end,
		},
		{
			"GetGuildRosterMOTD",
			function()
				return nil
			end,
		},
		{
			"GetGuildRosterInfo",
			function()
				return nil
			end,
		},
		{
			"HasCompletedAnyAchievement",
			function()
				return false
			end,
		},
		{
			"HasCompletedAnyAchievementForAccount",
			function()
				return false
			end,
		},
		{
			"IsAchievementEligible",
			function()
				return false
			end,
		},
		{
			"GetNumGuildMembers",
			function()
				return 0
			end,
		},
		{
			"GetGuildRosterShowOffline",
			function()
				return false
			end,
		},
		{
			"IsCommunitiesUIDisabledByTrialAccount",
			function()
				return false
			end,
		},
	}) do
		if G[entry[1]] == nil then
			G[entry[1]] = entry[2]
		end
	end
	G.addframetext = function() end
	-- FrameXML's movie frames are not booted; Blizzard_Gamepad's cinematic setup assigns handler methods to them.
	G.MovieFrame = G.MovieFrame or {}
	G.CinematicFrame = G.CinematicFrame or {}
	-- Unit frames are not booted; the character panel's OnHide clears a flag on these bars.
	G.PlayerFrameHealthBar = G.PlayerFrameHealthBar or {}
	G.PlayerFrameManaBar = G.PlayerFrameManaBar or {}
	G.PlayerFrameAlternatePowerBar = G.PlayerFrameAlternatePowerBar or {}
	G.PetFrameHealthBar = G.PetFrameHealthBar or {}
	G.PetFrameManaBar = G.PetFrameManaBar or {}
	G.PlayerFrame_GetHealthBar = function()
		return G.PlayerFrameHealthBar
	end
	G.PlayerFrame_GetManaBar = function()
		return G.PlayerFrameManaBar
	end
	G.PlayerFrame_GetAlternatePowerBar = function()
		return G.PlayerFrameAlternatePowerBar
	end
	-- FunctionUtil's next-frame helper: callbacks run after the current frame, as C_Timer.After(0) does.
	G.RunNextFrame = function(callback)
		sim.impl["C_Timer.After"](0, callback)
	end
	G.RunOnNextFrame = G.RunNextFrame
	-- Empty quest fixtures still use the native quest-map refresh and sorting entry points.
	G.SortQuestSortTypes = function() end
	G.SortQuests = function() end
	G.QuestMapUpdateAllQuests = function()
		return 0
	end
	G.QuestPOIUpdateIcons = function() end
	-- The quest log's header collapse/expand, which the quest map calls while it refreshes its filters.
	G.ExpandQuestHeader = function() end
	G.CollapseQuestHeader = function() end
	-- The FrameXML-era quest-log natives the client implements in C: Blizzard's tracker and quest map read them, and
	-- the documentation does not list them. A scenario answers through sim.impl when it has objectives to show.
	local function questNative(name, default)
		G[name] = function(...)
			local f = sim.impl[name]
			if f then
				return f(...)
			end
			return default
		end
	end
	questNative("GetNumQuestLeaderBoards", 0)
	questNative("GetQuestLogLeaderBoard", nil)
	questNative("GetQuestLogCompletionText", nil)
	questNative("IsQuestSequenced", false)
	-- The quest's special item, if any. Blizzard's tracker asks before it makes the item button; no item means none.
	questNative("GetQuestLogSpecialItemInfo", nil)
	-- The item button's cooldown and range checks; the client answers no cooldown and out of range.
	questNative("GetQuestLogSpecialItemCooldown", nil)
	questNative("IsQuestLogSpecialItemInRange", 0)
	-- The bonus objectives table: the sim's player has none.
	G.GetTasksTable = function()
		return {}
	end
	-- Auto quest pop-ups: none.
	questNative("GetNumAutoQuestPopUps", 0)
	-- No scenario: no stages. The tracker compares the count GetInfo returns.
	G.C_Scenario = G.C_Scenario or {}
	G.C_Scenario.GetInfo = function()
		return nil, nil, 0
	end
	G.SpellCanTargetQuest = function()
		return false
	end
	G.SpellIsTargeting = function()
		return false
	end
	-- Undocumented legacy native the client's bag frames read: the sim's player carries no profession bags.
	G.IsInventoryItemProfessionBag = function()
		return false
	end
	G.SpellCanTargetItem = function()
		return false
	end
	G.SpellStopTargeting = function() end
	G.debuglocals = function()
		return ""
	end
	G.GetNumBattlefieldFlagPositions = function()
		return 0
	end
	G.GetNumBattlefieldVehicles = function()
		return 0
	end
	G.GetNumDisplayChannels = function()
		return 0
	end

	-- Functions from Blizzard addons the sim does not boot (sim.SKIP_DEPS) that booted UI calls while loading;
	-- each is recorded in sim.gaps when called.
	for _, name in ipairs({
		"PaperDollItemSlotButton_OnLoad",
		"PaperDollItemSlotButton_Update",
		"PaperDollItemSlotButton_SetAutoEquipSlotIDs",
		"PaperDollItemSlotButton_OnShow",
		"PaperDollItemSlotButton_OnHide",
		"PaperDollItemSlotButton_OnEvent",
		"PaperDollItemSlotButton_OnEnter",
		"PaperDollItemSlotButton_OnClick",
		"MicroButtonPulseStop",
		"MultiActionBar_ShowAllGrids",
		"MultiActionBar_HideAllGrids",
		"UpdateMicroButtons",
		"MainMenuMicroButton_HideAlert",
		"MainMenuMicroButton_ShowAlert",
		"MicroButtonPulse",
	}) do
		if G[name] == nil then
			G[name] = function()
				sim.gaps["shim " .. name] = true
			end
		end
	end

	-- The client's extensions to math, string and table (documented; implemented here).
	local I = sim.impl
	local function round(x)
		if x < 0 then
			return math.ceil(x - 0.5)
		end
		return math.floor(x + 0.5)
	end
	local function clamp(v, lo, hi)
		return math.min(math.max(v, lo), hi)
	end
	local mathExt = {
		round = round,
		clamp = clamp,
		saturate = function(v)
			return clamp(v, 0, 1)
		end,
		isnan = function(v)
			return v ~= v
		end,
		isinf = function(v)
			return v == math.huge or v == -math.huge
		end,
		isfinite = function(v)
			return v == v and v ~= math.huge and v ~= -math.huge
		end,
		lerp = function(a, b, t)
			return a + (b - a) * t
		end,
		normalize = function(v, lo, hi)
			if hi == lo then
				return 0
			end
			return (v - lo) / (hi - lo)
		end,
		remap = function(v, a, b, c, d)
			if b == a then
				return c
			end
			return c + (v - a) / (b - a) * (d - c)
		end,
		sign = function(v)
			return v > 0 and 1 or (v < 0 and -1 or 0)
		end,
		wrap = function(v, lo, hi)
			if hi == lo then
				return lo
			end
			return lo + (v - lo) % (hi - lo)
		end,
	}
	for k, f in pairs(mathExt) do
		I["math." .. k] = Secret.lift(f)
		G.math[k] = I["math." .. k]
	end
	local function trimSet(chars)
		return chars and ("[" .. chars:gsub("[%^%]%-%%]", "%%%0") .. "]") or "%s"
	end
	local stringExt = {
		ltrim = function(s, chars)
			return (s:gsub("^" .. trimSet(chars) .. "+", ""))
		end,
		rtrim = function(s, chars)
			return (s:gsub(trimSet(chars) .. "+$", ""))
		end,
		trim = function(s, chars)
			local set = trimSet(chars)
			return (s:gsub("^" .. set .. "+", ""):gsub(set .. "+$", ""))
		end,
		contains = function(s, sub)
			return s:find(sub, 1, true) ~= nil
		end,
		startswith = function(s, prefix)
			return s:sub(1, #prefix) == prefix
		end,
		endswith = function(s, suffix)
			return suffix == "" or s:sub(-#suffix) == suffix
		end,
	}
	for k, f in pairs(stringExt) do
		I["string." .. k] = Secret.lift(f)
		G.string[k] = I["string." .. k]
	end
	local tableExt = {
		contains = function(t, v)
			for _, x in next_, t do
				if x == v then
					return true
				end
			end
			return false
		end,
		count = function(t)
			local n = 0
			for _ in next_, t do
				n = n + 1
			end
			return n
		end,
		create = function()
			return {}
		end,
		indexof = function(t, v)
			for i, x in ipairs(t) do
				if x == v then
					return i
				end
			end
		end,
		freeze = function(t)
			return t
		end,
		isfrozen = function()
			return false
		end,
		keys = function(t)
			local out = {}
			for k in next_, t do
				out[#out + 1] = k
			end
			return out
		end,
		values = function(t)
			local out = {}
			for _, v in next_, t do
				out[#out + 1] = v
			end
			return out
		end,
		isempty = function(t)
			return next_(t) == nil
		end,
		getcountinfo = function(t)
			local n, ints, maxInt = 0, 0, 0
			for k in next_, t do
				n = n + 1
				if type(k) == "number" and k > 0 and k % 1 == 0 then
					ints = ints + 1
					maxInt = math.max(maxInt, k)
				end
			end
			return n, ints, maxInt
		end,
		removeunordered = function(t, i)
			local n = #t
			i = i or n
			if i < 1 or i > n then
				return nil
			end
			local v = t[i]
			t[i] = t[n]
			t[n] = nil
			return v
		end,
		removevalue = function(t, v)
			local removed = 0
			for i = #t, 1, -1 do
				if t[i] == v then
					table.remove(t, i)
					removed = removed + 1
				end
			end
			return removed
		end,
	}
	for k, f in pairs(tableExt) do
		I["table." .. k] = f
		G.table[k] = f
	end

	-- Curves (C_CurveUtil): piecewise linear, enough for Blizzard's percentage curves.
	local curveMethods = {}
	curveMethods.__index = curveMethods
	function curveMethods:AddPoint(x, y)
		table.insert(self.points, { x, y })
		table.sort(self.points, function(a, b)
			return a[1] < b[1]
		end)
	end
	function curveMethods:ClearPoints()
		self.points = {}
	end
	function curveMethods:SetType(t)
		self.type = t
	end
	function curveMethods:GetType()
		return self.type or 0
	end
	function curveMethods:GetPointCount()
		return #self.points
	end
	function curveMethods:GetPoint(i)
		local p = self.points[i]
		if p then
			return p[1], p[2]
		end
	end
	function curveMethods:Copy()
		local c = setmetatable({ points = {}, type = self.type }, curveMethods)
		for _, p in ipairs(self.points) do
			c.points[#c.points + 1] = { p[1], p[2] }
		end
		return c
	end
	function curveMethods:Evaluate(x)
		local secret = Secret.is(x)
		x = Secret.unwrap(x)
		local pts = self.points
		local y = 0
		if #pts == 1 then
			y = pts[1][2]
		elseif #pts > 1 then
			if x <= pts[1][1] then
				y = pts[1][2]
			elseif x >= pts[#pts][1] then
				y = pts[#pts][2]
			else
				for i = 2, #pts do
					local a, b = pts[i - 1], pts[i]
					if x <= b[1] then
						y = a[2] + (b[2] - a[2]) * (x - a[1]) / (b[1] - a[1])
						break
					end
				end
			end
		end
		return secret and Secret.wrap(y) or y
	end
	function curveMethods:GetPoints()
		return self.points
	end
	sim.impl["C_CurveUtil.CreateCurve"] = function()
		return setmetatable({ points = {} }, curveMethods)
	end
	sim.impl["C_CurveUtil.CreateColorCurve"] = function()
		return setmetatable({ points = {} }, curveMethods)
	end
end

return M
