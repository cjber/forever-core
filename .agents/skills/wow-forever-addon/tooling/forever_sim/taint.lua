-- Execution taint, as the client tracks it.
--
-- Every chunk is loaded with a chunk name naming its addon folder ("@SkillUpForever/UI/Tooltip.lua",
-- "@Blizzard_SharedXML/SharedTooltipTemplates.lua"), and instrumented (transform.lua) so every table field
-- read and write calls __fsi_get / __fsi_set / __fsi_callm / __fsi_ctor here. A field written while an addon
-- runs carries that addon's taint; a secure reader of a tainted field becomes tainted by the addon, exactly as in
-- game. Globals use the same slot idea through the chunk environment.
--
-- A call hook is still available (FOREVER_SIM_HOOK=1) to see each function as it starts; the normal path
-- classifies a function from its chunk name only when it is first seen.
local M = {}

local getinfo, sethook = debug.getinfo, debug.sethook

M.current = nil -- the addon tainting the running code, or nil when secure
M.origin = nil -- how the current taint was picked up: { addon, kind, write = {file,line}, read = {file,line}, ... }
M.secureFolders = {} -- folder -> true for client code (Blizzard_*, the harness)
M.addonFolders = {} -- folder -> addon name
M.globalTaint = {} -- global name -> addon that last wrote it
M.globalInfo = {} -- global name -> { addon, file, line }
M.listeners = { taint = {}, untaint = {} }

-- (table, key) -> writer info. The outer table is weak-keyed so a table the game drops leaves no trace, and
-- nothing is written into the table itself: next, # and pairs see exactly what they did without the sim.
M.slots = setmetatable({}, { __mode = "k" })
M.owners = setmetatable({}, { __mode = "k" }) -- table -> "blizzard" or "addon", from its first field write
M.parents = setmetatable({}, { __mode = "k" }) -- table -> { parent table, key } it was first stored under
M.globalObjects = setmetatable({}, { __mode = "k" }) -- table-valued global -> its global name
M.hits = {} -- secure reads of an addon-tainted slot, for the scenario gate

local MAX_HITS = 5000

local addonSite -- defined below; M.set records the entry site when taint is taken

local classified = {}
-- Function -> addon (or false), so the hook reads a function's source once.
local byFunction = setmetatable({}, { __mode = "k" })

local function shortSource(source)
	if type(source) == "string" and source:sub(1, 1) == "@" then
		return source:sub(2)
	end
	return source
end
M.shortSource = shortSource

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

-- Drops every piece of state a previous client in this process left, so each scenario starts clean.
function M.reset()
	M.current, M.origin = nil, nil
	M.globalTaint, M.globalInfo = {}, {}
	M.addonFolders, M.secureFolders = {}, {}
	M.slots, M.owners = setmetatable({}, { __mode = "k" }), setmetatable({}, { __mode = "k" })
	M.parents, M.globalObjects = setmetatable({}, { __mode = "k" }), setmetatable({}, { __mode = "k" })
	M.hits = {}
	M.listeners = { taint = {}, untaint = {} }
	classified = {}
	byFunction = setmetatable({}, { __mode = "k" })
end

local function notify(kind, addon)
	for _, f in ipairs(M.listeners[kind]) do
		f(addon)
	end
end

-- Moves the execution to `addon`'s taint (nil: secure), telling the watchers about each change of state.
function M.set(addon, origin)
	local was = M.current
	if was == addon then
		if addon and origin and not M.origin then
			M.origin = origin
			if not origin.site then
				origin.site = addonSite(addon)
			end
		end
		return
	end
	if was and addon == nil then
		notify("untaint", was)
	end
	M.current = addon
	M.origin = addon and origin or nil
	if addon and origin and not origin.site then
		origin.site = addonSite(addon)
	end
	if addon and was == nil then
		notify("taint", addon)
	end
end

-- The writer location of the running function, as "file:line", skipping the helper frames in this file.
local THIS_SOURCE = debug.getinfo(1, "S").source
local function externalSite()
	local level = 2
	while true do
		local info = getinfo(level, "Sl")
		if not info then
			return nil, nil
		end
		if info.source ~= THIS_SOURCE then
			return shortSource(info.source), info.currentline
		end
		level = level + 1
	end
