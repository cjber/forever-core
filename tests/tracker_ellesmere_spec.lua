-- EllesmereUI's Custom Quest Tracker draws its filtered list in EUI_CustomQuestTracker while Blizzard's tracker stays
-- shown at alpha 0 with every watched quest. The shared column must follow the visible, filtered list rather than the
-- muted native content, and come with it when it moves, grows or shrinks. Every scenario builds fresh closures, which
-- LuaJIT cannot trace; the game runs plain Lua 5.1, so interpret.
local jit = rawget(_G, "jit")
if jit then
	jit.off()
end
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end
local function noop() end
local function fraction(point)
	local x = point:find("LEFT", 1, true) and 0 or point:find("RIGHT", 1, true) and 1 or 0.5
	local y = point:find("BOTTOM", 1, true) and 0 or point:find("TOP", 1, true) and 1 or 0.5
	return x, y
end
-- Screen pixels from the bottom left corner: left, top, width, height, bottom.
local function bounds(frame)
	if frame.root then
		local scale = frame:GetEffectiveScale()
		return 0, frame.height * scale, frame.width * scale, frame.height * scale, 0
	end
	local point, relative, relativePoint, x, y = unpack((assert(frame.point, "missing anchor")))
	local left, top, rw, _, relativeBottom = bounds(relative)
	local rx, ry = fraction(relativePoint)
	local fx, fy = fraction(point)
	local scale = frame:GetEffectiveScale()
	local width, height = frame.width * scale, frame.height * scale
	left = left + rx * rw + (x or 0) * scale - fx * width
	local anchorY = ry == 0 and relativeBottom or ry == 1 and top or (top + relativeBottom) / 2
	local bottom = anchorY + (y or 0) * scale - fy * height
	return left, bottom + height, width, height, bottom
end
local function clears(a, b)
	local al, at, aw, _, ab = bounds(a)
	local bl, bt, bw, _, bb = bounds(b)
	return not (al < bl + bw - 0.01 and al + aw > bl + 0.01 and ab < bt - 0.01 and at > bb + 0.01)
end
local function near(a, b)
	return math.abs(a - b) < 0.01
end

-- Each scenario runs the files afresh in its own environment; compiling them once keeps that cheap.
local chunks = {}
local function chunk(path)
	chunks[path] = chunks[path] or assert(loadfile(path))
	return chunks[path]
end

