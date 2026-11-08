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

	-- Runs a typed slash command the way the chat box does: "/cmd rest" split on the first space, the command
	-- found by its aliases in lower case as the client compares them, and the handler called as fresh input.
	function Sim:slash(text)
		local cmd, rest = text:match("^(%S+)%s*(.*)$")
		local wanted = cmd:lower()
		local G = self.G
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

	-- Drives every surface a player reaches without addon-specific knowledge: each addon's own slash commands,
	-- bare (twice, so a toggle opens then closes) and then the scenario's own, the world map, the same in
	-- combat, and the commands and map again on a fresh client after /reload. Fails on an error either client
	-- caused, unless opts.allowErrors. Returns the reloaded client.
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
		if not self.loggedIn then
			self:login({ savedVariables = opts.savedVariables })
		end
		local bare = {}
		for _, addon in ipairs(addons) do
			for _, command in ipairs(self:slashCommands(addon)) do
				bare[#bare + 1] = command
			end
		end
		for _, command in ipairs(bare) do
			self:slash(command)
			self:slash(command)
		end
		for _, command in ipairs(opts.commands or {}) do
			self:slash(command)
		end
		self:openWorldMap()
		self:zoomMap(2)
		self:panMap(0.1, 0.1)
		self:closeWorldMap()
		self:enterCombat()
		for _, command in ipairs(bare) do
			self:slash(command)
		end
		self:openWorldMap()
		self:closeWorldMap()
		self:leaveCombat()
		local sim = self:reload()
		for _, command in ipairs(bare) do
			sim:slash(command)
		end
		sim:openWorldMap()
		sim:closeWorldMap()
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
