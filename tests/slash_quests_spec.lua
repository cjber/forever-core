local env = setmetatable({ SlashCmdList = {} }, { __index = _G })
local function noop() end
local ns = {
	CoreAPI = { version = 2, minor = 1 },
	TrackerHost = {},
	SafeCallFor = noop,
	LogFor = noop,
	ReportFor = noop,
	MapCanvasFor = noop,
}
for _, path in ipairs({ "Locales/enUS.lua", "Expose.lua" }) do
	setfenv(assert(loadfile(path)), env)("ForeverCore", ns)
end

local printed = {}
env.print = function(line)
	printed[#printed + 1] = line
end
ns.TrackerHost.Debug = function()
	return "combat = false"
end
local function run(command)
	printed = {}
	env.SlashCmdList.FOREVERCORE(command)
	assert(#printed == 1, "expected one line for " .. command)
	return printed[1]
end

local note = run("quests")
assert(not note:find("combat =", 1, true), "/fcore quests prints the quest note instead of tracker diagnostics")
assert(note:find("Questie", 1, true) and note:find("Attach to quest tracker", 1, true), "the note explains attachment")
assert(run("quest") == note, "quest and quests print the same note")
local usage = "/fcore report, /fcore debug, /fcore tracker"
assert(run("unknown"):find(usage, 1, true), "unknown commands print usage")
assert(run("") == run("unknown"), "bare /fcore prints usage")
assert(run("tracker") == "combat = false", "tracker explicitly prints the diagnostic")

print("slash_quests_spec: passed")
