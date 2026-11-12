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

-- The Agent chat tab: its own window, held in the client's chat dock, so an agent reads the commands' answers there
-- and General stays clean. A line is kept under 255 characters because that is where the chat box cuts one.
local MAX_CHAT_WINDOWS = NUM_CHAT_WINDOWS or 10
local MAX_LINE = 254
local COOKING_SKILL_LINE = 185

local function trim(text)
	return type(text) == "string" and text:match("^%s*(.-)%s*$") or ""
end

local function chatFrame(name)
	for index = 1, MAX_CHAT_WINDOWS do
		if GetChatWindowInfo(index) == name then
			return _G["ChatFrame" .. index]
		end
	end
end

local function agentFrame()
	local frame = chatFrame("Agent")
	if frame then
		return frame
	end
	if type(FCF_OpenNewWindow) == "function" then
		local opened = FCF_OpenNewWindow("Agent", true)
		if type(opened) == "table" then
			return opened
		end
	end
	return chatFrame("Agent")
end

local function say(text)
	local line = tostring(text)
	if #line > MAX_LINE then
		line = line:sub(1, MAX_LINE)
	end
	local frame = agentFrame()
	if frame and type(frame.AddMessage) == "function" then
		frame:AddMessage(line, 1, 1, 1)
	end
end

local function selectChat(name)
	local frame = name == "Agent" and agentFrame() or chatFrame(name)
	if not frame then
		say(("Dev Smoke: no %s chat tab"):format(name))
		return
	end
	if type(FCF_SelectDockFrame) == "function" then
		FCF_SelectDockFrame(frame)
	end
	say(("Dev Smoke: %s tab selected"):format(name))
end

local function sayTab(argument)
	if trim(argument) == "off" then
		selectChat("General")
	else
		selectChat("Agent")
	end
end

local function versionOf(name)
	local ok, version = pcall(C_AddOns.GetAddOnMetadata, name, "Version")
	if ok and type(version) == "string" and version ~= "" then
		return version
	end
	return "unknown"
end

local function loadedState(name)
	if C_AddOns.IsAddOnLoaded(name) then
		return "loaded"
	end
	return "not loaded"
end

local function sayVersion(name)
	say(("%s | version %s | %s"):format(name, versionOf(name), loadedState(name)))
end

