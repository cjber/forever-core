-- luacheck: globals Polestar, read globals FOREVER_SIM_STUBS
-- A stand-in for the one Polestar surface the Forever addons read, written for forever_sim (no Polestar code):
-- Polestar.Get(path) answers a setting by its path. FOREVER_SIM_STUBS.Polestar.settings = { [path] = value }.
local options = (FOREVER_SIM_STUBS and FOREVER_SIM_STUBS.Polestar) or {}
local settings = options.settings or {}

Polestar = { version = options.version or "1.0.0" }

function Polestar.Get(path)
	return settings[path]
end
