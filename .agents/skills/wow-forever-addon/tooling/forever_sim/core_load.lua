-- ForeverCore's files loaded into a spec's fake client the way the client loads them: the TOC's entries in order,
-- each XML's virtual templates registered before the Lua beside it, every Lua file run with one shared namespace.
--
--   local CoreLoad = dofile("tools/forever_sim/core_load.lua")
--   local ns = CoreLoad.load(env, { names = { "Core/SafeCall.lua", "Expose.lua" } })
--
-- A load of chosen files (`names`) leaves out files whose functions the chosen ones call. `CoreLoad.standIns` fills
-- those in with what the full load would give a client that has just logged in, so every addon's specs share one answer
-- instead of each patching its own: `ns.AtStart` (Core.lua) runs its work at once, as an unwrapped core does, and
-- `ns.AfterWorldEvents` (UI/TrackerHost.lua) waits for PLAYER_ENTERING_WORLD and VARIABLES_LOADED.
local CoreLoad = {}

local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Toc = dofile(here .. "toc.lua")

local DEFAULT_DIRECTORY = "../forever-core"

local function Exists(path)
	local handle = io.open(path .. "/ForeverCore.toc", "r")
	if handle then
		handle:close()
		return true
	end
	return false
end

-- The checkout FOREVER_CORE names, else the sibling ../forever-core. A relative path is read from the working
-- directory first, then from GITHUB_WORKSPACE, because packaged specs run from a scratch folder.
---@return string
function CoreLoad.directory()
	local configured = os.getenv("FOREVER_CORE")
	local candidates = {}
	if configured and configured ~= "" then
		candidates[#candidates + 1] = configured
		local workspace = os.getenv("GITHUB_WORKSPACE")
		if configured:sub(1, 1) ~= "/" and workspace and workspace ~= "" then
			candidates[#candidates + 1] = workspace .. "/" .. configured
		end
	else
		candidates[#candidates + 1] = DEFAULT_DIRECTORY
	end
	for _, path in ipairs(candidates) do
		local cleaned = path:gsub("/+$", "")
		if cleaned ~= "" and Exists(cleaned) then
			return cleaned
		end
	end
	error(
		"ForeverCore's checkout is not at "
			.. table.concat(candidates, " or ")
			.. "; set FOREVER_CORE to it (tools/forever-core.txt names the ref)"
	)
end

-- Fills the namespace functions a partial load or a hand-built namespace lacks; a function already there stays.
---@param ns table
---@param env table the fake client the chunks run in
---@return table ns
function CoreLoad.standIns(ns, env)
	if ns.AtStart == nil then
		ns.AtStart = function(work)
			work()
		end
	end
	if ns.AfterWorldEvents == nil then
		ns.AfterWorldEvents = function(callback)
			local eventUtil = env.EventUtil or _G.EventUtil
			assert(eventUtil, "AfterWorldEvents needs EventUtil.ContinueAfterAllEvents in the fake client")
			eventUtil.ContinueAfterAllEvents(callback, "PLAYER_ENTERING_WORLD", "VARIABLES_LOADED")
		end
	end
	return ns
end

-- Runs one ForeverCore file in `env` with `ns`, after filling the stand-ins: for a spec that builds its own namespace,
-- such as a stubbed TrackerHost beside the real UI/TrackerSection.lua.
---@param env table
---@param relative string the path as the TOC writes it, such as "UI/TrackerSection.lua"
---@param ns table
---@param options? { directory?: string, name?: string }
function CoreLoad.file(env, relative, ns, options)
	options = options or {}
	CoreLoad.standIns(ns, env)
	local chunk = assert(loadfile((options.directory or CoreLoad.directory()) .. "/" .. relative), relative)
	setfenv(chunk, env)
	chunk(options.name or "ForeverCore", ns)
end

-- Loads ForeverCore into `env` and returns the namespace. Options:
--   names: only these files (plus Locales/enUS.lua, the phrases every module reads), in TOC order; every file when nil.
--     Such a load gets the stand-ins first; a full load defines the real functions itself.
--   ns: the namespace to fill, a new one when nil. name: the addon name each chunk receives, "ForeverCore".
--   templates: called with each virtual template an XML entry declares ({ name, type, inherits }).
--   directory: the checkout, CoreLoad.directory() when nil.
---@param env table
---@param options? { names?: string[], ns?: table, name?: string, directory?: string, templates?: fun(template: table) }
---@return table
function CoreLoad.load(env, options)
	options = options or {}
	local directory = (options.directory or CoreLoad.directory()):gsub("/+$", "")
	local ns = options.ns or {}
	local wanted
	if options.names ~= nil then
		wanted = { ["Locales/enUS.lua"] = true }
		for _, name in ipairs(options.names) do
			wanted[name] = true
		end
		CoreLoad.standIns(ns, env)
	end
	-- The reader resolves each path (Toc.clean), so the TOC's own name for an entry follows the resolved directory.
	local prefix = Toc.clean(directory) .. "/"
	for _, entry in ipairs(Toc.files(directory, "ForeverCore.toc")) do
		local relative = entry.path:sub(1, #prefix) == prefix and entry.path:sub(#prefix + 1) or entry.path
		if entry.kind == "xml" then
			if options.templates then
				for _, template in ipairs(Toc.templates(entry.path)) do
					options.templates(template)
				end
			end
		elseif wanted == nil or wanted[relative] then
			local chunk = assert(loadfile(entry.path), relative)
			setfenv(chunk, env)
			chunk(options.name or "ForeverCore", ns)
		end
	end
	return ns
end

return CoreLoad
