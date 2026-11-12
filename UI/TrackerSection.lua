---@type string, ForeverTrackerNamespace
local _, ns = ...

-- The section plumbing every Forever addon's tracker repeats: the game's module template, its mixin, the header, the
-- column's order and line template, the attach after saved variables, and the optional show switch and legacy table.
-- An addon keeps only its own rows; this file owns how a section joins the column.
---@class ForeverTrackerSectionAPI
local TrackerSection = {}
ns.TrackerSection = TrackerSection

-- A missing tracker or host is recorded in core's journal rather than raised, so an addon that loads before the client
-- can still finish loading and draw nothing.
---@param name string
---@param reason string
local function Unavailable(name, reason)
	local message = ("tracker section %s: %s"):format(tostring(name), reason)
	local safe = ns.SafeCall
	if safe then
		safe("tracker section", function()
			error(message, 2)
		end)
	end
end

-- The saved table has not loaded when an addon's files run, so a consumer may pass the table or a function that
-- answers it once saved variables are there.
---@param legacy table|fun(): table?
---@return table?
local function LegacyTable(legacy)
	---@type any
	local value = legacy
	if type(value) == "function" then
		value = value()
	end
	if type(value) == "table" then
		return value
	end
	return nil
end

-- Builds a section from ObjectiveTrackerModuleTemplate and attaches it to core's column after the world loads.
---@param name string the section frame's global name
---@param mixin? table the addon's module mixin
---@param opts? ForeverTrackerSectionOptions
---@return ForeverTrackerModule?
function TrackerSection.Create(name, mixin, opts)
	opts = opts or {}
	if not ObjectiveTrackerFrame then
		Unavailable(name, "the objective tracker is not available")
		return nil
	end
	local host = ns.TrackerHost
	if type(host) ~= "table" or type(host.Attach) ~= "function" then
		Unavailable(name, "the shared tracker host is not available")
		return nil
	end
	local module = CreateFrame("Frame", name, UIParent, "ObjectiveTrackerModuleTemplate") --[[@as ForeverTrackerModule]]
	if type(mixin) == "table" then
		Mixin(module, mixin)
	end
	-- A section that lays itself out in combat would move a protected frame there; the default holds the last layout.
	if type(module.CanUpdate) ~= "function" then
		module.CanUpdate = function()
			return not InCombatLockdown()
		end
	end
	module.uiOrder = opts.order
	if opts.lineTemplate ~= nil then
		module.lineTemplate = opts.lineTemplate
	end
	if opts.header ~= nil then
		module:SetHeader(opts.header)
	end
	if type(opts.safeCall) == "function" then
		module.safeCall = opts.safeCall
	end
	local function Attach()
		local current = ns.TrackerHost
		if type(current) ~= "table" or type(current.Attach) ~= "function" then
			return
		end
		local legacy = LegacyTable(opts.legacy)
		if legacy then
			local old = opts.legacyKey and legacy[opts.legacyKey] or legacy
			if type(old) == "table" then
				module.legacySettings = old
			end
		end
		current.Attach(module, opts.show)
		-- The old table is offered once, then removed, as a consumer's own attach did before core owned the column.
		if legacy and opts.legacyKey then
			legacy[opts.legacyKey] = nil
		end
	end
	EventUtil.ContinueAfterAllEvents(function()
		C_Timer.After(0, Attach)
		C_Timer.After(5, function()
			if type(opts.onUnattached) ~= "function" then
				return
			end
			if type(host.IsAttached) ~= "function" or not host.IsAttached(module) then
				opts.onUnattached(module)
			end
		end)
	end, "PLAYER_ENTERING_WORLD", "VARIABLES_LOADED")
	return module
end

-- Rewrites the text a layout already built, without another layout, so a countdown or a distance can tick. An entry is
-- `{ key, title, rows }`, each row `{ key, text, color }`, matching the blocks a section keeps for its own refresh.
---@param module ForeverTrackerModule
---@param blocks ForeverTrackerTextBlock[]
---@return boolean resized whether a line grew enough to need a new layout
function TrackerSection.UpdateText(module, blocks)
	local resized = false
	local headerColor = OBJECTIVE_TRACKER_COLOR and OBJECTIVE_TRACKER_COLOR.Header
	local normalColor = OBJECTIVE_TRACKER_COLOR and OBJECTIVE_TRACKER_COLOR.Normal
	for _, entry in ipairs(blocks or {}) do
		local block = module:GetExistingBlock(entry.key)
		if block and block.used then
			if entry.title and block.HeaderText and block.HeaderText:GetText() ~= entry.title then
				local height = block:SetStringText(block.HeaderText, entry.title, nil, headerColor, block.isHighlighted)
				resized = resized or height ~= block.headerHeight
				block.headerHeight = height
			end
			for _, row in ipairs(entry.rows or {}) do
				local line = block:GetExistingLine(row.key)
				if line and line.used and line.Text and line.Text:GetText() ~= row.text then
					local height =
						block:SetStringText(line.Text, row.text, true, row.color or normalColor, block.isHighlighted)
					resized = resized or height > line:GetHeight() + 0.5
				end
			end
		end
	end
	if resized then
		module:MarkDirty()
	end
	return resized
