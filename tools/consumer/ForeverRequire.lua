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
local function candidate(index)
	local state = safe("GetAddOnEnableState", index, _G.UnitName and _G.UnitName("player"))
	if not (safe("IsAddOnLoaded", index) or (type(state) == "number" and state > 0)) then
		return false
	end
	local result = { pcall(C_AddOns and C_AddOns.GetAddOnDependencies, index) }
	for position = 2, result[1] and #result or 0 do
		local dependency = result[position]
		if type(dependency) == "string" and dependency:lower() == "forevercore" then
			return true
		end
	end
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
function ns.ForeverRequire(ready)
	if ready then
		return true
	end
	ns.broken = true
	local own = title(addonName, addonName)
	local other = foreign()
	local text
	if other then
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
	if _G.UIErrorsFrame and _G.UIErrorsFrame.AddMessage then
		_G.UIErrorsFrame:AddMessage(text, 1, 0.1, 0.1)
	end
	return false
end
