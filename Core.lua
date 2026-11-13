local _, ns = ...

ns.isCore = true

-- ns.store is the one authoritative settings table for this runtime copy. All core files read it through ns.Store();
-- a converted copy (ns.copy present) never touches the global ForeverCoreDB in elected mode. The standalone path
-- resolves the authoritative table in Start, after the client has loaded SavedVariables, so a pre-start read never
-- caches a placeholder over the real table. The unwrapped standalone path is transitional.
---@return table?
function ns.Store()
	return ns.store
end

-- ForeverCore is the shared floor under the Forever addons: one objective-tracker column the suite docks into, the
-- grip and Lock switch that move it, and the section order that stacks them. Every Forever addon requires this addon
-- (docs/adoption.md), so exactly one copy of each shared file loads in the game. This file is ForeverCore's own
-- install of the tracker contract: the settings the host reads, the one ns.Store() seam, and the explicit ns.Start()
-- a converted copy gets from the loader (with the transitional ADDON_LOADED handler for the unwrapped standalone).

-- One defaults constructor, used both for a throwaway table before the store exists and for the table kept in the
-- runtime store (ForeverCoreDB in the transitional standalone). The tracker scale, the Lock switch, the background
-- opacity and the detach position live in the host's own settings rather than an addon's defaults table, because the
-- host outlives whichever addon happened to load first.
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
	local db = ns.Store()
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

-- One start body: normalize the store, then attach core's journal and log, then run the one-time tracker migration.
-- Converted copies call it through ns.Start(); the unwrapped standalone path reaches it through its ADDON_LOADED frame.
local function InitializeStore()
	-- Building the host's table here is also the normalisation the host reads on every access.
	ns.TrackerHostSettings()
	if ns.AttachCoreDb then
		ns.AttachCoreDb()
	end
	if ns.MigrateTrackerSettings then
		ns.MigrateTrackerSettings()
	end
end

-- The loader calls this after the converted files have defined the runtime and before publishing the facade. An
-- elected copy must be handed its reconciled store; it refuses to invent one or fall back to the global. Only the
-- standalone copy may adopt ForeverCoreDB, and only here.
function ns.Start()
	if ns.copy ~= nil then
		if ns.mode == "standalone" then
			-- The converted standalone starts at its ADDON_LOADED, after SavedVariables; it owns the one global.
			if type(ForeverCoreDB) ~= "table" then
				ForeverCoreDB = {}
			end
			ns.store = ForeverCoreDB
		elseif type(ns.Store()) ~= "table" then
			error("ForeverCore elected Start requires a supplied ns.store table", 0)
		end
		InitializeStore()
		return
	end
	-- Transitional unwrapped standalone: Start always adopts the saved global as it stands now, replacing any
	-- placeholder a pre-saved-variables read might have left behind.
	if type(ForeverCoreDB) == "table" then
		ns.store = ForeverCoreDB
	else
		ForeverCoreDB = {}
		ns.store = ForeverCoreDB
	end
	InitializeStore()
end

-- The loader calls Login once at PLAYER_LOGIN after activation. Store reconciliation is a later slice; this is the
-- lifecycle seam that keeps the converted runtime's call shape stable.
function ns.Login() end

-- The one ADDON_LOADED handler for the transitional unwrapped standalone. Saved variables can be nil on a first
-- install, so the table and its tracker settings are made here, after the host and Expose have loaded but before any
-- consumer attaches. A converted copy gets ns.Start() from the loader instead and registers no self event.
local function InitializeSavedVariables()
	if type(ForeverCoreDB) ~= "table" then
		ForeverCoreDB = {}
	end
	ns.Start()
end

if ns.copy == nil and type(CreateFrame) == "function" then
	local frame = CreateFrame("Frame")
	frame:RegisterEvent("ADDON_LOADED")
	frame:SetScript("OnEvent", function(_, _, addon)
		if addon == "ForeverCore" then
			InitializeSavedVariables()
		end
	end)
end
