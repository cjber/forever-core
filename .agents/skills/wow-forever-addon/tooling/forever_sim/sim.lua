-- forever_sim: a headless WoW: Forever client for scenario tests.
--
--   local Sim = dofile("tools/forever_sim/sim.lua")
--   local sim = Sim.new({ ui = "tools/.cache/wow-ui-source" })
--   sim:addon(".")                         -- the addon under test (its TOC), tainted by its folder name
--   sim:login({ savedVariables = "tests/sim/fixtures/broken.lua" })
--   sim:openProfessions(); sim:hoverRecipe(1)
--   sim:expectNoErrors()
--
-- See README.md for the scenario API, and the design note for what it models and what it cannot.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
package.path = here .. "?.lua;" .. package.path

local Taint = require("taint")
local Secret = require("veil")
local Docs = require("docs")

local Sim = {}
Sim.__index = Sim
Sim.dir = here
require("scenario").install(Sim)

-- Advances the clock: timers, animations and OnUpdate, in steps of at most 50 ms.
function Sim:advance(seconds, step)
	self.step(seconds or 0, step)
	return self
end

-- The Blizzard addons every scenario boots, in load order (each pulls its own dependencies).
Sim.CORE = {
	"Blizzard_SharedXMLBase",
	"Blizzard_SharedXML",
	"Blizzard_SharedXMLGame",
	"Blizzard_FrameXMLBase",
	"Blizzard_UIParent",
	"Blizzard_StaticPopup",
	"Blizzard_UIPanelTemplates",
	"Blizzard_UIParentPanelManager",
	"Blizzard_GameTooltip",
	"Blizzard_ItemButton",
	"Blizzard_FrameXMLUtil",
	"Blizzard_Flyout",
	"Blizzard_POIButton",
	"Blizzard_ObjectAPI",
	"Blizzard_Settings_Shared",
	"Blizzard_GamepadSoftCursor",
	-- Single files from addons too large to boot whole: the templates other UI inherits from them.
	"Blizzard_FrameXML/SecureTemplatesBase.xml",
	"Blizzard_FrameXML/Mainline/NavigationBar.lua",
	"Blizzard_FrameXML/Mainline/NavigationBar.xml",
	"Blizzard_ActionBar/Shared/ActionButtonUtil.lua",
	"Blizzard_ChatFrameBase/Shared/SlashCommands.lua",
	-- The map, quest log and fog-of-war pieces of Blizzard_UIPanels_Game, in its TOC order.
	"Blizzard_UIPanels_Game:PlayerInteractionFrameManager|ScrollingFlatPanel|WarCampaignTemplates|WorldMap"
		.. "|MapLegend|QuestMap|FogOfWar|UnitPosition",
	-- Loaded at startup by the client, and what most Forever addons draw on.
	"Blizzard_WorldMap",
	"Blizzard_ObjectiveTracker",
}

local docsCache = {}

