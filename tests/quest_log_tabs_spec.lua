-- UI/QuestLogTabs.lua against a stub of the world map: two vendored copies share one registry, the tabs stack by
-- order rather than registration, selecting shows one panel and ShowQuests puts the quest log's own pages back.
local function newFrame(name, parent)
	local frame = {
		name = name,
		parent = parent,
		shown = true,
		checked = false,
		points = {},
		sizeCalls = {},
		scripts = {},
		scriptHooks = {},
	}
	function frame:SetPoint(...)
		self.points = { ... }
	end
	function frame:GetPoint()
		return unpack(self.points)
	end
	function frame:ClearAllPoints()
		self.points = {}
	end
	function frame:SetShown(value)
		self.shown = value == true
	end
	function frame:IsShown()
		return self.shown
	end
	function frame:Show()
		self.shown = true
	end
	function frame:Hide()
		self.shown = false
	end
	function frame:SetChecked(value)
		self.checked = value == true
	end
	function frame:IsChecked()
		return self.checked
	end
	function frame:SetCustomOnMouseUpHandler(handler)
		self.mouseUpHandler = handler
	end
	function frame:SetScript(script, handler)
		self.scripts[script] = handler
	end
	function frame:HookScript(script, handler)
		self.scriptHooks[script] = self.scriptHooks[script] or {}
		self.scriptHooks[script][#self.scriptHooks[script] + 1] = handler
	end
	function frame:SetHeight(value)
		self.height = value
		self.sizeCalls[#self.sizeCalls + 1] = { "SetHeight", value }
	end
	function frame:SetSize(width, height)
		self.width, self.height = width, height
		self.sizeCalls[#self.sizeCalls + 1] = { "SetSize", width, height }
	end
	return frame
end

local function countCreated(world, name)
	local count = 0
	for _, frame in ipairs(world.created) do
		if frame.name == name then
			count = count + 1
		end
	end
	return count
end

-- A fresh client per scenario, so each world's published global and QuestMapFrame are independent.
local function newWorld(questTabHidden, offsetX, offsetY)
	_G.ForeverQuestLogTabs = nil
	_G.ForeverQuestLogQuestsTab = nil
	local map = newFrame("QuestMapFrame")
	map.displayMode = 1
	map.ContentFrames = { newFrame("QuestsContent"), newFrame("LegendContent") }
	map.ContentFrames[1].displayMode = 1
	map.ContentFrames[2].displayMode = 2
	map.QuestsTab = newFrame("QuestsTab", map)
	map.MapLegendTab = newFrame("MapLegendTab", map)
	local worldMap = newFrame("WorldMapFrame")
	worldMap.QuestLog = map
	function worldMap:SetQuestLogPanelShown(shown)
		self.QuestLog:SetShown(shown)
	end
	local world = { map = map, worldMap = worldMap, created = {}, callbacks = {}, hooks = {} }

	_G.QuestMapFrame = map
	_G.WorldMapFrame = worldMap
	_G.securecallfunction = function(fn, ...)
		return pcall(fn, ...)
	end
	_G.QuestMapFrameOverrides = {
		questTabHidden = questTabHidden,
		GetQuestsTabAnchorOffset = function()
			return offsetX or 4, offsetY or -7
		end,
	}
	_G.QUESTS_LABEL = "Quests"
	_G.CreateFrame = function(_, frameName, parent, template)
		local frame = newFrame(frameName, parent)
		frame.template = template
		if frameName then
			_G[frameName] = frame
		end
		world.created[#world.created + 1] = frame
		return frame
	end
	_G.EventRegistry = {
		RegisterCallback = function(_, event, callback, owner)
			world.callbacks[event] = world.callbacks[event] or {}
			world.callbacks[event][#world.callbacks[event] + 1] = { callback = callback, owner = owner }
		end,
		TriggerEvent = function(_, event, ...)
			for _, entry in ipairs(world.callbacks[event] or {}) do
				entry.callback(entry.owner, ...)
			end
		end,
	}
	_G.hooksecurefunc = function(target, nameOrCallback, callback)
		if type(target) == "table" then
			local original = target[nameOrCallback]
			target[nameOrCallback] = function(...)
				local results = { original(...) }
				callback(...)
				return unpack(results)
			end
			return
		end
		world.hooks[target] = world.hooks[target] or {}
		world.hooks[target][#world.hooks[target] + 1] = nameOrCallback
	end
	return world
end

local function load(ns)
	assert(loadfile("UI/QuestLogTabs.lua"))("Addon", ns)
	return ns.QuestLogTabs
end

-- Two addons with their own vendored copies, like Adventure Guide and Shortest Path. The second adopts the first.
local world = newWorld(true)
local nsA, nsB = {}, {}
local first = load(nsA)
local second = load(nsB)
assert(first and second, "no quest log tabs API")
assert(first == second, "the second copy did not adopt the first")
assert(_G.ForeverQuestLogTabs == first, "the shared global is not the published API")

local panelA = newFrame("ForeverPanelA")
local panelB = newFrame("ForeverPanelB")
panelA.scroll = 42
local tabB = first.Register("b", { name = "AddonBTab", tooltip = "B", panel = panelB, order = 20 })
local tabA = second.Register("a", { name = "AddonATab", tooltip = "A", panel = panelA, order = 10 })

assert(tabA ~= tabB, "both keys share one tab")
assert(_G.AddonATab == tabA and _G.AddonBTab == tabB, "tabs did not take their names")
assert(tabA.template == "LargeSideTabButtonTemplate", tabA.template)
assert(tabA.parent == world.map, "tab is not parented to QuestMapFrame")
assert(tabA.tooltipText == "A" and tabB.tooltipText == "B", "tooltip")
assert(not tabA.checked and not tabB.checked, "addon tab created checked")
assert(first.Selected() == nil, "a panel started selected")

-- The hidden stock Quests tab gets one replacement, with the client's vertical offset and no horizontal gap.
assert(countCreated(world, "ForeverQuestLogQuestsTab") == 1, "the replacement Quests tab was made more than once")
local quests = _G.ForeverQuestLogQuestsTab
assert(quests and quests.template == "LargeSideTabButtonTemplate", "no replacement Quests tab")
assert(quests.tooltipText == "Quests", quests.tooltipText)
assert(quests.activeAtlas == "questlog-tab-icon-quest", quests.activeAtlas)
assert(quests.inactiveAtlas == "questlog-tab-icon-quest-inactive", quests.inactiveAtlas)
assert(quests.checked, "the replacement Quests tab did not start checked")
assert(
	quests.points[1] == "TOPLEFT"
		and quests.points[2] == world.map
		and quests.points[3] == "TOPRIGHT"
		and quests.points[4] == 0
		and quests.points[5] == -7,
	"Quests tab anchor"
)

-- Order 10 sits above order 20 even though order 20 registered first.
assert(tabA.points[1] == "TOP" and tabA.points[2] == quests and tabA.points[3] == "BOTTOM", "order 10 anchor")
assert(tabA.points[4] == 0 and tabA.points[5] == -3, "order 10 gap")
assert(tabB.points[1] == "TOP" and tabB.points[2] == tabA and tabB.points[3] == "BOTTOM", "order 20 anchor")
assert(tabB.points[4] == 0 and tabB.points[5] == -3, "order 20 gap")

local map = world.map
local displayMode = map.displayMode
map.ContentFrames[1]:Show()
map.ContentFrames[2]:Show()

-- Selecting shows one panel, hides the quest log's pages and checks only the matching tab.
second.Select("a")
assert(first.Selected() == "a", first.Selected())
assert(panelA.shown and not panelB.shown, "panel visibility after Select(a)")
assert(not map.ContentFrames[1].shown and not map.ContentFrames[2].shown, "content frame left showing")
assert(tabA.checked and not tabB.checked and not quests.checked, "tab checks after Select(a)")
assert(map.displayMode == displayMode, "Select wrote Blizzard's displayMode")
assert(#map.sizeCalls == 0, "Select resized QuestMapFrame")
assert(#panelA.sizeCalls == 0 and #panelB.sizeCalls == 0, "Select resized a panel")

-- Switching away and back leaves the panels' own scroll offsets alone.
first.Select("b")
assert(panelB.shown and not panelA.shown, "panel visibility after Select(b)")
assert(tabB.checked and not tabA.checked, "tab checks after Select(b)")
first.Select("a")
assert(panelA.shown and not panelB.shown, "panel visibility after Select(a) again")
assert(panelA.scroll == 42, "the panel's scroll offset moved")

-- ShowQuests hides every panel and restores each content frame exactly as displayMode says.
map.displayMode = 2
first.ShowQuests()
assert(first.Selected() == nil, "a panel stayed selected")
assert(not panelA.shown and not panelB.shown, "a panel stayed shown")
assert(not map.ContentFrames[1].shown, "the quests page should be hidden in mode 2")
assert(map.ContentFrames[2].shown, "the legend page should be shown in mode 2")
assert(not tabA.checked and not tabB.checked, "an addon tab stayed checked")
assert(quests.checked, "the Quests tab was not checked")

-- The SetDisplayMode callback only returns to quests while one of our panels is selected.
map.displayMode = 1
map.ContentFrames[1]:Show()
map.ContentFrames[2]:Show()
_G.EventRegistry:TriggerEvent("QuestLog.SetDisplayMode", map.displayMode)
assert(map.ContentFrames[2].shown, "the callback restored the pages with no panel selected")
first.Select("a")
_G.EventRegistry:TriggerEvent("QuestLog.SetDisplayMode", map.displayMode)
assert(first.Selected() == nil, "the callback left a panel selected")
assert(map.ContentFrames[1].shown and not map.ContentFrames[2].shown, "the callback did not restore the pages")
assert(quests.checked, "the callback did not check the Quests tab")

-- The ShowQuestDetails hook does the same, for the tracked quest that asks for Quests mode unchanged.
assert(#world.hooks.QuestMapFrame_ShowQuestDetails == 1, "the quest details hook is not installed once")
local showQuestDetails = world.hooks.QuestMapFrame_ShowQuestDetails[1]
map.ContentFrames[2]:Show()
showQuestDetails()
assert(map.ContentFrames[2].shown, "the hook restored the pages with no panel selected")
first.Select("b")
showQuestDetails()
assert(first.Selected() == nil, "the hook left a panel selected")
assert(map.ContentFrames[1].shown and not map.ContentFrames[2].shown, "the hook did not restore the pages")

-- One key is one tab.
local ok, err = pcall(first.Register, "a", { name = "DuplicateTab", tooltip = "A", panel = panelA, order = 10 })
assert(not ok, "a duplicate key registered")
assert(tostring(err):find("already registered", 1, true), tostring(err))

-- Without the hidden stock tab there is no replacement, and the first addon tab hangs off the map's own last tab.
local openWorld = newWorld(false)
local nsC = {}
local api = load(nsC)
assert(_G.ForeverQuestLogTabs == api, "the new world did not publish its own API")
assert(_G.ForeverQuestLogQuestsTab == nil, "a replacement Quests tab exists with the stock one shown")
local openMap = openWorld.map
openMap.MapLegendTab:Show()
local panelC = newFrame("ForeverPanelC")
local tabC = api.Register("c", { name = "AddonCTab", tooltip = "C", panel = panelC, order = 10 })
assert(countCreated(openWorld, "ForeverQuestLogQuestsTab") == 0, "a replacement Quests tab was created")
assert(tabC.points[2] == openMap.MapLegendTab, "the first tab did not hang off the legend tab")
openMap.MapLegendTab:Hide()
local panelD = newFrame("ForeverPanelD")
local tabD = api.Register("d", { name = "AddonDTab", tooltip = "D", panel = panelD, order = 20 })
assert(tabC.points[2] == openMap.QuestsTab, "the first tab did not fall back to the Quests tab")
assert(tabD.points[2] == tabC, "the second tab did not follow the first")

-- With no replacement tab ShowQuests still restores the pages and checking it is a no-op.
api.Select("c")
assert(not openMap.ContentFrames[1].shown, "Select left a content frame showing")
api.ShowQuests()
assert(openMap.ContentFrames[1].shown, "the quests page did not come back")
assert(not openMap.ContentFrames[2].shown, "the legend page came back in the wrong mode")

-- `shown` reports each visibility change once, and the map's own callbacks tell a panel when it opens or closes,
-- so no frame under the world map needs an OnShow or OnHide script.
local eventWorld = newWorld(false)
local nsE = {}
local events = load(nsE)
assert(_G.ForeverQuestLogTabs == events, "the event world did not publish its own API")
local eventMap = eventWorld.map
local panelE = newFrame("ForeverPanelE")
local panelF = newFrame("ForeverPanelF")
local panelG = newFrame("ForeverPanelG")
local panelH = newFrame("ForeverPanelH")
local calls = {}
local function record(key)
	return function(visible)
		calls[#calls + 1] = { key = key, visible = visible }
	end
end
events.Register("e", { name = "AddonETab", tooltip = "E", panel = panelE, order = 10, shown = record("e") })
events.Register("f", { name = "AddonFTab", tooltip = "F", panel = panelF, order = 20, shown = record("f") })
assert(#calls == 0, "registering a tab reported a visibility change")

-- Selecting while the map is shown starts the panel's work.
eventWorld.worldMap:Show()
eventMap:Show()
events.Select("e")
assert(#calls == 1 and calls[1].key == "e" and calls[1].visible, "Select did not report the panel visible")

-- Switching stops the old panel before starting the new one, and selecting the same key reports nothing.
events.Select("f")
assert(#calls == 3, "switching did not report one change per panel")
assert(calls[2].key == "e" and not calls[2].visible, "the previous panel was not reported hidden")
assert(calls[3].key == "f" and calls[3].visible, "the new panel was not reported visible")
events.Select("f")
assert(#calls == 3, "Select reported an unchanged panel again")

-- ShowQuests hides the reported panel exactly once.
events.ShowQuests()
assert(#calls == 4 and calls[4].key == "f" and not calls[4].visible, "ShowQuests did not report the panel hidden")
events.ShowQuests()
assert(#calls == 4, "ShowQuests reported an already hidden panel again")

-- The paths that bring the stock pages back hide it too.
events.Select("e")
_G.EventRegistry:TriggerEvent("QuestLog.SetDisplayMode", eventMap.displayMode)
assert(#calls == 6 and calls[6].key == "e" and not calls[6].visible, "SetDisplayMode did not report the panel hidden")
events.Select("e")
assert(eventWorld.hooks.QuestMapFrame_ShowQuestDetails and #eventWorld.hooks.QuestMapFrame_ShowQuestDetails == 1)
eventWorld.hooks.QuestMapFrame_ShowQuestDetails[1]()
assert(#calls == 8 and calls[8].key == "e" and not calls[8].visible, "ShowQuestDetails did not report the panel hidden")

-- Closing the map through the panel manager hides the panel, and the same event again reports nothing.
events.Select("e")
assert(#calls == 9 and calls[9].key == "e" and calls[9].visible, "Select did not report the panel visible again")
_G.EventRegistry:TriggerEvent("UIParentPanelManager.HideUIPanel", eventWorld.worldMap, false)
assert(#calls == 10 and calls[10].key == "e" and not calls[10].visible, "HideUIPanel did not report the panel hidden")
_G.EventRegistry:TriggerEvent("UIParentPanelManager.HideUIPanel", eventWorld.worldMap, false)
assert(#calls == 10, "a second HideUIPanel reported again")

-- Another frame's show or hide says nothing about our panel, but ForcePanelHide on the map does.
events.Select("e")
assert(#calls == 11 and calls[11].key == "e" and calls[11].visible, "Select did not report the panel visible again")
_G.EventRegistry:TriggerEvent("UIParentPanelManager.HideUIPanel", {}, false)
_G.EventRegistry:TriggerEvent("UIParentPanelManager.ForcePanelHide", {})
assert(#calls == 11, "a panel event for another frame reported")
_G.EventRegistry:TriggerEvent("UIParentPanelManager.ForcePanelHide", eventWorld.worldMap)
assert(
	#calls == 12 and calls[12].key == "e" and not calls[12].visible,
	"ForcePanelHide did not report the panel hidden"
)

-- Opening the map with the tab still selected starts the panel's work again, once.
_G.EventRegistry:TriggerEvent("UIParentPanelManager.ShowUIPanel", eventWorld.worldMap, false, nil)
assert(#calls == 13 and calls[13].key == "e" and calls[13].visible, "ShowUIPanel did not report the panel visible")
_G.EventRegistry:TriggerEvent("UIParentPanelManager.ShowUIPanel", eventWorld.worldMap, false, nil)
_G.EventRegistry:TriggerEvent("UIParentPanelManager.ShowUIPanel", {})
assert(#calls == 13, "a second or unrelated ShowUIPanel reported again")

-- Closing the map after returning to the stock pages reports nothing, since no panel is visible.
events.ShowQuests()
assert(#calls == 14 and calls[14].key == "e" and not calls[14].visible, "ShowQuests did not report the panel hidden")
_G.EventRegistry:TriggerEvent("UIParentPanelManager.HideUIPanel", eventWorld.worldMap)
assert(#calls == 14, "a hide with no panel selected reported")

-- The quest log side panel collapsing or expanding is a visibility change too, through the client's
-- SetQuestLogPanelShown on the map.
events.Select("e")
assert(#calls == 15 and calls[15].key == "e" and calls[15].visible, "Select did not report the panel visible again")
eventWorld.worldMap:SetQuestLogPanelShown(false)
assert(
	#calls == 16 and calls[16].key == "e" and not calls[16].visible,
	"collapsing the side panel did not report the panel hidden"
)
eventWorld.worldMap:SetQuestLogPanelShown(true)
assert(
	#calls == 17 and calls[17].key == "e" and calls[17].visible,
	"expanding the side panel did not report the panel visible"
)

-- With the stock pages back, collapsing or expanding says nothing about a Forever panel.
events.ShowQuests()
assert(#calls == 18 and calls[18].key == "e" and not calls[18].visible, "ShowQuests did not report the panel hidden")
eventWorld.worldMap:SetQuestLogPanelShown(false)
assert(#calls == 18, "collapsing the side panel with Quests selected reported")
eventWorld.worldMap:SetQuestLogPanelShown(true)
assert(#calls == 18, "expanding the side panel with Quests selected reported")

-- Selecting while the side panel is collapsed waits for it to expand before reporting.
eventWorld.worldMap:SetQuestLogPanelShown(false)
events.Select("e")
assert(#calls == 18, "Select reported a panel the collapsed side panel hides")
eventWorld.worldMap:SetQuestLogPanelShown(true)
assert(
	#calls == 19 and calls[19].key == "e" and calls[19].visible,
	"expanding the side panel did not report the selected panel visible"
)

-- The map opening through the panel manager still says nothing while the side panel is collapsed.
eventWorld.worldMap:SetQuestLogPanelShown(false)
assert(
	#calls == 20 and calls[20].key == "e" and not calls[20].visible,
	"collapsing the side panel did not report the panel hidden"
)
_G.EventRegistry:TriggerEvent("UIParentPanelManager.ShowUIPanel", eventWorld.worldMap, false, nil)
assert(#calls == 20, "ShowUIPanel reported a panel the collapsed side panel hides")
eventWorld.worldMap:SetQuestLogPanelShown(true)
assert(
	#calls == 21 and calls[21].key == "e" and calls[21].visible,
	"expanding the side panel did not report the panel visible"
)
events.ShowQuests()
assert(#calls == 22 and calls[22].key == "e" and not calls[22].visible, "ShowQuests did not report the panel hidden")

-- A spec without `shown` registers and switches like any other.
events.Register("g", { name = "AddonGTab", tooltip = "G", panel = panelG, order = 30 })
events.Select("g")
assert(events.Selected() == "g" and panelG.shown, "a spec with no shown did not switch")
assert(#calls == 22, "a spec with no shown reported a visibility change")

-- A callback that errors does not break the module's own switching.
events.Register("h", {
	name = "AddonHTab",
	tooltip = "H",
	panel = panelH,
	order = 40,
	shown = function()
		error("panel callback failed")
	end,
})
events.Select("h")
assert(events.Selected() == "h" and panelH.shown and not panelG.shown, "a failing shown callback broke switching")
assert(#calls == 22, "a failing shown callback recorded a change")

-- Nothing the module created or was given carries a script under the world map.
local function assertNoShowScripts(frames)
	for _, frame in ipairs(frames) do
		assert(
			frame.scripts.OnShow == nil and frame.scripts.OnHide == nil,
			"a map child has a show script: " .. tostring(frame.name)
		)
		local hooks = frame.scriptHooks
		assert(not hooks.OnShow or #hooks.OnShow == 0, "a map child hooked OnShow: " .. tostring(frame.name))
		assert(not hooks.OnHide or #hooks.OnHide == 0, "a map child hooked OnHide: " .. tostring(frame.name))
	end
end

local allFrames = {}
for _, oneWorld in ipairs({ world, openWorld, eventWorld }) do
	allFrames[#allFrames + 1] = oneWorld.worldMap
	for _, frame in ipairs(oneWorld.created) do
		allFrames[#allFrames + 1] = frame
	end
end
for _, frame in ipairs({ panelA, panelB, panelC, panelD, panelE, panelF, panelG, panelH }) do
	allFrames[#allFrames + 1] = frame
end
assertNoShowScripts(allFrames)
