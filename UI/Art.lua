local _, ns = ...

-- The little art core's own windows need. A file icon is square as every one is, drawn whole: a texture that held an
-- atlas before keeps that atlas's crop until it is reset, so the crop is reset here too.

---@class ForeverCooldownArt
---@field mask MaskTexture
---@field overlay Texture

---@class ForeverArt
---@field minor integer raised with each member the module adds
local Art = { minor = 2 }
ns.Art = Art

-- The step markers every Forever addon draws, written by tools/export_markers.py: the gold numbers 1 to 25, the empty
-- ring a place a route visits twice stacks behind its marker, and that ring with the goal pin's diamond in it for a
-- step that has no number next.
local MARKER_FILE = [[Interface\AddOns\ForeverCore\media\Numbers\%d]]
local RING_FILE = [[Interface\AddOns\ForeverCore\media\Numbers\Ring]]
local DIAMOND_FILE = [[Interface\AddOns\ForeverCore\media\Numbers\Diamond]]
local MAX_MARKER = 25

-- The mask and overlay the Cooldown Manager's icon carries, one pair per icon texture. They are weak-keyed so an icon
-- the client drops takes its pair with it, and they stay off the Blizzard object itself.
---@type table<Texture, ForeverCooldownArt>
local cooldownArt = setmetatable({}, { __mode = "k" })

-- A file icon, square, `size` across and whole.
---@param texture Texture
---@param file string|integer
---@param size number
function Art.Icon(texture, file, size)
	texture:SetTexCoord(0, 1, 0, 1)
	texture:SetTexture(file)
	texture:SetSize(size, size)
end

-- The Cooldown Manager's icon frame: the client's own mask over the icon and its overlay around it. The client builds
-- this frame only inside its Cooldown Manager (Blizzard_CooldownViewer/CooldownViewer.xml) and offers no template, so
-- any icon an addon draws gets the same two atlases here. The pair is made once per icon texture, because an addon
-- calls this again on every refresh and a second mask would multiply the icon's alpha twice.
---@param texture Texture
---@param file string|integer
---@param size number
---@return Texture overlay the overlay texture, so a caller can hide or recolour it
function Art.CooldownIcon(texture, file, size)
	Art.Icon(texture, file, size)
	local art = cooldownArt[texture]
	if not art then
		local frame = texture:GetParent()
		local mask = frame:CreateMaskTexture()
		mask:SetAtlas("UI-HUD-CoolDownManager-Mask")
		mask:SetAllPoints(texture)
		texture:AddMaskTexture(mask)
		local overlay = frame:CreateTexture(nil, "OVERLAY")
		overlay:SetAtlas("UI-HUD-CoolDownManager-IconOverlay")
		art = { mask = mask, overlay = overlay }
		cooldownArt[texture] = art
	end
	-- The overlay reaches 9/50 of the icon's width past each side and 8/50 of its height past the top and bottom.
	local x, y = 9 * size / 50, 8 * size / 50
	art.overlay:ClearAllPoints()
	art.overlay:SetPoint("TOPLEFT", texture, "TOPLEFT", -x, y)
	art.overlay:SetPoint("BOTTOMRIGHT", texture, "BOTTOMRIGHT", x, -y)
	return art.overlay
end

-- The gold numbered step marker for `number`, a file path for the markers 1 to 25 and nil for anything else, so a
-- route with more steps keeps the art it already has.
---@param number integer?
---@return string? file
function Art.Marker(number)
	if type(number) ~= "number" or number < 1 or number > MAX_MARKER or number % 1 ~= 0 then
		return nil
	end
	return MARKER_FILE:format(number)
end

-- The empty ring, for a place a route visits twice: its numbered marker draws over this.
---@return string file
function Art.Ring()
	return RING_FILE
end

-- The ring with the goal pin's diamond in it, for a step that has no number next.
---@return string file
function Art.Diamond()
	return DIAMOND_FILE
end
