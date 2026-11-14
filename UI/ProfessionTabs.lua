---@type string, table
local _, ns = ...

-- A shared side tab for the addon pages that live in the Professions window. Each addon registers a key, its page and
-- a tab; core places every tab under the client's own side tabs in registration order, and selecting one shows that
-- page in place of the others. Native pages stay in Blizzard's ownership, so the client keeps its own page and
-- gamepad bookkeeping; custom pages are alpha-hidden around the native page while selected. The window uses the
-- custom width only while a custom page is selected; native pages keep the client's own width.

---@class ForeverProfessionTabEntry
---@field key string
---@field spec ForeverProfessionTabSpec
---@field tab ForeverProfessionTab

-- The registry is addon state: nothing of Blizzard's reads it.
---@type table<string, ForeverProfessionTabEntry>
local tabs = {}
---@type ForeverProfessionTabEntry[]
local order = {}
local selectedKey
local installed = false

-- Custom profession pages share the approved 850-unit layout, independent of native page history.
local CUSTOM_WIDTH = 850
local fixedWidth = CUSTOM_WIDTH
local enforcingWidth = false

-- Frame work waits for combat to end, the way UI/TrackerQuests.lua does: a protected native window, or an addon page
-- with a secure child, refuses SetWidth and Show/Hide under our taint.
local pending = false
---@type Frame[]
local hiddenNativePages = {}
---@type table<Frame, number>
local nativePageAlpha = {}
---@type Frame?
local watcher

local Queue
local EnforceWidth
local ApplyPages
local RecomputeWidth
local Anchor

-- One pending next-frame placement at a time, however many layout triggers ask for it.
local anchorQueued = false

-- The client loads Blizzard_Professions on demand, so the window is read at call time, never captured at load. The
-- width reads may run before the client has built it; the install paths run only once an addon registers a tab,
-- which needs the client's window already built.
---@return ForeverProfessionsWindow?
local function Window()
	return _G.ProfessionsFrame --[[@as ForeverProfessionsWindow?]]
end

---@return boolean
local function Locked()
	return type(InCombatLockdown) == "function" and InCombatLockdown() == true
end

-- All registered pages share one width. A consumer can request more room, but selection never changes it.
RecomputeWidth = function()
	local width = CUSTOM_WIDTH
	for _, entry in ipairs(order) do
		local minWidth = entry.spec.minWidth
		if type(minWidth) == "number" and minWidth > width then
			width = minWidth
		end
	end
	fixedWidth = width
end

-- Camelot/Blizzard_ProfessionsFrame.xml owns the native 673-unit host. Its side-tab path bypasses the
-- upstream desired-width getter, so custom handback restores that native width without calling Blizzard Lua.
---@return number
local function TargetWidth()
	return selectedKey and fixedWidth or 673
end

EnforceWidth = function()
	local window = Window()
	if not fixedWidth or not window or enforcingWidth then
		return
	end
	local target = TargetWidth()
	if not target then
		return
	end
	if Locked() then
		Queue()
		return
	end
	local current = window:GetWidth()
	if type(current) ~= "number" or math.abs(current - target) > 0.5 then
		enforcingWidth = true
		window:SetWidth(target)
		enforcingWidth = false
	end
end

