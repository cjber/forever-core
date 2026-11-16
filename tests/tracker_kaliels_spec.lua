-- KT 8.11.1's outer frame stays at maxHeight; Background is the visible list end.
local harness = dofile("tests/tracker_host_harness.lua")
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end
local function near(a, b)
	return math.abs(a - b) < 0.001
end
local function scenario()
	local bridge = {}
	local ns = { TrackerKaliels = bridge, L = setmetatable({}, {
		__index = function(_, key)
			return key
		end,
	}) }
	local t = harness.new({ deferReady = true, ns = ns })
	local source = {}
	setfenv(assert(loadfile("UI/TrackerQuestie.lua")), t.env)("Test", source)
	setfenv(assert(loadfile("UI/TrackerKaliels.lua")), t.env)("Test", source)
	for key, value in pairs(source.TrackerKaliels) do
		bridge[key] = value
	end
	t.env.ForeverTrackerHost = nil
	local frame = t.env.CreateFrame
	local outer = frame("Frame")
	outer.top, outer.left, outer.width, outer.height = 800, 600, 400, 600
	outer.effectiveScale = 0.8
	local edge = frame("Frame")
	edge.top, edge.left, edge.width, edge.height = 800, 600, 400, 180
	edge.effectiveScale = 0.8
	outer.Background = edge
	local content = frame("Frame")
	content.left, content.width, content.effectiveScale = 624, 352, 0.8
	t.env["!KalielsTrackerFrame"], t.env.KT_ObjectiveTrackerFrame = outer, content
	local function tick()
		for _, f in ipairs(t.frames) do
			if f.scripts.OnUpdate then
				f.scripts.OnUpdate(f, 1)
			end
		end
		t.drain()
	end
	return t, outer, edge, content, tick
end
local t, outer, edge, content, tick = scenario()
t.ready()
t.drain()
check(t.host:IsShown(), "KT attached sections show")
check(near(t.host:GetWidth(), 352), "column uses inner KT content width")
check(near(t.host:GetEffectiveScale(), 0.8), "column follows KT scale")
check(t.host.point[2] == t.parent, "column anchors to UIParent, never KT")
-- UIParent uses 1000 units in the harness; convert its height to the host scale.
local screenHeight = t.parent:GetHeight() * t.parent:GetEffectiveScale() / t.host:GetEffectiveScale()
check(near(t.host.point[5], edge:GetBottom() - 8 - screenHeight), "column follows visible Background bottom")
check(near(t.host.point[4], content:GetLeft()), "column aligns with inner content left")
outer.left, edge.left, content.left = 500, 500, 524
edge.height, content.width = 240, 300
tick()
check(near(t.host:GetWidth(), 300), "resize updates section width")
check(near(t.host.point[4], 524), "silent move follows KT")
check(near(t.host.point[5], edge:GetBottom() - 8 - screenHeight), "content growth follows visible bottom")
local heldX, heldY, heldWidth = t.host.point[4], t.host.point[5], t.host:GetWidth()
t.setCombat(true)
content.left, content.width, edge.height = 424, 280, 280
tick()
check(
	t.host.point[4] == heldX and t.host.point[5] == heldY and t.host:GetWidth() == heldWidth,
	"combat holds all protected geometry"
)
t.setCombat(false)
t.fire("PLAYER_REGEN_ENABLED")
t.drain()
check(near(t.host:GetWidth(), 280) and near(t.host.point[4], 424), "combat end applies deferred layout")
content.isCollapsed = true
tick()
check(not t.host:IsShown(), "KT collapse hides sections without native fallback")
content.isCollapsed = false
tick()
check(t.host:IsShown(), "KT expand restores sections")
outer:Hide()
tick()
check(not t.host:IsShown(), "KT hide hides attached sections")
outer:Show()
tick()
check(t.host:IsShown(), "KT show restores sections")
outer.effectiveScale, edge.effectiveScale, content.effectiveScale = 1.2, 1.2, 1.2
tick()
check(near(t.host:GetEffectiveScale(), 1.2), "silent scale change follows KT")
t.ns.TrackerHost.SetAttached(false)
t.drain()
local observer
for _, f in ipairs(t.frames) do
	if f.events and f.events.ADDON_LOADED then
		observer = f
	end
