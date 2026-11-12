-- The taint gate's fixtures: a known-bad shape writes a table field from addon code, a secure read of that slot
-- taints execution, and the gate names the field, the writer and the reader. The boundary fixtures do the same
-- work on the other side of a C API, securecallfunction/secureexecuterange, a client-dispatched script or a
-- hooksecurefunc post-hook: they leave no tainted field and pass the gate. No list is consulted.
--
-- Run from tooling/: luajit tests/sim/taint_gate_spec.lua
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
local fixtures = here .. "fixtures/"

local passed, failed = 0, 0
local function test(name, fn)
	local ok, err = xpcall(fn, debug.traceback)
	if ok then
		passed = passed + 1
		print(string.format("ok   %s", name))
	else
		failed = failed + 1
		print(string.format("FAIL %s\n  %s", name, tostring(err):gsub("\n", "\n  ")))
	end
end

local function maps(sim)
	sim.world.maps[1454] = { name = "Orgrimmar", parent = 1411 }
	sim.world.maps[1411] = { name = "Durotar", parent = 1414 }
	sim.world.maps[1414] = { name = "Kalimdor", parent = 947, mapType = 2 }
end

local function has(haystack, needle)
	return tostring(haystack):find(needle, 1, true) ~= nil
end

-- Every field and script slot the fixture wrote, as { table, key, info, script }.
local function writtenSlots(sim, addon)
	local out = {}
	for table_, map in pairs(sim.taint.slots) do
		for key, info in pairs(map) do
			if info.addon == addon then
				out[#out + 1] = { table = table_, key = key, info = info }
			end
		end
	end
	for frame, state in pairs(sim.widgets.state) do
		for name, info in pairs(state.scriptInfo or {}) do
			if info.addon == addon then
				out[#out + 1] = { table = frame, key = "__script:" .. name, info = info, script = true }
			end
		end
	end
	return out
end

-- Reads each slot from a secure dispatch, the way Blizzard's own code would read it, then makes the protected
-- call whose refusal reports the field.
local function secureReads(sim, slots)
	local reader = assert(
		sim.G.loadstring(
			"return function(t, k) __fsi_get(t, k); "
				.. "if SetPreferredGamepadInteractTarget then SetPreferredGamepadInteractTarget(nil) end end"
		)
	)
	local fn = assert(reader())
	for _, slot in ipairs(slots) do
		if slot.script then
			sim.run(function()
				sim.taint.readSlotAt(slot.table, slot.key, slot.info, "Blizzard_Probe/Script.lua", 1)
				if sim.G.SetPreferredGamepadInteractTarget then
					sim.G.SetPreferredGamepadInteractTarget(nil)
				end
			end)
		else
			sim.run(fn, slot.table, slot.key)
		end
	end
end

local fixtureSim

local function fieldSlots(sim, addon)
	local out = {}
	for _, slot in ipairs(writtenSlots(sim, addon)) do
		if not slot.script then
			out[#out + 1] = slot
		end
	end
	return out
end

-- A fixture whose action ends with no addon-tainted table field: the boundary kept the Blizzard code secure.
local function expectNoFieldTaint(name, drive)
	local sim = fixtureSim(name)
	if drive then
		drive(sim)
	end
	local slots = fieldSlots(sim, name)
	if #slots > 0 then
		local first = slots[1]
		error(
			string.format(
				"%s left a tainted field %s[%s] written at %s:%s",
				name,
				tostring(sim.taint.tablePath(first.table) or "<table>"),
				tostring(first.key),
				tostring(first.info.file),
				tostring(first.info.line)
			),
			2
		)
	end
	sim:expectNoGamepadTaint(name)
	return sim
end

fixtureSim = function(name)
	local sim = Sim.new()
	maps(sim)
	sim:addon(fixtures .. name, name)
	sim:setGamepad(true)
	sim:login()
	return sim
end

local function check(name, drive)
	local sim = fixtureSim(name)
	if drive then
		drive(sim)
	end
	local slots = writtenSlots(sim, name)
	assert(#slots > 0, name .. " wrote no table field or script slot")
	secureReads(sim, slots)
	local ok, err = pcall(sim.expectNoGamepadTaint, sim, name)
	assert(not ok, name .. " passed the gate")
	assert(has(err, "written by " .. name), err)
	assert(has(err, "read by secure code"), err)
	assert(has(err, " (entered from "), err)
	local first = slots[1]
	assert(has(err, tostring(first.info.file)) and has(err, ":" .. tostring(first.info.line)), err)
	return sim
end

test("clean fixture passes the gate", function()
	local sim = fixtureSim("SimTaintClean")
	sim:openBags()
	sim:closeBags()
	sim:openWorldMap(1454)
	sim:closeWorldMap()
	sim:event("QUEST_LOG_UPDATE")
	sim:expectNoGamepadTaint("SimTaintClean")
end)

test("a C API keeps the caller's taint across its deferred callback", function()
	local sim = check("SimTaintCAPI", function(client)
		client:advance(0.2)
	end)
	assert(sim.G.WorldMapFrame:IsShown(), "the timer ran Blizzard's map opener")
end)

test("secureexecuterange restores a secure caller after an addon callback", function()
	local sim = fixtureSim("SimTaintCallbackRange")
	sim.run(function()
		sim.G.EventRegistry:TriggerEvent("SimTaintCallbackRange")
	end)
	local slot = sim.taint.slotInfo(sim.G.EventRegistry.executingEvents, "SimTaintCallbackRange")
	assert(slot == nil, "the dispatcher's later write stayed secure")
	sim:expectNoGamepadTaint("SimTaintCallbackRange")
end)

test("secureexecuterange does not launder a tainted caller", function()
	local sim = fixtureSim("SimTaintCallbackRange")
	sim.G.SimTaintCallbackRangeTrigger()
	local slot = sim.taint.slotInfo(sim.G.EventRegistry.executingEvents, "SimTaintCallbackRange")
	assert(slot and slot.addon == "SimTaintCallbackRange", "the dispatcher's later write kept the caller's taint")
	sim:expectNoGamepadTaint("SimTaintCallbackRange")
end)

test("securecallfunction keeps a tainted caller tainted inside the call", function()
	check("SimTaintSecureCall")
end)

-- C_Map.OpenWorldMap carries the pin's nocombat class, not an always override: the live client opens a map for a
-- plain out-of-combat addon call (#486), and the AGF#411 block came from a cleanup-menu callback, a narrower
-- context this class does not describe. The combat side is the documented refusal.
test("a nocombat restriction passes out of combat and is refused in combat", function()
	local sim = fixtureSim("SimRestrictionProbe")
	sim:runAs("SimRestrictionProbe", "SimRestrictionProbeWorldMap()")
	assert(sim.G.WorldMapFrame:IsShown(), "the out-of-combat call opened the map")
	sim:closeWorldMap()
	sim:enterCombat()
	sim:runAs("SimRestrictionProbe", "SimRestrictionProbeWorldMap()")
	assert(sim:expectError("tried to call the protected function 'C_Map.OpenWorldMap()'"))
	assert(not sim.G.WorldMapFrame:IsShown(), "the combat call did not open the map")
end)

test("a hardware-event restriction is refused from a timer and allowed from input", function()
	local sim = fixtureSim("SimRestrictionProbe")
	sim:runAs("SimRestrictionProbe", "SimRestrictionProbeWho()")
	assert(sim:expectError("tried to call the protected function 'C_FriendList.SendWho()'"))
	local before = #sim.errors
	sim:input(function()
		sim:runAs("SimRestrictionProbe", "SimRestrictionProbeWho()")
	end)
	for i = before + 1, #sim.errors do
		assert(not tostring(sim.errors[i].message):find("C_FriendList.SendWho", 1, true), sim.errors[i].message)
	end
end)

test("an always restriction is refused out of combat", function()
	local sim = fixtureSim("SimRestrictionProbe")
	sim:runAs("SimRestrictionProbe", "SimRestrictionProbeAlways()")
	assert(sim:expectError("tried to call the protected function 'CopyToClipboard()'"))
end)

test("a restriction with several classes is refused when any one applies", function()
	local sim = fixtureSim("SimRestrictionProbe")
	-- SimRestrictionProbeWho calls C_FriendList.SendWho, normally hwevent; give it both classes.
	sim.restrictionOverrides["C_FriendList.SendWho"] =
		{ class = { "nocombat", "hwevent" }, issue = "cjber/forever-core#297" }
	-- Out of combat, from a timer: hwevent refuses.
	sim:runAs("SimRestrictionProbe", "SimRestrictionProbeWho()")
	assert(sim:expectError("tried to call the protected function 'C_FriendList.SendWho()'"))
	-- Out of combat, from input: neither class applies.
	local quiet = #sim.errors
	sim:input(function()
		sim:runAs("SimRestrictionProbe", "SimRestrictionProbeWho()")
	end)
	assert(#sim.errors == quiet, "neither class refused the input call")
	-- In combat, from input: nocombat refuses even though the hwevent class is satisfied.
	local before = #sim.errors
	sim:enterCombat()
	sim:input(function()
		sim:runAs("SimRestrictionProbe", "SimRestrictionProbeWho()")
	end)
	assert(#sim.errors == before + 1, "the nocombat class refused the combat call")
	assert(
		tostring(sim.errors[#sim.errors].message):find("C_FriendList.SendWho", 1, true),
		sim.errors[#sim.errors].message
	)
end)

test("an addon's Show of a Blizzard frame taints its OnShow", function()
	check("SimTaintClientScript")
end)

test("a hooksecurefunc post-hook starts secure", function()
	expectNoFieldTaint("SimTaintHookSecureFunc")
end)

test("a Blizzard write under addon taint records the addon site it entered from", function()
	local sim = fixtureSim("SimTaintMenu")
	sim:openWorldMap()
	sim:closeWorldMap()
	sim:input(function()
		sim.G.ShowUIPanel(sim.G.SettingsPanel)
	end)
	sim:input(function()
		sim.G.SettingsPanel:Close()
	end)
	local found
	for _, slot in ipairs(writtenSlots(sim, "SimTaintMenu")) do
		-- A slot Blizzard's own file wrote while the addon's taint was running: the report must name the
		-- addon frame that made that code run, not just the Blizzard line.
		if tostring(slot.info.file):find("^Blizzard_") and slot.info.origin then
			found = slot
			break
		end
	end
	assert(found, "no Blizzard file wrote a slot under the addon's taint")
	assert(found.info.origin.file and found.info.origin.file:find("SimTaintMenu", 1, true), "the origin is addon code")
	secureReads(sim, { found })
	local ok, err = pcall(sim.expectNoGamepadTaint, sim, "SimTaintMenu")
	assert(not ok, "the gate passed")
	assert(
		has(err, "(entered from " .. tostring(found.info.origin.file) .. ":" .. tostring(found.info.origin.line) .. ")"),
		err
	)
end)

test("a Blizzard menu opened from addon code under the gamepad interface taints a panel's read", function()
	check("SimTaintMenu", function(sim)
		sim:openWorldMap()
		sim:closeWorldMap()
		sim:input(function()
			sim.G.ShowUIPanel(sim.G.SettingsPanel)
		end)
		sim:input(function()
			sim.G.SettingsPanel:Close()
		end)
	end)
end)

test("pressing Escape names the Blizzard handler list an addon wrote", function()
	local sim = fixtureSim("SimGameMenuEsc")
	sim:enterCombat()
	sim:pressEscape()
	local hits = sim.gamepadTaint("SimGameMenuEsc")
	assert(#hits > 0, "Blizzard's secure read of the handler list was not recorded")
	local report = sim.watch.describe(hits)
	assert(has(report, "written by SimGameMenuEsc"), report)
	assert(has(report, "Blizzard_GameMenuEsc/Blizzard_GameMenuEsc.lua"), report)
	assert(has(report, "read by secure code"), report)
end)

test("an addon frame's own mouse scripts are not a taint slot", function()
	local sim = fixtureSim("SimTaintMouseScripts")
	sim.run(function()
		sim.G.SmartNavigation_CanFocusFrame(sim.G.SimTaintMouseFrame)
	end)
	-- The client keeps scripts outside the table-slot rule: secure code checking whether an addon frame has an
	-- OnMouseUp does not read the addon's taint, though running the script would.
	sim:expectNoGamepadTaint("SimTaintMouseScripts")
end)

local calls = {
	"SetModuleContainer",
	"UpdateFrameSize",
	"UpdateItemLayout",
	"UpdateContainerFrameAnchors",
	"UpdateUIPanelPositions",
	"GetBagsShown",
	"EnumerateValidItems",
	"GetBagSize",
	"GetRows",
	"ContainerFrameUtil_EnumerateContainerFrames",
	"SetParentInitializer",
	"AddMaskableTexture",
	"UpdateAnchors",
	"OpenWorldMap",
	"OpenQuestLog",
	"ToggleWorldMap",
	"QuestMapFrame_ShowQuestDetails",
}

for _, name in ipairs(calls) do
	test("the field taint of " .. name .. " fails the gate", function()
		check("SimTaint" .. name, function(sim)
			sim:openBags()
			sim:closeBags()
			sim:openWorldMap(1454)
			sim:closeWorldMap()
			sim:openQuestLog()
			sim:closeQuestLog()
			sim:event("QUEST_LOG_UPDATE")
		end)
	end)
end

print(string.format("taint_gate_spec: %d passed, %d failed", passed, failed))
os.exit(failed == 0 and 0 or 1)
