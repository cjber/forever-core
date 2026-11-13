std = "lua51"
max_line_length = 120
exclude_files = { ".agents/**", ".claude/**", "docs/**", "tools/.cache/**", ".types/**", "types/**", ".release/**", "Nav/**" , ".bugpatrol/runs/**", ".speedpatrol/runs/**", ".sloppatrol/runs/**"}
globals = {
	"EventUtil",
	-- UI/TrackerHost.lua: the companion tracker registry a store build's vendored host still uses.
	"ForeverTrackerHost",
	"ShortestPathForever",
	"ShortestPathForeverCharDB",
	"ShortestPathForeverDB",
	"ShortestPathForever_OnAddonCompartmentClick",
	"TomTom",
	"SLASH_SHORTESTPATHFOREVER1",
	"SLASH_SHORTESTPATHFOREVER2",
	"SlashCmdList",
	"bit",
	"SLASH_SPFNEAR1",
	"SLASH_SHORTESTPATHFOREVERWAY1",
}
read_globals = {
	"IsAltKeyDown",
	"CreateFramePoolCollection",
	"C_XMLUtil",
	"Clamp",
	"GREEN_FONT_COLOR",
	"CreateSettingsButtonInitializer",
	"Lerp",
	"Menu",
	"MenuUtil",
	"Saturate",
	"C_InputInterfaceStyle",
	"C_Map",
	"C_SettingsUtil",
	"C_Texture",
	"C_Timer",
	"date",
	"CreateFrame",
	"CreateFromMixins",
	"CreateVector2D",
	"Enum",
	"GameTooltip",
	"GameTooltip_Hide",
	"GameTooltip_AddColoredDoubleLine",
	"GameTooltip_AddColoredLine",
	"GameTooltip_AddInstructionLine",
	"GameTooltip_AddNormalLine",
	"GameTooltip_SetTitle",
	"geterrorhandler",
	"GetTime",
	"GRAY_FONT_COLOR",
	"HIGHLIGHT_FONT_COLOR",
	"hooksecurefunc",
	"securecallfunction",
	"IsInGuild",
	"IsInInstance",
	"LE_PARTY_CATEGORY_INSTANCE",
	"Mixin",
	"NORMAL_FONT_COLOR",
	"ObjectiveTrackerFrame",
	"ObjectiveTrackerManager",
	"ORANGE_FONT_COLOR",
	"Settings",
	"MinimalSliderWithSteppersMixin",
	"SecondsToTime",
	"OFF",
	"RaidWarningUtil",
	"PlaySoundFile",
	"FlashClientIcon",
	"ChatTypeInfo",
	"UIParent",
	"UiMapPoint",
	"IsShiftKeyDown",
	"IsModifierKeyDown",
	"GetUnitSpeed",
	"GetTaxiMapID",
	"NumTaxiNodes",
	"TaxiNodeGetType",
	"TaxiGetNodeSlot",
	"GetNumRoutes",
	"TaxiFrame",
	"TaxiRouteMap",
	"NUM_TAXI_ROUTES",
	"TAXIROUTE_LINEFACTOR",
	"DrawOneHopLines",
	"DrawLine",
	"C_TaxiMap",
	"C_SuperTrack",
	"UnitFactionGroup",
	"UnitOnTaxi",
	"UnitPosition",
	"UnitIsDeadOrGhost",
	"UnitIsGhost",
	"C_DeathInfo",
	"UNKNOWN",
	"WorldMapFrame",
	"Minimap",
	"GetPlayerFacing",
	"GetCVar",
	"GetCVarBool",
	"GetMinimapShape",
	"C_Minimap",
}
files["tests/"] = { std = "+luajit" }
-- The headless test client's dev addon (tools/headless): it closes a chat box and takes the ready screenshot.
files["tools/headless/"] = { read_globals = { "ChatEdit_DeactivateChat", "Screenshot" } }
-- The !!DevSmoke dev addon (tools/devsmoke) and its spec: the client's error frame, its error handler, the world map
-- toggle, the secure-value check, the addon's saved runs and its slash alias; the Agent chat tab's window functions,
-- BugGrabber's own API, and the panels the close command hides.
files["tools/devsmoke/"] = {
	read_globals = {
		"UIErrorsFrame",
		"seterrorhandler",
		"ToggleWorldMap",
		"issecurevariable",
		"debugstack",
		"time",
		"NUM_CHAT_WINDOWS",
		"GetChatWindowInfo",
		"FCF_OpenNewWindow",
		"FCF_SelectDockFrame",
		"BugGrabber",
		"ProfessionsFrame",
		"WorldMapFrame",
		"SettingsPanel",
		"HideUIPanel",
		"C_TradeSkillUI",
		"C_AddOns",
	},
	globals = { "DevSmokeDB", "SLASH_DEVSMOKE1" },
}
files["tests/devsmoke_spec.lua"] = { globals = { "DevSmokeDB", "SLASH_DEVSMOKE1" } }

