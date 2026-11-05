local _, ns = ...
-- luacheck: globals CollectionsMicroButton DEFAULT_CHAT_FRAME GameTooltip_Hide
-- luacheck: globals MainMenuMicroButton MicroMenu MicroMenuContainer UpdateMicroButtons ForeverMicroButtons
-- luacheck: globals hooksecurefunc InCombatLockdown NORMAL_FONT_COLOR GRAY_FONT_COLOR

-- The button is an addon-owned micro-menu child. Addons provide their own saved setting and click action.
local MicroButton = {}
ns.MicroButton = MicroButton

-- Every Forever addon vendors this file, so each loads its own copy. They share one registry, published by the first
-- copy to load, so the buttons of every addon form one row instead of each copy stacking its own on the same spot.
-- The registry is addon state: nothing of Blizzard's reads it.
local shared = _G.ForeverMicroButtons
if type(shared) ~= "table" then
	shared = { buttons = {} }
	_G.ForeverMicroButtons = shared
end

local function Safe(label, fn, ...)
	if ns.SafeCall then
		return ns.SafeCall(label, fn, ...)
	end
	return pcall(fn, ...)
end

-- Blizzard's micro buttons, in the order MicroMenu's grid lays them out. Only shown children with a layoutIndex are
-- in the grid; the addon buttons have none, so the grid never reads a field an addon wrote.
local function NativeButtons()
	local list = {}
	for _, child in ipairs({ MicroMenu:GetChildren() }) do
		---@cast child ForeverMicroGridChild
		if child.layoutIndex and child:IsShown() then
			list[#list + 1] = child
		end
	end
	table.sort(list, function(a, b)
		return a.layoutIndex < b.layoutIndex
	end)
	return list
end

-- Moves a Blizzard button along the row to `x`, keeping the rest of the anchor the grid gave it.
local function Place(button, x)
	local point, relativeTo, relativePoint, oldX, y = button:GetPoint(1)
	if point and math.abs(oldX - x) >= 0.01 then
		button:ClearAllPoints()
		button:SetPoint(point, relativeTo, relativePoint, x, y)
	end
end

local function SlotOf(button)
	local spec = button.microButtonSpec
	return spec and (spec.getSlot and spec.getSlot() or spec.slot)
end

-- Chains `list` from `anchor`, each button `toward` ("LEFT" or "RIGHT") of the one before, overlapping by the grid's
-- own padding, so the addon buttons sit at the same spacing as Blizzard's.
local function Chain(list, anchor, toward, overlap)
	local from = toward == "LEFT" and "RIGHT" or "LEFT"
	local x = toward == "LEFT" and overlap or -overlap
	for _, button in ipairs(list) do
		button:ClearAllPoints()
		button:SetPoint(from, anchor, toward, x, 0)
		anchor = button
	end
end

-- Sets the menu's width to `width`, and the container's to match, as MicroMenuContainer:Layout sizes it. The width
-- is the menu's only measure of the row: Edit Mode places the container by it, the action bar and bags anchor to
-- its sides, and the menu's art spans it.
local function Resize(width)
	if math.abs(MicroMenu:GetWidth() - width) >= 0.01 then
		MicroMenu:SetWidth(width)
	end
	local container = MicroMenuContainer
	if container and MicroMenu:GetParent() == container then
		local scaled = width * MicroMenu:GetScale()
		if math.abs(container:GetWidth() - scaled) >= 0.01 then
			container:SetWidth(scaled)
		end
	end
end

-- Places every shown addon button in its slot, moves Blizzard's buttons after it aside to make room, and widens the
-- menu by the room it made. The menu sits in its container at the corner nearest the screen edge (MicroMenuMixin's
-- AnchorToMenuContainer) and the container grows with it, so the row stays inside the menu, its art and its
-- neighbours however Edit Mode placed it.
local function Reflow()
	if not (MicroMenu and MicroMenu.GetChildren) then
		return
	end
	-- Resizing the container moves the action bar anchored to it, which waits for the end of combat.
	if InCombatLockdown and InCombatLockdown() then
		return
	end
	local native = NativeButtons()
	local position = {}
	for index, button in ipairs(native) do
		position[button] = index
	end
	local before, after = {}, {}
	for _, button in ipairs(shared.buttons) do
		if button:IsShown() then
			if SlotOf(button) == "afterCollections" and position[CollectionsMicroButton] then
				after[#after + 1] = button
			else
				before[#before + 1] = button
			end
		end
	end
	local padding = MicroMenu.childXPadding or -5
	local overlap = -padding
	local gameMenu = position[MainMenuMicroButton]
	local oneRow = MicroMenu.isHorizontal ~= false
		and MicroMenu.layoutFramesGoingRight ~= false
		and (MicroMenu.stride or #native) >= #native
	if not (oneRow and gameMenu) then
		-- A vertical or stacked menu: leave Blizzard's grid alone and line the addon buttons up beside it, away from
		-- the screen edge the menu is anchored to. Switching the menu to either changes the grid's settings, so its
		-- Layout re-places every button and resizes the menu.
		for _, button in ipairs(after) do
			before[#before + 1] = button
		end
		local anchorPoint = MicroMenu:GetPoint(1)
		local anchoredRight = type(anchorPoint) == "string" and anchorPoint:find("RIGHT") ~= nil
		Chain(before, MicroMenu, anchoredRight and "LEFT" or "RIGHT", 0)
		shared.width = nil
		return
	end
	-- Every slot is one step: a button's width less the grid's overlap. The grid puts its first button at the row's
	-- origin, and this never moves that button, so its anchor gives the origin on every run.
	local _, _, _, origin = native[1]:GetPoint(1)
	if not origin then
		return
	end
	local collections = position[CollectionsMicroButton] or 0
	local width = native[1]:GetWidth()
	width = width > 0 and width or 32
	local step = width + padding
	for index, button in ipairs(native) do
		local units = (index > collections and #after or 0) + (index >= gameMenu and #before or 0)
		Place(button, origin + (index - 1 + units) * step)
	end
	Chain(before, MainMenuMicroButton, "LEFT", overlap)
	Chain(after, CollectionsMicroButton, "RIGHT", overlap)
	-- The grid sized the menu to its own buttons. Widen it by the addon buttons, or give back what the last run
	-- added once none is shown, and leave a menu this never widened as Blizzard sized it.
	local added = #before + #after
	if added > 0 or shared.width then
		local row = origin + (#native - 1 + added) * step + width
		Resize(row)
		shared.width = added > 0 and row or nil
	end
end
shared.Reflow = shared.Reflow or Reflow

local function ReflowAll()
	Safe("micro button placement", shared.Reflow)
end

local function RefreshOne(button)
	local spec = button.microButtonSpec
	if spec then
		button:SetShown(spec.getShown() == true)
	end
end

-- One hook of each for every copy, kept in the shared registry. Each hook is made once and never again: hooksecurefunc
-- replaces the hooked function with a wrapper, so a guard that compares against the current function hooks again
-- whenever another copy or addon has wrapped it since, and every call then nests one hook deeper until the client's
-- C stack overflows.
local function HookUpdate()
	if not shared.hookedUpdate and type(UpdateMicroButtons) == "function" and hooksecurefunc then
		shared.hookedUpdate = true
		hooksecurefunc("UpdateMicroButtons", function()
			Safe("micro button refresh", MicroButton.Refresh)
		end)
	end
	-- The grid re-places Blizzard's buttons when one of them shows or hides, or the menu changes size or Edit Mode
	-- layout; make room again straight after. Script hooks and an event frame of our own leave Blizzard's methods
	-- and their callers untouched.
	if MicroMenu and MicroMenu.GetChildren then
		shared.hookedScripts = shared.hookedScripts or setmetatable({}, { __mode = "k" })
		local targets = { MicroMenu } ---@type Frame[]
		for _, child in ipairs({ MicroMenu:GetChildren() }) do
			---@cast child ForeverMicroGridChild
			if child.layoutIndex then
				targets[#targets + 1] = child
			end
		end
		for _, target in ipairs(targets) do
			if not shared.hookedScripts[target] and target.HookScript then
				shared.hookedScripts[target] = true
				if target == MicroMenu then
					target:HookScript("OnSizeChanged", ReflowAll)
				else
					target:HookScript("OnShow", ReflowAll)
					target:HookScript("OnHide", ReflowAll)
				end
			end
		end
	end
	if not shared.events then
		shared.events = CreateFrame("Frame")
		shared.events:RegisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
		shared.events:SetScript("OnEvent", ReflowAll)
	end
	-- A placement skipped in combat runs when it ends.
	shared.events:RegisterEvent("PLAYER_REGEN_ENABLED")
end

function MicroButton.Refresh()
	HookUpdate()
	for _, button in ipairs(shared.buttons) do
		Safe("micro button visibility", RefreshOne, button)
	end
	ReflowAll()
end

---@param spec table
---@return Frame?
function MicroButton.Create(spec)
	if not MicroMenu then
		if DEFAULT_CHAT_FRAME and DEFAULT_CHAT_FRAME.AddMessage then
			DEFAULT_CHAT_FRAME:AddMessage(ns.L.MICRO_MENU_UNAVAILABLE)
		end
		return nil
	end
	local button = CreateFrame("Button", spec.name, MicroMenu, "MainMenuBarMicroButton") --[[@as ForeverMicroButton]]
	button.microButtonSpec = spec
	-- The template's OnMouseDown builds the pressed highlight from this name, as LoadMicroButtonTextures sets it.
	button.textureName = spec.atlas
	if spec.host then
		spec.host.microButton = button
	end
	button:SetSize(32, 41)
	button:SetNormalAtlas("UI-HUD-MicroMenu-" .. spec.atlas .. "-Up") -- art-ok: native micro-menu atlas
	button:SetPushedAtlas("UI-HUD-MicroMenu-" .. spec.atlas .. "-Down") -- art-ok: native micro-menu atlas
	button:SetDisabledAtlas("UI-HUD-MicroMenu-" .. spec.atlas .. "-Disabled") -- art-ok: native micro-menu atlas
	button:SetHighlightAtlas("UI-HUD-MicroMenu-" .. spec.atlas .. "-Mouseover") -- art-ok: native micro-menu atlas
	local icon = button:CreateTexture(nil, "ARTWORK")
	icon:SetSize(22, 22)
	icon:SetPoint("CENTER", 0, 0.5)
	icon:SetTexture(spec.icon) -- art-ok: square icon texture drawn at the approved 22-unit size
	button.icon = icon
	if button.alert then
		button.alert:Hide()
	end
	button:SetScript("OnClick", function()
		Safe("micro button click", spec.onClick)
	end)
	button:SetScript("OnEnter", function(self)
		GameTooltip:SetOwner(self, "ANCHOR_TOP")
		GameTooltip:SetText(spec.title)
		GameTooltip:AddLine("(" .. spec.binding .. ")", NORMAL_FONT_COLOR:GetRGB())
		GameTooltip:AddLine(spec.subtext, GRAY_FONT_COLOR:GetRGB())
		GameTooltip:Show()
	end)
	button:SetScript("OnLeave", GameTooltip_Hide)
	-- The template's OnShow and OnHide run MicroMenuContainer:Layout, which from addon code would taint the grid's
	-- cached settings. Showing or hiding an addon button only needs the addon row placed again.
	button:SetScript("OnShow", ReflowAll)
	button:SetScript("OnHide", ReflowAll)
	shared.buttons[#shared.buttons + 1] = button
	HookUpdate()
	Safe("micro button visibility", RefreshOne, button)
	ReflowAll()
	return button
end

function MicroButton.Destroy(button)
	for index, candidate in ipairs(shared.buttons) do
		if candidate == button then
			table.remove(shared.buttons, index)
			break
		end
	end
	if button then
		button:Hide()
		button:ClearAllPoints()
		local spec = button.microButtonSpec
		if spec and spec.host and spec.host.microButton == button then
			spec.host.microButton = nil
		end
	end
	ReflowAll()
end

function MicroButton.SetShown(button, shown)
	if button then
		button:SetShown(shown == true)
		ReflowAll()
	end
end
