-- UI/ProfessionTabs.lua against a stub of the Professions window: two addons register a tab, selecting either shows one
-- page and checks one tab, a client tab or page hands the window back, and the window keeps one width and its anchor
-- across every switch and profession change.
local function newFrame(name, parent)
	local frame = {
		name = name,
		parent = parent,
		shown = false,
		checked = false,
		points = {},
		scripts = {},
		hooks = {},
		showCalls = 0,
		hideCalls = 0,
		widthCalls = 0,
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
		if value then
			self:Show()
		else
			self:Hide()
		end
	end
	function frame:IsShown()
		return self.shown
	end
	function frame:Show()
		self.shown = true
		self.showCalls = self.showCalls + 1
		if self.scripts.OnShow then
			self.scripts.OnShow(self)
		end
		for _, handler in ipairs(self.hooks.OnShow or {}) do
			handler(self)
		end
	end
	function frame:Hide()
		self.shown = false
		self.hideCalls = self.hideCalls + 1
		if self.scripts.OnHide then
			self.scripts.OnHide(self)
		end
		for _, handler in ipairs(self.hooks.OnHide or {}) do
			handler(self)
		end
	end
	function frame:SetChecked(value)
		self.checked = value == true
	end
	function frame:GetChecked()
		return self.checked
	end
	function frame:IsChecked()
		return self.checked
	end
	function frame:SetCustomOnMouseUpHandler(handler)
		self.mouseUpHandler = handler
	end
	function frame:SetFillToInterior(value)
		self.fillToInterior = value
	end
	function frame:EnableMouse(value)
		self.mouseEnabled = value
	end
	function frame:SetScript(script, handler)
		self.scripts[script] = handler
	end
	function frame:RegisterEvent(event)
		self.events = self.events or {}
		self.events[event] = true
	end
	function frame:UnregisterEvent(event)
		if self.events then
			self.events[event] = nil
		end
	end
	function frame:HookScript(script, handler)
		self.hooks[script] = self.hooks[script] or {}
		self.hooks[script][#self.hooks[script] + 1] = handler
	end
	function frame:SetWidth(value)
		self.width = value
		self.widthCalls = self.widthCalls + 1
		for _, handler in ipairs(self.hooks.OnSizeChanged or {}) do
			handler(self)
		end
	end
	function frame:GetWidth()
		return self.width or 0
	end
	function frame:SetHeight(value)
		self.height = value
	end
	function frame:GetHeight()
		return self.height or 0
	end
	return frame
end

local function newTexture()
	local texture = {}
	function texture:SetTexture(value)
		self.texture = value
	end
	return texture
end

-- A fresh client per scenario, so each world's ProfessionsFrame and named frames are independent.
local function newWorld()
	local pf = newFrame("ProfessionsFrame")
	pf:SetWidth(673)
	pf.points = { "TOPLEFT", "UIParent", "TOPLEFT", 0, 0 }

	local crafting = newFrame("CraftingPage", pf)
	crafting:SetWidth(782)
	crafting.shown = true
	local book = newFrame("BookPage", pf)
	book:SetWidth(782)
	local overview = newFrame("ProfessionsOverviewTab", pf)
	overview.checked = true
	local native1 = newFrame("Professions1Tab", pf)
	native1.checked = false
	native1.shown = true
	local native2 = newFrame("Professions2Tab", pf)
	native2.checked = false
	native2.shown = false

	pf.CraftingPage = crafting
	pf.BookPage = book
	pf.Pages = { crafting, book }
	pf.ProfessionsOverviewTab = overview
	pf.rightProfessionTabs = { native1, native2 }
	-- A native side tab checks itself and shows its page when the client runs its mouse-up. The module's hook on the
	-- same script hands our pages back.
	overview.OnMouseUp = function(self)
		self:SetChecked(true)
		book:Show()
	end
	native1.OnMouseUp = function(self)
		self:SetChecked(true)
		crafting:Show()
	end
	native2.OnMouseUp = native1.OnMouseUp

	local world = {
		frame = pf,
		crafting = crafting,
		book = book,
		overview = overview,
		native1 = native1,
		native2 = native2,
		created = {},
		callbacks = {},
	}
	_G.ProfessionsFrame = pf
	_G.InCombatLockdown = function()
		return world.combat == true
	end
	_G.CreateFrame = function(frameType, frameName, parent, template)
		local frame = newFrame(frameName, parent)
		frame.frameType = frameType
		frame.template = template
		frame.Icon = newTexture()
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
	_G.securecallfunction = function(fn, ...)
		return pcall(fn, ...)
	end
	return world
end

local function load(ns)
	assert(loadfile("UI/ProfessionTabs.lua"))("Addon", ns)
	return ns.ProfessionTabs
end

local function assertOnePage(shown, hidden, label)
	assert(shown.shown, label .. ": the selected page is hidden")
	assert(not hidden.shown, label .. ": another page stayed shown")
end

-- A mouse-up on a client side tab: its own script runs, then the module's hook on the same script.
local function pressNative(tab)
	tab:SetChecked(false)
	tab.OnMouseUp(tab, "LeftButton", true)
	for _, handler in ipairs(tab.hooks.OnMouseUp or {}) do
		handler(tab)
	end
end

local function assertWidthAndAnchor(world, width, point, label)
	assert(world.frame:GetWidth() == width, label .. ": the window width changed: " .. tostring(world.frame:GetWidth()))
	local actual = { world.frame:GetPoint() }
	assert(#actual == #point, label .. ": the window anchor point changed")
	for index = 1, #point do
		assert(actual[index] == point[index], label .. ": the window anchor changed at " .. index)
	end
end

local world = newWorld()
local ns = {}
local api = load(ns)
assert(api, "no profession tabs API")
assert(api.minor == 1, "the module's minor is 1")

local pageA = newFrame("ForeverCommissionsPage")
local pageB = newFrame("ForeverSkillUpPage")
local selected = {}
local tabA = api.Register("commissions", {
	icon = "Interface\\Icons\\INV_Misc_Note_01",
	tooltip = "Commissions Forever",
	page = pageA,
	onSelect = function(key)
		selected[#selected + 1] = key
	end,
})
local tabB = api.Register("skillup", {
	icon = "Interface\\Icons\\INV_Scroll_03",
	tooltip = "SkillUp",
	page = pageB,
	minWidth = 900,
	onSelect = function(key)
		selected[#selected + 1] = key
	end,
})

-- One tab per key, built the way the client builds its own side tabs.
assert(tabA ~= tabB, "both keys share one tab")
assert(tabA.frameType == "Button" and tabB.frameType == "Button", "a tab was not created as a Button")
assert(tabA.template == "LargeSideTabButtonTemplate" and tabB.template == "LargeSideTabButtonTemplate", "tab template")
assert(tabA.parent == world.frame and tabB.parent == world.frame, "a tab is not parented to ProfessionsFrame")
assert(tabA.Icon.texture == "Interface\\Icons\\INV_Misc_Note_01", "Commissions tab icon")
assert(tabB.Icon.texture == "Interface\\Icons\\INV_Scroll_03", "SkillUp tab icon")
assert(tabA.tooltipText == "Commissions Forever" and tabB.tooltipText == "SkillUp", "tab tooltip")
assert(tabA.fillToInterior and tabB.fillToInterior, "a tab did not fill its interior")
assert(not tabA.checked and not tabB.checked, "an addon tab was created checked")
assert(api.Selected() == nil, "a tab started selected")

-- The column starts under the last client side tab that is shown, then runs in registration order.
assert(tabA.points[1] == "TOPLEFT" and tabA.points[2] == world.native1 and tabA.points[3] == "BOTTOMLEFT")
assert(tabA.points[4] == 0 and tabA.points[5] == -2, "first tab gap")
assert(tabB.points[1] == "TOPLEFT" and tabB.points[2] == tabA and tabB.points[3] == "BOTTOMLEFT")
assert(tabB.points[4] == 0 and tabB.points[5] == -2, "second tab gap")

-- One width for every profession and tab, raised by the largest registration. The anchor never moves.
local width = 900
local point = { world.frame:GetPoint() }
assertWidthAndAnchor(world, width, point, "after registering both tabs")
assert(world.frame.widthCalls > 0, "the window width was never set")

-- Selecting a tab shows one page, checks one tab and unchecks every client tab.
api.Select("commissions")
assert(api.Selected() == "commissions", api.Selected())
assertOnePage(pageA, pageB, "Select(commissions)")
assert(tabA.checked and not tabB.checked, "tab checks after Select(commissions)")
assert(not world.overview.checked, "the client's overview tab stayed checked")
assert(not world.native1.checked and not world.native2.checked, "a client profession tab stayed checked")
assert(#selected == 1 and selected[1] == "commissions", "onSelect did not run with the key")
assertWidthAndAnchor(world, width, point, "after Select(commissions)")

-- Switching shows exactly the other page.
api.Select("skillup")
assertOnePage(pageB, pageA, "Select(skillup)")
assert(tabB.checked and not tabA.checked, "tab checks after Select(skillup)")
assert(not world.overview.checked and not world.native1.checked and not world.native2.checked, "a client tab checked")
assert(#selected == 2 and selected[2] == "skillup", "onSelect did not run for the second tab")
assertWidthAndAnchor(world, width, point, "after Select(skillup)")

-- A client side tab hands the window back: every registered page hides and every registered tab unchecks.
pressNative(world.native1)
assert(world.native1.checked, "the client tab did not check itself")
assert(not pageA.shown and not pageB.shown, "a registered page stayed shown after a client tab")
assert(not tabA.checked and not tabB.checked, "a registered tab stayed checked after a client tab")
assert(api.Selected() == nil, "a tab stayed selected after a client tab")
assertWidthAndAnchor(world, width, point, "after a client tab")

-- And back to a registered tab, then a client page: the client's own page shows and ours hide, never the other way.
api.Select("commissions")
assertOnePage(pageA, pageB, "Select(commissions) again")
world.book:Show()
assert(world.book.shown, "the client page was hidden by the module")
assert(not pageA.shown and not pageB.shown, "a registered page stayed shown after a client page")
assert(not tabA.checked and not tabB.checked, "a registered tab stayed checked after a client page")
assert(api.Selected() == nil, "a tab stayed selected after a client page")
assertWidthAndAnchor(world, width, point, "after a client page")

-- A profession change resizes the window through the client's own path. The fixed width comes back from
-- OnSizeChanged and the events, and the anchor stays where it was.
api.Select("skillup")
world.native1:Hide()
world.native2:Show()
world.frame:SetWidth(600)
assert(world.frame:GetWidth() == width, "OnSizeChanged did not restore the fixed width")
_G.EventRegistry:TriggerEvent("Professions.ProfessionSelected", { professionID = 2 })
_G.EventRegistry:TriggerEvent("ProfessionsFrame.TabSet", world.frame, 2)
_G.EventRegistry:TriggerEvent("ProfessionsFrame.Show", world.frame)
assertWidthAndAnchor(world, width, point, "after a profession change")
assertOnePage(pageB, pageA, "after a profession change")

-- The client column changed, so our tabs moved, not the window: the first follows the last shown client tab and the
-- second follows the first.
assert(tabA.points[2] == world.native2, "the first tab did not follow the last shown client tab")
assert(tabB.points[2] == tabA, "the second tab did not follow the first")

-- A registration can raise its minWidth after it registered: the one window width changes at once and stays through a
-- tab switch.
api.SetMinWidth("skillup", 1050)
width = 1050
assertWidthAndAnchor(world, width, point, "after raising a minWidth")
api.Select("commissions")
assertWidthAndAnchor(world, width, point, "after a tab switch at the raised minWidth")
api.Select("skillup")

-- Lowering one registration leaves the largest of the rest; nil clears it and the window returns to the client's own
-- width. A minWidth below that width never shrinks it.
api.SetMinWidth("commissions", 800)
assertWidthAndAnchor(world, width, point, "after a lower minWidth under another registration")
api.SetMinWidth("skillup", nil)
width = 800
assertWidthAndAnchor(world, width, point, "after clearing the largest minWidth")
api.SetMinWidth("commissions", 673)
width = 673
assertWidthAndAnchor(world, width, point, "after lowering a minWidth to the client width")
api.SetMinWidth("commissions", nil)
assertWidthAndAnchor(world, width, point, "after clearing every minWidth")

-- The client page and its own tabs were never hidden by the module; the only shows are the client's own, run by the
-- spec's mouse-up and page show.
assert(world.crafting.hideCalls == 0, "the module hid the client crafting page")
assert(world.book.hideCalls == 0, "the module hid the client book page")
assert(world.crafting.showCalls == 1, "the module showed or hid the client crafting page")
assert(world.book.showCalls == 1, "the module showed or hid the client book page")

-- The module's own handback is the same one a client tab or page runs.
api.ShowNative()
assert(not pageA.shown and not pageB.shown, "ShowNative left a registered page shown")
assert(not tabA.checked and not tabB.checked, "ShowNative left a registered tab checked")
assert(api.Selected() == nil, "ShowNative left a tab selected")

-- One key is one tab.
local ok, err = pcall(api.Register, "commissions", { icon = "x", tooltip = "Duplicate", page = pageA })
assert(not ok, "a duplicate key registered")
assert(tostring(err):find("already registered", 1, true), tostring(err))

-- An unknown key is a caller error, raised at the calling line.
ok, err = pcall(api.SetMinWidth, "missing", 900)
assert(not ok, "an unknown key changed a minWidth")
assert(tostring(err):find("not registered", 1, true), tostring(err))

-- A callback that errors does not break the module's own switching, and runs in the addon's SafeCall when registered.
local safeCalls = {}
local pageC = newFrame("ForeverFailingPage")
api.Register("failing", {
	icon = "Interface\\Icons\\INV_Misc_QuestionMark",
	tooltip = "Failing",
	page = pageC,
	onSelect = function()
		error("tab callback failed")
	end,
	safeCall = function(label, fn, ...)
		safeCalls[#safeCalls + 1] = label
		return pcall(fn, ...)
	end,
})
api.Select("failing")
assert(api.Selected() == "failing" and pageC.shown, "a failing onSelect broke switching")
assert(#safeCalls > 0 and safeCalls[#safeCalls] == "profession tab selected", "onSelect did not use its SafeCall")

-- In combat the tab state changes at once, but the pages and the width wait for the client to leave it.
api.ShowNative()
world.combat = true
api.Select("commissions")
assert(tabA.checked and not tabB.checked, "a combat selection did not check its tab")
assert(not pageA.shown and not pageB.shown, "a combat selection showed a page")
api.SetMinWidth("commissions", 1200)
assertWidthAndAnchor(world, width, point, "a combat minWidth changed the window at once")
local combatWatcher
for _, frame in ipairs(world.created) do
	if frame.events and frame.events.PLAYER_REGEN_ENABLED then
		combatWatcher = frame
	end
end
assert(combatWatcher, "a combat selection did not wait for combat to end")
world.combat = false
combatWatcher.scripts.OnEvent(combatWatcher, "PLAYER_REGEN_ENABLED")
assert(not pageB.shown and pageA.shown, "leaving combat did not show the selected page")
assertWidthAndAnchor(world, 1200, point, "leaving combat did not apply the combat minWidth")
assert(not combatWatcher.events.PLAYER_REGEN_ENABLED, "the combat watcher stayed registered")
api.SetMinWidth("commissions", nil)
assertWidthAndAnchor(world, 673, point, "clearing the combat minWidth did not restore the client width")

-- A registration made before the client has laid its crafting page out keeps no width yet: the engine's width is
-- read once the page is shown, and only then is the largest minWidth applied.
local late = newWorld()
late.crafting.shown = false
local lateWidthCalls = late.frame.widthCalls
local lateNs = {}
local lateApi = load(lateNs)
lateApi.Register("late", {
	icon = "Interface\\Icons\\INV_Misc_Note_02",
	tooltip = "Late",
	page = newFrame("ForeverLatePage"),
	minWidth = 900,
})
assert(late.frame:GetWidth() == 673, "the module set a width before the client laid its crafting page out")
assert(late.frame.widthCalls == lateWidthCalls, "the module wrote the window width before the engine's width was known")
late.crafting:Show()
assert(late.frame:GetWidth() == 900, "the module did not take the width once the client laid its page out")

print("profession_tabs_spec: ok")
