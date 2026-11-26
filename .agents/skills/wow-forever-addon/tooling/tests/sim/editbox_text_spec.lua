-- Notification timing from live client probe 2026-11-17.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")
for _, method in ipairs({ "SetNumber", "SetText" }) do
	local sim = Sim.new({ addon = false })
	local edit = sim.G.CreateFrame("EditBox")
	local changed, set, userInput = 0, 0, nil
	edit:SetScript("OnTextChanged", function(_, input)
		changed = changed + 1
		userInput = input
	end)
	edit:SetScript("OnTextSet", function()
		set = set + 1
	end)
	edit[method](edit, 42)
	assert(edit:GetText() == "42" and edit:GetNumber() == 42)
	local function check(phase, expected)
		local actual =
			string.format("%s %s changed=%d set=%d userInput=%s", phase, method, changed, set, tostring(userInput))
		assert(actual == expected, actual)
		print(actual)
	end
	check("sync", "sync " .. method .. " changed=0 set=1 userInput=nil")
	sim:advance(0)
	check("later", "later " .. method .. " changed=1 set=1 userInput=false")
	edit[method](edit, 42)
	sim:advance(0)
	assert(changed == 1 and set == 1, "unchanged text does not notify")
	sim:expectNoErrors()
end
-- Live client probe (ForeverCore 1.17.0), with all sets in one timer callback:
-- two-diff       ("a","b")      sync=0 set=2 changed=1 ["b"@f0/false]
-- three-diff     ("a","b","c")  sync=0 set=3 changed=1 ["c"@f0/false]
-- set-and-back   ("a","")       sync=0 set=2 changed=1 [""@f0/false]
-- same-twice     ("a","a")      sync=0 set=1 changed=1 ["a"@f0/false]
-- diff-then-same ("a","b","b")  sync=0 set=2 changed=1 ["b"@f0/false]
local sim = Sim.new({ addon = false })
local cases = {
	{ name = "two-diff", texts = { "a", "b" }, expectedSets = 2 },
	{ name = "three-diff", texts = { "a", "b", "c" }, expectedSets = 3 },
	{ name = "set-and-back", texts = { "a", "" }, expectedSets = 2 },
	{ name = "same-twice", texts = { "a", "a" }, expectedSets = 1 },
	{ name = "diff-then-same", texts = { "a", "b", "b" }, expectedSets = 2 },
}
local notifications, expected = {}, {}
local function record(name, text, input)
	return string.format("%s=%q/%s", name, text, tostring(input))
end
local function checkNotifications()
	local actual = table.concat(notifications, ", ")
	assert(actual == table.concat(expected, ", "), "OnTextChanged notifications: " .. actual)
end
for _, case in ipairs(cases) do
	local edit = sim.G.CreateFrame("EditBox")
	case.edit, case.sets = edit, 0
	edit:SetScript("OnTextSet", function()
		case.sets = case.sets + 1
	end)
	edit:SetScript("OnTextChanged", function(self, input)
		notifications[#notifications + 1] = record(case.name, self:GetText(), input)
	end)
	edit:SetText(case.texts[1])
	expected[#expected + 1] = record(case.name, case.texts[#case.texts], false)
end
-- Finish the sequences in reverse order to distinguish first-change order from last-change order.
for i = #cases, 1, -1 do
	local case = cases[i]
	for j = 2, #case.texts do
		case.edit:SetText(case.texts[j])
	end
	assert(case.sets == case.expectedSets, case.name .. " synchronous OnTextSet count: " .. case.sets)
end
assert(#notifications == 0, "OnTextChanged is deferred")
sim:advance(0)
checkNotifications()

local edit = sim.G.CreateFrame("EditBox")
edit:SetScript("OnTextChanged", function(self, input)
	local value = self:GetText()
	notifications[#notifications + 1] = record("reentrant", value, input)
	if value == "outer" then
		self:SetText("nested")
		self:SetText("next frame")
	end
end)
edit:SetText("outer")
expected[#expected + 1] = record("reentrant", "outer", false)
sim:advance(0)
checkNotifications()
expected[#expected + 1] = record("reentrant", "next frame", false)
sim:advance(0)
checkNotifications()
sim:advance(0)
checkNotifications()
sim:expectNoErrors()
print("editbox_text_spec: passed")