end
M.site = externalSite

-- The nearest addon frame on the Lua stack, optionally only `want`'s, as { addon, file, line }.
function addonSite(want)
	local level = 2
	while true do
		local info = getinfo(level, "Sl")
		if not info then
			return nil
		end
		if info.source ~= THIS_SOURCE then
			local addon = classify(info.source)
			if addon and (not want or addon == want) then
				return { addon = addon, file = shortSource(info.source), line = info.currentline }
			end
		end
		level = level + 1
	end
end
M.addonSite = addonSite

-- The addon site the current taint entered at: the origin of the slot a secure read picked it up from, the
-- dispatch or execution site recorded when the taint was set, or the nearest addon frame still on the stack.
local function originSite(origin)
	if not origin then
		return nil
	end
	if (origin.kind == "field" or origin.kind == "global") and origin.write then
		return origin.write.origin or origin.site
	end
	return origin.site
end
M.originSite = originSite

-- The writer info a field call records: the addon running now, where the write is, and the addon site the
-- taint entered at. A write by addon code names the frame writing it; a write by Blizzard code that a tainted
-- read handed the addon's taint to names the addon site the read picked it up from, not a stale addon frame
-- still lower on the stack.
function M.writer()
	local addon = M.current
	if not addon then
		return nil
	end
	local file, line = externalSite()
	local origin
	if M.origin and M.origin.kind ~= "execution" then
		origin = originSite(M.origin)
	end
	origin = origin or addonSite(addon) or originSite(M.origin)
	return { addon = addon, file = file, line = line, origin = origin }
end

-- Records (or clears) the taint of one (table, key) slot.
function M.writeSlot(t, k, info)
	local map = M.slots[t]
	if info then
		if not map then
			map = {}
			M.slots[t] = map
		end
		map[k] = info
		if M.owners[t] == nil then
			M.owners[t] = info.addon and "addon" or "blizzard"
		end
	elseif map then
		map[k] = nil
	end
end

function M.slotInfo(t, k)
	local map = M.slots[t]
	return map and map[k] or nil
end

-- The known depth of `t` from a global name, or nil when it has no path yet: used to keep the shortest of two
-- names for the same table, as the walk did. A cycle ends the chain.
local function pathDepth(t)
	local seen = {}
	local depth = 0
	local current = t
	while current do
		if seen[current] then
			return nil
		end
		seen[current] = true
		if M.globalObjects[current] then
			return depth
		end
		local parent = M.parents[current]
		if not parent then
			return nil
		end
		depth = depth + 1
		current = parent[1]
	end
	return nil
end

-- Records where a table value is stored, so a report can name it without walking the globals. The first name
-- wins, unless a later store gives the table a shorter path (the walk preferred the shortest one).
local function recordParent(t, k, v)
	if type(v) ~= "table" or (type(k) ~= "string" and type(k) ~= "number") then
		return
	end
	if M.globalObjects[v] then
		return
	end
	if M.parents[v] == nil then
		M.parents[v] = { t, k }
		return
	end
	local oldDepth = pathDepth(v)
	local newDepth = pathDepth(t)
	if newDepth and (not oldDepth or newDepth + 1 < oldDepth) then
		M.parents[v] = { t, k }
	end
end

