-- The converted runtime identity: a loader copy that runs Core.lua and Expose.lua as chunks keeps core's fixed name,
-- publishes the facade on the namespace only, starts against the reconciled store and never creates ForeverCoreDB.
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local env = setmetatable({}, { __index = _G })
env._G = env
env.GetLocale = function()
	return "enUS"
end
env.GetBuildInfo = function()
	return "1.60.1", "70938"
end
env.date = function()
	return "2026-01-01 00:00:00"
end
env.GetTime = function()
	return 1
end
env.strtrim = function(text)
	return text:match("^%s*(.-)%s*$") or text
end
env.geterrorhandler = function()
	return function() end
end
env.ForeverCoreLoader = {
	Offers = function()
		return {}
	end,
	Candidates = function()
		return { { folder = "AddonA", build = 1012001 } }
	end,
	Selected = function()
		return { folder = "AddonA", build = 1012001 }
	end,
}

local ns = {
	copy = { build = 1012001 },
	mode = "elected",
	folder = "AddonA",
	root = "Interface\\AddOns\\AddonA\\Libs\\ForeverCore",
	build = 1012001,
}
setfenv(assert(loadfile("Core.lua")), env)("ForeverCore", ns)
check(type(ns.Store), "Core.lua publishes the store seam")
check(ns.Store() == nil, "a converted copy starts with no placeholder store")
ns.Start()
check(type(ns.Store()) == "table", "Start reconciles an elected store")
check(env.ForeverCoreDB == nil, "an elected start creates no ForeverCoreDB")
check(ns.Store().trackerHost.attached == false, "and normalizes the tracker defaults")

-- Stub the module surface Expose publishes, so the converted chunk is the only code under test.
ns.TrackerHost = { Debug = function() end }
ns.SafeCallFor = function()
	return {
		SafeCall = function()
			return true
		end,
		RecordError = function() end,
		CaughtErrors = function()
			return {}
		end,
		Attach = function(_, db)
			ns.attached = db
		end,
	}
end
ns.LogFor = function()
	return { Log = function() end, LogLines = function() end, Attach = function() end }
end
ns.ReportFor = function()
	return {}
end
ns.MapCanvasFor = function()
	return {}
end
ns.CoreAPI = { version = 2, minor = 2 }
ns.CutText = function(text)
	return text
end
ns.DebugEnabled = function()
	return false
end
ns.DebugCommand = function()
	return true
end

setfenv(assert(loadfile("Expose.lua")), env)("ForeverCore", ns)
check(env.ForeverCore == nil, "converted Expose never publishes the global facade")
check(type(ns.ForeverCore) == "table", "the converted facade lives on the namespace")
equal(ns.ForeverCore.loaderSchema, 1, "the converted facade declares the loader schema")
equal(ns.ForeverCore.build, 1012001, "the converted facade carries the sealed build")

-- Attaching core's own history reads the namespace store, not the standalone global.
ns.attached = nil
ns.AttachCoreDb()
check(ns.attached == ns.Store().errors, "AttachCoreDb attaches the namespace store's journal")

-- Start runs the attach and migration hooks in order and keeps the one store.
local order = {}
ns.AttachCoreDb = function()
	order[#order + 1] = "attach"
end
ns.MigrateTrackerSettings = function()
	order[#order + 1] = "migrate"
end
ns.Start()
equal(order[1], "attach", "Start attaches the journal before migration")
equal(order[2], "migrate", "then runs the one-time tracker migration")
check(env.ForeverCoreDB == nil, "a converted Start still creates no global saved table")

print(("runtime_identity_spec: %d checks passed"):format(checks))
