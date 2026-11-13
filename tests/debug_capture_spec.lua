-- Contract for /forever debug on and off: what the client's values were, what the capture sets, what a reload
-- records, and how off and the next login put the client back.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end
local function check(value, label)
	checks = checks + 1
	assert(value, label)
end

-- The client's saved values. Every read and write is a plain table access so the spec can read back what the module
-- did, and the initial values are distinct from the ones the capture sets.
local cvars = { taintLog = "2", advancedCombatLogging = "0" }
local chat, combat = true, false
_G.GetCVar = function(name)
	return cvars[name]
end
_G.SetCVar = function(name, value)
	cvars[name] = value
	return true
end
_G.LoggingChat = function(value)
	if value ~= nil then
		chat = value
	end
	return chat
end
_G.LoggingCombat = function(value)
	if value ~= nil then
		combat = value
	end
	return combat
end

-- The client's frame creation, so the entering-world handler is reachable.
local created = {}
_G.CreateFrame = function()
	local frame = { events = {}, scripts = {} }
	function frame:RegisterEvent(event)
		self.events[event] = true
	end
	function frame:SetScript(event, callback)
		self.scripts[event] = callback
	end
	created[#created + 1] = frame
	return frame
end

_G.strtrim = function(text)
	return text:match("^%s*(.-)%s*$")
end
_G.geterrorhandler = function()
	return function() end
end
_G.seterrorhandler = function() end
_G.GetTime = function()
	return 1
end
_G.date = function()
	return "2026-11-13 12:00:00"
end
local shown = {}
_G.UIErrorsFrame = {
	AddMessage = function(_, text)
		shown[#shown + 1] = text
	end,
}

---@param target table
---@return table
local function Load(target)
	target.L = setmetatable({}, {
		__index = function(_, key)
			return key
		end,
	})
	assert(loadfile("Core/SafeCall.lua"))("CaptureAddon", target)
	assert(loadfile("Core/Capture.lua"))("CaptureAddon", target)
	assert(loadfile("Core/Log.lua"))("CaptureAddon", target)
	return target
end

---@param isInitialLogin boolean
---@param isReloadingUi boolean
local function FireEnteringWorld(isInitialLogin, isReloadingUi)
	for _, frame in ipairs(created) do
		if frame.events.PLAYER_ENTERING_WORLD then
			frame.scripts.OnEvent(frame, "PLAYER_ENTERING_WORLD", isInitialLogin, isReloadingUi)
		end
	end
end

_G.ForeverCoreDB = {}
local ns = Load({})

-- On saves each previous value before it changes the client.
equal(ns.StartDebugCapture(), true, "the capture starts")
local saved = _G.ForeverCoreDB.debugCapture
check(type(saved) == "table" and saved.on == true, "the saved state says the capture is on")
equal(saved.taintLog, "2", "the taint log CVar before the capture is saved")
equal(saved.advancedCombatLogging, "0", "the advanced combat log CVar before the capture is saved")
equal(saved.chat, true, "chat logging before the capture is saved")
equal(saved.combat, false, "combat logging before the capture is saved")
equal(cvars.taintLog, "1", "the capture sets the taint log CVar")
equal(cvars.advancedCombatLogging, "1", "the capture sets the advanced combat log CVar")
equal(chat, true, "the capture turns chat logging on")
equal(combat, true, "the capture turns combat logging on")
check(ns.DebugCaptureEnabled(), "the capture reads as on")
check(ns.DebugCaptureNotice() ~= nil, "the one-line notice is available while it is on")
check(ns.DebugCaptureShortNotice() ~= nil, "the settings line is available while it is on")

-- A fresh module load with the same saved variables keeps the values saved before the first change.
-- The client turns chat and combat logging off with the UI on a reload.
chat, combat = false, false
local reloaded = Load({})
FireEnteringWorld(false, true)
equal(_G.ForeverCoreDB.debugCapture.taintLog, "2", "a reload keeps the saved taint log value")
equal(_G.ForeverCoreDB.debugCapture.chat, true, "a reload keeps the saved chat value")
equal(cvars.taintLog, "1", "a reload applies the capture again")
equal(chat, true, "a reload turns chat logging on again")
equal(combat, true, "a reload turns combat logging on again")

-- Starting again never replaces the originals with the capture's own values.
reloaded.StartDebugCapture()
equal(_G.ForeverCoreDB.debugCapture.taintLog, "2", "starting again keeps the original taint log value")

-- Off puts every value back and clears the saved state.
equal(reloaded.StopDebugCapture(), true, "off stops the capture")
equal(cvars.taintLog, "2", "off restores the taint log CVar")
equal(cvars.advancedCombatLogging, "0", "off restores the advanced combat log CVar")
equal(chat, true, "off restores chat logging")
equal(combat, false, "off restores combat logging")
equal(_G.ForeverCoreDB.debugCapture, nil, "off clears the saved state")
check(not reloaded.DebugCaptureEnabled(), "the capture reads as off")
equal(reloaded.DebugCaptureNotice(), nil, "no notice shows while it is off")
equal(reloaded.DebugCaptureShortNotice(), nil, "no settings line shows while it is off")

-- The command's own one-line answer, and its pairing with the debug log switch.
equal(ns.DebugCommand("on"), true, "on is handled")
check(ns.DebugEnabled(), "on turns the debug log switch on")
equal(
	shown[#shown],
	"Debug capture is on. The client's logs are in its Logs folder; turn it off with /forever debug off.",
	"on answers in one line"
)
equal(_G.ForeverCoreDB.debugCapture.taintLog, "2", "the command saves the taint log value")
equal(ns.DebugCommand("off"), true, "off is handled")
check(not ns.DebugEnabled(), "off turns the debug log switch off")
equal(
	shown[#shown],
	"Debug capture is off and the client's settings are back; the debug log is off and unpinned.",
	"off answers in one line"
)
equal(_G.ForeverCoreDB.debugCapture, nil, "the command clears the saved state")

-- The next login restores and clears, so a player never leaves the capture on.
ns.StartDebugCapture()
equal(cvars.taintLog, "1", "the capture is on before the next login")
FireEnteringWorld(true, false)
equal(cvars.taintLog, "2", "the next login restores the taint log CVar")
equal(cvars.advancedCombatLogging, "0", "the next login restores the advanced combat log CVar")
equal(chat, true, "the next login restores chat logging")
equal(combat, false, "the next login restores combat logging")
equal(_G.ForeverCoreDB.debugCapture, nil, "the next login clears the saved state")

-- Zoning into an instance is neither, and leaves the capture as it is.
ns.StartDebugCapture()
FireEnteringWorld(false, false)
check(ns.DebugCaptureEnabled(), "a zone change keeps the capture on")
ns.StopDebugCapture()

print(("debug_capture_spec: %d checks passed"):format(checks))
