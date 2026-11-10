-- What core's own shared files add to the namespace. The tracker contract lives in types/ForeverTracker.lua.

---@alias ForeverSafeCall fun(label: string, fn: function, ...: any): boolean, any

---@class ForeverQuestLogTabSpec
---@field name string the tab frame's global name
---@field tooltip string the tab's tooltip text
---@field panel Frame the panel the tab shows
---@field order number where the tab sits in the stack, lowest first
---@field shown? fun(visible: boolean) told when this panel becomes visible or stops being visible
---@field safeCall? fun(label: string, fn: function, ...: any): boolean, any the addon's SafeCall for its own callbacks

---@class ForeverQuestLogTabsAPI
---@field Register fun(key: string, spec: ForeverQuestLogTabSpec): ForeverQuestLogTab
---@field Select fun(key: string)
---@field ShowQuests fun()
---@field Selected fun(): string?

-- The Forever quest list's pure ordering model, in Core/QuestOrder.lua.
---@class ForeverQuestRecord
---@field questID number
---@field title string?
---@field zone string?
---@field ready boolean?
---@field onMap boolean?
---@field distanceSq number?

---@class ForeverQuestGroup
---@field title string
---@field quests ForeverQuestRecord[]

-- UI/TrackerQuests.lua, core's own optional section.
---@class ForeverTrackerQuestsAPI
---@field Enabled fun(): boolean
---@field SetEnabled fun(value: boolean)
---@field Toggle fun()

---@class ForeverQuestTrackerModule : ForeverTrackerModule
---@field MarkDirty fun(self: ForeverQuestTrackerModule)
---@field SetHeader fun(self: ForeverQuestTrackerModule, text: string)
---@field GetBlock fun(self: ForeverQuestTrackerModule, id: any, template?: string): any, boolean
---@field LayoutBlock fun(self: ForeverQuestTrackerModule, block: any): boolean
---@field DoQuestObjectives fun(self: ForeverQuestTrackerModule, block: any, questCompleted: boolean, questSequenced: boolean, isExistingBlock: boolean, useFullHeight: boolean): boolean
---@field GetQuestTagText fun(self: ForeverQuestTrackerModule, questID: number): string?
---@field ShouldDisplayQuest fun(self: ForeverQuestTrackerModule, quest: any): boolean
---@field Records fun(self: ForeverQuestTrackerModule): ForeverQuestRecord[]
---@field UpdateQuest fun(self: ForeverQuestTrackerModule, record: ForeverQuestRecord): boolean
---@field AddHeaderMenuEntries fun(self: ForeverQuestTrackerModule, root: any)
---@field OnBlockHeaderClick fun(self: ForeverQuestTrackerModule, block: any, mouseButton: string)

-- UI/SettingsPage.lua, the shared settings canvas a consumer's settings page is drawn on.
---@class ForeverSettingsPageModule
---@field Register fun(name: string, build: function, L?: table<string, string>, safeCall?: function): table?, Frame?
---@field AddCheck fun(panel: Frame, label: string, get: function, set: function, tooltip?: string): CheckButton

-- UI/ContextMenu.lua, the suite's one context menu.
---@alias ForeverMenuEntryKind "root"|"button"|"title"|"divider"|"checkbox"

---@class ForeverMenuDescription
---@field kind ForeverMenuEntryKind
---@field text? string
---@field entries ForeverMenuDescription[]
---@field onClick? fun()
---@field isSelected? fun(): boolean
---@field isEnabled? boolean|fun(): boolean
---@field tooltip? fun(tooltip: GameTooltip)
---@field scrollExtent? number
---@field parent? ForeverMenuDescription
---@field back? ForeverMenuDescription
---@field CreateButton fun(self: ForeverMenuDescription, text: string, action?: fun()): ForeverMenuDescription
---@field CreateTitle fun(self: ForeverMenuDescription, text: string): ForeverMenuDescription
---@field CreateDivider fun(self: ForeverMenuDescription): ForeverMenuDescription
---@field CreateCheckbox fun(self: ForeverMenuDescription, text: string, selected: function, action: function): ForeverMenuDescription
---@field CreateRadio fun(self: ForeverMenuDescription, text: string, selected: function, action: function, data?: any): ForeverMenuDescription
---@field SetEnabled fun(self: ForeverMenuDescription, enabled: boolean|fun(): boolean)
---@field IsEnabled fun(self: ForeverMenuDescription): boolean
---@field SetTooltip fun(self: ForeverMenuDescription, tooltip: function)
---@field SetScrollMode fun(self: ForeverMenuDescription, extent: number)

