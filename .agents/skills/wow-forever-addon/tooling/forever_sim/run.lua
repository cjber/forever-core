-- The scenario runner: luajit tools/forever_sim/run.lua [file or folder ...] (default tests/sim), from the
-- addon's repository root. Each *_scenario.lua file declares scenarios:
--
--   scenario("hovering a recipe shows the bar", function(sim)
--       sim.world.professions = { ... }
--       sim:login()
--       sim:openProfessions()
--       sim:hoverRecipe(1)
--   end)
--
--   scenario("with Questie's tracker", { stubs = { Questie = {} }, locale = "deDE" }, function(sim) ... end)
--
-- Every scenario gets a fresh client with the repository's addon (the TOC at the root) registered. It fails on an
-- error from its code, on any error the addon caused (one raised in its code or in execution it tainted), and on
-- any gamepad-interface taint the addon left, unless its options say `allowErrors = true` or
-- `allowGamepadTaint = true`. Exit status: 0 when every scenario passes.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "sim.lua")

local args = { ... }
local verbose = false
local filter
local paths = {}
for _, a in ipairs(args) do
	if a == "-v" then
		verbose = true
	elseif a:match("^%-%-only=") then
		filter = a:match("^%-%-only=(.*)$")
	else
		paths[#paths + 1] = a
	end
end
if #paths == 0 then
	paths = { "tests/sim" }
end

local function listFiles(path)
	local out = {}
	local p = io.popen('find "' .. path .. '" -name "*_scenario.lua" 2>/dev/null | sort')
	for f in p:lines() do
		out[#out + 1] = f
	end
	p:close()
	if #out == 0 and path:match("%.lua$") then
		out[1] = path
	end
	return out
end

local function tocName()
	local p = io.popen("ls *.toc 2>/dev/null")
	local name = p:read("*l")
	p:close()
	return name and name:gsub("%.toc$", "")
end

local addonName = tocName()
local scenarios = {}
local function declare(name, options, fn)
	if type(options) == "function" then
		options, fn = {}, options
	end
	scenarios[#scenarios + 1] = { name = name, options = options or {}, fn = fn, file = Sim.currentFile }
end

for _, path in ipairs(paths) do
	for _, file in ipairs(listFiles(path)) do
		Sim.currentFile = file
		local chunk = assert(loadfile(file))
		setfenv(chunk, setmetatable({ scenario = declare, Sim = Sim, ADDON = addonName }, { __index = _G }))
		chunk()
	end
end

local passed, failed = 0, 0
local started = os.clock()
for _, sc in ipairs(scenarios) do
	if not filter or sc.name:find(filter, 1, true) then
		local t0 = os.clock()
		local opts = sc.options
		local sim
		local ok, err = xpcall(function()
			sim = Sim.new({ locale = opts.locale, cache = opts.cache, verbose = verbose })
			for name, stubOptions in pairs(opts.stubs or {}) do
				sim:stub(name, stubOptions)
			end
			if addonName and opts.addon ~= false then
				sim:addon(".", addonName)
			end
			for _, extra in ipairs(opts.addons or {}) do
				sim:addon(extra[1], extra[2])
			end
			sc.fn(sim)
			if not opts.allowErrors and addonName then
				sim:expectNoErrors(addonName)
			end
			if not opts.allowGamepadTaint and addonName then
				sim:expectNoGamepadTaint(addonName)
			end
		end, debug.traceback)
		local seconds = os.clock() - t0
		if ok then
			passed = passed + 1
			print(string.format("ok   %-70s %5.1fs", sc.name, seconds))
		else
			failed = failed + 1
			print(string.format("FAIL %-70s %5.1fs  (%s)", sc.name, seconds, sc.file))
			print("     " .. tostring(err):gsub("\n", "\n     "))
			if verbose and sim then
				print("     client errors:\n     " .. Sim.describe(sim.errors):gsub("\n", "\n     "))
			end
		end
	end
end
print(string.format("%d passed, %d failed, %.1fs", passed, failed, os.clock() - started))
os.exit(failed == 0 and 0 or 1)
