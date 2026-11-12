-- The fake client ForeverCore's TOC specs load into: one CreateFrame over widgets that remember what the shared files
-- set, every global the files read, and the frames created so a spec can fire an event. api_spec.lua loads the whole
-- TOC with it, and expose_subset_spec.lua loads it without UI/Credits.lua.

local M = {}

-- A tiny client: frames remember what the modules set, and every method the shared files call exists. Methods the
-- modules do not use are no-ops, so a new read in a shared file fails here rather than at runtime.
local created = {}
local function texture()
	local value = { points = {} }
	local methods = {}
	function methods:SetPoint(...)
		self.points[#self.points + 1] = { ... }
	end
	function methods:ClearAllPoints()
		self.points, self.point = {}, nil
	end
	function methods:SetAllPoints(owner)
		self.allPoints = owner or true
	end
	function methods:GetParent()
		return self.parent
	end
	function methods:AddMaskTexture(mask)
		self.masks = rawget(self, "masks") or {}
		self.masks[#self.masks + 1] = mask
	end
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
	local function child(self, textureName, drawLayer, objectType)
		local value_ = texture()
		value_.name, value_.layer, value_.parent, value_.kind = textureName, drawLayer, self, objectType
		self.children[#self.children + 1] = value_
		return value_
	end
	function methods:CreateTexture(textureName, drawLayer)
		return child(self, textureName, drawLayer, "Texture")
	end
	function methods:CreateMaskTexture(textureName, drawLayer)
		return child(self, textureName, drawLayer, "MaskTexture")
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

M.widget = widget

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
		},
		CreateFromMixins = function(...)
			local result = {}
			for _, mixin in ipairs({ ... }) do
				env.Mixin(result, mixin)
			end
			return result
		end,
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

-- A fresh client: its globals, the frames it has created, and the frames by name.
function M.new()
	local named = Client()
	return env, created, named
end

return M
