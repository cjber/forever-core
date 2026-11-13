local _, ns = ...

-- `/forever debug on` turns the client's own logs on, the way !!DevSessionLog does, so a player's report can include
-- them; `/forever debug off` or the next login puts the client's settings back. The values found before the
-- first change are saved under ForeverCoreDB.debugCapture and kept across a reload, so a second load never records our
-- own values as the originals. Nothing is sent anywhere: the logs stay in the client's Logs folder.
--
-- The capture sets exactly what !!DevSessionLog sets: the taint log CVar, the advanced combat log CVar, chat logging
-- and combat logging. Each previous value is put back when the capture stops.

-- The CVars the capture turns on, with the value !!DevSessionLog sets.
local CVARS = {
	{ name = "taintLog", value = "1" },
	{ name = "advancedCombatLogging", value = "1" },
}

---@return ForeverCoreSavedVariables?
local function Saved()
	local db = rawget(_G, "ForeverCoreDB")
	return type(db) == "table" and db or nil
end

-- A value the client holds secret cannot be read or formatted (Core/SafeCall.lua, loaded first).
local Readable = ns.Readable

---@param name string
---@return string?
local function ReadCVar(name)
	local get = rawget(_G, "GetCVar")
	if type(get) ~= "function" then
		return nil
	end
	local ok, value = pcall(get, name)
	if not ok then
		return nil
	end
	value = Readable(value)
	if type(value) == "string" then
		return value
	end
end

---@param name string
---@return boolean?
local function ReadLogging(name)
	local read = rawget(_G, name)
	if type(read) ~= "function" then
		return nil
	end
	local ok, enabled = pcall(read)
	if not ok then
		return nil
	end
	enabled = Readable(enabled)
	if type(enabled) == "boolean" then
		return enabled
	end
end

---@param name string
---@param value boolean
local function SetLogging(name, value)
	local set = rawget(_G, name)
	if type(set) == "function" then
		pcall(set, value)
	end
end

---@param state ForeverDebugCaptureState
local function Apply(state)
	local set = rawget(_G, "SetCVar")
	if type(set) == "function" then
		for _, cvar in ipairs(CVARS) do
			if state[cvar.name] ~= nil then
				pcall(set, cvar.name, cvar.value)
			end
		end
	end
	if state.chat ~= nil then
		SetLogging("LoggingChat", true)
	end
	if state.combat ~= nil then
		SetLogging("LoggingCombat", true)
	end
end

---@param state ForeverDebugCaptureState
local function Restore(state)
	local set = rawget(_G, "SetCVar")
	if type(set) == "function" then
		for _, cvar in ipairs(CVARS) do
			local previous = state[cvar.name]
			if type(previous) == "string" then
				pcall(set, cvar.name, previous)
			end
		end
	end
	if type(state.chat) == "boolean" then
		SetLogging("LoggingChat", state.chat)
	end
	if type(state.combat) == "boolean" then
		SetLogging("LoggingCombat", state.combat)
	end
end

-- The saved state, when it says the capture is on.
---@return ForeverDebugCaptureState?
local function State()
	local db = Saved()
	local state = db and db.debugCapture
	if type(state) == "table" and state.on == true then
		return state
	end
end

-- Turn the capture on. The saved state is made only when there is none, so a load with the state already on keeps the
-- values saved before the first change and applies the capture again instead of replacing them.
---@return boolean started
function ns.StartDebugCapture()
	local db = Saved()
	if not db then
		return false
	end
	local state = db.debugCapture
	if type(state) ~= "table" or state.on ~= true then
		state = { on = true } ---@type ForeverDebugCaptureState
		for _, cvar in ipairs(CVARS) do
			state[cvar.name] = ReadCVar(cvar.name)
		end
		state.chat = ReadLogging("LoggingChat")
		state.combat = ReadLogging("LoggingCombat")
		db.debugCapture = state
	end
	Apply(state)
	return true
end

-- Put back every saved value and clear the saved state.
---@return boolean stopped true when a capture was on and has now been restored
function ns.StopDebugCapture()
	local db = Saved()
	local state = db and db.debugCapture
	if type(state) ~= "table" or state.on ~= true then
		return false
	end
	Restore(state)
	db.debugCapture = nil
	return true
end

-- A reload keeps the capture: the client turns chat and combat logging off with the UI, so they are applied again.
function ns.ResumeDebugCapture()
	local state = State()
	if state then
		Apply(state)
	end
end

---@return boolean
function ns.DebugCaptureEnabled()
	return State() ~= nil
end

-- The one line the report window and the settings page show while the capture is on.
local CAPTURE_NOTICE = "Debug capture is on. Attach the files in the client's Logs folder to your report. "
	.. "Turn it off with /forever debug off."
---@return string?
function ns.DebugCaptureNotice()
	if not ns.DebugCaptureEnabled() then
		return nil
	end
	return ns.L[CAPTURE_NOTICE]
end

-- The same state in one short line, for the settings pages, where it sits beside the title.
---@return string?
function ns.DebugCaptureShortNotice()
	if not ns.DebugCaptureEnabled() then
		return nil
	end
	return ns.L["Debug capture is on: /forever debug off stops it."]
end

-- The capture lasts across reloads and ends at the next login, so a player never leaves it on by accident.
-- PLAYER_LOGOUT cannot tell the two apart (it fires on a reload too); PLAYER_ENTERING_WORLD says which one this is.
-- The CVars stay set between a logout and the next login, which is when they are put back.
---@param isInitialLogin boolean?
---@param isReloadingUi boolean?
function ns.DebugCaptureEnteringWorld(isInitialLogin, isReloadingUi)
	if isInitialLogin then
		ns.StopDebugCapture()
	elseif isReloadingUi then
		ns.ResumeDebugCapture()
	end
end

if type(CreateFrame) == "function" then
	local frame = CreateFrame("Frame")
	frame:RegisterEvent("PLAYER_ENTERING_WORLD")
	frame:SetScript("OnEvent", function(_, event, isInitialLogin, isReloadingUi)
		if event == "PLAYER_ENTERING_WORLD" then
			ns.DebugCaptureEnteringWorld(isInitialLogin, isReloadingUi)
		end
	end)
end
