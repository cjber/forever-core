-- Gamepad-interface taint, on the client's field rule instead of a list of watched tables.
--
-- Every table field written while an addon runs carries that addon's taint (taint.lua). Secure Blizzard code
-- that reads such a slot becomes tainted, and under the gamepad interface its next protected call
-- (SetPreferredGamepadInteractTarget, from GamepadMainActionBarFrameMixin:UpdateInteractIcons) is refused. The
-- tracker records each such secure read, so a scenario can name the field, its writer and the reader even when
-- the refused call is what the player sees.
local M = {}

local function interfaceEnum(sim, name)
	local E = sim.G.Enum and sim.G.Enum[name]
	return E or {}
end

function M.build(sim)
	local Taint = sim.taint
	local W = {}
	sim.watch = W

	-- The secure reads of addon-written slots so far, optionally only one addon's.
	function sim.gamepadTaint(_, addon)
		local out = {}
		for _, hit in ipairs(Taint.hits) do
			if not addon or hit.addon == addon then
				out[#out + 1] = hit
			end
		end
		return out
	end

	local function entered(info)
		local site = info and info.origin
		if not site then
			return ""
		end
		return string.format(" (entered from %s:%s)", tostring(site.file or "?"), tostring(site.line or "?"))
	end
	local function describe(list)
		local lines = {}
		for _, hit in ipairs(list) do
			local path = Taint.tablePath(hit.table) or "<table>"
			lines[#lines + 1] = string.format(
				"%s[%s] written by %s at %s:%s%s, read by secure code at %s:%s",
				path,
				tostring(hit.key),
				tostring(hit.addon),
				tostring(hit.write.file or "?"),
				tostring(hit.write.line or "?"),
				entered(hit.write),
				tostring(hit.read.file or "?"),
				tostring(hit.read.line or "?")
			)
		end
		return table.concat(lines, "\n")
	end
	W.describe = describe

	-- Fails only on a refused protected call caused by a field the addon wrote, the client's observable taint.
	-- A secure read that returns without a protected call is recorded in gamepadTaint but is not a failure.
	-- One line per distinct cause (field, writer line, origin line), with the number of refused calls.
	function sim.expectNoGamepadTaint(_, addon)
		local groups, order = {}, {}
		for _, error_ in ipairs(sim.errors) do
			local origin = error_.origin
			if error_.event == "ADDON_ACTION_BLOCKED" and origin and origin.write and origin.write.addon == addon then
				local key = Taint.causeKey(origin) or error_.message
				local group = groups[key]
				if not group then
					group = { message = error_.message, count = 0 }
					groups[key] = group
					order[#order + 1] = group
				end
				group.count = group.count + 1
			end
		end
		if #order > 0 then
			local lines = {}
			for _, group in ipairs(order) do
				lines[#lines + 1] = string.format("%dx %s", group.count, group.message)
			end
			error(
				"taint: protected calls refused because of fields this addon wrote:\n" .. table.concat(lines, "\n"),
				2
			)
		end
	end

	local function interfaceStyle(gamepad)
		local E = interfaceEnum(sim, "InputDeviceInterfaceType")
		return gamepad and (E.Gamepad or 1) or (E.Mkb or 0)
	end

	-- The gamepad action bar's own OnLoad registers UpdateInteractIcons on target and soft-interact changes and
	-- on binding-set changes (through BindToCoreBindingActive). The sim's template instantiation runs one of the
	-- override bars before its mixin has its map, which stops that OnLoad short; finish the client's own setup
	-- once, after login, if it did not run.
	function W.ensureGamepad()
		local G = sim.G
		local frame = G.GamepadMainActionBarFrame
		local ER = G.EventRegistry
		if not frame or not frame.PostVariableSetUp or not ER or not ER.GetCallbackTables then
			return
		end
		-- The override bars (possess, stance, targeting, shortcuts) build their CVar maps in their own OnLoad;
		-- the sim's template order can run the page unit's first check before one has. Give every key a mapping
		-- so the check has the client's answer instead of indexing nil.
		for _, bar in ipairs((frame.PageUnit and frame.PageUnit.overrideBars) or {}) do
			bar.overrideMap = bar.overrideMap or {}
			for value = 0, 12 do
				bar.overrideMap[value] = bar.overrideMap[value]
					or {
						anchor = function(owner)
							return owner
						end,
						page = 1,
					}
			end
		end
		-- The interact callback is the one defined in MainActionBarFrame.lua; other frames also listen to
		-- PLAYER_TARGET_CHANGED, so a registrant count cannot tell whether this setup ran.
		for _, callbacks in pairs(ER:GetCallbackTables()) do
			local event = callbacks["PLAYER_TARGET_CHANGED"]
			if event then
				for _, f in pairs(event) do
					local info = debug.getinfo(f, "S")
					if info and info.source and info.source:find("MainActionBarFrame", 1, true) then
						return
					end
				end
			end
		end
		pcall(frame.PostVariableSetUp, frame)
	end

	-- Turns the gamepad interface on or off (C_InputInterfaceStyle, CVAR_UPDATE), and on a change fires
	-- INPUT_DEVICE_INTERFACE_TRANSITION (new style, old style), which runs InputUtil's gamepad Setup/Init schemes.
	function sim.setGamepad(_, on)
		local was = sim.gamepad == true
		sim.gamepad = on and true or false
		sim.cvars.GamePadEnable = on and "1" or "0"
		sim.events.fire("CVAR_UPDATE", "GamePadEnable", sim.cvars.GamePadEnable)
		sim.events.fire("ACTIVE_INPUT_DEVICE_TYPE_CHANGED")
		if was ~= sim.gamepad then
			sim.events.fire("INPUT_DEVICE_INTERFACE_TRANSITION", interfaceStyle(sim.gamepad), interfaceStyle(was))
		end
		sim:advance(0.1)
	end
	sim.impl["C_InputInterfaceStyle.GetCurrentStyle"] = function()
		return interfaceStyle(sim.gamepad)
	end

	-- One gamepad navigation pass, as the client's secure gamepad code runs on a target change: the action bar's
	-- UpdateInteractIcons walks the binding stack and makes its protected call.
	function sim.gamepadNavigate(_)
		sim.run(function()
			local frame = sim.G.GamepadMainActionBarFrame
			if frame and frame.UpdateInteractIcons then
				frame:UpdateInteractIcons()
			elseif sim.G.SetPreferredGamepadInteractTarget then
				sim.G.SetPreferredGamepadInteractTarget(nil)
			end
		end)
		sim:advance(0.05)
	end

	-- A binding-set change: add and remove a set through the client's InputBindingManager, which calls the
	-- registered core-binding listeners; the gamepad action bar refreshes its interact icons from there.
	function sim.bindingSetChange(_)
		sim.run(function()
			local manager = sim.G.GamepadSharedUtility and sim.G.GamepadSharedUtility.InputBindingManager
			if not manager or not manager.AddBindingSet then
				return
			end
			local set = {
				type = "InputBindingSet",
				treatBindsAsCore = false,
				BindAll = function() end,
				Iterator = function()
					return function() end
				end,
				RunOnBuried = function() end,
			}
			manager:AddBindingSet(set)
			manager:RemoveSet(set)
		end)
		sim:advance(0.05)
	end
end

return M
