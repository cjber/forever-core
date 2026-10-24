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
_G.geterrorhandler = function()
	return function(message)
		handled[#handled + 1] = message
	end
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

errors[1].label = "mutated copy"
equal(ns.CaughtErrors()[1].label, "failure", "callers receive copies")
equal(ns.CutText(string.rep("a", 301), 300):len(), 300, "text is clipped to the limit")
equal(ns.CutText(string.rep("é", 200), 300):sub(-3), "...", "text clipping does not split UTF-8")

print(("safe_call_spec: %d checks passed"):format(checks))