-- options: ellesmere = { point, x, y, width, height } or nil, questie = { point, x, y, height } or nil,
-- attached, uiScale, userScale, loadsLate
local function scenario(options)
	local frames, timers, ready, combat = {}, {}, nil, false
	local function frame(_, name, parent)
		local f = { name = name, parent = parent, width = 250, height = 1, scripts = {} }
		function f:GetEffectiveScale()
			return (self.scale or 1) * (self.parent and self.parent:GetEffectiveScale() or 1)
		end
		function f:SetScale(value)
			self.scale = value
		end
		function f:SetPoint(...)
			self.point = { ... }
		end
		function f:GetPoint()
			return unpack(self.point or {})
		end
		function f:ClearAllPoints()
			self.point = nil
		end
		function f:SetWidth(value)
			self.width = value
		end
		function f:GetWidth()
			return self.width
		end
		function f:SetHeight(value)
			self.height = value
		end
		function f:GetHeight()
			return self.height
		end
		function f:GetLeft()
			return (bounds(self)) / self:GetEffectiveScale()
		end
		function f:GetTop()
			return select(2, bounds(self)) / self:GetEffectiveScale()
		end
		function f:GetRight()
			local left, _, width = bounds(self)
			return (left + width) / self:GetEffectiveScale()
		end
		function f:GetBottom()
			return select(5, bounds(self)) / self:GetEffectiveScale()
		end
		function f:GetCenter()
			local left, top, width, height = bounds(self)
			local scale = self:GetEffectiveScale()
			return (left + width / 2) / scale, (top - height / 2) / scale
		end
		function f:SetClampedToScreen(value)
			self.clamped = value
		end
		function f:IsClampedToScreen()
			return self.clamped
		end
		function f:SetScript(event, fn)
			self.scripts[event] = fn
		end
		function f:HookScript(event, fn)
			self.hooks = self.hooks or {}
			self.hooks[event] = fn
		end
		function f:SetShown(value)
			self.shown = value
		end
		function f:Hide()
			self.shown = false
		end
		function f:Show()
			self.shown = true
		end
		function f:IsShown()
			return self.shown ~= false
		end
		function f.CreateFontString(_)
			return { SetPoint = noop, SetText = noop }
		end
		function f.CreateTexture(_)
			return {
				SetPoint = noop,
				SetAtlas = noop,
				SetVertexColor = noop,
				SetShown = noop,
				Hide = noop,
			}
		end
		f.SetMovable, f.RegisterForDrag, f.RegisterEvent = noop, noop, noop
		frames[#frames + 1] = f
		return f
	end
	local screen = frame()
	screen.root, screen.width, screen.height, screen.scale = true, 1200, 1080, options.uiScale or 1
	local native = frame(nil, "native", screen)
	native.scale, native.height = options.scale or 1, options.nativeHeight or 300
	native:SetClampedToScreen(true)
	native:SetPoint("TOPRIGHT", screen, "TOPRIGHT", -24, -100)
	local slot = { native:GetPoint() }
	local nineSlice = frame(nil, "nineSlice", native)
	nineSlice:SetPoint("TOP", native, "TOP", 0, -300)
	native.NineSlice = nineSlice
	local rawPoint, rawClear = native.SetPoint, native.ClearAllPoints
	function native:SetPoint(...)
		assert(not combat, "protected combat reposition")
		rawPoint(self, ...)
	end
	function native:ClearAllPoints()
		assert(not combat, "protected combat clear")
		rawClear(self)
	end
	local settings = { attached = options.attached ~= false, scale = options.userScale or 1 }
	local ns = {
		L = setmetatable({}, {
			__index = function(_, key)
				return key
			end,
		}),
		TrackerHostSettings = function()
			return settings
		end,
	}
	local env = setmetatable({
		UIParent = screen,
		ObjectiveTrackerFrame = native,
		CreateFrame = frame,
		InCombatLockdown = function()
			return combat
		end,
		C_Timer = {
			After = function(_, fn)
				timers[#timers + 1] = fn
			end,
		},
		EventUtil = {
			ContinueAfterAllEvents = function(fn)
				ready = fn
			end,
		},
		EventRegistry = { RegisterCallback = noop },
		Mixin = function(target, mixin)
			for key, value in pairs(mixin) do
				target[key] = value
			end
		end,
		hooksecurefunc = function() end,
		CreateFramePoolCollection = function()
			return {}
		end,
	}, { __index = _G })
	env._G = env
	if options.ellesmere then
		-- The real addon loads first through ## OptionalDeps; the spec mimics that before our files run.
		env.EllesmereUIQuestTracker = {}
	end
	setfenv(chunk("UI/TrackerQuestie.lua"), env)("Test", ns)
	setfenv(chunk("UI/TrackerEllesmere.lua"), env)("Test", ns)
	setfenv(chunk("UI/TrackerLock.lua"), env)("Test", ns)
	setfenv(chunk("UI/TrackerOrder.lua"), env)("Test", ns) -- the section order, loaded before the host
	setfenv(chunk(os.getenv("TRACKER_HOST_SOURCE") or "UI/TrackerHost.lua"), env)("Test", ns)
	local host = frames[4]
	local module = frame()
	module.uiOrder = -1
	module.SetContainer, module.Update = noop, noop
	module.SetParent = function(self, parent)
		self.parent = parent
	end
	module.GetContentsHeight = function()
		return module.empty and 0 or 227
	end
	ns.TrackerHost.Attach(module)
	local function drain()
		local pending = timers
		timers = {}
		for _, fn in ipairs(pending) do
			fn()
		end
	end
	local ellesmere, questie
	local function makeEllesmere(spec)
		ellesmere = frame(nil, "EUI_CustomQuestTracker", screen)
		ellesmere.width, ellesmere.height = spec.width or 250, spec.height
		ellesmere:SetPoint(spec.point or "TOPRIGHT", screen, spec.point or "TOPRIGHT", spec.x or -24, spec.y or -100)
		env.EUI_CustomQuestTracker = ellesmere
		return ellesmere
	end
	local function makeQuestie(spec)
		questie = frame(nil, "Questie_BaseFrame", screen)
		questie.width, questie.height = 280, spec.height
		questie:SetPoint(spec.point, screen, spec.point, spec.x, spec.y)
		env.Questie_BaseFrame = questie
		return questie
	end
	if options.ellesmere then
		if not options.loadsLate then
			makeEllesmere(options.ellesmere)
		end
	end
	if options.questie then
		env.Questie = {}
		makeQuestie(options.questie)
	end
	ready()
	drain()
	if options.loadsLate then
		check(#timers == 1, "waits for EllesmereUI's custom tracker while it is still starting")
		makeEllesmere(options.ellesmere)
		drain()
		drain()
	end
	return {
		host = host,
		module = module,
		native = native,
		frames = frames,
		ellesmere = ellesmere,
		questie = questie,
		slot = slot,
		settings = settings,
		drain = drain,
		-- One watcher tick, the way the game runs the ticker's OnUpdate.
		tick = function(delta)
			for _, other in ipairs(frames) do
				if other.scripts.OnUpdate then
					other.scripts.OnUpdate(other, delta or 1)
				end
			end
		end,
		pending = function()
			return #timers
		end,
		setCombat = function(value)
			combat = value
		end,
	}
end

-- The native tracker keeps its own slot and the column starts where the native quests end.
local function stacked(s, label)
	local p, rel, rp, x, y = s.native:GetPoint()
	check(
		p == s.slot[1] and rel == s.slot[2] and rp == s.slot[3] and x == s.slot[4] and y == s.slot[5],
		label .. ": the native tracker keeps its slot"
	)
	local _, _, _, _, contentBottom = bounds(s.native.NineSlice)
	local _, hostTop = bounds(s.host)
	check(near(hostTop, contentBottom), label .. ": the column starts below the native quests")
end

-- The column sits just below the custom tracker, not the native content.
local function belowEllesmere(s, label)
	local _, _, _, _, listBottom = bounds(s.ellesmere)
	local _, hostTop = bounds(s.host)
	check(s.host:IsShown(), label .. ": the column shows")
	check(clears(s.host, s.ellesmere), label .. ": the column clears the visible quest list")
	local gap = 8 * s.host:GetEffectiveScale()
	check(near(hostTop, listBottom - gap), label .. ": the column sits just below the filtered list")
	local p, rel, rp, x, y = s.native:GetPoint()
	check(
		p == s.slot[1] and rel == s.slot[2] and rp == s.slot[3] and x == s.slot[4] and y == s.slot[5],
		label .. ": the native tracker stays in its own slot"
	)
end

for _, uiScale in ipairs({ 1, 0.8 }) do
	for _, userScale in ipairs({ 0.5, 1 }) do
		local label = ("ui %s user %s"):format(uiScale, userScale)
		local base = { uiScale = uiScale, userScale = userScale }
		local function with(extra)
			local result = {}
			for key, value in pairs(base) do
				result[key] = value
			end
			for key, value in pairs(extra) do
				result[key] = value
			end
			return result
		end

		-- Without EllesmereUI nothing changes.
		stacked(scenario(base), label .. " no EllesmereUI")

		-- The visible custom tracker replaces the muted native content as the column's reference.
		local s = scenario(with({
			nativeHeight = 700,
			ellesmere = { point = "TOPRIGHT", x = -24, y = -100, height = 200 },
		}))
		belowEllesmere(s, label .. " custom tracker")
		local _, _, _, _, listBottom = bounds(s.ellesmere)
		local _, hostTop = bounds(s.host)
		local _, _, _, _, nativeBottom = bounds(s.native.NineSlice)
		check(listBottom > nativeBottom, label .. ": the filtered list ends above the muted native content's bottom")
		check(s.ellesmere.point[1] == "TOPRIGHT" and s.ellesmere.point[4] == -24, label .. ": the list is untouched")
		-- Nothing of ours may sit in EllesmereUI's anchor family.
		local anchored = false
		for _, other in ipairs(s.frames) do
			if other.point and other.point[2] == s.ellesmere then
				anchored = true
			end
		end
		check(not anchored, label .. ": no Forever frame is anchored to the custom tracker")

		-- A filter hides quests and the list shrinks: the column follows its new bottom.
		s.ellesmere.height = 120
		s.ellesmere.hooks.OnSizeChanged(s.ellesmere)
		s.drain()
		belowEllesmere(s, label .. " after a filter shrinks the list")
		local _, shrunkTop = bounds(s.host)
		check(shrunkTop > hostTop, label .. ": the column moved up with the list")
		-- And grows again.
		s.ellesmere.height = 300
		s.ellesmere.hooks.OnSizeChanged(s.ellesmere)
		s.drain()
		belowEllesmere(s, label .. " after more quests show")

		-- A move with no event of the list's own is still noticed by the ticker.
		s.ellesmere:SetPoint("TOPLEFT", s.host.parent, "TOPLEFT", 24, -100)
		s.tick(1)
		s.drain()
		belowEllesmere(s, label .. " after the list moves")

		-- EllesmereUI's visibility rules hide the frame in raids and out of instances. The player's chosen slot is
		-- still the right reference, not the muted native frame at the bottom.
		s.ellesmere:Hide()
		s.ellesmere.hooks.OnHide(s.ellesmere)
		s.drain()
		belowEllesmere(s, label .. " after the list hides")

		-- No journey section: the column hides and the custom list keeps its anchor.
		local empty = scenario(with({ ellesmere = { point = "TOPRIGHT", x = -24, y = -100, height = 200 } }))
		empty.module.empty = true
		empty.host:MarkDirty()
		empty.drain()
		check(not empty.host:IsShown(), label .. ": no journey section hides the column")
		check(
			empty.ellesmere.point[1] == "TOPRIGHT" and empty.ellesmere.point[4] == -24,
			label .. ": the custom list's anchor stays user-owned"
		)

		-- A tracker low on the screen: the column goes above it instead of off the bottom.
		local low = scenario(with({
			ellesmere = { point = "BOTTOMRIGHT", x = -24, y = 30, height = 200 },
		}))
		local _, _, _, _, lowHostBottom = bounds(low.host)
		local _, lowListTop = bounds(low.ellesmere)
		check(clears(low.host, low.ellesmere), label .. ": a low tracker puts the column above it")
		check(
			lowHostBottom > lowListTop and lowHostBottom < lowListTop + 20,
			label .. ": the column sits just above the tracker"
		)

		-- A detached column the player has not dragged starts beside the visible list.
		local detached = scenario(with({
			attached = false,
			ellesmere = { point = "TOPLEFT", x = 24, y = -100, height = 200 },
		}))
		local hostLeft, detachedTop = bounds(detached.host)
		local listLeft, listTop = bounds(detached.ellesmere)
		check(clears(detached.host, detached.ellesmere), label .. ": the detached column clears the list")
		check(hostLeft > listLeft and near(detachedTop, listTop), label .. ": beside it, level with its top")

		-- In combat the list may still resize; only our frames move.
		local late = scenario(with({ ellesmere = { point = "TOPRIGHT", x = -24, y = -100, height = 200 } }))
		late.setCombat(true)
		late.ellesmere.height = 140
		late.ellesmere.hooks.OnSizeChanged(late.ellesmere)
		late.drain()
		belowEllesmere(late, label .. " after a filter change in combat")
		late.setCombat(false)

		-- Questie is still the fallback when EllesmereUI's custom tracker is not there.
		local questie = scenario(with({ questie = { point = "TOPRIGHT", x = -24, y = -100, height = 300 } }))
		local _, _, _, _, questieBottom = bounds(questie.questie)
		local _, questieHostTop = bounds(questie.host)
		check(clears(questie.host, questie.questie), label .. ": Questie's list still moves the column")
		check(
			near(questieHostTop, questieBottom - 8 * questie.host:GetEffectiveScale()),
			label .. ": below Questie's list"
		)

		-- With both installed, the custom tracker the player chose wins, even while EllesmereUI's visibility
		-- rules hide it: the slot they chose is still that one.
		local both = scenario(with({
			ellesmere = { point = "TOPLEFT", x = 24, y = -100, height = 200 },
			questie = { point = "TOPRIGHT", x = -24, y = -100, height = 300 },
		}))
		belowEllesmere(both, label .. " EllesmereUI over Questie")
		both.ellesmere:Hide()
		both.ellesmere.hooks.OnHide(both.ellesmere)
		both.drain()
		belowEllesmere(both, label .. " a hidden custom tracker still wins over Questie")

		-- The custom tracker is built after the host's first layout.
		local lateStart = scenario(with({
			loadsLate = true,
			ellesmere = { point = "TOPRIGHT", x = -24, y = -100, height = 200 },
		}))
		belowEllesmere(lateStart, label .. " a late custom tracker")
	end
end

-- Without EllesmereUI there is nothing to wait for.
local none = scenario({})
check(none.pending() == 0, "no wait without EllesmereUI")
print("tracker_ellesmere_spec: " .. checks .. " checks passed")
