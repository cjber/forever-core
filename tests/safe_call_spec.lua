-- Contract for the shared error capture used by the report window.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local handled = {}
_G.strtrim = function(text)
	return text:match("^%s*(.-)%s*$")
end
local function baseHandler(message)
	handled[#handled + 1] = message
end
local currentHandler = baseHandler
_G.geterrorhandler = function()
	return currentHandler
end
_G.seterrorhandler = function(handler)
	currentHandler = handler
end

-- The journal falls back to os.time without a clock, so give it one that moves on every read.
local clock = 0
_G.time = function()
	clock = clock + 1
	return clock
end

local frames = {}
_G.CreateFrame = function(kind)
	local frame = { kind = kind, events = {} }
	function frame:RegisterEvent(name)
		self.events[name] = true
	end
	function frame:SetScript(name, script)
		self[name] = script
	end
	frames[#frames + 1] = frame
	return frame
end

local ns = {}
assert(loadfile("Core/SafeCall.lua"))("ForeverCore", ns)

local ok, first, second = ns.SafeCall("returns", function()
	return "value", 42
end)
equal(ok, true, "successful call remains successful")
equal(first, "value", "successful call returns first value")
equal(second, 42, "successful call returns all values")

local failed, message = ns.SafeCall("failure", function()
	error("deliberate failure")
end)
equal(failed, false, "failed call returns false")
equal(message:find("deliberate failure", 1, true) ~= nil, true, "failure is returned")
equal(#handled, 1, "failure reaches the game error handler")
local errors = ns.CaughtErrors()
equal(#errors, 1, "failure is recorded")
equal(errors[1].label, "failure", "error label is recorded")
equal(errors[1].count, 1, "first failure count")
equal(type(errors[1].stack), "string", "trace is recorded")
local shared = string.rep("shared prefix ", 25)
ns.RecordError("same label", shared .. "A", "stack")
ns.RecordError("same label", shared .. "B", "stack")
ns.RecordError("same label", shared .. "A", "stack")
local distinct = ns.CaughtErrors()
equal(#distinct, 3, "same-label errors with distinct long identities remain separate")
equal(distinct[2].count, 1, "second long identity has its own count")
equal(distinct[3].count, 2, "repeated first long identity increments its own count")
equal(#distinct[2].message, 300, "long error display remains clipped")

local function previousCalls(callback)
	local before = #handled
	callback()
	return #handled - before
end

local function lastError()
	local list = ns.CaughtErrors()
	return list[#list]
end

equal(
	previousCalls(function()
		currentHandler("Interface/AddOns/ForeverCore/Core/Unwrapped.lua:12: an unwrapped error")
	end),
	1,
	"the previous handler runs once for an unwrapped error"
)
equal(lastError().kind, "error", "an unwrapped error is journalled")
equal(lastError().message:find("an unwrapped error", 1, true) ~= nil, true, "the unwrapped error is kept")

local ignoredCount = #ns.CaughtErrors()
equal(
	previousCalls(function()
		currentHandler("Interface/AddOns/OtherAddon/Other.lua:3: another addon's error")
	end),
	1,
	"the previous handler still runs for another addon"
)
equal(#ns.CaughtErrors(), ignoredCount, "another addon's error is not journalled")

equal(
	previousCalls(function()
		currentHandler("Interface/AddOns/ForeverCore/Core/Thing.lua:12: failed at 12")
	end),
	1,
	"the previous handler runs once for a numbered error"
)
local numbered = lastError()
equal(numbered.count, 1, "the numbered error is recorded once")
local numberedSignature = numbered.signature
equal(
	previousCalls(function()
		currentHandler("Interface/AddOns/ForeverCore/Core/Thing.lua:34: failed at 0x1F")
	end),
	1,
	"the previous handler runs once for the repeat"
)
equal(#ns.CaughtErrors(), ignoredCount + 1, "a repeat adds no entry")
equal(lastError().signature, numberedSignature, "numbers and addresses normalise into one signature")
equal(lastError().count, 2, "a repeat raises the count instead of adding an entry")

local frame = frames[1]
equal(frame ~= nil, true, "the journal installs an event frame")
equal(frame.events.ADDON_ACTION_BLOCKED, true, "blocked actions are registered")
equal(frame.events.ADDON_ACTION_FORBIDDEN, true, "forbidden actions are registered")
equal(frame.events.LUA_WARNING, true, "Lua warnings are registered")
equal(frame.events.ADDON_LOADED, true, "a later BugGrabber load is watched")
equal(frame.events.PLAYER_LOGIN, true, "a late BugGrabber setup is watched")

local function byKind(kind)
	for _, entry in ipairs(ns.CaughtErrors()) do
		if entry.kind == kind then
			return entry
		end
	end
end

frame.OnEvent(frame, "ADDON_ACTION_BLOCKED", "ForeverCore", "SetPoint")
local blocked = byKind("blocked")
equal(blocked ~= nil, true, "a blocked action is journalled")
equal(blocked.message:find("SetPoint", 1, true) ~= nil, true, "the blocked action names the function")
local blockedCount = #ns.CaughtErrors()

frame.OnEvent(frame, "ADDON_ACTION_BLOCKED", "OtherAddon", "SetPoint")
equal(#ns.CaughtErrors(), blockedCount, "another addon's blocked action is ignored")

frame.OnEvent(frame, "ADDON_ACTION_FORBIDDEN", "ForeverCore", "CastSpellByName")
local forbidden = byKind("forbidden")
equal(forbidden ~= nil, true, "a forbidden action is journalled")
equal(forbidden.message:find("CastSpellByName", 1, true) ~= nil, true, "the forbidden action names the function")

frame.OnEvent(frame, "LUA_WARNING", "Interface/AddOns/ForeverCore/Core/Warn.lua:4: a warning")
local warning = byKind("warning")
equal(warning ~= nil, true, "a Lua warning is journalled")
equal(warning.message:find("a warning", 1, true) ~= nil, true, "the warning text is kept")

local warningCount = #ns.CaughtErrors()
frame.OnEvent(frame, "LUA_WARNING", "Interface/AddOns/OtherAddon/Warn.lua:4: a warning")
equal(#ns.CaughtErrors(), warningCount, "another addon's warning is ignored")

frame.OnEvent(frame, "LUA_WARNING", "prefix", "Interface/AddOns/ForeverCore/Core/Warn.lua:5: second argument warning")
local secondWarning
for _, entry in ipairs(ns.CaughtErrors()) do
	if type(entry.message) == "string" and entry.message:find("second argument warning", 1, true) then
		secondWarning = entry
	end
end
equal(secondWarning ~= nil, true, "a warning is found after the first argument")
equal(secondWarning.kind, "warning", "the second-argument warning keeps its kind")
equal(
	secondWarning.message:find("prefix Interface/AddOns/ForeverCore/", 1, true) ~= nil,
	true,
	"the warning joins every argument"
)

local function findMessage(list, needle)
	for _, entry in ipairs(list) do
		if type(entry.message) == "string" and entry.message:find(needle, 1, true) then
			return entry
		end
	end
end

local function findSignature(list, signature)
	for _, entry in ipairs(list) do
		if entry.signature == signature then
			return entry
		end
	end
end

local store = {
	{
		signature = "earlier\n",
		kind = "error",
		message = "error from an earlier session",
		stack = "",
		count = 3,
		firstSeen = 1,
		lastSeen = 2,
		version = "0.1.0",
		build = "1.0.0",
		locale = "enUS",
	},
}
ns.AttachErrorJournal(store)
equal(findMessage(store, "an unwrapped error") ~= nil, true, "entries recorded before attach are merged")
equal(findMessage(store, "error from an earlier session") ~= nil, true, "an existing saved entry stays")
local savedNumbered = findSignature(store, numberedSignature)
equal(savedNumbered ~= nil, true, "a repeated signature is saved once")
equal(savedNumbered.count, 2, "attach keeps the repeat count")

local earlier = 0
for _, entry in ipairs(ns.CaughtErrors()) do
	if entry.fromSession == false then
		earlier = earlier + 1
	end
end
equal(earlier, 1, "earlier sessions are returned after this session's errors")

local capped = {}
ns.AttachErrorJournal(capped)
ns.RecordError("cap", "cap marker", "")
for index = 1, 60 do
	ns.RecordError("cap", "cap " .. string.rep("x", index), "")
end
equal(#capped, 50, "the journal keeps at most 50 signatures")
equal(findMessage(capped, "cap marker"), nil, "the least recently seen signature is dropped")

local other = {}
assert(loadfile("Core/SafeCall.lua"))("OtherAddon", other)
equal(
	previousCalls(function()
		currentHandler("Interface/AddOns/OtherAddon/Other.lua:5: its own error")
	end),
	1,
	"the chained handler still runs once"
)
local otherErrors = other.CaughtErrors()
equal(#otherErrors, 1, "a second copy records its own error")
equal(otherErrors[1].kind, "error", "the second copy records its own kind")
equal(
	previousCalls(function()
		currentHandler("Interface/AddOns/ForeverCore/Core/New.lua:6: primary through the chain")
	end),
	1,
	"the chained handler runs once for the first addon"
)
equal(#other.CaughtErrors(), 1, "a second copy ignores another addon's error")
equal(lastError().fromSession, true, "the first copy's new error is from this session")
equal(
	lastError().message:find("primary through the chain", 1, true) ~= nil,
	true,
	"the first copy still records its own error"
)

local beforeOwn = #handled
local ownOk, ownMessage = ns.SafeCall("own failure", function()
	error("Interface/AddOns/ForeverCore/Core/Boom.lua:9: own failure")
end)
equal(ownOk, false, "an own SafeCall failure returns false")
equal(ownMessage:find("own failure", 1, true) ~= nil, true, "an own SafeCall failure is returned")
equal(#handled - beforeOwn, 1, "an own SafeCall failure reaches the handler once")
equal(lastError().count, 1, "an own SafeCall failure is recorded once through the chain")

local mutable = ns.CaughtErrors()
local originalLabel = mutable[1].label
mutable[1].label = "mutated copy"
equal(ns.CaughtErrors()[1].label, originalLabel, "callers receive copies")
equal(ns.CutText(string.rep("a", 301), 300):len(), 300, "text is clipped to the limit")
equal(ns.CutText(string.rep("é", 200), 300):sub(-3), "...", "text clipping does not split UTF-8")

-- BugGrabber replaces seterrorhandler with a no-op, so its callback is then the only route for a grabbed error.
local bugCallbacks = {}
_G.BugGrabber = {
	RegisterCallback = function(_, event, callback)
		bugCallbacks[event] = callback
	end,
}
local function grabHandler(errorMessage)
	local errorObject = { message = tostring(errorMessage), stack = debug.traceback("", 2) }
	local callback = bugCallbacks.BugGrabber_BugGrabbed
	if callback then
		callback(nil, "BugGrabber_BugGrabbed", errorObject)
	end
end
_G.geterrorhandler = function()
	return grabHandler
end
_G.seterrorhandler = function() end

local grabbedNs = {}
assert(loadfile("Core/SafeCall.lua"))("GrabbyAddon", grabbedNs)
equal(bugCallbacks.BugGrabber_BugGrabbed ~= nil, true, "a BugGrabber that owns seterrorhandler still gets our callback")

bugCallbacks.BugGrabber_BugGrabbed(nil, {
	message = "Interface/AddOns/GrabbyAddon/Core/Boom.lua:7: grabbed error",
	stack = "",
})
local grabbedErrors = grabbedNs.CaughtErrors()
equal(#grabbedErrors, 1, "a grabbed unwrapped error is journalled")
equal(grabbedErrors[1].count, 1, "a grabbed unwrapped error is journalled once")

bugCallbacks.BugGrabber_BugGrabbed(nil, {
	message = "Interface/AddOns/OtherAddon/Other.lua:3: someone else's grabbed error",
	stack = "",
})
equal(#grabbedNs.CaughtErrors(), 1, "another addon's grabbed error is ignored")

local grabbedOk, grabbedMessage = grabbedNs.SafeCall("grabber", function()
	error("Interface/AddOns/GrabbyAddon/Core/Safe.lua:8: grabbed SafeCall")
end)
equal(grabbedOk, false, "a grabbed SafeCall failure returns false")
equal(grabbedMessage:find("grabbed SafeCall", 1, true) ~= nil, true, "a grabbed SafeCall failure is returned")
grabbedErrors = grabbedNs.CaughtErrors()
equal(#grabbedErrors, 2, "a grabbed SafeCall error adds one entry")
local grabbedSafeCall = findMessage(grabbedErrors, "grabbed SafeCall")
equal(grabbedSafeCall ~= nil, true, "the grabbed SafeCall error is kept")
equal(grabbedSafeCall.count, 1, "a grabbed SafeCall error is not double counted")

-- When our Handler is still in the chain ahead of BugGrabber's own handler, the callback fires during delivery and
-- must not record the same error a second time.
local chainedCallbacks = {}
_G.BugGrabber = {
	RegisterCallback = function(_, event, callback)
		chainedCallbacks[event] = callback
	end,
}
local function chainedGrabHandler(errorMessage)
	local errorObject = { message = tostring(errorMessage), stack = debug.traceback("", 2) }
	local callback = chainedCallbacks.BugGrabber_BugGrabbed
	if callback then
		callback(nil, "BugGrabber_BugGrabbed", errorObject)
	end
end
local chainedCurrent = chainedGrabHandler
_G.geterrorhandler = function()
	return chainedCurrent
end
_G.seterrorhandler = function(handler)
	chainedCurrent = handler
end

local chainedNs = {}
assert(loadfile("Core/SafeCall.lua"))("ChainedAddon", chainedNs)
equal(chainedCallbacks.BugGrabber_BugGrabbed, nil, "a handler still in the chain does not attach at load")
local chainedFrame = frames[#frames]
chainedFrame.OnEvent(chainedFrame, "ADDON_LOADED", "BugGrabber")
equal(chainedCallbacks.BugGrabber_BugGrabbed ~= nil, true, "a BugGrabber below our handler is attached on ADDON_LOADED")
chainedCurrent("Interface/AddOns/ChainedAddon/Core/Boom.lua:9: chained error")
local chainedErrors = chainedNs.CaughtErrors()
equal(#chainedErrors, 1, "a chained BugGrabber error is one entry")
equal(chainedErrors[1].count, 1, "a chained BugGrabber error is counted once")

print(("safe_call_spec: %d checks passed"):format(checks))
