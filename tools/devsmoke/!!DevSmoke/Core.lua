-- Private dev addon: opens and closes every loaded Forever addon's bare slash surface, then the world map, and
-- keeps a pass or fail line per surface in DevSmokeDB. Nothing here ships to players and nothing here is secure.
local MAX_RUNS = 20
local STEP_DELAY = 0.5

local run

local function record(message)
	if not run or not run.current then
		return
	end
	local result = run.current
	result.errors[#result.errors + 1] = tostring(message)
	result.ok = false
end

local function show(text, red)
	if UIErrorsFrame then
		UIErrorsFrame:AddMessage(text, 1, red, red)
	end
end

local function finish()
	local current = run
	if not current then
		return
	end
	run = nil
	if type(current.previous) == "function" then
		seterrorhandler(current.previous)
	end
	local failed = 0
	for _, result in ipairs(current.entry.results) do
		if not result.ok then
			failed = failed + 1
		end
	end
	local red = failed > 0 and 0.3 or 1
	show(("Dev Smoke: %d surfaces, %d failed"):format(#current.entry.results, failed), red)
end

local function step()
	if not run then
		return
	end
	local action = run.actions[run.next]
	if not action then
		finish()
		return
	end
	run.next = run.next + 1
	run.current = action.result
	local function capture(message)
		record(message)
		record(debugstack())
		return message
	end
	local started = debugprofilestop()
	if action.worldMap then
		xpcall(ToggleWorldMap, capture)
	else
		xpcall(function()
			SlashCmdList[action.key]("", nil)
		end, capture)
	end
	local ms = debugprofilestop() - started
	local result = action.result
	-- The first run of a surface opens it cold; the second runs with whatever the first warmed up. Keep both, and
	-- the slowest of the two as the surface's cost.
	if result.firstMs == nil then
		result.firstMs = ms
	end
	if result.ms == nil or ms > result.ms then
		result.ms = ms
	end
	C_Timer.After(STEP_DELAY, step)
end

-- Ours is any addon depending on ForeverCore, the way every Forever addon declares it in its TOC. A name suffix
-- would also match third-party addons such as NaowhForever, which declare no such dependency.
local function isOurs(name)
	if name == "ForeverCore" then
		return true
	end
	for _, dependency in ipairs({ C_AddOns.GetAddOnDependencies(name) }) do
		if dependency == "ForeverCore" then
			return true
		end
	end
	return false
end

-- Commands a run cannot exercise. Tweaks' /rl calls ReloadUI, which the client allows only from a key press or
-- click, so run from a timer it is always blocked, and blamed on Tweaks; allowed, it would end the run.
local SKIP = { TWEAKSFOREVER_RELOAD = true }

-- Every registered command key. Once the chat box has parsed a slash command, ChatFrameUtil's ImportListToHash
-- moves each SlashCmdList entry into the proxy table behind its __index and wipes the list itself, so the list
-- alone is empty in a running client; a command registered since then is back in the list until the next parse.
local function commandKeys()
	local keys = {}
	local meta = getmetatable(SlashCmdList)
	local proxy = meta and meta.__index
	if type(proxy) == "table" then
		for key in pairs(proxy) do
			keys[key] = true
		end
	end
	for key in pairs(SlashCmdList) do
		keys[key] = true
	end
	return keys
end

-- One slash surface per command the addon wrote, named by its first alias, plus the world map at the end.
local function collect()
	local surfaces = {}
	for index = 1, C_AddOns.GetNumAddOns() do
		local name = C_AddOns.GetAddOnInfo(index)
		if type(name) == "string" and C_AddOns.IsAddOnLoaded(name) and isOurs(name) then
			for key in pairs(commandKeys()) do
				local global = "SLASH_" .. key .. "1"
				local alias = rawget(_G, global)
				if key ~= "DEVSMOKE" and not SKIP[key] and type(alias) == "string" then
					local secure, owner = issecurevariable(global)
					if secure == false and owner == name then
						surfaces[#surfaces + 1] = { key = key, label = name .. " " .. alias, alias = alias }
					end
				end
			end
		end
	end
	table.sort(surfaces, function(a, b)
		return a.label < b.label
	end)
	surfaces[#surfaces + 1] = { label = "world map", worldMap = true }
	return surfaces
end

local function begin()
	if run then
		show("Dev Smoke: a run is already in progress", 0.3)
		return
	end
	DevSmokeDB = DevSmokeDB or {}
	local runs = DevSmokeDB.runs
	if type(runs) ~= "table" then
		runs = {}
		DevSmokeDB.runs = runs
	end
	local entry = { started = time(), build = select(4, GetBuildInfo()), results = {} }
	runs[#runs + 1] = entry
	while #runs > MAX_RUNS do
		table.remove(runs, 1)
	end
	if InCombatLockdown() then
		entry.result = "skipped: in combat"
		show("Dev Smoke: skipped: in combat", 0.3)
		return
	end
	local actions = {}
	for _, surface in ipairs(collect()) do
		local result = { surface = surface.label, ok = true, errors = {} }
		entry.results[#entry.results + 1] = result
		actions[#actions + 1] = { result = result, key = surface.key, worldMap = surface.worldMap }
		actions[#actions + 1] = { result = result, key = surface.key, worldMap = surface.worldMap }
	end
	local previous = geterrorhandler()
	run = { entry = entry, actions = actions, next = 1, current = nil, previous = previous }
	seterrorhandler(function(message, ...)
		record(message)
		if type(previous) == "function" then
			return previous(message, ...)
		end
	end)
	step()
end

SLASH_DEVSMOKE1 = "/devsmoke"
SlashCmdList["DEVSMOKE"] = function()
	begin()
end

-- The Forever addons load after this one, so /forever only exists here once PLAYER_LOGIN has fired.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function()
	local original = SlashCmdList and SlashCmdList["FOREVERLEADERBOARDS"]
	if type(original) ~= "function" then
		return
	end
	SlashCmdList["FOREVERLEADERBOARDS"] = function(message, ...)
		local command = type(message) == "string" and message:match("^%s*(%S+)") or nil
		if command == "selftest" then
			begin()
			return
		end
		return original(message, ...)
	end
end)

-- Taint and warning reports belong to the step that is running when they arrive.
local reports = CreateFrame("Frame")
reports:RegisterEvent("ADDON_ACTION_BLOCKED")
reports:RegisterEvent("ADDON_ACTION_FORBIDDEN")
reports:RegisterEvent("LUA_WARNING")
reports:SetScript("OnEvent", function(_, event, ...)
	if not run then
		return
	end
	-- LUA_WARNING carries (warnType, message); the blocked events carry (addonName, function).
	local parts = { event .. ":" }
	for index = 1, select("#", ...) do
		parts[#parts + 1] = tostring((select(index, ...)))
	end
	record(table.concat(parts, " "))
end)
