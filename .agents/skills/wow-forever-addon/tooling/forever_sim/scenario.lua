-- Scenario steps: what a player does, driven the way the client drives the UI (events, ShowUIPanel, script
-- dispatch with fresh taint), so the real Blizzard code and the addons under test react as they do in game.
local Secret = require("veil")

local M = {}

function M.install(Sim)
	-- Saved variables: a fixture file returning { VarName = value, ... }, or that table itself.
	local function savedVariables(spec)
		if type(spec) == "string" then
			local chunk = assert(loadfile(spec))
			return chunk() or {}
		end
		return spec or {}
	end

	-- Logs in: every registered addon loads (saved variables first, ADDON_LOADED after each), then
	-- VARIABLES_LOADED, PLAYER_LOGIN and PLAYER_ENTERING_WORLD, then a few frames pass.
	function Sim:login(opts)
		opts = opts or {}
		local saved = savedVariables(opts.savedVariables)
		self.savedSpec = saved
		for _, entry in ipairs(self.loader.addons) do
			for _, var in ipairs(self.loader.savedVariables(entry)) do
				if saved[var] ~= nil then
					self.G[var] = saved[var]
					self.taint.globalTaint[var] = entry.name
				end
			end
		end
		for _, entry in ipairs(self.loader.addons) do
			if not entry.loaded and not entry.toc.metadata.LoadOnDemand then
				self.loader.load(entry.name)
			end
		end
		local E = self.events
		E.fire("SPELLS_CHANGED")
		E.fire("VARIABLES_LOADED")
		-- The client's EventUtil.TriggerOnVariablesLoaded: Blizzard_Game calls it on VARIABLES_LOADED, and the
		-- gamepad action bars finish their setup there.
		if self.G.EventUtil and self.G.EventUtil.TriggerOnVariablesLoaded then
			self.run(function()
				self.G.EventUtil.TriggerOnVariablesLoaded()
			end)
		end
		if self.watch and self.watch.ensureGamepad then
			self.watch.ensureGamepad()
		end
		self.loggedIn = true
		E.fire("PLAYER_LOGIN")
		E.fire("PLAYER_ENTERING_WORLD", true, false)
		self:advance(0.5)
		return self
	end

	-- What /reload would save: each addon's saved variables as they are now (deep-copied).
	function Sim:savedState()
		local out = {}
		local function deep(v, seen)
			if type(v) ~= "table" then
				return Secret.unwrap(v)
			end
			seen = seen or {}
			if seen[v] then
				return seen[v]
			end
			local t = {}
			seen[v] = t
			for k, x in pairs(v) do
				if type(x) ~= "function" and type(x) ~= "userdata" then
					t[deep(k, seen)] = deep(x, seen)
				end
			end
			return t
		end
		for _, entry in ipairs(self.loader.addons) do
			for _, var in ipairs(self.loader.savedVariables(entry)) do
				out[var] = deep(self.G[var])
			end
		end
		return out
	end

	function Sim:tick(seconds)
		self:advance(seconds or 0.1)
		return self
	end

	-- Runs f as the client would run input: a fresh, secure dispatch.
	function Sim:input(f, ...)
		return self.run(f, ...)
	end

	-- Presses Escape as fresh hardware input: the client's own ToggleGameMenu, which walks every Escape handler
	-- secure code has registered, Blizzard's and addons'.
	function Sim:pressEscape()
		local G = self.G
		self:input(function()
			if G.ToggleGameMenu then
				G.ToggleGameMenu()
			end
		end)
		self:advance(0.1)
	end

	function Sim:showPanel(frame)
		local G = self.G
		self.run(function()
			if G.ShowUIPanel then
				G.ShowUIPanel(frame)
			else
				frame:Show()
			end
		end)
		self:advance(0.1)
	end

	---------------------------------------------------------------------------
	-- Mouse
	---------------------------------------------------------------------------
	-- Moves the mouse onto frame: OnLeave for the old focus, OnEnter for the new, each a fresh dispatch.
	function Sim:hover(frame)
		local W = self.widgets
		local old = self.mouseFocus
		if old == frame then
			return frame
		end
		if old then
			W.dispatch(old, "OnLeave", true)
		end
		self.mouseFocus = frame
		local r = frame and W.rect(frame)
		if r then
			self.mouseX, self.mouseY = r[1] + r[3] / 2, r[2] + r[4] / 2
		end
		if frame then
			W.dispatch(frame, "OnEnter", true)
		end
		self.events.flush()
		return frame
	end

	function Sim:leave()
		return self:hover(nil)
	end

	function Sim:click(frame, button)
		self.run(function()
			frame:Click(button or "LeftButton")
		end)
		self:advance(0.05)
	end

	-- Mouses over a unit in the world: the client sets "mouseover" and shows it on GameTooltip.
	function Sim:hoverUnit(def)
		local G = self.G
		self:leave()
		self.world.units.mouseover = def
		self.run(function()
			G.GameTooltip_SetDefaultAnchor(G.GameTooltip, G.UIParent)
			G.GameTooltip:SetUnit("mouseover")
		end)
		self.events.fire("UPDATE_MOUSEOVER_UNIT")
		self:advance(0.05)
	end

	function Sim:unhoverUnit()
		self.world.units.mouseover = nil
		self.run(function()
			self.G.GameTooltip:Hide()
		end)
		self:advance(0.05)
	end

	---------------------------------------------------------------------------
	-- Combat, group, locale
	---------------------------------------------------------------------------
	function Sim:enterCombat()
		self.inCombat = true
		self.events.fire("PLAYER_REGEN_DISABLED")
		self.combatLockdown = true
		self:advance(0.1)
	end

	function Sim:leaveCombat()
		self.combatLockdown = false
		self.inCombat = false
		self.events.fire("PLAYER_REGEN_ENABLED")
		self:advance(0.1)
	end

	-- members: { { name = "Ally", classFile = "MAGE", level = 60 }, ... }
	function Sim:joinGroup(members)
		for i, m in ipairs(members) do
			m.guid = m.guid or string.format("Player-0000-%08d", 100 + i)
			m.isPlayer, m.friendly, m.party = true, true, true
			self.world.group[i] = m
		end
		self.events.fire("GROUP_JOINED", 1, "group")
		self.events.fire("GROUP_ROSTER_UPDATE")
		self:advance(0.1)
	end

	function Sim:leaveGroup()
		self.world.group = {}
		self.events.fire("GROUP_LEFT", 1, "group")
		self.events.fire("GROUP_ROSTER_UPDATE")
		self:advance(0.1)
	end

	---------------------------------------------------------------------------
	-- Professions
	---------------------------------------------------------------------------
	-- Opens the Professions window on the profession `skillLineID` (default: the first in sim.world).
	function Sim:openProfessions(skillLineID)
		local G = self.G
		skillLineID = skillLineID or (self.world.professions[1] and self.world.professions[1].skillLineID)
		assert(skillLineID, "openProfessions: no profession in sim.world.professions")
		self.world.openProfession = skillLineID
		self.ensureRecipeItems()
		self.run(function()
			G.C_AddOns.LoadAddOn("Blizzard_Professions")
		end)
		local E = self.events
		E.fire("TRADE_SKILL_SHOW")
		self:showPanel(G.ProfessionsFrame)
		E.fire("TRADE_SKILL_DATA_SOURCE_CHANGED")
		E.fire("TRADE_SKILL_LIST_UPDATE")
		self:advance(0.2)
		return G.ProfessionsFrame
	end

	function Sim:closeProfessions()
		self.world.openProfession = nil
		self.events.fire("TRADE_SKILL_CLOSE")
		self.run(function()
			self.G.HideUIPanel(self.G.ProfessionsFrame)
		end)
		self:advance(0.1)
	end

	-- The recipe list's row frames now on screen, in order: { frame, recipeInfo }.
	function Sim:recipeRows()
		local G = self.G
		local list = G.ProfessionsFrame and G.ProfessionsFrame.CraftingPage.RecipeList
		assert(list, "the Professions window is not loaded")
		local rows = {}
		local frames = {}
		list.ScrollBox:ForEachFrame(function(frame)
			frames[#frames + 1] = frame
		end)
		for _, frame in ipairs(frames) do
			local data = frame.GetElementData and frame:GetElementData()
			local info = data and data.data and data.data.recipeInfo
			if info then
				rows[#rows + 1] = { frame = frame, recipeInfo = info }
			end
		end
		return rows
	end

	-- Hovers the recipe row `which` (an index among recipe rows, or a recipe name or ID).
	function Sim:hoverRecipe(which)
		local rows = self:recipeRows()
		local row
		for i, r in ipairs(rows) do
			if i == which or r.recipeInfo.name == which or r.recipeInfo.recipeID == which then
				row = r
				break
			end
		end
		assert(row, "no recipe row " .. tostring(which) .. " among " .. #rows .. " shown")
		self:hover(row.frame)
		self:advance(0.05)
		return row.frame
	end

	---------------------------------------------------------------------------
	-- World map
	---------------------------------------------------------------------------
	function Sim:openWorldMap(mapID)
		self.run(function()
			self.G.C_Map.OpenWorldMap(mapID)
		end)
		self:advance(0.3)
		return self.G.WorldMapFrame
	end

	function Sim:closeWorldMap()
		self.run(function()
			self.G.HideUIPanel(self.G.WorldMapFrame)
		end)
		self:advance(0.1)
	end

	-- Zooms the open map by `steps` (positive in) and pans it by a fraction of the canvas.
	function Sim:zoomMap(steps)
		local G = self.G
		self.run(function()
			local sc = G.WorldMapFrame.ScrollContainer
			for _ = 1, math.abs(steps) do
				if steps > 0 then
					sc:ZoomIn()
				else
					sc:ZoomOut()
				end
			end
		end)
		self:advance(0.5)
	end

	function Sim:panMap(dx, dy)
		local G = self.G
		self.run(function()
			local sc = G.WorldMapFrame.ScrollContainer
			local x, y = sc:GetNormalizedHorizontalScroll(), sc:GetNormalizedVerticalScroll()
			sc:SetPanTarget(x + (dx or 0), y + (dy or 0))
		end)
		self:advance(0.5)
	end

	---------------------------------------------------------------------------
	-- Panels other than Professions and the map: trainer, merchant, bags, character, tracker, quest log
	---------------------------------------------------------------------------
	local function dispatchTab(sim, tab)
		if tab then
			sim.widgets.dispatch(tab, "OnMouseUp", "LeftButton", true)
			sim:advance(0.02)
		end
	end

	-- The bag bar's token tracker comes from the currency UI; the sim has no currency frame, so give the bag
	-- settings manager a plain tracker to own (the fields the client's container code reads).
	local function ensureBagTracker(sim)
		local G = sim.G
		local manager = G.ContainerFrameSettingsManager
		if not manager or manager.TokenTracker then
			return
		end
		local tracker = G.CreateFrame("Frame", "SimContainerTokenTracker", G.UIParent)
		tracker.SetIsCombinedInventory = function() end
		tracker.MarkDirty = function() end
		manager.TokenTracker = tracker
	end

	-- The Professions window's right-hand profession tabs, then a selected recipe.
	function Sim:professionTabs()
		local pf = self.G.ProfessionsFrame
		local out = {}
		if not pf then
			return out
		end
		local named = { "ProfessionsOverviewTab" }
		for i = 1, 7 do
			named[#named + 1] = "Professions" .. i .. "Tab"
		end
		for _, key in ipairs(named) do
			if pf[key] then
				out[#out + 1] = pf[key]
			end
		end
		if #out == 0 then
			for _, tab in ipairs(pf.rightProfessionTabs or {}) do
				out[#out + 1] = tab
			end
		end
		return out
	end

	function Sim:selectProfessionTabs()
		for _, tab in ipairs(self:professionTabs()) do
			dispatchTab(self, tab)
		end
		return self
	end

	function Sim:openTrainer()
		local G = self.G
		self.run(function()
			G.C_AddOns.LoadAddOn("Blizzard_TrainerUI")
		end)
		local frame = G.ClassTrainerFrame or G.TrainerFrame
		if frame then
			self:showPanel(frame)
			self.events.fire("TRAINER_SHOW")
			self:advance(0.1)
		end
		return frame
	end

	function Sim:closeTrainer()
		local frame = self.G.ClassTrainerFrame or self.G.TrainerFrame
		if frame then
			self.events.fire("TRAINER_CLOSED")
			self.run(function()
				self.G.HideUIPanel(frame)
			end)
			self:advance(0.1)
		end
	end

	function Sim:openMerchant()
		ensureBagTracker(self)
		local G = self.G
		local frame = G.MerchantFrame
		if frame then
			self:showPanel(frame)
			self.events.fire("MERCHANT_SHOW")
			self:advance(0.1)
		end
		return frame
	end

	function Sim:selectMerchantTabs()
		local frame = self.G.MerchantFrame
		if frame then
			for _, tab in ipairs(frame.Tabs or {}) do
				dispatchTab(self, tab)
			end
		end
		return self
	end

	function Sim:closeMerchant()
		local frame = self.G.MerchantFrame
		if frame then
			self.events.fire("MERCHANT_CLOSED")
			self.run(function()
				self.G.HideUIPanel(frame)
			end)
			self:advance(0.1)
		end
	end

	function Sim:openBags()
		ensureBagTracker(self)
		local frame = self.G.ContainerFrame1
		if frame then
			-- The client generates the bag's item buttons before showing it; a panel shown directly has none yet.
			self.run(function()
				if frame.UpdateItemSlots then
					frame:UpdateItemSlots()
				end
			end)
			self:showPanel(frame)
			self.events.fire("BAG_UPDATE", 0)
			self:advance(0.1)
		end
		return frame
	end

	function Sim:closeBags()
		local frame = self.G.ContainerFrame1
		if frame then
			self.run(function()
				self.G.HideUIPanel(frame)
			end)
			self:advance(0.1)
		end
	end

	function Sim:openCharacter()
		local frame = self.G.CharacterFrame
		if frame then
			self:showPanel(frame)
			self:advance(0.1)
		end
		return frame
	end

	function Sim:selectCharacterTabs()
		local frame = self.G.CharacterFrame
		if frame then
			for _, tab in ipairs(frame.ModeTabs or {}) do
				local button = type(tab) == "table" and tab.Tab or tab
				if type(button) == "table" then
					dispatchTab(self, button)
				end
			end
			if frame.SetSelectedModeTabByFrame and frame.ModeTabs then
				for _, tab in ipairs(frame.ModeTabs) do
					if type(tab) == "table" then
						self.run(function()
							frame:SetSelectedModeTabByFrame(tab)
						end)
					end
				end
			end
		end
		return self
	end

	function Sim:closeCharacter()
		local frame = self.G.CharacterFrame
		if frame then
			self.run(function()
				self.G.HideUIPanel(frame)
			end)
			self:advance(0.1)
		end
	end

	function Sim:openObjectiveTracker()
		local frame = self.G.ObjectiveTrackerFrame
		if frame then
			self.run(function()
				frame:Show()
			end)
			self.events.fire("QUEST_LOG_UPDATE")
			self:advance(0.1)
		end
		return frame
	end

	function Sim:closeObjectiveTracker()
		local frame = self.G.ObjectiveTrackerFrame
		if frame then
			self.run(function()
				frame:Hide()
			end)
			self:advance(0.1)
		end
	end

	-- The world map's quest log panel; Camelot has no separate QuestLogFrame.
	function Sim:openQuestLog()
		self:openWorldMap()
		local frame = self.G.WorldMapFrame
		if frame and frame.SetQuestLogPanelShown then
			self.run(function()
				frame:SetQuestLogPanelShown(true)
			end)
			self:advance(0.1)
		end
		return frame
	end

	function Sim:closeQuestLog()
		local frame = self.G.WorldMapFrame
		if frame and frame.SetQuestLogPanelShown then
			self.run(function()
				frame:SetQuestLogPanelShown(false)
			end)
		end
		self:closeWorldMap()
	end

	---------------------------------------------------------------------------
	-- Slash commands, reload and the shared exercise
	---------------------------------------------------------------------------
	-- The slash commands `addon` registered, as each one's first alias: the client keys a command on a
	-- SlashCmdList entry K, with its aliases in SLASH_K1, SLASH_K2, ..., and the taint tracker knows which addon
	-- wrote the first alias, so that global alone says whose command it is.
	function Sim:slashCommands(addon)
		local out = {}
		for key in pairs(self.G.SlashCmdList) do
			local first = self.G["SLASH_" .. key .. "1"]
			if type(first) == "string" and self.taint.globalTaint["SLASH_" .. key .. "1"] == addon then
				out[#out + 1] = first
			end
		end
		table.sort(out)
		return out
	end

	-- The client's own word, from a SLASH_* global the Blizzard UI set (no addon ever wrote it). The chat box consults
	-- its secure commands first, so such a word never reaches an addon's SlashCmdList entry.
	local function clientSlashOwner(G, taint, word)
		for name, value in pairs(G) do
			if
				type(name) == "string"
				and name:sub(1, 6) == "SLASH_"
				and type(value) == "string"
				and not taint.globalTaint[name]
				and value:lower() == word
			then
				return name
			end
		end
	end

	-- Runs a typed slash command the way the chat box does: "/cmd rest" split on the first space, a client command
	-- refused by the word the client owns, otherwise the command found by its aliases in lower case as the client
	-- compares them, and the handler called as fresh input.
	function Sim:slash(text)
		local cmd, rest = text:match("^(%S+)%s*(.*)$")
		local wanted = cmd:lower()
		local G = self.G
		local owner = clientSlashOwner(G, self.taint, wanted)
		if owner then
			error(
				string.format(
					"slash command %s is the client's own (%s), so the chat box runs it before any addon command",
					cmd,
					owner
				),
				2
			)
		end
		for key in pairs(G.SlashCmdList) do
			local n = 1
			while true do
				local alias = G["SLASH_" .. key .. n]
				if alias == nil then
					break
				end
				if type(alias) == "string" and alias:lower() == wanted then
					self:input(G.SlashCmdList[key], rest, G.ChatFrame1EditBox)
					self:advance(0.1)
					return
				end
				n = n + 1
			end
		end
		error("no slash command named " .. cmd, 2)
	end

	-- What /reload does: a fresh client with the same options, the same addons and stubs in the same order, then
	-- a login carrying what this one would have saved.
	function Sim:reload()
		local saved = self:savedState()
		local sim = Sim.new(self.opts)
		for _, entry in ipairs(self.registered) do
			if entry.kind == "stub" then
				sim:stub(entry.name, entry.options)
			else
				sim:addon(entry.dir, entry.name)
			end
		end
		sim:login({ savedVariables = saved })
		return sim
	end

	-- Drives every surface a player reaches without addon-specific knowledge, with the gamepad interface off and
	-- then on: each addon's own slash commands, Professions with every side tab and a selected recipe, the trainer,
	-- merchant tabs, bags, the character panel and its tabs, the objective tracker, the quest log, the world map,
	-- and a target change, a soft-interact change and a binding-set change after each. The same runs in combat for
	-- the commands and map, then again on a fresh client after /reload. Fails on an error either client caused.
	function Sim:exercise(opts)
		opts = opts or {}
		local addons = opts.addons
		if not addons then
			addons = {}
			for _, entry in ipairs(self.registered) do
				if entry.kind == "addon" then
					addons[#addons + 1] = entry.name
				end
			end
		end
		if #self.world.professions == 0 then
			self.world.professions = {
				{
					skillLineID = 164,
					name = "Blacksmithing",
					skill = 30,
					max = 75,
					categories = { { id = 1, name = "Materials" } },
					recipes = { { id = 2660, name = "Rough Sharpening Stone", category = 1, itemID = 2862 } },
				},
			}
		end
		if not self.loggedIn then
			self:login({ savedVariables = opts.savedVariables })
		end
		local bare = {}
		for _, addon in ipairs(addons) do
			for _, command in ipairs(self:slashCommands(addon)) do
				bare[#bare + 1] = command
			end
		end
		for _, command in ipairs(opts.commands or {}) do
			bare[#bare + 1] = command
		end

		local function touch(sim)
			sim:event("PLAYER_TARGET_CHANGED")
			sim:event("PLAYER_SOFT_INTERACT_CHANGED")
			sim:bindingSetChange()
		end

		local function surfaces(sim)
			for _, command in ipairs(bare) do
				sim:slash(command)
				sim:slash(command)
			end
			sim:openProfessions()
			sim:selectProfessionTabs()
			if #sim:recipeRows() > 0 then
				sim:hoverRecipe(1)
			end
			sim:closeProfessions()
			touch(sim)
			sim:openTrainer()
			touch(sim)
			sim:closeTrainer()
			touch(sim)
			sim:openMerchant()
			sim:selectMerchantTabs()
			touch(sim)
			sim:closeMerchant()
			touch(sim)
			sim:openBags()
			touch(sim)
			sim:closeBags()
			touch(sim)
			sim:openCharacter()
			sim:selectCharacterTabs()
			touch(sim)
			sim:closeCharacter()
			touch(sim)
			sim:openObjectiveTracker()
			touch(sim)
			sim:closeObjectiveTracker()
			touch(sim)
			sim:openQuestLog()
			touch(sim)
			sim:closeQuestLog()
			touch(sim)
			sim:openWorldMap()
			sim:zoomMap(2)
			sim:panMap(0.1, 0.1)
			touch(sim)
			sim:closeWorldMap()
			touch(sim)
			sim:pressEscape()
			touch(sim)
		end

		local function combat(sim)
			sim:enterCombat()
			for _, command in ipairs(bare) do
				sim:slash(command)
			end
			sim:openWorldMap()
			sim:closeWorldMap()
			sim:pressEscape()
			sim:leaveCombat()
		end

		for _, gamepad in ipairs({ false, true }) do
			self:setGamepad(gamepad)
			surfaces(self)
			combat(self)
		end
		local sim = self:reload()
		sim.world.professions = self.world.professions
		sim.world.maps = self.world.maps
		sim.world.items = self.world.items
		for _, gamepad in ipairs({ false, true }) do
			sim:setGamepad(gamepad)
			surfaces(sim)
			combat(sim)
		end
		if not opts.allowErrors then
			for _, addon in ipairs(addons) do
				self:expectNoErrors(addon)
				sim:expectNoErrors(addon)
			end
		end
		return sim
	end

	-- Fires a game event as the client does.
	function Sim:event(event, ...)
		self.events.fire(event, ...)
		self:advance(0.05)
	end
end

return M
