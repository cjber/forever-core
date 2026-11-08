---@meta

-- Core checks the helper without loading the generated FrameXML annotations consumers provide.
---@class WorldMapFrame : Frame
---@field GetMapID fun(self: WorldMapFrame): number?
---@field GetCanvas fun(self: WorldMapFrame): Frame
---@field GetCanvasScale fun(self: WorldMapFrame): number?
---@field GetCanvasZoomPercent fun(self: WorldMapFrame): number?
---@field GetGlobalPinScale fun(self: WorldMapFrame): number?
---@field GetPinFrameLevelsManager? fun(self: WorldMapFrame): ForeverCanvasLevels
---@class ForeverCanvasLevels
---@field GetValidFrameLevel fun(self: ForeverCanvasLevels, levelType: string): number?

---@type {GetCurrentStyle: fun(): number}?
C_InputInterfaceStyle = nil
---@type Frame
SoftCursor = nil
---@type table<string, fun(map: ForeverCanvasMap): {x: number, y: number, kind: string}[]>
ForeverMapMarkers = nil
---@param value number
---@return number
function Saturate(value) end
---@param a number
---@param b number
---@param t number
---@return number
function Lerp(a, b, t) end

-- FrameXML surfaces the shared files read that Ketho's pinned Core annotations do not carry. Signatures follow
-- Gethe/wow-ui-source forever. Consumers declare the same globals in their own types/; these declarations never load
-- in the client.

---@type table<string, fun(msg: string)>
SlashCmdList = {}
---@type MessageFrame
DEFAULT_CHAT_FRAME = nil
-- Frames Escape closes, by name.
---@type string[]
UISpecialFrames = {}
---@type {ContinueOnAddOnLoaded: fun(name: string, callback: fun()), ContinueAfterAllEvents: fun(callback: fun(), ...: string)}
EventUtil = {}
function GameTooltip_Hide() end

-- ForeverCore's own saved variables, from ForeverCore.toc.
---@type {trackerHost?: ForeverTrackerSettings}?
ForeverCoreDB = nil

-- UI/Leaderboards.lua publishes the shared window every Forever addon registers into.
---@type ForeverLeaderboardsAPI?
ForeverLeaderboards = nil

---@class EditModeManagerFrame : Frame
---@field IsEditModeActive fun(self: EditModeManagerFrame): boolean
---@type EditModeManagerFrame?
EditModeManagerFrame = nil

---@type ForeverNativeTrackerFrame
ObjectiveTrackerFrame = nil

-- Blizzard_SharedXML/Pool.lua; addon-owned instances, never ObjectiveTrackerManager's pool.
---@class ForeverPrivateFramePool
---@field Acquire fun(self: ForeverPrivateFramePool, template: string): Frame, boolean
---@class ForeverPrivatePoolCollection
---@field GetOrCreatePool fun(self: ForeverPrivatePoolCollection, frameType: string, parent: Frame, template: string): ForeverPrivateFramePool
---@field Release fun(self: ForeverPrivatePoolCollection, frame: Frame)
---@return ForeverPrivatePoolCollection
function CreateFramePoolCollection() end

-- The saved table a consumer hands the shared minimap button: the angle and the hide flag live in it.
---@class ForeverMinimapButtonSpec
---@field name string the frame name, unique in the addon
---@field icon string|number the addon's own content icon
---@field title string the tooltip title
---@field binding? string shown under the title, e.g. "Shift-F"
---@field subtext? string the tooltip's one line about what a click does
---@field onClick? fun(button: Frame, mouseButton: string) what a left click runs
---@field settings? table the saved table holding the angle and hide flag
---@field angleKey? string the settings key holding the angle, default "minimapButtonAngle"
---@field hiddenKey? string the settings key whose true value hides the button, default "minimapButtonHidden"
---@field getShown? fun(): boolean an addon-owned visibility rule, which wins over the hide flag
---@field host? table receives the frame as its minimapButton

-- The registry every vendored copy of Core/MinimapButton.lua shares, published by the first to load.
---@class ForeverMinimapButtonRegistry
---@field buttons ForeverMinimapButton[] every addon button, in creation order
---@type ForeverMinimapButtonRegistry?
ForeverMinimapButtons = nil

