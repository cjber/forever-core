-- Client data fetched at test time (fetch.py): global strings for the scenario's locale, the global colours
-- (C_UIColor.GetColors) and texture atlas sizes (SetAtlas with useAtlasSize, C_Texture.GetAtlasInfo).
local M = {}

local function load(path)
	local chunk = loadfile(path)
	if not chunk then
		return nil
	end
	return chunk()
end

function M.build(sim)
	local G = sim.G
	local strings = load(sim.dataDir .. "/globalstrings-" .. sim.locale .. ".lua")
	if not strings then
		error(
			string.format(
				"no global strings for %s in %s: run python3 tools/forever_sim/fetch.py --locale %s",
				sim.locale,
				sim.dataDir,
				sim.locale
			)
		)
	end
	for k, v in pairs(strings) do
		if G[k] == nil then
			G[k] = v
		end
	end
	local colors = load(sim.dataDir .. "/globalcolors.lua") or {}
	sim.impl["C_UIColor.GetColors"] = function()
		local out = {}
		for i, c in ipairs(colors) do
			out[i] = { baseTag = c[1], color = { r = c[2], g = c[3], b = c[4], a = c[5] } }
		end
		return out
	end
	local atlas = load(sim.dataDir .. "/atlas.lua") or {}
	sim.atlasInfo = function(name)
		local a = type(name) == "string" and atlas[name:lower()]
		if a then
			return { width = a[1], height = a[2] }
		end
	end
	sim.impl["C_Texture.GetAtlasInfo"] = function(name)
		local a = type(name) == "string" and atlas[name:lower()]
		if not a then
			return nil
		end
		return {
			width = a[1],
			height = a[2],
			leftTexCoord = 0,
			rightTexCoord = 1,
			topTexCoord = 0,
			bottomTexCoord = 1,
			tilesHorizontally = false,
			tilesVertically = false,
			file = 0,
			filename = name,
		}
	end
end

return M
