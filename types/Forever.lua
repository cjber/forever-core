-- What core's own non-tracker shared files add to the namespace. The tracker contract lives in types/ForeverTracker.lua,
-- vendored with the tracker files, so a consumer declares nothing of it by hand.

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

-- UI/SettingsPage.lua, the shared settings canvas this addon's one row is drawn on.
---@class ForeverSettingsPageModule
---@field Register fun(name: string, build: function): table?, Frame?
---@field AddCheck fun(panel: Frame, label: string, get: function, set: function, tooltip?: string): CheckButton

---@class ForeverTrackerNamespace
---@field OpenMap fun(mapID?: integer): boolean
---@field OpenSettingsPanel fun(categoryID?: integer, element?: string): boolean
---@field SettingsPage? ForeverSettingsPageModule
---@field MapCanvas? ForeverMapCanvas
---@field Leaderboards? ForeverLeaderboardsAPI
---@field LeaderboardsData? ForeverLeaderboardsData
---@field MinimapButton? ForeverMinimapButtonAPI
---@field QuestLogTabs? ForeverQuestLogTabsAPI
---@field QuestOrder fun(records: ForeverQuestRecord[]): ForeverQuestGroup[]
---@field TrackerQuests? ForeverTrackerQuestsAPI
---@field SafeCall fun(label: string, fn: function, ...: any): boolean, ...any
---@field Defaults? ForeverTrackerSettings
