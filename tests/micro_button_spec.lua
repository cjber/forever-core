-- Core/MicroButton.lua against a stub of MicroMenu's grid: every addon button gets its own place in the row, two
-- vendored copies share it, and Blizzard's buttons move aside instead of being covered.
local function newNs()
	return {
		L = setmetatable({}, {
			__index = function(_, key)
				return key
			end,
		}),
		SafeCall = function(label, fn, ...)
			local ok, err = pcall(fn, ...)
			assert(ok, label .. ": " .. tostring(err))
			return ok
		end,
	}
end

local function frame(name, parent)
	local f = { name = name, shown = true, points = {}, width = 32, height = 41, scripts = {}, children = {} }
	function f:SetSize(w, h)
		self.width, self.height = w, h
	end
	function f:GetWidth()
		return self.width
	end
	function f:SetWidth(w)
		local was = self.width
		self.width = w
		if was ~= w and self.scripts.OnSizeChanged then
			self.scripts.OnSizeChanged(self)
		end
	end
	function f.GetScale()
		return 1
	end
	function f:GetParent()
		return self.parent
	end
	function f:SetPoint(...)
		self.points = { ... }
	end
	function f:GetPoint()
		return unpack(self.points)
	end
	function f:ClearAllPoints()
		self.points = {}
	end
	function f:SetShown(value)
		local was = self.shown
		self.shown = value == true
		if was ~= self.shown then
			local script = self.scripts[self.shown and "OnShow" or "OnHide"]
			if script then
				script(self)
			end
		end
	end
	function f:IsShown()
		return self.shown
	end
	function f:Hide()
		self:SetShown(false)
	end
	function f:Show()
		self:SetShown(true)
	end
	function f:GetChildren()
		return unpack(self.children)
	end
	function f.CreateTexture()
		return { SetSize = function() end, SetPoint = function() end, SetTexture = function() end }
	end
	for _, method in ipairs({ "SetNormalAtlas", "SetPushedAtlas", "SetDisabledAtlas", "SetHighlightAtlas" }) do
		f[method] = function(self, value)
			self[method] = value
		end
	end
	function f:SetScript(scriptName, value)
		self.scripts[scriptName] = value
	end
	function f:HookScript(scriptName, hook)
		self.hooked = (self.hooked or 0) + 1
		local original = self.scripts[scriptName]
		self.scripts[scriptName] = function(...)
			if original then
				original(...)
			end
			hook(...)
		end
	end
	function f:RegisterEvent(event)
		self.events = self.events or {}
		self.events[event] = true
	end
	if parent then
		f.parent = parent
		parent.children[#parent.children + 1] = f
	end
	return f
end

local hooks = { UpdateMicroButtons = 0 }
_G.hooksecurefunc = function(target, name, callback)
	if type(target) == "string" then
		target, name, callback = _G, target, name
	end
	hooks[name] = hooks[name] + 1
	local original = target[name]
	target[name] = function(...)
		original(...)
		callback(...)
	end
end

-- The Edit Mode container, at one edge of a 1000-wide screen, and the menu in its corner nearest that edge.
local SCREEN = 1000
local container = frame("MicroMenuContainer")
_G.MicroMenuContainer = container
local menu = frame("MicroMenu", container)
menu.childXPadding, menu.isHorizontal, menu.layoutFramesGoingRight = -5, true, true
local NATIVE = { "Character", "Spellbook", "Talent", "QuestLog", "Guild", "Collections", "EJ", "Help", "MainMenu" }
local native = {}
for index, short in ipairs(NATIVE) do
	local button = frame(short .. "MicroButton", menu)
	button.layoutIndex = index
	native[#native + 1] = button
	_G[button.name] = button
end
-- Like MainMenuBarMicroButtonMixin, a Blizzard button re-lays the row when it shows or hides.
for _, button in ipairs(native) do
	button:SetScript("OnShow", function()
		_G.MicroMenu:Layout()
	end)
	button:SetScript("OnHide", function()
		_G.MicroMenu:Layout()
	end)
end
menu.stride = #native
-- Blizzard's grid: shown children with a layoutIndex, left to right from the menu's TOPLEFT, overlapping by 5, then
-- the menu sized to them (ResizeLayoutMixin) and the container to the menu (MicroMenuContainerMixin:Layout).
function menu:Layout()
	local x, right = 0, 0
	for _, button in ipairs(native) do
		if button.shown then
			button:ClearAllPoints()
			button:SetPoint("TOPLEFT", self, "TOPLEFT", x, 0)
			right = x + button.width
			x = x + button.width + self.childXPadding
		end
	end
	self:SetWidth(right)
	container.width = self.width
end
-- Edit Mode places the container; MicroMenuMixin:AnchorToMenuContainer puts the menu in its corner on that side.
local function placeContainer(side)
	container:SetPoint("BOTTOM" .. side, nil, "BOTTOM" .. side, 0, 0)
	menu:SetPoint("BOTTOM" .. side, container, "BOTTOM" .. side, 0, 0)
end
placeContainer("RIGHT")
menu:Layout()
_G.MicroMenu = menu
_G.UpdateMicroButtons = function()
	menu:Layout()
end
_G.CreateFrame = function(_, name, parent, template)
	local button = frame(name, parent)
	button.parent, button.template = parent, template
	button.alert = {
		Hide = function(self)
			self.hidden = true
		end,
	}
	return button
end
_G.GameTooltip =
	{ SetOwner = function() end, SetText = function() end, AddLine = function() end, Show = function() end }
_G.GameTooltip_Hide = function() end
_G.NORMAL_FONT_COLOR = {
	GetRGB = function()
		return 1, 1, 1
	end,
}
_G.GRAY_FONT_COLOR = {
	GetRGB = function()
		return 0.5, 0.5, 0.5
	end,
}
_G.DEFAULT_CHAT_FRAME = { AddMessage = function() end }

-- The screen edges of the container and the menu in it.
local function containerLeft()
	return container.points[1] == "BOTTOMRIGHT" and SCREEN - container.width or 0
end
local function menuLeft()
	if menu.points[1] == "BOTTOMRIGHT" then
		return containerLeft() + container.width - menu.width
	end
	return containerLeft()
end

-- Left edge of a frame on the row, following its anchor chain back to the menu.
local function left(f)
	local point, relativeTo, relativePoint, x = unpack(f.points)
	if relativeTo == menu then
		assert(point == "TOPLEFT" and relativePoint == "TOPLEFT", f.name .. " anchored oddly")
		return x
	end
	assert(relativeTo, f.name .. " has no anchor")
	if point == "RIGHT" and relativePoint == "LEFT" then
		return left(relativeTo) + x - f.width
	end
	assert(point == "LEFT" and relativePoint == "RIGHT", f.name .. " anchored oddly")
	return left(relativeTo) + relativeTo.width + x
end

-- The shown row from left to right, checked for even spacing: no button covers another.
local function row()
	local shown = {}
	for _, f in ipairs(menu.children) do
		if f.shown then
			shown[#shown + 1] = f
		end
	end
	table.sort(shown, function(a, b)
		return left(a) < left(b)
	end)
	-- The whole row is inside the menu, so inside its art, its container and the screen; the container fits it.
	local first, last = shown[1], shown[#shown]
	assert(left(first) >= 0, first.name .. " starts left of the menu")
	assert(left(last) + last.width <= menu.width, last.name .. " ends right of the menu")
	assert(container.width == menu.width, "container " .. container.width .. " for menu " .. menu.width)
	assert(menuLeft() >= 0 and menuLeft() + menu.width <= SCREEN, "menu off the screen")
	local names = {}
	for index, f in ipairs(shown) do
		names[index] = f.name
		if index > 1 then
			local gap = left(f) - left(shown[index - 1])
			assert(gap == 27, ("%s sits %d from %s, not one slot"):format(f.name, gap, shown[index - 1].name))
		end
	end
	return table.concat(names, " ")
end

-- Two addons, each with its own vendored copy of the module, like Adventure Guide and Field Guide.
local function load()
	local ns = newNs()
	assert(loadfile("Core/MicroButton.lua"))("Addon", ns)
	return ns.MicroButton
end
local first, second = load(), load()
local shown = { First = true, Second = true }
local slot = { First = "beforeGameMenu", Second = "beforeGameMenu" }
local function spec(name)
	return {
		name = name,
		atlas = "FieldGuide",
		icon = "icon",
		title = "title",
		binding = "Shift-F",
		subtext = "subtext",
		slot = "beforeGameMenu",
		getSlot = function()
			return slot[name]
		end,
		getShown = function()
			return shown[name]
		end,
		onClick = function() end,
	}
end
-- Where a frame sits on the screen.
local function screen(f)
	return menuLeft() + left(f)
end
local naturalWidth = menu.width
local gameMenuRight = screen(_G.MainMenuMicroButton) + _G.MainMenuMicroButton.width
assert(gameMenuRight == SCREEN)
local a = first.Create(spec("First"))
second.Create(spec("Second"))
assert(a.parent == menu and a.template == "MainMenuBarMicroButton")
assert(a.width == 32 and a.height == 41)
assert(a.SetNormalAtlas == "UI-HUD-MicroMenu-FieldGuide-Up")
assert(a.SetHighlightAtlas == "UI-HUD-MicroMenu-FieldGuide-Mouseover")
assert(a.alert.hidden)
-- The template's OnMouseDown and UpdateMicroButtons build the pressed and normal highlights from textureName.
assert(a.textureName == "FieldGuide")

-- Same slot, two places: the first made sits next to Game Menu, the second one further left. The menu and its
-- container widen by two slots; anchored to the right of the screen, they grow left so Game Menu stays at the edge.
local beforeBoth = "CharacterMicroButton SpellbookMicroButton TalentMicroButton QuestLogMicroButton GuildMicroButton "
	.. "CollectionsMicroButton EJMicroButton HelpMicroButton Second First MainMenuMicroButton"
assert(row() == beforeBoth, row())
assert(menu.width == naturalWidth + 54, menu.width)
assert(screen(_G.MainMenuMicroButton) + _G.MainMenuMicroButton.width == SCREEN)

-- Blizzard re-laying the row, or any number of refreshes, lands in the same place.
for _ = 1, 5 do
	_G.UpdateMicroButtons()
	first.Refresh()
	second.Refresh()
	menu:Layout()
	_G.UpdateMicroButtons()
end
assert(row() == beforeBoth, row())
for _, f in ipairs(native) do
	assert(f.hooked == 2, f.name .. " script hooks: " .. tostring(f.hooked))
end
assert(menu.hooked == 1, "menu script hooks: " .. tostring(menu.hooked))
-- hooksecurefunc swaps the global for a wrapper; refreshing again must not hook that wrapper too, or every
-- UpdateMicroButtons call nests one hook deeper until the client's C stack overflows.
local before = hooks.UpdateMicroButtons
for _ = 1, 50 do
	_G.UpdateMicroButtons()
	first.Refresh()
end
assert(hooks.UpdateMicroButtons == before, "UpdateMicroButtons hooked again")

-- After Collections is its own slot.
slot.Second = "afterCollections"
second.Refresh()
assert(
	row()
		== "CharacterMicroButton SpellbookMicroButton TalentMicroButton QuestLogMicroButton GuildMicroButton "
			.. "CollectionsMicroButton Second EJMicroButton HelpMicroButton First MainMenuMicroButton",
	row()
)
-- Without Collections it falls back to before Game Menu.
_G.CollectionsMicroButton:Hide()
assert(row():find("HelpMicroButton Second First MainMenuMicroButton$"), row())
_G.CollectionsMicroButton:Show()
slot.Second = "beforeGameMenu"

-- Hiding a button gives its place back; hiding both leaves Blizzard's row exactly as the grid laid it.
shown.First = false
first.Refresh()
assert(not a.shown)
assert(row():find("HelpMicroButton Second MainMenuMicroButton$"), row())
shown.Second = false
second.Refresh()
assert(left(_G.CharacterMicroButton) == 0 and menu.width == naturalWidth, row())
assert(screen(_G.MainMenuMicroButton) + _G.MainMenuMicroButton.width == SCREEN)
shown.First, shown.Second = true, true
first.Refresh()
second.Refresh()
assert(row() == beforeBoth, row())

-- A container moved to the left edge in Edit Mode, which leaves the grid as it was and fires
-- EDIT_MODE_LAYOUTS_UPDATED: the menu grows right instead, so Character stays at the edge.
placeContainer("LEFT")
local events = _G.ForeverMicroButtons.events
assert(events.events.EDIT_MODE_LAYOUTS_UPDATED)
events.scripts.OnEvent(events, "EDIT_MODE_LAYOUTS_UPDATED")
assert(row() == beforeBoth, row())
assert(screen(_G.CharacterMicroButton) == 0, row())
-- and back to the right edge, without a re-lay in between.
placeContainer("RIGHT")
events.scripts.OnEvent(events, "EDIT_MODE_LAYOUTS_UPDATED")
assert(row() == beforeBoth, row())
assert(screen(_G.MainMenuMicroButton) + _G.MainMenuMicroButton.width == SCREEN)

-- In combat the container, which the action bar anchors to, stays as it is; the placement runs when combat ends.
local inCombat = true
_G.InCombatLockdown = function()
	return inCombat
end
assert(events.events.PLAYER_REGEN_ENABLED)
shown.First = false
first.Refresh()
assert(menu.width == naturalWidth + 54, "resized in combat")
inCombat = false
events.scripts.OnEvent(events, "PLAYER_REGEN_ENABLED")
assert(row():find("HelpMicroButton Second MainMenuMicroButton$"), row())
assert(menu.width == naturalWidth + 27, menu.width)
shown.First = true
first.Refresh()
assert(row() == beforeBoth, row())

-- Destroy takes the button out of the shared row.
first.Destroy(a)
assert(row():find("HelpMicroButton Second MainMenuMicroButton$"), row())

local saved = _G.MicroMenu
_G.MicroMenu = nil
assert(first.Create({}) == nil)
_G.MicroMenu = saved
