-- Core/APIKit.lua, loaded from the TOC the way the client loads it: one next-frame dispatch per burst of channel
-- changes, only the changed names sent, and every callback under its addon's SafeCall.
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

-- A tiny client: frames remember what the modules set, and every method the shared files call exists. Methods the
-- modules do not use are no-ops, so a new read in a shared file fails here rather than at runtime.
local created = {}
local function texture()
	local value = { points = {} }
	local methods = {}
	function methods:SetPoint(...)
		self.points[#self.points + 1] = { ... }
	end
	function methods.SetAllPoints() end
	function methods:SetSize(width, height)
		self.width, self.height = width, height
	end
	function methods:SetWidth(width)
		self.width = width
	end
	function methods:SetAtlas(atlas)
		self.atlas = atlas
	end
	function methods:SetTexture(path)
		self.texture = path
	end
	function methods:SetTexCoord(...)
		self.texCoord = { ... }
	end
	function methods:SetVertexColor(...)
		self.color = { ... }
	end
	function methods:SetShown(shown)
		self.shown = shown
	end
	function methods:Show()
		self.shown = true
	end
	function methods:Hide()
		self.shown = false
	end
	function methods:IsShown()
		return self.shown ~= false
	end
	setmetatable(value, {
		__index = function(_, key)
			return methods[key] or function() end
		end,
	})
	return value
end

local function widget(kind, name, parent, template)
	local value = {
		kind = kind,
		name = name,
		parent = parent,
		template = template,
		scripts = {},
		hooks = {},
		events = {},
		points = {},
		children = {},
		text = "",
		shown = true,
	}
	local methods = {}
	function methods:SetScript(event, fn)
		self.scripts[event] = fn
	end
	function methods:GetScript(event)
		return self.scripts[event]
	end
	function methods:HookScript(event, fn)
		self.hooks[event] = self.hooks[event] or {}
		self.hooks[event][#self.hooks[event] + 1] = fn
	end
	function methods:RegisterEvent(event)
		self.events[event] = true
	end
	function methods:UnregisterEvent(event)
		self.events[event] = nil
	end
	function methods:UnregisterAllEvents()
		self.events = {}
	end
	function methods:SetSize(width, height)
		self.width, self.height = width, height
	end
	function methods:SetWidth(width)
		self.width = width
	end
	function methods:GetWidth()
		return self.width or 250
	end
	function methods:SetHeight(height)
		self.height = height
	end
	function methods:GetHeight()
		return self.height or 0
	end
	function methods:SetPoint(...)
		self.points[#self.points + 1] = { ... }
		self.point = { ... }
	end
	function methods:GetPoint()
		return unpack(self.point or {})
	end
	function methods:ClearAllPoints()
		self.point = nil
	end
	function methods:SetShown(shown)
		self.shown = shown
	end
	function methods:Show()
		self.shown = true
	end
	function methods:Hide()
		self.shown = false
	end
	function methods:IsShown()
		return self.shown ~= false
	end
	function methods:IsVisible()
		return self.shown ~= false
	end
	function methods:SetParent(owner)
		self.parent = owner
	end
	function methods:GetParent()
		return self.parent
	end
	function methods.EnableMouse() end
	function methods.RegisterForDrag() end
	function methods.RegisterForClicks() end
	function methods.SetMovable() end
	function methods.SetClampedToScreen() end
	function methods.SetFrameStrata() end
	function methods.SetFrameLevel() end
	function methods.SetFixedFrameStrata() end
	function methods.SetFixedFrameLevel() end
	function methods.SetToplevel() end
	function methods.SetHighlightTexture() end
	function methods.StartMoving() end
	function methods.StopMovingOrSizing() end
	function methods:SetScale(scale)
		self.scale = scale
	end
	function methods:GetScale()
		return self.scale or 1
	end
	function methods:GetEffectiveScale()
		return self.scale or 1
	end
	function methods:SetAlpha(alpha)
		self.alpha = alpha
	end
	function methods:GetAlpha()
		return self.alpha or 1
	end
	function methods:GetEffectiveAlpha()
		return self.alpha or 1
	end
	function methods:GetLeft()
		return self.left or 0
	end
	function methods:GetRight()
		return self.right or (self:GetLeft() + self:GetWidth())
	end
	function methods:GetTop()
		return self.top or 1080
	end
	function methods:GetBottom()
		return self.bottom or (self:GetTop() - self:GetHeight())
	end
	function methods:GetCenter()
		return (self:GetLeft() + self:GetRight()) / 2, (self:GetTop() + self:GetBottom()) / 2
	end
	function methods:GetRect()
		return self:GetLeft(), self:GetBottom(), self:GetWidth(), self:GetHeight()
	end
	function methods:SetText(text)
		self.text = text
	end
	function methods:GetText()
		return self.text
	end
	function methods:SetJustifyH(justify)
		self.justify = justify
	end
	function methods:SetTextColor(...)
		self.textColor = { ... }
	end
	function methods.SetFontObject() end
	function methods.SetMultiLine() end
	function methods.SetAutoFocus() end
	function methods.SetMaxLetters() end
	function methods:SetFocus()
		self.focused = true
	end
	function methods:HighlightText()
		self.highlighted = true
	end
	function methods.SetCursorPosition() end
	function methods.Insert() end
	function methods:SetChecked(checked)
		self.checked = checked
	end
	function methods:GetChecked()
		return self.checked == true
	end
	function methods:SetButtonState(state)
		self.buttonState = state
	end
	function methods:SetMinMaxValues(minimum, maximum)
		self.minimum, self.maximum = minimum, maximum
	end
	function methods:SetValueStep(step)
		self.step = step
	end
	function methods:SetObeyStepOnDrag(obey)
		self.obeyStep = obey
	end
	function methods:SetValue(number)
		self.value = number
	end
	function methods:GetValue()
		return self.value
	end
	function methods:SetScrollChild(child)
		self.scrollChild = child
	end
	function methods:SetDataProvider(provider)
		self.provider = provider
	end
	function methods:SetDefaultText(text)
		self.defaultText = text
	end
	function methods:SetupMenu(generator)
		self.menu = generator
	end
	function methods.OpenMenu() end
	function methods.IsEnabled()
		return true
	end
	function methods.SetEnabled() end
	function methods:SetCustomOnMouseUpHandler(handler)
		self.mouseUp = handler
	end
	function methods.GetPortrait()
		return texture()
	end
	function methods:SetTitle(title)
		self.title = title
	end
	function methods:CreateTexture()
		local value_ = texture()
		self.children[#self.children + 1] = value_
		return value_
	end
	function methods:CreateFontString()
		local value_ = widget("FontString", nil, self)
		self.children[#self.children + 1] = value_
		return value_
	end
	function methods:GetFontString()
		return self
	end
	function methods:GetStringWidth()
		return #(self.text or "") * 7
	end
	function methods:GetStringHeight()
		return math.max(1, math.ceil(#(self.text or "") / 50)) * 14
	end
	function methods.SetTooltip() end
	function methods.SetAllPoints() end
	setmetatable(value, {
		__index = function(_, key)
			local method = methods[key]
			if method then
				return method
			end
			return function() end
		end,
	})
	if parent then
		parent.children[#parent.children + 1] = value
	end
	created[#created + 1] = value
	return value
end

local env
local function Client()
	created = {}
	local named = {}
	env = {
		_G = nil,
		CreateFrame = function(kind, name, parent, template)
			local frame = widget(kind, name, parent, template)
			if name then
				named[name] = frame
				env[name] = frame
			end
			return frame
		end,
		UISpecialFrames = {},
		SlashCmdList = {},
		Mixin = function(target, mixin)
			for key, value in pairs(mixin) do
				target[key] = value
			end
		end,
		tContains = function(list, value)
			for _, item in ipairs(list) do
				if item == value then
					return true
				end
			end
			return false
		end,
		hooksecurefunc = function(target, name, callback)
			local original = target[name]
			target[name] = function(...)
				local result = original(...)
				callback(...)
				return result
			end
		end,
		securecallfunction = function(fn, ...)
			return fn(...)
		end,
		InCombatLockdown = function()
			return false
		end,
		IsShiftKeyDown = function()
			return false
		end,
		GetCursorPosition = function()
			return 0, 0
		end,
		GetTime = function()
			return 1
		end,
		GetServerTime = function()
			return 1700000000
		end,
		GetBuildInfo = function()
			return "1.60.1", "70124", "", 16001
		end,
		GetLocale = function()
			return "enUS"
		end,
		UnitClass = function()
			return nil, "MAGE"
		end,
		UnitRace = function()
			return nil, "Human"
		end,
		UnitLevel = function()
			return 60
		end,
		UnitFactionGroup = function()
			return "Alliance"
		end,
		UnitName = function()
			return "Tester"
		end,
		GetNormalizedRealmName = function()
			return "MyRealm"
		end,
		GetRealmName = function()
			return "MyRealm"
		end,
		IsInGuild = function()
			return false
		end,
		IsInGroup = function()
			return false
		end,
		IsInRaid = function()
			return false
		end,
		GetNumGroupMembers = function()
			return 0
		end,
		date = function()
			return "2026-11-10 12:00:00"
		end,
		strtrim = function(text)
			return text:match("^%s*(.-)%s*$")
		end,
		geterrorhandler = function()
			return env.errorHandler or function() end
		end,
		seterrorhandler = function(handler)
			env.errorHandler = handler
		end,
		C_AddOns = {
			GetAddOnMetadata = function(name, key)
				if key == "Version" then
					return ({ AddonA = "9.9.9", AddonB = "1.2.3" })[name] or "0.0.1"
				end
				if key == "X-Website" then
					return "https://github.com/cjber/" .. tostring(name):lower()
				end
			end,
			GetNumAddOns = function()
				return 0
			end,
			GetAddOnInfo = function() end,
			IsAddOnLoaded = function()
				return false
			end,
		},
		C_Map = {
			GetBestMapForUnit = function()
				return nil
			end,
			GetPlayerMapPosition = function() end,
			GetMapInfo = function() end,
		},
		C_DateAndTime = {
			GetSecondsUntilWeeklyReset = function()
				return nil
			end,
		},
		C_ChatInfo = {
			RegisterAddonMessagePrefix = function() end,
			SendAddonMessage = function()
				return 0
			end,
		},
		C_Timer = {
			After = function(_, fn)
				table.insert(env.timers, fn)
			end,
		},
		C_XMLUtil = {
			GetTemplateInfo = function()
				return { type = "Frame" }
			end,
		},
		CreateFramePoolCollection = function()
			return {
				GetOrCreatePool = function()
					return {
						Acquire = function()
							return widget("Frame"), true
						end,
					}
				end,
				Release = function() end,
			}
		end,
		EventRegistry = {
			RegisterCallback = function() end,
			TriggerEvent = function() end,
		},
		EventUtil = {
			ContinueAfterAllEvents = function(fn)
				fn()
			end,
		},
		MenuUtil = {
			CreateContextMenu = function(owner, generator)
				local root = {
					CreateCheckbox = function() end,
					CreateRadio = function() end,
					CreateButton = function()
						return { SetTooltip = function() end }
					end,
					CreateDivider = function() end,
				}
				generator(owner, root)
			end,
		},
		Enum = {
			InputDeviceInterfaceType = { Gamepad = 2 },
			SendAddonMessageResult = { Success = 0 },
			TooltipDataType = { Unit = 7 },
		},
		CreateFromMixins = function(...)
			local result = {}
			for _, mixin in ipairs({ ... }) do
				env.Mixin(result, mixin)
			end
			return result
		end,
		CreateDataProvider = function(rows)
			return { rows = rows }
		end,
		CreateScrollBoxListLinearView = function()
			return {
				SetElementExtent = function() end,
				SetElementInitializer = function() end,
			}
		end,
		ScrollUtil = { InitScrollBoxListWithScrollBar = function() end },
		ScrollBoxConstants = { RetainScrollPosition = 1 },
		RAID_CLASS_COLORS = { MAGE = { GetRGB = function() end }, HUNTER = { GetRGB = function() end } },
		NORMAL_FONT_COLOR = { GetRGB = function() end },
		HIGHLIGHT_FONT_COLOR = { GetRGB = function() end },
		GRAY_FONT_COLOR = { GetRGB = function() end },
		GREEN_FONT_COLOR = { GetRGB = function() end },
		GameTooltip = widget("GameTooltip"),
		Settings = nil,
		timers = {},
	}
	env._G = env
	env.print = function() end
	env.UIParent = widget("Frame")
	env.UIParent:SetWidth(1200)
	env.UIParent:SetHeight(1080)
	env.UIParent.scale = 1
	env.ObjectiveTrackerFrame = widget("Frame")
	env.ObjectiveTrackerFrame:SetWidth(250)
	env.ObjectiveTrackerFrame:SetHeight(300)
	env.ObjectiveTrackerFrame.point = { "TOPRIGHT", env.UIParent, "TOPRIGHT", 0, 0 }
	env.ObjectiveTrackerFrame.top = 1080
	env.ObjectiveTrackerFrame.scale = 1
	env.ObjectiveTrackerFrame.NineSlice = {
		GetBottom = function()
			return 780
		end,
		GetEffectiveScale = function()
			return 1
		end,
	}
	env.ObjectiveTrackerFrame.Header = widget("Frame")
	env.ObjectiveTrackerFrame.Header.MinimizeButton = widget("Button")
	env.Minimap = widget("Frame")
	env.Minimap:SetWidth(198)
	env.Minimap:SetHeight(198)
	env.Minimap.shown = false
	env.Minimap.GetEffectiveScale = function()
		return 1
	end
	env.GameTooltip.HookScript = function() end
	setmetatable(env, { __index = _G })
	return named
end

-- The TOC's files, in order, the way the client loads them.
local function tocFiles()
	local files = {}
	for line in io.lines("ForeverCore.toc") do
		line = line:gsub("\r$", "")
		if not (line:match("^%s*$") or line:match("^%s*#")) then
			files[#files + 1] = (line:gsub("\\", "/"))
		end
	end
	return files
end

-- C_Timer.After only queues here; `flush` runs one frame's timers by hand, so a synchronous dispatch would show up as
-- a callback that ran before the flush.
local function flush()
	local queued = env.timers
	env.timers = {}
	for _, callback in ipairs(queued) do
		callback()
	end
end

Client()
env.errorHandler = function() end
local ns = {}
for _, path in ipairs(tocFiles()) do
	-- Core's own quest list needs the full native tracker template, as api_spec.lua does for the same client.
	local native = env.ObjectiveTrackerFrame
	if path == "UI/TrackerQuests.lua" then
		env.ObjectiveTrackerFrame = nil
	end
	local chunk = assert(loadfile(path), path)
	setfenv(chunk, env)
	chunk("ForeverCore", ns)
	env.ObjectiveTrackerFrame = native
end
-- The TOC's own load-time timers are not this spec's; every scenario starts with an empty queue.
env.timers = {}
local ForeverCore = env.ForeverCore
local kit = ForeverCore.APIKit
check(kit ~= nil, "the TOC publishes the API kit")
check(kit == ns.APIKit, "and it is the module Core/APIKit.lua built")
equal(kit.minor, 1, "the kit's minor is 1")
check(type(kit.Hub) == "function", "Hub builds an addon's hub")
check(type(kit.NotReady) == "function", "NotReady answers a read with nothing to say")

-- NotReady ------------------------------------------------------------------------------------------------------
do
	local value, reason = kit.NotReady("loading")
	check(value == nil, "NotReady returns nil first")
	equal(reason, "loading", "and the reason second")
	local _, disabled = kit.NotReady("disabled")
	equal(disabled, "disabled", "a disabled feature says so")
	local _, none = kit.NotReady("none")
	equal(none, "none", "an empty answer says so")
end

-- A hub, its channels and its own state. A fresh hub per scenario keeps each baseline out of the next.
local function Hub(state, ready)
	return kit.Hub("KitAddon", {
		stop = function()
			return state.stop
		end,
		journey = function()
			return state.journey
		end,
		status = function()
			return state.status
		end,
	}, ready)
end

-- No subscriber, no timer ----------------------------------------------------------------------------------------
do
	local state = { stop = "a", journey = "alpha", status = "running" }
	local hub = Hub(state)
	hub.Queue()
	hub.Queue()
	equal(#env.timers, 0, "Queue arms no timer while nobody listens")
end

-- The next frame, once per burst, only what changed --------------------------------------------------------------
do
	local state = { stop = "a", journey = "alpha", status = "running" }
	local hub = Hub(state)
	local calls, seen = 0, nil
	hub.Subscribe(function(changes)
		calls = calls + 1
		seen = changes
	end)
	flush()
	equal(calls, 0, "the baseline calls nobody")
	hub.Queue()
	hub.Queue()
	hub.Queue()
	equal(#env.timers, 1, "three Queue calls in a frame arm one timer")
	equal(calls, 0, "nothing is dispatched synchronously")
	flush()
	equal(calls, 0, "an unchanged burst calls nobody")
	state.stop = "b"
	hub.Queue()
	hub.Queue()
	flush()
	equal(calls, 1, "one burst calls once")
	check(seen.stop == true, "the changed channel is named")
	check(seen.journey == nil and seen.status == nil, "the unchanged channels are not")
	state.stop, state.journey = "c", "beta"
	hub.Queue()
	flush()
	equal(calls, 2, "the next burst calls again")
	check(seen.stop == true and seen.journey == true, "both changed channels are named")
	check(seen.status == nil, "and only them")
	equal(#env.timers, 0, "the timer is spent")
end

-- Each subscriber gets its own fresh table ----------------------------------------------------------------------
do
	local state = { stop = "a", journey = "alpha", status = "running" }
	local hub = Hub(state)
	local first, second
	hub.Subscribe(function(changes)
		first = changes
	end)
	hub.Subscribe(function(changes)
		second = changes
	end)
	flush()
	state.stop = "b"
	hub.Queue()
	flush()
	check(first ~= nil and second ~= nil, "both subscribers hear the change")
	check(first ~= second, "each gets its own table")
	check(first.stop == true and second.stop == true, "with the same change named")
end

-- A subscriber added by a callback waits for the next burst -----------------------------------------------------
do
	local state = { stop = "a", journey = "alpha", status = "running" }
	local hub = Hub(state)
	local calls, lateCalls = 0, 0
	local lateChanges
	local joined = false
	hub.Subscribe(function()
		calls = calls + 1
		if not joined then
			joined = true
			hub.Subscribe(function(changes)
				lateCalls = lateCalls + 1
				lateChanges = changes
			end)
		end
	end)
	flush()
	state.stop = "b"
	hub.Queue()
	flush()
	equal(calls, 1, "the first subscriber hears the burst")
	equal(lateCalls, 0, "the subscriber added during it waits")
	state.stop = "c"
	hub.Queue()
	flush()
	equal(lateCalls, 1, "and hears the next burst")
	check(lateChanges.stop == true, "with that burst's change")
end

-- An erroring callback does not stop the others -----------------------------------------------------------------
do
	local state = { stop = "a", journey = "alpha", status = "running" }
	local hub = Hub(state)
	local context = ForeverCore.Register("KitAddon")
	local before = #context.CaughtErrors()
	local order = {}
	hub.Subscribe(function()
		order[#order + 1] = "first"
		error("Interface/AddOns/KitAddon/Core.lua:1: subscriber failed")
	end)
	hub.Subscribe(function()
		order[#order + 1] = "second"
	end)
	flush()
	state.stop = "b"
	hub.Queue()
	flush()
	equal(#order, 2, "both callbacks ran")
	equal(order[1], "first", "in subscription order")
	equal(order[2], "second", "the error did not stop the second")
	equal(#context.CaughtErrors(), before + 1, "the error reached the addon's error handler")
end

-- Unsubscribe, twice, and no timer once nobody listens ----------------------------------------------------------
do
	local state = { stop = "a", journey = "alpha", status = "running" }
	local hub = Hub(state)
	local calls = 0
	local unsubscribe = hub.Subscribe(function()
		calls = calls + 1
	end)
	unsubscribe()
	unsubscribe()
	state.stop = "b"
	hub.Queue()
	equal(#env.timers, 0, "a hub with no subscriber arms no timer after unsubscribing")
	flush()
	equal(calls, 0, "and the callback never runs")
end

-- ready() false skips the dispatch and the reads -----------------------------------------------------------------
do
	local state = { stop = "a", journey = "alpha", status = "running" }
	local ready = false
	local reads, calls = 0, 0
	local hub = kit.Hub("KitAddon", {
		stop = function()
			reads = reads + 1
			return state.stop
		end,
	}, function()
		return ready
	end)
	local seen
	hub.Subscribe(function(changes)
		calls = calls + 1
		seen = changes
	end)
	equal(reads, 0, "the baseline reads no key while the addon is working")
	state.stop = "b"
	hub.Queue()
	flush()
	equal(reads, 0, "the dispatch reads no key while the addon is working")
	equal(calls, 0, "and sends nothing")
	ready = true
	hub.Queue()
	flush()
	equal(calls, 1, "the settled hub dispatches")
	check(seen.stop == true, "with the change it could not see before")
end

-- The first subscriber takes the baseline -----------------------------------------------------------------------
do
	local state = { stop = "a", journey = "alpha", status = "running" }
	local hub = Hub(state)
	local calls, seen = 0, nil
	hub.Subscribe(function(changes)
		calls = calls + 1
		seen = changes
	end)
	flush()
	equal(calls, 0, "what the channels read when the first subscriber joined is the baseline")
	state.stop = "b"
	hub.Queue()
	flush()
	equal(calls, 1, "only a later change is heard")
	check(seen.stop == true, "and it is named")
end

-- A later first subscriber takes a new baseline -----------------------------------------------------------------
do
	local state = { stop = "a", journey = "alpha", status = "running" }
	local hub = Hub(state)
	local calls = 0
	local unsubscribe = hub.Subscribe(function()
		calls = calls + 1
	end)
	flush()
	unsubscribe()
	state.stop = "b"
	hub.Queue()
	equal(#env.timers, 0, "the gap arms no timer")
	hub.Subscribe(function()
		calls = calls + 1
	end)
	flush()
	equal(calls, 0, "the new first subscriber takes what the channels read then as its baseline")
	state.stop = "c"
	hub.Queue()
	flush()
	equal(calls, 1, "and hears only the next change")
end

-- A non-function callback is an error ---------------------------------------------------------------------------
do
	local hub = Hub({ stop = "a" })
	local ok, message = pcall(hub.Subscribe, "not a function")
	check(ok == false, "a non-function subscriber is refused")
	check(
		tostring(message):find("KitAddon.API.Subscribe: callback must be a function", 1, true) ~= nil,
		"and the message names the addon and the call"
	)
end

print(("api_kit_spec: %d checks passed"):format(checks))
