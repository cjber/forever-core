-- UI/Credits.lua: two fake addons register their generated tables, the page merges a player by exact name across
-- them and names the addons they helped, an addon's own line lists up to three names and counts the rest, and a
-- missing or malformed table never throws.
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local ns = {
	L = setmetatable({}, {
		__index = function(_, key)
			return key
		end,
	}),
	SafeCall = function(label, fn, ...)
		local ok, err = pcall(fn, ...)
		assert(ok, label .. ": " .. tostring(err))
		return ok
	end,
}
local path = "UI/Credits.lua"
assert(loadfile(path))("ForeverCore", ns)
local credits = ns.CreditsPage

-- The module is the only thing this file builds at load; the window waits for Open.
check(type(credits) == "table", "the module is published on the namespace")
equal(credits.minor, 1, "the module's minor")

check(
	credits.Register("SkillUp Forever", {
		players = {
			{ name = "Brainc3ll", what = "The French translation" },
			{ name = "Alex", what = "The cheapest route idea" },
			{ name = "Robin", what = "A bug report" },
		},
		inspired = {
			{ name = "Questie", what = "The tracker layout" },
		},
	}),
	"an addon's credits register"
)
check(
	credits.Register("Legacy Forever", {
		players = {
			{ name = "Brainc3ll", what = "" },
			{ name = "Sam", what = "The map notes" },
		},
	}),
	"a second addon's credits register"
)

