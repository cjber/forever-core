-- The tracker contract the shared files read and publish. Kept here so the core typechecks without an addon's own
-- declarations, and vendored nowhere: consumers declare the same classes in their own types/Forever.lua.

---@class ForeverTrackerSettings
---@field attached boolean the column follows the native quest tracker
---@field locked? boolean the Lock switch, which suppresses the grip's drag
---@field scale number the player's tracker scale, 0.5 to 2
---@field backdropOpacity? number the optional backdrop's opacity, 0 (off) to 1
---@field x? number the detached position, from UIParent's top left corner
---@field y? number

---@class ForeverTrackerGrip
---@field Show fun(value: boolean)
---@field SetLabel fun(value: boolean)

---@class ForeverTrackerHostAPI
---@field Attach fun(module: Frame)
---@field IsAttached fun(module: Frame?): boolean
---@field IsLocked fun(): boolean
---@field SetLocked fun(value: boolean)
---@field GetBackdropOpacity fun(): number
---@field SetBackdropOpacity fun(value: number)
---@field IsAttachedToQuestTracker fun(): boolean
---@field SetAttached fun(value: boolean)
---@field OnAttachmentChanged fun(callback: fun(attached: boolean))
---@field SavePosition fun(x: number, y: number)
---@field Debug fun(): string

---@class ForeverTrackerOrderAPI
---@field Sort fun(modules: ForeverTrackerModule[])

---@class ForeverQuestLogTabSpec
---@field name string the tab frame's global name
---@field tooltip string the tab's tooltip text
---@field panel Frame the panel the tab shows
---@field order number where the tab sits in the stack, lowest first
---@field shown? fun(visible: boolean) told when this panel becomes visible or stops being visible

---@class ForeverQuestLogTabsAPI
---@field Register fun(key: string, spec: ForeverQuestLogTabSpec): ForeverQuestLogTab
---@field Select fun(key: string)
---@field ShowQuests fun()
---@field Selected fun(): string?

---@class ForeverTrackerNamespace
---@field MapCanvas? ForeverMapCanvas
---@field ContextMenu? fun(owner: Frame, generator: fun(owner: Frame, root: any)): any
---@field Leaderboards? ForeverLeaderboardsAPI
---@field LeaderboardsData? ForeverLeaderboardsData
---@field MinimapButton? ForeverMinimapButtonAPI
---@field QuestLogTabs? ForeverQuestLogTabsAPI
---@field SafeCall fun(label: string, fn: function, ...: any): boolean, ...any
---@field L table<string, string>
---@field TrackerHost? ForeverTrackerHostAPI
---@field TrackerLock? table
---@field TrackerOrder? ForeverTrackerOrderAPI
---@field TrackerQuestie? ForeverTrackerQuestie
---@field TrackerEqot? ForeverTrackerEqot
---@field TrackerHostSettings? fun(): ForeverTrackerSettings
---@field Defaults? ForeverTrackerSettings
