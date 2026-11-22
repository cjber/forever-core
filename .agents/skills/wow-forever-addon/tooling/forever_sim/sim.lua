-- forever_sim: a simulated WoW: Forever client API for scenario tests.
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
	-- FriendsFrame reads the social utility mixins even when the full social panel is not loaded.
	"Blizzard_SocialUIShared/SocialUIUtil.lua",
	"Blizzard_UIParent",
	"Blizzard_UIErrorsFrame",
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
	-- Single files from addons too large to boot whole: the templates other UI inherits from them (the secure
	-- templates and the deprecated settings templates), and the alert frames the client loads at startup
	-- (AlertFrame is a global addons anchor to).
	"Blizzard_FrameXML/SecureTemplatesBase.xml",
	"Blizzard_FrameXML/SecureTemplates.lua",
	"Blizzard_FrameXML/SecureTemplates.xml",
	"Blizzard_RestrictedAddOnEnvironment/SecureStateDriver.lua",
	"Blizzard_FrameXML/DeprecatedTemplates.xml",
	"Blizzard_FrameXML/Mainline/AlertFrames.lua",
	"Blizzard_FrameXML/Mainline/AlertFrames.xml",
	"Blizzard_FrameXML/Mainline/AlertFrameSystems.lua",
	"Blizzard_FrameXML/Camelot/AlertFrameSystemsOverride.lua",
	"Blizzard_FrameXML/Mainline/AlertFrameSystems.xml",
	-- SplashFrame's OnLoad disables alerts through AlertFrame, so it loads after the alert frames it names.
	"Blizzard_SplashFrame",
	"Blizzard_FrameXML/Mainline/NavigationBar.lua",
	"Blizzard_FrameXML/Mainline/NavigationBar.xml",
	-- The quest session dialog the quest log updates when it is shown, loaded by the client at startup.
	"Blizzard_FrameXML/QuestSession.lua",
	"Blizzard_FrameXML/QuestSession.xml",
	"Blizzard_ActionBar/Shared/ActionButtonUtil.lua",
	-- ActionButtonTemplate inherits QuickKeybindButtonTemplate, which its own addon declares in one XML file.
	-- Load that file rather than the addon, whose SettingsDefinitions_Frame dependency is not part of this boot.
	"Blizzard_QuickKeybind/QuickKeybind.xml",
	-- ActionButton's UpdateSpellAlert calls ActionButtonSpellAlertManager, defined beside its button code.
	"Blizzard_ActionBar/Shared/ActionButtonSpellAlerts.lua",
	"Blizzard_ActionBar/Shared/ActionButtonSpellAlerts.xml",
	"Blizzard_ActionBar/Shared/ActionButton.lua",
	"Blizzard_ActionBar/Shared/ActionButtonComponentTemplate.xml",
	"Blizzard_ActionBar/Mainline/ActionButtonTemplate.xml",
	-- PetActionButtonMixin, which the gamepad pet buttons mix in through GamepadActionBarPetButtonMixin.
	"Blizzard_ActionBar/Shared/PetActionBar.lua",
	-- SpellFlyoutMixin and its popup button mixin, which the gamepad flyouts mix in.
	"Blizzard_ActionBar/Shared/SpellFlyout.lua",
	"Blizzard_ActionBar/Shared/SpellFlyout.xml",
	-- The Escape handler registry Blizzard_ActionBar loads at startup: addons register into its file-local list.
	"Blizzard_GameMenuEsc",
	-- The Escape menu the client loads at startup: gamepad legend and radial code read GameMenuFrame:IsShown().
	"Blizzard_GameMenu",
	-- The gamepad action bars are real: they are where UpdateInteractIcons makes its protected call. The action
	-- bar templates above supply the buttons they inherit; the gamepad UI's own setup registers the target and
	-- soft-interact callbacks and reacts to binding-set changes.
	"Blizzard_GamepadSharedUtility",
	"Blizzard_GamepadSmartNavigation",
	"Blizzard_GamepadActionBars",
	-- Action-bar click handlers consume modifiers through the native targeting controller.
	"Blizzard_GamepadTargeting/TargetLogic.lua",
	-- Native objective-tracker clicks offer quest chat links before opening quest details.
	"Blizzard_ChatFrameBase/Shared/ChatFrameConstants.lua",
	"Blizzard_ChatFrameBase/Shared/ChatTypeInfoConstants.lua",
	"Blizzard_ChatFrameBase/Shared/ChatFrameUtil.lua",
	"Blizzard_ChatFrameBase/Shared/SlashCommands.lua",
	-- The map, quest log and fog-of-war pieces of Blizzard_UIPanels_Game, in its TOC order, plus the quest frame
	-- the quest log's OnHide closes the quest portrait through.
	-- ContainerFrame bag positioning reads BankFrame even when the bank is closed.
	"Blizzard_SharedXML/ClassColors.lua",
	"Blizzard_FrameXML/EquipmentFlyout.lua",
	"Blizzard_FrameXML/EquipmentFlyout.xml",
	-- MerchantFrame's BAG_UPDATE closes this split frame, open or not.
	"Blizzard_FrameXML/Mainline/StackSplitFrame.lua",
	"Blizzard_FrameXML/Mainline/StackSplitFrame.xml",
	-- QuestFrame's OnShow reads the tutorial frame's id.
	"Blizzard_FrameXML/Mainline/TutorialFrame.lua",
	"Blizzard_FrameXML/Mainline/TutorialFrame.xml",
	"Blizzard_TextStatusBar",
	"Blizzard_StatusTrackingBar",
	"Blizzard_UIPanels_Game:PlayerInteractionFrameManager|ScrollingFlatPanel|WarCampaignTemplates|WorldMap"
		.. "|MapLegend|QuestMap|FogOfWar|UnitPosition|CastingBarFrame|ContainerFrame|Bank"
		.. "|QuestFrameTemplates|FriendshipStatusBar|QuestFrame|QuestInfo|DressUpFrames|CharacterFrame"
		.. "|AzeritePaperDoll|PaperDoll|ReputationFrame|MerchantFrame|SkillsFrame",
	-- Loaded at startup by the client, and what most Forever addons draw on.
	-- EncounterBar lives in Blizzard_UnitFrame's UnitPowerBarAlt files; UIWidgets' power-bar layout anchors to it.
	"Blizzard_UnitFrame/Mainline/UnitPowerBarAlt.lua",
	"Blizzard_UnitFrame/Mainline/UnitPowerBarAlt.xml",
	-- Non-LoadOnDemand startup addon: ContainerFrame initializes its token tracker on this ADDON_LOADED.
	"Blizzard_TokenUI",
	"Blizzard_WorldMap",
	-- Bonus objective QUEST_ACCEPTED events display banners through this native manager.
	"Blizzard_FrameXML/Mainline/ZoneText.lua",
	"Blizzard_FrameXML/Mainline/ZoneText.xml",
	"Blizzard_FrameXML/TopBannerManager.lua",
	"Blizzard_ObjectiveTracker",
	"Blizzard_ContentTracking",
	"Blizzard_TrainerUI",
	"Blizzard_RaidWarning/RaidWarningUtil.lua",
	"Blizzard_RaidWarning/RaidWarning.lua",
	"Blizzard_RaidWarning/RaidWarning.xml",
	"Blizzard_NamePlates/Blizzard_NamePlateConstants.lua",
	"Blizzard_NamePlates/Blizzard_NamePlateFrameOptions.lua",
	"Blizzard_NamePlates/Blizzard_NamePlates.lua",
	"Blizzard_NamePlates/Blizzard_NamePlates.xml",
}

