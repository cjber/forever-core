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
-- Live client probe (2026-11-22, ForeverCore 1.17.0), with all sets in one timer callback:
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
local function checkNotification(notifications, index, text, label)
	local entry = notifications[index]
	assert(entry and entry.text == text and entry.userInput == false, label .. " OnTextChanged payload")
end

for _, case in ipairs(cases) do
	local edit = sim.G.CreateFrame("EditBox")
	case.edit, case.sets, case.notifications = edit, 0, {}
	edit:SetScript("OnTextSet", function()
		case.sets = case.sets + 1
	end)
	edit:SetScript("OnTextChanged", function(self, input)
		table.insert(case.notifications, { text = self:GetText(), userInput = input })
	end)
	edit:SetText(case.texts[1])
end
-- Interleave the sets so each box already has a change pending when another is changed.
for i = #cases, 1, -1 do
	local case = cases[i]
	for j = 2, #case.texts do
		case.edit:SetText(case.texts[j])
	end
	assert(case.sets == case.expectedSets, case.name .. " synchronous OnTextSet count: " .. case.sets)
	assert(#case.notifications == 0, case.name .. " OnTextChanged is deferred")
end
sim:advance(0)
for _, case in ipairs(cases) do
	assert(#case.notifications == 1, case.name .. " OnTextChanged count: " .. #case.notifications)
	checkNotification(case.notifications, 1, case.texts[#case.texts], case.name)
end

local reentrant = {}
local edit = sim.G.CreateFrame("EditBox")
edit:SetScript("OnTextChanged", function(self, input)
	local value = self:GetText()
	table.insert(reentrant, { text = value, userInput = input })
	if value == "outer" then
		self:SetText("nested")
		self:SetText("next frame")
	end
end)
edit:SetText("outer")
sim:advance(0)
assert(#reentrant == 1, "reentrant changes are deferred")
checkNotification(reentrant, 1, "outer", "reentrant")
sim:advance(0)
assert(#reentrant == 2, "reentrant changes coalesce on the next frame")
checkNotification(reentrant, 2, "next frame", "reentrant")
sim:advance(0)
assert(#reentrant == 2, "no further reentrant notifications")
for _, case in ipairs(cases) do
	assert(#case.notifications == 1, case.name .. " has no later notifications")
end
-- Live client probe (client 1.60.1.71139, forever-core#1111), all calls in one timer callback:
-- insert_insert    1 'ab' user=true
-- settext_insert   1 'ab' user=true
-- insert_settext   1 'b'  user=false
local mixed = {
	{ name = "insert-insert", calls = { "Insert", "Insert" }, text = "ab", userInput = true },
	{ name = "settext-insert", calls = { "SetText", "Insert" }, text = "ab", userInput = true },
	{ name = "insert-settext", calls = { "Insert", "SetText" }, text = "b", userInput = false },
}
for _, case in ipairs(mixed) do
	local box, notifications = sim.G.CreateFrame("EditBox"), {}
	box:SetScript("OnTextChanged", function(self, input)
		table.insert(notifications, { text = self:GetText(), userInput = input })
	end)
	box[case.calls[1]](box, "a")
	box[case.calls[2]](box, "b")
	assert(#notifications == 0, case.name .. " OnTextChanged is deferred")
	sim:advance(0)
	local first = notifications[1]
	assert(#notifications == 1, case.name .. " OnTextChanged count: " .. #notifications)
	assert(first.text == case.text and first.userInput == case.userInput, case.name .. " OnTextChanged payload")
end
sim:expectNoErrors()
print("editbox_text_spec: passed")
