-- GameTooltip's native half: owner, lines (TextLeftN/TextRightN font strings the client creates on demand and
-- anchors under each other), size on Show, and OnTooltipCleared. Blizzard's own TooltipDataHandler (loaded from
-- the UI source) fills tooltips from C_TooltipInfo; the sim answers C_TooltipInfo from scenario data, with unit
-- names secret while unit identity is restricted, as the client does.
local Secret = require("veil")

local M = {}

function M.build(sim)
	local G, W, Taint = sim.G, sim.widgets, sim.taint
	local S = W.state
	local impl = W.impl.GameTooltip

	local function lines(self)
		local s = S[self]
		s.lines = s.lines or { left = {}, right = {} }
		return s.lines
	end

	local function line(self, side, i)
		local l = lines(self)
		local list = l[side]
		local fs = list[i]
		if fs then
			return fs
		end
		local s = S[self]
		local base = s.name or ("GameTooltip" .. s.id)
		local key = side == "left" and "TextLeft" or "TextRight"
		fs = sim.templates.createRegion("FontString", base .. key .. i, self, nil, "ARTWORK")
		local fontKey = rawget(self, (side == "left" and "textLeft" or "textRight") .. i .. "Font")
		local font = G[fontKey or (i == 1 and "GameTooltipHeaderText" or "GameTooltipText")]
		if font and S[font] then
			fs:SetFontObject(font)
		end
		S[fs].shown = false
		if side == "left" then
			if i == 1 then
				fs:SetPoint("TOPLEFT", self, "TOPLEFT", 10, -10)
			else
				fs:SetPoint("TOPLEFT", line(self, "left", i - 1), "BOTTOMLEFT", 0, -2)
			end
		else
			fs:SetPoint("RIGHT", line(self, "left", i), "LEFT", 40, 0)
			fs:SetJustifyH("RIGHT")
		end
		rawset(self, key .. i, fs)
		list[i] = fs
		return fs
	end

	local function clear(self)
		local s = S[self]
		local l = lines(self)
		for _, side in ipairs({ "left", "right" }) do
			for _, fs in ipairs(l[side]) do
				-- The client empties the text but does not reset the line, so a secret Text aspect stays.
				S[fs].text = ""
				S[fs].shown = false
			end
		end
		s.numLines = 0
		s.minimumWidth = 0
		W.dirty()
		W.fire(self, "OnTooltipCleared")
	end

	local function resize(self)
		local s = S[self]
		local width, height = 0, 20
		for i = 1, s.numLines or 0 do
			local left = line(self, "left", i)
			local w = W.textSize(S[left])
			local right = lines(self).right[i]
			if right and S[right].shown then
				w = w + 20 + W.textSize(S[right])
			end
			width = math.max(width, w)
			local _, h = W.textSize(S[left])
			height = height + math.max(h, 12) + 2
		end
		s.width = math.max(width + 20, Secret.unwrap(s.minimumWidth) or 0)
		s.height = height
		W.dirty()
	end

	impl.SetOwner = function(self, owner, anchor, x, y)
		local s = S[self]
		clear(self)
		s.owner, s.anchor, s.anchorX, s.anchorY = owner, anchor or "ANCHOR_LEFT", x or 0, y or 0
		s.points = {}
		if owner and anchor ~= "ANCHOR_NONE" and anchor ~= "ANCHOR_PRESERVE" then
			if anchor == "ANCHOR_CURSOR" or anchor == "ANCHOR_CURSOR_RIGHT" then
				W.setPoint(self, "BOTTOMLEFT", W.root(), "BOTTOMLEFT", sim.mouseX or 0, sim.mouseY or 0)
			elseif anchor == "ANCHOR_RIGHT" then
				W.setPoint(self, "BOTTOMLEFT", owner, "TOPRIGHT", x or 0, y or 0)
			elseif anchor == "ANCHOR_LEFT" then
				W.setPoint(self, "BOTTOMRIGHT", owner, "TOPLEFT", x or 0, y or 0)
			elseif anchor == "ANCHOR_TOP" then
				W.setPoint(self, "BOTTOM", owner, "TOP", x or 0, y or 0)
			elseif anchor == "ANCHOR_BOTTOM" then
				W.setPoint(self, "TOP", owner, "BOTTOM", x or 0, y or 0)
			elseif anchor == "ANCHOR_BOTTOMRIGHT" then
				W.setPoint(self, "TOPLEFT", owner, "BOTTOMRIGHT", x or 0, y or 0)
			elseif anchor == "ANCHOR_BOTTOMLEFT" then
				W.setPoint(self, "TOPRIGHT", owner, "BOTTOMLEFT", x or 0, y or 0)
			elseif anchor == "ANCHOR_TOPRIGHT" then
				W.setPoint(self, "BOTTOMRIGHT", owner, "TOPRIGHT", x or 0, y or 0)
			elseif anchor == "ANCHOR_TOPLEFT" then
				W.setPoint(self, "BOTTOMLEFT", owner, "TOPLEFT", x or 0, y or 0)
			else
				W.setPoint(self, "BOTTOMRIGHT", W.root(), "BOTTOMRIGHT", -100, 100)
			end
		end
	end
	impl.GetOwner = function(self)
		return S[self].owner
	end
	impl.IsOwned = function(self, frame)
		return S[self].owner == frame
	end
	impl.GetAnchorType = function(self)
		local s = S[self]
		return s.anchor or "ANCHOR_NONE", s.anchorX or 0, s.anchorY or 0
	end
	impl.SetAnchorType = function(self, anchor, x, y)
		local s = S[self]
		s.anchor, s.anchorX, s.anchorY = anchor, x, y
	end
	impl.ClearLines = function(self)
		clear(self)
	end
	impl.NumLines = function(self)
		return S[self].numLines or 0
	end
	local function addLine(self, text, r, g, b, wrap, leftOffset)
		local s = S[self]
		s.numLines = (s.numLines or 0) + 1
		local fs = line(self, "left", s.numLines)
		fs:SetText(text)
		fs:SetTextColor(r or 1, g or 0.82, b or 0)
		S[fs].shown = true
		local right = lines(self).right[s.numLines]
		if right then
			S[right].shown = false
			S[right].text = ""
		end
		local _ = wrap
		local _ = leftOffset
		resize(self)
		return fs
	end
	impl.AddLine = function(self, text, r, g, b, wrap, leftOffset)
		addLine(self, text, r, g, b, wrap, leftOffset)
	end
	impl.AddDoubleLine = function(self, left, right, lr, lg, lb, rr, rg, rb, wrap, leftOffset)
		local s = S[self]
		addLine(self, left, lr, lg, lb, wrap, leftOffset)
		local fs = line(self, "right", s.numLines)
		fs:SetText(right)
		fs:SetTextColor(rr or 1, rg or 0.82, rb or 0)
		S[fs].shown = true
		resize(self)
	end
	impl.SetText = function(self, text, r, g, b, a, wrap)
		clear(self)
		addLine(self, text, r, g, b, wrap)
		local _ = a
	end
	impl.AppendText = function(self, text)
		local s = S[self]
		local fs = line(self, "left", math.max(1, s.numLines or 0))
		fs:SetText(G.tostring(fs:GetText() or "") .. text)
	end
	impl.GetLeftLine = function(self, i)
		return line(self, "left", i)
	end
	impl.GetRightLine = function(self, i)
		return line(self, "right", i)
	end
	impl.AddTexture = function() end
	impl.SetMinimumWidth = function(self, w)
		S[self].minimumWidth = w
		resize(self)
	end
	impl.GetMinimumWidth = function(self)
		return S[self].minimumWidth or 0
	end
	impl.SetPadding = function(self, r, b, l, t)
		S[self].padding = { r, b, l, t }
	end
	impl.GetPadding = function(self)
		local p = S[self].padding or { 0, 0, 0, 0 }
		return p[1], p[2], p[3], p[4]
	end
	impl.SetCustomLineSpacing = function(self, n)
		S[self].lineSpacing = n
	end
	impl.GetCustomLineSpacing = function(self)
		return S[self].lineSpacing
	end
	impl.FadeOut = function(self)
		self:Hide()
	end
	impl.IsEquippedItem = function()
		return false
	end
	impl.GetUnit = function(self)
		local s = S[self]
		return s.unitName, s.unit
	end
	impl.GetItem = function()
		return nil
	end
	impl.GetSpell = function()
		return nil
	end
	impl.SetBackdrop = function() end
	impl.SetBackdropColor = function() end
	impl.SetBackdropBorderColor = function() end
	impl.ResetSecondaryCompareItem = function() end
	impl.SetAllowShowWithNoLines = function(self, on)
		S[self].allowNoLines = on
	end
	impl.IsTooltipType = function()
		return false
	end
	impl.AddFontStrings = function(self, left, right)
		local l = lines(self)
		table.insert(l.left, left)
		table.insert(l.right, right)
	end
	impl.CopyTooltip = function() end

	-- The secure delegate the client builds: runs untainted, then restores the caller's taint.
	G.CreateSecureDelegate = function(f)
		return function(...)
			local saved = Taint.current
			Taint.set(nil)
			local result = { pcall(f, ...) }
			Taint.set(saved)
			if not result[1] then
				error(result[2], 0)
			end
			return unpack(result, 2, table.maxn(result))
		end
	end
	G.canaccessallvalues = function(...)
		if not Taint.current then
			return true
		end
		for i = 1, select("#", ...) do
			if Secret.is((select(i, ...))) then
				return false
			end
		end
		return true
	end
	G.mapvalues = function(f, ...)
		local out = { ... }
		local n = select("#", ...)
		for i = 1, n do
			out[i] = f(out[i])
		end
		return unpack(out, 1, n)
	end
	sim.impl["C_RestrictedActions.CheckAllowProtectedFunctions"] = function(object)
		local s = object and S[object]
		if s and s.protected and Taint.current and sim.inCombat then
			sim.blocked(object, "CheckAllowProtectedFunctions")
			return false
		end
		return true
	end

	-- C_TooltipInfo from scenario data. A line's text is read through the same documented stubs an addon would
	-- call (UnitName...), so it carries their secrecy.
	local LINE = G.Enum and G.Enum.TooltipDataLineType or {}
	local TYPE = G.Enum and G.Enum.TooltipDataType or {}
	sim.impl["C_TooltipInfo.GetUnit"] = function(unit)
		local u = sim.units[Secret.unwrap(unit)]
		if not u then
			return nil
		end
		local name = G.UnitName(unit)
		local data = { type = TYPE.Unit, guid = G.UnitGUID(unit), lines = {} }
		table.insert(data.lines, { type = LINE.UnitName, leftText = name, leftColor = G.HIGHLIGHT_FONT_COLOR })
		local levelLine = G.string.format("Level %s %s", G.tostring(G.UnitLevel(unit)), u.creatureType or u.race or "")
		if sim.restrictions.unitRestricted or sim.inCombat then
			if unit ~= "player" then
				levelLine = Secret.wrap(Secret.unwrap(levelLine))
			end
		end
		table.insert(data.lines, { type = LINE.None, leftText = levelLine })
		if u.faction then
			local factionLine = u.faction
			if (sim.inCombat or sim.restrictions.unitRestricted) and unit ~= "player" then
				factionLine = Secret.wrap(factionLine)
			end
			table.insert(data.lines, { type = LINE.None, leftText = factionLine })
		end
		return data
	end
	sim.impl["C_TooltipInfo.GetItemByID"] = function(itemID)
		local item = sim.items[itemID]
		if not item then
			return nil
		end
		local data = { type = TYPE.Item, id = itemID, lines = {} }
		table.insert(data.lines, { type = LINE.ItemName, leftText = item.name })
		for _, text in ipairs(item.lines or {}) do
			table.insert(data.lines, { type = LINE.None, leftText = text })
		end
		return data
	end
	sim.impl["C_TooltipInfo.GetRecipeResultItem"] = function(recipeID)
		local recipe = sim.recipes[recipeID]
		if not recipe then
			return nil
		end
		return sim.impl["C_TooltipInfo.GetItemByID"](recipe.itemID)
	end
	sim.units = sim.units or {}
	sim.items = sim.items or {}
	sim.recipes = sim.recipes or {}
end

return M
