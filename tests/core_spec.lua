-- ForeverCore's own install of the shared contract: the TOC ships every file the host needs, the settings the host
-- reads survive saved variables arriving late, and Expose.lua publishes what the addon's companions reach for.
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end

-- The TOC is the one list of what ships, so a file it names must exist and every shared file must be named.
local function tocFiles()
	local files, loading = {}, false
	for line in io.lines("ForeverCore.toc") do
		line = line:gsub("\r$", "")
		if line:match("^%s*$") or line:match("^##") then
			loading = loading
		elseif line:match("^%s*#") then
			loading = loading
		else
			files[#files + 1] = (line:gsub("\\", "/"))
		end
	end
	return files
end

local shipped = {}
for _, path in ipairs(tocFiles()) do
	shipped[path] = true
	local handle = io.open(path, "rb")
	check(handle ~= nil, "TOC names a file that is not there: " .. path)
	if handle then
		handle:close()
	end
end
for _, path in ipairs({
	"Core.lua",
	"Expose.lua",
	"Locales/enUS.lua",
	"UI/TrackerHost.lua",
	"UI/TrackerLock.lua",
	"UI/TrackerOrder.lua",
	"UI/TrackerQuestie.lua",
}) do
	check(shipped[path] == true, "TOC does not load " .. path)
end
-- The lock, order and questie modules answer the host, so they load before it.
local hostAt, lockAt
for index, path in ipairs(tocFiles()) do
	hostAt = path == "UI/TrackerHost.lua" and index or hostAt
	lockAt = path == "UI/TrackerLock.lua" and index or lockAt
end
check(hostAt ~= nil and lockAt ~= nil and lockAt < hostAt, "the grip loads before the host it drags")

-- Core.lua, loaded the way the client loads it, with no saved variables yet.
local ns = {}
local env = { type = type, math = math, pairs = pairs, ipairs = ipairs }
setmetatable(env, { __index = _G })
local core = assert(loadfile("Core.lua"))
setfenv(core, env)
core("ForeverCore", ns)
check(ns.isCore == true, "Core.lua marks its namespace")
check(type(ns.TrackerHostSettings) == "function", "Core.lua publishes the host's settings")
local settings = ns.TrackerHostSettings()
check(
	settings.attached == true and settings.locked == false and settings.scale == 1,
	"a fresh install docks the column"
)
check(ns.TrackerHostSettings() ~= settings, "a table with no saved variables is never kept")

-- With saved variables, one table is kept and repaired.
env.ForeverCoreDB = { trackerHost = { attached = false, scale = 0 / 0, locked = "yes" } }
local saved = ns.TrackerHostSettings()
check(saved.attached == false, "a saved detach survives")
check(saved.scale == 1, "a broken scale falls back to 1")
check(saved.locked == false, "a broken Lock switch falls back to off")
check(env.ForeverCoreDB.trackerHost == saved, "the saved table is the one kept")

-- Expose.lua publishes the shared modules the host built, and attaches through them.
local host = { attached = {} }
function host.Attach(module)
	host.attached[#host.attached + 1] = module
end
function host.Debug()
	return "debug"
end
ns.TrackerHost = host
ns.TrackerLock, ns.TrackerOrder = { name = "lock" }, { name = "order" }
ns.TrackerQuestie = { name = "questie" }
local printed
env.print = function(text)
	printed = text
end
env.SlashCmdList = {}
local expose = assert(loadfile("Expose.lua"))
setfenv(expose, env)
expose("ForeverCore", ns)
local ForeverCore = env.ForeverCore
check(type(ForeverCore) == "table", "Expose.lua publishes the core")
check(ForeverCore.name == "ForeverCore", "the core knows its name")
check(ForeverCore.TrackerHost == host, "the core publishes the host")
check(ForeverCore.TrackerLock == ns.TrackerLock and ForeverCore.TrackerOrder == ns.TrackerOrder, "and the modules")
local module = {}
check(ForeverCore.Attach(module) == true, "Attach hands a section to the column")
check(host.attached[1] == module, "Attach reaches the host")
env.SLASH_FOREVERCORE1 = nil
check(env.SlashCmdList.FOREVERCORE ~= nil, "the slash command is registered")
env.SlashCmdList.FOREVERCORE()
check(printed == "debug", "the slash command prints the host's diagnostic")
ns.TrackerHost = nil
check(ForeverCore.Attach({}) == false, "a client with no native tracker attaches nothing")

print(("core_spec: %d checks passed"):format(checks))
