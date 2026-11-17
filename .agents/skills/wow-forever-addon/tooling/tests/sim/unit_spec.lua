-- forever_sim's offline unit specs (no UI source needed): luajit tests/sim/unit_spec.lua, from tooling/.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
package.path = here .. "../../forever_sim/?.lua;" .. package.path

local XML = require("xml")
local Instrument = require("instrument")
local Veil = require("veil")
local Taint = require("taint")
local Loader = require("loader")
local Client = require("client")

-- A client built on its own, without the Blizzard UI source: enough for the error handler and the native stubs.
local function freshClient()
	Taint.current = nil
	Taint.globalTaint = {}
	local sim = { taint = Taint, impl = {} }
	local G = Client.build(sim)
	return sim, G
end

local passed, failed = 0, 0
local function test(name, fn)
	local ok, err = pcall(fn)
	if ok then
		passed = passed + 1
	else
		failed = failed + 1
		print("FAIL " .. name .. "\n  " .. tostring(err))
	end
end
local function eq(a, b, label)
	if a ~= b then
		error(string.format("%s: expected %s, got %s", label or "value", tostring(b), tostring(a)), 2)
	end
end

test("widgets: EditBox inserts at the caret, replaces selection and respects maxLetters", function()
	local widgets = require("widgets").build({ G = {}, env = {}, taint = Taint, docs = { enums = {}, widgets = {} } })
	widgets.finalize()
	local edit = widgets.new("EditBox")
	edit:SetText("ab")
	edit:SetCursorPosition(1)
	edit:Insert("X")
	eq(edit:GetText(), "aXb", "caret insertion")
	eq(edit:GetCursorPosition(), 2, "caret follows inserted text")
	edit:HighlightText(1, 2)
	edit:Insert("YZ")
	eq(edit:GetText(), "aYZb", "selection replacement")
	edit:SetMaxLetters(5)
	edit:HighlightText(1, 3)
	edit:Insert("12345")
	eq(edit:GetText(), "a123b", "limit preserves unselected suffix")
	eq(edit:GetCursorPosition(), 4)
	edit:Insert("ignored")
	eq(edit:GetText(), "a123b", "full box accepts no more text")
	edit:SetMaxLetters(0)
	edit:HighlightText()
	edit:Insert("new")
	eq(edit:GetText(), "new", "default highlight replaces all text")
	edit:Insert("!")
	eq(edit:GetText(), "new!", "insertion clears selection")
end)

test("stubgen: MayReturnNothing defaults to no results but preserves implementations", function()
	local sim, G = freshClient()
	sim.dataDir = here .. "../../forever_sim/no-data"
	sim.docs = {
		enums = {},
		constants = {},
		events = {},
		widgets = {},
		structures = {},
		systems = {
			{ Functions = { { Name = "OptionalResult", MayReturnNothing = true, Returns = { { Type = "number" } } } } },
		},
	}
	require("stubgen").build(sim)
	eq(select("#", G.OptionalResult()), 0, "absent optional result")
	sim.impl.OptionalResult = function()
		return 7
	end
	eq(G.OptionalResult(), 7, "explicit implementation")
end)

test("widgets: GetAttribute reads the secure prefix and suffix form", function()
	Taint.current = nil
	local widgets = require("widgets").build({ G = {}, env = {}, taint = Taint, docs = { enums = {}, widgets = {} } })
	widgets.finalize()
	local frame = widgets.new("Frame")
	frame:SetAttribute("type", "item")
	frame:SetAttribute("shift-type1", "shifted")
	frame:SetAttribute("*action2", "wildcard")
	eq(frame:GetAttribute("type"), "item", "plain attribute")
	eq(frame:GetAttribute("", "type", ""), "item", "secure form without modifiers")
	eq(frame:GetAttribute("shift-", "type", "1"), "shifted", "secure form with a modifier and button")
	eq(frame:GetAttribute("*", "action", "2"), "wildcard", "secure wildcard form")
	eq(frame:GetAttribute("", "missing", ""), nil, "missing secure attribute")
end)

test("widgets: scroll callbacks only report changed offsets", function()
	Taint.current = nil
	local widgets = require("widgets").build({ G = {}, env = {}, taint = Taint, docs = { enums = {}, widgets = {} } })
	widgets.finalize()
	for _, axis in ipairs({ "Vertical", "Horizontal" }) do
		local frame = widgets.new("ScrollFrame")
		local calls = 0
		local setter, getter = frame["Set" .. axis .. "Scroll"], frame["Get" .. axis .. "Scroll"]
		frame:SetScript("On" .. axis .. "Scroll", function(self, offset)
			calls = calls + 1
			eq(getter(self), offset, "callback observes stored offset")
			-- A scrollbar callback can write the same offset back, as Blizzard's map legend does.
			assert(calls <= 3, "unchanged offset recursively fires the scroll handler")
			setter(self, offset)
		end)
		setter(frame, 0)
		eq(calls, 0, axis .. " initial zero")
		setter(frame, 12)
		eq(calls, 1, axis .. " change fires once")
		setter(frame, 12)
		eq(calls, 1, axis .. " unchanged offset")
		setter(frame, 0)
		eq(calls, 2, axis .. " returning to zero")
	end
end)

