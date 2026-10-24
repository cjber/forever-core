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
		return unpack(out, 1, select("#", ...))
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
		local folder = source:match("^@([^/]+)/") or ""
		local module = name:gsub("^%.", "")
		local loaded = sim.modules[folder] and sim.modules[folder][module]
		if loaded == nil then
			error(string.format("import(): module '%s' not found in %s", name, folder), 2)
		end
		return loaded
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
	-- Kiosk (event demo) mode: off. A native table the UI checks everywhere.
	G.Kiosk = G.Kiosk
		or setmetatable({}, {
			__index = function()
				return function()
					return false
				end
			end,
		})
	G.addframetext = function() end
	G.SpellCanTargetQuest = function()
		return false
	end
	G.SpellIsTargeting = function()
		return false
	end
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
