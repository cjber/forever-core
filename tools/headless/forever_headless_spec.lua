-- Lua 5.1 fixtures for the startup handshake. A missing parked-character configuration must never signal readiness.
local source = assert(io.open("tools/headless/!!ForeverHeadless/ForeverHeadless.lua")):read("*a")

local function run(config, name, guid, resting, dead, combat, lockdown, screenshot)
	local events, callback = {}, nil
	_G.CreateFrame = function()
		return {
			RegisterEvent = function(_, event)
				events[#events + 1] = event
			end,
			SetScript = function(_, _, fn)
				callback = fn
			end,
			SetSize = function() end,
			SetPoint = function() end,
			SetIgnoreParentScale = function() end,
			SetFrameStrata = function() end,
			Hide = function() end,
			CreateTexture = function()
				return {
					SetAllPoints = function() end,
					SetColorTexture = function() end,
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
	_G.IsResting = function()
		return resting
	end
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
end

local screenshot = { count = 0 }
run(nil, "Tester", "Player-1-2-3", true, false, false, false, screenshot)
assert(screenshot.count == 0, "missing parked-character configuration refuses readiness")
run(
	{ name = "Tester", guid = "Player-1-2-3", require_resting = true },
	"Tester",
	"Player-1-2-3",
	true,
	false,
	false,
	false,
	screenshot
)
assert(screenshot.count == 1, "approved resting character signals readiness")
run(
	{ name = "Other", guid = "Player-1-2-3", require_resting = true },
	"Tester",
	"Player-1-2-3",
	true,
	false,
	false,
	false,
	screenshot
)
assert(screenshot.count == 1, "unexpected identity refuses readiness")
run(
	{ name = "Tester", guid = "Player-1-2-3", require_resting = true },
	"Tester",
	"Player-1-2-3",
	false,
	false,
	false,
	false,
	screenshot
)
assert(screenshot.count == 1, "unresting character refuses readiness")
run(
	{ name = "Tester", guid = "Player-1-2-3", require_resting = true },
	"Tester",
	"Player-1-2-3",
	true,
	true,
	false,
	false,
	screenshot
)
assert(screenshot.count == 1, "dead character refuses readiness")
run(
	{ name = "Tester", guid = "Player-1-2-3", require_resting = true },
	"Tester",
	"Player-1-2-3",
	true,
	false,
	true,
	false,
	screenshot
)
assert(screenshot.count == 1, "combat character refuses readiness")
run(
	{ name = "Tester", guid = "Player-1-2-3", require_resting = true },
	"Tester",
	"Player-1-2-3",
	true,
	false,
	false,
	true,
	screenshot
)
assert(screenshot.count == 1, "lockdown character refuses readiness")
print("forever headless: identity and resting handshake pass")
