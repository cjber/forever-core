-- Execution taint, as the client tracks it.
--
-- Every chunk is loaded with a chunk name naming its addon folder ("@SkillUpForever/UI/Tooltip.lua",
-- "@Blizzard_SharedXML/SharedTooltipTemplates.lua"). A call hook sees each Lua function as it starts: when it
-- belongs to an addon, the running execution becomes tainted by that addon and stays tainted until control returns
-- to the client (the end of an event, script or timer dispatch) or a securecall restores the caller's state.
-- Globals written while tainted carry that taint, and reading one taints the reader, as in the client.
local M = {}

local getinfo, sethook = debug.getinfo, debug.sethook

M.current = nil -- the addon tainting the running code, or nil when secure
M.secureFolders = {} -- folder -> true for client code (Blizzard_*, the harness)
M.addonFolders = {} -- folder -> addon name
M.globalTaint = {} -- global name -> addon that last wrote it
M.listeners = { taint = {}, untaint = {} }

local classified = {}
-- Function -> addon (or false), so the hook reads a function's source once.
local byFunction = setmetatable({}, { __mode = "k" })

local function classify(source)
	local cached = classified[source]
	if cached ~= nil then
		return cached
	end
	local folder = source:match("^@([^/\\]+)[/\\]")
	local addon = folder and M.addonFolders[folder] or false
	classified[source] = addon
	return addon
end
M.classify = classify

function M.registerAddon(folder, name)
	M.addonFolders[folder] = name or folder
	classified = {}
	byFunction = setmetatable({}, { __mode = "k" })
end

local function notify(kind, addon)
	for _, f in ipairs(M.listeners[kind]) do
		f(addon)
	end
end

-- Moves the execution to `addon`'s taint (nil: secure), telling the watchers about each change of state.
function M.set(addon)
	local was = M.current
	if was == addon then
		return
	end
	if was and addon == nil then
		notify("untaint", was)
	end
	M.current = addon
	if addon and was == nil then
		notify("taint", addon)
	end
end

local function hook()
	local info = getinfo(2, "f")
	local f = info and info.func
	if not f then
		return
	end
	local addon = byFunction[f]
	if addon == nil then
		local s = getinfo(f, "S")
		addon = classify(s.source)
		byFunction[f] = addon
	end
	if addon and M.current ~= addon then
		M.set(addon)
	end
end

function M.attach(thread)
	M.hooked = true
	if thread then
		sethook(thread, hook, "c")
	else
		sethook(hook, "c")
	end
end

function M.detach()
	sethook()
end

-- The error sink: (message, traceback, taint) for each error the client would report.
M.onError = function(message)
	io.stderr:write(tostring(message), "\n")
end

local function traceback(message)
	return { message = message, traceback = debug.traceback("", 2), taint = M.current }
end

-- Runs f(...) as the client runs a handler from C: starting with `taint` (nil for client code, or the addon that
-- set the script) and back to the caller's state afterwards. Errors go to M.onError, never up.
function M.dispatch(taint, f, ...)
	local saved = M.current
	M.set(taint)
	local result = { xpcall(f, traceback, ...) }
	if not result[1] then
		local e = result[2]
		M.onError(e.message, e.traceback, e.taint)
	end
	M.set(saved)
	return unpack(result, 1, table.maxn(result))
end

-- securecall: call f with the caller's taint, report its error, and restore the caller's taint afterwards, so a
-- tainted callback cannot taint the client code that called it.
function M.securecall(f, ...)
	local saved = M.current
	local result = { xpcall(f, traceback, ...) }
	if not result[1] then
		local e = result[2]
		M.onError(e.message, e.traceback, e.taint)
	end
	M.set(saved)
	if result[1] then
		return unpack(result, 2, table.maxn(result))
	end
end

-- The global environment every chunk runs in: an empty proxy over the real table G that records which addon wrote
-- each global and taints whoever reads a tainted one.
function M.environment(G)
	local gt = M.globalTaint
	local env = setmetatable({}, {
		__index = function(_, k)
			local v = G[k]
			if v == nil and M.onMissingGlobal then
				v = M.onMissingGlobal(k)
			end
			local by = gt[k]
			if by and v ~= nil and M.current == nil then
				M.set(by)
			end
			return v
		end,
		__newindex = function(_, k, v)
			G[k] = v
			gt[k] = M.current
		end,
		__metatable = false,
	})
	return env
end

-- Installs securecall, issecure and friends into G; `env` is the proxy from M.environment.
function M.install(G, env)
	local rawget_, rawset_, next_ = rawget, rawset, next
	G.rawget = function(t, k)
		if t == env then
			return G[k]
		end
		return rawget_(t, k)
	end
	G.rawset = function(t, k, v)
		if t == env then
			G[k] = v
			M.globalTaint[k] = M.current
			return t
		end
		return rawset_(t, k, v)
	end
	G.next = function(t, k)
		if t == env then
			return next_(G, k)
		end
		return next_(t, k)
	end
	G.pairs = function(t)
		if t == env then
			return next_, G, nil
		end
		return pairs(t)
	end
	local create, wrap = coroutine.create, coroutine.wrap
	local co = {}
	for k, v in pairs(coroutine) do
		co[k] = v
	end
	co.create = function(f)
		local thread = create(f)
		if M.hooked then
			M.attach(thread)
		end
		return thread
	end
	co.wrap = function(f)
		local thread = create(f)
		if M.hooked then
			M.attach(thread)
		end
		return function(...)
			local r = { coroutine.resume(thread, ...) }
			if not r[1] then
				error(r[2], 2)
			end
			return unpack(r, 2, table.maxn(r))
		end
	end
	local _ = wrap
	G.coroutine = co

	G.issecure = function()
		return M.current == nil
	end
	G.securecall = function(f, ...)
		if type(f) == "string" then
			f = G[f]
		end
		return M.securecall(f, ...)
	end
	G.securecallfunction = function(f, ...)
		return M.securecall(f, ...)
	end
	G.secureexecuterange = function(t, f, ...)
		for k, v in pairs(t) do
			M.securecall(f, k, v, ...)
		end
	end
	G.forceinsecure = function()
		if not M.current then
			M.set("*** ForceTaint_Strong ***")
		end
	end
	G.issecurevariable = function(t, k)
		if k == nil then
			k = t
			local by = M.globalTaint[k]
			return by == nil, by
		end
		local by = M.fieldTaint and M.fieldTaint(t, k)
		return by == nil, by
	end
	G.hooksecurefunc = function(t, name, post)
		if type(t) == "string" then
			t, name, post = env, t, name
		end
		local original = t == env and G[name] or t[name]
		if type(original) ~= "function" then
			error(string.format("hooksecurefunc(): %s is not a function", tostring(name)), 2)
		end
		local hooked = function(...)
			local result = { original(...) }
			local after = M.current
			M.securecall(post, ...)
			M.set(after)
			return unpack(result, 1, table.maxn(result))
		end
		-- The client writes the hook itself, so the field keeps its old (secure) taint.
		if t == env then
			G[name] = hooked
		else
			rawset_(t, name, hooked)
		end
	end
end

return M
