local ns = {
	L = setmetatable({}, {
		__index = function(_, key)
			return key
		end,
	}),
	SafeCall = function(_, fn, ...)
		return pcall(fn, ...)
	end,
}
local function frame(name, shown)
	local f = { name = name, shown = shown ~= false, points = {} }
	function f:SetSize(w, h)
		self.width, self.height = w, h
	end
	function f:SetPoint(...)
		self.points = { ... }
	end
	function f:ClearAllPoints()
		self.points = {}
	end
	function f:SetShown(value)
		self.shown = value
	end
	function f:IsShown()
		return self.shown
	end
	function f:Hide()
		self.shown = false
	end
	function f.CreateTexture()
		return { SetSize = function() end, SetPoint = function() end, SetTexture = function() end }
	end
	function f:SetNormalAtlas(value)
		self.normal = value
	end
	function f:SetPushedAtlas(value)
		self.pushed = value
	end
	function f:SetDisabledAtlas(value)
		self.disabled = value
	end
	function f:SetHighlightAtlas(value)
		self.highlight = value
	end
	function f:SetScript(scriptName, value)
		self[scriptName] = value
	end
	function f.Layout() end
	return f
end
_G.MicroMenu = frame("MicroMenu")
_G.MainMenuMicroButton = frame("MainMenuMicroButton")
_G.CollectionsMicroButton = frame("CollectionsMicroButton")
_G.hooksecurefunc = function(name, callback)
	local original = _G[name]
	_G[name] = function(...)
		original(...)
		callback(...)
	end
end
_G.UpdateMicroButtons = function() end
_G.CreateFrame = function(_, name, parent, template)
	local button = frame(name)
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

assert(loadfile("Core/MicroButton.lua"))("ForeverCore", ns)

local shown = true
local slot = "beforeGameMenu"
local button = ns.MicroButton.Create({
	name = "TestMicroButton",
	atlas = "FieldGuide",
	icon = "icon",
	title = "title",
	binding = "Shift-F",
	subtext = "subtext",
	slot = slot,
	getSlot = function()
		return slot
	end,
	getShown = function()
		return shown
	end,
	onClick = function() end,
})
assert(button.parent == _G.MicroMenu and button.template == "MainMenuBarMicroButton")
assert(button.width == 32 and button.height == 41)
assert(button.normal == "UI-HUD-MicroMenu-FieldGuide-Up")
assert(button.pushed == "UI-HUD-MicroMenu-FieldGuide-Down")
assert(button.disabled == "UI-HUD-MicroMenu-FieldGuide-Disabled")
assert(button.highlight == "UI-HUD-MicroMenu-FieldGuide-Mouseover")
assert(button.alert.hidden)
assert(button.points[1] == "RIGHT" and button.points[2] == _G.MainMenuMicroButton and button.points[4] == 5)

slot = "afterCollections"
ns.MicroButton.Refresh()
assert(button.points[1] == "LEFT" and button.points[2] == _G.CollectionsMicroButton and button.points[4] == -5)
_G.CollectionsMicroButton:Hide()
ns.MicroButton.Refresh()
assert(button.points[1] == "RIGHT" and button.points[2] == _G.MainMenuMicroButton)
shown = false
ns.MicroButton.Refresh()
assert(not button.shown)
shown = true
ns.MicroButton.Refresh()
assert(button.shown)
ns.MicroButton.SetShown(nil, true)

local old = _G.MainMenuMicroButton
_G.MainMenuMicroButton = frame("NewMainMenuMicroButton")
_G.UpdateMicroButtons()
assert(button.points[2] == _G.MainMenuMicroButton and button.points[2] ~= old)

local saved = _G.MicroMenu
_G.MicroMenu = nil
assert(ns.MicroButton.Create({}) == nil)
_G.MicroMenu = saved
print("micro button contract passed")
