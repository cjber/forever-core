-- UI/ContextMenu.lua against a mocked client: the suite's own menu opens instead of Blizzard's, cascades nested
-- entries beside their rows, scrolls a long level, and follows an owner's hide.
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
	function methods:GetEffectiveScale()
		return (rawget(self, "scale") or 1) * (self:GetParent() and self:GetParent():GetEffectiveScale() or 1)
	end
	function methods:GetRight()
		if rawget(self, "right") then
			return self.right
		end
		if rawget(self, "point") and type(self.point[2]) == "table" then
			return self.point[2]:GetRight() + self.point[4]
		end
		return rawget(self, "right") or 0
	end
	function methods:GetLeft()
		return rawget(self, "left") or 0
	end
	function methods:GetBottom()
		return rawget(self, "bottom") or 0
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
	function methods:SetClampRectInsets(left, right, top, bottom)
		self.clampInsets = { left, right, top, bottom }
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
	function methods:CreateTexture(_, layer)
		local texture = region("Texture", self)
		texture.layer = layer
		function texture.SetAtlas(texture_, atlas, useAtlasSize)
			texture_.atlas, texture_.useAtlasSize = atlas, useAtlasSize
		end
		function texture.SetTexture(texture_, path)
			texture_.texture = path
		end
		function texture.SetBlendMode(texture_, mode)
			texture_.blend = mode
		end
		function texture.SetAlpha(texture_, alpha)
			texture_.alpha = alpha
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
	function methods:LockHighlight()
		self.highlightLocked = true
	end
	function methods:UnlockHighlight()
		self.highlightLocked = false
	end
	function methods:SetScrollChild(child)
		self.scrollChild = child
	end
	function methods:SetVerticalScroll(setting)
		self.scroll = setting
	end
	setmetatable(widget, {
		__index = function(_, key)
			-- An unknown method is a no-op; an unset field reads nil, as on a client frame.
			return methods[key] or (type(key) == "string" and key:match("^%u") and function() end or nil)
		end,
	})
	return widget
end

local pending = {}
local function drain()
	local callbacks = pending
	pending = {}
	for _, fn in ipairs(callbacks) do
		fn()
	end
end

