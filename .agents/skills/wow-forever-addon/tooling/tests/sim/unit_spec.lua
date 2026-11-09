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
		alwaysRestrictedMethods = { SetPassThroughButtons = "cjber/adventure-guide-forever#534" },
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

print(string.format("unit_spec: %d passed, %d failed", passed, failed))
os.exit(failed == 0 and 0 or 1)
