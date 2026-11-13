local _, ns = ...

-- Shared structured log for the Forever addons. A log remembers the last 200 lines, oldest dropped, so a bug report
-- can say what led to the error instead of only the error. Info, warn and error are always kept; debug is kept only
-- while the switch is on, and a dropped debug line costs no formatting at all. Nothing goes to chat: /forever debug
-- answers in the client's error frame, /forever debug show opens the report window with every attached addon's latest
-- lines selected for copying, and the report's own copy carries the last lines that fit after the error journal.
-- /forever debug on also starts the client-log capture in Core/Capture.lua, so the logs a report asks for begin at
-- once; /forever debug off stops it and puts the client's settings back.
--
-- One copy of this file loads, in ForeverCore. Each registered addon gets its own ring and saved table through
-- ns.LogFor(name); the debug switch is one state for the character that every ring shares.

local L = ns.L
local MAX_LINES = 200
local MAX_LINE = 300
local MAX_SHOWN = 50
local LEVELS = { debug = true, info = true, warn = true, error = true }

-- The one switch every registered addon shares for the character.
local switch = { enabled = false, pinned = false }

---@class ForeverDebugLogStore
---@field lines string[] the saved ring, oldest first
---@field pinned boolean the debug switch stays on across sessions

---@class ForeverDebugLogAttachment
---@field name string the addon that attached the store
---@field store ForeverDebugLogStore
---@field context? ForeverDebugLogContext
---@field listed? boolean true once it holds a store and is in the show list

-- The attached rings, in registration order, and the same by addon name so a second attach replaces its own.
---@type ForeverDebugLogAttachment[]
local stores = {}
---@type table<string, ForeverDebugLogAttachment>
local byName = {}

---@class ForeverDebugLogContext
---@field name string
---@field lines string[]
local Context = {}
Context.__index = Context

---@param value any
---@return string
local function ToString(value)
	local ok, text = pcall(tostring, value)
	return ok and text or "?"
end

-- The client's own date and this session's seconds. The client's sandbox has no os table, so both are the client's
-- globals; a spec installs the same two.
---@return string
local function Stamp()
	return ("%s +%.1fs"):format(date("%Y-%m-%d %H:%M:%S"), GetTime())
end

-- Keep `list` bounded from the oldest end.
---@param list string[]
---@param limit integer
local function Trim(list, limit)
	while #list > limit do
		table.remove(list, 1)
	end
end

