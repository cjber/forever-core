local coreName, ns = ...

-- Shared error capture for the report window. SafeCall runs a callback as pcall does and keeps the last few errors;
-- the journal beneath it also records an addon's unwrapped errors, blocked and forbidden actions and Lua warnings, so
-- a report can include them after a reload. One copy of this file loads, in ForeverCore, so it installs one global
-- error handler for every addon that registers. An error belongs to an addon when its message or stack names that
-- addon's folder, "AddOns/<addonName>/"; ForeverCore's own files are registered like any addon.

local MAX_ERRORS = 5
local MAX_MESSAGE = 300
local STACK_LINES = 4
local MAX_SIGNATURES = 50
local MAX_ADDONS = 60

---@class ForeverCaughtError
---@field label? string where it was caught, e.g. "route listener"
---@field kind string error, blocked, forbidden or warning
---@field message string the error, cut to 300 characters
---@field rawMessage? string the full error, for exact deduplication
---@field stack string up to four stack lines, outermost last
---@field count integer how many times this label and message were caught this session
---@field signature string the normalised identity, shared with the journal
---@field fromSession? boolean true for this session, false for an earlier session kept in the journal
---@field firstSeen? integer when the journal first saw the signature
---@field lastSeen? integer when the journal last saw the signature
---@field version? string the addon version at first sight
---@field build? string the client build at first sight
---@field locale? string the client locale at first sight
---@field addons? string[] the other addons loaded at first sight

---@param text string
---@param limit integer
---@return string
local function Cut(text, limit)
	if #text <= limit then
		return text
	end
	local stop = limit - 3
	-- Back off a UTF-8 continuation byte, so a character is never split.
	while stop > 0 and text:byte(stop + 1) and text:byte(stop + 1) >= 0x80 and text:byte(stop + 1) < 0xC0 do
		stop = stop - 1
	end
	return text:sub(1, stop) .. "..."
end
ns.CutText = Cut

-- The value the client handed over, or nil when it holds it secret. A secret cannot be compared, indexed, concatenated
-- or formatted, so every read of a value that may be secret goes through here (WFA-30).
---@param value any
---@return any
function ns.Readable(value)
	local canAccess = rawget(_G, "canaccessvalue")
	if type(canAccess) == "function" then
		local ok, allowed = pcall(canAccess, value)
		if not ok or not allowed then
			return nil
		end
	end
	return value
end

-- The client provides time(); the specs fall back to os.time.
---@return integer
local function Now()
	local clock = _G.time
	if type(clock) == "function" then
		return clock()
	end
	return os.time()
end

---@param value any
---@return string
local function ToString(value)
	local ok, text = pcall(tostring, value)
	return ok and text or "?"
end

-- Numbers and addresses move between sessions, so the signature keeps only their shape.
---@param text string
---@return string
local function Normalize(text)
	text = text:gsub("0[xX]%x+", "#")
	return (text:gsub("%d+%.?%d*", "#"))
end

