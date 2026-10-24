-- The game world the client reports: the player, other units and the group, professions and recipes, items,
-- maps and the addon list. Scenarios set sim.world (see README.md); every answer goes through the generated,
-- documented stubs, so secrecy and argument rules still apply.
local Secret = require("veil")

local M = {}

local function copy(t)
	local out = {}
	for k, v in pairs(t or {}) do
		out[k] = v
	end
	return out
end

function M.build(sim)
	local G, impl = sim.G, sim.impl
	local W = {
		player = {
			name = "Syrberus",
			realm = "Forever",
			level = 60,
			race = "Orc",
			raceFile = "Orc",
			className = "Warrior",
			classFile = "WARRIOR",
			classID = 1,
			faction = "Horde",
			guid = "Player-0000-00000001",
			money = 1000000,
			map = 1454, -- Orgrimmar
			x = 0.5,
			y = 0.5,
			instance = 1,
		},
		units = {},
		group = {}, -- party member units, "party1".."party4"
		professions = {}, -- { skillLineID, name, skill, max, modifier, icon, recipes = {...}, categories = {...} }
		openProfession = nil,
		items = {},
		maps = {},
		addons = {},
	}
	sim.world = W
	sim.units = setmetatable({}, {
		__index = function(_, unit)
			return M.unit(sim, unit)
		end,
	})
	sim.items = W.items

	function M.unit(_, unit)
		unit = Secret.unwrap(unit)
		if unit == "player" then
			local p = W.player
			return {
				name = p.name,
				level = p.level,
				guid = p.guid,
				isPlayer = true,
				friendly = true,
				race = p.race,
				faction = p.faction,
				classFile = p.classFile,
			}
		end
		if type(unit) == "string" and unit:match("^party%d$") then
			return W.group[tonumber(unit:sub(6))]
		end
		return W.units[unit]
	end
	local function unit(u)
		return M.unit(sim, u)
	end

	impl.UnitName = function(u)
		local x = unit(u)
		if x then
			return x.name, x.realm
		end
	end
	impl.UnitNameUnmodified = impl.UnitName
	impl.UnitFullName = function(u)
		local x = unit(u)
		if x then
			return x.name, x.realm or W.player.realm
		end
	end
	impl.GetUnitName = function(u)
		local x = unit(u)
		return x and x.name
	end
	impl.UnitGUID = function(u)
		local x = unit(u)
		return x and x.guid
	end
	impl.UnitLevel = function(u)
		local x = unit(u)
		return x and x.level or 0
	end
	impl.UnitEffectiveLevel = impl.UnitLevel
	impl.UnitExists = function(u)
		return unit(u) ~= nil
	end
	impl.UnitIsPlayer = function(u)
		local x = unit(u)
		return x and x.isPlayer or false
	end
	impl.UnitIsUnit = function(a, b)
		local x, y = unit(a), unit(b)
		return x ~= nil and y ~= nil and x.guid == y.guid
	end
	impl.UnitIsFriend = function(_, b)
		local x = unit(b)
		return x and x.friendly or false
	end
	impl.UnitCanAttack = function(_, b)
		local x = unit(b)
		return x and not x.friendly or false
	end
	impl.UnitIsEnemy = impl.UnitCanAttack
	impl.UnitIsDeadOrGhost = function(u)
		local x = unit(u)
		return x and x.dead or false
	end
	impl.UnitIsDead = impl.UnitIsDeadOrGhost
	impl.UnitClass = function(u)
		local x = unit(u)
		if x then
			return x.className or W.player.className, x.classFile or W.player.classFile, x.classID or 1
		end
	end
	impl.UnitClassBase = function(u)
		local x = unit(u)
		if x then
			return x.classFile or W.player.classFile, x.classID or 1
		end
	end
	impl.UnitRace = function(u)
		local x = unit(u)
		if x then
			return x.race or W.player.race, x.raceFile or W.player.raceFile, 2
		end
	end
	impl.UnitFactionGroup = function(u)
		local x = unit(u)
		if x then
			return x.faction or W.player.faction, x.faction or W.player.faction
		end
	end
	impl.UnitHealth = function(u)
		local x = unit(u)
		return x and (x.health or 100) or 0
	end
	impl.UnitHealthMax = function(u)
		local x = unit(u)
		return x and (x.healthMax or 100) or 0
	end
	impl.UnitAffectingCombat = function(u)
		return Secret.unwrap(u) == "player" and sim.inCombat or false
	end
	impl.UnitInParty = function(u)
		local x = unit(u)
		return x ~= nil and (Secret.unwrap(u) == "player" and #W.group > 0 or x.party == true)
	end
	impl.UnitInRaid = function()
		return nil
	end
	impl.IsInGroup = function()
		return #W.group > 0
	end
	impl.IsInRaid = function()
		return false
	end
	impl.GetNumGroupMembers = function()
		return #W.group > 0 and #W.group + 1 or 0
	end
	impl.GetNumSubgroupMembers = function()
		return #W.group
	end
	impl.UnitPosition = function(u)
		if Secret.unwrap(u) == "player" then
			return W.player.worldY or 0, W.player.worldX or 0, 0, W.player.instance
		end
	end
	impl.GetNormalizedRealmName = function()
		return W.player.realm
	end
	impl.GetRealmName = impl.GetNormalizedRealmName
	impl.GetMoney = function()
		return W.player.money
	end
	impl.IsPlayerInWorld = function()
		return sim.loggedIn == true
	end
	impl.IsLoggedIn = impl.IsPlayerInWorld
	impl.PlayerIsInCombat = function()
		return sim.inCombat == true
	end
	impl.GetMaxPlayerLevel = function()
		return 60
	end
	impl.GetExpansionLevel = function()
		return 0
	end
	impl.GetClassicExpansionLevel = function()
		return 0
	end

	-- Professions.
	local function profession(skillLineID)
		for _, p in ipairs(W.professions) do
			if p.skillLineID == skillLineID then
				return p
			end
		end
	end
	local function open()
		return W.openProfession and profession(W.openProfession)
	end
	sim.profession = open
	local function professionInfo(p)
		local info = sim.api.zero({ Type = "ProfessionInfo" })
		if not p then
			return info
		end
		info.professionID = p.skillLineID
		info.professionName = p.name
		info.parentProfessionName = nil
		info.parentProfessionID = nil
		info.skillLevel = p.skill
		info.maxSkillLevel = p.max
		info.skillModifier = p.modifier or 0
		info.isPrimaryProfession = p.primary ~= false
		info.sourceCounter = 1
		info.profession = p.profession or 0
		info.expansionName = ""
		return info
	end
	impl.GetProfessions = function()
		local idx = {}
		for i in ipairs(W.professions) do
			idx[i] = i
		end
		return idx[1], idx[2], idx[3], idx[4], idx[5], idx[6]
	end
	impl.GetProfessionInfo = function(index)
		local p = W.professions[index]
		if p then
			return p.name, p.icon or 136241, p.skill, p.max, 0, 0, p.skillLineID, p.modifier or 0, 0, 0, p.name
		end
	end
	impl["C_TradeSkillUI.GetBaseProfessionInfo"] = function()
		return professionInfo(open())
	end
	impl["C_TradeSkillUI.GetChildProfessionInfo"] = function()
		return professionInfo(open())
	end
	impl["C_TradeSkillUI.GetChildProfessionInfos"] = function()
		local p = open()
		return p and { professionInfo(p) } or {}
	end
	impl["C_TradeSkillUI.GetProfessionInfoBySkillLineID"] = function(id)
		return professionInfo(profession(id))
	end
	impl["C_TradeSkillUI.GetProfessionInfoByRecipeID"] = function(recipeID)
		for _, p in ipairs(W.professions) do
			for _, r in ipairs(p.recipes or {}) do
				if r.id == recipeID then
					return professionInfo(p)
				end
			end
		end
		return professionInfo(nil)
	end
	impl["C_TradeSkillUI.IsTradeSkillReady"] = function()
		return open() ~= nil
	end
	impl["C_TradeSkillUI.GetShowLearned"] = function()
		return true
	end
	impl["C_TradeSkillUI.GetShowUnlearned"] = function()
		return true
	end
	impl["C_TradeSkillUI.GetTradeSkillTexture"] = function()
		return 136241
	end
	impl["C_TradeSkillUI.GetTradeSkillDisplayName"] = function(id)
		local p = profession(id)
		return p and p.name or ""
	end
	impl["C_TradeSkillUI.GetTradeSkillLine"] = function()
		local p = open()
		if p then
			return p.skillLineID, p.name, p.skill, p.max, p.modifier or 0
		end
	end
	local DIFFICULTY = { optimal = 0, medium = 1, easy = 2, trivial = 3, nodifficulty = 4 }
	local function recipe(id)
		for _, p in ipairs(W.professions) do
			for _, r in ipairs(p.recipes or {}) do
				if r.id == id then
					return r, p
				end
			end
		end
	end
	sim.recipe = recipe
	local function recipeInfo(r)
		local info = sim.api.zero({ Type = "TradeSkillRecipeInfo" }) or {}
		info.recipeID = r.id
		info.name = r.name
		info.categoryID = r.category or 1
		info.learned = r.learned ~= false
		info.relativeDifficulty = DIFFICULTY[r.difficulty or "optimal"] or 0
		info.numSkillUps = r.skillUps or 1
		info.maxTrivialLevel = r.grey or 0
		info.icon = r.icon or 134400
		info.craftable = true
		info.disabled = false
		info.favorite = false
		info.supportsQualities = false
		info.isRecraft = false
		info.firstCraft = false
		info.hyperlink = string.format("|cffffffff|Henchant:%d|h[%s]|h|r", r.id, r.name)
		return info
	end
	impl["C_TradeSkillUI.GetAllRecipeIDs"] = function()
		local ids = {}
		for _, r in ipairs((open() or {}).recipes or {}) do
			ids[#ids + 1] = r.id
		end
		return ids
	end
	impl["C_TradeSkillUI.GetFilteredRecipeIDs"] = impl["C_TradeSkillUI.GetAllRecipeIDs"]
	impl["C_TradeSkillUI.GetRecipeInfo"] = function(id)
		local r = recipe(id)
		return r and recipeInfo(r)
	end
	impl["C_TradeSkillUI.IsRecipeInSkillLine"] = function(id)
		return recipe(id) ~= nil
	end
	impl["C_TradeSkillUI.GetCategories"] = function()
		local ids = {}
		for _, c in ipairs((open() or {}).categories or {}) do
			ids[#ids + 1] = c.id
		end
		return unpack(ids)
	end
	impl["C_TradeSkillUI.GetCategoryInfo"] = function(id)
		for _, c in ipairs((open() or {}).categories or {}) do
			if c.id == id then
				local info = sim.api.zero({ Type = "TradeSkillCategoryInfo" }) or {}
				info.categoryID, info.name, info.type = c.id, c.name, "header"
				info.uiOrder, info.numIndents, info.hasProgressBar = c.order or c.id, 0, false
				info.skillLineCurrentLevel, info.skillLineMaxLevel = 0, 0
				return info
			end
		end
	end
	impl["C_TradeSkillUI.GetRecipeSchematic"] = function(id)
		local r = recipe(id)
		if not r then
			return nil
		end
		local s = sim.api.zero({ Type = "CraftingRecipeSchematic" }) or {}
		s.recipeID, s.outputItemID, s.quantityMin, s.quantityMax, s.recipeType = id, r.itemID or 0, 1, 1, 1
		s.name = r.name
		s.reagentSlotSchematics = {}
		for i, reagent in ipairs(r.reagents or {}) do
			s.reagentSlotSchematics[i] = {
				reagents = { { itemID = reagent[1] } },
				reagentType = 1,
				quantityRequired = reagent[2],
				slotIndex = i,
				dataSlotType = 1,
				dataSlotIndex = i,
				required = true,
			}
		end
		return s
	end
	impl["C_TradeSkillUI.GetCraftableCount"] = function()
		return 5
	end
	impl["C_TradeSkillUI.GetRecipeRequirements"] = function()
		return {}
	end
	impl["C_TradeSkillUI.OpenTradeSkill"] = function(id)
		if profession(id) then
			sim:openProfessions(id)
			return true
		end
		return false
	end

	-- Items.
	impl["C_Item.GetItemInfo"] = function(id)
		local item = W.items[tonumber(id) or 0]
		if item then
			return item.name,
				item.link,
				item.quality or 1,
				item.level or 1,
				0,
				"",
				"",
				20,
				"",
				item.icon or 134400,
				item.sell or 0
		end
	end
	G.GetItemInfo = G.C_Item.GetItemInfo
	impl["C_Item.GetItemNameByID"] = function(id)
		local item = W.items[tonumber(id) or 0]
		return item and item.name
	end
	impl["C_Item.GetItemIconByID"] = function(id)
		local item = W.items[tonumber(id) or 0]
		return item and (item.icon or 134400)
	end
	impl["C_Item.GetItemCount"] = function(id)
		local item = W.items[tonumber(id) or 0]
		return item and item.count or 0
	end
	G.GetItemCount = G.C_Item.GetItemCount
	impl["C_Item.DoesItemExistByID"] = function(id)
		return W.items[tonumber(id) or 0] ~= nil
	end
	impl["C_Item.IsItemDataCachedByID"] = function()
		return true
	end

	-- Items a profession's recipes make or use exist (named after the recipe, or "Item <id>").
	function sim.ensureRecipeItems()
		for _, p in ipairs(W.professions) do
			for _, r in ipairs(p.recipes or {}) do
				if r.itemID and not W.items[r.itemID] then
					W.items[r.itemID] = { name = r.name }
				end
				for _, reagent in ipairs(r.reagents or {}) do
					if not W.items[reagent[1]] then
						W.items[reagent[1]] = { name = "Item " .. reagent[1] }
					end
				end
			end
		end
	end

	-- Spells: recipes and sim.world.spells[id] = { name, icon }. Data loads answer on the next frame.
	W.spells = W.spells or {}
	local function spell(id)
		id = tonumber(Secret.unwrap(id))
		if not id then
			return nil
		end
		if W.spells[id] then
			return W.spells[id]
		end
		local r = recipe(id)
		return r and { name = r.name, icon = r.icon or 134400 }
	end
	impl["C_Spell.DoesSpellExist"] = function(id)
		return spell(id) ~= nil
	end
	impl["C_Spell.IsSpellDataCached"] = function(id)
		return spell(id) ~= nil
	end
	impl["C_Spell.RequestLoadSpellData"] = function(id)
		sim.events.queue("SPELL_DATA_LOAD_RESULT", id, spell(id) ~= nil)
	end
	impl["C_Spell.GetSpellName"] = function(id)
		local x = spell(id)
		return x and x.name
	end
	impl["C_Spell.GetSpellTexture"] = function(id)
		local x = spell(id)
		return x and x.icon, x and x.icon
	end
	impl["C_Spell.GetSpellInfo"] = function(id)
		local x = spell(id)
		if x then
			return {
				name = x.name,
				iconID = x.icon,
				originalIconID = x.icon,
				spellID = tonumber(id),
				castTime = 0,
				minRange = 0,
				maxRange = 0,
			}
		end
	end
	impl["C_Spell.GetSpellLink"] = function(id)
		local x = spell(id)
		return x and string.format("|cff71d5ff|Hspell:%d:0|h[%s]|h|r", id, x.name)
	end
	impl["C_Spell.GetSpellDescription"] = function()
		return ""
	end
	impl["C_Item.RequestLoadItemDataByID"] = function(id)
		sim.events.queue("ITEM_DATA_LOAD_RESULT", id, W.items[tonumber(id) or 0] ~= nil)
	end

	-- Maps: the player's position and the map tree (fill sim.world.maps[id] = { name, parent, mapType }).
	impl["C_Map.GetBestMapForUnit"] = function(u)
		if Secret.unwrap(u) == "player" then
			return W.player.map
		end
	end
	impl["C_Map.GetPlayerMapPosition"] = function(mapID, u)
		if Secret.unwrap(u) == "player" and mapID == W.player.map then
			return G.CreateVector2D and G.CreateVector2D(W.player.x, W.player.y) or { x = W.player.x, y = W.player.y }
		end
	end
	impl["C_Map.GetMapInfo"] = function(mapID)
		local m = W.maps[mapID]
		if not m then
			return nil
		end
		return {
			mapID = mapID,
			name = m.name,
			mapType = m.mapType or 3,
			parentMapID = m.parent or 0,
			flags = 0,
		}
	end
	impl["C_Map.GetMapChildrenInfo"] = function(mapID)
		local out = {}
		for id, m in pairs(W.maps) do
			if m.parent == mapID then
				out[#out + 1] = impl["C_Map.GetMapInfo"](id)
			end
		end
		return out
	end
	impl["C_Map.GetFallbackWorldMapID"] = function()
		return 947
	end
	impl["C_Map.GetMapArtLayers"] = function()
		return {
			{
				layerHeight = 668,
				layerWidth = 1002,
				tileHeight = 256,
				tileWidth = 256,
				minScale = 1,
				maxScale = 1,
				additionalZoomSteps = 0,
			},
		}
	end
	impl["C_Map.GetMapArtLayerTextures"] = function()
		return {}
	end
	impl["C_Map.GetMapRectOnMap"] = function()
		return 0, 1, 0, 1
	end
	impl["C_Map.GetWorldPosFromMapPos"] = function(_, pos)
		return 0, pos
	end
	impl["C_Map.GetUserWaypointPositionForMap"] = function(mapID)
		local wp = W.waypoint
		if wp and wp.map == mapID then
			return G.CreateVector2D(wp.x, wp.y)
		end
	end
	impl["C_Map.HasUserWaypoint"] = function()
		return W.waypoint ~= nil
	end
	impl["C_Map.CanSetUserWaypointOnMap"] = function()
		return true
	end
	impl["C_Map.MapHasArt"] = function()
		return true
	end

	-- Addons: Blizzard's (load on demand from the UI source) and the scenario's.
	local function addonName(x)
		if type(x) == "number" then
			local e = sim.loader.addons[x]
			return e and e.name
		end
		return x
	end
	impl["C_AddOns.IsAddOnLoaded"] = function(name)
		name = addonName(name)
		local e = sim.loader.addons[name]
		if e then
			return e.loaded == true, e.loaded == true
		end
		return sim.loader.loaded[name] ~= nil, sim.loader.loaded[name] ~= nil
	end
	impl["C_AddOns.LoadAddOn"] = function(name)
		name = addonName(name)
		if sim.loader.addons[name] then
			return sim.loader.load(name), nil
		end
		local ok = sim.loader.blizzard(name)
		return ok, ok and nil or "MISSING"
	end
	impl["C_AddOns.GetAddOnMetadata"] = function(name, key)
		local e = sim.loader.addons[addonName(name)]
		return e and e.toc.metadata[key]
	end
	impl["C_AddOns.GetNumAddOns"] = function()
		return #sim.loader.addons
	end
	impl["C_AddOns.GetAddOnInfo"] = function(i)
		local e = sim.loader.addons[addonName(i)]
		if e then
			return e.name, e.toc.metadata.Title or e.name, e.toc.metadata.Notes or "", true, "INSECURE", false
		end
	end
	impl["C_AddOns.DoesAddOnExist"] = function(name)
		return sim.loader.addons[addonName(name)] ~= nil
	end
	impl["C_AddOns.GetAddOnEnableState"] = function(name)
		return sim.loader.addons[addonName(name)] and 2 or 0
	end
	impl["C_AddOns.IsAddOnLoadOnDemand"] = function()
		return false
	end
	-- Undocumented globals implemented above get a plain function.
	for k in pairs(impl) do
		if not k:find(".", 1, true) and G[k] == nil then
			G[k] = function(...)
				return impl[k](...)
			end
		end
	end
	G.IsAddOnLoaded = G.C_AddOns.IsAddOnLoaded
	G.LoadAddOn = G.C_AddOns.LoadAddOn
	G.GetAddOnMetadata = G.C_AddOns.GetAddOnMetadata
	local _ = copy
end

return M
