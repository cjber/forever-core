-- luacheck: read globals scenario ADDON
-- The sim's player is on a Forever realm, as the live client is (#997): no realm name, realm ID 0, the surname as
-- UnitName's second return. The shared character key then comes from the full name and the GUID's server (#999).
scenario("the character key on a Forever realm with no name", function(sim)
	sim:login()
	local ns
	for _, entry in ipairs(sim.loader.addons) do
		if entry.name == ADDON then
			ns = entry.ns
		end
	end
	assert(ns, "the addon namespace is loaded")
	local G = sim.G
	local realm, normalized, realmID = G.GetRealmName(), G.GetNormalizedRealmName(), G.GetRealmID()
	local name, surname = G.UnitName("player")
	assert(realm == "" and normalized == "", "a Forever realm has no name")
	assert(realmID == 0, "and realm ID 0")
	assert(name == "Syrberus" and surname == "Ironhide", "UnitName's second return is the surname")
	local key = ns.CharacterKey()
	assert(key == "Syrberus Ironhide-6941", "the key is the full name and the GUID's server: " .. tostring(key))

	-- A named realm keeps the key addons have always saved under.
	sim.world.player.realm = "Firemaw"
	local _, second = G.UnitName("player")
	assert(second == nil and G.GetRealmID() ~= 0, "a named realm has an ID and no surname return")
	key = ns.CharacterKey()
	assert(key == "Syrberus-Firemaw", "a named realm keeps Name-Realm: " .. tostring(key))
	sim:expectNoErrors(ADDON)
end)