test("widgets: scrolling moves child geometry, nested content and controls", function()
	Taint.current = nil
	local widgets = require("widgets").build({
		G = {},
		env = {},
		taint = Taint,
		screenWidth = 1000,
		screenHeight = 800,
		docs = { enums = {}, widgets = {} },
	})
	widgets.finalize()
	local root = widgets.new("Frame")
	widgets.setRoot(root)
	root:SetSize(500, 500)
	root:SetPoint("BOTTOMLEFT", nil, "BOTTOMLEFT", 0, 0)
	local scroll = widgets.new("ScrollFrame", nil, root)
	scroll:SetSize(100, 100)
	scroll:SetPoint("TOPLEFT", root, "TOPLEFT", 10, -10)
	local child = widgets.new("Frame", nil, scroll)
	child:SetSize(300, 400)
	child:SetPoint("TOPLEFT", scroll, "TOPLEFT")
	scroll:SetScrollChild(child)
	local control = widgets.new("Button", nil, child)
	control:SetSize(20, 20)
	control:SetPoint("TOPLEFT", child, "TOPLEFT", 5, -5)
	local sibling = widgets.new("Frame", nil, scroll)
	sibling:SetSize(10, 10)
	sibling:SetPoint("TOPLEFT", scroll, "TOPLEFT")
	local left, top = child:GetLeft(), child:GetTop()
	local controlLeft, controlTop = control:GetLeft(), control:GetTop()
	local siblingTop = sibling:GetTop()
	scroll:SetScript("OnVerticalScroll", function()
		eq(child:GetTop(), top + 50, "callback observes updated geometry")
	end)
	scroll:SetVerticalScroll(50)
	scroll:SetHorizontalScroll(25)
	eq(child:GetTop(), top + 50, "child vertical translation")
	eq(child:GetLeft(), left - 25, "child horizontal translation")
	eq(control:GetTop(), controlTop + 50, "control inherits vertical translation")
	eq(control:GetLeft(), controlLeft - 25, "control inherits horizontal translation")
	eq(sibling:GetTop(), siblingTop, "non-scroll child stays fixed")
	assert(control:GetTop() > scroll:GetTop(), "off-viewport control keeps its actual screen position")
	local nested = widgets.new("ScrollFrame", nil, child)
	nested:SetSize(50, 50)
	nested:SetPoint("TOPLEFT", child, "TOPLEFT", 0, -100)
	local inner = widgets.new("Frame", nil, nested)
	inner:SetSize(100, 100)
	inner:SetPoint("TOPLEFT", nested, "TOPLEFT")
	nested:SetScrollChild(inner)
	local innerTop = inner:GetTop()
	nested:SetVerticalScroll(10)
	eq(inner:GetTop(), innerTop + 10, "nested scroll applies once")
	scroll:SetScript("OnVerticalScroll", nil)
	scroll:SetVerticalScroll(70)
	eq(inner:GetTop(), innerTop + 30, "outer and nested offsets compose")
	scroll:SetVerticalScroll(0)
	scroll:SetHorizontalScroll(0)
	nested:SetVerticalScroll(0)
	eq(child:GetTop(), top, "reset restores child vertical position")
	eq(child:GetLeft(), left, "reset restores child horizontal position")
	eq(control:GetTop(), controlTop, "reset restores descendant position")
	scroll:SetScale(2)
	child:SetScale(0.5)
	local scaledTop, scaledLeft = child:GetTop(), child:GetLeft()
	scroll:SetVerticalScroll(30)
	scroll:SetHorizontalScroll(20)
	eq(child:GetTop(), scaledTop + 60, "scroll offset uses viewport scale, not child scale")
	eq(child:GetLeft(), scaledLeft - 40, "scaled horizontal offset")
end)

test("widgets: side anchors do not stretch a sized tracker block vertically", function()
	Taint.current = nil
	local widgets = require("widgets").build({
		G = {},
		env = {},
		taint = Taint,
		screenWidth = 1000,
		screenHeight = 800,
		docs = { enums = {}, widgets = {} },
	})
	widgets.finalize()
	local root = widgets.new("Frame")
	widgets.setRoot(root)
	local first = widgets.new("Frame", nil, root)
	first:SetHeight(40)
	first:SetPoint("TOP", root, "TOP", 0, -10)
	first:SetPoint("LEFT", root, "LEFT")
	first:SetPoint("RIGHT", root, "RIGHT")
	local second = widgets.new("Frame", nil, root)
	second:SetHeight(60)
	second:SetPoint("TOP", first, "BOTTOM", 0, -10)
	second:SetPoint("LEFT", root, "LEFT")
	second:SetPoint("RIGHT", root, "RIGHT")
	eq(first:GetHeight(), 40, "first explicit height")
	eq(first:GetTop(), 790, "top anchor")
	eq(second:GetTop(), 740, "second block follows first bottom")
	eq(second:GetHeight(), 60, "second explicit height")
	eq(first:GetWidth(), 1000, "opposite horizontal edges stretch width")
end)

test("widgets: intrinsic text height agrees with its screen rectangle and header button", function()
	Taint.current = nil
	local widgets = require("widgets").build({
		G = {},
		env = {},
		taint = Taint,
		screenWidth = 1000,
		screenHeight = 800,
		docs = { enums = {}, widgets = {} },
	})
	widgets.finalize()
	local root = widgets.new("Frame")
	widgets.setRoot(root)
	local block = widgets.new("Frame", nil, root)
	block:SetSize(200, 80)
	block:SetPoint("TOPLEFT", root, "TOPLEFT", 0, 0)
	local text = widgets.new("FontString", nil, block)
	text:SetText("One row")
	text:SetPoint("TOPLEFT", block, "TOPLEFT")
	text:SetPoint("RIGHT", block, "RIGHT")
	local button = widgets.new("Button", nil, block)
	button:SetPoint("TOPLEFT", text, "TOPLEFT")
	button:SetPoint("BOTTOMRIGHT", text, "BOTTOMRIGHT")
	eq(text:GetTop() - text:GetBottom(), text:GetHeight(), "text rectangle uses intrinsic height")
	eq(button:GetHeight(), text:GetHeight(), "header button follows text height")
	text:SetPoint("BOTTOMLEFT", block, "BOTTOMLEFT")
	eq(text:GetTop() - text:GetBottom(), 80, "explicit top and bottom stretch text")
end)

test("widgets: SetToDefaults clears anchors, as Compositor's PoolReset relies on", function()
	Taint.current = nil
	local widgets = require("widgets").build({ G = {}, env = {}, taint = Taint, docs = { enums = {}, widgets = {} } })
	widgets.finalize()
	local parent = widgets.new("Frame")
	local region = widgets.new("Frame", parent)
	region:SetPoint("LEFT", parent, "LEFT", 4, 0)
	eq(region:GetNumPoints(), 1, "anchored")
	region:SetToDefaults()
	eq(region:GetNumPoints(), 0, "anchors cleared")
end)

test("widgets: GetHighestFrameLevel reads direct children, or every descendant when asked", function()
	Taint.current = nil
	local widgets = require("widgets").build({ G = {}, env = {}, taint = Taint, docs = { enums = {}, widgets = {} } })
	widgets.finalize()
	local parent = widgets.new("Frame")
	local child = widgets.new("Frame", nil, parent)
	local grandchild = widgets.new("Frame", nil, child)
	parent:SetFrameLevel(2)
	child:SetFrameLevel(5)
	grandchild:SetFrameLevel(9)
	eq(parent:GetHighestFrameLevel(), 5, "direct children by default")
	eq(parent:GetHighestFrameLevel(true), 9, "every descendant")
	eq(grandchild:GetHighestFrameLevel(), 9, "a frame with no children")
end)

