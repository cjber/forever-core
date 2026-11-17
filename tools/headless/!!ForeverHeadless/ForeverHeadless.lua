-- Dev addon for tools/headless/forever_client.py. The launcher links this folder into AddOns only for its own session
-- and removes it on stop, so a player's login never loads it.
-- Config.lua is generated into an isolated session copy before the client starts. A missing config refuses readiness.
local SAFE_CHARACTER = _G.FOREVER_HEADLESS_CHARACTER
local UnitGUID = _G.UnitGUID
local UnitAffectingCombat = _G.UnitAffectingCombat
local IsResting = _G.IsResting
local MARKER = {
	"10011001",
	"01100110",
	"11001001",
	"00110110",
	"10101100",
	"01010011",
	"11100010",
	"00011101",
}

local function unsafe(api, ...)
	return type(api) ~= "function" or api(...) ~= false
end

local function safety()
	return unsafe(_G.UnitIsDeadOrGhost, "player"), unsafe(UnitAffectingCombat, "player") or unsafe(_G.InCombatLockdown)
end

local function safeCharacter()
	if type(SAFE_CHARACTER) ~= "table" then
		return false, "no safe parked character configured"
	end
	if type(UnitGUID) ~= "function" or type(UnitAffectingCombat) ~= "function" then
		return false, "player identity or combat API unavailable"
	end
	local name, realm = UnitName("player")
	local guid = UnitGUID("player")
	if type(name) ~= "string" or name == "" or type(guid) ~= "string" or guid == "" then
		return false, "player identity unavailable"
	end
	if name ~= SAFE_CHARACTER.name or guid ~= SAFE_CHARACTER.guid then
		return false, "unexpected player identity"
	end
	local dead, combat = safety()
	if dead then
		return false, "player is dead or a ghost"
	end
	if combat then
		return false, "player is in combat"
	end
	if SAFE_CHARACTER.require_resting then
		if type(IsResting) ~= "function" or type(IsResting()) ~= "boolean" then
			return false, "resting state unavailable"
		end
		if not IsResting() then
			return false, "player is not resting at the approved park spot"
		end
	end
	return true, realm or ""
end

-- A live, unscaled pixel protocol is observable through gamescope while Lua is running. SavedVariables
-- cannot provide live state: they normally flush only at logout/reload. Hide on leaving world so the
-- login screen cannot retain a ready signal. Python reads these bits, never text or OCR.
local inWorld = false
local status = CreateFrame("Frame", nil, UIParent)
status:SetIgnoreParentScale(true)
status:SetFrameStrata("TOOLTIP")
status:SetSize(52, 4)
status:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
local cells = {}
for column = 1, 13 do
	local texture = status:CreateTexture(nil, "OVERLAY")
	texture:SetSize(4, 4)
	texture:SetPoint("TOPLEFT", (column - 1) * 4, 0)
	cells[column] = texture
end
status:SetScript("OnUpdate", function()
	local box = ChatEdit_GetActiveWindow and ChatEdit_GetActiveWindow()
	local dead, combat = safety()
	local bits = {
		false,
		true,
		true,
		true,
		false,
		false,
		true,
		false,
		inWorld,
		_G.GameMenuFrame and _G.GameMenuFrame:IsShown(),
		box and box:HasFocus(),
		dead,
		combat,
	}
	for column = 1, 13 do
		local value = bits[column] and 1 or 0
		cells[column]:SetColorTexture(value, value, value, 1)
	end
end)

-- Each time the world loads, validate the parked character before taking the screenshot that tells Python the world is
-- ready.  An unsafe or unknown state produces no readiness screenshot, so no proof flow or reload can begin.
local frame = CreateFrame("Frame")
frame:RegisterEvent("PLAYER_ENTERING_WORLD")
frame:RegisterEvent("PLAYER_LEAVING_WORLD")
frame:SetScript("OnEvent", function(_, event)
	if event == "PLAYER_LEAVING_WORLD" then
		inWorld = false
		return
	end
	inWorld = true
	C_Timer.After(2, function()
		local safe, reason = safeCharacter()
		if not safe then
			print("FOREVER_HEADLESS_PREFLIGHT_REFUSED", reason)
			return
		end
		local marker = CreateFrame("Frame", nil, UIParent)
		marker:SetIgnoreParentScale(true)
		marker:SetFrameStrata("TOOLTIP")
		marker:SetSize(32, 32)
		marker:SetPoint("CENTER")
		for row, bits in ipairs(MARKER) do
			for column = 1, #bits do
				local texture = marker:CreateTexture(nil, "OVERLAY")
				texture:SetSize(4, 4)
				texture:SetPoint("TOPLEFT", (column - 1) * 4, -(row - 1) * 4)
				texture:SetColorTexture(
					bits:sub(column, column) == "1" and 1 or 0,
					bits:sub(column, column) == "1" and 1 or 0,
					bits:sub(column, column) == "1" and 1 or 0,
					1
				)
			end
		end
		local box = ChatEdit_GetActiveWindow and ChatEdit_GetActiveWindow()
		if box then
			ChatEdit_DeactivateChat(box)
		end
		Screenshot()
		C_Timer.After(0.5, function()
			marker:Hide()
			marker = nil
		end)
	end)
end)
