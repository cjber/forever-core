local FakeClient = dofile("tests/fake_client.lua")
local env = FakeClient.new()
local ns = { L = setmetatable({}, {
	__index = function(_, key)
		return key
	end,
}) }
for _, path in ipairs({ "Core/SafeCall.lua", "Core/APIKit.lua", "Core/Open.lua", "Core/Journey.lua" }) do
	setfenv(assert(loadfile(path)), env)("ForeverCore", ns)
end
local messages = {}
env.DEFAULT_CHAT_FRAME = {
	AddMessage = function(_, text)
		messages[#messages + 1] = text
	end,
}
local combat = false
env.InCombatLockdown = function()
	return combat
end
assert(select(2, ns.Open(5)) == "invalid")
assert(select(2, ns.Open("Missing")) == "none")
local target = {}
ns.RegisterOpener("Alpha", function(where)
	assert(where == target)
	return false, "collapsed"
end, true)
local accepted, reason = ns.Open("Alpha", target)
assert(accepted == false and reason == "collapsed" and #messages == 1)
combat = true
assert(ns.Open("Alpha", target) == false and #messages == 2)
combat = false
ns.RegisterOpener("Alpha", function(where)
	return where == target
end)
assert(ns.Open("Alpha", target) == true)
ns.RegisterOpener("Alpha", function()
	error("opener failed")
end)
assert(ns.Open("Alpha") == false)
assert(#ns.SafeCallFor("Alpha"):CaughtErrors() == 1)
local journey = ns.Journey
local calls, notices = {}, 0
local unsubscribe = journey.Subscribe(function(changes)
	assert(changes.journey)
	notices = notices + 1
end)
assert(select(2, journey.Owner()) == "none")
assert(select(2, journey.Claim("", "bad", function() end)) == "invalid")
assert(journey.Claim("Alpha", "First", function(why)
	calls[#calls + 1] = why
	journey.Release("Alpha")
end))
assert(journey.Claim("Beta", "Second", function(why)
	calls[#calls + 1] = why
end))
assert(calls[1] == "replaced" and journey.Owner() == "Beta")
assert(not journey.Release("Alpha"))
assert(select(2, journey.End("Alpha")) == "invalid")
assert(notices == 0)
local timers = env.timers
env.timers = {}
for _, timer in ipairs(timers) do
	timer()
end
assert(notices == 1)
assert(journey.End("Beta") and calls[2] == "ended")
assert(select(2, journey.Owner()) == "none")
journey.Claim("Alpha", "Again", function()
	error("end failed")
end)
assert(journey.End() == false and journey.Owner() == nil)
journey.Claim("Alpha", "Again", function()
	journey.Claim("Beta", "Reentrant", function() end)
end)
assert(journey.End() and journey.Owner() == "Beta")
assert(journey.Release("Beta"))
unsubscribe()
unsubscribe()
print("open_journey_spec: passed")