local env = {
	C_Timer = {
		After = function(_, fn)
			pending[#pending + 1] = fn
		end,
	},
	UIParent = region("Frame"),
	UISpecialFrames = {},
	menu = {},
	cursor = { 0, 0 },
}
env.GetCursorPosition = function()
	return env.cursor[1], env.cursor[2]
end
-- Blizzard_SharedXML's InputUtil and FrameUtil as the client has them: the cursor anchor (UIParent is not letterboxed
-- here) and the gamepad interface's quadrant, which a spec sets as env.gamepad and env.quadrant.
env.InputUtil = {
	IsGamepadUIEnabled = function()
		return env.gamepad == true
	end,
	AnchorRegionToCursor = function(menu, point)
		local x, y = env.GetCursorPosition()
		local scale = env.UIParent:GetEffectiveScale()
		menu:ClearAllPoints()
		menu:SetPoint(point, env.UIParent, "BOTTOMLEFT", x / scale, y / scale)
	end,
}
env.FrameUtilQuadrantEnum = { BottomLeft = 1, BottomRight = 2, TopLeft = 3, TopRight = 4 }
env.FrameUtil = {
	GetScreenQuadrant = function()
		return env.quadrant
	end,
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
env.UIParent.right = 4000
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
equal(popup.rows[3]:GetHeight(), 20, "rows are 20 high, as MenuVariants.CreateFontString makes them")
equal(popup.rows[3].fontString:GetText(), "First", "button uses its text label")
equal(popup.rows[3].normalFont, "GameFontHighlight", "rows use the game menu's GameFontHighlight")
equal(popup.rows[1].disabledFont, "GameFontNormal", "a title is the same font in gold")
equal(popup.rows[2].disabledFont, "GameFontDisable", "a disabled row is greyed")
local arrowPath = "Interface\\ChatFrame\\ChatFrameExpandArrow"
equal(popup.rows[3].arrow.texture, arrowPath, "a submenu carries the client's expand arrow")
equal(popup.rows[3].arrow.width, 16, "at its 16-unit size")
equal(popup.rows[3].arrow.shown, true, "the submenu arrow is shown")
equal(popup.rows[3].indicator.shown, false, "a plain submenu row carries no checkbox")
equal(popup:GetParent(), env.UIParent, "popup escapes owner scroll clipping")
equal(popup.rows[1]:IsEnabled(), false, "title not actionable")
equal(popup.rows[2]:IsEnabled(), false, "disabled action stays disabled")
-- Submenus cascade as Blizzard_Menu's do: resting on a row opens its level beside it after 0.33 s, the parent stays
-- open, and there is no Back row.
local function hover(row)
	row.mouseOver = true
	row.scripts.OnEnter(row)
	drain()
	row.mouseOver = false
end
local firstRow = popup.rows[3]
firstRow.mouseOver = true
firstRow.scripts.OnEnter(firstRow)
equal(env.ForeverCoreContextMenu2, nil, "a submenu waits for the pointer to rest")
drain()
local second = env.ForeverCoreContextMenu2
firstRow.mouseOver = false
firstRow.scripts.OnLeave(firstRow)
drain()
equal(second:IsShown(), false, "a submenu the pointer left without entering closes")
equal(popup:IsShown(), true, "and the root stays")
firstRow.mouseOver = true
firstRow.scripts.OnEnter(firstRow)
drain()
firstRow.mouseOver = false
firstRow.scripts.OnLeave(firstRow)
second.mouseOver = true
second.scripts.OnEnter(second)
drain()
second.mouseOver = false
check(second ~= nil and second:IsShown(), "hovering a submenu row opens its level")
equal(popup:IsShown(), true, "the parent level stays open beside it")
equal(second.rows[1]:GetText(), "Second", "the submenu lists its own entries, with no Back row")
equal(second.point[1], "TOPLEFT", "the submenu's top-left corner")
equal(second.point[2], firstRow, "meets its row")
equal(second.point[3], "TOPRIGHT", "at the row's top-right corner")
equal(firstRow.highlightLocked, true, "the opening row stays lit while its submenu is open")
hover(second.rows[1])
local third = env.ForeverCoreContextMenu3
check(third ~= nil and third:IsShown(), "a deeper submenu cascades from the first")
equal(third.rows[1]:GetText(), "Action", "with its own entries")
equal(second:IsShown() and popup:IsShown(), true, "every level above stays open")
hover(firstRow)
equal(third:IsShown(), true, "resting on the open row again keeps its cascade")
hover(popup.rows[2])
equal(second:IsShown(), false, "resting on another row closes the submenu")
equal(third:IsShown(), false, "and every level below it")
equal(firstRow.highlightLocked, false, "and lets its row's highlight go")
equal(popup:IsShown(), true, "the root stays open")
firstRow.mouseOver = true
firstRow.scripts.OnEnter(firstRow)
firstRow.mouseOver = false
drain()
equal(second:IsShown(), false, "a pointer that moved on before the delay opens nothing")
firstRow.scripts.OnClick(firstRow)
equal(second:IsShown(), true, "a click or gamepad press on a submenu row opens it at once")
equal(popup:IsShown(), true, "and keeps the root open")
second.mouseOver = true
popup.scripts.OnEvent(popup)
equal(second:IsShown() and popup:IsShown(), true, "a click inside a submenu keeps the cascade open")
second.mouseOver = false
second.rows[1].scripts.OnClick(second.rows[1])
third.rows[1].scripts.OnClick(third.rows[1])
equal(calls, 1, "leaf executes once")
equal(popup:IsShown(), false, "leaf closes menu")
equal(second:IsShown() or third:IsShown(), false, "and every submenu")

-- A submenu that would leave the screen opens to its row's left instead.
env.UIParent.right = 1000
firstRow.left, firstRow.right = 600, 950
ns.ContextMenu(owner, function(_, root)
	root:CreateTitle("Title")
	root:CreateButton("Disabled"):SetEnabled(false)
	root:CreateButton("First"):CreateButton("Second", function() end)
end)
hover(popup.rows[3])
equal(second.point[1], "TOPRIGHT", "an off-screen submenu flips")
equal(second.point[3], "TOPLEFT", "to its row's left")
firstRow.left = 20
hover(popup.rows[2])
hover(popup.rows[3])
equal(second.point[1], "TOPLEFT", "a submenu with less room on the left stays on the right")
env.UIParent.right, firstRow.left, firstRow.right = 4000, nil, nil
popup:Hide()
equal(second:IsShown(), false, "closing the root closes its submenus")

-- The menu opens at the cursor, as MenuUtil.CreateContextMenu does: a tracker passes its whole section as the owner,
-- whose bottom-right corner can sit far below the clicked title (#850).
owner.right, owner.bottom, owner.scale = 300, 200, 0.625
env.UIParent.scale = 0.8
env.cursor = { 400, 960 }
ns.ContextMenu(owner, function(_, root)
	root:CreateButton("Re-plan action", function()
		calls = calls + 1
	end)
end)
equal(popup.point[1], "TOPLEFT", "the menu's top-left corner sits at the cursor")
equal(popup.point[2], env.UIParent, "menu anchors to the screen instead of its moving owner")
equal(popup.point[3], "BOTTOMLEFT", "menu snapshots coordinates from the screen origin")
equal(popup.point[4], 500, "cursor x is converted to popup effective scale")
equal(popup.point[5], 1200, "cursor y is converted to popup effective scale")
local openedPoint = { unpack(popup.point) }
local openedRight = popup:GetRight()
owner.right, owner.bottom = 500, 400
owner:Hide()
owner:Show()
drain()
equal(popup:IsShown(), true, "a layout hide and reshow keeps the menu open")
equal(popup:GetRight(), openedRight, "owner movement leaves the popup position unchanged")
equal(popup.point[4] == openedPoint[4] and popup.point[5] == openedPoint[5], true, "the menu stays where it opened")
popup.mouseOver = true
popup.scripts.OnEvent(popup)
equal(popup:IsShown(), true, "a click inside the stationary popup keeps its action reachable")
popup.rows[1].scripts.OnClick(popup.rows[1])
equal(calls, 2, "the stationary menu entry still executes")
popup.mouseOver = false

-- Under the gamepad interface a press leaves the cursor parked, so the menu opens beside the owner, toward the
-- screen's middle, as Blizzard's context menus do there.
env.gamepad = true
for _, case in ipairs({
	{ "BottomRight", "BOTTOMRIGHT", "BOTTOMLEFT" },
	{ "BottomLeft", "BOTTOMLEFT", "BOTTOMRIGHT" },
	{ "TopRight", "TOPRIGHT", "TOPLEFT" },
	{ "TopLeft", "TOPLEFT", "TOPRIGHT" },
}) do
	env.quadrant = env.FrameUtilQuadrantEnum[case[1]]
	ns.ContextMenu(owner, function(_, root)
		root:CreateButton("Pad", function() end)
	end)
	equal(popup.point[1], case[2], case[1] .. " owner: the menu's corner")
	equal(popup.point[2], owner, case[1] .. " owner: beside the owner, not the parked cursor")
	equal(popup.point[3], case[3], case[1] .. " owner: the owner's facing corner")
end
env.quadrant = env.FrameUtilQuadrantEnum.TopRight
ns.ContextMenu(owner, function(_, root)
	root:CreateButton("Pad"):CreateButton("Inside", function() end)
end)
popup.rows[1].scripts.OnClick(popup.rows[1])
local padSub = env.ForeverCoreContextMenu2
equal(padSub.point[1], "TOPRIGHT", "a gamepad submenu opens toward the middle")
equal(padSub.point[3], "TOPLEFT", "from its row's facing side")
env.gamepad, env.quadrant = nil, nil
popup:Hide()

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
check(checkRow:GetWidth() >= checkRow:GetTextWidth() + 12 + 7 + 20, "the checkbox row holds its art and label")
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
check(longRow:GetWidth() >= longRow:GetTextWidth() + 16 + 20, "a submenu row leaves room for its arrow")

-- A long level scrolls, and a level that sets its own extent scrolls past it.
ns.ContextMenu(owner, function(_, root)
	for index = 1, 40 do
		root:CreateButton("Entry " .. index, function() end)
	end
end)
equal(popup:GetHeight(), 8 + 406 + 15, "a long menu stops at the default extent inside its insets")
equal(popup.body:GetHeight() > popup:GetHeight(), true, "long menu scrolls")
ns.ContextMenu(owner, function(_, root)
	root:SetScrollMode(100)
	for index = 1, 10 do
		root:CreateButton("Entry " .. index, function() end)
	end
end)
equal(popup:GetHeight(), 8 + 100 + 15, "a scrolled level stops at its extent, inside the menu's insets")
equal(popup.scroll.ScrollBar:IsShown(), true, "and shows its scroll bar")

-- An owner that hides closes its menu; a card under the map hears the panel manager instead.
owner:Hide()
drain()
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
equal(popup.body:GetWidth(), popup.rows[1]:GetTextWidth() + 20, "the body is the longest row plus Blizzard's 20")
equal(popup.rows[2]:GetWidth(), popup.body:GetWidth(), "every row spans the level, so its highlight does")
equal(popup:GetWidth(), popup.body:GetWidth() + 16, "the popup adds its 8-unit side insets")
equal(popup.rows[1]:GetWidth() >= popup.rows[1]:GetTextWidth(), true, "the longest row is not cut")
equal(popup:GetWidth() > 320, true, "the menu is wider than the old fixed width")

-- A row still cut at the width cap carries its whole text in a tooltip.
local huge = string.rep("Complete objectives - The Greenbelt ", 3)
ns.ContextMenu(owner, function(_, root)
	root:CreateButton(huge, function() end)
end)
local cut = popup.rows[1]
equal(cut:GetWidth(), 600, "a very long row stops at the width cap")
equal(cut:GetTextWidth() > cut:GetWidth() - 20, true, "the row is cut at the width cap")
cut.mouseOver = true
cut.scripts.OnEnter(cut)
equal(env.GameTooltip.title, huge, "a cut row's tooltip holds the whole text")

-- A row that fits inside the cap shows all of its text, so it gets no tooltip of its own.
local fits = string.rep("x", 83) -- 581 units: past the cap with Blizzard's 20, still inside the 600-unit row
ns.ContextMenu(owner, function(_, root)
	root:CreateButton(fits, function() end)
end)
env.GameTooltip.title = nil
popup.rows[1].mouseOver = true
popup.rows[1].scripts.OnEnter(popup.rows[1])
equal(popup.rows[1]:GetWidth(), 600, "a row just under the cap stops at the cap")
equal(env.GameTooltip.title, nil, "and, not being cut, shows no tooltip")

-- An entry that already has a tooltip keeps it: the row's own text is not shown over it.
ns.ContextMenu(owner, function(_, root)
	local entry = root:CreateButton(huge, function() end)
	entry:SetTooltip(function(tooltip)
		env.GameTooltip_SetTitle(tooltip, "Own tip")
	end)
end)
popup.rows[1].scripts.OnEnter(popup.rows[1])
equal(env.GameTooltip.title, "Own tip", "a row with its own tooltip keeps it")

-- MenuStyle1: the background reaches past the frame, and the last row ends inside it with Blizzard's 15-unit bottom
-- inset (#875: the old popup set the background to its own edges and its last row, Tracker, sat cut off on the bottom).
ns.ContextMenu(owner, function(_, root)
	root:CreateTitle("Visit Saldean's Farm: Pick up 2")
	root:CreateButton("Go", function() end)
	root:CreateButton("Not this quest"):CreateButton("Inside", function() end)
	root:CreateButton("End journey", function() end)
	root:CreateDivider()
	root:CreateCheckbox("Lock the tracker", function()
		return true
	end, function() end)
	root:CreateButton("Tracker"):CreateButton("Inside", function() end)
end)
local background = popup.background
equal(background.atlas, "common-dropdown-bg", "the background is the game menu's art")
equal(background.alpha, 0.925, "at the game menu's alpha")
local corners = {}
for _, p in ipairs(background.points) do
	corners[p[1]] = p
end
check(corners.TOPLEFT[2] == -10 and corners.TOPLEFT[3] == 3, "the background reaches 10 left and 3 up")
check(corners.BOTTOMRIGHT[2] == 10 and corners.BOTTOMRIGHT[3] == -3, "and 10 right and 3 down")
local scrollAt = {}
for _, p in ipairs(popup.scroll.points) do
	scrollAt[p[1]] = p
end
check(scrollAt.TOPLEFT[2] == 8 and scrollAt.TOPLEFT[3] == -8, "the rows start 8 in and 8 down")
check(scrollAt.BOTTOMRIGHT[2] == -8 and scrollAt.BOTTOMRIGHT[3] == 15, "then 8 right, 15 up")
local divider = popup.rows[5]
equal(divider:GetHeight(), 13, "a divider is 13 high")
equal(divider.shown, true, "and drawn")
local dividerPath = "Interface\\Common\\UI-TooltipDivider-Transparent"
equal(divider.divider.texture, dividerPath, "as the tooltip divider line")
equal(divider:IsEnabled(), false, "and not clickable")
local last = popup.rows[7]
local lastBottom = 8 - last.point[3] + last:GetHeight() -- the row's offset in the body is negative
equal(lastBottom, 8 + 20 * 6 + 13, "the last row ends after every row above it")
equal(popup:GetHeight(), lastBottom + 15, "the frame keeps Blizzard's 15-unit bottom inset below the last row")
local highlight = last.textures[1]
equal(highlight.layer, "HIGHLIGHT", "a row's hover is a highlight layer")
equal(highlight.texture, "Interface\\QuestFrame\\UI-QuestTitleHighlight", "in the quest log's highlight")
equal(highlight.blend, "ADD", "added over the background")
equal(popup.rows[1].highlight.alpha, 0, "a title never lights up")
equal(divider.highlight.alpha, 0, "nor a divider")
equal(last.highlight.alpha, 1, "an action lights up fully")
local clamp = popup.clampInsets
check(
	clamp[1] == -10 and clamp[2] == 10 and clamp[3] == 3 and clamp[4] == -3,
	"the clamp keeps the background on screen"
)

-- A short menu, then a long one on the same rows: the level widens to the long label.
ns.ContextMenu(owner, function(_, root)
	root:CreateButton("Go", function() end)
end)
local narrow = popup.body:GetWidth()
ns.ContextMenu(owner, function(_, root)
	root:CreateButton("Complete objectives, then talk to the farmer", function() end)
end)
check(popup.body:GetWidth() > narrow, "a long menu after a short one widens to its label")
equal(popup.body:GetWidth(), popup.rows[1]:GetTextWidth() + 20, "to the label plus Blizzard's 20")

-- A reused row drops what its last entry drew: the divider slot becomes a checked submenu row, then a plain row.
ns.ContextMenu(owner, function(_, root)
	for _ = 1, 4 do
		root:CreateButton("Row", function() end)
	end
	local checked = root:CreateCheckbox("Checked", function()
		return true
	end, function() end)
	checked:CreateButton("Inside", function() end)
end)
local reused = popup.rows[5]
equal(reused:GetHeight(), 20, "a divider slot reused as a row is a row's height")
equal(reused.divider.shown, false, "without the divider line")
equal(reused.indicator.shown, true, "with its checkbox")
equal(reused.arrow.shown, true, "and its submenu arrow")
equal(reused:IsEnabled(), true, "and it answers the mouse")
ns.ContextMenu(owner, function(_, root)
	for _ = 1, 5 do
		root:CreateButton("Plain", function() end)
	end
end)
equal(reused.indicator.shown, false, "a plain row in that slot has no checkbox")
equal(reused.tick.shown, false, "nor a tick")
equal(reused.arrow.shown, false, "nor an arrow")
equal(reused.divider.shown, false, "nor a divider")

print(("context_menu_spec: %d checks passed"):format(checks))
