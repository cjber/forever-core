-- UI/ProfessionTabs.lua against a stub of the Professions window: two addons register a tab, selecting either shows one
-- page and checks one tab, a client tab or page hands the window back, and the window keeps one width and its anchor
-- across every switch and profession change, except on the client's book page, which keeps the client's own width.
-- Frames carry a real rectangle from their point chain, so a placement is checked where it lands and a side tab another
-- addon put in the same column is an overlap rather than a point string.

-- Where a frame lands: the parent's corner named by its point, the point's offsets, then the frame's own width and
-- height back to its top-left. A frame with no points is placed by its own left and top.
local corner
local function rect(frame, depth)
	if not frame or (depth or 0) > 8 then
		return nil
	end
	if not frame.points[1] then
		return frame.left, frame.top
	end
	local point, relativeTo, relativePoint, x, y = unpack(frame.points)
	local anchorLeft, anchorTop = corner(relativeTo, relativePoint)
	if not anchorLeft then
		return nil
	end
	local left, top = anchorLeft + (x or 0), anchorTop + (y or 0)
	local width, height = frame:GetWidth(), frame:GetHeight()
	if point == "TOPLEFT" then
		return left, top
	elseif point == "TOPRIGHT" then
		return left - width, top
	elseif point == "BOTTOMLEFT" then
		return left, top + height
	elseif point == "BOTTOMRIGHT" then
		return left - width, top + height
	end
	return nil
end
corner = function(frame, point)
	local left, top = rect(frame)
	if not left then
		return nil
	end
	local width, height = frame:GetWidth(), frame:GetHeight()
	if point == "TOPLEFT" then
		return left, top
	elseif point == "TOPRIGHT" then
		return left + width, top
	elseif point == "BOTTOMLEFT" then
		return left, top - height
	elseif point == "BOTTOMRIGHT" then
		return left + width, top - height
	end
	return nil
end

