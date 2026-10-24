-- Contract for the shared report window, issue composer and slash-command dispatch.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local widgets = {}
local function widget(widgetKind, widgetName)
	local value = { kind = widgetKind, name = widgetName, scripts = {}, text = "" }
	local methods = {}
	function methods:SetScript(name, callback)
		self.scripts[name] = callback
	end
	function methods:SetText(text)
		self.text = text
		self.highlighted = nil
	end
	function methods:GetText()
		return self.text
	end
	function methods:HighlightText(start)
		if start ~= nil and type(start) ~= "number" then
			error("HighlightText start must be a number")
		end
		self.highlighted = self.text
	end
	function methods:SetFocus()
		self.focused = true
	end
	function methods:Show()
		self.shown = true
	end
	function methods:Hide()
		self.shown = false
	end
	function methods:SetTitle(text)
		self.title = text
	end
	function methods:GetPortrait()
		self.hasPortrait = true
		return widget("Texture")
	end
	function methods:CreateFontString()
		self.createdFontString = true
		return widget("FontString")
	end
	function methods:SetScrollChild(child)
		self.child = child
	end
	setmetatable(value, {
		__index = function(_, key)
			return methods[key] or function() end
		end,
	})
	widgets[#widgets + 1] = value
	return value
end

_G.UIParent = {}
_G.UISpecialFrames = {}
_G.CreateFrame = function(kind, name)
	return widget(kind, name)
end
_G.GameFontNormal, _G.ChatFontNormal = {}, {}
_G.C_AddOns = {
	GetAddOnMetadata = function(_, key)
		return key == "X-Website" and "https://github.com/cjber/example-addon" or "1.0.0"
	end,
}

local phrases = setmetatable({}, {
	__index = function(_, key)
		return key
	end,
})
local reportLinesCalls = 0
local ns = {
	L = phrases,
	Art = { Icon = function() end },
	ReportLines = function()
		reportLinesCalls = reportLinesCalls + 1
		return { "addon details" }
	end,
}
_G.strtrim = function(text)
	return text:match("^%s*(.-)%s*$")
end
_G.geterrorhandler = function()
	return function() end
end
assert(loadfile("Core/SafeCall.lua"))("ForeverCore", ns)
local chunk = assert(loadfile("UI/Report.lua"))
chunk("ExampleAddon", ns)
ns.ReportTitle = "ExampleAddon report"
ns.Report.Text = function(lines)
	return table.concat(lines, "\n")
end

equal(ns.Report.Command("unknown"), false, "unknown command remains for addon handler")
equal(ns.Report.Command("report"), true, "report command handled")
equal(reportLinesCalls, 1, "report command gets addon lines")

local reportBox
for _, value in ipairs(widgets) do
	if value.kind == "EditBox" and value.scripts.OnEditFocusGained then
		reportBox = value
		break
	end
end
equal(reportBox ~= nil, true, "report edit box created")
reportBox.scripts.OnEditFocusGained(reportBox, true)
equal(reportBox.highlighted, "addon details", "focus selects report text")

equal(ns.Report.Command("issue", "feature"), true, "issue command handled")
local issueWindow
for _, value in ipairs(widgets) do
	if value.name == "ExampleAddonIssue" then
		issueWindow = value
	end
end
equal(issueWindow.kind, "feature", "issue argument selects feature request")
local issueBox
for _, value in ipairs(widgets) do
	if value.kind == "EditBox" and value.scripts.OnEditFocusGained and value ~= reportBox then
		issueBox = value
	end
end
equal(issueBox ~= nil, true, "issue output box created")
issueBox.scripts.OnEditFocusGained(issueBox, true)
equal(issueBox.highlighted, issueBox.text, "focus selects issue link")

print(("report_spec: %d checks passed"):format(checks))
