-- Marks every function an addon defines so the sim knows when the addon's code runs, and instruments every
-- table field read and write so taint follows the slot (transform.lua parses the source; this module only
-- caches the rewrite and the disk copy of Blizzard's files).
--
-- Addon chunks get `__fst("Addon");` after each function's parameter list and at the chunk start; Blizzard
-- chunks get the field calls only and run with the writer taint at the time. Line numbers are the client's.
local Transform = require("transform")

local M = {}

M.MARKER = "__fst"

local cache = {}

local function hash(text)
	-- Two mod-2^32 hashes side by side; the arithmetic stays exact in a double for these multipliers.
	local a, b = 5381, 52711
	for i = 1, #text do
		local byte = text:byte(i)
		a = (a * 33 + byte) % 4294967296
		b = (b * 65599 + byte) % 4294967296
	end
	return string.format("%08x%08x", a, b)
end
M.hash = hash

-- The rewriter's own source names the Blizzard rewrite cache, so a change to the rewrite never serves output the
-- old code made.
local REWRITER = (function()
	local dir = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
	local parts = {}
	for _, name in ipairs({ "transform.lua", "instrument.lua" }) do
		local file = assert(io.open(dir .. name, "rb"))
		parts[#parts + 1] = file:read("*a")
		file:close()
	end
	return hash(table.concat(parts, "\0"))
end)()

-- Rewrites a chunk; `addon` names the addon (addon code) or is nil for Blizzard's.
function M.rewrite(src, addon)
	local key = (addon or "-") .. "\0" .. src
	local hit = cache[key]
	if hit then
		return hit
	end
	local out = Transform.rewrite(src, addon)
	cache[key] = out
	return out
end

local madeDirs = {}

local function ensureDir(path)
	if madeDirs[path] then
		return
	end
	os.execute("mkdir -p '" .. path:gsub("'", "'\\''") .. "'")
	madeDirs[path] = true
end

-- Rewrites Blizzard source, caching the result under `<cacheDir>/<rewriter hash>/<build>/<source hash>.lua` so a
-- pinned build parses once per machine and rewriter rather than once per client.
function M.rewriteBlizzard(src, cacheDir, build)
	local dir = string.format("%s/%s/%s", cacheDir, REWRITER, build)
	local path = dir .. "/" .. hash(src) .. ".lua"
	local file = io.open(path, "rb")
	if file then
		local text = file:read("*a")
		file:close()
		return text
	end
	local out = M.rewrite(src, nil)
	ensureDir(dir)
	local write = io.open(path, "wb")
	if write then
		write:write(out)
		write:close()
	end
	return out
end

M.cacheStats = function()
	local n = 0
	for _ in pairs(cache) do
		n = n + 1
	end
	return n
end

return M
