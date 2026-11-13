-- The runner's automatic exercise: `luajit forever_sim/run.lua` from a fixture addon's own directory, with no
-- scenario file. A fixture with a button that makes a refused call, anchors a frame to its own child, or reloads from
-- its login handler must fail with no scenario written for it; a clean fixture must pass.
--
-- Run from tooling/: luajit tests/sim/exercise_spec.lua
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local pwd = io.popen("pwd"):read("*l")
local root = here:sub(1, 1) == "/" and here or (pwd .. "/" .. here:gsub("^%./", ""))
local fixtures = root .. "fixtures/"
local runner = root .. "../../forever_sim/run.lua"

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
local function has(haystack, needle)
	if not tostring(haystack):find(needle, 1, true) then
		error(string.format("expected %q in the runner's output:\n%s", needle, haystack), 2)
	end
end
local function lacks(haystack, needle)
	if tostring(haystack):find(needle, 1, true) then
		error(string.format("did not expect %q in the runner's output:\n%s", needle, haystack), 2)
	end
end

-- The cache holds Blizzard's UI source and client data; the fixture's own directory has no tools/.cache of its own.
local cache = os.getenv("FOREVER_SIM_CACHE") or (pwd .. "/.cache/forever_sim")

local function runFixture(name, env)
	local command = string.format(
		'cd "%s%s" && %sFOREVER_SIM_CACHE="%s" luajit "%s" 2>&1',
		fixtures,
		name,
		env and (env .. " ") or "",
		cache,
		runner
	)
	local pipe = assert(io.popen(command))
	local out = pipe:read("*a")
	pipe:close()
	return out
end

test("a fixture with no scenario runs the automatic exercise and passes", function()
	local out = runFixture("SimExerciseClean")
	has(out, "ok   exercise: every surface and the addon")
	has(out, "1 passed, 0 failed")
end)

test("a protected call in combat from the addon's own button fails the exercise", function()
	local out = runFixture("SimExerciseProtected")
	has(out, "FAIL exercise: every surface and the addon")
	has(out, "tried to call the protected function 'C_Map.OpenWorldMap()'")
	has(out, "0 passed, 1 failed")
end)

test("a frame anchored to its own child fails the exercise", function()
	local out = runFixture("SimExerciseAnchor")
	has(out, "FAIL exercise: every surface and the addon")
	has(out, "Cannot anchor to a region dependent on it")
	has(out, "SimExerciseAnchor")
end)

test("a reload from a login handler fails the exercise", function()
	local out = runFixture("SimExerciseReload")
	has(out, "FAIL exercise: every surface and the addon")
	has(out, "tried to call the protected function 'C_UI.Reload()'")
end)

test("a declared exercise passes its own options and is not run a second time", function()
	local out = runFixture("SimExerciseOptions")
	has(out, "ok   the declared exercise with its own options")
	lacks(out, "exercise: every surface and the addon")
	has(out, "1 passed, 0 failed")
end)

test("an addon that depends on ForeverCore gets that checkout loaded for the exercise", function()
	local core = fixtures .. "SimExerciseCore/ForeverCore"
	local out = runFixture("SimExerciseCore", 'FOREVER_CORE="' .. core .. '"')
	-- The addon's own button was created and clicked in combat: core was registered, its files did not stop.
	has(out, "tried to call the protected function 'C_Map.OpenWorldMap()'")
	lacks(out, "ForeverCore was not registered before the dependent addon")
end)

print(string.format("exercise_spec: %d passed, %d failed", passed, failed))
os.exit(failed == 0 and 0 or 1)
