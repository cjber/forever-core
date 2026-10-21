local _, ns = ...
ns.isCore = true

-- ForeverCore is the shared floor under the Forever addons: one objective-tracker column the suite docks into, the
-- grip and Lock switch that move it, and the section order that stacks them. Every Forever addon ships these same
-- files, vendored from this repo (docs/adoption.md), so a client with several of them installed still draws one
-- column: the first host to load publishes ForeverTrackerHost and the rest adopt it rather than building a second.
-- This file is ForeverCore's own install of that contract: the settings the host reads and nothing else.

-- The tracker scale, the Lock switch and the detach position live in the host's own settings rather than an addon's
-- defaults table, because the host outlives whichever addon happened to load first.
local DEFAULTS = { attached = true, locked = false, scale = 1 }
ns.Defaults = DEFAULTS

-- Saved variables arrive after the TOC loads, so answer with a throwaway default until they do.
---@return ForeverTrackerSettings
function ns.TrackerHostSettings()
	if type(ForeverCoreDB) ~= "table" then
		return { attached = true, locked = false, scale = 1 }
	end
	local settings = ForeverCoreDB.trackerHost
	if type(settings) ~= "table" then
		settings = { attached = true, locked = false, scale = 1 }
		ForeverCoreDB.trackerHost = settings
	end
	if type(settings.scale) ~= "number" or settings.scale ~= settings.scale then
		settings.scale = 1
	end
	if type(settings.locked) ~= "boolean" then
		settings.locked = false
	end
	return settings
end
