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
	local world = { map = map, created = {}, callbacks = {}, hooks = {} }

	_G.QuestMapFrame = map
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
				entry.callback(...)
			end
		end,
	}
	_G.hooksecurefunc = function(name, callback)
		world.hooks[name] = world.hooks[name] or {}
		world.hooks[name][#world.hooks[name] + 1] = callback
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
