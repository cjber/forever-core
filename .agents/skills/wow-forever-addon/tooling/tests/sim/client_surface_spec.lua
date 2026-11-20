-- The client surface guard (cjber/forever-core#932), against the real Blizzard UI (fetch it first: python3
-- forever_sim/fetch.py), from tooling/: luajit tests/sim/client_surface_spec.lua. forever_sim answers cvars and
-- script support from client_surface.lua, a ForeverProbe dump; this checks that dump against every Blizzard file a
-- login loads, so a client patch that adds a cvar or a widget script fails here instead of as a false red.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
local Surface = require("client_surface")
local Widgets = require("widgets")

local passed, failed = 0, 0
local function test(name, fn)
	local ok, err = xpcall(fn, debug.traceback)
	if ok then
		passed = passed + 1
		print("ok   " .. name)
	else
		failed = failed + 1
		print("FAIL " .. name .. "\n  " .. tostring(err):gsub("\n", "\n  "))
	end
end

-- Every Blizzard file the sim loaded, in load order (templates.lua records each as it reads it).
local sim = Sim.new()
sim:login()
local files = sim.templates.files
assert(#files > 100, "a login loads Blizzard's UI files, got " .. #files)

local function read(path)
	local f = assert(io.open(path, "rb"))
	local text = f:read("*a")
	f:close()
	return text
end

-- A literal cvar name in a read or a default lookup. Names built at run time are covered by the full dump.
local CVAR_READS = {
	'GetCVar%(%s*"([%w_]+)"',
	'GetCVarBool%(%s*"([%w_]+)"',
	'GetCVarDefault%(%s*"([%w_]+)"',
	'GetCVarNumberOrDefault%(%s*"([%w_]+)"',
	'GetCVarBitfield%(%s*"([%w_]+)"',
}

test("every cvar the loaded Blizzard code reads by name has the client's own answer", function()
	-- The client matches cvar names in any case.
	local defined, missing = {}, {}
	for name in pairs(Surface.cvars) do
		defined[name:lower()] = true
	end
	-- The client answers nil for these too, so the sim's nil is the client's answer.
	for _, name in ipairs(Surface.undefined) do
		defined[name:lower()] = true
	end
	for _, path in ipairs(files) do
		for name in read(path):gmatch('RegisterCVar%(%s*"([%w_]+)"') do
			defined[name:lower()] = true
		end
	end
	for _, path in ipairs(files) do
		local text = read(path)
		for _, pattern in ipairs(CVAR_READS) do
			for name in text:gmatch(pattern) do
				if not defined[name:lower()] then
					missing[#missing + 1] = name .. " (" .. path:gsub(".*/Interface/", "") .. ")"
				end
			end
		end
	end
	assert(#missing == 0, "cvars the client dump lacks:\n  " .. table.concat(missing, "\n  "))
end)

test("each widget type the client makes has its own script set from the dump", function()
	-- Types no factory makes: their scripts only matter through the concrete types below them.
	local abstract = { Object = true, FrameScriptObject = true, ScriptRegion = true, Region = true, TextureBase = true }
	local missing = {}
	for kind in pairs(Widgets.TYPES) do
		if not abstract[kind] and not Surface.scripts[kind] and not Surface.unmade[kind] then
			missing[#missing + 1] = kind
		end
	end
	table.sort(missing)
	assert(#missing == 0, "widget types with no dumped scripts: " .. table.concat(missing, ", "))
end)

test("every script handler in the loaded Blizzard XML is one its widget type takes", function()
	local refused = {}
	for _, message in ipairs(sim.templates.errors) do
		if message:find("does not take script", 1, true) then
			refused[#refused + 1] = message
		end
	end
	assert(#refused == 0, "XML scripts the client's types refuse:\n  " .. table.concat(refused, "\n  "))
end)

test("the sim reads cvars as the client does", function()
	local G = sim.G
	assert(G.GetCVar("userFontScale") == Surface.cvars.userFontScale, "a defined cvar reads its default")
	assert(G.GetCVar("USERFONTSCALE") == Surface.cvars.userFontScale, "cvar names match in any case")
	assert(G.GetCVar("notACVarTheClientDefines") == nil, "an undefined cvar reads nil")
	assert(G.SetCVar("notACVarTheClientDefines", "1") == false, "setting an undefined cvar changes nothing")
	assert(G.GetCVar("notACVarTheClientDefines") == nil)
	G.C_CVar.RegisterCVar("foreverSurfaceSpec", "7")
	assert(G.GetCVarDefault("foreverSurfaceSpec") == "7", "a registered cvar's value is its default")
end)

test("a script the client refuses still errors", function()
	local text = sim.G.UIParent:CreateFontString()
	assert(not pcall(text.SetScript, text, "OnClick", function() end), "FontString takes no OnClick")
end)

print(string.format("client_surface_spec: %d passed, %d failed", passed, failed))
os.exit(failed == 0 and 0 or 1)