-- One line per loaded addon depending on ForeverCore, the way a selftest finds them, plus ForeverCore itself and
-- LibAHTab, the Auction House tab library Tweaks Forever ships for Auctionator. Both of those are listed even when
-- the client has not loaded them.
local function sayVersions()
	local dependants = {}
	for index = 1, C_AddOns.GetNumAddOns() do
		local name = C_AddOns.GetAddOnInfo(index)
		if type(name) == "string" and name ~= "ForeverCore" and C_AddOns.IsAddOnLoaded(name) and isOurs(name) then
			dependants[#dependants + 1] = name
		end
	end
	table.sort(dependants)
	say("Dev Smoke: addons")
	sayVersion("ForeverCore")
	sayVersion("LibAHTab")
	for _, name in ipairs(dependants) do
		sayVersion(name)
	end
end

-- This session's BugGrabber entries, skipping only the error a chat /run line itself raises, whose message starts with
-- [string ". An addon error triggered from a /run line names the same chunk in its stack and is still counted.
-- BugGrabber keeps every caught error and stamps each with the session it was last raised in.
local function sayErrors()
	local grabber = BugGrabber
	if type(grabber) ~= "table" or type(grabber.GetDB) ~= "function" then
		say("Dev Smoke: BugGrabber is not loaded")
		return
	end
	local ok, db = pcall(grabber.GetDB, grabber)
	local session
	if type(grabber.GetSessionId) == "function" then
		local sessionOk, id = pcall(grabber.GetSessionId, grabber)
		if sessionOk then
			session = id
		end
	end
	local kept = {}
	if ok and type(db) == "table" then
		for _, entry in ipairs(db) do
			if type(entry) == "table" and (session == nil or entry.session == session) then
				local message = tostring(entry.message or "")
				if message:sub(1, 9) ~= '[string "' then
					kept[#kept + 1] = message
				end
			end
		end
	end
	say(("Dev Smoke: %d errors this session"):format(#kept))
	for index, message in ipairs(kept) do
		say(("%d: %s"):format(index, message:sub(1, 180)))
	end
end

-- Every addon title the Thanks page knows, from the rows its two lists carry.
local function creditTitles(page)
	local titles = {}
	for _, list in ipairs({ page.Players, page.Inspired }) do
		if type(list) == "function" then
			local ok, rows = pcall(list)
			if ok and type(rows) == "table" then
				for _, row in ipairs(rows) do
					for _, helped in ipairs(row.helped or {}) do
						if type(helped.addon) == "string" then
							titles[helped.addon] = true
						end
					end
				end
			end
		end
	end
	return titles
end

-- The addon title is every word but the optional player, matched against the titles the page knows, so a title with
-- spaces comes through whole.
local function splitCredit(text, titles)
	local words = {}
	for word in text:gmatch("%S+") do
		words[#words + 1] = word
	end
	for last = #words, 1, -1 do
		local title = table.concat(words, " ", 1, last)
		if titles[title] then
			return title, last == #words - 1 and words[#words] or nil
		end
	end
	return text, nil
end

local function sayThanks(argument)
	local page = ForeverCore and ForeverCore.Credits
	if type(page) ~= "table" or type(page.Open) ~= "function" then
		say("Dev Smoke: the Thanks page is not loaded")
		return
	end
	local text = trim(argument)
	if text == "" then
		say("Dev Smoke: usage /devsmoke thanks <addon title> [player]")
		return
	end
	local title, player = splitCredit(text, creditTitles(page))
	if not page.Open(title) then
		say(("Dev Smoke: could not open the Thanks page for %s"):format(title))
		return
	end
	if not player then
		say(("Dev Smoke: Thanks opened for %s"):format(title))
		return
	end
	local window = page.window
	local content = window and window.contents
	if type(content) ~= "table" or type(content.GetTop) ~= "function" or type(content.GetParent) ~= "function" then
		say("Dev Smoke: the Thanks page has no scrollable list")
		return
	end
	for _, item in ipairs(window.rows or {}) do
		if item.row and item.row.name == player and item.holder and item.holder:IsShown() then
			local offset = content:GetTop() - item.holder:GetTop()
			local scroll = content:GetParent()
			local bar = scroll.ScrollBar
			local range = type(scroll.GetVerticalScrollRange) == "function" and scroll:GetVerticalScrollRange()
			-- The client's ScrollFrameTemplate drives a percentage scroll bar, which moves the list and its thumb.
			if bar and type(bar.SetScrollPercentage) == "function" and type(range) == "number" and range > 0 then
				bar:SetScrollPercentage(offset / range, true)
			elseif type(scroll.SetVerticalScroll) == "function" then
				scroll:SetVerticalScroll(offset)
			end
			say(("Dev Smoke: Thanks at %s"):format(player))
			return
		end
	end
	say(("Dev Smoke: no credit row for %s"):format(player))
end

-- A profession tab needs its window open, and Cooking opens with no profession known, so it is the one the command
-- uses when nothing is open.
local function sayProf(argument)
	local tab = trim(argument)
	if tab == "" then
		say("Dev Smoke: usage /devsmoke prof <tab>")
		return
	end
	local page = ForeverCore and ForeverCore.ProfessionTabs
	if type(page) ~= "table" or type(page.Select) ~= "function" then
		say("Dev Smoke: the profession tabs are not loaded")
		return
	end
	local window = ProfessionsFrame
	if not (window and window:IsShown()) then
		local tradeSkill = C_TradeSkillUI
		if type(tradeSkill) ~= "table" or type(tradeSkill.OpenTradeSkill) ~= "function" then
			say("Dev Smoke: cannot open the Cooking window")
			return
		end
		tradeSkill.OpenTradeSkill(COOKING_SKILL_LINE)
	end
	page.Select(tab)
	say(("Dev Smoke: profession tab %s"):format(tab))
end

-- Hide every window an agent leaves open, through the client's own panel manager where it has one, so Escape is
-- never pressed and the game menu never opens.
local function sayClose()
	local closed = 0
	local function hide(frame)
		if type(frame) ~= "table" or type(frame.IsShown) ~= "function" or not frame:IsShown() then
			return
		end
		frame:Hide()
		closed = closed + 1
	end
	local function hidePanel(frame)
		if type(frame) ~= "table" or type(frame.IsShown) ~= "function" or not frame:IsShown() then
			return
		end
		if type(HideUIPanel) == "function" then
			HideUIPanel(frame)
		else
			frame:Hide()
		end
		closed = closed + 1
	end
	local page = ForeverCore and ForeverCore.Credits
	hide(page and page.window)
	hidePanel(ProfessionsFrame)
	hidePanel(WorldMapFrame)
	local settings = SettingsPanel
	if type(settings) == "table" and type(settings.IsShown) == "function" and settings:IsShown() then
		if type(settings.Close) == "function" then
			settings:Close()
		else
			settings:Hide()
		end
		closed = closed + 1
	end
	say(("Dev Smoke: closed %d windows"):format(closed))
end

local COMMANDS = {
	tab = sayTab,
	versions = sayVersions,
	errors = sayErrors,
	thanks = sayThanks,
	prof = sayProf,
	close = sayClose,
}

local USAGE = "Dev Smoke: /devsmoke, tab [off], versions, errors, thanks <addon> [player], prof <tab>, close"

SLASH_DEVSMOKE1 = "/devsmoke"
SlashCmdList["DEVSMOKE"] = function(message)
	local command, rest = trim(message):match("^(%S*)%s*(.-)$")
	if command == "" then
		begin()
		return
	end
	local handler = COMMANDS[command]
	if handler then
		handler(rest)
		return
	end
	say(("Dev Smoke: unknown command %s"):format(command))
	say(USAGE)
end

-- The Forever addons load after this one, so core's command only exists here once PLAYER_LOGIN has fired.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function()
	local original = SlashCmdList and SlashCmdList["FOREVERCORE"]
	if type(original) ~= "function" then
		return
	end
	SlashCmdList["FOREVERCORE"] = function(message, ...)
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