local docsCache = {}

function Sim.new(opts)
	opts = opts or {}
	local sim = setmetatable({}, Sim)
	-- Kept so Sim:reload builds the same client; registered holds the addons and stubs in registration order.
	sim.opts = opts
	sim.registered = {}
	sim.cache = opts.cache or os.getenv("FOREVER_SIM_CACHE") or "tools/.cache/forever_sim"
	sim.ui = opts.ui or (sim.cache .. "/wow-ui-source")
	sim.build = "1.60.1.70425"
	sim.dataDir = sim.cache .. "/data/" .. sim.build
	sim.verbose = opts.verbose or os.getenv("FOREVER_SIM_VERBOSE") == "1"
	sim.taint = Taint
	sim.gaps = {}
	-- True only while a hardware input's synchronous call runs, so a hardware-event restriction can refuse a call
	-- made from a timer or an event.
	sim.hardwareInput = false
	-- The client's legacy LE_* constants are native and undocumented: client code reading one gets a distinct
	-- number (recorded in sim.gaps), including when the reader runs tainted.
	local leValue = 200000
	Taint.onMissingGlobal = function(k)
		if type(k) ~= "string" or not k:match("^LE_") then
			return nil
		end
		leValue = leValue + 1
		sim.G[k] = leValue
		sim.gaps[k] = true
		return leValue
	end
	Taint.reset()
	sim.secret = Secret
	Secret.taintedBy = function()
		return Taint.current
	end
	docsCache[sim.ui] = docsCache[sim.ui] or Docs.load(sim.ui)
	sim.docs = docsCache[sim.ui]
	sim.docs.restrictions()
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
			Taint.set(addon, addon and { addon = addon, kind = "execution" } or nil)
		end
	end
	rawset(sim.env, "__fst", mark)
	sim.G.__fst = mark
	if opts.hook or os.getenv("FOREVER_SIM_HOOK") == "1" then
		Taint.attach()
	end
	-- An addon's runtime chunk is instrumented with the marker bound as a local of a wrapper, so the chunk keeps it
	-- under any environment the addon gives it (a data parser's setfenv(chunk, {})). The chunk name defaults to the
	-- addon's own code, as the client's does. The field helpers are locals for the same reason.
	local rawLoadstring = loadstring
	local Instrument = require("instrument")
	local bind = "local __fsi_get, __fsi_set, __fsi_callm, __fsi_ctor, "
		.. Instrument.MARKER
		.. " = ...; return function(...) "
	sim.G.loadstring = function(code, name)
		local addon = Taint.current
		local chunk, err
		if type(code) == "string" and code:sub(1, 1) ~= "\27" then
			if addon then
				local wrapper
				wrapper, err = rawLoadstring(bind .. Instrument.rewrite(code, addon) .. "\nend", name or code)
				chunk = wrapper and wrapper(Taint.fieldGet, Taint.fieldSet, Taint.methodCall, Taint.constructor, mark)
			else
				chunk, err = rawLoadstring(Instrument.rewrite(code, nil), name or code)
			end
		else
			chunk, err = rawLoadstring(code, name)
		end
		if chunk then
			setfenv(chunk, sim.env)
		end
		return chunk, err
	end
	for _, name in ipairs(opts.blizzard or Sim.CORE) do
		sim:loadBlizzard(name)
	end
	-- Unit frames are omitted from this boot, but the character panel uses their text-status-bar contract.
	if sim.G.TextStatusBarMixin then
		for _, bar in ipairs({
			sim.G.PlayerFrameHealthBar,
			sim.G.PlayerFrameManaBar,
			sim.G.PlayerFrameAlternatePowerBar,
			sim.G.PetFrameHealthBar,
			sim.G.PetFrameManaBar,
		}) do
			sim.G.Mixin(bar, sim.G.TextStatusBarMixin)
		end
	end
	-- The raid warning anchors below Blizzard_BuffFrame's DeadlyDebuffFrame, which needs the omitted unit frames: the
	-- hidden frame it reads stands in for it.
	if sim.G.RaidWarningFrame and not sim.G.DeadlyDebuffFrame then
		sim.G.CreateFrame("Frame", "DeadlyDebuffFrame", sim.G.UIParent):Hide()
	end
	-- The full Edit Mode event updates systems whose frames are outside the simulated boot (buffs, cast bar,
	-- and action bars). Model the tracker anchor from the event payload and keep the other native events intact.
	local editMode, tracker = sim.G.EditModeManagerFrame, sim.G.ObjectiveTrackerFrame
	if editMode and tracker then
		local onEvent = editMode:GetScript("OnEvent")
		editMode:SetScript("OnEvent", function(frame, event, ...)
			if event ~= "EDIT_MODE_LAYOUTS_UPDATED" then
				return onEvent(frame, event, ...)
			end
			-- A notification without a payload leaves the scenario's current tracker placement in place.
			local layoutInfo = ...
			if not layoutInfo then
				return
			end
			-- As UpdateLayoutInfo does: the manager keeps the payload, its layouts the presets then the saved ones.
			local layouts = sim.G.EditModePresetLayoutManager:GetCopyOfPresetLayouts()
			for _, saved in ipairs(layoutInfo.layouts or {}) do
				layouts[#layouts + 1] = saved
			end
			layoutInfo.layouts = layouts
			frame.layoutInfo = layoutInfo
			local layout = layouts[layoutInfo.activeLayout]
			if not layout then
				return
			end
			for _, system in ipairs(layout.systems) do
				if system.system == tracker.system then
					local scale = tracker:GetScale()
					tracker:ClearAllPoints()
					for _, anchor in ipairs({ system.anchorInfo, system.anchorInfo2 }) do
						tracker:SetPoint(
							anchor.point,
							anchor.relativeTo,
							anchor.relativePoint,
							anchor.offsetX / scale,
							anchor.offsetY / scale
						)
					end
					break
				end
			end
		end)
	end
	sim.events.watchRegistry(rawget(sim.G, "EventRegistry"))
	sim.loader.bootstrap()
	sim.createChat()
	sim.bootSeconds = os.clock() - sim.started
	return sim
end

function Sim:loadBlizzard(name)
	return self.loader.blizzard(name)
end

-- Registers an addon under test (a folder holding its TOC). `name` defaults to the TOC's name.
function Sim:addon(dir, name)
	local entry = self.loader.addon(dir, name)
	self.registered[#self.registered + 1] = { kind = "addon", dir = dir, name = entry.name }
	return entry
end

-- The ForeverCore checkout a scenario loads beside the repository's addon (at `root`, a path ending in a slash; the
-- working directory by default) ($FOREVER_CORE, else the sibling
-- ../forever-core), or nil when the addon in the working directory carries its own core: a packaged build embeds it
-- under Libs/ForeverCore (the embed step writes Libs/ForeverCore/bundle.json), which is what a player without the
-- standalone runs. An unpackaged checkout beside it reads as an older standalone (@project-version@), so the
-- loader's outdated notice would be the run's subject instead of the addon.
function Sim.foreverCoreDir(root)
	local bundle = io.open((root or "") .. "Libs/ForeverCore/bundle.json", "rb")
	if bundle then
		bundle:close()
		return nil
	end
	local directory = os.getenv("FOREVER_CORE")
	if directory == nil or directory == "" then
		directory = "../forever-core"
	end
	return directory
end

-- Registers the ForeverCore checkout (Sim.foreverCoreDir) before login, unless the addon embeds its own core.
function Sim:foreverCore()
	local directory = Sim.foreverCoreDir()
	if directory then
		return self:addon(directory, "ForeverCore")
	end
end

-- Adds a third-party stand-in from stubs/ (Questie, TomTom, Auctionator, Polestar), with its options; it loads
-- with the addons at login and runs tainted by its own name, as the real addon would.
function Sim:stub(name, options)
	self.G.FOREVER_SIM_STUBS = self.G.FOREVER_SIM_STUBS or {}
	self.G.FOREVER_SIM_STUBS[name] = options or {}
	self.taint.globalTaint.FOREVER_SIM_STUBS = nil
	self.registered[#self.registered + 1] = { kind = "stub", name = name, options = options or {} }
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

-- One entry per distinct taint cause (field, writer line, origin line), with the number of occurrences; every
-- other error keeps its own entry.
local function describe(errors)
	local out, groups, order = {}, {}, {}
	for _, e in ipairs(errors) do
		local key = Taint.causeKey(e.origin)
		if key then
			local group = groups[key]
			if not group then
				group = { entry = e, count = 0 }
				groups[key] = group
				order[#order + 1] = group
			end
			group.count = group.count + 1
		else
			order[#order + 1] = { entry = e, count = 0 }
		end
	end
	for _, group in ipairs(order) do
		local e = group.entry
		local text = e.message .. (e.traceback ~= "" and ("\n" .. e.traceback) or "")
		if group.count > 0 then
			text = string.format("%dx %s", group.count, text)
		end
		out[#out + 1] = text
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

-- The waits that can never call back (client.lua, E.late): registrations for PLAYER_LOGIN or VARIABLES_LOADED made
-- after the event fired and still pending, optionally only `addon`'s, as { addon, event, kind, site }.
function Sim:strandedWaits(addon)
	local out = {}
	for _, kind in ipairs({ "frame", "callback" }) do
		for _, waits in pairs(self.events.late[kind]) do
			for _, wait in pairs(waits) do
				if not addon or wait.addon == addon then
					out[#out + 1] = wait
				end
			end
		end
	end
	table.sort(out, function(a, b)
		local sa, sb = a.site or {}, b.site or {}
		return string.format("%s:%08d:%s", tostring(sa.file), sa.line or 0, a.event)
			< string.format("%s:%08d:%s", tostring(sb.file), sb.line or 0, b.event)
	end)
	return out
end

-- Fails when `addon` (any addon when nil) waits for a loading event that already fired: its files ran after it,
-- as they do when a packaged ForeverCore is elected at PLAYER_LOGIN. Wait with ns.AfterEvents instead.
function Sim:expectNoStrandedWaits(addon)
	local waits = self:strandedWaits(addon)
	if #waits > 0 then
		local lines = {}
		for _, wait in ipairs(waits) do
			local site = wait.site or {}
			lines[#lines + 1] = string.format(
				"%s:%s: %s waits for %s, which already fired (%s); it never calls back. Use ns.AfterEvents",
				tostring(site.file or "?"),
				tostring(site.line or "?"),
				tostring(wait.addon),
				wait.event,
				wait.kind == "frame" and "a frame registered for it" or "an EventRegistry callback"
			)
		end
		error("expected no stranded waits, got " .. #waits .. ":\n" .. table.concat(lines, "\n"), 2)
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
