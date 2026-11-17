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
print("editbox_text_spec: passed")
