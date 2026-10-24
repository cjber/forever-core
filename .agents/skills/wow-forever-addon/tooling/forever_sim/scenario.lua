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
		self.events.fire("PLAYER_REGEN_DISABLED")
		self.inCombat = true
		self:advance(0.1)
	end

	function Sim:leaveCombat()
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
		local G = self.G
		self.run(function()
			G.C_AddOns.LoadAddOn("Blizzard_WorldMap")
		end)
		self:showPanel(G.WorldMapFrame)
		if mapID then
			self.run(function()
				G.WorldMapFrame:SetMapID(mapID)
			end)
		end
		self:advance(0.2)
		return G.WorldMapFrame
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

	-- Fires a game event as the client does.
	function Sim:event(event, ...)
		self.events.fire(event, ...)
		self:advance(0.05)
	end
end

return M