end
check(observer and observer.scripts.OnUpdate == nil, "detached host stops KT polling")
t.ns.TrackerHost.SetAttached(true)
t.drain()
t.env["!KalielsTrackerFrame"] = nil
t.host:MarkDirty()
t.drain()
check(t.host.point[2] == t.native.NineSlice, "absent KT restores native layout")
check(t.first.Header:GetWidth() == t.host:GetWidth(), "native header width restored")
-- Only Forever-owned instances are restyled, and pooled text gets its font before measurement.
local function text(path, size)
	local f = { font = { path, size, "" }, points = { { "LEFT", 7, 0 } } }
	function f:GetFont()
		return unpack(self.font)
	end
	function f:SetFont(...)
		self.font = { ... }
	end
	function f:GetNumPoints()
		return #self.points
	end
	function f:GetPoint(index)
		return unpack(self.points[index])
	end
	function f:ClearAllPoints()
		self.points = {}
	end
	function f:SetPoint(...)
		self.points[#self.points + 1] = { ... }
	end
	return f
end
local function texture()
	return {
		SetTexCoord = function(self, ...)
			self.coords = { ... }
		end,
		SetAllPoints = function() end,
		SetVertexColor = function() end,
	}
end
local create = t.env.CreateFrame
t.env.CreateFrame = function(...)
	local f = create(...)
	function f:SetSize(w, h)
		self.width, self.height = w, h
	end
	function f:SetNormalTexture(value)
		self.texture = value
		self.normal = self.normal or texture()
	end
	function f:GetNormalTexture()
		return self.normal
	end
	return f
end
local reference = {
	GetTexture = function()
		return "KT-sprite"
	end,
	GetVertexColor = function()
		return 1, 1, 1, 1
	end,
}
local heading, body = text("KT-font", 15), text("KT-font", 14)
t.env.KT_QuestObjectiveTracker =
	{ Header = { Text = heading, Icon = reference }, usedBlocks = { Quest = { { HeaderText = body } } } }
local header = create("Frame")
header.Text, header.MinimizeButton = text("native", 12), create("Button")
local toggles = 0
header.OnToggle = function()
	toggles = toggles + 1
end
header.SetCollapsed = function() end
local line = { Text = text("native", 11), Dash = text("native", 11) }
local block = { HeaderText = text("native", 11) }
block.GetLine = function()
	return line
end
block.SetStringText = function(_, value)
	check(value.font[1] == "KT-font", "font applied before measurement")
end
local module = {
	Header = header,
	GetBlock = function()
		return block, true
	end,
	IsCollapsed = function()
		return false
	end,
}
local style = t.ns.TrackerKaliels.Style
style(module, true)
check(header.Text.font[1] == "KT-font" and header.Text.font[2] == 15, "heading matches live KT font")
local result, wasActive = module:GetBlock()
check(result == block and wasActive, "GetBlock preserves native results")
result:GetLine()
result:SetStringText(line.Text)
check(line.Dash.font[2] == 14 and block.HeaderText.font[2] == 14, "pooled body and dash match KT")
check(
	not header.MinimizeButton:IsShown() and module.kalielsCollapse.button:IsShown(),
	"left control replaces native control"
)
local button = module.kalielsCollapse.button
button.scripts.OnClick()
check(toggles == 1, "left control invokes own header toggle")
t.setCombat(true)
button.scripts.OnClick()
check(toggles == 1, "combat defers protected collapse")
t.setCombat(false)
header:SetCollapsed(true)
check(button:GetNormalTexture().coords[1] == 0, "collapsed control uses KT expand sprite")
style(module, false)
check(header.Text.font[1] == "native" and line.Text.font[1] == "native", "detach restores original fonts")
check(header.MinimizeButton:IsShown() and not button:IsShown(), "detach restores native control")
check(header.Text.points[1][2] == 7, "detach restores original text anchor")
style(module, true)
check(line.Text.font[1] == "KT-font", "reattach restyles pooled text")
-- A released template instance can move between Forever sections and native modules.
local pooledLine = { Text = text("row-native", 10), Dash = text("dash-native", 9) }
local measured
local pooled = { HeaderText = text("block-native", 11) }
local nativeGetLine = function()
	return pooledLine
end
local nativeSetString = function(_, value)
	measured = value.font[1]
end
local nativeFreeLine = function(_, value)
	check(value.Text.font[1] == "row-native", "line font restored before pool release")
	check(value.Dash.font[1] == "dash-native", "dash font restored before pool release")
end
pooled.GetLine, pooled.SetStringText, pooled.FreeLine = nativeGetLine, nativeSetString, nativeFreeLine
local function section()
	local owner = { Header = { Text = text("section-native", 12) } }
	owner.GetBlock = function(self)
		pooled.parentModule = self
		return pooled, false
	end
	owner.FreeBlock = function(_, value)
		check(value.HeaderText.font[1] == "block-native", "block font restored before pool release")
		check(
			value.GetLine == nativeGetLine and value.SetStringText == nativeSetString,
			"block methods restored before pool release"
		)
		value:FreeLine(pooledLine)
		return "released"
	end
	return owner
end
local first, second = section(), section()
style(first, true)
first:GetBlock():GetLine()
pooled:SetStringText(pooledLine.Text)
check(measured == "KT-font", "first owner matches KT before measurement")
check(first:FreeBlock(pooled) == "released", "FreeBlock preserves return value")
-- The next owner is native and never calls Style.
pooled.parentModule = {}
pooled:SetStringText(pooledLine.Text)
check(measured == "row-native", "native owner measures original font")
style(first, false)
style(first, true)
check(pooledLine.Text.font[1] == "row-native", "former owner cannot restyle released rows")
style(second, true)
second:GetBlock():GetLine()
pooled:SetStringText(pooledLine.Text)
check(measured == "KT-font", "second Forever owner matches KT")
style(first, false)
check(pooledLine.Text.font[1] == "KT-font", "former owner detach leaves current owner unchanged")
pooled:FreeLine(pooledLine)
style(second, false)
style(second, true)
check(pooledLine.Text.font[1] == "row-native", "released line stays native during owner style changes")
pooled:GetLine()
check(pooledLine.Text.font[1] == "KT-font", "reacquired line matches current owner")
second:FreeBlock(pooled)
print("tracker_kaliels_spec: " .. checks .. " checks passed")
