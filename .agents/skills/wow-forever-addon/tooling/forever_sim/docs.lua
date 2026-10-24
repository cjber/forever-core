-- Reads Blizzard_APIDocumentationGenerated: every system (C_* namespaces and global functions), every widget API
-- (ScriptObject systems), enumerations, constants and events, with the client's secret and protection flags.
local M = {}

local function readFile(path)
	local f = io.open(path, "rb")
	if not f then
		return nil
	end
	local text = f:read("*a")
	f:close()
	return text
end
M.readFile = readFile

-- Returns { systems = {...}, widgets = { [systemName] = system }, enums = {...}, constants = {...},
-- structures = { [name] = table }, events = { [LiteralName] = event } }.
function M.load(uiRoot)
	local dir = uiRoot .. "/Interface/AddOns/Blizzard_APIDocumentationGenerated/"
	local toc = readFile(dir .. "Blizzard_APIDocumentationGenerated.toc")
	if not toc then
		error("no API documentation under " .. dir .. " (fetch the UI source first)")
	end
	local out = { systems = {}, widgets = {}, enums = {}, constants = {}, structures = {}, events = {} }
	local sink = {
		AddDocumentationTable = function(_, t)
			if t.Type == "ScriptObject" then
				out.widgets[t.Name] = t
			else
				out.systems[#out.systems + 1] = t
			end
			for _, tbl in ipairs(t.Tables or {}) do
				if tbl.Type == "Enumeration" then
					out.enums[tbl.Name] = tbl
				elseif tbl.Type == "Constants" then
					out.constants[tbl.Name] = tbl
				elseif tbl.Type == "Structure" then
					out.structures[tbl.Name] = tbl
				end
			end
			for _, ev in ipairs(t.Events or {}) do
				out.events[ev.LiteralName] = ev
			end
		end,
	}
	-- The documentation files reference Enum and Constants values in defaults; give them a forgiving lookup.
	local forgivingMeta
	-- A placeholder remembers its path ("SecretAspect.Text") so flags naming enum values can be read back.
	local function forgiving(path)
		return setmetatable({ __name = path }, forgivingMeta)
	end
	local function same(a, b)
		return getmetatable(a) == forgivingMeta and a or b
	end
	forgivingMeta = {
		__index = function(t, k)
			local base = rawget(t, "__name")
			local child = forgiving(base and (base .. "." .. tostring(k)) or tostring(k))
			rawset(t, k, child)
			return child
		end,
		__add = same,
		__sub = same,
		__mul = same,
		__div = same,
		__unm = same,
		__concat = same,
	}
	-- Native macros some constants are documented with (Classic-era values, as the Forever client uses).
	local macros = {
		NUM_BAG_SLOTS = 4,
		NUM_REAGENTBAG_SLOTS = 0,
		NUM_CHARACTERBANK_SLOTS = 6,
		NUM_ACCOUNTBANK_SLOTS = 0,
	}
	local env = setmetatable({ APIDocumentation = sink }, {
		__index = function(_, k)
			if k == "Enum" or k == "Constants" then
				return forgiving(nil)
			end
			if macros[k] then
				return macros[k]
			end
			return _G[k]
		end,
	})
	for line in toc:gmatch("[^\r\n]+") do
		local file = line:match("^%s*([^#%s][^%s]*%.lua)")
		if file then
			local text = readFile(dir .. file:gsub("\\", "/"))
			if text then
				local chunk = assert(loadstring(text, "@Blizzard_APIDocumentationGenerated/" .. file))
				setfenv(chunk, env)
				chunk()
			end
		end
	end
	return out
end

-- The enum value names a documentation flag lists ({ Enum.SecretAspect.Text } -> { "Text" }).
function M.enumNames(list)
	local out = {}
	for _, v in ipairs(list or {}) do
		local name = type(v) == "table" and rawget(v, "__name")
		if name then
			out[#out + 1] = name:match("([^.]+)$")
		end
	end
	return out
end

return M
