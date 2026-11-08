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

---@class ForeverTrackerNamespace
---@field MapCanvas? ForeverMapCanvas
---@field Leaderboards? ForeverLeaderboardsAPI
---@field LeaderboardsData? ForeverLeaderboardsData
---@field MinimapButton? ForeverMinimapButtonAPI
---@field QuestLogTabs? ForeverQuestLogTabsAPI
---@field SafeCall fun(label: string, fn: function, ...: any): boolean, ...any
---@field Defaults? ForeverTrackerSettings