-- Field names for a report: the recorded global path to `t`, with no walk of the globals, so it is the same on
-- every LuaJIT. nil when no recorded name reaches a global.
function M.tablePath(t)
	if type(t) ~= "table" then
		return nil
	end
	local parts, seen = {}, {}
	local current = t
	while true do
		if seen[current] then
			return nil
		end
		seen[current] = true
		local name = M.globalObjects[current]
		if name then
			parts[#parts + 1] = tostring(name)
			local path = {}
			for i = #parts, 1, -1 do
				path[#path + 1] = parts[i]
			end
			return table.concat(path, ".")
		end
		local parent = M.parents[current]
		if not parent then
			return nil
		end
		parts[#parts + 1] = tostring(parent[2])
		current = parent[1]
	end
end

-- The identity of one protected-action cause: (field, writer line, origin line), so a report lists each
-- distinct cause once with a count instead of every refused call.
function M.causeKey(origin)
	if not origin then
		return nil
	end
	local site = originSite(origin) or origin.site
	local siteKey = site and (tostring(site.file) .. ":" .. tostring(site.line)) or "?"
	if origin.kind == "field" and origin.write then
		local path = M.tablePath(origin.table) or "<table>"
		return table.concat({
			"field",
			path,
			tostring(origin.key),
			tostring(origin.write.file) .. ":" .. tostring(origin.write.line),
			siteKey,
		}, "\0")
	elseif origin.kind == "global" and origin.write then
		return table.concat({
			"global",
			tostring(origin.global),
			tostring(origin.write.file) .. ":" .. tostring(origin.write.line),
			siteKey,
		}, "\0")
	end
	return table.concat({ tostring(origin.kind), tostring(origin.addon), siteKey }, "\0")
end

function M.readSlot(t, k, info, level)
	local _ = level
	return M.readSlotAt(t, k, info, externalSite())
end

-- A secure read whose caller has already located the read site (widget methods sit between the chunk and here).
function M.readSlotAt(t, k, info, file, line)
	local read = { file = file, line = line }
	local hit = { addon = info.addon, key = k, table = t, write = info, read = read }
	if #M.hits < MAX_HITS then
		M.hits[#M.hits + 1] = hit
	end
	M.set(info.addon, { addon = info.addon, kind = "field", write = info, read = read, key = k, table = t })
end

-- t.k / t[k] as an expression.
function M.fieldGet(t, k)
	local map = M.slots[t]
	if map then
		local info = map[k]
		if info and info.addon and M.current == nil then
			M.readSlot(t, k, info, 3)
		end
	end
	return t[k]
end

-- t.k = v / t[k] = v / rawset.
function M.fieldSet(t, k, v)
	recordParent(t, k, v)
	M.writeSlot(t, k, M.writer())
	t[k] = v
end

-- A table constructor `{ ... }` writes every field it names. The table's own fields are fresh, so each (table, key)
-- slot carries the taint of the execution that built it, exactly as `t.k = v` does.
function M.constructor(t)
	local info, wrote
	for k, v in next, t do
		recordParent(t, k, v)
		if not wrote then
			wrote, info = true, M.writer()
		end
		M.writeSlot(t, k, info)
	end
	return t
end

-- t:m(...), which reads the method field once and calls it with t.
function M.methodCall(t, k, ...)
	local map = M.slots[t]
	if map then
		local info = map[k]
		if info and info.addon and M.current == nil then
			M.readSlot(t, k, info, 3)
		end
	end
	local f = t[k]
	return f(t, ...)
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
		M.set(addon, { addon = addon, kind = "execution" })
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
	return { message = message, traceback = debug.traceback("", 2), taint = M.current, origin = M.origin }
end

-- Runs f(...) as the client runs a handler from C: starting with `taint` (nil for client code, or the addon that
-- set the script) and back to the caller's state afterwards. `site` is the addon frame that handed this code to
-- the client (the SetScript or timer registration), for when no addon frame is on the stack as it runs. Errors go
-- to M.onError, never up.
function M.dispatchFrom(taint, site, f, ...)
	local saved, savedOrigin = M.current, M.origin
	M.set(taint, taint and { addon = taint, kind = "dispatch", site = site } or nil)
	local result = { xpcall(f, traceback, ...) }
	if not result[1] then
		local e = result[2]
		M.onError(e.message, e.traceback, e.taint)
	end
	M.current, M.origin = saved, savedOrigin
	return unpack(result, 1, table.maxn(result))
end

function M.dispatch(taint, f, ...)
	return M.dispatchFrom(taint, nil, f, ...)
end

-- securecall / securecallfunction: the callee runs in the caller's execution taint. It protects a secure caller
-- from its callee, never upgrades a tainted caller: a secure caller is secure again after the call even if the
-- callee tainted itself, and a tainted caller stays tainted. Errors go to the error handler, not the caller.
function M.securecall(f, ...)
	local saved, savedOrigin = M.current, M.origin
	local result = { xpcall(f, traceback, ...) }
	if not result[1] then
		local e = result[2]
		M.onError(e.message, e.traceback, e.taint)
	end
	M.current, M.origin = saved, savedOrigin
	if result[1] then
		return unpack(result, 2, table.maxn(result))
	end
end

-- A post-hook (hooksecurefunc, HookScript) is isolated from the execution that runs the original: it starts
-- secure and the caller's state returns afterwards, whatever the hook taints.
function M.securecallIsolated(f, ...)
	local saved, savedOrigin = M.current, M.origin
	M.current, M.origin = nil, nil
	local result = { xpcall(f, traceback, ...) }
	if not result[1] then
		local e = result[2]
		M.onError(e.message, e.traceback, e.taint)
	end
	M.current, M.origin = saved, savedOrigin
	if result[1] then
		return unpack(result, 2, table.maxn(result))
	end
end

-- A C API that runs Blizzard Lua synchronously: that Lua runs in the caller's execution taint, as a script
-- fired by a Lua call does. There is no blanket secure start; an engine boundary that really starts secure is
-- modelled by the native that has it. Errors go back to the caller, unlike securecall, because the client
-- raises them from the API call itself.
function M.callSecure(f, ...)
	local saved, savedOrigin = M.current, M.origin
	local result = { pcall(f, ...) }
	M.current, M.origin = saved, savedOrigin
	if not result[1] then
		error(result[2], 0)
	end
	return unpack(result, 2, table.maxn(result))
end

-- A table-valued global can be named in a failure report.
local function named(k, v)
	if type(v) == "table" and M.current == nil then
		M.globalObjects[v] = M.globalObjects[v] or k
	end
end

-- The global environment every chunk runs in: an empty proxy over the real table G that records which addon wrote
-- each global and taints whoever reads a tainted one.
function M.environment(G)
	M.globalTable = G
	local gt = M.globalTaint
	local env = setmetatable({}, {
		__index = function(_, k)
			local v = G[k]
			if v == nil and M.onMissingGlobal then
				v = M.onMissingGlobal(k)
			end
			local info = M.globalInfo[k]
			if info and v ~= nil and M.current == nil then
				M.set(info.addon, { addon = info.addon, kind = "global", global = k, write = info })
			end
			return v
		end,
		__newindex = function(_, k, v)
			G[k] = v
			gt[k] = M.current
			named(k, v)
			if M.current then
				local file, line = externalSite()
				M.globalInfo[k] = {
					addon = M.current,
					file = file,
					line = line,
					origin = addonSite(M.current) or originSite(M.origin),
				}
			else
				M.globalInfo[k] = nil
			end
		end,
		__metatable = false,
	})
	return env
end

-- Installs securecall, issecure and friends into G; `env` is the proxy from M.environment.
function M.install(G, env)
	local rawget_, rawset_, next_ = rawget, rawset, next
	local function slotRead(t, k, level)
		local info = M.slotInfo(t, k)
		if info and info.addon and M.current == nil then
			M.readSlot(t, k, info, level)
		end
	end
	G.rawget = function(t, k)
		if t == env then
			return env[k]
		end
		slotRead(t, k, 2)
		return rawget_(t, k)
	end
	G.rawset = function(t, k, v)
		if t == env then
			env[k] = v
			return t
		end
		recordParent(t, k, v)
		M.writeSlot(t, k, M.writer())
		return rawset_(t, k, v)
	end
	G.next = function(t, k)
		if t == env then
			return next_(G, k)
		end
		local key, value = next_(t, k)
		if key ~= nil and M.slots[t] then
			slotRead(t, key, 2)
		end
		return key, value
	end
	G.pairs = function(t)
		if t == env then
			return next_, G, nil
		end
		return function(tt, key)
			return G.next(tt, key)
		end, t, nil
	end
	G.ipairs = function(t)
		return function(tt, i)
			i = i + 1
			local value = tt[i]
			if value == nil then
				return nil
			end
			slotRead(tt, i, 2)
			return i, value
		end,
			t,
			0
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

	-- The table library mutates slots in C; record those writes with the running taint, as a field write would.
	local table_ = G.table
	if table_ and table_ ~= table then
		local insert_, remove_, sort_ = table_.insert, table_.remove, table_.sort
		local function markRange(t)
			local info = M.writer()
			local n = #t
			for i = 1, n do
				M.writeSlot(t, i, info)
			end
		end
		G.table.insert = function(t, ...)
			local count = select("#", ...)
			local position = count >= 2 and (select(1, ...)) or (#t + 1)
			local first, second = ...
			local result
			if count >= 2 then
				result = insert_(t, first, second)
			else
				result = insert_(t, first)
			end
			M.writeSlot(t, position, M.writer())
			return result
		end
		G.table.remove = function(t, position)
			local result = remove_(t, position)
			M.writeSlot(t, position or #t + 1, M.writer())
			return result
		end
		G.table.sort = function(t, comparator)
			local result = sort_(t, comparator)
			markRange(t)
			return result
		end
		local wipe_ = G.table.wipe
		if wipe_ then
			G.table.wipe = function(t)
				local map = M.slots[t]
				if map then
					for k in next, map do
						M.writeSlot(t, k, nil)
					end
				end
				return wipe_(t)
			end
		end
	end
	if G.wipe and G.table and G.wipe ~= G.table.wipe then
		local wipe_ = G.wipe
		G.wipe = function(t)
			local map = M.slots[t]
			if map then
				for k in next, map do
					M.writeSlot(t, k, nil)
				end
			end
			return wipe_(t)
		end
	end

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
		-- secureexecuterange walks the table in C and calls each pair the way securecallfunction does from the
		-- caller's state. A pair is also tainted when its slot was written by an addon or `f` itself is addon
		-- code, so a secure registry read of an addon callback taints only that pair; taint from one pair never
		-- carries to the next, and the caller is restored afterwards.
		local saved, savedOrigin = M.current, M.origin
		local fInfo = getinfo(f, "S")
		local fAddon = fInfo and classify(fInfo.source) or false
		local keys = {}
		for k in next, t do
			keys[#keys + 1] = k
		end
		local readFile, readLine = externalSite()
		for _, k in ipairs(keys) do
			M.current, M.origin = saved, savedOrigin
			local slot = M.slotInfo(t, k)
			if slot and slot.addon then
				M.set(slot.addon, {
					addon = slot.addon,
					kind = "field",
					write = slot,
					read = { file = readFile, line = readLine },
					key = k,
					table = t,
				})
			elseif fAddon then
				M.set(fAddon, { addon = fAddon, kind = "execution" })
			end
			M.securecall(f, k, t[k], ...)
		end
		M.current, M.origin = saved, savedOrigin
	end
	G.forceinsecure = function()
		if not M.current then
			M.set("*** ForceTaint_Strong ***", { addon = "*** ForceTaint_Strong ***", kind = "force" })
		end
	end
	G.issecurevariable = function(t, k)
		if k == nil then
			k = t
			local info = M.globalInfo[k]
			local by = info and info.addon or nil
			return by == nil, by
		end
		local info = M.slotInfo(t, k)
		return not (info and info.addon), info and info.addon
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
			M.securecallIsolated(post, ...)
			M.set(after, M.origin)
			return unpack(result, 1, table.maxn(result))
		end
		-- The client writes the hook itself, so the field keeps its old (secure) taint.
		if t == env then
			G[name] = hooked
		else
			rawset_(t, name, hooked)
		end
	end
	M.installHelpers(G)
end

-- The field helpers the instrumented chunks call.
function M.installHelpers(G)
	G.__fsi_get = M.fieldGet
	G.__fsi_set = M.fieldSet
	G.__fsi_callm = M.methodCall
	G.__fsi_ctor = M.constructor
end

return M