function Sim.new(opts)
	opts = opts or {}
	local sim = setmetatable({}, Sim)
	sim.cache = opts.cache or os.getenv("FOREVER_SIM_CACHE") or "tools/.cache/forever_sim"
	sim.ui = opts.ui or (sim.cache .. "/wow-ui-source")
	sim.build = "1.60.1.70425"
	sim.dataDir = sim.cache .. "/data/" .. sim.build
	sim.verbose = opts.verbose or os.getenv("FOREVER_SIM_VERBOSE") == "1"
	sim.taint = Taint
	sim.gaps = {}
	-- The client's legacy LE_* constants are native and undocumented: client code reading one gets a distinct
	-- number (recorded in sim.gaps); addon code gets nil.
	local leValue = 200000
	Taint.onMissingGlobal = function(k)
		if Taint.current or type(k) ~= "string" or not k:match("^LE_") then
			return nil
		end
		leValue = leValue + 1
		sim.G[k] = leValue
		sim.gaps[k] = true
		return leValue
	end
	Taint.current = nil
	Taint.globalTaint = {}
	Taint.addonFolders = {}
	Taint.listeners = { taint = {}, untaint = {} }
	sim.secret = Secret
	Secret.taintedBy = function()
		return Taint.current
	end
	docsCache[sim.ui] = docsCache[sim.ui] or Docs.load(sim.ui)
	sim.docs = docsCache[sim.ui]
	sim.impl = {}
	sim.started = os.clock()
	require("client").build(sim)
	require("natives").build(sim)
	require("stubgen").build(sim)
	sim.locale = opts.locale or "enUS"
	require("clientdata").build(sim)
	require("widgets").build(sim)
	require("templates").build(sim)
	require("tooltip").build(sim)
	require("world").build(sim)
	sim.widgets.finalize()
	sim.createRoots()
	require("loader").build(sim)
	require("watch").build(sim)
	require("layout").build(sim)
	-- Addon functions report themselves (instrument.lua); FOREVER_SIM_HOOK=1 also watches every call, slowly.
	local mark = function(addon)
		if Taint.current ~= addon then
			Taint.set(addon)
		end
	end
	rawset(sim.env, "__fst", mark)
	sim.G.__fst = mark
	if opts.hook or os.getenv("FOREVER_SIM_HOOK") == "1" then
		Taint.attach()
	end
	local rawLoadstring = loadstring
	sim.G.loadstring = function(code, name)
		local addon = Taint.current
		if addon and type(code) == "string" then
			code = require("instrument").rewrite(code, addon)
		end
		local chunk, err = rawLoadstring(code, name)
		if chunk then
			setfenv(chunk, sim.env)
		end
		return chunk, err
	end
	for _, name in ipairs(opts.blizzard or Sim.CORE) do
		sim:loadBlizzard(name)
	end
	sim.createChat()
	sim.bootSeconds = os.clock() - sim.started
	return sim
end

function Sim:loadBlizzard(name)
	return self.loader.blizzard(name)
end

-- Registers an addon under test (a folder holding its TOC). `name` defaults to the TOC's name.
function Sim:addon(dir, name)
	return self.loader.addon(dir, name)
end

-- Adds a third-party stand-in from stubs/ (Questie, TomTom, Auctionator, Polestar), with its options; it loads
-- with the addons at login and runs tainted by its own name, as the real addon would.
function Sim:stub(name, options)
	self.G.FOREVER_SIM_STUBS = self.G.FOREVER_SIM_STUBS or {}
	self.G.FOREVER_SIM_STUBS[name] = options or {}
	self.taint.globalTaint.FOREVER_SIM_STUBS = nil
	return self.loader.addon(Sim.dir .. "stubs/" .. name, name)
end

-- Runs Lua as the given addon would (its chunk name), for test stubs of third-party addons.
function Sim:runAs(addon, code, ...)
	self.taint.registerAddon(addon, addon)
	local chunk = assert(self.templates.compile(code, addon .. "/stub.lua"))
	return self.run(chunk, ...)
end

function Sim:global(name)
	return self.G[name]
end

-- Errors since the last call (or all), as { message, traceback, taint }.
function Sim:takeErrors()
	local errors = self.errors
	self.errors = {}
	return errors
end

local function describe(errors)
	local out = {}
	for _, e in ipairs(errors) do
		out[#out + 1] = e.message .. (e.traceback ~= "" and ("\n" .. e.traceback) or "")
	end
	return table.concat(out, "\n\n")
end
Sim.describe = describe

-- Fails unless no error was reported (optionally: none attributed to `addon`).
function Sim:expectNoErrors(addon)
	local found = {}
	for _, e in ipairs(self.errors) do
		if not addon or e.taint == addon or tostring(e.message):find(addon, 1, true) then
			found[#found + 1] = e
		end
	end
	if #found > 0 then
		error("expected no errors, got " .. #found .. ":\n" .. describe(found), 2)
	end
end

-- Fails unless an error matching `pattern` (plain text) was reported; returns it.
function Sim:expectError(text)
	for _, e in ipairs(self.errors) do
		if tostring(e.message):find(text, 1, true) then
			return e
		end
	end
	error("expected an error containing: " .. text .. "\ngot:\n" .. describe(self.errors), 2)
end

return Sim
