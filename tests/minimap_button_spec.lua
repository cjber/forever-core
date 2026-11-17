-- Core/MinimapButton.lua against a stub of the Minimap and the cursor: two vendored copies share one ring, each button
-- lands on its own angle, a drag saves the angle it stopped on, and the hide flag takes it off the rim.
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
	local f = { name = name, shown = true, points = {}, scripts = {}, textures = {} }
	function f:SetSize(width, height)
		self.width, self.height = width, height
	end
	function f:GetWidth()
		return self.width
	end
	function f:GetHeight()
		return self.height
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
	function f:SetShown(shown)
		self.shown = shown == true
	end
	function f:IsShown()
		return self.shown
	end
	function f:Show()
		self.shown = true
	end
	function f:Hide()
		self.shown = false
	end
	function f:SetScript(scriptName, value)
		self.scripts[scriptName] = value
	end
	function f:RegisterForClicks(...)
		self.clicks = { ... }
	end
	function f:RegisterForDrag(...)
		self.drags = { ... }
	end
	function f:SetFrameStrata(value)
		self.strata = value
	end
	function f:SetFrameLevel(value)
		self.level = value
	end
	function f:SetFixedFrameStrata(value)
		self.fixedStrata = value
	end
	function f:SetFixedFrameLevel(value)
		self.fixedLevel = value
	end
	function f:SetHighlightTexture(value, blend)
		self.highlight, self.highlightBlend = value, blend
	end
	function f.CreateTexture(_, _, layer)
		local texture = { layer = layer }
		function texture:SetSize(width, height)
			self.width, self.height = width, height
		end
		function texture:SetPoint(...)
			self.points = { ... }
		end
		function texture:SetTexture(value)
			self.texture = value
		end
		function texture:SetTexCoord(...)
			self.texCoord = { ... }
		end
		f.textures[#f.textures + 1] = texture
		return texture
	end
	if parent then
		f.parent = parent
	end
	return f
end

local minimap = frame("Minimap")
minimap.width, minimap.height = 198, 198
minimap.centerX, minimap.centerY = 200, 150
function minimap:GetCenter()
	return self.centerX, self.centerY
end
function minimap.GetEffectiveScale()
	return 1
end
_G.Minimap = minimap

local cursorX, cursorY = 200, 254
function _G.GetCursorPosition()
	return cursorX, cursorY
end

_G.CreateFrame = function(_, name, parent)
	local button = frame(name, parent)
	button.parent = parent
	return button
end
_G.GameTooltip = {
	lines = {},
	SetOwner = function(self, owner)
		self.owner = owner
		self.lines = {}
	end,
	SetText = function(self, text)
		self.title = text
	end,
	AddLine = function(self, text)
		self.lines[#self.lines + 1] = text
	end,
	Show = function() end,
	Hide = function() end,
}
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
local messages = {}
_G.DEFAULT_CHAT_FRAME = {
	AddMessage = function(_, message)
		messages[#messages + 1] = message
	end,
}

-- Two addons, each with its own vendored copy of the module, like Field Guide and Adventure Guide.
local function load()
	local ns = newNs()
	assert(loadfile("Core/MinimapButton.lua"))("Addon", ns)
	return ns.MinimapButton
end
local first = load()

local clicked = {}
local function spec(name, settings)
	return {
		name = name,
		icon = "icon-" .. name,
		title = "title-" .. name,
		binding = "Shift-F",
		subtext = "subtext-" .. name,
		settings = settings,
		host = {},
		onClick = function(button, mouseButton)
			clicked[#clicked + 1] = { button = button, mouseButton = mouseButton }
		end,
	}
end

local settingsA = {}
local aSpec = spec("FirstMinimapButton", settingsA)
local a = first.Create(aSpec)
assert(a, "no button")
assert(a.parent == minimap, "not parented to the Minimap")

local function textureOn(button, layer)
	for _, texture in ipairs(button.textures) do
		if texture.layer == layer then
			return texture
		end
	end
end

-- LibDBIcon's construction: a 31-unit button with the tracking border over a 24-unit background and 18-unit icon.
assert(a.width == 31 and a.height == 31, "size")
assert(a.strata == "MEDIUM", a.strata)
assert(a.fixedStrata == true and a.level == 8 and a.fixedLevel == true, "pinned above the Minimap")
assert(a.level == 8, a.level)
assert(a.highlight == 136477, a.highlight)
local overlay = textureOn(a, "OVERLAY")
assert(overlay and overlay.width == 50 and overlay.height == 50, "overlay size")
assert(overlay.texture == 136430, overlay.texture)
assert(overlay.points[1] == "TOPLEFT", overlay.points[1])
local background = textureOn(a, "BACKGROUND")
assert(background and background.width == 24 and background.height == 24, "background size")
assert(background.texture == 136467, background.texture)
assert(background.points[1] == "CENTER", background.points[1])
assert(a.icon == textureOn(a, "ARTWORK"), "icon is not the artwork texture")
assert(a.icon.texture == "icon-FirstMinimapButton", a.icon.texture)
assert(a.icon.width == 18 and a.icon.height == 18, "icon size")
assert(a.icon.points[1] == "CENTER", a.icon.points[1])
assert(not a.icon.mask, "icon still masked")
local texCoord = a.icon.texCoord
assert(
	texCoord and texCoord[1] == 0.05 and texCoord[2] == 0.95 and texCoord[3] == 0.05 and texCoord[4] == 0.95,
	"icon texcoord"
)
assert(aSpec.host.minimapButton == a, "host not published")
assert(a.clicks and a.clicks[1] == "LeftButtonUp", "clicks")
assert(a.drags and a.drags[1] == "LeftButton", "drag button")
assert(settingsA.minimapButtonAngle == 225, settingsA.minimapButtonAngle)
assert(a.shown, "hidden on create")

-- Holding the mouse nudges the icon down-right, as LibDBIcon does, and letting go puts it back.
a.scripts.OnMouseDown(a)
assert(a.icon.points[1] == "CENTER" and a.icon.points[2] == a and a.icon.points[3] == "CENTER", "nudge anchor")
assert(a.icon.points[4] == 1 and a.icon.points[5] == -1, "nudge offset")
a.scripts.OnMouseUp(a)
assert(a.icon.points[1] == "CENTER" and #a.icon.points == 1, "nudge stayed")

-- A second addon gets the next free angle rather than landing on the first one.
local settingsB2 = {}
local b = first.Create(spec("SecondMinimapButton", settingsB2))
assert(b, "no second button")
assert(settingsB2.minimapButtonAngle == 195, settingsB2.minimapButtonAngle)
assert(math.abs(a.angle - b.angle) >= 25, "two buttons on one angle")
assert(#first.Buttons() == 2, "registry")

-- The angle is an offset from the Minimap's centre, not a screen position.
local point, relativeTo, relativePoint, x, y = a:GetPoint()
assert(point == "CENTER" and relativeTo == minimap and relativePoint == "CENTER", "anchor")
assert(math.abs(x - math.cos(math.rad(225)) * 104) < 0.01, "x")
assert(math.abs(y - math.sin(math.rad(225)) * 104) < 0.01, "y")

-- A click runs the addon's action with the mouse button.
a.scripts.OnClick(a, "LeftButton")
assert(#clicked == 1 and clicked[1].button == a and clicked[1].mouseButton == "LeftButton", "click")

-- Hovering shows the addon's lines; the shared module never draws its own.
a.scripts.OnEnter(a)
assert(GameTooltip.owner == a and GameTooltip.title == "title-FirstMinimapButton", "tooltip title")
assert(GameTooltip.lines[1] == "(Shift-F)", GameTooltip.lines[1])
assert(GameTooltip.lines[2] == "subtext-FirstMinimapButton", GameTooltip.lines[2])
a.scripts.OnLeave(a)

-- A drag around the rim moves the button and saves the angle it stopped on. Straight above the Minimap is 90°.
cursorX, cursorY = 200, 254
a.scripts.OnDragStart(a)
assert(a.dragging and a.scripts.OnUpdate, "drag did not start")
a.scripts.OnUpdate(a, 0.01)
assert(math.abs(a.angle - 90) < 0.01, a.angle)
local points = { a:GetPoint() }
assert(math.abs(points[4]) < 0.01 and math.abs(points[5] - 104) < 0.01, "moved while dragging")
a.scripts.OnDragStop(a)
assert(not a.dragging and not a.scripts.OnUpdate, "drag did not stop")
assert(math.abs(settingsA.minimapButtonAngle - 90) < 0.01, settingsA.minimapButtonAngle)
assert(settingsB2.minimapButtonAngle == 195, "the other button moved")

-- The hide flag is read on create and on refresh; hiding keeps its angle for when it comes back.
settingsA.minimapButtonHidden = true
first.Refresh()
assert(not a:IsShown(), "hide flag ignored")
settingsB2.minimapButtonHidden = true
first.Refresh()
assert(not b:IsShown(), "second hide flag ignored")
settingsA.minimapButtonHidden = false
settingsB2.minimapButtonHidden = false
first.Refresh()
assert(a:IsShown() and b:IsShown(), "buttons stayed hidden")
assert(math.abs(a.angle - 90) < 0.01, "angle lost while hidden")

-- Destroy takes the button out of the shared ring and clears the host's reference.
first.Destroy(a)
assert(#first.Buttons() == 1, "destroyed button stayed in the registry")
assert(aSpec.host.minimapButton == nil, "host still points at the destroyed button")

-- A button records its callbacks under the addon that registered it, not under ForeverCore.
local ownerNs = newNs()
local coreCalls, ownerCalls = {}, {}
ownerNs.SafeCall = function(label, fn, ...)
	coreCalls[#coreCalls + 1] = label
	return pcall(fn, ...)
end
assert(loadfile("Core/MinimapButton.lua"))("OwnerAddon", ownerNs)
local ownerModule = ownerNs.MinimapButton
local ownerSpec = spec("OwnerMinimapButton", {})
ownerSpec.safeCall = function(label, fn, ...)
	ownerCalls[#ownerCalls + 1] = label
	return pcall(fn, ...)
end
ownerSpec.onClick = function()
	error("the addon's click failed")
end
local ownerButton = ownerModule.Create(ownerSpec)
assert(ownerButton, "no owner button")
ownerCalls = {}
ownerButton.scripts.OnClick(ownerButton, "LeftButton")
assert(#ownerCalls == 1 and ownerCalls[1] == "minimap button click", "the click did not run in the owner's SafeCall")
assert(#coreCalls == 0, "the click was recorded under ForeverCore")
ownerModule.Refresh()
assert(#ownerCalls == 2 and ownerCalls[2] == "minimap button refresh", "the refresh did not use the owner's SafeCall")
assert(#coreCalls == 0, "the refresh was recorded under ForeverCore")

-- Without an addon SafeCall, core's is the fallback.
local fallbackSpec = spec("FallbackMinimapButton", {})
fallbackSpec.onClick = function() end
local fallbackButton = ownerModule.Create(fallbackSpec)
ownerCalls, coreCalls = {}, {}
fallbackButton.scripts.OnClick(fallbackButton, "LeftButton")
assert(#coreCalls == 1 and coreCalls[1] == "minimap button click", "the fallback did not use core's SafeCall")
assert(#ownerCalls == 0, "the fallback called an addon SafeCall")

-- Without the client's Minimap the module says so and skips the button instead of erroring.
local saved = _G.Minimap
_G.Minimap = nil
assert(first.Create(spec("MissingMinimapButton", {})) == nil, "made a button with no Minimap")
assert(messages[#messages] == "MINIMAP_UNAVAILABLE", messages[#messages])
_G.Minimap = saved

-- Opted-in launchers use LibDBIcon without constructing a private frame.
local privateCreate = CreateFrame
local ownFrames, lookups = 0, 0
_G.CreateFrame = function(...)
	ownFrames = ownFrames + 1
	return privateCreate(...)
end
local objects, registered = {}, {}
local broker = {}
function broker.NewDataObject(_, name, object)
	if objects[name] then
		return nil
	end
	objects[name] = object
	return object
end
function broker.GetDataObjectByName(_, name)
	return objects[name]
end
local lib = {}
function lib.IsRegistered(_, name)
	return registered[name] ~= nil
end
function lib:Register(name, object, db)
	registered[name] = { object = object, db = db, button = frame("LibDBIcon10_" .. name) }
	self:Refresh(name, db)
end
function lib.GetMinimapButton(_, name)
	return registered[name].button
end
function lib.Show(_, name)
	registered[name].button:Show()
end
function lib.Hide(_, name)
	registered[name].button:Hide()
end
function lib:Refresh(name, db)
	registered[name].button.position = db.minimapPos
	if db.hide then
		self:Hide(name)
	else
		self:Show(name)
	end
end
_G.LibStub = function(name, silent)
	assert(silent == true, "library lookup must be silent")
	lookups = lookups + 1
	if name == "LibDataBroker-1.1" then
		return broker
	end
	if name == "LibDBIcon-1.0" then
		return lib
	end
end
local managed = load()
local db = { angle = 123, hidden = true }
local managedSpec = spec("Managed", db)
managedSpec.libDBIcon = "SkillUp Forever"
managedSpec.angleKey, managedSpec.hiddenKey = "angle", "hidden"
local managedButton = managed.Create(managedSpec)
assert(registered[managedSpec.libDBIcon], "opted-in button did not register with LibDBIcon")
assert(ownFrames == 0, "managed launcher created a private frame")
local registration = registered[managedSpec.libDBIcon]
local proxy = registration.db
assert(managedButton == registration.button and managedSpec.host.minimapButton == managedButton, "managed host")
assert(managed.Buttons()[1] == managedButton, "managed registry")
assert(managedButton.position == 123 and not managedButton:IsShown(), "saved position and visibility")
proxy.minimapPos = 42
assert(db.angle == 42 and proxy.minimapPos == 42, "drag did not update saved angle")
proxy.hide = false
assert(db.hidden == false and proxy.hide == false, "hide proxy write")
proxy.lock = true
assert(proxy.lock and db.lock == nil, "extra proxy field was saved")
db.hidden = true
managed.Refresh()
assert(not managedButton:IsShown() and managedButton.position == 42, "refresh hide and position")
db.hidden = false
managed.Refresh()
assert(managedButton:IsShown(), "refresh show")
managed.SetShown(managedButton, false)
assert(not managedButton:IsShown(), "managed SetShown hide")
managed.SetShown(managedButton, true)
assert(managedButton:IsShown(), "managed SetShown show")
registration.object.OnClick(managedButton, "LeftButton")
assert(clicked[#clicked].button == managedButton, "launcher click")
GameTooltip:SetOwner(managedButton)
registration.object.OnTooltipShow(GameTooltip)
assert(GameTooltip.title == managedSpec.title and GameTooltip.lines[3] == "MINIMAP_DRAG_HINT", "launcher tooltip hint")
a.scripts.OnEnter(a)
assert(GameTooltip.lines[3] == "MINIMAP_DRAG_HINT", "private tooltip hint")
local shown = false
managedSpec.getShown = function()
	return shown
end
assert(proxy.hide == true, "getShown hide proxy")
shown = true
assert(proxy.hide == false, "getShown show proxy")
managed.Destroy(managedButton)
assert(
	not managedButton:IsShown() and #managed.Buttons() == 0 and not managedSpec.host.minimapButton,
	"managed destroy"
)
-- Recreating a destroyed launcher reuses its registration and binds the new owner's state.
local replacementDB = { angle = 77, hidden = false }
local replacementSpec = spec("Replacement", replacementDB)
replacementSpec.libDBIcon = managedSpec.libDBIcon
replacementSpec.angleKey, replacementSpec.hiddenKey = "angle", "hidden"
local replacementClicked = false
replacementSpec.onClick = function()
	replacementClicked = true
end
local framesBeforeReuse = ownFrames
local replacement = managed.Create(replacementSpec)
assert(replacement == managedButton, "destroy then create did not reuse LibDBIcon button")
assert(ownFrames == framesBeforeReuse, "recreated launcher made a private frame")
assert(replacement:IsShown() and replacement.position == 77, "recreated launcher ignored new settings")
assert(managed.Buttons()[1] == replacement and #managed.Buttons() == 1, "recreated launcher registry")
assert(replacementSpec.host.minimapButton == replacement, "recreated launcher host")
assert(registration.object.icon == replacementSpec.icon, "recreated launcher icon")
registration.object.OnClick(replacement, "LeftButton")
assert(replacementClicked, "recreated launcher kept old click callback")
GameTooltip:SetOwner(replacement)
registration.object.OnTooltipShow(GameTooltip)
assert(GameTooltip.title == replacementSpec.title, "recreated launcher kept old tooltip")
proxy.minimapPos = 88
assert(replacementDB.angle == 88 and db.angle == 42, "recreated proxy kept old settings")
replacementDB.hidden = true
managed.Refresh()
assert(not replacement:IsShown(), "recreated launcher ignored new hide setting")
managed.Destroy(replacement)
local before = lookups
managed.Create(spec("Legacy", {}))
assert(lookups == before, "legacy spec looked up libraries")
local takenSpec = spec("Taken", {})
takenSpec.libDBIcon = "Another addon"
objects[takenSpec.libDBIcon] = {}
assert(managed.Create(takenSpec).name == "Taken", "taken name did not fall back")
-- Default settings keys and a new launcher's free angle use the same proxy contract.
local defaultSettings = {}
local defaultSpec = spec("DefaultManaged", defaultSettings)
defaultSpec.libDBIcon = "Default managed launcher"
local defaultButton = managed.Create(defaultSpec)
local defaultProxy = registered[defaultSpec.libDBIcon].db
assert(defaultProxy.minimapPos == defaultSettings.minimapButtonAngle, "default angle not seeded")
assert(defaultSettings.minimapButtonAngle == 255, "default managed angle")
defaultSettings.minimapButtonHidden = true
managed.Refresh()
assert(not defaultButton:IsShown(), "default hide key ignored")
defaultProxy.hide = false
assert(defaultSettings.minimapButtonHidden == false, "default hide write")
managed.Refresh()
assert(defaultButton:IsShown(), "default show ignored")
-- Either missing library falls back, without creating a broker object.
for _, missing in ipairs({ "LibDataBroker-1.1", "LibDBIcon-1.0" }) do
	_G.LibStub = function(name)
		if name == missing then
			return nil
		end
		return name == "LibDataBroker-1.1" and broker or lib
	end
	local partialSpec = spec("Partial" .. missing, {})
	partialSpec.libDBIcon = "Partial launcher " .. missing
	assert(managed.Create(partialSpec).name == partialSpec.name, "partial libraries did not fall back")
	assert(not objects[partialSpec.libDBIcon], "partial libraries created broker object")
end
_G.LibStub = nil
local missingSpec = spec("MissingLibraries", {})
missingSpec.libDBIcon = "Missing"
assert(managed.Create(missingSpec).name == "MissingLibraries", "missing libraries did not fall back")
_G.CreateFrame = privateCreate
