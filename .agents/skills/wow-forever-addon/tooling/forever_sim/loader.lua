-- TOC loading for Blizzard's addons (from the pinned UI source) and the addons under test: the Forever client's
-- game type (camelot, in the mainline family), [Family]/[Game] folders, load conditions, dependencies, saved
-- variables and ADDON_LOADED.
local M = {}

M.GAME_TYPES = { camelot = true, mainline = true }

-- Heavy Blizzard addons a dependency pulls in whose frames no scenario uses (action bars, chat, unit frames,
-- the shop). Skipped as dependencies, to keep a scenario's boot in seconds; a scenario can still load one
-- by name. Listed in the design note's fidelity limits.
M.SKIP_DEPS = {}
for _, name in ipairs({
	"Blizzard_FrameXML",
	"Blizzard_UIPanels_Game",
	"Blizzard_ActionBar",
	"Blizzard_ActionStatus",
	"Blizzard_UnitFrame",
	"Blizzard_ChatFrame",
	"Blizzard_ChatFrameBase",
	"Blizzard_RaidFrame",
	"Blizzard_CatalogShop",
	"Blizzard_CatalogShopRefundFlow",
	"Blizzard_CatalogShopSharedTemplates",
	"Blizzard_CatalogShopSharedUtil",
	"Blizzard_CatalogShopTopUpFlow",
	"Blizzard_StoreUI",
	"Blizzard_EnvironmentCleanup",
	"Blizzard_RestrictedAddOnEnvironment",
	"Blizzard_GuildRename",
	"Blizzard_SplashFrame",
	"Blizzard_Statistics",
	"Blizzard_ZoneAbility",
	"Blizzard_IME",
}) do
	M.SKIP_DEPS[name] = true
end
M.FAMILY, M.GAME = "Mainline", "Camelot"

local function readFile(path)
	local f = io.open(path, "rb")
	if not f then
		return nil
	end
	local text = f:read("*a")
	f:close()
	return text
end

local function exists(path)
	local f = io.open(path, "rb")
	if f then
		f:close()
		return true
	end
	return false
end

