-- The key a Forever addon files one character's saved data under. A Forever realm has no name: the client answers ""
-- for GetRealmName and GetNormalizedRealmName and 0 for GetRealmID, and UnitName's second return is the character's
-- surname, not a realm. One account can hold several characters with the same first name on one server, so the key
-- there is the full name and the server segment of the player GUID, "Hel Io-6941". A realm with a name keeps the
-- "Name-NormalizedRealm" key addons have always saved under, so existing data still matches.

local _, ns = ...

-- The realm's normalized name, falling back to GetRealmName without spaces or hyphens for a read early in loading;
-- nil when the client names no realm.
---@return string?
local function RealmName()
	local normalized = rawget(_G, "GetNormalizedRealmName")
	local realm = type(normalized) == "function" and normalized() or nil
	if type(realm) ~= "string" or realm == "" then
		local plain = rawget(_G, "GetRealmName")
		realm = type(plain) == "function" and plain() or nil
		realm = type(realm) == "string" and (realm:gsub("[%s%-]", "")) or nil
	end
	return realm ~= "" and realm or nil
end

-- This character's key: "Name-NormalizedRealm" on a named realm, "Name Surname-ServerID" on a Forever realm. Nil
-- until the client has the character's name and GUID, and while a realm with an ID has no name yet, so an early read
-- on a named realm never answers a Forever key. Read fresh every call: a caller that asks again later gets the key.
---@return string?
function ns.CharacterKey()
	local name, surname = UnitName("player")
	if type(name) ~= "string" or name == "" or name == rawget(_G, "UNKNOWNOBJECT") then
		return nil
	end
	local guid = UnitGUID("player")
	local server = type(guid) == "string" and guid:match("^Player%-(%d+)%-") or nil
	if not server then
		return nil
	end
	local realm = RealmName()
	if realm then
		return name .. "-" .. realm
	end
	-- Only a Forever realm, ID 0, has no name for good.
	local realmID = rawget(_G, "GetRealmID")
	if type(realmID) ~= "function" or realmID() ~= 0 then
		return nil
	end
	if type(surname) == "string" and surname ~= "" then
		name = name .. " " .. surname
	end
	return name .. "-" .. server
end