---@param stack? string
---@return string[]
local function StackLines(stack)
	local lines = {}
	for line in (stack or ""):gmatch("[^\n]+") do
		line = strtrim(line)
		-- LuaJIT writes "file.lua:12:", the client '[string "@Interface/AddOns/.../file.lua"]:12:'.
		if #lines < STACK_LINES and line:find("%.lua%S-:%d+") then
			lines[#lines + 1] = line
		end
	end
	return lines
end

---@param name string
---@return string?
local function AddonVersion(name)
	if not (C_AddOns and C_AddOns.GetAddOnMetadata) then
		return nil
	end
	local ok, version = pcall(C_AddOns.GetAddOnMetadata, name, "Version")
	return ok and version or nil
end

---@return string?
local function ClientBuild()
	if type(GetBuildInfo) ~= "function" then
		return nil
	end
	local ok, gameVersion, build = pcall(GetBuildInfo)
	return ok and gameVersion and build or nil
end

---@return string?
local function ClientLocale()
	if type(GetLocale) ~= "function" then
		return nil
	end
	local ok, locale = pcall(GetLocale)
	return ok and locale or nil
end

-- The other addons loaded when a signature is first seen, capped so one entry cannot bloat the saved table.
---@param name string
---@return string[]?
local function LoadedAddons(name)
	local addOns = C_AddOns
	if not (addOns and addOns.GetNumAddOns and addOns.GetAddOnInfo and addOns.IsAddOnLoaded) then
		return nil
	end
	local ok, names = pcall(function()
		local result = {}
		for index = 1, addOns.GetNumAddOns() do
			if #result >= MAX_ADDONS then
				break
			end
			local addon = addOns.GetAddOnInfo(index)
			if type(addon) == "string" and addon ~= name and addOns.IsAddOnLoaded(index) then
				result[#result + 1] = addon
			end
		end
		return result
	end)
	return ok and names or nil
end

---@param list ForeverCaughtError[]
---@param signature string
---@return ForeverCaughtError?, integer?
local function Find(list, signature)
	for index, entry in ipairs(list) do
		if entry.signature == signature then
			return entry, index
		end
	end
end

-- Keep at most MAX_SIGNATURES, dropping the least recently seen.
---@param list ForeverCaughtError[]
local function Trim(list)
	while #list > MAX_SIGNATURES do
		local dropIndex = 1
		for index = 2, #list do
			if (tonumber(list[index].lastSeen) or 0) < (tonumber(list[dropIndex].lastSeen) or 0) then
				dropIndex = index
			end
		end
		table.remove(list, dropIndex)
	end
end

-- Repair a saved journal so one hand-edited or older entry cannot break the report.
---@param list table
local function Sanitize(list)
	for index = #list, 1, -1 do
		local entry = list[index]
		if type(entry) ~= "table" or type(entry.signature) ~= "string" then
			table.remove(list, index)
		else
			entry.kind = type(entry.kind) == "string" and entry.kind or "error"
			entry.message = type(entry.message) == "string" and entry.message or ""
			entry.stack = type(entry.stack) == "string" and entry.stack or ""
			entry.count = tonumber(entry.count) or 1
			entry.firstSeen = tonumber(entry.firstSeen) or Now()
			entry.lastSeen = tonumber(entry.lastSeen) or entry.firstSeen
		end
	end
end

---@param entry ForeverCaughtError
---@return ForeverCaughtError
local function Copy(entry)
	local addons
	if type(entry.addons) == "table" then
		addons = {}
		for index, name in ipairs(entry.addons) do
			addons[index] = name
		end
	end
	return {
		label = entry.label,
		kind = entry.kind,
		signature = entry.signature,
		message = entry.message,
		rawMessage = entry.rawMessage,
		stack = entry.stack,
		count = entry.count,
		firstSeen = entry.firstSeen,
		lastSeen = entry.lastSeen,
		version = entry.version,
		build = entry.build,
		locale = entry.locale,
		addons = addons,
	}
end

-- Fold one entry into another list, summing counts and keeping the first sight metadata.
---@param into ForeverCaughtError[]
---@param entry ForeverCaughtError
local function Merge(into, entry)
	local existing = Find(into, entry.signature)
	if not existing then
		into[#into + 1] = Copy(entry)
		return
	end
	existing.count = (tonumber(existing.count) or 0) + (tonumber(entry.count) or 0)
	local firstSeen, sourceFirst = tonumber(existing.firstSeen), tonumber(entry.firstSeen)
	if sourceFirst and (not firstSeen or sourceFirst < firstSeen) then
		existing.firstSeen = sourceFirst
	end
	local lastSeen, sourceLast = tonumber(existing.lastSeen), tonumber(entry.lastSeen)
	if sourceLast and (not lastSeen or sourceLast > lastSeen) then
		existing.lastSeen = sourceLast
	end
	if type(existing.message) ~= "string" then
		existing.message = entry.message
	end
	if type(existing.stack) ~= "string" then
		existing.stack = entry.stack
	end
	if type(existing.kind) ~= "string" then
		existing.kind = entry.kind
	end
	if type(existing.version) ~= "string" then
		existing.version = entry.version
	end
	if existing.build == nil then
		existing.build = entry.build
	end
	if type(existing.locale) ~= "string" then
		existing.locale = entry.locale
	end
	if type(existing.addons) ~= "table" then
		existing.addons = entry.addons
	end
end

-- One addon's journal, caught list and session set.
---@class ForeverSafeCallContext
---@field name string
---@field own string this addon's folder as it appears in a stack, "AddOns/<name>/"
---@field caught ForeverCaughtError[]
---@field session table<string, boolean>
---@field journal ForeverCaughtError[]
local Context = {}
Context.__index = Context

---@param name string
---@return ForeverSafeCallContext
local function NewContext(name)
	name = tostring(name)
	return setmetatable({
		name = name,
		own = "AddOns/" .. name .. "/",
		caught = {},
		session = {},
		journal = {},
	}, Context)
end

---@param text? string
---@return boolean
function Context:Own(text)
	return type(text) == "string" and text:find(self.own, 1, true) ~= nil
end

-- The first stack frame in this addon's folder separates two errors with the same message.
---@param stack? string
---@return string
function Context:OwnFrame(stack)
	for line in (stack or ""):gmatch("[^\n]+") do
		line = strtrim(line)
		if self:Own(line) then
			return line
		end
	end
	return ""
end

---@param message string
---@param stack? string
---@return string
function Context:Signature(message, stack)
	return Normalize(message) .. "\n" .. self:OwnFrame(stack)
end

---@param signature string
---@param kind string
---@param message string
---@param stack? string
function Context:Journal(signature, kind, message, stack)
	local entry = Find(self.journal, signature)
	local now = Now()
	local lines = table.concat(StackLines(stack), "\n")
	if entry then
		entry.count = (tonumber(entry.count) or 0) + 1
		entry.lastSeen = now
		entry.message = Cut(message, MAX_MESSAGE)
		entry.stack = lines
	else
		self.journal[#self.journal + 1] = {
			signature = signature,
			kind = kind,
			message = Cut(message, MAX_MESSAGE),
			stack = lines,
			count = 1,
			firstSeen = now,
			lastSeen = now,
			version = AddonVersion(self.name),
			build = ClientBuild(),
			locale = ClientLocale(),
			addons = LoadedAddons(self.name),
		}
	end
	Trim(self.journal)
end

---@param signature string
---@param label string
---@param kind string
---@param message string
---@param stack? string
function Context:Session(signature, label, kind, message, stack)
	self.session[signature] = true
	local entry, index = Find(self.caught, signature)
	local now = Now()
	local lines = table.concat(StackLines(stack), "\n")
	if entry then
		table.remove(self.caught, index)
	else
		entry = {
			signature = signature,
			label = label,
			kind = kind,
			message = Cut(message, MAX_MESSAGE),
			rawMessage = message,
			stack = lines,
			count = 0,
			firstSeen = now,
		}
	end
	entry.lastSeen = now
	entry.message = Cut(message, MAX_MESSAGE)
	entry.rawMessage = message
	entry.stack = lines
	entry.count = entry.count + 1
	self.caught[#self.caught + 1] = entry
	if #self.caught > MAX_ERRORS then
		table.remove(self.caught, 1)
	end
end

---@param kind string
---@param label string
---@param message any
---@param stack? string
function Context:Record(kind, label, message, stack)
	local text = ToString(message)
	local signature = self:Signature(text, stack)
	self:Journal(signature, kind, text, stack)
	self:Session(signature, label, kind, text, stack)
end

-- Keep `message` from `label`, with `stack` (a traceback) cut to its first lines that name a file.
---@param label string
---@param message any
---@param stack? string
function Context:RecordError(label, message, stack)
	self:Record("error", label, message, stack)
end

-- This session's errors first, then earlier sessions' from the journal, each marked with whether it is from this
-- session, as copies.
---@return ForeverCaughtError[]
function Context:CaughtErrors()
	local copies = {}
	for _, entry in ipairs(self.caught) do
		copies[#copies + 1] = {
			label = entry.label,
			kind = entry.kind,
			message = entry.message,
			rawMessage = entry.rawMessage,
			stack = entry.stack,
			count = entry.count,
			signature = entry.signature,
			fromSession = true,
			firstSeen = entry.firstSeen,
			lastSeen = entry.lastSeen,
		}
	end
	for _, entry in ipairs(self.journal) do
		if not self.session[entry.signature] then
			copies[#copies + 1] = {
				label = entry.kind or "error",
				kind = entry.kind,
				message = entry.message,
				rawMessage = entry.message,
				stack = entry.stack,
				count = entry.count,
				signature = entry.signature,
				fromSession = false,
				firstSeen = entry.firstSeen,
				lastSeen = entry.lastSeen,
				version = entry.version,
				build = entry.build,
				locale = entry.locale,
				addons = entry.addons,
			}
		end
	end
	return copies
end

-- Use `store`, a table from the addon's saved variables, for the journal and merge what was recorded before it loaded.
---@param store table
function Context:Attach(store)
	if type(store) ~= "table" or store == self.journal then
		return
	end
	Sanitize(store)
	for _, entry in ipairs(self.journal) do
		Merge(store, entry)
	end
	Trim(store)
	self.journal = store
end

-- The labels of the SafeCalls under way, innermost last, with the context each belongs to.
---@type { ctx: ForeverSafeCallContext, label: string }[]
local labels = {}

local previousHandler
local inHandler = false
-- Set while a caught error is handed to the game's handler, so that handler does not record it a second time.
local delivering = false

---@type table<string, ForeverSafeCallContext>
local registered = {}

-- The context for `name`, made on first use and always the same table afterwards.
---@param name string
---@return ForeverSafeCallContext
function ns.SafeCallFor(name)
	name = tostring(name or "?")
	local context = registered[name]
	if not context then
		context = NewContext(name)
		registered[name] = context
	end
	return context
end

-- BugGrabber replaces seterrorhandler with a no-op so it stays the only handler. When it does, its EventRegistry
-- callback is the only place an unwrapped error reaches us; it fires the error object's tostring, and GetErrorByID
-- turns that back into the object, which carries the same message and stack.
local bugGrabberAttached = false
local bugGrabberTarget = {}

-- Every registered addon whose folder the text names records it.
---@param kind string
---@param label string
---@param message string
---@param stack? string
local function RecordMatching(kind, label, message, stack)
	for _, context in pairs(registered) do
		if context:Own(message) or context:Own(stack) then
			context:Record(kind, label, message, stack)
		end
	end
end

---@param _ any the target this file registered, as EventRegistry passes it back
---@param tableID string the error object's tostring, as BugGrabber fires it
local function FromBugGrabber(_, tableID)
	if delivering or inHandler then
		return
	end
	local grabber = _G["BugGrabber"]
	if type(grabber) ~= "table" or type(grabber.GetErrorByID) ~= "function" then
		return
	end
	local ok, errorObject = pcall(grabber.GetErrorByID, grabber, tableID)
	if not ok or type(errorObject) ~= "table" then
		return
	end
	RecordMatching("error", "Lua error", ToString(errorObject.message), errorObject.stack)
end

-- Attach once BugGrabber and the client's EventRegistry exist. It may load before us, or after us, so the event
-- frame retries on ADDON_LOADED and PLAYER_LOGIN until both are there.
local function AttachBugGrabber()
	if bugGrabberAttached then
		return
	end
	local grabber = _G["BugGrabber"]
	local registry = _G.EventRegistry
	if type(grabber) ~= "table" or type(grabber.GetErrorByID) ~= "function" then
		return
	end
	if type(registry) ~= "table" or type(registry.RegisterCallback) ~= "function" then
		return
	end
	bugGrabberAttached = true
	pcall(registry.RegisterCallback, registry, "BugGrabber.BugGrabbed", FromBugGrabber, bugGrabberTarget)
end

-- The global error handler: keep every registered addon's errors, then always pass the error on, so BugSack and the
-- default error frame still see exactly what they saw before.
---@param message any
---@return any
local function Handler(message)
	local text = ToString(message)
	local stack = debugstack and debugstack(2) or debug.traceback("", 2)
	if not delivering then
		RecordMatching("error", "Lua error", text, stack)
	end
	if not previousHandler then
		return nil
	end
	inHandler = true
	local ok, result = pcall(previousHandler, message)
	inHandler = false
	if ok then
		return result
	end
end

-- xpcall's message handler, at the error, before the stack unwinds: keep it for the caller's report, then hand it to
-- the game's error handler here, so BugSack and the error frame capture the stack and locals where it happened.
---@param message any
local function Trace(message)
	-- The addon that wrapped the call owns its failure. The stack always passes through this file, so matching
	-- folders would also file every wrapped error under ForeverCore.
	local entry = labels[#labels]
	local stack = debugstack and debugstack(2) or debug.traceback()
	if entry then
		entry.ctx:Record("error", entry.label, ToString(message), stack)
	end
	local wasDelivering = delivering
	delivering = true
	pcall(function()
		return geterrorhandler()(message)
	end)
	delivering = wasDelivering
	return message
end

local function Finish(...)
	labels[#labels] = nil
	return ... -- multi-value: xpcall's answers, as pcall gives them
end

-- Run fn(...) as pcall would: true and its results, or false and the error. A failure is kept for this addon's report
-- and passed on to the game's error handler, never swallowed.
---@param label string where this call is made from, as the report names it
---@param fn function
---@return boolean ok, any ...
function Context:SafeCall(label, fn, ...)
	labels[#labels + 1] = { ctx = self, label = label }
	return Finish(xpcall(fn, Trace, ...))
end

-- The markers on a name the client may hold secret cannot be read; that is not this addon's error.
---@param name string
---@return boolean
local function IsRegisteredName(name)
	return registered[name] ~= nil
end

-- Install the handler and event frame once for the whole client. Every registered addon shares it.
previousHandler = type(geterrorhandler) == "function" and geterrorhandler() or nil
local set = _G.seterrorhandler
if type(set) == "function" then
	set(Handler)
end
if type(geterrorhandler) == "function" and geterrorhandler() ~= Handler then
	AttachBugGrabber()
end
if type(CreateFrame) == "function" then
	local frame = CreateFrame("Frame")
	frame:RegisterEvent("ADDON_ACTION_BLOCKED")
	frame:RegisterEvent("ADDON_ACTION_FORBIDDEN")
	frame:RegisterEvent("LUA_WARNING")
	frame:RegisterEvent("ADDON_LOADED")
	frame:RegisterEvent("PLAYER_LOGIN")
	frame:SetScript("OnEvent", function(_, event, ...)
		if event == "ADDON_LOADED" or event == "PLAYER_LOGIN" then
			AttachBugGrabber()
		elseif event == "ADDON_ACTION_BLOCKED" or event == "ADDON_ACTION_FORBIDDEN" then
			local blockedAddon, functionName = ...
			local context = IsRegisteredName(blockedAddon) and registered[blockedAddon] or nil
			if context then
				local blocked = event == "ADDON_ACTION_BLOCKED"
				local kind = blocked and "blocked" or "forbidden"
				local action = ToString(functionName)
				context:Record(kind, kind .. " action", (blocked and "Blocked: " or "Forbidden: ") .. action, nil)
			end
		elseif event == "LUA_WARNING" then
			local parts = {}
			for index = 1, select("#", ...) do
				parts[index] = ToString((select(index, ...)))
			end
			RecordMatching("warning", "Lua warning", table.concat(parts, " "), nil)
		end
	end)
end

-- Core's own context: errors in ForeverCore's files are recorded under ForeverCore.
local core = ns.SafeCallFor(coreName or "ForeverCore")
ns.SafeCall = function(...)
	return core:SafeCall(...)
end
