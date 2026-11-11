-- ForeverCore's public API, loaded from the TOC the way the client loads it: one copy of every shared file, one
-- global, and per-addon contexts that keep their own errors, report and markers.
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

-- The TOC's files, in order, the way the client loads them. XML templates are registered by the client loader; this
-- fake client runs Lua files only.
local Toc = dofile(".agents/skills/wow-forever-addon/tooling/forever_sim/toc.lua")
local function tocFiles()
	local files = {}
	for _, entry in ipairs(Toc.files(".", "ForeverCore.toc")) do
		if entry.kind == "lua" then
			files[#files + 1] = entry.path
		end
	end
	return files
end

Client()
local ns = {}
for _, path in ipairs(tocFiles()) do
	-- Core's own quest list needs the full native tracker template, which this fake client does not build. The
	-- tracker host has already captured its native frame, so hiding it here only skips that optional section.
	local native = env.ObjectiveTrackerFrame
	if path == "UI/TrackerQuests.lua" then
		env.ObjectiveTrackerFrame = nil
	end
	local chunk = assert(loadfile(path), path)
	setfenv(chunk, env)
	chunk("ForeverCore", ns)
	env.ObjectiveTrackerFrame = native
end
local ForeverCore = env.ForeverCore
check(type(ForeverCore) == "table", "the TOC publishes ForeverCore")
equal(ForeverCore.API, 1, "the interface version is 1")
check(type(ForeverCore.Register) == "function", "Register is the per-addon factory")
check(type(ForeverCore.ContextMenu) == "function", "ContextMenu is the shared menu")
check(ForeverCore.ContextMenu == ns.ContextMenu, "and it is the module UI/ContextMenu.lua built")
check(rawequal(env.ForeverTrackerHost, ns.TrackerHost), "ForeverTrackerHost publishes core's one host")
check(env.ForeverFamily == nil, "ForeverFamily is gone")
check(env.ForeverLeaderboards == nil, "ForeverLeaderboards is gone")
check(env.ForeverPeerStats == nil, "ForeverPeerStats is gone")
check(env.ForeverQuestLogTabs == nil, "ForeverQuestLogTabs is gone")
check(ForeverCore.ProfessionTabs == ns.ProfessionTabs, "ForeverCore publishes the ProfessionTabs module")
check(env.ForeverErrorJournal == nil, "ForeverErrorJournal is gone")
check(env.ForeverDebugLog == nil, "ForeverDebugLog is gone")
check(env.ForeverMinimapButtons == nil, "ForeverMinimapButtons is gone")
check(env.ForeverMapMarkers == nil, "ForeverMapMarkers is gone")
check(ForeverCore.Attach == nil, "the old Attach helper is gone")
check(ForeverCore.Defaults == nil, "the old Defaults field is gone")
check(env.ForeverCoreDB == nil, "saved variables load after the files")

-- A first install: the client fires ForeverCore's ADDON_LOADED with no saved table. Core.lua's one handler makes it,
-- builds the host's settings and attaches core's own journal and log before any consumer registers.
local function fireAddonLoaded(addon)
	for _, frame in ipairs(created) do
		if frame.events and frame.events.ADDON_LOADED and frame.scripts and frame.scripts.OnEvent then
			frame.scripts.OnEvent(frame, "ADDON_LOADED", addon)
			return true
		end
	end
	return false
end
check(fireAddonLoaded("ForeverCore"), "the core's ADDON_LOADED handler runs")
check(type(env.ForeverCoreDB) == "table", "a first install gets a saved table")
check(type(env.ForeverCoreDB.trackerHost) == "table", "with the host's settings")
check(type(env.ForeverCoreDB.errors) == "table", "core's journal is attached")
check(type(env.ForeverCoreDB.log) == "table", "core's log ring is attached")

-- Two addons, each with its own saved table.
local A = ForeverCore.Register("AddonA", { db = { errors = {} } })
local B = ForeverCore.Register("AddonB", { db = { errors = {} } })
check(ForeverCore.Register("AddonA") == A, "Register is idempotent")
check(A.Report ~= B.Report, "each addon has its own report window")
check(A.MapCanvas ~= B.MapCanvas, "and its own map markers")

-- An error is attributed by the exact folder its stack names.
local ok = A.SafeCall("A borrowed error", function()
	error("Interface/AddOns/AddonA/Core.lua:1: borrow failed")
end)
check(ok == false, "a failing SafeCall returns false")
equal(#A.CaughtErrors(), 1, "AddonA keeps its own error")
equal(#B.CaughtErrors(), 0, "AddonB never sees it")
equal(#ForeverCore.Register("ForeverCore").CaughtErrors(), 0, "and neither does ForeverCore")

-- An error outside SafeCall goes through the one handler to the addon its stack names.
env.errorHandler("Interface/AddOns/AddonB/Core.lua:2: unwrapped")
equal(#B.CaughtErrors(), 1, "the one handler attributes an unwrapped error to AddonB")
equal(#A.CaughtErrors(), 1, "and leaves AddonA alone")

-- A blocked action names the addon the client blamed.
local blocked = created[1]
for _, frame in ipairs(created) do
	if frame.events and frame.events.ADDON_ACTION_BLOCKED then
		blocked = frame
		break
	end
end
check(blocked.events.ADDON_ACTION_BLOCKED == true, "SafeCall installs the one action-blocked frame")
blocked.scripts.OnEvent(blocked, "ADDON_ACTION_BLOCKED", "AddonB", "SetPoint")
local found = false
for _, entry in ipairs(B.CaughtErrors()) do
	if entry.kind == "blocked" and entry.message:find("SetPoint", 1, true) then
		found = true
	end
end
check(found, "a blocked action lands in the blamed addon's journal")
equal(#A.CaughtErrors(), 1, "and not in the other addon's")

-- A wrapped failure belongs to the addon that wrapped the call: every such stack also runs through ForeverCore's
-- SafeCall, so matching folders would file it under ForeverCore and any addon it passed through.
local beforeA, beforeB = #A.CaughtErrors(), #B.CaughtErrors()
local beforeCore = #ForeverCore.Register("ForeverCore").CaughtErrors()
B.SafeCall("borrowed call", function()
	error("Interface/AddOns/AddonA/Core.lua:3: borrowed failure")
end)
equal(#B.CaughtErrors(), beforeB + 1, "the error lands in the addon that wrapped the call")
equal(#A.CaughtErrors(), beforeA, "not in another addon its message names")
equal(#ForeverCore.Register("ForeverCore").CaughtErrors(), beforeCore, "nor in ForeverCore")

-- The report header names the addon and its version.
local header = A.Report.Text({})
check(header:find("AddonA 9.9.9", 1, true) ~= nil, "the report names AddonA and its version")
check(header:find("AddonB", 1, true) == nil, "and not another addon")

-- One tracker host, shared by every addon, so its scale is one setting.
local host = ForeverCore.TrackerHost
check(host ~= nil, "there is one tracker host")
check(rawequal(host, ns.TrackerHost), "and ForeverCore publishes it")
host.SetScale(1.25)
equal(host.GetScale(), 1.25, "the scale is one value")
check(A.TrackerHost == nil and B.TrackerHost == nil, "no addon owns a second host")
check(rawequal(ForeverCore.TrackerHost, host), "both addons read the same host")

-- The migration copies the first legacy tracker table offered, once.
local legacy = widget("Frame")
legacy.legacySettings = { scale = 1.5, attached = false, locked = true, x = 100, y = -200, backdropOpacity = 0.5 }
host.Attach(legacy)
local settings = env.ForeverCoreDB.trackerHost
equal(settings.scale, 1.5, "the legacy scale is copied")
equal(settings.attached, false, "the legacy attachment is copied")
equal(settings.locked, true, "the legacy Lock is copied")
equal(settings.x, 100, "the legacy x is copied")
equal(settings.y, -200, "the legacy y is copied")
equal(settings.backdropOpacity, 0.5, "the legacy backdrop is copied")
equal(settings.migrated, true, "the copy is marked done")
local later = widget("Frame")
later.legacySettings = { scale = 0.5, attached = true }
host.Attach(later)
equal(env.ForeverCoreDB.trackerHost.scale, 1.5, "a later offer changes nothing")

print(("api_spec: %d checks passed"):format(checks))
