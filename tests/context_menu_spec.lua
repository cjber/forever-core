-- UI/ContextMenu.lua against a mocked client: the suite's own menu opens instead of Blizzard's, navigates nested
-- entries, scrolls a long level, and follows an owner's hide.
local checks = 0
local function check(value, message)
	checks = checks + 1
	assert(value, message)
end
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local function region(kind, parent)
	local widget = {
		kind = kind,
		parent = parent,
		shown = true,
		mouseOver = false,
		width = 0,
		height = 0,
		fontString = false,
		enabled = true,
		scripts = {},
		hooks = {},
		events = {},
		textures = {},
		text = "",
		rows = {},
		points = {},
	}
	local methods = {}
	function methods:SetPoint(...)
		self.point = { ... }
		self.points[#self.points + 1] = { ... }
	end
	function methods:ClearAllPoints()
		self.point = nil
		self.points = {}
	end
	function methods:SetFrameStrata(setting)
		self.strata = setting
	end
	function methods:SetClampedToScreen(setting)
		self.clamped = setting
	end
	function methods:EnableMouse(setting)
		self.mouse = setting
	end
	function methods:SetScript(name, fn)
		self.scripts[name] = fn
	end
	function methods:GetScript(name)
		return self.scripts[name]
	end
	function methods:HookScript(name, fn)
		self.hooks[name] = self.hooks[name] or {}
		self.hooks[name][#self.hooks[name] + 1] = fn
	end
	function methods:RegisterEvent(event)
		self.events = self.events or {}
		self.events[event] = true
	end
	function methods:UnregisterEvent(event)
		if self.events then
			self.events[event] = nil
		end
	end
	function methods:SetSize(width, height)
		self.width, self.height = width, height
	end
	function methods:SetWidth(width)
		self.width = width
	end
	function methods:GetWidth()
		return self.width or 0
	end
	function methods:SetHeight(height)
		self.height = height
	end
	function methods:GetHeight()
		return self.height or 0
	end
	function methods:SetText(text)
		self.text = text
		if rawget(self, "fontString") then
			self.fontString:SetText(text)
		end
	end
	function methods:GetText()
		return self.text
	end
	function methods:GetTextWidth()
		return #(self.text or "") * 7
	end
	function methods:SetFontString(fontString)
		self.fontString = fontString
	end
	function methods:SetJustifyH(setting)
		self.justify = setting
	end
	function methods:SetNormalFontObject(setting)
		self.normalFont = setting
	end
	function methods:SetDisabledFontObject(setting)
		self.disabledFont = setting
	end
	function methods:SetEnabled(setting)
		self.enabled = setting
	end
	function methods:IsEnabled()
		return self.enabled ~= false
	end
	function methods:SetMotionScriptsWhileDisabled(setting)
		self.motionWhileDisabled = setting
	end
	function methods:SetShown(setting)
		self.shown = setting == true
	end
	function methods:Show()
		self.shown = true
		if self.scripts.OnShow then
			self.scripts.OnShow(self)
		end
	end
	function methods:Hide()
		self.shown = false
		if self.scripts.OnHide then
			self.scripts.OnHide(self)
		end
		for _, fn in ipairs(self.hooks.OnHide or {}) do
			fn(self)
		end
	end
	function methods:IsShown()
		return self.shown
	end
	function methods:IsVisible()
		return self.shown
	end
	function methods:IsMouseOver()
		return self.mouseOver
	end
	function methods:GetParent()
		return rawget(self, "parent")
	end
	function methods:CreateTexture(layer)
		local texture = region("Texture", self)
		texture.layer = layer
		function texture.SetAtlas(texture_, atlas, useAtlasSize)
			texture_.atlas, texture_.useAtlasSize = atlas, useAtlasSize
		end
		function texture.SetAllPoints(texture_)
			texture_.allPoints = true
		end
		function texture.SetColorTexture(texture_, r, g, b, a)
			texture_.color = { r, g, b, a }
		end
		function texture.SetDrawLayer(texture_, drawLayer, subLevel)
			texture_.drawLayer, texture_.subLevel = drawLayer, subLevel
		end
		self.textures[#self.textures + 1] = texture
		return texture
	end
	function methods:CreateFontString(name, layer, font)
		local text = region("FontString", self)
		text.name, text.layer, text.font = name, layer, font
		return text
	end
	function methods:SetScrollChild(child)
		self.scrollChild = child
	end
	function methods:SetVerticalScroll(setting)
		self.scroll = setting
	end
	setmetatable(widget, {
		__index = function(_, key)
			return methods[key] or function() end
		end,
	})
	return widget
end

local env = {
	UIParent = region("Frame"),
	UISpecialFrames = {},
	menu = {},
}
setmetatable(env, { __index = _G })
env._G = env
env.GameTooltip = {
	title = nil,
	SetOwner = function(self, owner)
		self.owner = owner
	end,
	Show = function(self)
		self.shown = true
	end,
	Hide = function(self)
		self.shown = false
	end,
}
env.GameTooltip_Hide = function()
	env.GameTooltip:Hide()
end
env.GameTooltip_SetTitle = function(tooltip, text)
	tooltip.title = text
end
env.WorldMapFrame = region("Frame", env.UIParent)
env.CreateFrame = function(kind, name, parent, template)
	local frame = region(kind, parent)
	frame.name, frame.template = name, template
	if template == "ScrollFrameTemplate" then
		frame.ScrollBar = region("ScrollBar", frame)
	end
	if name then
		env[name] = frame
	end
	return frame
end
local callbacks = {}
env.EventRegistry = {
	RegisterCallback = function(_, event, callback, owner)
		callbacks[event] = callbacks[event] or {}
		callbacks[event][#callbacks[event] + 1] = { callback = callback, owner = owner }
	end,
	TriggerEvent = function(_, event, ...)
		for _, entry in ipairs(callbacks[event] or {}) do
			entry.callback(entry.owner, ...)
		end
	end,
}

local ns = {
	L = setmetatable({}, {
		__index = function(_, key)
			if key == "MENU_BACK" then
				return "Back"
			end
			return key
		end,
	}),
}
local chunk = assert(loadfile("UI/ContextMenu.lua"))
setfenv(chunk, env)
chunk("ContextMenuSpec", ns)
env.MenuUtil = {
	CreateContextMenu = function()
		error("the native menu can assert on this client build")
	end,
}

local owner = env.CreateFrame("Button", nil, env.UIParent)
local calls = 0
ns.ContextMenu(owner, function(_, root)
	root:CreateTitle("Title")
	root:CreateButton("Disabled", function()
		calls = calls + 100
	end):SetEnabled(false)
	local first = root:CreateButton("First")
	local second = first:CreateButton("Second")
	second:CreateButton("Action", function()
		calls = calls + 1
	end)
end)
local popup = env.ForeverCoreContextMenu
check(popup ~= nil, "the suite's popup is built")
equal(popup:IsShown(), true, "owned menu opens")
equal(popup.rows[3]:GetHeight(), 20, "compact dropdown rows")
equal(popup.rows[3].fontString:GetText(), "First", "button uses its compact text label")
equal(popup.rows[3].arrow.atlas, "common-dropdown-icon-next", "a submenu carries the client's expand arrow")
equal(popup.rows[3].arrow.shown, true, "the submenu arrow is shown")
equal(popup.rows[3].indicator.shown, false, "a plain submenu row carries no checkbox")
equal(popup:GetParent(), env.UIParent, "popup escapes owner scroll clipping")
equal(popup.rows[1]:IsEnabled(), false, "title not actionable")
equal(popup.rows[2]:IsEnabled(), false, "disabled action stays disabled")
popup.rows[3].scripts.OnClick(popup.rows[3])
equal(popup.rows[1]:GetText(), "Back", "submenu has back")
popup.rows[2].scripts.OnClick(popup.rows[2])
popup.rows[1].scripts.OnClick(popup.rows[1])
equal(popup.rows[1]:GetText(), "Back", "deep back retains parent navigation")
popup.rows[1].scripts.OnClick(popup.rows[1])
equal(popup.rows[3]:GetText(), "First", "back returns root")
popup.rows[3].scripts.OnClick(popup.rows[3])
popup.rows[2].scripts.OnClick(popup.rows[2])
popup.rows[2].scripts.OnClick(popup.rows[2])
equal(calls, 1, "leaf executes once")
equal(popup:IsShown(), false, "leaf closes menu")

-- The tracker's background choice is a set of radios with Blizzard's MenuUtil contract.
local picked = 0.5
ns.ContextMenu(owner, function(_, root)
	for _, value in ipairs({ 0.5, 1 }) do
		root:CreateRadio(value * 100 .. "%", function(data)
			return picked == data
		end, function(data)
			picked = data
		end, value)
	end
end)
equal(popup.rows[1]:GetText(), "50%", "a radio label carries no marker text")
equal(popup.rows[1].indicator.atlas, "common-dropdown-tickradial", "a radio draws the client's radio art")
equal(popup.rows[1].indicator.shown, true, "the radio art is shown")
equal(popup.rows[1].tick.atlas, "common-dropdown-icon-radialtick-yellow", "a chosen radio draws the client's dot")
equal(popup.rows[1].tick.shown, true, "the chosen radio is marked")
equal(popup.rows[2]:GetText(), "100%", "the other radio label carries no marker text")
equal(popup.rows[2].tick.shown, false, "the other radio is not")
popup.rows[2].scripts.OnClick(popup.rows[2])
equal(picked, 1, "a radio hands its data to the setter")

-- A checkbox row draws the client's tick square.
local attached = false
ns.ContextMenu(owner, function(_, root)
	root:CreateCheckbox("Attach", function()
		return attached
	end, function()
		attached = not attached
	end)
end)
local checkRow = popup.rows[1]
equal(checkRow:GetText(), "Attach", "a checkbox label carries no marker text")
equal(checkRow.indicator.atlas, "common-dropdown-ticksquare", "a checkbox draws the client's tick square")
equal(checkRow.indicator.shown, true, "the tick square is shown")
equal(checkRow.tick.atlas, "common-dropdown-icon-checkmark-yellow", "a checked box draws the client's checkmark")
equal(checkRow.tick.shown, false, "an unchecked box draws no checkmark")
check(checkRow:GetWidth() >= checkRow:GetTextWidth() + 12 + 7 + 16, "the checkbox row holds its art and label")
checkRow.scripts.OnClick(checkRow)
equal(attached, true, "a checkbox toggle writes the setting")
equal(popup:IsShown(), false, "a checkbox toggle closes the menu")

-- A long submenu label still leaves room for the arrow inside its row.
local longSubmenu = "A submenu label long enough to size the row past its minimum"
ns.ContextMenu(owner, function(_, root)
	root:CreateButton(longSubmenu):CreateButton("Inside", function() end)
end)
local longRow = popup.rows[1]
equal(longRow:GetText(), longSubmenu, "a submenu label carries no arrow text")
check(longRow:GetWidth() >= longRow:GetTextWidth() + 17 + 4 + 16, "a submenu row leaves room for its arrow")

-- A long level scrolls, and a level that sets its own extent scrolls past it.
ns.ContextMenu(owner, function(_, root)
	for index = 1, 40 do
		root:CreateButton("Entry " .. index, function() end)
	end
end)
equal(popup:GetHeight() <= 420, true, "long menus fit viewport")
equal(popup.body:GetHeight() > popup:GetHeight(), true, "long menu scrolls")
ns.ContextMenu(owner, function(_, root)
	root:SetScrollMode(100)
	for index = 1, 10 do
		root:CreateButton("Entry " .. index, function() end)
	end
end)
equal(popup:GetHeight(), 114, "a scrolled level stops at its extent")
equal(popup.scroll.ScrollBar:IsShown(), true, "and shows its scroll bar")

-- An owner that hides closes its menu; a card under the map hears the panel manager instead.
owner:Hide()
equal(popup:IsVisible(), false, "owner hide closes visible menu")
owner:Show()
equal(popup:IsShown(), false, "owner reshow does not reopen menu")
local mapOwner = env.CreateFrame("Button", nil, env.WorldMapFrame)
ns.ContextMenu(mapOwner, function(_, root)
	root:CreateButton("On the map")
end)
equal(mapOwner.scripts.OnShow, nil, "a map owner carries no OnShow script")
equal(mapOwner.scripts.OnHide, nil, "a map owner carries no OnHide script")
equal(popup:IsShown(), true, "a map menu opens")
env.EventRegistry:TriggerEvent("UIParentPanelManager.HideUIPanel", env.WorldMapFrame)
equal(popup:IsShown(), false, "hiding the map closes its menu")
ns.ContextMenu(mapOwner, function(_, root)
	root:CreateButton("On the map again")
end)
env.EventRegistry:TriggerEvent("UIParentPanelManager.ForcePanelHide", env.WorldMapFrame)
equal(popup:IsShown(), false, "a forced panel hide closes the map's menu")

-- A click inside keeps the menu open; a click outside closes it.
ns.ContextMenu(owner, function(_, root)
	root:CreateButton("Outside")
end)
popup.mouseOver = true
popup.scripts.OnEvent(popup)
equal(popup:IsShown(), true, "inside click keeps menu open")
popup.mouseOver = false
owner.mouseOver = false
popup.scripts.OnEvent(popup)
equal(popup:IsShown(), false, "outside click closes menu")

-- A long entry widens the whole menu rather than being cut.
local aside = "Overlook Standing - For levels 36-44: the overlook on the ridge"
ns.ContextMenu(owner, function(_, root)
	root:CreateTitle(aside)
	root:CreateButton("Short", function() end)
end)
equal(popup.body:GetWidth() > 296, true, "the body grows past its default")
equal(popup.body:GetWidth(), popup.rows[1]:GetWidth() + 12, "the body holds the longest row")
equal(popup:GetWidth(), popup.body:GetWidth() + 24, "the popup leaves room for the scroll bar")
equal(popup.rows[1]:GetWidth() + 20 >= popup.rows[1]:GetTextWidth(), true, "the longest row is not cut")
equal(popup:GetWidth() > 320, true, "the menu is wider than the old fixed width")

-- A row still cut at the width cap carries its whole text in a tooltip.
local huge = string.rep("Complete objectives - The Greenbelt ", 3)
ns.ContextMenu(owner, function(_, root)
	root:CreateButton(huge, function() end)
end)
local cut = popup.rows[1]
equal(cut:GetTextWidth() > cut:GetWidth() - 20, true, "the row is cut at the width cap")
cut.mouseOver = true
cut.scripts.OnEnter(cut)
equal(env.GameTooltip.title, huge, "a cut row's tooltip holds the whole text")

-- An entry that already has a tooltip keeps it: the row's own text is not shown over it.
ns.ContextMenu(owner, function(_, root)
	local entry = root:CreateButton(huge, function() end)
	entry:SetTooltip(function(tooltip)
		env.GameTooltip_SetTitle(tooltip, "Own tip")
	end)
end)
popup.rows[1].scripts.OnEnter(popup.rows[1])
equal(env.GameTooltip.title, "Own tip", "a row with its own tooltip keeps it")

print(("context_menu_spec: %d checks passed"):format(checks))
