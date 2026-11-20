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
		knownSpells = {}, -- learned spell IDs; cached spell data in spells does not imply knowledge
		-- WorldMapMixin:OnShow selects the player's map through MapUtil.GetDisplayableMapForPlayer.
		-- Both that default map and the native fallback must exist before a scenario supplies map fixtures.
		maps = {
			[1454] = { name = "Orgrimmar", mapType = 3 },
			[947] = { name = "Azeroth", mapType = 1 },
		},
		addons = {},
		achievements = { categories = {} },
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

	-- Empty equipment and no active pet or specialization in the default world.
	impl.GetInventoryItemTexture = function()
		return nil
	end
	G.GetInventoryItemTexture = impl.GetInventoryItemTexture
	G.GetInventoryItemLink = function()
		return nil
	end
	G.GetInventoryItemQuality = function()
		return nil
	end
	G.GetInventoryItemID = function()
		return nil
	end
	impl["C_ClassColor.GetClassColor"] = function()
		return sim.api.zero({ Type = "colorRGB", Mixin = "ColorMixin" })
	end
	G.GetShapeshiftFormID = function()
		return nil
	end
	G.IsWatchingHonorAsXP = function()
		return false
	end
	G.IsInActiveWorldPVP = function()
		return false
	end
	G.HasArtifactEquipped = function()
		return false
	end
	G.GetSpellBonusDamage = function()
		return 0
	end
	G.GetSpellBonusHealing = function()
		return 0
	end
	G.IsInventoryItemLocked = function()
		return false
	end
	G.GetHitModifier = function()
		return 0
	end
	G.GetOffhandHitModifier = function()
		return 0
	end
	G.GetRangedHitModifier = function()
		return 0
	end
	G.GetSpellHitModifier = function()
		return 0
	end
	G.GetCombatRatingBonus = function()
		return 0
	end
	G.GetPetExperience = function()
		return 0, 0
	end
	impl["C_SpecializationInfo.GetSpecialization"] = function()
		return nil
	end
	-- Native inventory slot IDs are stable client constants, including the legacy ammo and ranged slots.
	local inventorySlots = {
		AmmoSlot = 0,
		HeadSlot = 1,
		NeckSlot = 2,
		ShoulderSlot = 3,
		ShirtSlot = 4,
		ChestSlot = 5,
		WaistSlot = 6,
		LegsSlot = 7,
		FeetSlot = 8,
		WristSlot = 9,
		HandsSlot = 10,
		Finger0Slot = 11,
		Finger1Slot = 12,
		Trinket0Slot = 13,
		Trinket1Slot = 14,
		BackSlot = 15,
		MainHandSlot = 16,
		SecondaryHandSlot = 17,
		RangedSlot = 18,
		TabardSlot = 19,
		Bag0Slot = 31,
		Bag1Slot = 32,
		Bag2Slot = 33,
		Bag3Slot = 34,
		Prof0ToolSlot = 20,
		Prof0Gear0Slot = 21,
		Prof0Gear1Slot = 22,
		Prof1ToolSlot = 23,
		Prof1Gear0Slot = 24,
		Prof1Gear1Slot = 25,
		CookingToolSlot = 26,
		CookingGear0Slot = 27,
		FishingToolSlot = 28,
		FishingGear0Slot = 29,
		FishingGear1Slot = 30,
	}
	impl["C_PaperDollInfo.GetInventorySlotInfo"] = function(name)
		return inventorySlots[name], nil, false
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
	impl.UnitPower = function(u)
		local x = unit(u)
		return x and (x.power or 100) or 0
	end
	impl.UnitPowerMax = function(u)
		local x = unit(u)
		return x and (x.powerMax or 100) or 0
	end
	-- Mana unless a unit says otherwise: Enum.PowerType.Mana is 0.
	impl.UnitPowerType = function(u)
		local x = unit(u)
		if x then
			return x.powerType or 0, x.powerToken or "MANA"
		end
		return 0, "MANA"
	end
	impl.UnitPowerBarTimerInfo = function(u, index)
		local x = Secret.unwrap(u) == "player" and W.player or unit(u)
		local timer = x and x.powerBarTimers and x.powerBarTimers[Secret.unwrap(index) or 0]
		-- MayReturnNothing in UnitDocumentation.lua: the empty result terminates Blizzard's timer enumeration.
		if timer then
			return timer.duration, timer.expiration, timer.barID, timer.auraID
		end
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
	-- Legacy globals used by the pinned Camelot FriendsFrame and MailFrame. Scenarios start with
	-- no Battle.net session and an empty mail draft; return the API's individual tuple fields.
	W.battleNet = { enabled = false, connected = false, afk = false, dnd = false, realIDEnabled = false }
	W.mail = { sendPrice = 30 }
	impl.BNFeaturesEnabled = function()
		return W.battleNet.enabled
	end
	impl.BNConnected = function()
		return W.battleNet.connected
	end
	impl.BNFeaturesEnabledAndConnected = function()
		return W.battleNet.enabled and W.battleNet.connected
	end
	impl.BNGetInfo = function()
		local b = W.battleNet
		return b.presenceID, b.battleTag, b.toonID, b.broadcast or "", b.afk, b.dnd, b.realIDEnabled
	end
	impl.GetSendMailPrice = function()
		return W.mail.sendPrice
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
	-- A profession's child skill line (Cooking 185, child 2939) shows only where Forever reports it: by recipe. The open
	-- window reports the base line with no parent, and GetProfessionChildSkillLineID is 0 (cjber/forever-core#831).
	local function professionInfo(p, child)
		local info = sim.api.zero({ Type = "ProfessionInfo" })
		if not p then
			return info
		end
		info.professionID = p.skillLineID
		info.professionName = p.name
		info.parentProfessionName = nil
		info.parentProfessionID = nil
		if child and p.childSkillLineID then
			info.professionID = p.childSkillLineID
			info.parentProfessionID = p.skillLineID
			info.parentProfessionName = p.name
		end
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
		return idx[1], idx[2], idx[3], idx[4], idx[5], idx[6], idx[7]
	end
	impl.GetProfessionInfo = function(index)
		local p = W.professions[index]
		if p then
			return p.name, p.icon or 136241, p.skill, p.max, 1, index - 1, p.skillLineID, p.modifier or 0, 0, 0, p.name
		end
	end
	-- Each profession's spell sits in the player's spellbook at its profession index, so the client's right-hand
	-- profession tabs show one per profession that has a crafting window (p.craftingUI false: Herbalism, Skinning).
	local function spellProfession(spellID)
		for index, p in ipairs(W.professions) do
			if (p.spellID or 900000 + index) == spellID then
				return p
			end
		end
	end
	impl["C_SpellBook.GetSpellBookItemInfo"] = function(slot)
		local index = W.professions[slot] and slot
		if index then
			local p = W.professions[index]
			local info = sim.api.zero({ Type = "SpellBookItemInfo" })
			info.spellID = p.spellID or 900000 + index
			info.name = p.name
			return info
		end
	end
	impl["C_TradeSkillUI.CanTradeSkillShowCraftingUI"] = function(spellID)
		local p = spellProfession(spellID)
		return p ~= nil and p.craftingUI ~= false
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
					return professionInfo(p, true)
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
	-- See README.md's profession search contract and pinned-source evidence.
	local recipeNameFilter = ""
	local recipeListUpdatePending = false
	impl["C_TradeSkillUI.GetRecipeItemNameFilter"] = function()
		return recipeNameFilter
	end
	impl["C_TradeSkillUI.SetRecipeItemNameFilter"] = function(text)
		text = text or ""
		if text == recipeNameFilter then
			return
		end
		recipeNameFilter = text
		if not recipeListUpdatePending then
			recipeListUpdatePending = true
			sim.impl["C_Timer.After"](0, function()
				recipeListUpdatePending = false
				sim.events.fire("TRADE_SKILL_LIST_UPDATE")
			end)
		end
	end
	impl["C_TradeSkillUI.GetFilteredRecipeIDs"] = function()
		local ids = {}
		local filter = recipeNameFilter:lower()
		for _, r in ipairs((open() or {}).recipes or {}) do
			if r.name:lower():find(filter, 1, true) then
				ids[#ids + 1] = r.id
			end
		end
		return ids
	end
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
				variableQuantities = {},
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
	impl["C_TradeSkillUI.GetProfessionChildSkillLineID"] = function()
		return 0
	end
	local function recipeProfession(recipeID)
		for _, p in ipairs(W.professions) do
			for _, r in ipairs(p.recipes or {}) do
				if r.id == recipeID then
					return p
				end
			end
		end
	end
	local function openRecipeResponse(recipeID)
		local p = recipeProfession(recipeID)
		if p then
			sim.events.queue("OPEN_RECIPE_RESPONSE", recipeID, p.skillLineID, p.childSkillLineID or p.skillLineID)
		end
	end
	-- Forever's OpenRecipe, recorded live (cjber/forever-core#831, cjber/skillup-forever#840), where retail selects the
	-- recipe in the open window: the window closes, with three TRADE_SKILL_CLOSE in one frame, and then
	-- OPEN_RECIPE_RESPONSE(recipeID, base, child) fires; the window never reopens.
	impl["C_TradeSkillUI.OpenRecipe"] = function(recipeID)
		if W.openProfession then
			W.openProfession = nil
			for _ = 1, 3 do
				sim.events.queue("TRADE_SKILL_CLOSE")
			end
		end
		openRecipeResponse(recipeID)
	end
	-- Refused to tainted code outside a hardware event, the response still fires and the window stays open.
	sim.refusedImpl = sim.refusedImpl or {}
	sim.refusedImpl["C_TradeSkillUI.OpenRecipe"] = openRecipeResponse
	impl["C_TradeSkillUI.CloseTradeSkill"] = function()
		if not W.openProfession then
			return
		end
		-- Clear the skill before the event, as the client does: ProfessionsFrame:OnHide calls this API again, and
		-- with nothing open that second call is a no-op rather than another TRADE_SKILL_CLOSE.
		W.openProfession = nil
		sim.events.fire("TRADE_SKILL_CLOSE")
	end

	-- Items. A scenario's sim.world.items[id] wins; any other item ID answers from the client's own Item and
	-- ItemSparse rows at the pinned build (fetch.py writes items-<locale>.lua), loaded on the first read.
	local EQUIP_LOC = {
		[1] = "INVTYPE_HEAD",
		[2] = "INVTYPE_NECK",
		[3] = "INVTYPE_SHOULDER",
		[4] = "INVTYPE_BODY",
		[5] = "INVTYPE_CHEST",
		[6] = "INVTYPE_WAIST",
		[7] = "INVTYPE_LEGS",
		[8] = "INVTYPE_FEET",
		[9] = "INVTYPE_WRIST",
		[10] = "INVTYPE_HAND",
		[11] = "INVTYPE_FINGER",
		[12] = "INVTYPE_TRINKET",
		[13] = "INVTYPE_WEAPON",
		[14] = "INVTYPE_SHIELD",
		[15] = "INVTYPE_RANGED",
		[16] = "INVTYPE_CLOAK",
		[17] = "INVTYPE_2HWEAPON",
		[18] = "INVTYPE_BAG",
		[19] = "INVTYPE_TABARD",
		[20] = "INVTYPE_ROBE",
		[21] = "INVTYPE_WEAPONMAINHAND",
		[22] = "INVTYPE_WEAPONOFFHAND",
		[23] = "INVTYPE_HOLDABLE",
		[24] = "INVTYPE_AMMO",
		[25] = "INVTYPE_THROWN",
		[26] = "INVTYPE_RANGEDRIGHT",
		[27] = "INVTYPE_QUIVER",
		[28] = "INVTYPE_RELIC",
	}
	local QUALITY_HEX = { "ffffff", "1eff00", "0070dd", "a335ee", "ff8000", "e6cc80", "00ccff", [0] = "9d9d9d" }
	local clientRows, clientItems = nil, {}
	local function clientItem(id)
		if clientItems[id] then
			return clientItems[id]
		end
		-- A bare world built for a unit fixture has no data directory, so only its scenario items exist.
		if not sim.dataDir then
			return nil
		end
		if not clientRows then
			local path = sim.dataDir .. "/items-" .. sim.locale .. ".lua"
			local chunk = loadfile(path)
			if not chunk then
				error(
					string.format(
						"no item data for %s in %s: run python3 tools/forever_sim/fetch.py --locale %s",
						sim.locale,
						sim.dataDir,
						sim.locale
					)
				)
			end
			clientRows = chunk()
		end
		local row = clientRows.items[id]
		if row then
			local class = clientRows.classes[row[6]]
			clientItems[id] = {
				name = row[1],
				quality = row[2],
				sell = row[3],
				level = row[4],
				stack = row[5],
				classID = row[6],
				subClassID = row[7],
				itemEquipLoc = EQUIP_LOC[row[8]] or "",
				icon = row[9],
				minLevel = row[10],
				bindType = row[11],
				expansionID = row[12],
				setID = row[13] ~= 0 and row[13] or nil,
				description = row[14],
				itemType = class and class.name or "",
				itemSubType = class and class.subs[row[7]] or "",
			}
		end
		return clientItems[id]
	end
	function sim.item(id)
		id = tonumber(Secret.unwrap(id))
		return id and (W.items[id] or clientItem(id))
	end
	function sim.itemLink(id)
		local item = assert(sim.item(id), "no item " .. tostring(id))
		return item.link
			or string.format(
				"|cff%s|Hitem:%d::::::::%d:::::::::|h[%s]|h|r",
				QUALITY_HEX[item.quality or 1] or "ffffff",
				id,
				W.player.level,
				item.name
			)
	end
	local function resolveItemInfo(info)
		info = Secret.unwrap(info)
		if type(info) == "number" then
			return info, sim.item(info)
		end
		if type(info) == "string" then
			for id, item in pairs(W.items) do
				if info == item.link or info == item.name or info == "item:" .. id then
					return id, item
				end
			end
			local id = tonumber(info:match("^item:(%d+)") or info:match("^|c%x+|Hitem:(%d+)") or info:match("^(%d+)$"))
			if id then
				return id, sim.item(id)
			end
			-- The client resolves a name only for an item it has cached; the sim's cache is what the bags hold.
			for _, b in pairs(W.bags) do
				for slot = 1, b.size or 0 do
					local held = b[slot] and sim.item(b[slot].itemID)
					if held and held.name == info then
						return b[slot].itemID, held
					end
				end
			end
		end
	end
	impl["C_Item.GetItemInfoInstant"] = function(info)
		local id, item = resolveItemInfo(info)
		if item then
			return id,
				item.itemType or "",
				item.itemSubType or "",
				item.itemEquipLoc or "",
				item.icon or 134400,
				item.classID or 0,
				item.subClassID or 0
		end
	end
	impl["C_Item.GetItemIDForItemInfo"] = function(info)
		return resolveItemInfo(info) or 0
	end
	impl["C_Item.GetItemInfo"] = function(info)
		local id, item = resolveItemInfo(info)
		if item then
			-- isCraftingReagent: the client derives it from item flags the sim does not decode.
			return item.name,
				sim.itemLink(id),
				item.quality or 1,
				item.level or 1,
				item.minLevel or 0,
				item.itemType or "",
				item.itemSubType or "",
				item.stack or 20,
				item.itemEquipLoc or "",
				item.icon or 134400,
				item.sell or 0,
				item.classID or 0,
				item.subClassID or 0,
				item.bindType or 0,
				item.expansionID or 0,
				item.setID,
				false,
				item.description or ""
		end
	end
	G.GetItemInfo = G.C_Item.GetItemInfo
	impl["C_Item.GetItemNameByID"] = function(info)
		local _, item = resolveItemInfo(info)
		return item and item.name
	end
	impl["C_Item.GetItemQualityByID"] = function(info)
		local _, item = resolveItemInfo(info)
		return item and (item.quality or 1)
	end
	impl["C_Item.GetItemIconByID"] = function(info)
		local _, item = resolveItemInfo(info)
		return item and (item.icon or 134400)
	end
	-- The bags hold what the client counts; a scenario item with no bag slot keeps its own count.
	impl["C_Item.GetItemCount"] = function(info)
		local id, item = resolveItemInfo(info)
		local held = sim.bagCount(id)
		if held then
			return held
		end
		return item and item.count or 0
	end
	G.GetItemCount = G.C_Item.GetItemCount
	impl["C_Item.DoesItemExistByID"] = function(info)
		local _, item = resolveItemInfo(info)
		return item ~= nil
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
		if r then
			return { name = r.name, icon = r.icon or 134400 }
		end
		local p = spellProfession(id)
		return p and { name = p.name, icon = p.icon or 136241 }
	end
	-- Flyout definitions exist before their spells are learned. Blizzard's class action button enumerates
	-- these slots at PLAYER_LOGIN even when none are known; an unknown flyout ID still returns nothing.
	G.GetFlyoutInfo = function(id)
		local flyout = sim.flyouts[Secret.unwrap(id)]
		if flyout then
			local known = false
			for _, spellID in ipairs(flyout.slots) do
				known = known or W.knownSpells[spellID] == true
			end
			return flyout.name, flyout.description, #flyout.slots, known
		end
	end
	G.GetFlyoutSlotInfo = function(id, index)
		local flyout = sim.flyouts[Secret.unwrap(id)]
		local spellID = flyout and flyout.slots[Secret.unwrap(index)]
		if spellID then
			local info = spell(spellID)
			return spellID, spellID, W.knownSpells[spellID] == true, info and info.name
		end
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
		local known = W.items[tonumber(id) or 0] ~= nil
		-- A noisy client fails some loads of items it does know (sim:noisy).
		local failed = known and sim.noise and sim.noise.fails()
		sim.events.queue("ITEM_DATA_LOAD_RESULT", id, known and not failed)
	end

	-- Maps: the player's position and the map tree (fill sim.world.maps[id] = { name, parent, mapType }).
	impl["C_Map.OpenWorldMap"] = function(mapID)
		-- The C API raises the WORLD_MAP_OPEN event, which WorldMapFrame registers for and handles by opening
		-- the map (Blizzard_WorldMap/Blizzard_WorldMap.lua:171 and :198). The event dispatch is the engine
		-- boundary: handlers run with their own taint, while the Lua this API loads runs in the caller's taint.
		G.C_AddOns.LoadAddOn("Blizzard_WorldMap")
		sim.events.fire("WORLD_MAP_OPEN", mapID)
	end
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

	-- Achievements: the legacy globals the generated documentation leaves out, answered from
	-- sim.world.achievements in the client's documented shapes.
	local function achievementCategory(id)
		for _, c in ipairs(W.achievements.categories or {}) do
			if c.id == id then
				return c
			end
		end
	end
	local function achievement(id)
		for _, c in ipairs(W.achievements.categories or {}) do
			for _, a in ipairs(c.achievements or {}) do
				if a.id == id then
					return a, c
				end
			end
		end
	end
	local function achievementInfo(a)
		local wasEarnedByMe = a.wasEarnedByMe
		if wasEarnedByMe == nil then
			wasEarnedByMe = a.completed == true
		end
		return a.id,
			a.name,
			a.points or 0,
			a.completed == true,
			a.month,
			a.day,
			a.year,
			a.description or "",
			a.flags or 0,
			a.icon,
			a.rewardText,
			a.isGuild == true,
			wasEarnedByMe,
			a.earnedBy,
			a.isStatistic == true
	end
	impl.GetCategoryList = function()
		local ids = {}
		for _, c in ipairs(W.achievements.categories or {}) do
			ids[#ids + 1] = c.id
		end
		return ids
	end
	impl.GetCategoryNumAchievements = function(id)
		local c = achievementCategory(id)
		if not c then
			return nil
		end
		local total, completed = 0, 0
		for _, a in ipairs(c.achievements or {}) do
			total = total + 1
			if a.completed then
				completed = completed + 1
			end
		end
		return total, completed, total - completed
	end
	impl.GetAchievementInfo = function(id, index)
		local a
		if index ~= nil then
			local c = achievementCategory(id)
			a = c and (c.achievements or {})[index]
		else
			a = achievement(id)
		end
		if a then
			return achievementInfo(a)
		end
	end
	impl.GetAchievementCategory = function(id)
		local _, c = achievement(id)
		return c and c.id
	end
	impl.GetCategoryInfo = function(id)
		local c = achievementCategory(id)
		if c then
			return c.name, c.parent or -1, c.flags or 0
		end
	end
	impl.GetAchievementNumCriteria = function(id)
		local a = achievement(id)
		if a then
			return #(a.criteria or {})
		end
	end
	impl.GetAchievementCriteriaInfo = function(id, index)
		local a = achievement(id)
		local c = a and (a.criteria or {})[index]
		if not c then
			return nil
		end
		local quantity, required = c.quantity or 0, c.required or 0
		return c.text or "",
			c.type or 0,
			c.completed == true,
			quantity,
			required,
			c.charName,
			c.flags or 0,
			c.asset or c.assetID,
			c.quantityString or string.format("%d/%d", quantity, required),
			c.id or c.criteriaID or index,
			c.eligible ~= false
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
		local loaded = sim.loader.loaded[name] ~= nil or sim.loader.partialLoaded[name] == true
		return loaded, loaded
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
	-- Bags: sim.world.bags[bag] = { size = n, [slot] = { itemID = id, count = n } }, bag 0 the backpack (16 slots).
	-- Each slot's item answers from sim.item, so a slot naming an item the client does not have fails the read.
	W.bags = W.bags or { [0] = { size = 16 } }
	local function bagSlot(bag, slot)
		local b = W.bags[tonumber(Secret.unwrap(bag))]
		local s = b and b[tonumber(Secret.unwrap(slot))]
		if s then
			return s,
				assert(
					sim.item(s.itemID),
					"sim.world.bags holds item " .. tostring(s.itemID) .. ", which no client data has"
				)
		end
	end
	function sim.bagCount(id)
		local total
		for _, b in pairs(W.bags) do
			for slot = 1, b.size or 0 do
				local s = b[slot]
				if s and s.itemID == id then
					total = (total or 0) + (s.count or 1)
				end
			end
		end
		return total
	end
	impl["C_Container.GetContainerNumSlots"] = function(bag)
		local b = W.bags[tonumber(Secret.unwrap(bag))]
		return b and b.size or 0
	end
	impl["C_Container.GetContainerNumFreeSlots"] = function(bag)
		local b = W.bags[tonumber(Secret.unwrap(bag))]
		local free = 0
		for slot = 1, b and b.size or 0 do
			if not b[slot] then
				free = free + 1
			end
		end
		return free, 0
	end
	impl["C_Container.GetContainerItemID"] = function(bag, slot)
		local s = bagSlot(bag, slot)
		return s and s.itemID
	end
	impl["C_Container.GetContainerItemLink"] = function(bag, slot)
		local s = bagSlot(bag, slot)
		return s and sim.itemLink(s.itemID)
	end
	impl["C_Container.GetContainerItemInfo"] = function(bag, slot)
		local s, item = bagSlot(bag, slot)
		if not s then
			return nil
		end
		return {
			iconFileID = item.icon or 134400,
			stackCount = s.count or 1,
			isLocked = false,
			quality = item.quality or 1,
			isReadable = false,
			hasLoot = false,
			hyperlink = sim.itemLink(s.itemID),
			itemName = item.name,
			isFiltered = false,
			hasNoValue = (item.sell or 0) == 0,
			itemID = s.itemID,
			isBound = false,
		}
	end
	-- With a merchant open, using a bag item sells it: the slot empties and the player gets its sell price per unit.
	impl["C_Container.UseContainerItem"] = function(bag, slot)
		local s, item = bagSlot(bag, slot)
		local merchant = G.MerchantFrame
		if not s or not (merchant and merchant:IsShown()) or (item.sell or 0) == 0 then
			return
		end
		bag, slot = tonumber(Secret.unwrap(bag)), tonumber(Secret.unwrap(slot))
		W.bags[bag][slot] = nil
		W.player.money = W.player.money + item.sell * (s.count or 1)
		sim.events.fire("BAG_UPDATE", bag)
		sim.events.fire("PLAYER_MONEY")
		sim.events.fire("BAG_UPDATE_DELAYED")
	end
	-- Items the player receives in one transaction, each { itemID, count } in the first empty slot from the backpack
	-- up: BAG_UPDATE for each bag that changed, then one BAG_UPDATE_DELAYED. Stacks are not merged. Nothing moves and
	-- false returns when the free slots cannot hold them all, as the client refuses a loot or reward into full bags.
	function sim.giveItems(entries)
		local free = {}
		for bag = 0, 4 do
			local b = W.bags[bag]
			for slot = 1, b and b.size or 0 do
				if not b[slot] then
					free[#free + 1] = { bag, slot }
				end
			end
		end
		if #entries > #free then
			return false
		end
		local changed = {}
		for i, entry in ipairs(entries) do
			assert(sim.item(entry[1]), "no client data has item " .. tostring(entry[1]))
			local bag, slot = free[i][1], free[i][2]
			W.bags[bag][slot] = { itemID = entry[1], count = entry[2] or 1 }
			changed[bag] = true
		end
		for bag = 0, 4 do
			if changed[bag] then
				sim.events.fire("BAG_UPDATE", bag)
			end
		end
		if next(changed) then
			sim.events.fire("BAG_UPDATE_DELAYED")
		end
		return true
	end

	-- The quest giver's reward panel: sim.world.questReward = { questID, title, text, choices = { {itemID, count} },
	-- rewards = { {itemID, count} }, money, xp }, read through the client's legacy quest-frame natives.
	local function questItem(kind, index)
		local q = W.questReward
		local list = q and (Secret.unwrap(kind) == "choice" and q.choices or q.rewards)
		local entry = list and list[tonumber(Secret.unwrap(index))]
		if entry then
			return entry,
				assert(sim.item(entry[1]), "quest reward item " .. tostring(entry[1]) .. " has no client data")
		end
	end
	impl.GetQuestID = function()
		return W.questReward and W.questReward.questID or 0
	end
	impl.GetTitleText = function()
		return W.questReward and W.questReward.title or ""
	end
	impl.GetRewardText = function()
		return W.questReward and W.questReward.text or ""
	end
	impl.GetNumQuestChoices = function()
		return W.questReward and #(W.questReward.choices or {}) or 0
	end
	impl.GetNumQuestRewards = function()
		return W.questReward and #(W.questReward.rewards or {}) or 0
	end
	impl.GetQuestItemInfo = function(kind, index)
		local entry, item = questItem(kind, index)
		if entry then
			return item.name, item.icon or 134400, entry[2] or 1, item.quality or 1, true, entry[1]
		end
	end
	impl.GetQuestItemLink = function(kind, index)
		local entry = questItem(kind, index)
		return entry and sim.itemLink(entry[1])
	end
	impl.GetQuestItemInfoLootType = function()
		return 0
	end
	impl.GetRewardMoney = function()
		return W.questReward and W.questReward.money or 0
	end
	impl.GetRewardXP = function()
		return W.questReward and W.questReward.xp or 0
	end
	impl.GetQuestMoneyToGet = function()
		return 0
	end
	-- Rewards a scenario does not model: none of them.
	impl.GetRewardSkillPoints = function()
		return nil
	end
	impl.GetRewardArtifactXP = function()
		return 0, 0
	end
	impl.GetRewardHonor = function()
		return 0
	end
	impl.GetRewardTitle = function()
		return nil
	end
	impl.GetQuestPortraitTurnIn = function()
		return 0, "", ""
	end
	-- No giver-specific parchment: the frame draws its default.
	impl.GetQuestBackgroundMaterial = function()
		return nil
	end
	-- Turning the quest in: the chosen item and every fixed reward go to the bags, the money to the player.
	impl.GetQuestReward = function(choice)
		local q = W.questReward
		if not q then
			return
		end
		choice = tonumber(Secret.unwrap(choice)) or 0
		local items = {}
		if #(q.choices or {}) > 0 then
			items[1] = q.choices[choice]
			assert(items[1], "GetQuestReward needs a choice between 1 and " .. #q.choices)
		end
		for _, entry in ipairs(q.rewards or {}) do
			items[#items + 1] = entry
		end
		-- Bags too full for the rewards: the quest stays open, as the client keeps it.
		if not sim.giveItems(items) then
			return
		end
		W.questReward = nil
		if (q.money or 0) > 0 then
			W.player.money = W.player.money + q.money
			sim.events.fire("PLAYER_MONEY")
		end
		sim.events.fire("QUEST_FINISHED")
	end
	impl.CloseQuest = function()
		if W.questReward then
			W.questReward = nil
			sim.events.fire("QUEST_FINISHED")
		end
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
