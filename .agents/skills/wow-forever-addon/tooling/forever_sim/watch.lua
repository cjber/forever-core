-- Gamepad-interface taint: addon writes into the Blizzard tables the gamepad UI walks in secure code.
--
-- The client marks every table field written by tainted code. Under the gamepad interface, secure Blizzard code
-- walks the map's data providers, pin pools and overlay frames, the tracker's modules and the input binding
-- stack; reading a field an addon wrote taints that walk, and its next protected call
-- (SetPreferredGamepadInteractTarget, from GamepadMainActionBarFrameMixin:UpdateInteractIcons) is blocked.
--
-- The sim cannot see table writes as they happen without proxying Blizzard's tables, so it snapshots the watched
-- tables when execution becomes tainted and compares when it is secure again: every key added, changed or removed
-- in between was written by the tainting addon. Each finding names the table, the key and where the addon's
-- code was entered.
local M = {}

-- label -> function(G) returning the table (nil while it does not exist).
M.WATCHED = {
	{ "WorldMapFrame.dataProviders", { "WorldMapFrame", "dataProviders" } },
	{ "WorldMapFrame.pinPools", { "WorldMapFrame", "pinPools" } },
	{ "WorldMapFrame.overlayFrames", { "WorldMapFrame", "overlayFrames" } },
	{ "WorldMapFrame.dataProviderEventsCount", { "WorldMapFrame", "dataProviderEventsCount" } },
	{ "WorldMapFrame.pinFrameLevelsManager.definitions", { "WorldMapFrame", "pinFrameLevelsManager", "definitions" } },
	{ "BattlefieldMapFrame.dataProviders", { "BattlefieldMapFrame", "dataProviders" } },
	{ "FlightMapFrame.dataProviders", { "FlightMapFrame", "dataProviders" } },
	{ "ObjectiveTrackerManager.containers", { "ObjectiveTrackerManager", "containers" } },
	{ "ObjectiveTrackerManager.moduleToContainerMap", { "ObjectiveTrackerManager", "moduleToContainerMap" } },
	{ "ObjectiveTrackerFrame.modules", { "ObjectiveTrackerFrame", "modules" } },
	{ "InputBindingManager.bindingSetStack", { "InputBindingManager", "bindingSetStack" } },
}

function M.build(sim)
	local Taint, G = sim.taint, sim.G
	local W = { findings = {}, snapshots = nil }
	sim.watch = W
	local fieldTaint = setmetatable({}, { __mode = "k" })
	W.fieldTaint = fieldTaint
	Taint.fieldTaint = function(t, k)
		local f = fieldTaint[t]
		return f and f[k]
	end

	local function resolve(path)
		local t = G
		for _, key in ipairs(path) do
			if type(t) ~= "table" then
				return nil
			end
			t = rawget(t, key)
		end
		return type(t) == "table" and t or nil
	end

	local function snapshot()
		local snap = {}
		for _, spec in ipairs(M.WATCHED) do
			local t = resolve(spec[2])
			if t then
				local keys = {}
				for k, v in next, t do
					keys[k] = v
				end
				snap[spec[1]] = { t = t, keys = keys }
			else
				snap[spec[1]] = false
			end
		end
		return snap
	end

	local entered
	local function onTaint(addon)
		W.snapshots = snapshot()
		entered = debug.traceback("", 4)
		W.addon = addon
	end

	local function record(addon, label, key, kind, t)
		fieldTaint[t] = fieldTaint[t] or {}
		fieldTaint[t][key] = addon
		table.insert(W.findings, {
			addon = addon,
			table = label,
			key = key,
			kind = kind,
			entered = entered,
			time = sim.time,
		})
	end

	local function onUntaint(addon)
		local snap = W.snapshots
		W.snapshots = nil
		if not snap then
			return
		end
		for _, spec in ipairs(M.WATCHED) do
			local label = spec[1]
			local t = resolve(spec[2])
			local old = snap[label]
			if t then
				local before = old and old.t == t and old.keys or {}
				for k, v in next, t do
					if before[k] ~= v then
						record(addon, label, k, before[k] == nil and "added" or "changed", t)
					end
				end
				for k in next, before do
					if rawget(t, k) == nil then
						record(addon, label, k, "removed", t)
					end
				end
			end
		end
	end

	table.insert(Taint.listeners.taint, onTaint)
	table.insert(Taint.listeners.untaint, onUntaint)

	-- The findings so far, optionally only one addon's.
	function sim.gamepadTaint(_, addon)
		local out = {}
		for _, f in ipairs(W.findings) do
			if not addon or f.addon == addon then
				out[#out + 1] = f
			end
		end
		return out
	end

	local function describe(list)
		local lines = {}
		for _, f in ipairs(list) do
			lines[#lines + 1] = string.format(
				"%s %s %s[%s]%s",
				f.addon,
				f.kind,
				f.table,
				tostring(type(f.key) == "table" and (f.key.GetDebugName and f.key:GetDebugName() or "<table>") or f.key),
				f.entered and ("\n  entered at:" .. f.entered:gsub("\n", "\n  ")) or ""
			)
		end
		return table.concat(lines, "\n")
	end
	W.describe = describe

	-- Fails if any addon wrote into a watched Blizzard table.
	function sim.expectNoGamepadTaint(_, addon)
		local list = sim:gamepadTaint(addon)
		if #list > 0 then
			error(
				"gamepad-interface taint: addon writes into Blizzard tables the gamepad UI walks:\n" .. describe(list),
				2
			)
		end
	end

	-- Turns the gamepad interface on or off (C_InputInterfaceStyle, CVAR_UPDATE).
	function sim.setGamepad(_, on)
		sim.gamepad = on and true or false
		sim.cvars.GamePadEnable = on and "1" or "0"
		sim.events.fire("CVAR_UPDATE", "GamePadEnable", sim.cvars.GamePadEnable)
		sim.events.fire("ACTIVE_INPUT_DEVICE_TYPE_CHANGED")
		sim:advance(0.1)
	end
	sim.impl["C_InputInterfaceStyle.GetCurrentStyle"] = function()
		local E = G.Enum.InputDeviceInterfaceType or {}
		return sim.gamepad and (E.Gamepad or 1) or (E.Mkb or 0)
	end

	-- One gamepad navigation pass, as the client's secure gamepad code runs on a target change: it walks the
	-- watched tables (reading a field an addon wrote taints it) and then makes its protected call.
	function sim.gamepadNavigate(_)
		sim.run(function()
			for _, spec in ipairs(M.WATCHED) do
				local t = resolve(spec[2])
				local f = t and fieldTaint[t]
				if f then
					for k, by in next, f do
						if rawget(t, k) ~= nil and not Taint.current then
							Taint.set(by)
						end
					end
				end
			end
			G.SetPreferredGamepadInteractTarget(nil)
		end)
		sim:advance(0.05)
	end
end

return M