-- The frame Core/MinimapButton.lua builds: LibDBIcon's minimap button, the addon's icon and the angle on the rim.
---@class ForeverMinimapButton : Button
---@field minimapButtonSpec ForeverMinimapButtonSpec the spec the consumer passed to Create
---@field icon Texture the addon's icon drawn inside LibDBIcon's border
---@field angle number the angle around the Minimap, in degrees
---@field dragging boolean? true while the player drags the button around the rim

---@class ForeverMinimapButtonAPI
---@field Create fun(spec: ForeverMinimapButtonSpec): ForeverMinimapButton?
---@field Destroy fun(button: ForeverMinimapButton?)
---@field Refresh fun()
---@field SetShown fun(button: ForeverMinimapButton?, shown: boolean)

-- UI/QuestLogTabs.lua: the tab it builds from Blizzard's LargeSideTabButtonTemplate.
---@class ForeverQuestLogTab : Button
---@field SetCustomOnMouseUpHandler fun(self: ForeverQuestLogTab, handler: fun(self: ForeverQuestLogTab, mouseButton: string, upInside: boolean))
---@field SetChecked fun(self: ForeverQuestLogTab, checked: boolean)
---@field tooltipText string
---@field activeAtlas? string
---@field inactiveAtlas? string

-- The registry every vendored copy of UI/QuestLogTabs.lua shares, published by the first to load.
---@type ForeverQuestLogTabsAPI?
ForeverQuestLogTabs = nil

-- Blizzard's quest log, and the Forever override table that says its stock Quests tab is hidden.
---@class ForeverQuestLogContentFrame : Frame
---@field displayMode any
---@class ForeverQuestMapFrame : Frame
---@field ContentFrames ForeverQuestLogContentFrame[]
---@field QuestsTab Button
---@field MapLegendTab Button
---@field displayMode any
---@type ForeverQuestMapFrame
QuestMapFrame = nil
---@class ForeverQuestMapFrameOverrides
---@field questTabHidden? boolean
---@field GetQuestsTabAnchorOffset fun(): number, number
---@type ForeverQuestMapFrameOverrides
QuestMapFrameOverrides = nil
---@type string
QUESTS_LABEL = nil

-- The templates UI/SettingsPage.lua creates, each the widget its row is: the return type of CreateFrame with a
-- template is the union of the template class and the widget class.
---@class InterfaceOptionsCheckButtonTemplate : CheckButton
---@class OptionsSliderTemplate : Slider
---@class UIPanelButtonTemplate : Button

-- Settings: the canvas category the settings page registers itself as.
---@class ForeverSettings
---@field RegisterCanvasLayoutCategory fun(frame: Frame, name: string): table
---@field RegisterAddOnCategory fun(category: table)
---@type ForeverSettings?
Settings = nil

-- The settings page keeps one cursor down its canvas, so every row claims its height.
---@class Frame
---@field settingsRowY? number

-- UI/Leaderboards.lua: the client widgets it builds, declared here because the shared file typechecks in core.
---@class ForeverClassColor
---@field GetRGB fun(self: ForeverClassColor): number, number, number
---@type table<string, ForeverClassColor>?
RAID_CLASS_COLORS = nil

---@class ForeverDataProvider
---@field entries any[]
---@param entries? any[]
---@return ForeverDataProvider
function CreateDataProvider(entries) end

---@class ForeverScrollBoxView
---@field SetElementInitializer fun(self: ForeverScrollBoxView, template: string, initializer: fun(button: Button, element: any))
---@field SetElementExtent fun(self: ForeverScrollBoxView, extent: number)
---@field SetPadding fun(self: ForeverScrollBoxView, ...: number)
---@return ForeverScrollBoxView
function CreateScrollBoxListLinearView() end

---@class ForeverScrollUtil
---@field InitScrollBoxListWithScrollBar fun(box: Frame, bar: any, view: ForeverScrollBoxView)
---@type ForeverScrollUtil
ScrollUtil = nil

---@class ForeverScrollBoxConstants
---@field RetainScrollPosition integer
---@type ForeverScrollBoxConstants
ScrollBoxConstants = nil

-- UI/QuestLogTabs.lua: the client's protected call, which keeps a panel's error from breaking the module's switch.
---@param fn function
function securecallfunction(fn, ...) end
