local addonName, ns = ...
local function safe(name, ...)
	local ok, value = pcall(C_AddOns and C_AddOns[name], ...)
	return ok and value or nil
end
local function title(index, fallback)
	local text = safe("GetAddOnMetadata", index, "Title")
	return type(text) == "string" and (text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")) or fallback
end
local function outdated(tag, mine)
	local a, b, c
	if type(tag) == "string" then
		a, b, c = tag:match("^v(%d+)%.(%d+)%.(%d+)$")
	end
	if not a then
		return true
	end
	a, b, c = tonumber(a), tonumber(b), tonumber(c)
	return a < mine[1] or a == mine[1] and (b < mine[2] or b == mine[2] and c < mine[3])
end
-- The client keys per-character enable state by GUID and ignores a character name, answering 2 for every addon
-- (cjber/shortest-path-forever#996); with no character it gives the all-characters state, which reads 1 when an addon
-- is off for this character alone.
local function enabled(index)
	local state = safe("GetAddOnEnableState", index, _G.UnitGUID and _G.UnitGUID("player"))
	return safe("IsAddOnLoaded", index) or (type(state) == "number" and state > 0)
end
-- The index of an installed folder named ForeverCore, false when no such folder is installed at all, and nil when
-- the client will not say. A disabled addon is still installed, which is a different problem from having none.
local function installed()
	local total = safe("GetNumAddOns")
	if type(total) ~= "number" then
		return nil
	end
	for index = 1, total do
		local name = safe("GetAddOnInfo", index)
		if type(name) == "string" and name:lower() == "forevercore" then
			return index
		end
	end
	return false
end
-- Whether `getter` names ForeverCore among an addon's dependencies.
local function declares(getter, index)
	local result = { pcall(getter, index) }
	for position = 2, result[1] and #result or 0 do
		local dependency = result[position]
		if type(dependency) == "string" and dependency:lower() == "forevercore" then
			return true
		end
	end
end
-- A loaded addon naming ForeverCore in either dependency list: consumers moved it to `## OptionalDeps` so they load
-- and can say what is missing, and an older release still names it in `## Dependencies`.
local function candidate(index)
	if not enabled(index) then
		return false
	end
	return declares(C_AddOns and C_AddOns.GetAddOnDependencies, index)
		or declares(C_AddOns and C_AddOns.GetAddOnOptionalDependencies, index)
end
local function culprits()
	local own = safe("GetAddOnMetadata", addonName, "X-Forever-Core")
	local a, b, c
	if type(own) == "string" then
		a, b, c = own:match("^v(%d+)%.(%d+)%.(%d+)$")
	end
	local total = safe("GetNumAddOns")
	if not a or type(total) ~= "number" then
		return {}
	end
	local mine = { tonumber(a), tonumber(b), tonumber(c) }
	local found = {}
	for index = 1, total do
		local name = safe("GetAddOnInfo", index)
		local lower = type(name) == "string" and name:lower()
		local skip = lower == addonName:lower() or lower == "forevercore"
		local tag = safe("GetAddOnMetadata", index, "X-Forever-Core")
		if lower and not skip and candidate(index) and outdated(tag, mine) then
			found[#found + 1] = title(index, name)
		end
	end
	return found
end
local function phrase(key, ...)
	local text = (ns.L or {})[key]
	return string.format(type(text) == "string" and text or key, ...)
end
-- Our ForeverCore's identity, from its TOC. Another addon can install a folder named ForeverCore, so the project ID
-- it publishes is what tells our shared code from someone else's: nothing about a title or a version is compared.
local CORE_PROJECT = "1796337"
local CORE_WEBSITE = "https://github.com/cjber/forever-core"
local function trimmed(value)
	return type(value) == "string" and value:match("^%s*(.-)%s*$") or nil
end
-- True for our core, false for another addon's folder of the same name, and nil when its TOC names neither marker.
-- The project ID is the identity; the website covers a core old enough to predate the ID.
local function ours(index)
	local project = trimmed(safe("GetAddOnMetadata", index, "X-Curse-Project-ID"))
	if project and project ~= "" then
		return project == CORE_PROJECT
	end
	local website = trimmed(safe("GetAddOnMetadata", index, "X-Website"))
	if website and website ~= "" then
		return website == CORE_WEBSITE
	end
end
-- The title of an installed ForeverCore folder that is another addon's, or nil when ours, absent or unidentifiable.
local function foreign()
	local total = safe("GetNumAddOns")
	if type(total) ~= "number" then
		return nil
	end
	for index = 1, total do
		local name = safe("GetAddOnInfo", index)
		if type(name) == "string" and name:lower() == "forevercore" and ours(index) == false then
			return title(index, name)
		end
	end
end
local function show(text)
	if _G.UIErrorsFrame and _G.UIErrorsFrame.AddMessage then
		_G.UIErrorsFrame:AddMessage(text, 1, 0.1, 0.1)
	end
end
-- The frame a line waits on until the world is drawn, kept here so the client does not collect it before then.
local worldFrame
-- A stopped addon still owns the ways a player opens it, and each one repeats the line, so trying the addon says why it
-- does nothing (cjber/shortest-path-forever#996). The addon compartment calls the global its TOC names, which the
-- addon's own files would have defined; without one a click raises a Lua error. Slash words come from the caller,
-- because nothing in the TOC lists them.
local function answer(text, slash)
	local function repeatLine()
		show(text)
	end
	for _, field in ipairs({ "AddonCompartmentFunc", "AddonCompartmentFuncOnEnter", "AddonCompartmentFuncOnLeave" }) do
		local name = trimmed(safe("GetAddOnMetadata", addonName, field))
		if name and name ~= "" and _G[name] == nil then
			_G[name] = field == "AddonCompartmentFunc" and repeatLine or function() end
		end
	end
	if type(slash) == "table" and type(slash.key) == "string" and type(_G.SlashCmdList) == "table" then
		for index, word in ipairs(slash) do
			_G["SLASH_" .. slash.key .. index] = word
		end
		_G.SlashCmdList[slash.key] = repeatLine
	end
end
-- An addon that carries its own ForeverCore (Libs/ForeverCore) needs no separate install: its copy registered with the
-- loader. When it could not start, an older standalone ForeverCore that the loader would not adopt is the one install
-- to fix; anything else is a broken package, which reinstalling the addon fixes. Nil when the addon carries no copy.
local function embeddedFailure(own)
	local loader = rawget(_G, "ForeverCoreLoader")
	if type(loader) ~= "table" or type(loader.Candidates) ~= "function" then
		return nil
	end
	local carried = false
	for _, copy in ipairs(loader.Candidates()) do
		carried = carried or copy.folder == addonName
	end
	if not carried then
		return nil
	end
	local published = rawget(_G, "ForeverCore")
	if type(published) == "table" and published.loaderSchema ~= 1 and installed() then
		return phrase("%s: %s is out of date. Update it to fix this.", own, "ForeverCore")
	end
	return phrase("%s could not start. Reinstall %s to fix this.", own, own)
end
-- The line for an addon that relies on a separately installed ForeverCore.
local function standaloneFailure(own)
	local core = installed()
	local other = foreign()
	local text
	if core == false then
		text = phrase(
			"%s needs ForeverCore. Install it from CurseForge, or choose Reinstall on ForeverCore in the CurseForge app.",
			own
		)
	elseif core and not enabled(core) then
		text = phrase("%s: ForeverCore is turned off. Enable it in the AddOns list to fix this.", own)
	elseif other then
		text = phrase(
			"%s: the installed ForeverCore is another addon (%s). Remove it and install ForeverCore from CurseForge.",
			own,
			other
		)
	else
		local found = culprits()
		if #found == 1 then
			text = phrase("%s: %s is out of date. Update it to fix this.", own, found[1])
		elseif #found > 1 then
			local joined = #found == 2 and table.concat(found, " and ")
				or (table.concat(found, ", ", 1, #found - 1) .. " and " .. found[#found])
			text = phrase("%s: %s are out of date. Update them to fix this.", own, joined)
		else
			text = phrase("%s could not start. Reinstall %s to fix this.", own, own)
		end
	end
	return text
end
-- Calls back once every file of this addon has run and its saved variables are loaded. A file uses this, never
-- EventUtil.ContinueOnAddOnLoaded on its own addon's name: in a package that carries ForeverCore the files can run
-- at login, after the client counts the addon as loaded, and that call would run the callback inside the file that
-- asked, before the files after it (cjber/adventure-guide-forever#886). The package's runner sets the queue then.
---@param callback fun()
function ns.OnFilesLoaded(callback)
	local queue = ns.ForeverCoreHostAfter
	if type(queue) == "table" then
		queue[#queue + 1] = callback
		return
	end
	_G.EventUtil.ContinueOnAddOnLoaded(addonName, callback)
end
---@param ready boolean
---@param slash? { key: string, [integer]: string } the addon's slash words and their SlashCmdList key
function ns.ForeverRequire(ready, slash)
	-- The package's runner found a file of this addon the client did not load: the rest cannot run without it.
	if ready and not ns.ForeverCoreHostIncomplete then
		return true
	end
	ns.broken = true
	local own = title(addonName, addonName)
	local text = embeddedFailure(own) or standaloneFailure(own)
	answer(text, slash)
	-- This runs while the addon's files load, so the loading screen covers the line and it has faded before the world is
	-- drawn (#659). A player who is still logging in sees it on the first PLAYER_ENTERING_WORLD instead, once.
	if _G.IsLoggedIn and not _G.IsLoggedIn() and type(_G.CreateFrame) == "function" then
		worldFrame = _G.CreateFrame("Frame", nil, _G.UIParent)
		worldFrame:RegisterEvent("PLAYER_ENTERING_WORLD")
		worldFrame:SetScript("OnEvent", function(frame)
			-- An unregister keeps a later zone change from showing the line again.
			frame:UnregisterEvent("PLAYER_ENTERING_WORLD")
			show(text)
		end)
	else
		show(text)
	end
	return false
end
