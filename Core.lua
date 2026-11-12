local _, ns = ...

ns.isCore = true

-- ForeverCore is the shared floor under the Forever addons: one objective-tracker column the suite docks into, the
-- grip and Lock switch that move it, and the section order that stacks them. Every Forever addon requires this addon
-- (docs/adoption.md), so exactly one copy of each shared file loads in the game. This file is ForeverCore's own
-- install of the tracker contract: the settings the host reads and the ADDON_LOADED handler that creates its table.

-- One defaults constructor, used both for a throwaway table before saved variables arrive and for the table kept in
-- ForeverCoreDB. The tracker scale, the Lock switch, the background opacity and the detach position live in the host's
-- own settings rather than an addon's defaults table, because the host outlives whichever addon happened to load first.
---@return ForeverTrackerSettings
local function DefaultTrackerSettings()
	return { attached = true, locked = false, scale = 1, backdropOpacity = 0 }
end

-- Repair one settings table, so a hand-edited or older value cannot break the host's layout.
---@param settings ForeverTrackerSettings
---@return ForeverTrackerSettings
local function NormalizeTrackerSettings(settings)
	if type(settings.attached) ~= "boolean" then
		settings.attached = true
	end
	if type(settings.scale) ~= "number" or settings.scale ~= settings.scale then
		settings.scale = 1
	end
	if type(settings.locked) ~= "boolean" then
		settings.locked = false
	end
	if type(settings.backdropOpacity) ~= "number" or settings.backdropOpacity ~= settings.backdropOpacity then
		settings.backdropOpacity = 0
	end
	return settings
end

-- Saved variables arrive after the TOC loads, so answer with a throwaway default until they do.
---@return ForeverTrackerSettings
function ns.TrackerHostSettings()
	local db = ForeverCoreDB
	if type(db) ~= "table" then
		return DefaultTrackerSettings()
	end
	local settings = db.trackerHost
	if type(settings) ~= "table" then
		settings = DefaultTrackerSettings()
		db.trackerHost = settings
	end
	return NormalizeTrackerSettings(settings)
end

-- The one ADDON_LOADED handler for ForeverCore. Saved variables can be nil on a first install, so the table and its
-- tracker settings are made here, after the host and Expose have loaded but before any consumer attaches.
local function InitializeSavedVariables()
	if type(ForeverCoreDB) ~= "table" then
		ForeverCoreDB = {}
	end
	-- Forever Leaderboards and peer stats are gone, so drop the one saved choice core kept for them: the window's
	-- reach. Nothing else in ForeverCoreDB belonged to them.
	ForeverCoreDB.leaderboards = nil
	-- Building the host's table here is also the normalisation the host reads on every access.
	ns.TrackerHostSettings()
	-- Core's own journal and log attach first, then the one-time copy of a consumer's old tracker settings, each
	-- through the hook its file registered. Both hooks are set by the time this event fires.
	if ns.AttachCoreDb then
		ns.AttachCoreDb()
	end
	if ns.MigrateTrackerSettings then
		ns.MigrateTrackerSettings()
	end
end

if type(CreateFrame) == "function" then
	local frame = CreateFrame("Frame")
	frame:RegisterEvent("ADDON_LOADED")
	frame:SetScript("OnEvent", function(_, _, addon)
		if addon == "ForeverCore" then
			InitializeSavedVariables()
		end
	end)
end
