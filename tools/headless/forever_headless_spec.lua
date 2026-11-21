-- Lua 5.1 fixtures for the startup handshake. A missing character configuration must never signal readiness.
local source = assert(io.open("tools/headless/!!ForeverHeadless/ForeverHeadless.lua")):read("*a")
-- Every scale the addon set on a frame.
local scales = {}
-- The text the enrolment frame showed, if any.
local shown

local function run(config, name, guid, dead, combat, lockdown, screenshot)
	local events, callback, updates = {}, nil, {}
	-- Every OnUpdate the addon set: the safety strip's and the motion row's.
	local function update()
		for _, fn in ipairs(updates) do
			fn()
		end
	end
	local textures = {}
	_G.CreateFrame = function()
		return {
			RegisterEvent = function(_, event)
				events[#events + 1] = event
			end,
			SetScript = function(_, script, fn)
				if script == "OnUpdate" then
					updates[#updates + 1] = fn
				else
					callback = fn
				end
			end,
			SetSize = function(frame, width)
				frame.width = width
			end,
			SetPoint = function() end,
			SetIgnoreParentScale = function() end,
			SetScale = function(frame, scale)
				scales[#scales + 1] = scale
				-- The readiness marker is the one 32-unit-wide frame, the safety strip the one 52 wide.
				if frame.width == 32 then
					scales.marker = scale
				elseif frame.width == 52 then
					scales.status = scale
				end
			end,
			SetFrameStrata = function() end,
			SetAllPoints = function() end,
			Hide = function() end,
			CreateFontString = function()
				return {
					SetPoint = function() end,
					SetText = function(_, text)
						shown = text
					end,
				}
			end,
			CreateTexture = function()
				local cell = {}
				textures[#textures + 1] = cell
				return {
					SetAllPoints = function() end,
					SetColorTexture = function(_, value)
						cell.value = value
					end,
					SetSize = function() end,
					SetPoint = function() end,
				}
			end,
		}
	end
	_G.C_Timer = {
		After = function(_, fn)
			fn()
		end,
	}
	_G.UnitName = function()
		return name, "Realm"
	end
	_G.UnitGUID = function()
		return guid
	end
	_G.UnitIsDeadOrGhost = function()
		return dead
	end
	_G.UnitAffectingCombat = function()
		return combat
	end
	_G.InCombatLockdown = function()
		return lockdown
	end
	_G.FOREVER_HEADLESS_CHARACTER = config
	_G.ChatEdit_GetActiveWindow = function()
		return nil
	end
	_G.Screenshot = function()
		screenshot.count = screenshot.count + 1
	end
	_G.print = function() end
	-- The player's own windowed size, which the readiness marker must still draw at 4 pixels a cell.
	_G.GetPhysicalScreenSize = function()
		return 1432, 600
	end
	scales = {}
	assert(loadstring(source))()
	local registered = {}
	for _, event in ipairs(events) do
		registered[event] = true
	end
	assert(registered.PLAYER_ENTERING_WORLD, "registers world readiness")
	callback(nil, "PLAYER_ENTERING_WORLD")
	_G.GameMenuFrame = {
		IsShown = function()
			return true
		end,
	}
	_G.ChatEdit_GetActiveWindow = function()
		return {
			HasFocus = function()
				return true
			end,
		}
	end
	update()
	assert(
		textures[9].value == 1 and textures[10].value == 1 and textures[11].value == 1,
		"live protocol reports world, menu and chat focus"
	)
	assert(textures[1].value == 0 and textures[2].value == 1, "version 2 header")
	assert(textures[12].value == (dead ~= false and 1 or 0), "live dead or ghost cell fails closed")
	assert(textures[13].value == ((combat ~= false or lockdown ~= false) and 1 or 0), "live combat cell fails closed")
	local previousCombat, previousLockdown = combat, lockdown
	combat = true
	update()
	assert(textures[13].value == 1, "combat updates without world entry")
	combat, lockdown = false, true
	update()
	assert(textures[13].value == 1, "lockdown updates without world entry")
	combat, lockdown = false, false
	update()
	assert(textures[13].value == 0, "safe combat state clears the live cell")
	combat, lockdown = previousCombat, previousLockdown
	-- A resident character can become unsafe after entry, without another world event.
	_G.UnitIsDeadOrGhost = function()
		return true
	end
	update()
	assert(textures[12].value == 1, "live death or ghost updates without world entry")
	_G.UnitIsDeadOrGhost = nil
	_G.InCombatLockdown = nil
	update()
	assert(textures[12].value == 1 and textures[13].value == 1, "missing APIs fail closed")
	callback(nil, "PLAYER_LEAVING_WORLD")
	update()
	assert(textures[9].value == 0, "logout clears live world bit")
end

local screenshot = { count = 0 }
run(nil, "Tester", "Player-1-2-3", false, false, false, screenshot)
assert(screenshot.count == 0, "missing parked-character configuration refuses readiness")
run({ name = "Tester", guid = "Player-1-2-3" }, "Tester", "Player-1-2-3", false, false, false, screenshot)
assert(screenshot.count == 1, "approved character signals readiness")
assert(scales.marker == 768 / 600, "the readiness marker is scaled to exactly 4 screen pixels a cell")
assert(scales.status == 768 / 600, "the safety strip is scaled to exactly 4 screen pixels a cell")
run({ name = "Other", guid = "Player-1-2-3" }, "Tester", "Player-1-2-3", false, false, false, screenshot)
assert(screenshot.count == 1, "unexpected identity refuses readiness")
run({ name = "Tester", guid = "Player-1-2-3" }, "Tester", "Player-1-2-3", true, false, false, screenshot)
assert(screenshot.count == 2, "a ghost out of combat signals readiness, so it can be revived")
run({ name = "Tester", guid = "Player-1-2-3" }, "Tester", "Player-1-2-3", nil, false, false, screenshot)
assert(screenshot.count == 2, "an unreadable dead state refuses readiness")
run({ name = "Tester", guid = "Player-1-2-3" }, "Tester", "Player-1-2-3", true, true, false, screenshot)
assert(screenshot.count == 2, "a ghost in combat refuses readiness")
run({ name = "Tester", guid = "Player-1-2-3" }, "Tester", "Player-1-2-3", false, true, false, screenshot)
assert(screenshot.count == 2, "combat character refuses readiness")
run({ name = "Tester", guid = "Player-1-2-3" }, "Tester", "Player-1-2-3", false, false, true, screenshot)
assert(screenshot.count == 2, "lockdown character refuses readiness")
run({ name = "Tester", guid = "PENDING" }, "Tester", "Player-1-2-3", false, false, false, screenshot)
assert(screenshot.count == 2 and shown == "Player-1-2-3", "enrolment shows the GUID and refuses readiness")
shown = nil
run({ name = "Other", guid = "PENDING" }, "Tester", "Player-1-2-3", false, false, false, screenshot)
assert(screenshot.count == 2 and shown == nil, "enrolment never shows another character's GUID")
print("forever headless: identity handshake pass")

run(nil, "Tester", "Player-1-2-3", nil, nil, nil, screenshot)
run(nil, "Tester", "Player-1-2-3", false, nil, false, screenshot)
run(nil, "Tester", "Player-1-2-3", false, false, nil, screenshot)

-- The motion row under the safety strip: map, position, facing, map size, indoors and the target's nameplate, each
-- 16 bits after an 8-cell header and four flags, then an 8-bit checksum, as forever_client decodes it.
do
	local textures, updates = {}, {}
	_G.CreateFrame = function()
		return {
			RegisterEvent = function() end,
			SetScript = function(_, script, fn)
				if script == "OnUpdate" then
					updates[#updates + 1] = fn
				end
			end,
			SetSize = function() end,
			SetPoint = function() end,
			SetIgnoreParentScale = function() end,
			SetScale = function(_, scale)
				scales[#scales + 1] = scale
			end,
			SetFrameStrata = function() end,
			CreateTexture = function()
				local cell = {}
				textures[#textures + 1] = cell
				return {
					SetColorTexture = function(_, value)
						cell.value = value
					end,
					SetSize = function() end,
					SetPoint = function() end,
				}
			end,
		}
	end
	local function Vector(x, y)
		return {
			GetXY = function()
				return x, y
			end,
		}
	end
	_G.CreateVector2D = Vector
	_G.C_DeathInfo = {
		GetCorpseMapPosition = function(map)
			return map == 1453 and Vector(0.5, 0.25) or nil
		end,
	}
	_G.C_Map = {
		GetBestMapForUnit = function()
			return 1453
		end,
		GetPlayerMapPosition = function()
			return Vector(0.652, 0.714)
		end,
		-- A map 1000 yards across and 600 down, its world axes swapped as the client's are.
		GetWorldPosFromMapPos = function(_, at)
			local x, y = at:GetXY()
			return 0, Vector(-y * 600, -x * 1000)
		end,
	}
	_G.GetPlayerFacing = function()
		return math.pi / 2
	end
	_G.IsIndoors = function()
		return true
	end
	_G.UIParent = {
		GetWidth = function()
			return 1000
		end,
		GetEffectiveScale = function()
			return 1
		end,
	}
	_G.C_NamePlate = {
		GetNamePlateForUnit = function()
			return {
				IsVisible = function()
					return true
				end,
				GetCenter = function()
					return 250
				end,
				GetEffectiveScale = function()
					return 1
				end,
			}
		end,
	}
	_G.UnitExists = function()
		return true
	end
	local bound = { MOVEFORWARD = { "S" }, MOVEBACKWARD = { "DOWN" }, TURNLEFT = { "LEFT" }, JUMP = { "SPACE" } }
	_G.GetBindingKey = function(action)
		return unpack(bound[action] or {})
	end
	_G.CheckInteractDistance = function()
		return true
	end
	_G.GetPhysicalScreenSize = function()
		return 1920, 804
	end
	scales = {}
	assert(loadstring(source))()
	assert(scales[1] == 768 / 804, "the motion row is scaled to exactly 4 screen pixels a cell")
	for _, fn in ipairs(updates) do
		fn()
	end
	local row = {}
	for index = 14, #textures do
		row[#row + 1] = textures[index].value == 1
	end
	local at = 1
	local function read(bits)
		local value = 0
		for _ = 1, bits do
			value = value * 2 + (row[at] and 1 or 0)
			at = at + 1
		end
		return value
	end
	assert(read(8) == 155, "the motion header 10011011")
	local flags = { read(1), read(1), read(1), read(1), read(1) }
	assert(flags[1] == 1 and flags[2] == 1 and flags[3] == 1 and flags[4] == 1, "known, indoors, plate, near")
	assert(flags[5] == 1, "a corpse on this map")
	local fields = {}
	for index = 1, 10 do
		fields[index] = read(16)
	end
	assert(fields[1] == 1453, "the map")
	assert(fields[2] == math.floor(0.652 * 65535 + 0.5) and fields[3] == math.floor(0.714 * 65535 + 0.5), "x, y")
	assert(fields[4] == math.floor(65535 / 4 + 0.5), "facing a quarter turn")
	assert(fields[5] == 1000 and fields[6] == 600, "the map's size in yards")
	assert(fields[7] == math.floor(0.25 * 65535 + 0.5), "the target's plate a quarter across the screen")
	-- forever_client hashes "MOVEFORWARD=S,;MOVEBACKWARD=DOWN,;..." the same way; tools/test_forever_client.py
	-- checks the same string gives the same number.
	assert(fields[8] == 30719, "the movement bindings hash")
	assert(fields[9] == math.floor(0.5 * 65535 + 0.5) and fields[10] == math.floor(0.25 * 65535 + 0.5), "the corpse")
	local sum = 1 + 2 + 3 + 4 + 5
	for _, value in ipairs(fields) do
		sum = sum + value
	end
	assert(read(8) == sum % 256, "the checksum")
	assert(at == #row + 1, "nothing after the checksum")
	print("forever headless: motion row pass")
end
