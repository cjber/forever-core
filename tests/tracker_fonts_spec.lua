-- A tracker replacement that shrinks the shared tracker fonts (EllesmereUI sets them to 1 px and drops their shadow)
-- must not shrink core's sections: their text keeps readable fallback fonts, and follows the shared font again once
-- it is readable (#1099).
local harness = dofile("tests/tracker_host_harness.lua")

local t = harness.new({ hostSettings = { x = 30, y = -40 } })
local check = t.check
local env = t.env

local function NewFont(name, size)
	local font = { name = name, size = size }
	function font:GetFont() -- luacheck: ignore 212
		return "Fonts\\FRIZQT__.TTF", self.size, ""
	end
	function font:SetFont(_, newSize)
		self.size = newSize
	end
	function font.SetShadowColor() end
	function font:SetShadowOffset(x, y)
		self.shadow = { x, y }
	end
	return font
end
env.ObjectiveTrackerLineFont = NewFont("ObjectiveTrackerLineFont", 1)
env.ObjectiveTrackerHeaderFont = NewFont("ObjectiveTrackerHeaderFont", 1)
env.ChatFontNormal = NewFont("ChatFontNormal", 14)
env.CreateFont = function(name)
	local font = NewFont(name, 0)
	env[name] = font
	return font
end

local function NewText(font)
	local text = { font = font, justify = {} }
	function text:GetFont()
		return (self.font or font):GetFont()
	end
	function text:SetFontObject(name)
		self.font = env[name]
	end
	function text:SetJustifyH(value)
		self.justify.h = value
	end
	function text:SetJustifyV(value)
		self.justify.v = value
	end
	return text
end

local module = t.scrollModule(1, 1, 20)
module.Header.Text = NewText(env.ObjectiveTrackerHeaderFont)
local line = { Text = NewText(env.ObjectiveTrackerLineFont), Dash = NewText(env.ObjectiveTrackerLineFont) }
local block = { HeaderText = NewText(env.ObjectiveTrackerLineFont), usedLines = { a = line } }
module.usedBlocks = { Block = { [1] = block } }
t.ready()
t.drain()
t.host:MarkDirty()
t.drain()

local lineFallback, headerFallback = env.ForeverCoreTrackerLineFont, env.ForeverCoreTrackerHeaderFont
check(lineFallback and lineFallback.size == 12, "line text falls back to the game's 12 px minimum")
check(headerFallback and headerFallback.size == 14, "section header falls back to the 14 px minimum")
check(lineFallback and lineFallback.shadow and lineFallback.shadow[2] == -1, "the fallback carries a shadow")
check(line.Text.font == lineFallback and line.Dash.font == lineFallback, "a line's text and dash use the fallback")
check(block.HeaderText.font == lineFallback, "a block header uses the fallback")
check(module.Header.Text.font == headerFallback, "the section header uses the fallback")
check(line.Text.justify.h == "LEFT" and line.Text.justify.v == "TOP", "fallback text keeps the left and top edge")

-- The shared fonts become readable again (Edit Mode or the replacement is turned off): the text follows them.
env.ObjectiveTrackerLineFont.size, env.ObjectiveTrackerHeaderFont.size = 14, 16
t.host:MarkDirty()
t.drain()
check(line.Text.font == env.ObjectiveTrackerLineFont, "text returns to the shared line font once it is readable")
check(module.Header.Text.font == env.ObjectiveTrackerHeaderFont, "the header returns to the shared font")

-- A replacement that shrinks the shared fonts after the first layout reaches a manually placed column, which lays out
-- for no placement change: the next quest log update still rebuilds the text.
env.ObjectiveTrackerLineFont.size = 1
local before = module.updates
t.recheck("QUEST_LOG_UPDATE")
check(line.Text.font == lineFallback, "a font shrunk after the first layout falls back without a placement change")
t.drain()
check(module.updates > before, "the shrunk font lays the section out again")

print("tracker_fonts_spec: " .. t.checks() .. " checks passed")
