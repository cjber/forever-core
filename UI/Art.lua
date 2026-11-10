local _, ns = ...

-- The little art core's own windows need. A file icon is square as every one is, drawn whole: a texture that held an
-- atlas before keeps that atlas's crop until it is reset, so the crop is reset here too.

---@class ForeverArt
local Art = {}
ns.Art = Art

-- A file icon, square, `size` across and whole.
---@param texture Texture
---@param file string|integer
---@param size number
function Art.Icon(texture, file, size)
	texture:SetTexCoord(0, 1, 0, 1)
	texture:SetTexture(file)
	texture:SetSize(size, size)
end