-- Tracker colours.
read_globals[#read_globals + 1] = "OBJECTIVE_TRACKER_COLOR"
-- MapCanvas.lua: the gamepad's map cursor.
read_globals[#read_globals + 1] = "SoftCursor"
-- Shared-workspace arrow: Blizzard_QuestNavigation/SuperTrackedFrame.lua:291.
read_globals[#read_globals + 1] = "C_Navigation"
-- Blizzard_SharedXMLBase/Color.lua:3, saturated route colours.
read_globals[#read_globals + 1] = "CreateColor"
-- Native quest menus, locations and MapCanvas's consuming pin-click handler.
read_globals[#read_globals + 1] = "C_QuestLog"
read_globals[#read_globals + 1] = "GetQuestUiMapID"
read_globals[#read_globals + 1] = "GetMouseFoci"
-- Shift+click on the map defers to an open chat box.
read_globals[#read_globals + 1] = "ChatEdit_GetActiveWindow"
read_globals[#read_globals + 1] = "ChatFrameUtil"
read_globals[#read_globals + 1] = "MapCanvasMixin"
read_globals[#read_globals + 1] = "POIButtonUtil"
-- PathGrid.lua: its per-frame CPU clock and the per-continent walking-map addons it loads on demand.
read_globals[#read_globals + 1] = "debugprofilestop"
read_globals[#read_globals + 1] = "ShortestPathForeverPathData"
read_globals[#read_globals + 1] = "C_AddOns"
-- Whether a value the client may hold secret can be read: checked across Core, Journey, Transport and UI.
read_globals[#read_globals + 1] = "canaccessvalue"
-- JourneyGuide.lua: picks out the map's own waypoint data provider.
read_globals[#read_globals + 1] = "WaypointLocationDataProviderMixin"
-- Journey.lua: water walking from its buffs, or a spell to cast.
read_globals[#read_globals + 1] = "C_UnitAuras"
read_globals[#read_globals + 1] = "IsPlayerSpell"
read_globals[#read_globals + 1] = "C_Spell"
-- Route.lua: the cursor over the minimap.
read_globals[#read_globals + 1] = "GetCursorPosition"
-- UI/OpenMap.lua: the seamless world map addon's public API for other addons (version 2 and up).
read_globals[#read_globals + 1] = "OpenMapAPI"

read_globals[#read_globals + 1] = "IsPlayerMoving"
read_globals[#read_globals + 1] = "InCombatLockdown"
-- Core/OpenMap.lua and Core/OpenSettings.lua: the client's secure delegate for its restricted openers.
read_globals[#read_globals + 1] = "CreateSecureDelegate"
read_globals[#read_globals + 1] = "C_AddOnProfiler"
read_globals[#read_globals + 1] = "UpdateAddOnMemoryUsage"
read_globals[#read_globals + 1] = "GetAddOnMemoryUsage"
-- Teleports.lua: which teleports this character can cast, and where it is bound.
read_globals[#read_globals + 1] = "C_Item"
read_globals[#read_globals + 1] = "C_SpellBook"
read_globals[#read_globals + 1] = "GetBindLocation"
-- TrackerHost.lua: whether Edit Mode is open.
read_globals[#read_globals + 1] = "EditModeManagerFrame"

-- tests/ui_client.lua and tests/ui_map.lua are one chunk defining the client for the UI checks, which append code
-- reading their locals. 2xx: locals and arguments only the appended checks use; 43x: stub methods named like the
-- client's.
files["tests/ui_client.lua"] = {
	allow_defined_top = true,
	ignore = { "2", "43" },
	-- Blizzard_SharedXML/Spinner.lua defines SpinnerMixin.
	read_globals = { "SpinnerMixin" },
}
-- ui_map.lua continues ui_client.lua's chunk, so its "globals" are ui_client.lua's locals.
files["tests/ui_map.lua"] = { ignore = { "1", "2", "43" } }
read_globals[#read_globals + 1] = "EventRegistry"

read_globals[#read_globals + 1] = "C_EncodingUtil"

read_globals[#read_globals + 1] = "RXP"

read_globals[#read_globals + 1] = "AdventureGuideForever"
-- Core/TomTom.lua: Polestar's TomTom stand-in and its settings.
read_globals[#read_globals + 1] = "Polestar"
-- SafeCall.lua and Report.lua (the report window shared with the other Forever addons).
read_globals[#read_globals + 1] = "debugstack"
read_globals[#read_globals + 1] = "strtrim"
read_globals[#read_globals + 1] = "GetBuildInfo"
read_globals[#read_globals + 1] = "GetLocale"
read_globals[#read_globals + 1] = "UnitClass"
read_globals[#read_globals + 1] = "UnitRace"
read_globals[#read_globals + 1] = "UnitLevel"
read_globals[#read_globals + 1] = "UISpecialFrames"
read_globals[#read_globals + 1] = "tContains"
-- Mover.lua: whether the button of a fine drag is still held.
read_globals[#read_globals + 1] = "IsMouseButtonDown"

-- A translated line is one string; StyLua already wraps what it can, and CJK text counts bytes, not columns.
files["Locales/*.lua"] = { max_line_length = false }

-- ForeverCore: the shared files publish these globals, and Core.lua's saved table.
globals[#globals + 1] = "ForeverCore"
globals[#globals + 1] = "ForeverCoreDB"
-- Core/MinimapButton.lua says why a button was skipped when the client has no Minimap.
read_globals[#read_globals + 1] = "DEFAULT_CHAT_FRAME"
globals[#globals + 1] = "SLASH_FOREVERCORE1"
globals[#globals + 1] = "SLASH_FOREVERCORE2"
-- UI/QuestLogTabs.lua: Blizzard's quest log, the Forever override table and the stock Quests label.
read_globals[#read_globals + 1] = "QuestMapFrame"
read_globals[#read_globals + 1] = "QuestMapFrameOverrides"
read_globals[#read_globals + 1] = "QUESTS_LABEL"
-- UI/ProfessionTabs.lua: the client's Professions window and the native side tabs on it.
read_globals[#read_globals + 1] = "ProfessionsFrame"
-- UI/TrackerQuests.lua: the game's own quest tracker mixins, its quest cache and the strings they draw.
read_globals[#read_globals + 1] = "QuestObjectiveTrackerMixin"
read_globals[#read_globals + 1] = "CampaignQuestObjectiveTrackerMixin"
read_globals[#read_globals + 1] = "QuestCache"
read_globals[#read_globals + 1] = "TRACKER_HEADER_QUESTS"
read_globals[#read_globals + 1] = "QUEST_WATCH_QUEST_COMPLETE"
read_globals[#read_globals + 1] = "QUEST_WATCH_CLICK_TO_COMPLETE"
read_globals[#read_globals + 1] = "QUEST_WATCH_QUEST_READY"
read_globals[#read_globals + 1] = "FAILED"
read_globals[#read_globals + 1] = "WAYPOINT_OBJECTIVE_FORMAT_OPTIONAL"
read_globals[#read_globals + 1] = "OBJECTIVE_DASH_STYLE_HIDE"
read_globals[#read_globals + 1] = "SetQuestTitleLevelAndDifficultyColor"
read_globals[#read_globals + 1] = "GetQuestLogCompletionText"
read_globals[#read_globals + 1] = "IsQuestSequenced"
read_globals[#read_globals + 1] = "QuestMapFrame_GetFocusedQuestID"
