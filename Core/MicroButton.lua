local _, ns = ...
-- luacheck: globals CollectionsMicroButton DEFAULT_CHAT_FRAME GameTooltip_Hide
-- luacheck: globals MainMenuMicroButton MicroMenu UpdateMicroButtons
-- luacheck: globals hooksecurefunc NORMAL_FONT_COLOR GRAY_FONT_COLOR

-- The button is an addon-owned micro-menu child. Addons provide their own saved setting and click action.
local MicroButton = {}
ns.MicroButton = MicroButton

local buttons = {}
local hookedUpdate

local function Safe(label, fn, ...)
	if ns.SafeCall then
		return ns.SafeCall(label, fn, ...)
	end
	return pcall(fn, ...)
end

local function Anchor(button, slot)
	if slot == "afterCollections" and CollectionsMicroButton and CollectionsMicroButton:IsShown() then
		button:ClearAllPoints()
		button:SetPoint("LEFT", CollectionsMicroButton, "RIGHT", -5, 0)
	else
		button:ClearAllPoints()
		button:SetPoint("RIGHT", MainMenuMicroButton, "LEFT", 5, 0)
	end
	if MicroMenu.Layout then
		MicroMenu:Layout()
	end
end

local function RefreshOne(button)
	local spec = button.microButtonSpec
	if spec then
		button:SetShown(spec.getShown() == true)
		Anchor(button, spec.getSlot and spec.getSlot() or spec.slot)
	end
end

local function HookUpdate()
	if type(UpdateMicroButtons) == "function" and hookedUpdate ~= UpdateMicroButtons and hooksecurefunc then
		hookedUpdate = UpdateMicroButtons
		hooksecurefunc("UpdateMicroButtons", function()
			Safe("micro button refresh", MicroButton.Refresh)
		end)
	end
end

function MicroButton.Refresh()
	HookUpdate()
	for _, button in ipairs(buttons) do
		if button then
			Safe("micro button placement", RefreshOne, button)
		end
	end
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
	buttons[#buttons + 1] = button
	HookUpdate()
	Safe("micro button placement", RefreshOne, button)
	return button
end

function MicroButton.Destroy(button)
	for index, candidate in ipairs(buttons) do
		if candidate == button then
			table.remove(buttons, index)
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
end

function MicroButton.SetShown(button, shown)
	if button then
		button:SetShown(shown == true)
	end
end