local function tokens(list)
	local out = {}
	for t in list:gmatch("[^,%s]+") do
		out[#out + 1] = t:lower()
	end
	return out
end

-- True when a TOC line's bracketed conditions allow the Forever client.
function M.allowed(conditions)
	for kind, list in conditions:gmatch("%[(%a+)%s+([^%]]*)%]") do
		if kind == "AllowLoadGameType" then
			local ok = false
			for _, t in ipairs(tokens(list)) do
				if M.GAME_TYPES[t] then
					ok = true
				end
			end
			if not ok then
				return false
			end
		elseif kind == "ExcludeLoadGameType" then
			for _, t in ipairs(tokens(list)) do
				if t == "camelot" then
					return false
				end
			end
		elseif kind == "AllowLoad" then
			local l = list:lower()
			if l == "glue" then
				return false
			end
		elseif kind == "AllowLoadEnvironment" then
			-- Global and Restricted environments both load in the game.
			local _ = list
		end
	end
	return true
end

-- Parses a TOC: { metadata = {key = value}, files = { relative paths }, deps = {...} }.
function M.parseToc(text)
	local toc = { metadata = {}, files = {}, deps = {}, optional = {} }
	for raw in text:gmatch("[^\r\n]+") do
		local line = raw:gsub("^%s+", ""):gsub("%s+$", "")
		local key, value = line:match("^##%s*([^:]+):%s*(.-)%s*$")
		if key then
			local conditions = value:match("(%[.*%])%s*$") or ""
			local plainValue = value:gsub("%s*%[.*%]%s*$", "")
			if M.allowed(conditions) then
				toc.metadata[key] = toc.metadata[key] and (toc.metadata[key] .. ", " .. plainValue) or plainValue
				local k = key:lower()
				if
					k == "dependencies"
					or k == "requireddeps"
					or k == "requireddep"
					or k == "dep"
					or k:match("^dep")
				then
					for d in plainValue:gmatch("[^,%s]+") do
						toc.deps[#toc.deps + 1] = d
					end
				elseif k == "optionaldeps" or k == "optionaldependencies" then
					for d in plainValue:gmatch("[^,%s]+") do
						toc.optional[#toc.optional + 1] = d
					end
				end
			end
		elseif line ~= "" and not line:match("^#") then
			local file, conditions = line:match("^(%S+)%s*(.*)$")
			if file and M.allowed(conditions or "") then
				file = file:gsub("%[Family%]", M.FAMILY):gsub("%[Game%]", M.GAME):gsub("\\", "/")
				toc.files[#toc.files + 1] = file
			end
		end
	end
	return toc
end

function M.build(sim)
	local L = { loaded = {}, loading = {}, addons = {}, order = {} }
	sim.loader = L

	local function blizzardDir(name)
		return sim.ui .. "/Interface/AddOns/" .. name
	end

	local function findToc(dir, name)
		for _, suffix in ipairs({ "_" .. M.GAME, "_" .. M.FAMILY, "_Vanilla", "" }) do
			local path = dir .. "/" .. name .. suffix .. ".toc"
			if exists(path) then
				return path
			end
		end
		-- A TOC named differently from its folder (Blizzard_BarberShopUI).
		local p = io.popen('ls "' .. dir .. '" 2>/dev/null')
		if p then
			for f in p:lines() do
				if f:match("%.toc$") then
					p:close()
					return dir .. "/" .. f
				end
			end
			p:close()
		end
	end

	local function loadFiles(dir, folder, toc, ns)
		for _, rel in ipairs(toc.files) do
			local path = dir .. "/" .. rel
			if rel:match("%.lua$") then
				sim.templates.loadLua(path, folder .. "/" .. rel, folder, ns)
			elseif rel:match("%.xml$") then
				sim.templates.loadXML(path, folder, rel, folder, ns)
			end
		end
	end

	-- Loads a Blizzard addon from the UI source with its dependencies; returns false if it cannot be found
	-- or is not for this client.
	function L.blizzard(name)
		if L.loaded[name] or L.loading[name] then
			return true
		end
		local subset, patterns = name:match("^([^:/]+):(.+)$")
		if subset then
			-- Only the TOC entries of a Blizzard addon whose path matches one of the |-separated words.
			local dir = blizzardDir(subset)
			local toc = M.parseToc(readFile(findToc(dir, subset)))
			local files = {}
			for _, rel in ipairs(toc.files) do
				for word in patterns:gmatch("[^|]+") do
					if rel:find(word, 1, true) then
						files[#files + 1] = rel
						break
					end
				end
			end
			loadFiles(dir, subset, { files = files }, {})
			L.loaded[name] = { blizzard = true, seconds = 0, partial = true }
			return true
		end
		local addon, rel = name:match("^([^/]+)/(.+)$")
		if addon then
			-- One file of a Blizzard addon.
			local path = blizzardDir(addon) .. "/" .. rel
			if rel:match("%.xml$") then
				sim.templates.loadXML(path, addon, rel, addon, {})
			else
				sim.templates.loadLua(path, addon .. "/" .. rel, addon, {})
			end
			L.loaded[name] = { blizzard = true, seconds = 0, partial = true }
			return true
		end
		local dir = blizzardDir(name)
		local tocPath = findToc(dir, name)
		if not tocPath then
			return false
		end
		local toc = M.parseToc(readFile(tocPath))
		local gameTypes = toc.metadata.AllowLoadGameType
		if gameTypes then
			local ok = false
			for _, t in ipairs(tokens(gameTypes)) do
				if M.GAME_TYPES[t] then
					ok = true
				end
			end
			if not ok then
				return false
			end
		end
		if toc.metadata.AllowLoad and toc.metadata.AllowLoad:lower() == "glue" then
			return false
		end
		L.loading[name] = true
		for _, dep in ipairs(toc.deps) do
			if M.SKIP_DEPS[dep] then
				sim.gaps["skipped dependency " .. dep .. " of " .. name] = true
			else
				L.blizzard(dep)
			end
		end
		local started = os.clock()
		loadFiles(dir, name, toc, {})
		L.loading[name] = nil
		L.loaded[name] = { blizzard = true, seconds = os.clock() - started, toc = toc }
		table.insert(L.order, name)
		sim.events.queue("ADDON_LOADED", name, false)
		sim.events.flush()
		return true
	end

	-- The Blizzard addons the client loads at startup: every one for this client that is not load-on-demand,
	-- LoadFirst ones first, each after its dependencies.
	function L.startupList()
		local names = {}
		local p = io.popen('ls "' .. sim.ui .. '/Interface/AddOns"')
		for name in p:lines() do
			names[#names + 1] = name
		end
		p:close()
		local first, rest = {}, {}
		for _, name in ipairs(names) do
			local dir = blizzardDir(name)
			local tocPath = findToc(dir, name)
			local text = tocPath and readFile(tocPath)
			if text then
				local toc = M.parseToc(text)
				local md = toc.metadata
				local ok = md.LoadOnDemand ~= "1"
				local allowLoad = (md.AllowLoad or "both"):lower()
				if allowLoad == "glue" then
					ok = false
				end
				if md.AllowLoadGameType then
					local any = false
					for _, t in ipairs(tokens(md.AllowLoadGameType)) do
						if M.GAME_TYPES[t] then
							any = true
						end
					end
					ok = ok and any
				end
				if (md.DefaultState or ""):lower() == "disabled" then
					ok = false
				end
				if name:match("^Blizzard_APIDocumentation") or name:match("Glue") or name == "Blizzard_Deprecated" then
					ok = false
				end
				if ok then
					table.insert(md.LoadFirst == "1" and first or rest, name)
				end
			end
		end
		local out = {}
		for _, n in ipairs(first) do
			out[#out + 1] = n
		end
		for _, n in ipairs(rest) do
			out[#out + 1] = n
		end
		return out
	end

	-- Registers an addon under test: `dir` holds `<Name>.toc`; its files run tainted by Name.
	function L.addon(dir, name)
		if not name then
			local p = io.popen('ls "' .. dir .. '"')
			for f in p:lines() do
				if f:match("%.toc$") and not name then
					name = f:gsub("%.toc$", ""):gsub("_%a+$", function(s)
						return (s == "_Mainline" or s == "_Vanilla" or s == "_Classic") and "" or s
					end)
				end
			end
			p:close()
		end
		local tocPath = findToc(dir, name)
		assert(tocPath, "no TOC for " .. tostring(name) .. " in " .. dir)
		local toc = M.parseToc(readFile(tocPath))
		sim.taint.registerAddon(name, name)
		local entry = { name = name, dir = dir, toc = toc, ns = {} }
		L.addons[name] = entry
		L.addons[#L.addons + 1] = entry
		return entry
	end

	-- Loads a registered addon's files (with its saved variables in place) and fires its ADDON_LOADED.
	function L.load(name)
		local entry = L.addons[name]
		if not entry or entry.loaded then
			return entry ~= nil
		end
		entry.loading = true
		for _, list in ipairs({ entry.toc.deps, entry.toc.optional }) do
			for _, dep in ipairs(list) do
				if L.addons[dep] and not L.addons[dep].loading then
					L.load(dep)
				end
			end
		end
		entry.loading = nil
		local started = os.clock()
		loadFiles(entry.dir, name, entry.toc, entry.ns)
		entry.loaded = true
		entry.seconds = os.clock() - started
		sim.events.queue("ADDON_LOADED", name, false)
		sim.events.flush()
		return true
	end

	function L.savedVariables(entry)
		local out = {}
		for _, key in ipairs({ "SavedVariables", "SavedVariablesPerCharacter" }) do
			for v in (entry.toc.metadata[key] or ""):gmatch("[^,%s]+") do
				out[#out + 1] = v
			end
		end
		return out
	end

	return L
end

return M
