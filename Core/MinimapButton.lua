local _, ns = ...

-- A small round button on the Minimap rim. Addons provide their own icon, click action, tooltip lines and the saved
-- table the angle and hide flag live in. Nothing here hooks or resizes a Blizzard frame: the button is our own frame,
-- parented to Minimap and anchored by an angle around its centre.
local MinimapButton = {}
ns.MinimapButton = MinimapButton

-- Every Forever addon vendors this file, so each loads its own copy. They share one registry, published by the first
-- copy to load, so the buttons of every addon share one ring and never take the same default angle. The registry is
-- addon state: nothing of Blizzard's reads it.
local shared = _G.ForeverMinimapButtons
if type(shared) ~= "table" then
	shared = { buttons = {} }
	_G.ForeverMinimapButtons = shared
end

local ANGLE_KEY = "minimapButtonAngle"
local HIDDEN_KEY = "minimapButtonHidden"
-- The button's centre sits this far outside the Minimap's edge, so half of the 20-unit button overlaps the rim.
local RIM_OFFSET = 5
-- Half the rim is the usual place for one addon button; the rest spread around it before falling back to every 15°.
local DEFAULT_ANGLES = { 225, 195, 255, 165, 285, 135, 315, 105, 345, 75, 15, 45 }
-- Two buttons this close would sit on top of each other.
local MIN_GAP = 20
-- The icon fits inside the 20-unit plate's ring.
local ICON_SIZE = 13

local function Safe(label, fn, ...)
	if ns.SafeCall then
		return ns.SafeCall(label, fn, ...)
	end
	return pcall(fn, ...)
end

local function Normalize(angle)
	if type(angle) ~= "number" or angle ~= angle then
		return nil
	end
	return angle % 360
end

local function Distance(a, b)
	local delta = math.abs(Normalize(a) - Normalize(b))
	return math.min(delta, 360 - delta)
end

local function Taken(angle)
	for _, button in ipairs(shared.buttons) do
		if button.angle and Distance(button.angle, angle) < MIN_GAP then
			return true
		end
	end
	return false
end

-- The first free default angle, so a newly registered button never lands on one another addon already occupies.
local function FreeAngle()
	for _, angle in ipairs(DEFAULT_ANGLES) do
		if not Taken(angle) then
			return angle
		end
	end
	for step = 0, 23 do
		local angle = step * 15
		if not Taken(angle) then
			return angle
		end
	end
	return DEFAULT_ANGLES[1]
end

local function Radius()
	local width = Minimap:GetWidth()
	if type(width) ~= "number" or width <= 0 then
		width = 198
	end
	return width / 2 + RIM_OFFSET
end

-- The button is anchored by its angle, not by a saved x/y, so the ring follows the Minimap wherever Edit Mode puts it.
local function Place(button)
	local angle = math.rad(button.angle or DEFAULT_ANGLES[1])
	local radius = Radius()
	button:ClearAllPoints()
	button:SetPoint("CENTER", Minimap, "CENTER", math.cos(angle) * radius, math.sin(angle) * radius)
end

local function AngleFromCursor()
	local centerX, centerY = Minimap:GetCenter()
	local scale = Minimap:GetEffectiveScale()
	local cursorX, cursorY = GetCursorPosition()
	if not (centerX and centerY and scale and scale > 0 and cursorX and cursorY) then
		return nil
	end
	return Normalize(math.deg(math.atan2(cursorY / scale - centerY, cursorX / scale - centerX)))
end

local function SaveAngle(button, angle)
	angle = Normalize(angle)
	if not angle then
		return
	end
	button.angle = angle
	local spec = button.minimapButtonSpec
	if spec and spec.settings then
		spec.settings[spec.angleKey or ANGLE_KEY] = angle
	end
	Place(button)
end

local function Visible(button)
	local spec = button.minimapButtonSpec
	if spec.getShown then
		return spec.getShown() == true
	end
	return not (spec.settings and spec.settings[spec.hiddenKey or HIDDEN_KEY] == true)
end

local function Apply(button)
	local spec = button.minimapButtonSpec
	local stored = Normalize(spec.settings and spec.settings[spec.angleKey or ANGLE_KEY])
	if stored then
		button.angle = stored
	end
	button:SetShown(Visible(button))
	Place(button)
end

