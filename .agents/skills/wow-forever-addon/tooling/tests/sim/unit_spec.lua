-- forever_sim's offline unit specs (no UI source needed): luajit tests/sim/unit_spec.lua, from tooling/.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
package.path = here .. "../../forever_sim/?.lua;" .. package.path

local XML = require("xml")
local Instrument = require("instrument")
local Veil = require("veil")
local Taint = require("taint")

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

print(string.format("unit_spec: %d passed, %d failed", passed, failed))
os.exit(failed == 0 and 0 or 1)
