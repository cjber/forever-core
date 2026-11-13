-- The icon helper: a file icon drawn whole, and the Cooldown Manager's icon frame built from the client's own two
-- atlases. The mask and overlay are made once per icon texture, and the overlay moves when the icon is resized. Then
-- the shared step markers: the gold numbers 1 to 25, the empty ring and the ring with the goal pin's diamond.
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local FakeClient = dofile("tests/fake_client.lua")
local env = FakeClient.new()
local ns = {}
assert(loadfile("UI/Art.lua"))("ForeverCore", ns)
local Art = assert(ns.Art, "UI/Art.lua publishes ns.Art")
equal(Art.minor, 2, "the module's minor is 2")

local frame = env.CreateFrame("Frame")
local icon = frame:CreateTexture(nil, "ARTWORK")

local function findAtlas(atlas)
	for _, child in ipairs(frame.children) do
		if child.atlas == atlas then
			return child
		end
	end
end

-- The client's two atlases, the mask over the icon and the overlay returned to the caller.
local overlay = Art.CooldownIcon(icon, 134400, 50)
local mask = findAtlas("UI-HUD-CoolDownManager-Mask")
check(mask ~= nil, "the mask is the client's Cooldown Manager mask atlas")
equal(mask.allPoints, icon, "the mask covers the icon")
equal(#icon.masks, 1, "the mask is added to the icon once")
equal(icon.masks[1], mask, "and it is that mask")
equal(overlay, findAtlas("UI-HUD-CoolDownManager-IconOverlay"), "the overlay is the client's Cooldown Manager overlay")
equal(overlay.layer, "OVERLAY", "the overlay draws on the OVERLAY layer")
equal(icon.texture, 134400, "the icon's file is set")
equal(icon.width, 50, "the icon is sized across")
equal(icon.height, 50, "and down")
equal(overlay.points[1][1], "TOPLEFT", "the overlay starts at the icon's top-left")
equal(overlay.points[1][4], -9, "9/50 of a 50-unit icon past the left")
equal(overlay.points[1][5], 8, "and 8/50 past the top")
equal(overlay.points[2][1], "BOTTOMRIGHT", "and ends at the icon's bottom-right")
equal(overlay.points[2][4], 9, "9/50 past the right")
equal(overlay.points[2][5], -8, "and 8/50 past the bottom")

-- A second call reuses the pair: no second mask or overlay, and the mask is added only once.
Art.CooldownIcon(icon, 134400, 50)
equal(#frame.children, 3, "a second call builds no second mask or overlay")
equal(#icon.masks, 1, "and adds the mask only once")

-- A new size moves the same overlay to the new outset.
Art.CooldownIcon(icon, 134400, 20)
equal(#frame.children, 3, "resizing keeps the one pair")
equal(overlay.points[1][4], -9 * 20 / 50, "a 20-unit icon puts the left edge 3.6 out")
equal(overlay.points[1][5], 8 * 20 / 50, "and the top 3.2 out")
equal(overlay.points[2][4], 9 * 20 / 50, "the right edge too")
equal(overlay.points[2][5], -8 * 20 / 50, "and the bottom")

-- Art.Icon still draws a bare icon, crop reset and all.
icon.texCoord = { 0.1, 0.9, 0.2, 0.8 }
Art.Icon(icon, 999, 37)
equal(#icon.texCoord, 4, "a bare icon resets its crop")
equal(icon.texCoord[1], 0, "left")
equal(icon.texCoord[2], 1, "right")
equal(icon.texCoord[3], 0, "top")
equal(icon.texCoord[4], 1, "bottom")
equal(icon.texture, 999, "a bare icon sets its file")
equal(icon.width, 37, "and its width")
equal(icon.height, 37, "and its height")

-- The shared step markers, drawn straight from core's media/Numbers: the gold numbers 1 to 25, an empty ring and the
-- ring with the goal pin's diamond in it. A step with no art answers nil so the caller keeps its own.
equal(Art.Marker(1), [[Interface\AddOns\ForeverCore\media\Numbers\1]], "step 1 is the first gold marker")
equal(Art.Marker(25), [[Interface\AddOns\ForeverCore\media\Numbers\25]], "step 25 is the last gold marker")
equal(Art.Marker(0), nil, "there is no marker below 1")
equal(Art.Marker(26), nil, "and none above 25")
equal(Art.Marker(1.5), nil, "a step that is not a whole number has no marker")
equal(Art.Marker("1"), nil, "and neither does a string")
equal(Art.Marker(nil), nil, "nor a missing step")
equal(Art.Ring(), [[Interface\AddOns\ForeverCore\media\Numbers\Ring]], "the empty ring")
equal(Art.Diamond(), [[Interface\AddOns\ForeverCore\media\Numbers\Diamond]], "the ring with the goal pin's diamond")

print(("art_spec: %d checks passed"):format(checks))
