local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")

local tests = {}

function tests.craft()
	local sim = Sim.new()
	local crafted = 0
	sim.impl["C_TradeSkillUI.CraftRecipe"] = function()
		crafted = crafted + 1
	end
	sim:runAs("CraftProbe", [[CraftState = { recipe = 123 }]])
	local create = assert(sim.templates.compile(
		[[
		local recipe = CraftState.recipe
		assert(not issecure())
		C_TradeSkillUI.CraftRecipe(recipe, 1)
	]],
		"Blizzard_Probe/Create.lua"
	))
	sim:input(create)
	assert(crafted == 1, "native hardware Create must craft after reading addon state")
	sim:expectNoErrors()
	sim.run(create)
	assert(crafted == 1, "tainted execution without hardware input must be refused")
	assert(#sim.errors == 1 and sim.errors[1].message:find("CraftRecipe", 1, true))
	sim:runAs(
		"CraftProbe",
		[[
		function CraftFromAddon()
			C_TradeSkillUI.CraftRecipe(123, 1)
		end
	]]
	)
	sim:input(sim.G.CraftFromAddon)
	assert(crafted == 1, "addon execution on the hardware path must be refused")
	assert(#sim.errors == 2 and sim.errors[2].message:find("CraftRecipe", 1, true))
end

function tests.exercise()
	local sim = Sim.new()
	sim:login()
	sim:runAs(
		"ExerciseProbe",
		[[
		function ExerciseProbeSelected()
			return "elected"
		end
	]]
	)
	assert(sim.G.ExerciseProbeSelected() == "elected")
	assert(sim.taint.current == "ExerciseProbe")
	local setGamepad = sim.setGamepad
	function sim:setGamepad(on)
		assert(self.taint.current == nil, "exercise must start client orchestration in a secure context")
		return setGamepad(self, on)
	end
	local reloaded = sim:exercise({ addons = { "ExerciseProbe" } })
	sim:expectNoErrors()
	reloaded:expectNoErrors()
	assert(sim.taint.current == "ExerciseProbe", "exercise must restore the caller's execution taint")
end

function tests.chunk()
	local locals = {}
	for i = 1, 201 do
		locals[i] = "local v" .. i
	end
	local dir = "virtual-addon"
	local files = {
		[dir .. "/TooManyLocals.toc"] = "## Interface: 16001\nScripts.xml\nLater.lua\n",
		[dir .. "/Scripts.xml"] = '<Ui><Include file="Nested.xml"/></Ui>',
		[dir .. "/Nested.xml"] = '<Ui><Script file="Oversized.lua"/><Script file="Later.lua"/></Ui>',
		[dir .. "/Oversized.lua"] = table.concat(locals, "\n"),
		[dir .. "/Later.lua"] = "MissingFromOversized.value = 1",
	}
	local sim = Sim.new()
	local open = io.open
	local function openFixture(path, ...)
		if files[path] then
			return {
				read = function()
					return files[path]
				end,
				close = function() end,
			}
		end
		return open(path, ...)
	end
	rawset(io, "open", openFixture)
	local ok, err = pcall(function()
		sim:addon(dir, "TooManyLocals")
		sim:login()
		local expected = "TooManyLocals/Oversized.lua: cannot load in forever_sim: "
		assert(sim.errors[1] and sim.errors[1].message:find(expected, 1, true), sim.errors[1] and sim.errors[1].message)
		assert(sim.errors[1].message:find("more than 200 local variables", 1, true))
		assert(#sim.errors == 1, "files after the oversized chunk must not run")
		assert(not sim.G.C_AddOns.IsAddOnLoaded("TooManyLocals"), "failed addon must not be marked loaded")
	end)
	rawset(io, "open", open)
	assert(ok, err)
end

function tests.edit_mode()
	local sim = Sim.new()
	sim:login()
	local G = sim.G
	local tracker = G.ObjectiveTrackerFrame
	local listener = G.CreateFrame("Frame")
	listener:RegisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
	local seen = 0
	listener:SetScript("OnEvent", function()
		seen = seen + 1
	end)
	sim:event("EDIT_MODE_LAYOUTS_UPDATED")
	sim:expectNoErrors()
	local presets = G.EditModePresetLayoutManager
	local modern = presets:GetPresetLayoutSystemAnchorInfo(1, tracker.system, tracker.systemIndex)
	sim:event("EDIT_MODE_LAYOUTS_UPDATED", { layouts = {}, activeLayout = 1 })
	sim:expectNoErrors()
	local point, relativeTo, relativePoint, x, y = tracker:GetPoint()
	assert(point == modern.point and relativeTo == G[modern.relativeTo] and relativePoint == modern.relativePoint)
	assert(x * tracker:GetScale() == modern.offsetX and y * tracker:GetScale() == modern.offsetY)
	assert(seen == 2, "layout event must reach other registered listeners")
	local saved = { layoutName = "Mine", layoutType = 1, systems = presets:GetCopyOfPresetLayouts()[2].systems }
	sim:event(
		"EDIT_MODE_LAYOUTS_UPDATED",
		{ layouts = { saved }, activeLayout = #presets:GetCopyOfPresetLayouts() + 1 }
	)
	sim:expectNoErrors()
	assert(G.EditModeManagerFrame:GetActiveLayoutInfo() == saved, "the manager must report the saved layout as active")
end

for _, name in ipairs(arg[1] and { arg[1] } or { "craft", "exercise", "chunk", "edit_mode" }) do
	tests[name]()
	print("fidelity_spec: " .. name .. " passed")
end
