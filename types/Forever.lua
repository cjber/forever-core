-- The tracker contract the shared files read and publish. Kept here so the core typechecks without an addon's own
-- declarations, and vendored nowhere: consumers declare the same classes in their own types/Forever.lua.

---@class ForeverTrackerSettings
---@field attached boolean the column follows the native quest tracker
---@field locked? boolean the Lock switch, which suppresses the grip's drag
---@field scale number the player's tracker scale, 0.5 to 2
---@field x? number the detached position, from UIParent's top left corner
---@field y? number

---@class ForeverTrackerModule : Frame
---@field uiOrder? number
---@field parentContainer? Frame

---@class ForeverTrackerGrip
---@field Show fun(value: boolean)
---@field SetLabel fun(value: boolean)

---@class ForeverTrackerHostAPI
---@field Attach fun(module: Frame)
---@field IsAttached fun(module: Frame?): boolean
---@field IsLocked fun(): boolean
---@field SetLocked fun(value: boolean)
---@field IsAttachedToQuestTracker fun(): boolean
---@field SetAttached fun(value: boolean)
---@field OnAttachmentChanged fun(callback: fun(attached: boolean))
---@field SavePosition fun(x: number, y: number)
---@field Debug fun(): string

---@class ForeverTrackerOrderAPI
---@field Sort fun(modules: ForeverTrackerModule[])

---@class ForeverTrackerNamespace
---@field L table<string, string>
---@field TrackerHost? ForeverTrackerHostAPI
---@field TrackerLock? table
---@field TrackerOrder? ForeverTrackerOrderAPI
---@field TrackerQuestie? table
---@field TrackerHostSettings? fun(): ForeverTrackerSettings
---@field Defaults? ForeverTrackerSettings
