-- The client's native side: the global table and Lua builtins the game provides, the root frames, events,
-- timers and OnUpdate, CVars, the error handler, and ADDON_ACTION_BLOCKED / ADDON_ACTION_FORBIDDEN.
local Secret = require("veil")

local M = {}

local function strsplit(delimiter, text, pieces)
	text = Secret.unwrap(text)
	if text == nil then
		return nil
	end
	local out = {}
	local pattern = "([^" .. delimiter:gsub("[%^%]%-%%]", "%%%0") .. "]*)"
	local pos = 1
	local count = 0
	while true do
		count = count + 1
		if pieces and count >= pieces then
			out[#out + 1] = text:sub(pos)
			break
		end
		local s, e = text:find("[" .. delimiter:gsub("[%^%]%-%%]", "%%%0") .. "]", pos)
		if not s then
			out[#out + 1] = text:sub(pos)
			break
		end
		out[#out + 1] = text:sub(pos, s - 1)
		pos = e + 1
	end
	local _ = pattern
	return unpack(out)
end

local function strtrim(s, chars)
	s = Secret.unwrap(s)
	if not chars then
		return (s:gsub("^%s+", ""):gsub("%s+$", ""))
	end
	local set = "[" .. chars:gsub("[%^%]%-%%]", "%%%0") .. "]"
	return (s:gsub("^" .. set .. "+", ""):gsub(set .. "+$", ""))
end

local function wipe(t)
	for k in pairs(t) do
		t[k] = nil
	end
	return t
end

function M.build(sim)
	local G = {}
	sim.G = G
	for _, k in ipairs({
		"assert",
		"error",
		"getmetatable",
		"ipairs",
		"next",
		"pairs",
		"pcall",
		"print",
		"rawequal",
		"rawget",
		"rawset",
		"select",
		"setmetatable",
		"tonumber",
		"tostring",
		"type",
		"unpack",
		"xpcall",
		"getfenv",
		"setfenv",
		"loadstring",
		"collectgarbage",
		"gcinfo",
		"newproxy",
	}) do
		G[k] = _G[k]
	end
	local function copy(t)
		local out = {}
		for k, v in pairs(t) do
			out[k] = v
		end
		return out
	end
	G.string, G.table, G.math, G.coroutine = copy(string), copy(table), copy(math), copy(coroutine)
	G.bit = copy(require("bit"))
	G.os = { time = os.time, date = os.date, clock = os.clock, difftime = os.difftime }
	G.debug = { traceback = debug.traceback, getinfo = debug.getinfo }
	G.print = function(...)
		local parts = {}
		for i = 1, select("#", ...) do
			parts[i] = tostring(Secret.unwrap((select(i, ...))))
		end
		table.insert(sim.printed, table.concat(parts, " "))
	end
	G.table.wipe = wipe
	G.wipe = wipe
	G.table.removemulti = function(t, pos, count)
		for _ = 1, count or 1 do
			table.remove(t, pos)
		end
	end
	G.table.count = function(t)
		local n = 0
		for _ in pairs(t) do
			n = n + 1
		end
		return n
	end
	G.table.create = function()
		return {}
	end
	G.string.split = strsplit
	G.string.trim = strtrim
	G.string.join = function(sep, ...)
		return table.concat({ ... }, sep)
	end
	G.strsplit = strsplit
	G.strsplittable = function(delimiter, text, pieces)
		return { strsplit(delimiter, text, pieces) }
	end
	G.strtrim = strtrim
	G.strjoin = G.string.join
	G.strconcat = function(...)
		return table.concat({ ... })
	end
	G.strlenutf8 = function(s)
		local _, n = tostring(s):gsub("[^\128-\191]", "")
		return n
	end
	G.strcmputf8i = function(a, b)
		a, b = tostring(a):lower(), tostring(b):lower()
		return a < b and -1 or (a > b and 1 or 0)
	end
	G.debugstack = function()
		return debug.traceback("", 2)
	end
	G.debugprofilestop = function()
		return os.clock() * 1000
	end
	G.debugprofilestart = function() end
	G.GetTime = function()
		return sim.time
	end
	G.GetTimePreciseSec = G.GetTime
	G.GetServerTime = function()
		return math.floor(sim.epoch + sim.time)
	end
	G.time = function(t)
		if t then
			return os.time(t)
		end
		return math.floor(sim.epoch + sim.time)
	end
	G.date = function(fmt, t)
		return os.date(fmt, t or math.floor(sim.epoch + sim.time))
	end

	local Taint = sim.taint
	sim.env = Taint.environment(G)
	G._G = sim.env
	Secret.install(G)
	Taint.install(G, sim.env)
	-- The client's global aliases for the (secret-aware) libraries.
	local s, t, m = G.string, G.table, G.math
	local aliases = {
		strlen = s.len,
		strsub = s.sub,
		strfind = s.find,
		strmatch = s.match,
		gsub = s.gsub,
		gmatch = s.gmatch,
		format = s.format,
		strupper = s.upper,
		strlower = s.lower,
		strrep = s.rep,
		strbyte = s.byte,
		strchar = s.char,
		strrev = s.reverse,
		tinsert = t.insert,
		tremove = t.remove,
		sort = t.sort,
		floor = m.floor,
		ceil = m.ceil,
		abs = m.abs,
		max = m.max,
		min = m.min,
		mod = m.fmod,
		sqrt = m.sqrt,
		exp = m.exp,
		log = m.log,
		log10 = m.log10,
		frexp = m.frexp,
		ldexp = m.ldexp,
		random = m.random,
		fastrandom = m.random,
		deg = m.deg,
		rad = m.rad,
		sin = function(x)
			return math.sin(math.rad(x))
		end,
		cos = function(x)
			return math.cos(math.rad(x))
		end,
		tan = function(x)
			return math.tan(math.rad(x))
		end,
		asin = function(x)
			return math.deg(math.asin(x))
		end,
		acos = function(x)
			return math.deg(math.acos(x))
		end,
		atan = function(x)
			return math.deg(math.atan(x))
		end,
		atan2 = function(y, x)
			return math.deg(math.atan2(y, x))
		end,
		PI = math.pi,
	}
	for k, v in pairs(aliases) do
		G[k] = v
	end

	---------------------------------------------------------------------------
	-- Errors
	---------------------------------------------------------------------------
	sim.errors = {}
	sim.printed = {}
	local handler
	function sim.reportError(message, traceback, taint)
		message = tostring(Secret.unwrap(message))
		if taint and message:find("attempt to compare %a+ with %a+") and message:find("userdata") then
			-- A secret on one side of an ordering comparison: Lua 5.1 reports the types, the client the secret.
			message = message:gsub(
				"attempt to compare %a+ with %a+",
				string.format("attempt to compare a secret value (execution tainted by '%s')", taint)
			)
		end
		local entry = { message = message, traceback = traceback or "", taint = taint, time = sim.time }
		table.insert(sim.errors, entry)
		if handler then
			pcall(handler, message)
		end
		if sim.verbose then
			io.stderr:write("[sim error] ", message, "\n", traceback or "", "\n")
		end
	end
	Taint.onError = sim.reportError
	G.geterrorhandler = function()
		return handler or function(msg)
			sim.reportError(msg, debug.traceback("", 2), Taint.current)
		end
	end
	G.seterrorhandler = function(f)
		handler = f
	end
	G.CallErrorHandler = function(...)
		return G.geterrorhandler()(...)
	end

	-- Runs f as a fresh client dispatch (secure), reporting errors; returns true when it did not error.
	function sim.run(f, ...)
		local ok = Taint.dispatch(nil, f, ...)
		return ok
	end

	---------------------------------------------------------------------------
	-- Protected actions
	---------------------------------------------------------------------------
	sim.actions = {}
	local function actionEvent(event, what)
		local addon = Taint.current
		local entry = { event = event, addon = addon, func = what, traceback = debug.traceback("", 3) }
		table.insert(sim.actions, entry)
		sim.reportError(
			string.format("[%s] AddOn '%s' tried to call the protected function '%s'.", event, tostring(addon), what),
			entry.traceback,
			addon
		)
		if sim.events then
			sim.events.queue(event, addon, what)
		end
	end
	function sim.blocked(frame, method)
		local name = frame and frame.GetDebugName and frame:GetDebugName() or "UNKNOWN"
		actionEvent("ADDON_ACTION_BLOCKED", string.format("%s:%s()", name, method))
	end
	-- A protected function called by tainted code. The client reports ADDON_ACTION_BLOCKED for these (the
	-- message players see: "AddOn 'X' tried to call the protected function 'F()'").
	function sim.forbidden(func)
		actionEvent("ADDON_ACTION_BLOCKED", func .. "()")
	end
	-- Global protected functions the documentation does not mark (FrameXML-era API).
	sim.protectedGlobals = {
		"SetPreferredGamepadInteractTarget",
		"CastSpellByName",
		"CastSpellByID",
		"CastSpell",
		"UseAction",
		"UseContainerItem",
		"TargetUnit",
		"AssistUnit",
		"FocusUnit",
		"ClearTarget",
		"TargetNearestEnemy",
		"TargetLastTarget",
		"RunMacro",
		"RunMacroText",
		"SpellStopCasting",
		"PetAttack",
		"JumpOrAscendStart",
		"MoveForwardStart",
		"ToggleRun",
		"Logout",
		"Quit",
	}

	---------------------------------------------------------------------------
	-- Events
	---------------------------------------------------------------------------
	local E = { registered = {}, order = {}, pending = {} }
	sim.events = E
	local regSeq = 0
	function E.register(frame, event)
		E.registered[event] = E.registered[event] or {}
		if not E.registered[event][frame] then
			regSeq = regSeq + 1
			E.registered[event][frame] = regSeq
		end
	end
	function E.unregister(frame, event)
		if E.registered[event] then
			E.registered[event][frame] = nil
		end
	end
	function E.listeners(event)
		local list = {}
		for _, set in ipairs({ E.registered[event] or {}, E.registered["*"] or {} }) do
			for frame, seq in pairs(set) do
				list[#list + 1] = { frame, seq }
			end
		end
		table.sort(list, function(a, b)
			return a[2] < b[2]
		end)
		local out = {}
		for i, item in ipairs(list) do
			out[i] = item[1]
		end
		return out
	end
	-- Fires an event the way the client does: each registered frame's OnEvent in its own secure dispatch.
	function E.fire(event, ...)
		for _, frame in ipairs(E.listeners(event)) do
			local st = sim.widgets.state[frame]
			if st and st.events and (st.events[event] or st.allEvents) then
				local unitFilter = st.unitEvents and st.unitEvents[event]
				local unit = ...
				local pass = true
				if unitFilter and #unitFilter > 0 then
					pass = false
					for _, u in ipairs(unitFilter) do
						if u == unit then
							pass = true
						end
					end
				end
				if pass then
					sim.widgets.dispatch(frame, "OnEvent", event, ...)
				end
			end
		end
		if sim.onEvent then
			sim.onEvent(event, ...)
		end
	end
	function E.queue(event, ...)
		table.insert(E.pending, { n = select("#", ...) + 1, event, ... })
	end
	function E.flush()
		while #E.pending > 0 do
			local item = table.remove(E.pending, 1)
			E.fire(unpack(item, 1, item.n))
		end
	end
	-- Documented events, the FrameXML-era ones, and any Blizzard's own Lua names (client code may register
	-- any of those; addon code too).
	function sim.knownEvent(event)
		return sim.api.events[event] or sim.extraEvents[event] or sim.api.blizzardEvents[event] or false
	end
	-- Events the client fires that the documentation does not list (FrameXML-era).
	sim.extraEvents = {}
	for _, e in ipairs({
		"ADDON_LOADED",
		"VARIABLES_LOADED",
		"PLAYER_LOGIN",
		"PLAYER_LOGOUT",
		"PLAYER_ENTERING_WORLD",
		"PLAYER_LEAVING_WORLD",
		"PLAYER_REGEN_DISABLED",
		"PLAYER_REGEN_ENABLED",
		"ADDON_ACTION_BLOCKED",
		"ADDON_ACTION_FORBIDDEN",
		"SPELLS_CHANGED",
		"UI_SCALE_CHANGED",
		"DISPLAY_SIZE_CHANGED",
		"CVAR_UPDATE",
		"UPDATE_BINDINGS",
	}) do
		sim.extraEvents[e] = true
	end

	---------------------------------------------------------------------------
	-- Timers and OnUpdate
	---------------------------------------------------------------------------
	sim.time = 1000
	sim.epoch = 1760000000 - 1000
	sim.timers = {}
	sim.animations = {}
	local timerSeq = 0
	local function addTimer(seconds, callback, iterations, handle)
		timerSeq = timerSeq + 1
		local timer = {
			due = sim.time + math.max(0, tonumber(Secret.unwrap(seconds)) or 0),
			interval = math.max(0, tonumber(Secret.unwrap(seconds)) or 0),
			callback = callback,
			iterations = iterations,
			seq = timerSeq,
			taint = Taint.current,
			handle = handle,
		}
		table.insert(sim.timers, timer)
		return timer
	end
	local tickerMeta = {
		__index = {
			Cancel = function(self)
				self._cancelled = true
			end,
			IsCancelled = function(self)
				return self._cancelled == true
			end,
		},
	}
	sim.impl["C_Timer.After"] = function(seconds, callback)
		addTimer(seconds, callback, 1)
	end
	sim.impl["C_Timer.NewTimer"] = function(seconds, callback)
		local handle = setmetatable({}, tickerMeta)
		addTimer(seconds, function()
			callback(handle)
		end, 1, handle)
		return handle
	end
	sim.impl["C_Timer.NewTicker"] = function(seconds, callback, iterations)
		local handle = setmetatable({}, tickerMeta)
		addTimer(seconds, function()
			callback(handle)
		end, iterations, handle)
		return handle
	end

	-- Advances the clock by dt seconds in steps of at most `step`: timers, animations, OnUpdate.
	function sim.step(dt, step)
		step = step or 0.05
		local remaining = dt or 0
		repeat
			local d = math.min(step, remaining)
			remaining = remaining - d
			sim.time = sim.time + d
			-- Timers due now, in order.
			table.sort(sim.timers, function(a, b)
				if a.due == b.due then
					return a.seq < b.seq
				end
				return a.due < b.due
			end)
			local due = {}
			local keep = {}
			for _, timer in ipairs(sim.timers) do
				if timer.due <= sim.time + 1e-9 then
					due[#due + 1] = timer
				else
					keep[#keep + 1] = timer
				end
			end
			sim.timers = keep
			for _, timer in ipairs(due) do
				if not (timer.handle and timer.handle._cancelled) then
					Taint.dispatch(timer.taint, timer.callback)
					if timer.iterations ~= 1 and not (timer.handle and timer.handle._cancelled) then
						timer.iterations = timer.iterations and timer.iterations - 1
						timer.due = sim.time + math.max(timer.interval, 0.001)
						table.insert(sim.timers, timer)
					end
				end
			end
			sim.widgets.tickAnimations(d)
			-- The client fires OnSizeChanged when a frame's laid-out size changes, anchors included.
			sim.widgets.sizePass()
			-- OnUpdate for every visible frame that has one.
			local S = sim.widgets.state
			for _, frame in ipairs(sim.widgets.all) do
				local st = S[frame]
				if st.scripts and (st.scripts.OnUpdate or (st.hooks and st.hooks.OnUpdate)) then
					if sim.widgets.isVisible(frame) then
						sim.widgets.dispatch(frame, "OnUpdate", d)
					end
				end
			end
			E.flush()
		until remaining <= 0
	end

	---------------------------------------------------------------------------
	-- Root frames and CreateFrame
	---------------------------------------------------------------------------
	sim.screenWidth, sim.screenHeight = 1366, 768
	function sim.createRoots()
		local W = sim.widgets
		local root = W.new("Frame", "UIParent", nil, { source = "C" })
		W.state[root].width, W.state[root].height = sim.screenWidth, sim.screenHeight
		W.setRoot(root)
		local world = W.new("Frame", "WorldFrame", nil, { source = "C" })
		W.state[world].points = {}
		W.setPoint(world, "TOPLEFT", root, "TOPLEFT", 0, 0)
		W.setPoint(world, "BOTTOMRIGHT", root, "BOTTOMRIGHT", 0, 0)
		W.state[world].width, W.state[world].height = sim.screenWidth, sim.screenHeight
		Taint.globalTaint.UIParent, Taint.globalTaint.WorldFrame = nil, nil
	end
	-- The default chat frame (Blizzard_ChatFrame is not booted): AddMessage lines are kept in sim.chat.
	sim.chat = {}
	function sim.createChat()
		local chat = sim.templates.createFrame("Frame", "ChatFrame1", sim.widgets.root())
		chat.AddMessage = function(_, text)
			table.insert(sim.chat, tostring(Secret.unwrap(text)))
		end
		chat.Clear = function() end
		chat.GetNumMessages = function()
			return #sim.chat
		end
		G.DEFAULT_CHAT_FRAME = chat
		G.SELECTED_CHAT_FRAME = chat
		G.NUM_CHAT_WINDOWS = 1
		Taint.globalTaint.ChatFrame1 = nil
		-- Micro menu buttons other UI pulses (Blizzard_MicroMenu is not booted).
		for _, name in ipairs({
			"ProfessionMicroButton",
			"CharacterMicroButton",
			"SpellbookMicroButton",
			"MainMenuMicroButton",
		}) do
			if G[name] == nil then
				sim.templates.createFrame("Button", name, sim.widgets.root())
				Taint.globalTaint[name] = nil
			end
		end
	end
	G.CreateFrame = function(kind, name, parent, template, id)
		return sim.templates.createFrame(kind, name, parent, template, id)
	end
	G.CreateFont = function(name)
		return sim.templates.createFont(name)
	end
	G.GetScreenWidth = function()
		return sim.screenWidth
	end
	G.GetScreenHeight = function()
		return sim.screenHeight
	end
	G.GetPhysicalScreenSize = function()
		return 1920, 1080
	end
	G.GetCursorPosition = function()
		return sim.mouseX or 0, sim.mouseY or 0
	end
	G.GetMouseFoci = function()
		return { sim.mouseFocus }
	end
	G.GetMouseFocus = function()
		return sim.mouseFocus
	end
	G.EnumerateFrames = function(after)
		local list = sim.widgets.all
		local found = after == nil
		for _, obj in ipairs(list) do
			if found and sim.widgets.state[obj].isFrame then
				return obj
			end
			if obj == after then
				found = true
			end
		end
	end
	G.GetFramesRegisteredForEvent = function(event)
		return unpack(E.listeners(event))
	end
	G.InCombatLockdown = function()
		return sim.inCombat == true
	end
	G.GetLocale = function()
		return sim.locale
	end
	G.IsLoggedIn = function()
		return sim.loggedIn == true
	end
	G.ReloadUI = function()
		sim.reloadRequested = true
	end
	G.GetBuildInfo = function()
		return "1.60.1", "70425", "Oct 16 2026", 16001, "", "", 16001
	end
	G.IsOnGlueScreen = function()
		return false
	end
	G.IsPublicBuild = function()
		return true
	end
	G.IsTestBuild = function()
		return false
	end
	G.IsGMClient = function()
		return false
	end
	G.IsMacClient = function()
		return false
	end
	G.IsWindowsClient = function()
		return true
	end
	G.IsLinuxClient = function()
		return false
	end

	-- CVars.
	sim.cvars = {}
	-- Client code reads CVars the client always defines; an unset one reads "0" for it (recorded as a gap).
	local function cvar(name)
		local v = sim.cvars[name]
		if v == nil and not Taint.current and type(name) == "string" then
			sim.gaps["CVar " .. name] = true
			return "0"
		end
		return v
	end
	sim.impl["C_CVar.GetCVar"] = cvar
	sim.impl["C_CVar.SetCVar"] = function(name, value)
		sim.cvars[name] = value ~= nil and tostring(value) or nil
		return true
	end
	sim.impl["C_CVar.GetCVarBool"] = function(name)
		local v = cvar(name)
		return v == "1" or v == "true"
	end
	sim.impl["C_CVar.GetCVarDefault"] = function(name)
		return sim.cvars[name]
	end
	sim.impl["C_CVar.RegisterCVar"] = function(name, value)
		if sim.cvars[name] == nil then
			sim.cvars[name] = value ~= nil and tostring(value) or nil
		end
	end
	G.GetCVar = cvar
	G.SetCVar = function(name, value)
		sim.cvars[name] = value ~= nil and tostring(value) or nil
		return true
	end
	G.GetCVarBool = function(name)
		local v = sim.cvars[name]
		return v == "1" or v == "true"
	end
	G.GetCVarDefault = G.GetCVar
	G.RegisterCVar = function(name, value)
		if sim.cvars[name] == nil then
			sim.cvars[name] = value
		end
	end

	-- Bindings, sound, misc. engine calls that only need to exist.
	for _, name in ipairs({
		"PlaySound",
		"PlaySoundFile",
		"StopSound",
		"SetOverrideBinding",
		"SetOverrideBindingClick",
		"ClearOverrideBindings",
		"SetBinding",
		"SaveBindings",
		"LoadBindings",
		"RequestRaidInfo",
		"SetPortraitTexture",
		"SetPortraitToTexture",
		"SetRaidTargetIconTexture",
		"FlashClientIcon",
		"ResetCursor",
		"SetCursor",
		"ClearCursor",
		"CloseDropDownMenus",
		"UpdateAddOnMemoryUsage",
		"UpdateAddOnCPUUsage",
		"ResetAddOnCPUUsage",
		"Screenshot",
		"TakeScreenshot",
	}) do
		if G[name] == nil then
			G[name] = function() end
		end
	end
	G.GetBindingKey = function()
		return nil
	end
	G.GetBindingText = function(key)
		return key or ""
	end
	G.GetBindingAction = function()
		return ""
	end
	G.GetCurrentBindingSet = function()
		return 1
	end
	G.GetAddOnMemoryUsage = function()
		return 0
	end
	G.GetFramerate = function()
		return 60
	end
	G.GetNetStats = function()
		return 0, 0, 20, 20
	end
	G.IsModifierKeyDown = function()
		return sim.modifiers.shift or sim.modifiers.ctrl or sim.modifiers.alt or false
	end
	G.IsShiftKeyDown = function()
		return sim.modifiers.shift or false
	end
	G.IsControlKeyDown = function()
		return sim.modifiers.ctrl or false
	end
	G.IsAltKeyDown = function()
		return sim.modifiers.alt or false
	end
	G.IsLeftShiftKeyDown, G.IsRightShiftKeyDown = G.IsShiftKeyDown, G.IsShiftKeyDown
	G.IsLeftControlKeyDown, G.IsRightControlKeyDown = G.IsControlKeyDown, G.IsControlKeyDown
	G.IsLeftAltKeyDown, G.IsRightAltKeyDown = G.IsAltKeyDown, G.IsAltKeyDown
	G.IsMouseButtonDown = function()
		return false
	end
	G.GetMouseButtonClicked = function()
		return "LeftButton"
	end
	sim.modifiers = {}
	sim.restrictions = {}
	return G
end

return M