local function StartDrag(button)
	button.dragging = true
	button:SetScript("OnUpdate", function(self)
		local angle = AngleFromCursor()
		if angle then
			self.angle = angle
			Place(self)
		end
	end)
end

local function StopDrag(button)
	button.dragging = nil
	button:SetScript("OnUpdate", nil)
	SaveAngle(button, AngleFromCursor() or button.angle)
end

---@param spec ForeverMinimapButtonSpec
---@return ForeverMinimapButton?
function MinimapButton.Create(spec)
	if not (Minimap and Minimap.GetWidth) then
		if DEFAULT_CHAT_FRAME and DEFAULT_CHAT_FRAME.AddMessage then
			DEFAULT_CHAT_FRAME:AddMessage(ns.L.MINIMAP_UNAVAILABLE)
		end
		return nil
	end
	local button = CreateFrame("Button", spec.name, Minimap) --[[@as ForeverMinimapButton]]
	button.minimapButtonSpec = spec
	if spec.host then
		spec.host.minimapButton = button
	end
	button:SetSize(20, 20)
	button:SetNormalAtlas("UI-HUD-Minimap-Button") -- art-ok: the client's own modern minimap button plate
	button:SetPushedAtlas("UI-HUD-Minimap-Button-Down") -- art-ok: the client's own modern minimap button plate
	button:SetHighlightAtlas("bags-roundhighlight", "ADD") -- art-ok: the client's own round hover glow
	button:RegisterForClicks("LeftButtonUp")
	button:RegisterForDrag("LeftButton")
	-- The icon sits inside the plate's ring, cropped past its baked square border and masked round, as the
	-- client's own minimap buttons show theirs.
	local icon = button:CreateTexture(nil, "ARTWORK")
	icon:SetSize(ICON_SIZE, ICON_SIZE)
	icon:SetPoint("CENTER")
	icon:SetTexture(spec.icon) -- art-ok: the addon's own content icon, drawn on the client's plate
	icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
	local mask = button:CreateMaskTexture()
	mask:SetAllPoints(icon)
	mask:SetAtlas("CircleMaskScalable") -- art-ok: the client's round mask, already in the registry
	icon:AddMaskTexture(mask)
	button.icon = icon
	button:SetScript("OnClick", function(self, mouseButton)
		if spec.onClick then
			Safe("minimap button click", spec.onClick, self, mouseButton)
		end
	end)
	button:SetScript("OnEnter", function(self)
		GameTooltip:SetOwner(self, "ANCHOR_LEFT")
		GameTooltip:SetText(spec.title)
		if spec.binding then
			GameTooltip:AddLine("(" .. spec.binding .. ")", NORMAL_FONT_COLOR:GetRGB())
		end
		if spec.subtext then
			GameTooltip:AddLine(spec.subtext, GRAY_FONT_COLOR:GetRGB())
		end
		GameTooltip:Show()
	end)
	button:SetScript("OnLeave", function()
		GameTooltip:Hide()
	end)
	button:SetScript("OnDragStart", function(self)
		StartDrag(self)
	end)
	button:SetScript("OnDragStop", function(self)
		StopDrag(self)
	end)

	local angle = Normalize(spec.settings and spec.settings[spec.angleKey or ANGLE_KEY])
	if not angle then
		angle = FreeAngle()
		if spec.settings then
			spec.settings[spec.angleKey or ANGLE_KEY] = angle
		end
	end
	button.angle = angle
	shared.buttons[#shared.buttons + 1] = button
	Apply(button)
	return button
end

function MinimapButton.Destroy(button)
	for index, candidate in ipairs(shared.buttons) do
		if candidate == button then
			table.remove(shared.buttons, index)
			break
		end
	end
	if button then
		button:Hide()
		button:ClearAllPoints()
		local spec = button.minimapButtonSpec
		if spec and spec.host and spec.host.minimapButton == button then
			spec.host.minimapButton = nil
		end
	end
end

-- Re-reads every button's hide flag and saved angle, for a settings checkbox that has just written one.
function MinimapButton.Refresh()
	for _, button in ipairs(shared.buttons) do
		Safe("minimap button refresh", Apply, button)
	end
end

function MinimapButton.SetShown(button, shown)
	if button then
		button:SetShown(shown == true)
		Place(button)
	end
end