-- Show or hide the registered pages. When a custom page is selected it occupies the native page's slot, so the
-- currently shown native pages must step aside or their controls remain visible underneath the addon page.
local function HideNativePages()
	local window = Window()
	if not window then
		return
	end
	local function hide(page)
		if not page or not page:IsShown() then
			return
		end
		for _, hidden in ipairs(hiddenNativePages) do
			if hidden == page then
				return
			end
		end
		hiddenNativePages[#hiddenNativePages + 1] = page
		nativePageAlpha[page] = page:GetAlpha()
		page:SetAlpha(0)
	end
	local pages = window.Pages or {}
	for _, page in ipairs(pages) do
		hide(page)
	end
	for _, name in ipairs({ "CraftingPage", "BookPage", "SpecPage", "OrdersPage" }) do
		hide(window[name])
	end
end

local function ClearHiddenNativePages()
	hiddenNativePages = {}
	nativePageAlpha = {}
end

local function RestoreNativePages()
	for _, page in ipairs(hiddenNativePages) do
		page:SetAlpha(nativePageAlpha[page] or 1)
	end
end

ApplyPages = function()
	if Locked() then
		Queue()
		return
	end
	local selected = selectedKey and tabs[selectedKey]
	for _, entry in ipairs(order) do
		entry.spec.page:SetShown(entry == selected)
	end
	if selected then
		HideNativePages()
	end
end

local function ApplyPending()
	if Locked() then
		return
	end
	pending = false
	if watcher then
		watcher:UnregisterEvent("PLAYER_REGEN_ENABLED")
	end
	Anchor()
	ApplyPages()
	EnforceWidth()
end

Queue = function()
	if pending then
		return
	end
	pending = true
	if not watcher then
		watcher = CreateFrame("Frame")
		watcher:SetScript("OnEvent", function()
			if not Locked() then
				ApplyPending()
			end
		end)
	end
	watcher:RegisterEvent("PLAYER_REGEN_ENABLED")
end

-- Every tab this module builds is a Button, so the gamepad's SmartNavigation scan never reads this frame's mouse
-- scripts.
---@return ForeverProfessionTab
local function NewTab()
	return CreateFrame("Button", nil, Window(), "LargeSideTabButtonTemplate") --[[@as ForeverProfessionTab]]
end

-- The client's own side tabs, highest shown first. The last shown native tab is the slot our column starts under.
---@return ForeverProfessionNativeTab?
local function LastNativeTab()
	local window = Window() --[[@as ForeverProfessionsWindow]]
	local last = window.ProfessionsOverviewTab
	for _, native in ipairs(window.rightProfessionTabs or {}) do
		if native:IsShown() then
			last = native
		end
	end
	return last
end

-- Whether a frame is one of the tabs this module builds. Our own tabs sit in the same column, so they are never a slot
-- to start under.
---@param region ScriptRegion
---@return boolean
local function IsOurTab(region)
	for _, entry in ipairs(order) do
		if entry.tab == region then
			return true
		end
	end
	return false
end

-- Whether a frame hangs off one of our tabs. Anchoring our first tab under such a frame would make the two anchors a
-- loop, so it is not a slot to start under.
---@param frame Frame
---@return boolean
local function AnchoredToOurTabs(frame)
	local count = frame:GetNumPoints()
	for index = 1, count do
		local _, relativeTo = frame:GetPoint(index)
		if relativeTo and IsOurTab(relativeTo) then
			return true
		end
	end
	return false
end

-- No addon publishes a registration API for the column just outside the window's right edge, so another addon's side
-- tab is found by where it sits: level with the client's own tabs across and below the last one the window shows. That
-- geometric test holds for every addon drawing in the slot and names none of them.
---@param native ForeverProfessionNativeTab
---@return Frame?
local function ColumnOccupant(native)
	local nativeLeft, nativeRight, nativeBottom = native:GetLeft(), native:GetRight(), native:GetBottom()
	if type(nativeLeft) ~= "number" or type(nativeRight) ~= "number" or type(nativeBottom) ~= "number" then
		return nil
	end
	---@type Frame?
	local lowest
	local lowestBottom
	local seen = {}
	---@param frame Frame?
	local function inspect(frame)
		if not frame or frame == native or seen[frame] then
			return
		end
		seen[frame] = true
		if IsOurTab(frame) or not frame:IsShown() then
			return
		end
		local left, right, top, bottom = frame:GetLeft(), frame:GetRight(), frame:GetTop(), frame:GetBottom()
		if type(left) ~= "number" or type(right) ~= "number" or type(top) ~= "number" or type(bottom) ~= "number" then
			return
		end
		if right <= nativeLeft or left >= nativeRight or top > nativeBottom then
			return
		end
		if AnchoredToOurTabs(frame) then
			return
		end
		if not lowestBottom or bottom < lowestBottom then
			lowest, lowestBottom = frame, bottom
		end
	end
	-- All The Things reparents the client's own tabs, so a native tab's parent is read now rather than assumed to be
	-- the window itself.
	local parent = native:GetParent()
	if parent then
		for _, frame in ipairs({ parent:GetChildren() }) do
			inspect(frame)
		end
	end
	local window = Window()
	if window and window ~= parent then
		for _, frame in ipairs({ window:GetChildren() }) do
			inspect(frame)
		end
	end
	return lowest
end

-- Place every registered tab under the client's side tabs and then under one another, in registration order. Core
-- owns the anchoring, so no addon walks siblings.
Anchor = function()
	local native = LastNativeTab()
	if not native then
		return
	end
	-- Another addon's side tab can already hold the slot the column would start in, so the column starts under it
	-- instead. With the slot free, the placement is the client column's own.
	---@type Frame
	local above = ColumnOccupant(native) or native
	for _, entry in ipairs(order) do
		local tab = entry.tab
		tab:ClearAllPoints()
		tab:SetPoint("TOPLEFT", above, "BOTTOMLEFT", 0, -2)
		above = tab
	end
end

-- Other addons place their own side tab from the same window events this module listens to, and may run after it. The
-- column is placed again on the next frame, once for every trigger that asked in this one, so a tab placed later still
-- never sits under ours.
local function AnchorNextFrame()
	if anchorQueued then
		return
	end
	anchorQueued = true
	C_Timer.After(0, function()
		anchorQueued = false
		if Locked() then
			Queue()
			return
		end
		Anchor()
	end)
end

-- The window has laid itself out: keep the selected page width and our tab column.
local function Layout()
	Anchor()
	AnchorNextFrame()
	EnforceWidth()
end

-- A panel says whether it is visible through its own callback. The callback runs in its addon's SafeCall when one
-- was registered, so a failure lands in that journal.
---@param entry ForeverProfessionTabEntry
local function NotifySelected(entry)
	local spec = entry.spec
	if not spec.onSelect then
		return
	end
	local safe = spec.safeCall
	if safe then
		safe("profession tab selected", spec.onSelect, entry.key)
	elseif ns.SafeCall then
		ns.SafeCall("profession tab selected", spec.onSelect, entry.key)
	elseif securecallfunction then
		securecallfunction(spec.onSelect, entry.key)
	else
		spec.onSelect(entry.key)
	end
end

-- Our tab is the only checked one while it is selected, and no client tab is. Handing the window back leaves the
-- client's own checks alone, because the client has just set them.
local function SyncChecked()
	local selected = selectedKey and tabs[selectedKey]
	for _, entry in ipairs(order) do
		entry.tab:SetChecked(entry == selected)
	end
	if selected then
		local window = Window() --[[@as ForeverProfessionsWindow]]
		if window.ProfessionsOverviewTab then
			window.ProfessionsOverviewTab:SetChecked(false)
		end
		for _, native in ipairs(window.rightProfessionTabs or {}) do
			native:SetChecked(false)
		end
	end
end

-- Every native page hands the window back when the client shows it. The client builds a page as the window opens,
-- so its OnShow is the signal that the client wants its own page, not ours.
local function NativePageShown()
	RestoreNativePages()
	ClearHiddenNativePages()
	ns.ProfessionTabs.ShowNative()
	EnforceWidth()
end

-- Every native side tab hands the window back. The tab's own OnMouseUp runs first; our hook then clears our selection
-- even when the native page was already showing and its OnShow does not fire again.
local function NativeTabClicked()
	RestoreNativePages()
	ClearHiddenNativePages()
	ns.ProfessionTabs.ShowNative()
end

local function HookNativePages()
	local window = Window() --[[@as ForeverProfessionsWindow]]
	local seen = {}
	local function hook(page)
		if page and not seen[page] then
			seen[page] = true
			page:HookScript("OnShow", NativePageShown)
		end
	end
	for _, page in ipairs(window.Pages or {}) do
		hook(page)
	end
	hook(window.CraftingPage)
	hook(window.BookPage)
	hook(window.SpecPage)
	hook(window.OrdersPage)
end

-- Every native side tab hands the window back. The tab is a Frame with its own OnMouseUp script, so a mouse-up and a
-- gamepad press both reach our hook without touching the tab's method.
local function HookNativeTabs()
	local window = Window() --[[@as ForeverProfessionsWindow]]
	local overview = window.ProfessionsOverviewTab
	if overview then
		overview:HookScript("OnMouseUp", NativeTabClicked)
	end
	for _, native in ipairs(window.rightProfessionTabs or {}) do
		native:HookScript("OnMouseUp", NativeTabClicked)
	end
end

local function Install()
	if installed then
		return
	end
	installed = true
	HookNativePages()
	HookNativeTabs()
	-- The client resizes and rebuilds its own column through its own paths. Events and engine hooks tell us when the
	-- layout is done; nothing of the client's methods is replaced or called.
	local window = Window() --[[@as ForeverProfessionsWindow]]
	window:HookScript("OnShow", Layout)
	window:HookScript("OnSizeChanged", EnforceWidth)
	EventRegistry:RegisterCallback("ProfessionsFrame.TabSet", Layout, ns.ProfessionTabs)
	EventRegistry:RegisterCallback("ProfessionsFrame.Show", Layout, ns.ProfessionTabs)
	EventRegistry:RegisterCallback("Professions.ProfessionSelected", Layout, ns.ProfessionTabs)
end

---@class ForeverProfessionTabsAPI
local api = {}

-- The module's own version, raised with each member it adds. SetMinWidth arrived in minor 1; minor 2 means native
-- profession pages are hidden beneath a selected addon page, and restored when the window is handed back.
api.minor = 2

---@param key string
---@param spec ForeverProfessionTabSpec
---@return ForeverProfessionTab
function api.Register(key, spec)
	if type(key) ~= "string" or key == "" then
		error("ForeverCore.ProfessionTabs.Register: key must be a non-empty string", 2)
	end
	if tabs[key] then
		error("ForeverCore.ProfessionTabs.Register: key already registered: " .. key, 2)
	end
	Install()
	local tab = NewTab()
	tab.Icon:SetTexture(spec.icon)
	if tab.SetFillToInterior then
		tab:SetFillToInterior(true)
	end
	tab.tooltipText = spec.tooltip
	tab:EnableMouse(true)
	tab:SetCustomOnMouseUpHandler(function(_, mouseButton, upInside)
		if mouseButton == "LeftButton" and upInside then
			api.Select(key)
		end
	end)
	tab:SetChecked(false)
	local entry = { key = key, spec = spec, tab = tab }
	tabs[key] = entry
	order[#order + 1] = entry
	Anchor()
	AnchorNextFrame()
	RecomputeWidth()
	EnforceWidth()
	return tab
end

-- A page whose needed width changes after it registered raises or clears its minWidth, and the one width the window
-- keeps is recomputed and enforced. In combat the change waits with the rest of the frame work.
---@param key string
---@param width number?
function api.SetMinWidth(key, width)
	if type(key) ~= "string" or key == "" then
		error("ForeverCore.ProfessionTabs.SetMinWidth: key must be a non-empty string", 2)
	end
	local entry = tabs[key]
	if not entry then
		error("ForeverCore.ProfessionTabs.SetMinWidth: key not registered: " .. key, 2)
	end
	entry.spec.minWidth = width
	RecomputeWidth()
	EnforceWidth()
end

---@param key string
function api.Select(key)
	local entry = tabs[key]
	if not entry then
		return
	end
	selectedKey = key
	SyncChecked()
	ApplyPages()
	EnforceWidth()
	NotifySelected(entry)
end

-- Hand the window back to the client's own page: every registered page hides and every registered tab unchecks. The
-- client's tabs are left exactly as it set them.
function api.ShowNative()
	selectedKey = nil
	SyncChecked()
	ApplyPages()
	RestoreNativePages()
	ClearHiddenNativePages()
	EnforceWidth()
end

---@return string?
function api.Selected()
	return selectedKey
end

ns.ProfessionTabs = api
