-- Dev addon for tools/headless/forever_client.py. The launcher links this folder into AddOns only for its own session
-- and removes it on stop, so a player's login never loads it.
-- Config.lua is generated into an isolated session copy before the client starts. A missing config refuses readiness.
local SAFE_CHARACTER = _G.FOREVER_HEADLESS_CHARACTER
local UnitGUID = _G.UnitGUID
local UnitAffectingCombat = _G.UnitAffectingCombat
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
		return false, "no approved character configured"
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
	if combat then
		return false, "player is in combat"
	end
	-- A ghost out of combat still signals readiness, so a session can start for it and revive it with forever_client's
	-- dead-allowed verbs; the live strip carries the dead bit and every other verb refuses it (forever-core#1009).
	-- An unreadable dead state still refuses.
	local isDead = _G.UnitIsDeadOrGhost
	if dead and (type(isDead) ~= "function" or isDead("player") ~= true) then
		return false, "dead state unavailable"
	end
	return true, realm or ""
end

-- A live pixel protocol is observable through gamescope while Lua is running. SavedVariables
-- cannot provide live state: they normally flush only at logout/reload. Hide on leaving world so the
-- login screen cannot retain a ready signal. Python reads these bits, never text or OCR.
--
-- Every pixel-protocol frame draws exactly 4 screen pixels a cell, whatever the screen's height: an unscaled frame is
-- 768 units tall, so its scale is 768 over the physical height. In UI units the cells would be 4 * height / 768
-- pixels, which forever_client reads only on a screen near 768 tall, so the player's window size would decide
-- whether a session works.
local function pixelExact(frame)
	if type(_G.GetPhysicalScreenSize) ~= "function" then
		return
	end
	local _, height = _G.GetPhysicalScreenSize()
	if type(height) == "number" and height > 0 then
		frame:SetScale(768 / height)
	end
end

local inWorld = false
local status = CreateFrame("Frame", nil, UIParent)
status:SetIgnoreParentScale(true)
status:SetFrameStrata("TOOLTIP")
status:SetSize(52, 4)
status:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
pixelExact(status)
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

-- A second row under the safety strip carries where the player stands, for forever_client's `face` and `walkto`: map,
-- position, facing, the map's size in yards, whether the player is indoors and where the target's nameplate is on
-- screen. Each value is 16 bits, one 4-pixel cell per bit like the row above, closed by a checksum, so a torn or
-- missing frame decodes as nothing rather than as a wrong position (forever-core#820).
local MOTION_HEADER = { true, false, false, true, true, false, true, true }
-- map, x, y, facing, map width, map height, target plate x, movement bindings hash, corpse x, corpse y
local FIELDS = 10
local FLAGS = 5 -- position known, indoors, target plate shown, target within interact distance, corpse on this map
local motion = CreateFrame("Frame", nil, UIParent)
motion:SetIgnoreParentScale(true)
motion:SetFrameStrata("TOOLTIP")
local MOTION_CELLS = #MOTION_HEADER + FLAGS + FIELDS * 16 + 8
motion:SetSize(MOTION_CELLS * 4, 4)
motion:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, -4)
pixelExact(motion)
local resized = CreateFrame("Frame")
resized:RegisterEvent("DISPLAY_SIZE_CHANGED")
resized:RegisterEvent("UI_SCALE_CHANGED")
resized:SetScript("OnEvent", function()
	pixelExact(status)
	pixelExact(motion)
end)
local motionCells = {}
for column = 1, MOTION_CELLS do
	local texture = motion:CreateTexture(nil, "OVERLAY")
	texture:SetSize(4, 4)
	texture:SetPoint("TOPLEFT", (column - 1) * 4, 0)
	motionCells[column] = texture
end

-- A 16-bit hash of the keys bound to the actions forever_client presses, recomputed when the bindings change, so the
-- tool can tell whether the bindings it resolved still match this client (the same string and sum it builds).
local BOUND_ACTIONS = {
	"MOVEFORWARD",
	"MOVEBACKWARD",
	"TURNLEFT",
	"TURNRIGHT",
	"STRAFELEFT",
	"STRAFERIGHT",
	"JUMP",
	"INTERACTTARGET",
	"TARGETNEARESTENEMY",
}
local bindingsHash = 0
local function hashBindings()
	if type(_G.GetBindingKey) ~= "function" then
		bindingsHash = 0
		return
	end
	local parts = {}
	for _, action in ipairs(BOUND_ACTIONS) do
		local first, second = _G.GetBindingKey(action)
		parts[#parts + 1] = action .. "=" .. (first or "") .. "," .. (second or "") .. ";"
	end
	local text, sum = table.concat(parts), 0
	for index = 1, #text do
		sum = (sum + text:byte(index) * index) % 65536
	end
	bindingsHash = sum
end
hashBindings()
local bindingsChanged = CreateFrame("Frame")
bindingsChanged:RegisterEvent("PLAYER_LOGIN")
bindingsChanged:RegisterEvent("UPDATE_BINDINGS")
bindingsChanged:SetScript("OnEvent", hashBindings)

local sizes = {}
-- The map's width and height in yards, from the world positions of its corners; nil where the client gives none.
local function mapSize(map)
	if sizes[map] == nil then
		sizes[map] = false
		local world = _G.C_Map and _G.C_Map.GetWorldPosFromMapPos
		if type(world) == "function" and type(_G.CreateVector2D) == "function" then
			local _, origin = world(map, CreateVector2D(0, 0))
			local _, across = world(map, CreateVector2D(1, 0))
			local _, down = world(map, CreateVector2D(0, 1))
			if origin and across and down then
				local function span(a, b)
					local ax, ay = a:GetXY()
					local bx, by = b:GetXY()
					return math.sqrt((ax - bx) ^ 2 + (ay - by) ^ 2)
				end
				sizes[map] = { span(origin, across), span(origin, down) }
			end
		end
	end
	return sizes[map] or nil
end

local function word(value)
	return math.max(0, math.min(65535, math.floor(value + 0.5)))
end

-- The player's motion state as flags and 16-bit fields; zeros with the first flag off when the position is unknown.
local function motionState()
	local flags, fields = { false, false, false, false, false }, { 0, 0, 0, 0, 0, 0, 0, bindingsHash, 0, 0 }
	local map = _G.C_Map and _G.C_Map.GetBestMapForUnit and _G.C_Map.GetBestMapForUnit("player")
	local position = map and _G.C_Map.GetPlayerMapPosition and _G.C_Map.GetPlayerMapPosition(map, "player")
	local facing = _G.GetPlayerFacing and _G.GetPlayerFacing()
	if position and facing then
		local x, y = position:GetXY()
		local size = mapSize(map)
		flags[1] = true
		fields[1], fields[2], fields[3] = word(map), word(x * 65535), word(y * 65535)
		fields[4] = word(facing / (2 * math.pi) * 65535)
		if size then
			fields[5], fields[6] = word(size[1]), word(size[2])
		end
		-- A ghost's corpse on the same map, for `walkto corpse` (forever-core#1009).
		local corpseAt = _G.C_DeathInfo and _G.C_DeathInfo.GetCorpseMapPosition
		local corpse = type(corpseAt) == "function" and corpseAt(map)
		if corpse then
			local cx, cy = corpse:GetXY()
			flags[5] = true
			fields[9], fields[10] = word(cx * 65535), word(cy * 65535)
		end
	end
	flags[2] = _G.IsIndoors and _G.IsIndoors() and true or false
	local plate = _G.C_NamePlate and _G.C_NamePlate.GetNamePlateForUnit and _G.C_NamePlate.GetNamePlateForUnit("target")
	if plate and plate:IsVisible() then
		local x = plate:GetCenter()
		local width = UIParent:GetWidth()
		if x and width and width > 0 then
			flags[3] = true
			fields[7] = word(x * plate:GetEffectiveScale() / (width * UIParent:GetEffectiveScale()) * 65535)
		end
	end
	if _G.UnitExists and _G.UnitExists("target") and type(_G.CheckInteractDistance) == "function" then
		local ok, near = pcall(_G.CheckInteractDistance, "target", 3)
		flags[4] = ok and near and true or false
	end
	return flags, fields
end

local function paintMotion()
	local flags, fields = motionState()
	local bits = {}
	for _, bit in ipairs(MOTION_HEADER) do
		bits[#bits + 1] = bit
	end
	local sum = 0
	for index, flag in ipairs(flags) do
		bits[#bits + 1] = flag
		sum = sum + (flag and index or 0)
	end
	for _, value in ipairs(fields) do
		sum = sum + value
		for shift = 15, 0, -1 do
			bits[#bits + 1] = math.floor(value / 2 ^ shift) % 2 == 1
		end
	end
	sum = sum % 256
	for shift = 7, 0, -1 do
		bits[#bits + 1] = math.floor(sum / 2 ^ shift) % 2 == 1
	end
	for column = 1, MOTION_CELLS do
		local value = bits[column] and 1 or 0
		motionCells[column]:SetColorTexture(value, value, value, 1)
	end
end
motion:SetScript("OnUpdate", paintMotion)

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
		pixelExact(marker)
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