test("widgets: a HasRestrictions method is refused to tainted code in combat, unless always refused", function()
	Taint.current = nil
	local blocked = {}
	local sim = {
		G = {},
		env = {},
		taint = Taint,
		restrictionOverrides = {
			SetPassThroughButtons = { class = "always", issue = "cjber/adventure-guide-forever#534" },
		},
		docs = {
			enums = {},
			widgets = {
				SimpleFrameAPI = {
					Functions = { { Name = "SetPropagateKeyboardInput", HasRestrictions = true, Arguments = {} } },
				},
				SimpleScriptRegionAPI = {
					Functions = {
						{
							Name = "SetPassThroughButtons",
							IsProtectedFunction = true,
							HasRestrictions = true,
							Arguments = {},
						},
					},
				},
			},
		},
	}
	sim.blocked = function(_, name)
		blocked[#blocked + 1] = name
	end
	local widgets = require("widgets").build(sim)
	widgets.finalize()
	local frame = widgets.new("Frame")
	Taint.set("Addon")
	frame:SetPropagateKeyboardInput(true)
	frame:SetPassThroughButtons("RightButton")
	sim.combatLockdown = true
	frame:SetPropagateKeyboardInput(true)
	Taint.set(nil)
	eq(table.concat(blocked, ","), "SetPassThroughButtons,SetPropagateKeyboardInput")
end)

test("widgets: FocusEnter and FocusExit run OnEnter and OnLeave in the caller's taint", function()
	Taint.current = nil
	local widgets = require("widgets").build({ G = {}, env = {}, taint = Taint, docs = { enums = {}, widgets = {} } })
	widgets.finalize()
	local frame = widgets.new("Button")
	local seen = {}
	frame:SetScript("OnEnter", function()
		seen[#seen + 1] = "enter:" .. tostring(Taint.current)
	end)
	frame:SetScript("OnLeave", function()
		seen[#seen + 1] = "leave:" .. tostring(Taint.current)
	end)
	frame:FocusEnter()
	Taint.set("Addon")
	frame:FocusExit()
	Taint.set(nil)
	eq(table.concat(seen, ","), "enter:nil,leave:Addon")
end)

test("widgets: a script's setter taint stops when the handler returns", function()
	Taint.current = nil
	local widgets = require("widgets").build({ G = {}, env = {}, taint = Taint, docs = { enums = {}, widgets = {} } })
	widgets.finalize()
	local frame = widgets.new("Frame")
	local seen
	Taint.set("Addon")
	frame:SetScript("OnSizeChanged", function()
		seen = Taint.current
	end)
	Taint.set(nil)
	frame:SetSize(10, 10)
	eq(seen, "Addon", "the handler runs tainted")
	eq(Taint.current, nil, "the caller that triggered it stays secure")
end)

test("widgets: size notifications reflect changed dimensions exactly once", function()
	Taint.current = nil
	local widgets = require("widgets").build({
		G = {},
		env = {},
		taint = Taint,
		screenWidth = 1000,
		screenHeight = 800,
		docs = { enums = {}, widgets = {} },
	})
	widgets.finalize()
	local frame = widgets.new("Frame")
	frame:SetSize(20, 30)
	widgets.sizePass()
	local count = 0
	frame:SetScript("OnSizeChanged", function(self, width, height)
		count = count + 1
		assert(count < 8, "unchanged size setter must not recurse")
		eq(width, self:GetWidth(), "callback width")
		eq(height, self:GetHeight(), "callback height")
		self:SetHeight(height)
	end)
	frame:SetHeight(30)
	frame:SetWidth(20)
	frame:SetSize(20, 30)
	eq(count, 0, "unchanged dimensions have no notification")
	frame:SetHeight(40)
	eq(count, 1, "changed height notifies once")
	widgets.sizePass()
	eq(count, 1, "size pass does not duplicate synchronous notification")
	frame:SetSize(50, 60)
	eq(count, 2, "changed pair notifies once")
	widgets.sizePass()
	eq(count, 2, "changed pair is not repeated")
	frame:SetWidth(70)
	eq(count, 3, "changed width notifies once")
	widgets.sizePass()
	eq(count, 3, "changed width is not repeated")
	local root = widgets.new("Frame")
	widgets.setRoot(root)
	local parent = widgets.new("Frame", nil, root)
	parent:SetPoint("TOPLEFT", root, "TOPLEFT")
	parent:SetSize(100, 100)
	frame:SetAllPoints(parent)
	widgets.sizePass()
	eq(count, 4, "anchor-driven dimension change notifies")
	parent:SetSize(120, 130)
	widgets.sizePass()
	eq(count, 5, "parent resizing notifies anchored child")
end)

test("widgets: a Frame refuses OnClick, as the client does", function()
	Taint.current = nil
	local widgets = require("widgets").build({ G = {}, env = {}, taint = Taint, docs = { enums = {}, widgets = {} } })
	widgets.finalize()
	local frame = widgets.new("Frame")
	eq(frame:HasScript("OnClick"), false, "HasScript OnClick on a Frame")
	local ok, err = pcall(function()
		frame:SetScript("OnClick", function() end)
	end)
	eq(ok, false, "SetScript OnClick")
	assert(
		tostring(err):find(
			"Frame:SetScript(): Cannot assign script handler for 'onclick' (script type not supported by this object)",
			1,
			true
		),
		err
	)
	ok, err = pcall(function()
		frame:HookScript("OnClick", function() end)
	end)
	eq(ok, false, "HookScript OnClick")
	assert(
		tostring(err):find(
			"Frame:HookScript(): Cannot assign script handler for 'onclick' (script type not supported by this object)",
			1,
			true
		),
		err
	)
	ok = pcall(function()
		frame:SetScript("OnClick", nil)
	end)
	eq(ok, false, "SetScript OnClick nil")
end)

test("widgets: a Button supports OnClick and the scripts it inherits, in any case", function()
	Taint.current = nil
	local widgets = require("widgets").build({ G = {}, env = {}, taint = Taint, docs = { enums = {}, widgets = {} } })
	widgets.finalize()
	local button = widgets.new("Button")
	eq(button:HasScript("OnClick"), true, "OnClick")
	eq(button:HasScript("onclick"), true, "OnClick lower-case")
	eq(button:HasScript("ONSHOW"), true, "OnShow inherited from Frame, upper-case")
	eq(button:HasScript("onloop"), false, "OnLoop belongs to an AnimationGroup")
	local handler = function() end
	button:SetScript("onclick", handler)
	eq(button:GetScript("OnClick"), handler, "SetScript stores the client's spelling")
	eq(button:GetScript("ONCLICK"), handler, "GetScript is case-insensitive too")
end)

test("loader: bootstrap markers retain matching game conditions", function()
	local toc = Loader.parseToc(
		"Shared.lua [Bootstrap]\nWrong.lua [Bootstrap] [AllowLoadGameType cata]\n"
			.. "[Family]/Right.lua [Bootstrap] [AllowLoadGameType mainline]\nNormal.lua\n"
	)
	eq(#toc.files, 3)
	eq(toc.bootstrap["Shared.lua"], true)
	eq(toc.bootstrap["Mainline/Right.lua"], true)
	eq(toc.bootstrap["Wrong.lua"], nil)
	eq(toc.bootstrap["Normal.lua"], nil)
end)

test("loader: addon metadata excludes unsupported game types on every load path", function()
	eq(Loader.eligible({}), true)
	eq(Loader.eligible({ AllowLoadGameType = "cata, camelot" }), true)
	eq(Loader.eligible({ AllowLoadGameType = "cata" }), false)
	eq(Loader.eligible({ ExcludeLoadGameType = "cata, camelot" }), false)
	eq(Loader.eligible({ ExcludeLoadGameType = "cata" }), true)
	eq(Loader.eligible({ AllowLoad = "Glue" }), false)
end)

test("xml: elements, attributes, entities, CDATA and line numbers", function()
	local root = XML.parse(
		'<Ui>\n<Frame name="A" x="1 &amp; 2">\n<Scripts><OnLoad><![CDATA[print("<hi>")]]></OnLoad></Scripts>'
			.. "\n</Frame>\n</Ui>",
		"t.xml"
	)
	eq(root.tag, "Ui")
	local frame = root.children[1]
	eq(frame.attr.name, "A")
	eq(frame.attr.x, "1 & 2")
	eq(frame.line, 2, "line")
	eq(frame.children[1].children[1].text, 'print("<hi>")')
	local ok = pcall(XML.parse, "<Ui><Frame></Ui>", "bad.xml")
	eq(ok, false, "mismatched close")
end)

test("instrument: every function body and the chunk start report the addon, lines unchanged", function()
	local src = 'local f = function(a) return a end -- function(x)\nlocal s = "function(" .. [[ function( ]]\n'
		.. "function t.m:n(b, c) local g = function() end end"
	local out = Instrument.rewrite(src, "Addon")
	local _, markers = out:gsub('__fst%("Addon"%);', "")
	eq(markers, 4, "markers")
	local _, lines = out:gsub("\n", "")
	eq(lines, 2, "newlines")
	assert(loadstring(out))
end)

test("instrument: table constructor fields carry the writer's taint, as an assignment does", function()
	Taint.reset()
	local G = {}
	local env = Taint.environment(G)
	Taint.install(G, env)
	env.__fst = function(addon)
		Taint.set(addon, { addon = addon, kind = "execution" })
	end
	local chunk = assert(loadstring(Instrument.rewrite("return { x = 1, { y = 2 }, [3] = { z = 3 } }", "Addon")))
	setfenv(chunk, env)
	local t = chunk()
	Taint.set(nil)
	local x = Taint.slotInfo(t, "x")
	eq(x and x.addon, "Addon", "named field")
	local array = Taint.slotInfo(t, 1)
	eq(array and array.addon, "Addon", "array field")
	local keyed = Taint.slotInfo(t, 3)
	eq(keyed and keyed.addon, "Addon", "keyed field")
	local nested = Taint.slotInfo(t[1], "y")
	eq(nested and nested.addon, "Addon", "nested constructor field")
end)

test("instrument: a multiple assignment computes every target index before the first write", function()
	-- Writing each index as it is reached would make the second `#t` count the first append and leave a hole.
	local out = Instrument.rewrite("local t = {} t[#t + 1], t[#t + 2] = 1, 2 return #t", "Addon")
	local _, newlines = out:gsub("\n", "")
	eq(newlines, 0, "newlines")
	local chunk = assert(loadstring(out))
	setfenv(chunk, {
		__fst = function() end,
		__fsi_set = function(t, k, v)
			t[k] = v
		end,
		__fsi_ctor = function(t)
			return t
		end,
	})
	eq(chunk(), 2, "#t")
end)

test("instrument: the Blizzard rewrite cache is written to a temporary file and renamed into place", function()
	local scratch = "tools/.cache/forever_sim/spec-cache-" .. (tostring({}):gsub("%W", ""))
	local src = "local probe = 1 -- cache write probe\n"
	local opened, renamed = {}, {}
	local realOpen, realRename = io.open, os.rename
	rawset(io, "open", function(path, mode)
		opened[#opened + 1] = { path = path, mode = mode or "r" }
		return realOpen(path, mode)
	end)
	rawset(os, "rename", function(from, to)
		renamed[#renamed + 1] = { from = from, to = to }
		return realRename(from, to)
	end)
	local called, out = pcall(Instrument.rewriteBlizzard, src, scratch, "1.60.1.70124")
	rawset(io, "open", realOpen)
	rawset(os, "rename", realRename)
	local dest = renamed[1] and renamed[1].to
	local ok, problem = pcall(function()
		assert(called, out)
		for _, call in ipairs(opened) do
			if call.mode:find("[wa+]") then
				assert(not call.path:match("%.lua$"), "a cache entry was opened for writing: " .. call.path)
			end
		end
		eq(#renamed, 1, "renames")
		local tmp = renamed[1].from
		assert(dest:match("%.lua$"), "the rename target is not a cache entry: " .. tostring(dest))
		local dir = dest:match("^(.*)/[^/]+$")
		assert(
			tmp ~= dest and tmp:match("^(.*)/[^/]+$") == dir,
			"the temporary file is not beside the cache entry: " .. tostring(tmp)
		)
		local wroteTmp = false
		for _, call in ipairs(opened) do
			if call.path == dest then
				assert(not call.mode:find("[wa+]"), "the cache entry was opened for writing: " .. call.mode)
			end
			if call.path == tmp and call.mode:find("w") then
				wroteTmp = true
			end
		end
		assert(wroteTmp, "no temporary file was written")
		eq(Instrument.rewriteBlizzard(src, scratch, "1.60.1.70124"), out, "the cache read")
	end)
	for _, call in ipairs(opened) do
		if call.mode:find("[wa+]") then
			os.remove(call.path)
		end
	end
	for _, call in ipairs(renamed) do
		os.remove(call.to)
	end
	if dest then
		local dir = dest:match("^(.*)/[^/]+$")
		while dir and #dir >= #scratch do
			os.remove(dir)
			dir = dir:match("^(.*)/[^/]+$")
		end
	end
	assert(ok, problem)
end)

test("veil: secrets error for tainted arithmetic, compare, length; pass through untainted", function()
	local tainted
	Veil.taintedBy = function()
		return tainted
	end
	local x = Veil.wrap(10)
	local y = x + 5
	eq(Veil.is(y), true, "secure arithmetic stays secret")
	eq(Veil.unwrap(y), 15)
	eq(Veil.unwrap(x .. "!"), "10!", "concat")
	tainted = "Addon"
	local chunk = loadstring("local v = ... return v + 1", "@Blizzard_X/File.lua")
	local ok, err = pcall(chunk, x)
	eq(ok, false)
	eq(
		err,
		"Blizzard_X/File.lua:1: attempt to perform arithmetic on a secret number value (execution tainted by 'Addon')"
	)
	ok, err = pcall(function()
		return x < Veil.wrap(3)
	end)
	assert(not ok and err:find("attempt to compare a secret number value", 1, true), err)
	ok = pcall(function()
		return #Veil.wrap("abc")
	end)
	eq(ok, false, "length")
	eq(Veil.is(x .. "y"), true, "tainted concat is allowed and secret")
	tainted = nil
end)

test("veil: library functions take secrets and return them; string.format takes positional arguments", function()
	local G = { string = string, math = math }
	Veil.install(G)
	local s = G.string.format("%d items", Veil.wrap(3))
	eq(Veil.is(s), true)
	eq(Veil.unwrap(s), "3 items")
	eq(G.string.format("%2$s %1$s", "a", "b"), "b a")
	eq(G.type(Veil.wrap(1)), "number")
end)

test("taint: securecall restores the caller's state; globals carry their writer's taint", function()
	local G = {}
	Taint.globalTaint = {}
	local env = Taint.environment(G)
	Taint.install(G, env)
	Taint.current = nil
	G.securecall(function()
		Taint.set("Addon")
	end)
	eq(Taint.current, nil, "restored")
	Taint.set("Addon")
	env.SomeGlobal = 1
	Taint.set(nil)
	local secure, by = G.issecurevariable("SomeGlobal")
	eq(secure, false)
	eq(by, "Addon")
	local _ = env.SomeGlobal
	eq(Taint.current, "Addon", "reading a tainted global taints")
	Taint.set(nil)
end)

test("taint: securecall keeps a tainted caller tainted", function()
	local G = {}
	Taint.globalTaint = {}
	local env = Taint.environment(G)
	Taint.install(G, env)
	Taint.set("Addon")
	G.securecall(function()
		eq(Taint.current, "Addon", "the callee runs in the caller's taint")
		Taint.set(nil)
	end)
	eq(Taint.current, "Addon", "a tainted caller is not laundered")
	Taint.set(nil)
end)

test("taint: secureexecuterange taints a pair from an addon-written slot, not the next pair", function()
	local G = {}
	Taint.globalTaint = {}
	local env = Taint.environment(G)
	Taint.install(G, env)
	local seen = {}
	local t = {}
	Taint.set("Addon")
	t.a = true
	Taint.writeSlot(t, "a", Taint.writer())
	Taint.set(nil)
	G.secureexecuterange(t, function(key)
		seen[#seen + 1] = { key = key, taint = Taint.current }
	end)
	eq(seen[1].key, "a")
	eq(seen[1].taint, "Addon", "the addon-written slot taints its pair")
	eq(Taint.current, nil, "a secure caller is restored")
end)

test("taint: hooksecurefunc keeps the field secure and runs the hook isolated", function()
	local G = {}
	Taint.globalTaint = {}
	local env = Taint.environment(G)
	Taint.install(G, env)
	Taint.current = nil
	local t = {
		f = function()
			return 1
		end,
	}
	local seen
	G.hooksecurefunc(t, "f", function()
		seen = true
		Taint.set("Addon")
	end)
	eq(t.f(), 1)
	eq(seen, true)
	eq(Taint.current, nil, "the hook's taint does not leak")
end)

test("taint: a cause groups the field, the writer line and the origin line", function()
	local table_ = {}
	local write = {
		addon = "Addon",
		file = "Blizzard_X/File.lua",
		line = 7,
		origin = { addon = "Addon", file = "Addon/Main.lua", line = 11 },
	}
	local first = {
		kind = "field",
		addon = "Addon",
		key = "flag",
		table = table_,
		write = write,
		read = { file = "Blizzard_X/File.lua", line = 7 },
	}
	local moved = {
		addon = "Addon",
		file = "Blizzard_X/File.lua",
		line = 7,
		origin = { addon = "Addon", file = "Addon/Main.lua", line = 12 },
	}
	local second = {
		kind = "field",
		addon = "Addon",
		key = "flag",
		table = table_,
		write = write,
		read = { file = "Blizzard_X/File.lua", line = 9 },
	}
	eq(Taint.causeKey(first), Taint.causeKey(second), "the read line is not part of the cause")
	assert(
		Taint.causeKey(first)
			~= Taint.causeKey({ kind = "field", addon = "Addon", key = "flag", table = table_, write = moved }),
		"a different origin is a different cause"
	)
end)

test("sim: a report lists one entry per distinct taint cause, with a count", function()
	local Sim = require("sim")
	local table_ = {}
	local write = {
		addon = "Addon",
		file = "Blizzard_X/File.lua",
		line = 7,
		origin = { addon = "Addon", file = "Addon/Main.lua", line = 11 },
	}
	local function blocked(readLine)
		return {
			message = "blocked",
			traceback = "",
			origin = {
				kind = "field",
				addon = "Addon",
				key = "flag",
				table = table_,
				write = write,
				read = { file = "Blizzard_X/File.lua", line = readLine },
			},
		}
	end
	local text = Sim.describe({ blocked(7), blocked(9), { message = "other", traceback = "" } })
	assert(text:find("2x blocked", 1, true), text)
	local _, grouped = text:gsub("2x blocked", "")
	eq(grouped, 1, "one entry for the two blocked reads")
	assert(text:find("other", 1, true), text)
end)

test("client: a handler forwarding to the saved default records one error, at its raise site", function()
	local sim, G = freshClient()
	local previous = G.geterrorhandler()
	local seen = {}
	G.seterrorhandler(function(message)
		seen[#seen + 1] = message
		return previous(message)
	end)
	sim.reportError("Blizzard_X/File.lua:1: boom", "traceback", "SomeAddon")
	eq(#sim.errors, 1, "recorded once")
	eq(sim.errors[1].message, "Blizzard_X/File.lua:1: boom")
	eq(sim.errors[1].taint, "SomeAddon", "the raise site's taint")
	eq(#seen, 1, "the handler saw it")
	eq(seen[1], "Blizzard_X/File.lua:1: boom")
end)

test("client: the default handler records an error passed straight to it", function()
	local sim, G = freshClient()
	G.geterrorhandler()("boom")
	eq(#sim.errors, 1, "recorded once")
	eq(sim.errors[1].message, "boom")
end)

test("client: the key-binding globals the settings pages call are stubbed", function()
	local _, G = freshClient()
	eq(type(G.GetModifiedClick), "function", "GetModifiedClick")
	eq(type(G.GetBinding), "function", "GetBinding")
	local click = G.GetModifiedClick("SELFCAST")
	assert(click == nil or type(click) == "string", "GetModifiedClick returns the documented string")
	local action, category = G.GetBinding(1)
	assert(action == nil or type(action) == "string", "GetBinding returns the documented command")
	assert(category == nil or type(category) == "string", "GetBinding returns the documented category")
end)

test("natives: the quest-log leaderboard helpers answer the client's zero values", function()
	local sim, G = freshClient()
	require("natives").build(sim)
	eq(G.GetNumQuestLeaderBoards(1), 0, "no objectives")
	eq(G.GetQuestLogLeaderBoard(1, 1), nil, "no objective line")
	eq(G.GetQuestLogCompletionText(1), nil, "no completion text")
	eq(G.IsQuestSequenced(1), false, "not sequenced")
	eq(G.GetQuestLogSpecialItemInfo(1), nil, "no quest item")
	eq(type(G.ExpandQuestHeader), "function", "expand a quest header")
	eq(type(G.CollapseQuestHeader), "function", "collapse a quest header")
	-- A scenario answers through sim.impl, as it does for a documented API.
	sim.impl.GetNumQuestLeaderBoards = function()
		return 2
	end
	sim.impl.GetQuestLogLeaderBoard = function(index)
		return "Objective " .. index, nil, index == 2
	end
	sim.impl.GetQuestLogCompletionText = function()
		return "Return to the quest giver"
	end
	sim.impl.IsQuestSequenced = function()
		return true
	end
	eq(G.GetNumQuestLeaderBoards(1), 2, "the scenario's objective count")
	eq(select(1, G.GetQuestLogLeaderBoard(2, 1)), "Objective 2", "the scenario's objective text")
	eq(select(3, G.GetQuestLogLeaderBoard(2, 1)), true, "the scenario's finished flag")
	eq(G.GetQuestLogCompletionText(1), "Return to the quest giver", "the scenario's completion text")
	eq(G.IsQuestSequenced(1), true, "the scenario's sequenced flag")
	local nativeLink = G.GetQuestLink
	eq(nativeLink(608001), nil, "no quest link by default")
	sim.impl.GetQuestLink = function(id)
		return id == 608001 and "|Hquest:608001|h[Quest]|h" or nil
	end
	eq(G.GetQuestLink(608001), "|Hquest:608001|h[Quest]|h", "quest link comes from public fixture data")
	eq(G.GetQuestLink, nativeLink, "quest link engine identity stays stable")
	-- The quest map asks HaveQuestData before it draws or lists a quest; a scenario answers for the quests it holds.
	eq(G.HaveQuestData(608001), false, "no quest data by default")
	sim.impl.HaveQuestData = function(id)
		return id == 608001
	end
	eq(G.HaveQuestData(608001), true, "quest data comes from public fixture data")
	eq(G.HaveQuestData(608002), false, "a quest the fixture does not hold")
	eq(G.IsCurrentQuestFailed(), false, "no failed current quest by default")
	sim.impl.IsCurrentQuestFailed = function()
		return true
	end
	eq(G.IsCurrentQuestFailed(), true, "current quest failure comes from public fixture data")
end)

test("natives: color markup retains text and forces opaque RGB codes", function()
	local sim, G = freshClient()
	sim.G = G
	require("natives").build(sim)
	local code = sim.impl["C_ColorUtil.GenerateTextColorCode"]
	local wrap = sim.impl["C_ColorUtil.WrapTextInColorCode"]
	eq(code({ r = 1, g = 0.5, b = 0, a = 0.25 }), "ffff8000", "opaque rounded RGB")
	eq(
		sim.impl["C_ColorUtil.WrapTextInColor"]("Inspection output", { r = 1, g = 1, b = 1, a = 0 }),
		"|cffffffffInspection output|r",
		"colored text retained"
	)
	eq(
		wrap("Case %s |Ticon:8|t", "80402010"),
		"|c80402010Case %s |Ticon:8|t|r",
		"literal text and explicit alpha preserved"
	)
	eq(wrap("", "ffffffff"), "|cffffffff|r", "empty colored text")
end)

test("world: fixed recipe reagent slots include the required variable quantity list", function()
	local sim = { G = { C_Item = {}, C_AddOns = {} }, impl = {}, api = {
		zero = function()
			return {}
		end,
	} }
	require("world").build(sim)
	sim.world.professions =
		{ { skillLineID = 164, recipes = { { id = 901, name = "Fixed reagent recipe", reagents = { { 9001, 5 } } } } } }
	local slot = sim.impl["C_TradeSkillUI.GetRecipeSchematic"](901).reagentSlotSchematics[1]
	eq(type(slot.variableQuantities), "table", "required nonnil list")
	eq(#slot.variableQuantities, 0, "fixed reagent has no variable quantities")
	eq(slot.quantityRequired, 5, "fixed required quantity")
	eq(slot.reagents[1].itemID, 9001, "reagent identity")
end)

test("world: item identity resolves fixture ItemInfo without default zero", function()
	local sim = { G = { C_Item = {}, C_AddOns = {} }, impl = {} }
	require("world").build(sim)
	local link = "|cff0070dd|Hitem:9001:::::::::|h[Delayed ore]|h|r"
	sim.world.items[9001] = {
		name = "Delayed ore",
		link = link,
		quality = 3,
		count = 8,
		itemType = "Trade Goods",
		itemSubType = "Metal & Stone",
		itemEquipLoc = "",
		icon = 12345,
		classID = 7,
		subClassID = 7,
	}
	local instant = sim.impl["C_Item.GetItemInfoInstant"]
	local identity = sim.impl["C_Item.GetItemIDForItemInfo"]
	for _, info in ipairs({ 9001, "item:9001", "Delayed ore", link }) do
		eq(instant(info), 9001, "known ItemInfo identity")
		eq(identity(info), 9001, "identity API")
		eq(sim.impl["C_Item.GetItemNameByID"](info), "Delayed ore", "ItemInfo name")
		eq(sim.impl["C_Item.GetItemQualityByID"](info), 3, "ItemInfo quality")
		eq(sim.impl["C_Item.GetItemIconByID"](info), 12345, "ItemInfo icon")
		eq(sim.impl["C_Item.GetItemCount"](info), 8, "ItemInfo count")
		eq(sim.impl["C_Item.DoesItemExistByID"](info), true, "ItemInfo existence")
		eq(sim.impl["C_Item.GetItemInfo"](info), "Delayed ore", "ItemInfo cached metadata")
	end
	local id, kind, subtype, equip, icon, class, subclass = instant(9001)
	eq(id, 9001)
	eq(kind, "Trade Goods")
	eq(subtype, "Metal & Stone")
	eq(equip, "")
	eq(icon, 12345)
	eq(class, 7)
	eq(subclass, 7)
	for _, info in ipairs({ 9999, "unknown", "prefix item:9001", "spell:9001", {} }) do
		eq(instant(info), nil, "unknown or unsupported ItemInfo has no metadata")
		eq(sim.impl["C_Item.GetItemNameByID"](info), nil, "unknown name")
		eq(sim.impl["C_Item.GetItemQualityByID"](info), nil, "unknown quality")
		eq(sim.impl["C_Item.GetItemIconByID"](info), nil, "unknown icon")
		eq(sim.impl["C_Item.GetItemCount"](info), 0, "unknown count")
		eq(sim.impl["C_Item.DoesItemExistByID"](info), false, "unknown item does not exist")
	end
	eq(identity("unknown"), 0, "unresolved string has no item identity")
	eq(identity({}), 0, "unsupported type has no item identity")
	eq(identity(9999), 9999, "numeric identity does not require cached metadata")
end)

test("natives: task and scenario data changes preserve native function identities", function()
	local sim, G = freshClient()
	require("natives").build(sim)
	local tasks, info = G.GetTasksTable, G.C_Scenario.GetInfo
	eq(#tasks(), 0, "no tasks by default")
	eq(select(3, info()), 0, "no scenario stages by default")
	sim.impl.GetTasksTable = function()
		return { 608001 }
	end
	sim.impl.GetTaskInfo = function(id)
		return true, false, 2, "Task " .. id, false
	end
	sim.impl.GetQuestObjectiveInfo = function(id, index)
		return id .. ":" .. index, "monster", false
	end
	sim.impl.GetQuestProgressBarPercent = function(id)
		return id == 608001 and 50 or 0
	end
	sim.impl["C_Scenario.GetInfo"] = function()
		return "Scenario", 1, 2, nil, false
	end
	eq(G.GetTasksTable, tasks, "task native identity")
	eq(G.C_Scenario.GetInfo, info, "scenario native identity")
	eq(tasks()[1], 608001, "task IDs from public fixture input")
	eq(select(3, G.GetTaskInfo(608001)), 2, "task objective count")
	eq(select(4, G.GetTaskInfo(608001)), "Task 608001", "task title")
	eq(G.GetQuestObjectiveInfo(608001, 2), "608001:2", "objective arguments")
	eq(G.GetQuestProgressBarPercent(608001), 50, "progress percentage")
	eq(info(), "Scenario", "scenario title")
	eq(select(5, info()), false, "scenario trailing value after nil")
end)

test("natives: achievement category arrays remain stable fixture entry points", function()
	local sim, G = freshClient()
	require("natives").build(sim)
	for _, name in ipairs({ "GetGuildCategoryList", "GetStatisticsCategoryList" }) do
		local native = G[name]
		eq(type(native), "function", name .. " is an engine native")
		eq(#native(), 0, name .. " default is empty")
		local first = native()
		first[1] = 999
		eq(#native(), 0, name .. " returns an independent default array")
		sim.impl[name] = function()
			return { 608 }
		end
		eq(native()[1], 608, name .. " fixture categories")
		eq(G[name], native, name .. " native identity")
	end
end)

test("natives: legacy achievement search and chain preserve fixture contracts", function()
	local sim, G = freshClient()
	require("natives").build(sim)
	eq(type(G.SetAchievementSearchString), "function", "search native")
	eq(type(G.GetPreviousAchievement), "function", "chain native")
	eq(G.GetPreviousAchievement(401), nil, "no previous achievement by default")
	eq(G.GetNumFilteredAchievements(), 0, "no search results by default")
	eq(G.GetFilteredAchievementID(1), nil, "no result identity by default")
	sim.impl.GetNumFilteredAchievements = function()
		return 1
	end
	sim.impl.GetFilteredAchievementID = function(index)
		return index == 1 and 401 or nil
	end
	eq(G.GetNumFilteredAchievements(), 1, "explicit search count")
	eq(G.GetFilteredAchievementID(1), 401, "explicit search result identity")
	local search
	sim.impl.SetAchievementSearchString = function(text)
		search = text
	end
	eq(select("#", G.SetAchievementSearchString("Exact search")), 0, "search has no invented return")
	eq(search, "Exact search", "search passed to fixture")
	sim.impl.GetPreviousAchievement = function(id)
		return id == 402 and 401 or nil
	end
	eq(G.GetPreviousAchievement(402), 401, "explicit previous achievement")
	eq(G.GetPreviousAchievement(401), nil, "chain terminates")
	eq(G.GetNextAchievement(402), nil, "no next achievement by default")
	sim.impl.GetNextAchievement = function(id)
		return id == 401 and 402 or nil, false
	end
	local nextID, completed = G.GetNextAchievement(401)
	eq(nextID, 402, "next achievement identity")
	eq(completed, false, "next achievement completion")
end)

test("stubgen: native color results include numeric channels before mixing methods", function()
	local sim, G = freshClient()
	require("natives").build(sim)
	sim.docs = { enums = {}, constants = {}, systems = {}, events = {}, widgets = {}, structures = {} }
	sim.dataDir = here .. "../../forever_sim/no-data"
	G.ColorMixin = {
		GetRGBA = function(self)
			return self.r, self.g, self.b, self.a
		end,
	}
	require("stubgen").build(sim)
	local rgb = sim.api.zero({ Type = "colorRGB", Mixin = "ColorMixin" })
	local r, g, b, a = rgb:GetRGBA()
	eq(r, 0)
	eq(g, 0)
	eq(b, 0)
	eq(a, nil, "RGB has no invented alpha")
	local rgba = sim.api.zero({ Type = "colorRGBA", Mixin = "ColorMixin" })
	r, g, b, a = rgba:GetRGBA()
	eq(r, 0)
	eq(g, 0)
	eq(b, 0)
	eq(a, 0, "RGBA zero alpha")
	eq(sim.api.zero({ Type = "colorRGBA", Mixin = "ColorMixin", Nilable = true }), nil, "nilable color remains absent")
	rgb.r = 1
	eq(sim.api.zero({ Type = "colorRGB" }).r, 0, "results do not share channel tables")
end)

test("stubgen: QuestConsts aliases the documented QuestInfoLuaConsts", function()
	local sim, G = freshClient()
	sim.docs = {
		enums = {},
		constants = {
			QuestInfoLuaConsts = {
				Values = {
					{ Name = "QUEST_INFO_ELITE_ID", Value = 1 },
					{ Name = "QUEST_INFO_DUNGEON_ID", Value = 81 },
					{ Name = "QUEST_INFO_PVP_ID", Value = 41 },
					{ Name = "QUEST_INFO_RAID_ID", Value = 62 },
				},
			},
		},
		systems = {},
		events = {},
		widgets = {},
		structures = {},
	}
	sim.dataDir = here .. "../../forever_sim/no-data"
	require("stubgen").build(sim)
	eq(G.Constants.QuestConsts.QUEST_INFO_DUNGEON_ID, 81, "the dungeon tag id")
	eq(G.Constants.QuestConsts, G.Constants.QuestInfoLuaConsts, "the alias")
end)

test("docs: a restriction keeps every class its tag names, and any one refuses the call", function()
	local Docs = require("docs")
	local path = os.tmpname()
	local file = assert(io.open(path, "w"))
	file:write("X.Both nocombat,hwevent\nX.Always always,hwevent\n")
	file:close()
	local classes = Docs.restrictions(path)
	os.remove(path)
	eq(table.concat(classes["X.Both"], ","), "nocombat,hwevent", "both classes survive")
	eq(table.concat(classes["X.Always"], ","), "always,hwevent", "the tag order does not drop one")
	eq(Docs.applies(classes["X.Both"], false, false), true, "hwevent refuses without a hardware input")
	eq(Docs.applies(classes["X.Both"], false, true), false, "neither class applies out of combat with input")
	eq(Docs.applies(classes["X.Both"], true, true), true, "nocombat refuses in combat")
	eq(Docs.applies(classes["X.Always"], false, true), true, "always refuses regardless")
	eq(Docs.applies({ "untagged" }, false, true), false, "untagged keeps the combat-only rule")
end)

test("widgets: a quest POI frame records the quest areas it draws", function()
	Taint.current = nil
	local W = require("widgets").build({ G = {}, env = {}, taint = Taint, docs = { enums = {}, widgets = {} } })
	W.finalize()
	local frame = W.new("QuestPOIFrame")
	frame:DrawBlob(608001, true)
	frame:DrawBlob(608002, true)
	assert(W.state[frame].blobQuestIDs[608001], "first drawn quest recorded")
	assert(W.state[frame].blobQuestIDs[608002], "second drawn quest recorded")
	frame:DrawNone()
	assert(next(W.state[frame].blobQuestIDs) == nil, "DrawNone clears every drawn quest area")
end)

test("widgets: dependency cycles are rejected beyond recursive depth limits", function()
	Taint.current = nil
	local W = require("widgets").build({ G = {}, env = {}, taint = Taint, docs = { enums = {}, widgets = {} } })
	W.finalize()
	local root = W.new("Frame")
	W.setRoot(root)
	root:SetSize(800, 600)
	local base = W.new("Frame", nil, root)
	base:SetSize(10, 10)
	base:SetPoint("TOPLEFT", root, "TOPLEFT")
	local last = base
	for _ = 1, 120 do
		local frame = W.new("Frame", nil, root)
		frame:SetSize(10, 10)
		frame:SetPoint("TOPLEFT", last, "BOTTOMLEFT")
		last = frame
	end
	local ok, err = pcall(base.SetPoint, base, "TOPLEFT", last, "BOTTOMLEFT")
	assert(not ok and tostring(err):find("dependent on it", 1, true), "deep dependency cycle must be rejected")
end)

test("widgets: secret anchoring follows deep chains and shared dependencies", function()
	Taint.current = nil
	local W = require("widgets").build({ G = {}, env = {}, taint = Taint, docs = { enums = {}, widgets = {} } })
	W.finalize()
	local root = W.new("Frame")
	W.setRoot(root)
	root:SetSize(800, 600)
	local secret = W.new("Frame", nil, root)
	secret:SetWidth(Veil.wrap(10))
	secret:SetHeight(10)
	secret:SetPoint("TOPLEFT", root, "TOPLEFT")
	local last = secret
	for _ = 1, 60 do
		local frame = W.new("Frame", nil, root)
		frame:SetSize(10, 10)
		frame:SetPoint("TOPLEFT", last, "BOTTOMLEFT")
		last = frame
	end
	assert(last:IsAnchoringSecret(), "deep secret dependency remains secret")
	local public = W.new("Frame", nil, root)
	public:SetSize(10, 10)
	public:SetPoint("TOPLEFT", root, "TOPLEFT")
	last = public
	for _ = 1, 28 do
		local frame = W.new("Frame", nil, root)
		frame:SetPoint("TOPLEFT", last, "TOPLEFT")
		frame:SetPoint("BOTTOMRIGHT", last, "BOTTOMRIGHT")
		last = frame
	end
	assert(not last:IsAnchoringSecret(), "shared-edge DAG remains public")
end)

print(string.format("unit_spec: %d passed, %d failed", passed, failed))
os.exit(failed == 0 and 0 or 1)