local function newFrame(name, parent)
	local frame = {
		name = name,
		parent = parent,
		shown = false,
		checked = false,
		points = {},
		scripts = {},
		hooks = {},
		children = {},
		showCalls = 0,
		hideCalls = 0,
		widthCalls = 0,
		alpha = 1,
		width = 32,
		height = 40,
	}
	if parent then
		parent.children[#parent.children + 1] = frame
	end
	function frame:SetPoint(...)
		self.points = { ... }
	end
	function frame:GetNumPoints()
		return #self.points > 0 and 1 or 0
	end
	function frame:GetPoint(index)
		if (index or 1) ~= 1 or not self.points[1] then
			return nil
		end
		return unpack(self.points)
	end
	function frame:ClearAllPoints()
		self.points = {}
	end
	function frame:GetParent()
		return self.parent
	end
	function frame:SetParent(value)
		local old = self.parent
		if old then
			for index = #old.children, 1, -1 do
				if old.children[index] == self then
					table.remove(old.children, index)
				end
			end
		end
		self.parent = value
		if value then
			value.children[#value.children + 1] = self
		end
	end
	function frame:GetChildren()
		return unpack(self.children)
	end
	function frame:GetLeft()
		local left = rect(self)
		return left
	end
	function frame:GetTop()
		local _, top = rect(self)
		return top
	end
	function frame:GetRight()
		local left = rect(self)
		if not left then
			return nil
		end
		return left + self:GetWidth()
	end
	function frame:GetBottom()
		local _, top = rect(self)
		if not top then
			return nil
		end
		return top - self:GetHeight()
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
	function frame:SetAlpha(value)
		self.alpha = value
	end
	function frame:GetAlpha()
		return self.alpha
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

-- A fresh client per scenario, so each world's ProfessionsFrame and named frames are independent. The window sits at
-- the screen's top-left, the client's own side tabs hang down its right edge 40 units tall with a 2 unit gap, and the
-- pages take the window's own rectangle, as the client lays them out.
local function newWorld()
	local screen = newFrame("UIParent")
	screen.left, screen.top = 0, 0
	screen:SetWidth(1024)
	screen:SetHeight(768)

	local pf = newFrame("ProfessionsFrame")
	pf:SetWidth(673)
	pf:SetHeight(600)
	pf.currentPageWidth = 673
	pf:SetPoint("TOPLEFT", screen, "TOPLEFT", 0, 0)

	local crafting = newFrame("CraftingPage", pf)
	crafting:SetWidth(673)
	crafting:SetHeight(560)
	crafting:SetPoint("TOPLEFT", pf, "TOPLEFT", 0, -40)
	crafting.shown = true
	local book = newFrame("BookPage", pf)
	book:SetWidth(673)
	book:SetHeight(560)
	book:SetPoint("TOPLEFT", pf, "TOPLEFT", 0, -40)
	local overview = newFrame("ProfessionsOverviewTab", pf)
	overview:SetWidth(32)
	overview:SetHeight(40)
	overview:SetPoint("TOPLEFT", pf, "TOPRIGHT", 0, -100)
	overview.checked = true
	local native1 = newFrame("Professions1Tab", pf)
	native1:SetWidth(32)
	native1:SetHeight(40)
	native1:SetPoint("TOPLEFT", overview, "BOTTOMLEFT", 0, -2)
	native1.checked = false
	native1.shown = true
	local native2 = newFrame("Professions2Tab", pf)
	native2:SetWidth(32)
	native2:SetHeight(40)
	native2:SetPoint("TOPLEFT", native1, "BOTTOMLEFT", 0, -2)
	native2.checked = false
	native2.shown = false

	pf.CraftingPage = crafting
	pf.BookPage = book
	pf.Pages = { crafting, book }
	pf.ProfessionsOverviewTab = overview
	pf.rightProfessionTabs = { native1, native2 }
	-- A native side tab checks itself and shows its page when the client runs its mouse-up. The module's hook on the
	-- same script hands our pages back.
	-- Camelot side tabs return both native pages to the 673-unit host.
	overview.OnMouseUp = function(self)
		self:SetChecked(true)
		book:Show()
		crafting:Hide()
		pf:SetWidth(673)
		pf.currentPageWidth = 673
	end
	native1.OnMouseUp = function(self)
		self:SetChecked(true)
		crafting:Show()
		book:Hide()
		pf:SetWidth(673)
		pf.currentPageWidth = 673
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
		timers = {},
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
	-- The module places its column again on the next frame; the world holds those callbacks until a check runs them.
	_G.C_Timer = {
		After = function(_, callback)
			world.timers[#world.timers + 1] = callback
		end,
	}
	return world
end

local function load(ns)
	assert(loadfile("UI/ProfessionTabs.lua"))("Addon", ns)
	return ns.ProfessionTabs
end

-- The client's next frame: the callbacks C_Timer.After queued run in order.
local function runNextFrame(world)
	local timers = world.timers
	world.timers = {}
	for _, callback in ipairs(timers) do
		callback()
	end
end

-- Two frames share surface where they currently sit.
local function overlaps(a, b)
	local left, right, top, bottom = a:GetLeft(), a:GetRight(), a:GetTop(), a:GetBottom()
	local otherLeft, otherRight, otherTop, otherBottom = b:GetLeft(), b:GetRight(), b:GetTop(), b:GetBottom()
	if not (left and right and top and bottom and otherLeft and otherRight and otherTop and otherBottom) then
		return false
	end
	return right > otherLeft and left < otherRight and top > otherBottom and bottom < otherTop
end

-- One registration, with a page of its own, in a world of its own.
local function registerOne(api, key)
	local page = newFrame("Page" .. key)
	return api.Register(key, { icon = "Interface\\Icons\\INV_Misc_Note_01", tooltip = key, page = page })
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
-- Minor 2 is the native-page hiding contract: an addon can tell a core that hides the native profession pages beneath
-- its selected page (and restores them on hand-back) from the older core that drew over them.
assert(api.minor == 2, "the module's minor is 2")

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

-- Registration does not widen the native page. Selecting a custom page raises the window to the largest registered
-- minimum, and the anchor never moves.
local width = 673
local point = { world.frame:GetPoint() }
assertWidthAndAnchor(world, width, point, "after registering both tabs")
assert(world.frame.widthCalls > 0, "the window width was never set")

-- Selecting a tab shows one page, checks one tab and unchecks every client tab.
world.crafting:SetAlpha(0.4)
api.Select("commissions")
width = 900
assert(api.Selected() == "commissions", api.Selected())
assertOnePage(pageA, pageB, "Select(commissions)")
assert(tabA.checked and not tabB.checked, "tab checks after Select(commissions)")
assert(not world.overview.checked, "the client's overview tab stayed checked")
assert(not world.native1.checked and not world.native2.checked, "a client profession tab stayed checked")
assert(
	(not world.crafting.shown or world.crafting:GetAlpha() == 0)
		and (not world.book.shown or world.book:GetAlpha() == 0),
	"native profession controls stayed visible under the custom page"
)
assert(#selected == 1 and selected[1] == "commissions", "onSelect did not run with the key")
assertWidthAndAnchor(world, width, point, "after Select(commissions)")
api.ShowNative()
assert(world.crafting:GetAlpha() == 0.4, "handing back to native did not restore the native crafting page")

-- Switching shows exactly the other page.
api.Select("skillup")
assertOnePage(pageB, pageA, "Select(skillup)")
assert(tabB.checked and not tabA.checked, "tab checks after Select(skillup)")
assert(not world.overview.checked and not world.native1.checked and not world.native2.checked, "a client tab checked")
assert(
	(not world.crafting.shown or world.crafting:GetAlpha() == 0)
		and (not world.book.shown or world.book:GetAlpha() == 0),
	"native profession page stayed visible under the second custom page"
)
assert(#selected == 2 and selected[2] == "skillup", "onSelect did not run for the second tab")
assertWidthAndAnchor(world, width, point, "after Select(skillup)")

-- A client side tab hands the window back: every registered page hides and every registered tab unchecks.
pressNative(world.native1)
width = 673
assert(world.native1.checked, "the client tab did not check itself")
assert(not pageA.shown and not pageB.shown, "a registered page stayed shown after a client tab")
assert(not tabA.checked and not tabB.checked, "a registered tab stayed checked after a client tab")
assert(api.Selected() == nil, "a tab stayed selected after a client tab")
assertWidthAndAnchor(world, width, point, "after a client tab")

-- And back to a registered tab, then a client page: the client's own page shows and ours hide, never the other way.
api.Select("commissions")
assertOnePage(pageA, pageB, "Select(commissions) again")
pressNative(world.overview)
assert(world.book.shown, "the client page was hidden by the module")
assert(not pageA.shown and not pageB.shown, "a registered page stayed shown after a client page")
assert(not tabA.checked and not tabB.checked, "a registered tab stayed checked after a client page")
assert(api.Selected() == nil, "a tab stayed selected after a client page")

-- The book page lays its panels out at the client's own width, so it keeps that width rather than the fixed one;
-- a registered page over it, and the crafting page after it, take the fixed width again.
assertWidthAndAnchor(world, 673, point, "on the client's book page")
api.Select("skillup")
width = 900
assertWidthAndAnchor(world, width, point, "a registered page over the book page")
pressNative(world.overview)
assertWidthAndAnchor(world, 673, point, "back on the book page from a registered page")
pressNative(world.native1)
assertWidthAndAnchor(world, 673, point, "the crafting page after the book page")

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
width = 850
assertWidthAndAnchor(world, width, point, "after clearing the largest minWidth")
api.SetMinWidth("commissions", 673)
width = 850
assertWidthAndAnchor(world, width, point, "after lowering a minWidth below the shared custom width")
api.SetMinWidth("commissions", nil)
assertWidthAndAnchor(world, width, point, "after clearing every minWidth")

-- Selecting a custom page hides the native page beneath it; native clicks still own restoration.
assert(
	not world.crafting.shown or world.crafting:GetAlpha() == 0,
	"the native crafting controls were not cleared under custom pages"
)
assert(
	not world.book.shown or world.book:GetAlpha() == 0,
	"the native book controls were not cleared under custom pages"
)

-- The module's own handback is the same one a client tab or page runs.
api.ShowNative()
assert(world.crafting:GetAlpha() == 0.4, "native crafting alpha was not preserved across handback")
assert(not pageA.shown and not pageB.shown, "ShowNative left a registered page shown")
assert(not tabA.checked and not tabB.checked, "ShowNative left a registered tab checked")
assert(api.Selected() == nil, "ShowNative left a tab selected")

-- A native crafting page keeps the client's width even when a registered page's minimum is larger. The wider
-- width belongs only to a selected custom page, not to the native page after handback.
pressNative(world.native1)
api.SetMinWidth("commissions", 1050)
assert(world.frame:GetWidth() == 673, "a native crafting page inherited a custom page's dead width")
api.SetMinWidth("commissions", nil)
assert(world.frame:GetWidth() == 673, "clearing a native dead width did not keep the client width")

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
assertWidthAndAnchor(world, 673, point, "a combat minWidth changed the window at once")
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
assertWidthAndAnchor(world, 850, point, "clearing the combat minWidth did not restore the custom base width")

-- Registration leaves native geometry untouched; selecting the custom page applies its requested minimum.
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
assert(late.frame.widthCalls == lateWidthCalls, "registration rewrote the native width")
late.crafting:Show()
lateApi.Select("late")
assert(late.frame:GetWidth() == 900, "the module did not take the width once the client laid its page out")

-- The overview can be the first page opened. Custom sizing must not depend on visiting crafting first.
local overviewFirst = newWorld()
overviewFirst.crafting.shown = false
overviewFirst.book.shown = true
local firstApi = load({})
firstApi.Register("skillup", { icon = "x", tooltip = "SkillUp", page = newFrame("FirstSkillUp") })
firstApi.Register("commissions", { icon = "x", tooltip = "Commissions", page = newFrame("FirstCommissions") })
firstApi.Select("skillup")
assert(overviewFirst.frame:GetWidth() == 850, "overview-first SkillUp missed the shared width")
firstApi.Select("commissions")
assert(overviewFirst.frame:GetWidth() == 850, "Commissions changed the shared width")
firstApi.ShowNative()
assert(overviewFirst.frame:GetWidth() == 673, "overview handback retained the custom width")

-- Optional client pages can be absent on a build. A shown BookPage must still step aside when CraftingPage is nil.
local optional = newWorld()
optional.frame.CraftingPage = nil
optional.frame.Pages = { optional.book }
optional.book:Show()
local optionalApi = load({})
optionalApi.Register("optional", {
	icon = "Interface\\Icons\\INV_Misc_Note_03",
	tooltip = "Optional",
	page = newFrame("ForeverOptionalPage"),
})
optionalApi.Select("optional")
assert(optional.book:GetAlpha() == 0, "a shown optional native page stayed visible when CraftingPage was absent")
optionalApi.ShowNative()
assert(optional.book:GetAlpha() == 1, "the optional native page was not restored after handback")

-- With no other addon's tab in the column, the placement is exactly the client column's own: the first tab under the
-- last shown native tab, the next under the first.
local alone = newWorld()
local aloneApi = load({})
local aloneTab = registerOne(aloneApi, "alone")
assert(aloneTab.points[1] == "TOPLEFT" and aloneTab.points[2] == alone.native1, "the free slot moved the first tab")
assert(aloneTab.points[3] == "BOTTOMLEFT" and aloneTab.points[4] == 0 and aloneTab.points[5] == -2, "the free slot gap")
assert(aloneTab:GetTop() == alone.native1:GetBottom() - 2, "the first tab did not land directly under the native tab")

-- A side tab another addon anchors under the last native tab at the same 2 unit gap, as the recipe list addon does.
-- Ours steps below it instead of landing on top of it: a player must be able to click ours.
local ackis = newWorld()
local ackisForeign = newFrame("AckisProfessionTab", ackis.frame)
ackisForeign:SetWidth(32)
ackisForeign:SetHeight(40)
ackisForeign:SetPoint("TOPLEFT", ackis.native1, "BOTTOMLEFT", 0, -2)
ackisForeign:Show()
local ackisApi = load({})
local ackisTab = registerOne(ackisApi, "skillup")
assert(ackisTab.points[2] == ackisForeign, "our first tab did not step under the recipe list tab")
assert(ackisTab.points[4] == 0 and ackisTab.points[5] == -2, "the step under the recipe list tab was not the same gap")
assert(not overlaps(ackisTab, ackisForeign), "the recipe list tab still covers ours")

-- A tab collector reparents the client's own tabs into a sidebar of its own and puts its tab over the first hidden
-- native slot. The native tab's parent is read from the window, so its tab is still found and ours steps below it.
local att = newWorld()
local sidebar = newFrame("ProfessionsFrameTabSideBar", att.frame)
sidebar:SetWidth(32)
sidebar:SetHeight(40 * 3 + 4)
sidebar:SetPoint("TOPLEFT", att.overview, "TOPLEFT", 0, 0)
sidebar:Show()
att.overview:SetParent(sidebar)
att.native1:SetParent(sidebar)
att.native2:SetParent(sidebar)
local attForeign = newFrame("CollectedProfessionTab", sidebar)
attForeign:SetWidth(32)
attForeign:SetHeight(40)
attForeign:SetPoint("TOPLEFT", att.native2, "TOPLEFT", 0, 0)
attForeign:Show()
local attApi = load({})
local attTab = registerOne(attApi, "skillup")
assert(attTab.points[2] == attForeign, "our first tab did not step under the sidebar's tab")
assert(not overlaps(attTab, attForeign), "the sidebar's tab still covers ours")
assert(attTab:GetTop() < attForeign:GetBottom(), "our first tab landed on the sidebar's tab")

-- The other addon places its tab from the same layout event and may run after the module: the next-frame pass reads
-- that placement from the window and steps the column below it.
local later = newWorld()
local laterApi = load({})
local laterTab = registerOne(laterApi, "skillup")
_G.EventRegistry:TriggerEvent("ProfessionsFrame.TabSet", later.frame, 2)
_G.EventRegistry:TriggerEvent("ProfessionsFrame.Show", later.frame)
assert(#later.timers == 1, "several layout triggers in one frame queued more than one placement")
local laterForeign = newFrame("LateProfessionTab", later.frame)
laterForeign:SetWidth(32)
laterForeign:SetHeight(40)
laterForeign:SetPoint("TOPLEFT", later.native1, "BOTTOMLEFT", 0, -2)
laterForeign:Show()
assert(overlaps(laterTab, laterForeign), "the late tab did not land in our slot")
runNextFrame(later)
assert(laterTab.points[2] == laterForeign, "the next-frame pass did not step under the late tab")
assert(not overlaps(laterTab, laterForeign), "the late tab still covers ours after the next frame")

-- A side tab hanging off our own tab is not a slot: anchoring to it would make the two anchors a loop.
local hanging = newWorld()
local hangingApi = load({})
local hangingTab = registerOne(hangingApi, "skillup")
local hangingForeign = newFrame("HangingProfessionTab", hanging.frame)
hangingForeign:SetWidth(32)
hangingForeign:SetHeight(40)
hangingForeign:SetPoint("TOPLEFT", hangingTab, "BOTTOMLEFT", 0, -2)
hangingForeign:Show()
_G.EventRegistry:TriggerEvent("ProfessionsFrame.TabSet", hanging.frame, 2)
assert(hangingTab.points[2] == hanging.native1, "a tab hanging off ours was used as the anchor")
assert(hangingTab.points[2] ~= hangingForeign, "the column anchored to a tab that hangs off it")

print("profession_tabs_spec: ok")
