-- Shared scaffolding for the Forever Leaderboards specs: a mocked client, its loader and the board fixtures.
local harness = {}

local PATH = "UI/Leaderboards.lua"
local DATA_PATH = "Core/LeaderboardsData.lua"

local checks = 0
function harness.check(value, message)
	assert(value, message)
	checks = checks + 1
end

function harness.equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

function harness.checks()
	return checks
end

-- Client mock ----------------------------------------------------------------------------------------------------
harness.frames, harness.named = {}, {}
harness.unitNames, harness.unitClasses, harness.guildMembers = {}, {}, {}
harness.guildCalls = 0
harness.serverTime, harness.weekRemaining = 1700000000, 100000
local Create
local function noop() end
harness.noop = noop

local Widget = {}
Widget.__index = function(_, key)
	return Widget[key] or noop
end

function Widget:SetScript(event, handler)
	self.scripts[event] = handler
end

function Widget:GetScript(event)
	return self.scripts[event]
end

function Widget:HookScript(event, handler)
	self.hooks[event] = self.hooks[event] or {}
	self.hooks[event][#self.hooks[event] + 1] = handler
end

function Widget:Show()
	self.shown = true
	if self.scripts.OnShow then
		self.scripts.OnShow(self)
	end
end

function Widget:Hide()
	self.shown = false
end

function Widget:IsShown()
	return self.shown ~= false
end

function Widget:SetShown(shown)
	if shown then
		self:Show()
	else
		self:Hide()
	end
end

function Widget:SetText(text)
	self.text = text
end

function Widget:GetText()
	return self.text
end

function Widget:SetTextColor(r, g, b)
	self.textColor = { r, g, b }
end

function Widget:SetChecked(checked)
	self.checked = checked and true or false
end

function Widget:GetChecked()
	return self.checked == true
end

function Widget:SetEnabled(enabled)
	self.enabled = enabled
end

function Widget:IsEnabled()
	return self.enabled ~= false
end

function Widget:SetWidth(width)
	self.width = width
end

function Widget:GetWidth()
	return self.width or 0
end

function Widget:SetHeight(height)
	self.height = height
end

function Widget:GetHeight()
	return self.height or 0
end

function Widget:SetSize(width, height)
	self.width, self.height = width, height
end

function Widget:SetPoint(point)
	self.points[point] = true
end

function Widget:GetParent()
	return self.parent
end

function Widget:SetAtlas(atlas)
	self.atlas = atlas
end

function Widget:SetTexture(texture)
	self.texture = texture
end

function Widget:SetAllPoints()
	self.allPoints = true
end

function Widget:SetTitle(title)
	self.title = title
end

function Widget:GetPortrait()
	return self.portrait
end

function Widget:SetDefaultText(text)
	self.defaultText = text
end

function Widget:SetupMenu(generator)
	self.menu = generator
end

-- A dropdown's own OpenMenu: the window's gamepad wrapper calls it with the interface off, and records the call.
function Widget:OpenMenu()
	self.openedMenus = self.openedMenus + 1
end

function Widget:SetCustomOnMouseUpHandler(handler)
	self.mouseUp = handler
end

function Widget:SetDataProvider(provider)
	self.provider = provider
	self.buttons = {}
	local view = rawget(self, "view")
	if view and view.initializer then
		for _, entry in ipairs(provider and provider.entries or {}) do
			local button = Create("Button", self)
			self.buttons[#self.buttons + 1] = button
			view.initializer(button, entry)
		end
	end
end

function Widget:GetUnit()
	return self.unitName, self.unit
end

function Widget:AddLine(text, r, g, b)
	local lines = rawget(self, "lines")
	if not lines then
		lines = {}
		self.lines = lines
	end
	lines[#lines + 1] = { text = text, r = r, g = g, b = b }
end

function Widget:Click()
	if self.scripts.OnClick then
		self.scripts.OnClick(self)
	end
end

function Widget:ClickTab()
	if self.mouseUp then
		self.mouseUp(self, "LeftButton", true)
	end
end

function Widget:CreateFontString()
	return Create("FontString", self)
end

function Widget:CreateTexture()
	return Create("Texture", self)
end

function Create(kind, parent, template)
	local widget = setmetatable({
		kind = kind,
		parent = parent,
		template = template,
		scripts = {},
		hooks = {},
		children = {},
		points = {},
		shown = true,
		openedMenus = 0,
	}, Widget)
	if parent then
		parent.children[#parent.children + 1] = widget
	end
	if template == "PortraitFrameTemplate" then
		widget.portrait = Create("Texture", widget)
	end
	if template == "LargeSideTabButtonTemplate" then
		widget.Icon = Create("Texture", widget)
	end
	if kind == "CheckButton" then
		widget.checked = false
	end
	harness.frames[#harness.frames + 1] = widget
	return widget
end
harness.Create = Create

function harness.Client()
	harness.frames, harness.named, harness.unitNames = {}, {}, { player = { "Me" } }
	harness.unitClasses, harness.guildMembers, harness.guildCalls = { player = "HUNTER" }, {}, 0
	harness.serverTime, harness.weekRemaining = 1700000000, 100000
	local env = setmetatable({
		UIParent = Create("Frame"),
		UISpecialFrames = {},
		tContains = function(list, item)
			for _, value in ipairs(list) do
				if value == item then
					return true
				end
			end
			return false
		end,
		CreateFrame = function(kind, name, parent, template)
			local widget = Create(kind, parent, template)
			if name then
				harness.named[name] = widget
			end
			return widget
		end,
		UnitName = function(unit)
			local found = harness.unitNames[unit]
			if found then
				return found[1], found[2]
			end
			return "Me"
		end,
		UnitClass = function(unit)
			local class = harness.unitClasses[unit]
			if class then
				return class, class
			end
		end,
		IsInRaid = function()
			return false
		end,
		Ambiguate = function(name, context)
			if type(name) ~= "string" then
				return name
			end
			if context == "short" then
				return name:match("^([^%-]+)") or name
			end
			return name
		end,
		GetNumGuildMembers = function()
			-- The client returns (numMembers, numOnline); the second must not reach tonumber's base (#587).
			return #harness.guildMembers, 1
		end,
		GetGuildRosterInfo = function(index)
			harness.guildCalls = harness.guildCalls + 1
			local member = harness.guildMembers[index]
			if not member then
				return nil
			end
			-- name, rank, rankIndex, level, class, zone, note, officerNote, online, status, classFileName
			return member.name, nil, nil, nil, nil, nil, nil, nil, nil, nil, member.class
		end,
		GetNormalizedRealmName = function()
			return "MyRealm"
		end,
		GetServerTime = function()
			return harness.serverTime
		end,
		C_DateAndTime = {
			GetSecondsUntilWeeklyReset = function()
				return harness.weekRemaining
			end,
		},
		CreateDataProvider = function(entries)
			return { entries = entries }
		end,
		CreateScrollBoxListLinearView = function()
			return {
				SetElementInitializer = function(self, template, initializer)
					self.template, self.initializer = template, initializer
				end,
				SetElementExtent = function(self, extent)
					self.extent = extent
				end,
				SetPadding = noop,
			}
		end,
		ScrollUtil = {
			InitScrollBoxListWithScrollBar = function(box, _, view)
				-- The client's ScrollBoxListView reads a row's height from its XML template; a bare frame type has
				-- none, so it raises "Failed to obtain template info" unless the view has a fixed extent (#174).
				local bare = view.template == "Button" or view.template == "Frame"
				assert(
					not bare or view.extent,
					"a templateless " .. tostring(view.template) .. " row needs SetElementExtent"
				)
				box.view = view
			end,
		},
		ScrollBoxConstants = { RetainScrollPosition = 1 },
		SlashCmdList = {},
		RAID_CLASS_COLORS = {
			HUNTER = {
				GetRGB = function()
					return 0.67, 0.83, 0.45
				end,
			},
			MAGE = {
				GetRGB = function()
					return 0.25, 0.78, 0.92
				end,
			},
			PRIEST = {
				GetRGB = function()
					return 1, 1, 1
				end,
			},
			ROGUE = {
				GetRGB = function()
					return 1, 0.96, 0.41
				end,
			},
			WARRIOR = {
				GetRGB = function()
					return 0.78, 0.61, 0.43
				end,
			},
		},
		NORMAL_FONT_COLOR = {
			GetRGB = function()
				return 1, 0.82, 0
			end,
		},
		GRAY_FONT_COLOR = {
			GetRGB = function()
				return 0.5, 0.5, 0.5
			end,
		},
		GREEN_FONT_COLOR = {
			GetRGB = function()
				return 0.12, 1, 0
			end,
		},
		HIGHLIGHT_FONT_COLOR = {
			GetRGB = function()
				return 1, 1, 1
			end,
		},
	}, { __index = _G })
	env._G = env
	env.GameTooltip = Create("GameTooltip")
	harness.env = env
	return env
end

function harness.PhraseLocale()
	return setmetatable({}, {
		__index = function(_, phrase)
			return phrase
		end,
	})
end

function harness.Load(path, dataPath)
	local ns = { L = harness.PhraseLocale() }
	setfenv(assert(loadfile(dataPath or DATA_PATH)), harness.env)("Test", ns)
	setfenv(assert(loadfile(path or PATH)), harness.env)("Test", ns)
	return ns.Leaderboards, ns
end

function harness.row(name, value, extra, you, class)
	return { name = name, value = value, extra = extra, you = you, class = class }
end

-- The menu root a dropdown's SetupMenu generator builds into: it records the radios, in order, and counts dividers.
function harness.MenuRoot()
	local root = { radios = {}, dividers = 0 }
	root.SetScrollMode = function() end
	root.CreateDivider = function()
		root.dividers = root.dividers + 1
	end
	root.CreateRadio = function(_, text, getter, onClick)
		root.radios[#root.radios + 1] = { text = text, getter = getter, onClick = onClick }
	end
	return root
end

harness.ICON = "Interface\\Icons\\INV_Misc_Trophy_Argent"

function harness.spec(key, week, all, extra)
	return {
		title = key,
		metric = "Metric " .. key,
		icon = harness.ICON,
		board = function(scope)
			return scope == "week" and week or all
		end,
		sharing = function()
			return not extra or extra.shared ~= false
		end,
		setSharing = function(value)
			if extra then
				extra.shared = value
			end
		end,
	}
end

return harness
