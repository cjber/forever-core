-- Lua 5.1 fixtures for the startup handshake. A missing character configuration must never signal readiness.
local source = assert(io.open("tools/headless/!!ForeverHeadless/ForeverHeadless.lua")):read("*a")

local function run(config, name, guid, dead, combat, lockdown, screenshot)
	local events, callback, update = {}, nil, nil
	local textures = {}
	_G.CreateFrame = function()
		return {
			RegisterEvent = function(_, event)
				events[#events + 1] = event
			end,
			SetScript = function(_, script, fn)
				if script == "OnUpdate" then
					update = fn
				else
					callback = fn
				end
			end,
			SetSize = function() end,
			SetPoint = function() end,
			SetIgnoreParentScale = function() end,
			SetFrameStrata = function() end,
			Hide = function() end,
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
	assert(loadstring(source))()
	assert(events[1] == "PLAYER_ENTERING_WORLD", "registers world readiness")
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
run({ name = "Other", guid = "Player-1-2-3" }, "Tester", "Player-1-2-3", false, false, false, screenshot)
assert(screenshot.count == 1, "unexpected identity refuses readiness")
run({ name = "Tester", guid = "Player-1-2-3" }, "Tester", "Player-1-2-3", true, false, false, screenshot)
assert(screenshot.count == 1, "dead character refuses readiness")
run({ name = "Tester", guid = "Player-1-2-3" }, "Tester", "Player-1-2-3", false, true, false, screenshot)
assert(screenshot.count == 1, "combat character refuses readiness")
run({ name = "Tester", guid = "Player-1-2-3" }, "Tester", "Player-1-2-3", false, false, true, screenshot)
assert(screenshot.count == 1, "lockdown character refuses readiness")
print("forever headless: identity handshake pass")

run(nil, "Tester", "Player-1-2-3", nil, nil, nil, screenshot)
run(nil, "Tester", "Player-1-2-3", false, nil, false, screenshot)
run(nil, "Tester", "Player-1-2-3", false, false, nil, screenshot)