local players = credits.Players()
equal(#players, 4, "each exact player name appears once")
local names = {}
for _, row in ipairs(players) do
	names[#names + 1] = row.name
end
equal(table.concat(names, ", "), "Alex, Brainc3ll, Robin, Sam", "players are sorted by name")

local merged
for _, row in ipairs(players) do
	if row.name == "Brainc3ll" then
		merged = row
	end
end
check(merged ~= nil, "the merged player is there")
equal(#merged.helped, 2, "the player is credited by both addons")
equal(merged.helped[1].addon, "SkillUp Forever", "the first addon that registered")
equal(merged.helped[1].what, "The French translation", "with its own what line")
equal(merged.helped[2].addon, "Legacy Forever", "then the second")
equal(merged.helped[2].what, "", "with its own, even when that line is empty")

local inspired = credits.Inspired()
equal(#inspired, 1, "inspired entries merge the same way")
equal(inspired[1].name, "Questie", "the inspired name")
equal(#inspired[1].helped, 1, "the addon that credits it")
equal(inspired[1].helped[1].addon, "SkillUp Forever", "the inspired addon")
equal(inspired[1].helped[1].what, "The tracker layout", "and its what line")

equal(credits.Line("SkillUp Forever"), "Thanks to Brainc3ll, Alex and Robin", "three names read as a list")
equal(credits.Line("Legacy Forever"), "Thanks to Brainc3ll and Sam", "two names join with 'and'")
equal(credits.Line("No Such Addon"), nil, "an addon with no credits has no line")

credits.Register("Field Guide Forever", {
	players = {
		{ name = "Dana", what = "The journal idea" },
		{ name = "Eli", what = "A zone list" },
	},
})
equal(credits.Line("Field Guide Forever"), "Thanks to Dana and Eli", "another addon's own line lists only its players")

credits.Register("Commissions Forever", {
	players = {
		{ name = "Finn", what = "A turn-in report" },
		{ name = "Gale", what = "A bug report" },
		{ name = "Hana", what = "The materials list" },
		{ name = "Iris", what = "The next NPC idea" },
	},
})
equal(
	credits.Line("Commissions Forever"),
	"Thanks to Finn, Gale, Hana and 1 more",
	"past three names the line counts the rest"
)

-- A second registration of one title replaces it rather than listing its people twice.
credits.Register("Field Guide Forever", {
	players = {
		{ name = "Dana", what = "The journal idea" },
	},
})
equal(credits.Line("Field Guide Forever"), "Thanks to Dana", "a repeated title replaces its list")
local found = 0
for _, row in ipairs(credits.Players()) do
	if row.name == "Eli" then
		found = found + 1
	end
end
equal(found, 0, "the replaced addon's old players are gone")

-- Empty and malformed data is left out, never raised.
equal(credits.Register("", {}), false, "an empty title is refused")
equal(credits.Register(nil, {}), false, "a missing title is refused")
check(credits.Register("Empty Forever", nil), "an addon with no table still registers")
equal(credits.Line("Empty Forever"), nil, "an empty addon has no line")
check(
	credits.Register("Broken Forever", {
		players = {
			"not a table",
			{ name = 42 },
			{ name = "Ok", what = 7 },
			{ what = "no name" },
		},
		inspired = "not a list",
	}),
	"a malformed table registers what it can"
)
equal(credits.Line("Broken Forever"), "Thanks to Ok", "only the readable player is kept")
local broken
for _, row in ipairs(credits.Players()) do
	if row.name == "Ok" then
		broken = row
	end
end
equal(broken.helped[1].what, "", "a non-string what reads as an empty line")

-- A second load in a fake client that counts every frame: opening the page twice must reuse the window, and a list
-- that changes must grow the row pool, never rebuild it.
local framesMade = 0
local function Fake(kind)
	local value = { kind = kind, shown = false, scripts = {}, points = {} }
	function value:SetPoint(...)
		self.points[#self.points + 1] = { ... }
	end
	function value:ClearAllPoints()
		self.points = {}
	end
	function value:SetSize(width, height)
		self.width, self.height = width, height
	end
	function value:SetWidth(width)
		self.width = width
	end
	function value:SetHeight(height)
		self.height = height
	end
	function value.SetFrameStrata() end
	function value.SetToplevel() end
	function value.SetClampedToScreen() end
	function value.SetMovable() end
	function value.EnableMouse() end
	function value.RegisterForDrag() end
	function value:SetScrollChild(child)
		self.scrollChild = child
	end
	function value:SetScript(event, fn)
		self.scripts[event] = fn
	end
	function value:SetTitle(title)
		self.title = title
	end
	function value:SetJustifyH(justify)
		self.justify = justify
	end
	function value:SetJustifyV(justify)
		self.justifyV = justify
	end
	function value:SetWordWrap(wrap)
		self.wordWrap = wrap
	end
	function value:SetMaxLines(lines)
		self.maxLines = lines
	end
	function value:SetText(text)
		self.text = text
	end
	function value:GetText()
		return self.text
	end
	function value:SetTextColor(...)
		self.textColor = { ... }
	end
	function value:SetShown(shown)
		self.shown = shown
	end
	function value.SetNormalFontObject() end
	function value.SetHighlightFontObject() end
	function value.SetDisabledFontObject() end
	function value:SetTexture(texture)
		self.texture = texture
	end
	function value:SetHighlightTexture(texture, blend)
		self.highlight = texture
		self.highlightBlend = blend
	end
	function value.GetStringHeight()
		return 14
	end
	function value.GetPortrait()
		return Fake("Texture")
	end
	function value.CreateFontString()
		return Fake("FontString")
	end
	function value:Show()
		local was = self.shown
		self.shown = true
		if not was and self.scripts.OnShow then
			self.scripts.OnShow(self)
		end
	end
	function value:Hide()
		self.shown = false
	end
	function value:IsShown()
		return self.shown
	end
	return value
end

local tooltip = { lines = {} }
function tooltip:SetOwner(owner, anchor)
	self.owner, self.anchor = owner, anchor
end
function tooltip:SetText(text)
	self.title = text
end
function tooltip:AddLine(text, red, green, blue, wrap)
	self.lines[#self.lines + 1] = { text = text, wrap = wrap, color = { red, green, blue } }
end
function tooltip:Show()
	self.shown = true
end
function tooltip:Hide()
	self.shown = false
end

local client = {
	UISpecialFrames = {},
	UIParent = Fake("Frame"),
	GameTooltip = tooltip,
	GameTooltip_SetTitle = function(self, title)
		self.title = title
	end,
	GameTooltip_Hide = function()
		tooltip:Hide()
	end,
	NORMAL_FONT_COLOR = {
		GetRGB = function()
			return 1, 1, 1
		end,
	},
	GRAY_FONT_COLOR = {
		GetRGB = function()
			return 0.5, 0.5, 0.5
		end,
	},
	tContains = function(list, item)
		for _, value in ipairs(list) do
			if value == item then
				return true
			end
		end
		return false
	end,
	CreateFrame = function(kind, _name, _parent, template)
		framesMade = framesMade + 1
		local frame = Fake(kind)
		frame.template = template
		return frame
	end,
}
setmetatable(client, { __index = _G })
local own = { L = ns.L, SafeCall = ns.SafeCall }
local chunk = assert(loadfile(path))
setfenv(chunk, client)
chunk("ForeverCore", own)
local page = own.CreditsPage
check(type(page) == "table", "the module loads in a client")
check(
	page.Register("Pool Forever", {
		players = {
			{ name = "One", what = "The first report" },
			{ name = "Two", what = "The second report" },
		},
	}),
	"the pool's first list registers"
)
check(page.Open(), "the Thanks page opens")
local firstOpen = framesMade
check(#page.window.rows == 2, "a row per player")
check(page.window.rows[1].holder.kind == "Button", "a row is a button, so the client can draw its own hover")
equal(
	page.window.rows[1].holder.highlight,
	"Interface\\QuestFrame\\UI-QuestTitleHighlight",
	"the row wears the client's standard list highlight"
)
equal(page.window.rows[1].holder.highlightBlend, "ADD", "drawn additively over the row, as every list does")

-- The header: the subtitle on one line under the title, the filter on its own row below it, the inset moved down.
local window = page.window
equal(window.subtitle.points[1][1], "TOPLEFT", "the subtitle starts under the title")
equal(window.subtitle.points[1][3], -54, "at the title's own offset")
equal(window.subtitle.points[2][1], "RIGHT", "and runs to the window's right edge, so it stays on one line")
equal(window.subtitle.points[2][4], -14, "at the inset's edge")
equal(window.filterDropdown.points[1][1], "TOPRIGHT", "the filter is on its own row")
equal(window.filterDropdown.points[1][2], -14, "right-aligned to the inset")
equal(window.filterDropdown.points[1][3], -74, "below the subtitle")
equal(window.inset.points[1][1], "TOPLEFT", "the inset follows the filter")
equal(window.inset.points[1][3], -112, "moved down to fit it, with the window height unchanged")
equal(window.height, 380, "the window keeps its height; the list gets shorter")
page.Open()
check(framesMade == firstOpen, "opening twice creates no new frames")
page.Register("Pool Forever", {
	players = {
		{ name = "One", what = "The first report" },
	},
})
check(framesMade == firstOpen, "a shorter list reuses its rows")
check(page.window.rows[2].holder:IsShown() == false, "and hides the unused tail")
page.Register("Pool Forever", {
	players = {
		{ name = "One", what = "The first report" },
		{ name = "Two", what = "The second report" },
		{ name = "Three", what = "The third report" },
	},
})
check(framesMade == firstOpen + 1, "a longer list grows the pool by the row it needs")
check(page.window.rows[3].holder:IsShown(), "and shows the new row")
page.Toggle()
check(not page.IsShown(), "Toggle closes the page")
page.Toggle()
check(page.IsShown(), "and opens it again")
check(framesMade == firstOpen + 1, "with no new frames")

-- The addon filter: one addon's players stay, each showing that addon's own line; All puts every addon back.
page.Register("Other Forever", {
	players = {
		{ name = "Four", what = "The other idea" },
		{ name = "One", what = "The other line" },
	},
})
local dropdown = page.window.filterDropdown
check(dropdown ~= nil, "the header has its filter dropdown")
page.Open("Other Forever")
equal(dropdown:GetText(), "Other Forever", "the dropdown names the filtered addon")
local function ShownRows()
	local shown = {}
	for _, item in ipairs(page.window.rows) do
		if item.holder:IsShown() then
			shown[#shown + 1] = item.name.text
		end
	end
	return table.concat(shown, ", ")
end
equal(ShownRows(), "Four, One", "the filter keeps only that addon's players")
local one
for _, item in ipairs(page.window.rows) do
	if item.name.text == "One" and item.holder:IsShown() then
		one = item
	end
end
equal(one.detail.text, "The other line", "and each row shows that addon's what instead of the addon list")
page.Open()
equal(dropdown:GetText(), "Other Forever", "reopening with no title keeps the current filter")
page.Open(nil)
equal(dropdown:GetText(), "All addons", "an explicit nil shows every addon again")
equal(ShownRows(), "Four, One, Three, Two", "the unfiltered rows are back, in name order")
for _, item in ipairs(page.window.rows) do
	if item.name.text == "One" and item.holder:IsShown() then
		one = item
	end
end
equal(one.detail.text, "Pool Forever, Other Forever", "a row lists every addon that credits the player")
check(one.detail.wordWrap == false and one.detail.maxLines == 1, "the addon line is cut, never wrapped")

-- The filter is the client's own dropdown, and its menu is one radio per addon because the page shows one at a time.
local menu
own.ContextMenu = function(_, generator)
	menu = { entries = {} }
	generator(nil, {
		SetScrollMode = function() end,
		CreateRadio = function(_, text, selected, action)
			menu.entries[#menu.entries + 1] = { kind = "radio", text = text, selected = selected, action = action }
		end,
		CreateCheckbox = function(_, text)
			menu.entries[#menu.entries + 1] = { kind = "checkbox", text = text }
		end,
	})
end
equal(dropdown.template, "WowStyle1DropdownTemplate", "the filter is drawn as the client's own dropdown")
dropdown.OpenMenu(dropdown)
check(menu ~= nil, "the dropdown opens the suite's context menu")
equal(#menu.entries, 3, "every addon and All addons are choices")
equal(menu.entries[1].text, "All addons", "the first choice is every addon")
for _, entry in ipairs(menu.entries) do
	equal(entry.kind, "radio", "one addon at a time is a radio, never a checkbox")
end
check(menu.entries[1].selected(), "the current choice is marked")
check(not menu.entries[2].selected(), "and the others are not")

-- Hovering a row: the name as the title, then one wrapped line per addon with the addon in gold and its what white.
tooltip.lines, tooltip.title = {}, nil
one.holder.scripts.OnEnter(one.holder)
equal(tooltip.anchor, "ANCHOR_RIGHT", "the tooltip is anchored to the right of the row")
equal(tooltip.title, "One", "the tooltip is titled with the player")
equal(#tooltip.lines, 2, "one line per addon that credits them")
check(tooltip.lines[1].text:find("|cffffffffPool Forever|r", 1, true) ~= nil, "the addon is in the gold colour")
check(tooltip.lines[1].text:find("The first report", 1, true) ~= nil, "with what the player did for it")
equal(tooltip.lines[1].wrap, true, "the line wraps")
check(tooltip.lines[2].text:find("|cffffffffOther Forever|r", 1, true) ~= nil, "then the second addon")
check(tooltip.lines[2].text:find("The other line", 1, true) ~= nil, "with its own line")
one.holder.scripts.OnLeave(one.holder)
check(tooltip.shown == false, "leaving the row hides the tooltip")

-- Several addons that gave a player the identical words share one line, led by their names in registration order.
page.Register("Twin Forever", {
	players = {
		{ name = "One", what = "The first report" },
		{ name = "Six", what = "" },
	},
})
page.Register("Quiet Forever", {
	players = {
		{ name = "Six", what = "" },
	},
})
for _, item in ipairs(page.window.rows) do
	if item.name.text == "One" and item.holder:IsShown() then
		one = item
	end
end
tooltip.lines, tooltip.title = {}, nil
one.holder.scripts.OnEnter(one.holder)
equal(#tooltip.lines, 2, "an identical what line is drawn once, not once per addon")
check(
	tooltip.lines[1].text:find("|cffffffffPool Forever, Twin Forever|r: The first report", 1, true) ~= nil,
	"the line is led by every addon that gave it, in registration order"
)
check(tooltip.lines[2].text:find("|cffffffffOther Forever|r", 1, true) ~= nil, "then the addon with its own words")
one.holder.scripts.OnLeave(one.holder)

local six
for _, item in ipairs(page.window.rows) do
	if item.name.text == "Six" and item.holder:IsShown() then
		six = item
	end
end
tooltip.lines = {}
six.holder.scripts.OnEnter(six.holder)
equal(#tooltip.lines, 1, "an empty line shared by two addons is one line too")
check(tooltip.lines[1].text:find("|cffffffffTwin Forever, Quiet Forever|r", 1, true) ~= nil, "with both names in gold")
check(tooltip.lines[1].text:find(": ", 1, true) == nil, "and no colon when there are no words")
six.holder.scripts.OnLeave(six.holder)

print(("credits_spec: %d checks passed"):format(checks))
