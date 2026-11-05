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
	if parent then
		parent.children[#parent.children + 1] = f
	end
	return f
end

local hooks = { UpdateMicroButtons = 0, Layout = 0 }
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

local menu = frame("MicroMenu")
menu.childXPadding, menu.isHorizontal, menu.layoutFramesGoingRight = -5, true, true
local NATIVE = { "Character", "Spellbook", "Talent", "QuestLog", "Guild", "Collections", "EJ", "Help", "MainMenu" }
local native = {}
for index, short in ipairs(NATIVE) do
	local button = frame(short .. "MicroButton", menu)
	button.layoutIndex = index
	native[#native + 1] = button
	_G[button.name] = button
end
menu.stride = #native
-- Blizzard's grid: shown children with a layoutIndex, left to right from the menu's TOPLEFT, overlapping by 5.
function menu:Layout()
	local x = 0
	for _, button in ipairs(native) do
		if button.shown then
			button:ClearAllPoints()
			button:SetPoint("TOPLEFT", self, "TOPLEFT", x, 0)
			x = x + button.width + self.childXPadding
		end
	end
end
menu:SetPoint("BOTTOMRIGHT", nil, "BOTTOMRIGHT", 0, 0)
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
local gameMenuLeft = left(_G.MainMenuMicroButton)
local a = first.Create(spec("First"))
second.Create(spec("Second"))
assert(a.parent == menu and a.template == "MainMenuBarMicroButton")
assert(a.width == 32 and a.height == 41)
assert(a.SetNormalAtlas == "UI-HUD-MicroMenu-FieldGuide-Up")
assert(a.SetHighlightAtlas == "UI-HUD-MicroMenu-FieldGuide-Mouseover")
assert(a.alert.hidden)

-- Same slot, two places: the first made sits next to Game Menu, the second one further left, and the menu, anchored
-- to the right of the screen, grows left so Game Menu stays put.
local beforeBoth = "CharacterMicroButton SpellbookMicroButton TalentMicroButton QuestLogMicroButton GuildMicroButton "
	.. "CollectionsMicroButton EJMicroButton HelpMicroButton Second First MainMenuMicroButton"
assert(row() == beforeBoth, row())
assert(left(_G.MainMenuMicroButton) == gameMenuLeft)

-- Blizzard re-laying the row, or any number of refreshes, lands in the same place.
for _ = 1, 5 do
	_G.UpdateMicroButtons()
	first.Refresh()
	second.Refresh()
	menu:Layout()
end
assert(row() == beforeBoth, row())
assert(hooks.Layout == 1, "MicroMenu.Layout hooked " .. hooks.Layout .. " times")
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
menu:Layout()
assert(row():find("HelpMicroButton Second First MainMenuMicroButton$"), row())
_G.CollectionsMicroButton:Show()
menu:Layout()
slot.Second = "beforeGameMenu"

-- Hiding a button gives its place back; hiding both leaves Blizzard's row exactly as the grid laid it.
shown.First = false
first.Refresh()
assert(not a.shown)
assert(row():find("HelpMicroButton Second MainMenuMicroButton$"), row())
shown.Second = false
second.Refresh()
assert(left(_G.CharacterMicroButton) == 0 and left(_G.MainMenuMicroButton) == gameMenuLeft, row())
shown.First, shown.Second = true, true
first.Refresh()
second.Refresh()
assert(row() == beforeBoth, row())

-- A menu anchored on the left grows right instead, so Character stays put.
menu:SetPoint("BOTTOMLEFT", nil, "BOTTOMLEFT", 0, 0)
menu:Layout()
assert(row() == beforeBoth, row())
assert(left(_G.CharacterMicroButton) == 0 and left(_G.MainMenuMicroButton) == gameMenuLeft + 54, row())

-- Destroy takes the button out of the shared row.
first.Destroy(a)
assert(row():find("HelpMicroButton Second MainMenuMicroButton$"), row())

local saved = _G.MicroMenu
_G.MicroMenu = nil
assert(first.Create({}) == nil)
_G.MicroMenu = saved