end

-- The room a block laid out next still has in the section, as Blizzard's CanFitBlock measures it.
---@param module ForeverTrackerModule
---@param block any
---@return number
function TrackerSection.Room(module, block)
	if type(module.GetNextBlockAnchoring) ~= "function" then
		return 0
	end
	local _, offsetY = module:GetNextBlockAnchoring()
	return (module.availableHeight or 0) - (module.contentsHeight or 0) + (offsetY or 0) - (block.height or 0)
end

-- The line a section shows when the column runs out of room, one entry for every objective still hidden.
---@param block any
---@param key any
---@param count integer
---@return any
function TrackerSection.AddMore(block, key, count)
	return block:AddObjective(key, (ns.L["+%d more"]):format(count))
end

-- UI/TrackerSection.xml's line: a stock objective line that takes the mouse, kept in a template of its own so its
-- scripts never follow a pooled line back to Blizzard's or another section's rows.
---@class ForeverTrackerLineAPI
local TrackerLine = {}
ns.TrackerLine = TrackerLine

---@param line Frame
---@param spec ForeverTrackerInteractiveSpec
function TrackerLine.SetInteractive(line, spec)
	line:EnableMouse(true)
	line:SetScript("OnMouseUp", function(self, button)
		if button == "LeftButton" and type(spec.onClick) == "function" then
			spec.onClick(self, button)
		end
	end)
	line:SetScript("OnEnter", function(self)
		if type(spec.tooltip) == "function" then
			spec.tooltip(self)
		end
	end)
	line:SetScript("OnLeave", function()
		if GameTooltip and GameTooltip.Hide then
			GameTooltip:Hide()
		end
	end)
end

-- A block header's hover, the pattern Adventure Guide uses: a title and one or more normal lines. `tip` may be a
-- function of the block, so a section names the block the pointer is over without a second mixin method.
---@param module ForeverTrackerModule
---@param tip ForeverTrackerHeaderTooltip|fun(block: any): ForeverTrackerHeaderTooltip?
function TrackerLine.SetHeaderTooltip(module, tip)
	local previousEnter = module.OnBlockHeaderEnter
	local previousLeave = module.OnBlockHeaderLeave
	module.OnBlockHeaderEnter = function(self, block)
		if type(previousEnter) == "function" then
			previousEnter(self, block)
		end
		local content = type(tip) == "function" and tip(block) or tip
		if type(content) ~= "table" or type(content.title) ~= "string" or not GameTooltip then
			return
		end
		GameTooltip:SetOwner(block, "ANCHOR_RIGHT")
		if GameTooltip_SetTitle then
			GameTooltip_SetTitle(GameTooltip, content.title)
		else
			GameTooltip:SetText(content.title, 1, 1, 1)
		end
		local addNormalLine = rawget(_G, "GameTooltip_AddNormalLine")
		for _, text in ipairs(content.lines or {}) do
			if addNormalLine then
				addNormalLine(GameTooltip, text)
			else
				GameTooltip:AddLine(text, nil, nil, nil, true)
			end
		end
		local target = { kind = "block", id = block and block.id, block = block, module = module }
		local hint = type(module.trackerClick) == "function"
			and type(module.trackerClickHint) == "function"
			and module.trackerClickHint(target)
		if type(hint) == "string" and hint ~= "" then
			if addNormalLine then
				addNormalLine(GameTooltip, ns.L["Click to %s"]:format(hint))
			else
				GameTooltip:AddLine(ns.L["Click to %s"]:format(hint), nil, nil, nil, true)
			end
		end
		if module.trackerMenu then
			if addNormalLine then
				addNormalLine(GameTooltip, ns.L["Right-click for options"])
			else
				GameTooltip:AddLine(ns.L["Right-click for options"], nil, nil, nil, true)
			end
		end
		GameTooltip:Show()
	end
	module.OnBlockHeaderLeave = function(self, block)
		if type(previousLeave) == "function" then
			previousLeave(self, block)
		end
		if GameTooltip and GameTooltip.Hide then
			GameTooltip:Hide()
		end
	end
end
