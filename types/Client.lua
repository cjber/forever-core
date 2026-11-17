---@meta

-- Core checks the helper without loading the generated FrameXML annotations consumers provide.
---@class WorldMapFrame : Frame
---@field GetMapID fun(self: WorldMapFrame): number?
---@field GetCanvas fun(self: WorldMapFrame): Frame
---@field GetCanvasScale fun(self: WorldMapFrame): number?
---@field GetCanvasZoomPercent fun(self: WorldMapFrame): number?
---@field GetGlobalPinScale fun(self: WorldMapFrame): number?
---@field GetPinFrameLevelsManager? fun(self: WorldMapFrame): ForeverCanvasLevels
---@field SetQuestLogPanelShown fun(self: WorldMapFrame, shown: boolean)
---@class ForeverCanvasLevels
---@field GetValidFrameLevel fun(self: ForeverCanvasLevels, levelType: string): number?

---@type {GetCurrentStyle: fun(): number}?
C_InputInterfaceStyle = nil
---@type Frame
SoftCursor = nil
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
---@param tooltip GameTooltip
---@param text string
function GameTooltip_SetTitle(tooltip, text) end

-- ForeverCore's own saved variables, from ForeverCore.toc.
---@class ForeverCoreSavedVariables
---@field trackerHost? ForeverTrackerSettings
---@field leaderboards? table Retired Forever Leaderboards saved data, cleared at load.
---@field questList? boolean The retired Forever quest list's switch, cleared at load.
---@field questListHintDone? boolean The retired quest list hint's answer, cleared at load.
---@field questListFold? table The retired quest list's per-character folds, cleared at load.
---@field debugCapture? ForeverDebugCaptureState the client's values before /forever debug on, kept across a reload.
---@field _store? ForeverCoreStoreMeta the reconciled store node and any retained setting conflicts.
---@field ForeverCoreStore? table the reserved mirror key inside a consumer's account table.
---@type ForeverCoreSavedVariables?
ForeverCoreDB = nil

-- Whether the client lets this code read a value it may hold secret (WFA-30).
---@param value any
---@return boolean
function canaccessvalue(value) end

---@class EditModeManagerFrame : Frame
---@field IsEditModeActive fun(self: EditModeManagerFrame): boolean
---@type EditModeManagerFrame?
EditModeManagerFrame = nil

---@type ForeverNativeTrackerFrame
ObjectiveTrackerFrame = nil

-- The companion tracker registry a store build's vendored host still uses. ForeverCore adopts the column when it is
-- already there, and publishes its own so a vendored host loaded later reuses it instead of drawing another.
---@type ForeverTrackerHostAPI?
ForeverTrackerHost = nil

-- Blizzard_SharedXML/Pool.lua; addon-owned instances, never ObjectiveTrackerManager's pool.
---@class ForeverPrivateFramePool
---@field Acquire fun(self: ForeverPrivateFramePool, template: string): Frame, boolean
---@class ForeverPrivatePoolCollection
---@field GetOrCreatePool fun(self: ForeverPrivatePoolCollection, frameType: string, parent: Frame, template: string): ForeverPrivateFramePool
---@field Release fun(self: ForeverPrivatePoolCollection, frame: Frame)
---@return ForeverPrivatePoolCollection
function CreateFramePoolCollection() end

-- The retired minimap button's calls, kept one release as no-ops for addons released before it went.
---@class ForeverMinimapButtonAPI
---@field Create fun(spec: table): nil
---@field Destroy fun(button: any)
---@field Refresh fun()
---@field SetShown fun(button: any, shown: boolean)

-- UI/QuestLogTabs.lua: the tab it builds from Blizzard's LargeSideTabButtonTemplate.
---@class ForeverQuestLogTab : Button
---@field SetCustomOnMouseUpHandler fun(self: ForeverQuestLogTab, handler: fun(self: ForeverQuestLogTab, mouseButton: string, upInside: boolean))
---@field SetChecked fun(self: ForeverQuestLogTab, checked: boolean)
---@field tooltipText string
---@field activeAtlas? string
---@field inactiveAtlas? string

-- The registry UI/QuestLogTabs.lua shares across the suite, one tab per addon.

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
---@type WorldMapFrame
WorldMapFrame = nil
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

-- Settings: the settings page's canvas category.
---@class ForeverSettings
---@field RegisterCanvasLayoutCategory fun(frame: Frame, name: string): table
---@field RegisterAddOnCategory fun(category: table)
---@field RegisterVerticalLayoutSubcategory fun(parent: table, name: string): table
---@field RegisterProxySetting fun(category: table, variable: string, varType: string, name: string, default: any, get: (fun(): any), set: (fun(value: any))): table
---@field VarType {Boolean: string}
---@field CreateCheckbox fun(category: table, setting: table, tooltip?: string): table
---@field RegisterInitializer fun(category: table, initializer: table)
---@type ForeverSettings?
Settings = nil

---@class ForeverSettingsPanel : Frame
---@field IsShown fun(self: ForeverSettingsPanel): boolean
---@field OpenToCategory fun(self: ForeverSettingsPanel, categoryID?: number, scrollToElementName?: string)
---@type ForeverSettingsPanel?
SettingsPanel = nil

-- The client's native vertical-list section heading initializer.
---@type fun(name: string, tooltip?: string, newTagID?: number): table
CreateSettingsListSectionHeaderInitializer = nil

-- The settings page keeps one cursor down its canvas, so every row claims its height.
---@class Frame
---@field settingsRowY? number

-- The ForeverProfession* classes type core's view of the window; the client global is left for an addon to type.
-- UI/ProfessionTabs.lua: the tab it builds from Blizzard's LargeSideTabButtonTemplate.
---@class ForeverProfessionTab : Button
---@field Icon Texture
---@field tooltipText string
---@field SetCustomOnMouseUpHandler fun(self: ForeverProfessionTab, handler: fun(self: ForeverProfessionTab, mouseButton: string, upInside: boolean))
---@field SetChecked fun(self: ForeverProfessionTab, checked: boolean)
---@field SetFillToInterior? fun(self: ForeverProfessionTab, value: boolean)

-- A native side tab on the Professions window, from the client's ProfessionsFrame right-hand column.
---@class ForeverProfessionNativeTab : Frame
---@field SetChecked fun(self: ForeverProfessionNativeTab, checked: boolean)
---@field IsShown fun(self: ForeverProfessionNativeTab): boolean

-- A page in the Professions window.
---@class ForeverProfessionPage : Frame

-- The client's Professions window and its native side tabs and pages.
---@class ForeverProfessionsWindow : Frame
---@field CraftingPage ForeverProfessionPage
---@field BookPage? ForeverProfessionPage
---@field SpecPage? ForeverProfessionPage
---@field OrdersPage? ForeverProfessionPage
---@field Pages? ForeverProfessionPage[]
---@field ProfessionsOverviewTab? ForeverProfessionNativeTab
---@field rightProfessionTabs? ForeverProfessionNativeTab[]

-- UI/QuestLogTabs.lua: the client's protected call, which keeps a panel's error from breaking the module's switch.
---@param fn function
function securecallfunction(fn, ...) end