---@param list string[]
---@param count integer
---@return string[]
local function Newest(list, count)
	local first = #list - count + 1
	if first < 1 then
		first = 1
	end
	local result = {}
	for index = first, #list do
		result[#result + 1] = list[index]
	end
	return result
end

---@param text string
---@return string
local function Line(text)
	return ns.CutText(text, MAX_LINE)
end

-- One line: the client's clock, this session's seconds, the level, the caller's topic and the message. The level is
-- checked before anything is formatted, so a debug line that is off costs one comparison.
---@param level string debug, info, warn or error
---@param topic string the part of the addon the line came from
---@param message any the line, or a string.format template when arguments follow
---@param ... any
function Context:Log(level, topic, message, ...)
	if level == "debug" and switch.enabled ~= true then
		return
	end
	if not LEVELS[level] then
		level = "info"
	end
	local text
	if select("#", ...) > 0 then
		local ok, formatted = pcall(string.format, message, ...)
		text = ok and formatted or ToString(message)
	else
		text = ToString(message)
	end
	self.lines[#self.lines + 1] = Line(("%s %s %s: %s"):format(Stamp(), level, ToString(topic), text))
	Trim(self.lines, MAX_LINES)
end

-- The newest `count` lines, oldest first, as copies.
---@param count? integer
---@return string[]
function Context:LogLines(count)
	local limit = tonumber(count) or MAX_SHOWN
	if limit < 0 then
		limit = 0
	end
	return Newest(self.lines, limit)
end

-- Keep or drop the pin in every attached addon's saved table.
---@param value boolean
local function SavePin(value)
	switch.pinned = value
	for _, entry in ipairs(stores) do
		entry.store.pinned = value
	end
end

-- A one-line answer goes in the client's error frame; the copyable answer (`show`) opens the report window.
---@param text string
---@param copyable? boolean
local function Notify(text, copyable)
	local report = ns.Report
	if copyable and type(report) == "table" and type(report.Show) == "function" then
		report.Show(text)
		return
	end
	local frame = rawget(_G, "UIErrorsFrame")
	if type(frame) == "table" and type(frame.AddMessage) == "function" then
		pcall(frame.AddMessage, frame, text, 1, 1, 0, 2)
	end
end

---@return string
local function State()
	if not switch.enabled then
		return L["Debug log is off."]
	end
	return switch.pinned and L["Debug log is on and pinned for this character."]
		or L["Debug log is on for this session."]
end

-- Every attached addon's newest lines, under its name. This is the copyable answer, so it may be longer than one line.
---@return string
local function ShowText()
	local parts = { State() }
	if not stores[1] then
		parts[#parts + 1] = L["No addon has attached its log yet."]
		return table.concat(parts, "\n")
	end
	for _, entry in ipairs(stores) do
		local kept = Newest(entry.store.lines, MAX_SHOWN)
		if kept[1] then
			parts[#parts + 1] = (L["%s (last %d):"]):format(entry.name, #kept)
			for _, line in ipairs(kept) do
				parts[#parts + 1] = line
			end
		else
			parts[#parts + 1] = (L["%s: no lines yet."]):format(entry.name)
		end
	end
	return table.concat(parts, "\n")
end

-- Repair a saved store so one hand-edited or older table cannot break logging.
---@param store table
local function Prepare(store)
	if type(store.lines) ~= "table" then
		store.lines = {}
	end
	for index = #store.lines, 1, -1 do
		if type(store.lines[index]) ~= "string" then
			table.remove(store.lines, index)
		end
	end
	Trim(store.lines, MAX_LINES)
	store.pinned = store.pinned == true
end

-- Use `db`, the addon's saved table, for the ring and the pin, and keep what was logged before it arrived.
---@param db table the addon's saved table; the ring lives under its `log` key
function Context:Attach(db)
	if type(db) ~= "table" then
		return
	end
	local store = db.log
	if type(store) ~= "table" then
		store = { lines = {}, pinned = false }
		db.log = store
	end
	if store == self.store then
		return
	end
	Prepare(store)
	---@cast store ForeverDebugLogStore
	for _, line in ipairs(self.lines) do
		store.lines[#store.lines + 1] = line
	end
	Trim(store.lines, MAX_LINES)
	self.lines = store.lines
	self.store = store
	local entry = byName[self.name]
	if not entry then
		entry = { name = self.name, store = self.store }
		byName[self.name] = entry
	end
	entry.store = self.store
	if not entry.listed then
		entry.listed = true
		stores[#stores + 1] = entry
	end
	-- A pin from an earlier session turns the switch on; a store that has never seen a pin never turns it off.
	if self.store.pinned then
		switch.pinned = true
		switch.enabled = true
	end
end

-- The context for `name`, made on first use and always the same table afterwards.
---@param name string
---@return ForeverDebugLogContext
function ns.LogFor(name)
	name = tostring(name or "?")
	local context = byName[name] and byName[name].context or nil
	if not context then
		context = setmetatable({ name = name, lines = {} }, Context)
		byName[name] = { name = name, store = { lines = context.lines, pinned = false }, context = context }
	end
	return context
end

-- `/forever debug` routes here: no argument toggles the session, "pin" keeps it, "off" turns it off and unpins, and
-- "show" puts every attached addon's latest lines on screen in the report window. Returns whether the argument was a
-- known subcommand.
---@param argument? string
---@return boolean handled
function ns.DebugCommand(argument)
	local command = type(argument) == "string" and argument:match("^%s*(.-)%s*$") or ""
	if command == "" then
		switch.enabled = not switch.enabled
		if switch.enabled then
			Notify(
				switch.pinned and L["Debug log is on and pinned for this character."]
					or L["Debug log is on for this session."]
			)
		else
			Notify(
				switch.pinned and L["Debug log is off for this session; it is still pinned."] or L["Debug log is off."]
			)
		end
		return true
	end
	if command == "on" then
		switch.enabled = true
		local started = type(ns.StartDebugCapture) == "function" and ns.StartDebugCapture()
		if started then
			Notify(
				L["Debug capture is on. The client's logs are in its Logs folder; turn it off with /forever debug off."]
			)
		else
			Notify(L["Debug capture could not start because ForeverCore has not finished loading."])
		end
		return true
	end
	if command == "pin" then
		local already = switch.enabled and switch.pinned
		switch.enabled = true
		SavePin(true)
		Notify(
			already and L["Debug log is already on and pinned for this character."]
				or L["Debug log is on and pinned for this character."]
		)
		return true
	end
	if command == "off" then
		switch.enabled = false
		SavePin(false)
		if type(ns.StopDebugCapture) == "function" and ns.StopDebugCapture() then
			Notify(L["Debug capture is off and the client's settings are back; the debug log is off and unpinned."])
		else
			Notify(L["Debug log is off and unpinned."])
		end
		return true
	end
	if command == "show" then
		Notify(ShowText(), true)
		return true
	end
	Notify(L["Usage: /forever debug, /forever debug on, /forever debug off, /forever debug pin, /forever debug show"])
	return false
end

---@return boolean
function ns.DebugEnabled()
	return switch.enabled == true
end