---@class ForeverCoreSpec
---@field title? string|fun(): string the report window's title
---@field lines? fun(): string[] the addon's own report lines
---@field db? table the addon's saved table, when it is already loaded

---@class ForeverCoreAddon
---@field name string
---@field SafeCall fun(label: string, fn: function, ...: any): boolean, any
---@field RecordError fun(label: string, message: any, stack?: string)
---@field CaughtErrors fun(): ForeverCaughtError[]
---@field CutText fun(text: string, limit: integer): string
---@field Log fun(level: string, topic: string, message: any, ...: any)
---@field LogLines fun(count?: integer): string[]
---@field DebugEnabled fun(): boolean
---@field DebugCommand fun(argument?: string): boolean
---@field Report ForeverReportModule
---@field MapCanvas ForeverCanvasAPI
---@field Attach fun(db: table) the addon's saved table, once it loads

---@class ForeverCoreAPI
---@field API integer the interface version; 1 is the first
---@field Register fun(addonName: string, spec?: ForeverCoreSpec): ForeverCoreAddon
---@field TrackerHost? ForeverTrackerHostAPI
---@field TrackerLock? ForeverTrackerLock
---@field TrackerOrder? ForeverTrackerOrderAPI
---@field TrackerQuestie? ForeverTrackerQuestie
---@field TrackerEqot? ForeverTrackerEqot
---@field TrackerQuests? ForeverTrackerQuestsAPI
---@field QuestLogTabs? ForeverQuestLogTabsAPI
---@field PeerStats? ForeverPeerStatsNamespace
---@field Leaderboards? ForeverLeaderboardsAPI
---@field LeaderboardsData? ForeverLeaderboardsData
---@field MinimapButton? ForeverMinimapButtonAPI
---@field SettingsPage? ForeverSettingsPageModule
---@field Text? table
---@field QuestOrder fun(records: ForeverQuestRecord[]): ForeverQuestGroup[]
---@field OpenMap fun(mapID?: integer): boolean
---@field OpenSettingsPanel fun(categoryID?: integer, element?: string): boolean
---@field Family? ForeverFamilyAPI
---@field ContextMenu fun(owner: Region, generator: fun(owner: Region, root: ForeverMenuDescription)): ForeverMenuDescription?

---@type ForeverCoreAPI
ForeverCore = nil

---@class ForeverTrackerNamespace
---@field OpenMap fun(mapID?: integer): boolean
---@field OpenSettingsPanel fun(categoryID?: integer, element?: string): boolean
---@field SettingsPage? ForeverSettingsPageModule
---@field MapCanvas? ForeverCanvasAPI
---@field Leaderboards? ForeverLeaderboardsAPI
---@field LeaderboardsData? ForeverLeaderboardsData
---@field MinimapButton? ForeverMinimapButtonAPI
---@field QuestLogTabs? ForeverQuestLogTabsAPI
---@field QuestOrder fun(records: ForeverQuestRecord[]): ForeverQuestGroup[]
---@field TrackerQuests? ForeverTrackerQuestsAPI
---@field ContextMenu? fun(owner: Region, generator: fun(owner: Region, root: ForeverMenuDescription)): ForeverMenuDescription?
---@field SafeCall fun(label: string, fn: function, ...: any): boolean, ...any
