---@meta

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

-- The client's micro menu bar and the buttons Core/MicroButton.lua anchors against (FrameXML MicroMenu).
---@class ForeverMicroMenu : Frame
---@field Layout fun(self: ForeverMicroMenu)
---@type ForeverMicroMenu?
MicroMenu = nil
---@type Button?
MainMenuMicroButton = nil
---@type Button?
CollectionsMicroButton = nil
---@type fun()
UpdateMicroButtons = nil

-- The frame Core/MicroButton.lua builds: Blizzard's micro button template plus the state it stores on it.
---@class ForeverMicroButton : Button
---@field microButtonSpec table the spec the consumer passed to Create
---@field icon Texture the glyph drawn over the plate
---@field alert table? the template's alert overlay, hidden for a custom button

-- The templates UI/SettingsPage.lua creates, each the widget its row is: the return type of CreateFrame with a
-- template is the union of the template class and the widget class.
---@class InterfaceOptionsCheckButtonTemplate : CheckButton
---@class OptionsSliderTemplate : Slider
---@class UIDropDownMenuTemplate : Frame
---@class UIPanelButtonTemplate : Button

-- FrameXML's dropdown menu API, in its own file since Dragonflight; the pinned Core annotations predate that move.
---@type fun(dropdown: Frame, width: number)
UIDropDownMenu_SetWidth = nil
---@type fun(dropdown: Frame, value: any)
UIDropDownMenu_SetSelectedValue = nil
---@type fun(dropdown: Frame, initialize: fun(dropdown: Frame, level: number?))
UIDropDownMenu_Initialize = nil
---@type fun(): table
UIDropDownMenu_CreateInfo = nil
---@type fun(info: table, level: number?)
UIDropDownMenu_AddButton = nil

-- Settings: the canvas category the settings page registers itself as.
---@class ForeverSettings
---@field RegisterCanvasLayoutCategory fun(frame: Frame, name: string): table
---@field RegisterAddOnCategory fun(category: table)
---@type ForeverSettings?
Settings = nil

-- The settings page keeps one cursor down its canvas, so every row claims its height.
---@class Frame
---@field settingsRowY? number
