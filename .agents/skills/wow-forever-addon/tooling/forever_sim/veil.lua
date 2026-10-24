-- Secret values: the client's restricted APIs hand tainted code numbers and strings it may store and pass on,
-- but not inspect. A secret is a userdata proxy around the real value. Untainted (Blizzard) code may do anything
-- with it and gets a secret back; tainted code that does arithmetic, compares, measures, indexes or calls one gets
-- the client's error, naming the addon that tainted the execution.
local M = {}

local values = setmetatable({}, { __mode = "k" }) -- proxy -> real value
local kinds = setmetatable({}, { __mode = "k" }) -- proxy -> "number" | "string" | "boolean" | ...
local meta, base

-- Set by taint.lua: returns the addon tainting the running code, or nil when it is secure.
M.taintedBy = function()
	return nil
end

local function wrap(value)
	if value == nil or values[value] ~= nil then
		return value
	end
	if not base then
		base = newproxy(true)
		local mt = getmetatable(base)
		for k, v in pairs(meta) do
			mt[k] = v
		end
	end
	-- Every secret shares one metatable, so == between two secrets reaches __eq.
	local proxy = newproxy(base)
	values[proxy] = value
	kinds[proxy] = type(value)
	return proxy
end
M.wrap = wrap

function M.is(value)
	return type(value) == "userdata" and kinds[value] ~= nil
end

function M.unwrap(value)
	if type(value) == "userdata" and kinds[value] ~= nil then
		return values[value]
	end
	return value
end

function M.kind(value)
	return kinds[value]
end

local function fail(what, value, level)
	local addon = M.taintedBy()
	error(
		string.format("attempt to %s a secret %s value (execution tainted by '%s')", what, kinds[value], addon),
		level or 3
	)
end
M.fail = fail

local function secretOf(a, b)
	if M.is(a) then
		return a
	end
	return b
end

local function arith(op)
	return function(a, b)
		if M.taintedBy() then
			fail("perform arithmetic on", secretOf(a, b))
		end
		return wrap(op(M.unwrap(a), M.unwrap(b)))
	end
end

local function compare(op)
	return function(a, b)
		if M.taintedBy() then
			fail("compare", secretOf(a, b))
		end
		return op(M.unwrap(a), M.unwrap(b))
	end
end

meta = {
	__add = arith(function(a, b)
		return a + b
	end),
	__sub = arith(function(a, b)
		return a - b
	end),
	__mul = arith(function(a, b)
		return a * b
	end),
	__div = arith(function(a, b)
		return a / b
	end),
	__mod = arith(function(a, b)
		return a % b
	end),
	__pow = arith(function(a, b)
		return a ^ b
	end),
	__unm = function(a)
		if M.taintedBy() then
			fail("perform arithmetic on", a)
		end
		return wrap(-M.unwrap(a))
	end,
	-- Concatenation is allowed from tainted code; the result is secret.
	__concat = function(a, b)
		return wrap(tostring(M.unwrap(a)) .. tostring(M.unwrap(b)))
	end,
	__lt = compare(function(a, b)
		return a < b
	end),
	__le = compare(function(a, b)
		return a <= b
	end),
	__eq = compare(function(a, b)
		return a == b
	end),
	__len = function(a)
		if M.taintedBy() then
			fail("get length of", a)
		end
		return wrap(#M.unwrap(a))
	end,
	__index = function(a, k)
		if M.taintedBy() then
			fail("index", a)
		end
		local real = M.unwrap(a)
		if type(real) == "string" then
			local f = string[k]
			if type(f) == "function" then
				return function(self, ...)
					return wrap(f(M.unwrap(self), ...))
				end
			end
		end
		return nil
	end,
	__call = function(a)
		fail("call", a)
	end,
	__tostring = function()
		return "<secret>"
	end,
	__metatable = false,
}

-- Library functions take secrets and give secrets back, as the client's C functions do.
local function lift(f)
	return function(...)
		local n = select("#", ...)
		local args = { ... }
		local any = false
		for i = 1, n do
			if M.is(args[i]) then
				any = true
				args[i] = M.unwrap(args[i])
			end
		end
		if not any then
			return f(...)
		end
		local out = { f(unpack(args, 1, n)) }
		for i = 1, table.maxn(out) do
			out[i] = wrap(out[i])
		end
		return unpack(out, 1, table.maxn(out))
	end
end
M.lift = lift

-- Installs the secret-aware builtins and the client's secret API into the globals table G.
function M.install(G)
	local rawType = type
	G.type = function(v)
		if M.is(v) then
			return kinds[v]
		end
		return rawType(v)
	end
	G.tostring = function(v)
		if M.is(v) then
			return wrap(tostring(values[v]))
		end
		return tostring(v)
	end
	G.tonumber = lift(tonumber)
	-- The client's string.format takes positional arguments ("%2$s %1$s"), which Lua 5.1's does not.
	local rawFormat = string.format
	local function format(fmt, ...)
		if type(fmt) == "string" and fmt:find("%%%d+%$") then
			local args = { ... }
			local ordered = {}
			local nextIndex = 0
			fmt = fmt:gsub("%%(%%?)(%d*)(%$?)([%-%+ #0]*%d*%.?%d*[cdiouxXeEfgGqs])", function(pct, num, dollar, spec)
				if pct == "%" then
					return "%%" .. num .. dollar .. spec
				end
				local index
				if dollar == "$" then
					index = tonumber(num)
				else
					nextIndex = nextIndex + 1
					index = nextIndex
					spec = num .. spec
				end
				ordered[#ordered + 1] = args[index]
				return "%" .. spec
			end)
			return rawFormat(fmt, unpack(ordered, 1, table.maxn(ordered)))
		end
		return rawFormat(fmt, ...)
	end
	G.__format = format
	for _, lib in ipairs({ "string", "math" }) do
		local copy = {}
		for k, f in pairs(G[lib]) do
			copy[k] = rawType(f) == "function" and lift(f) or f
		end
		G[lib] = copy
	end
	G.string.format = lift(G.__format)
	G.__format = nil
	G.issecretvalue = function(v)
		return M.is(v)
	end
	G.canaccessvalue = function(v)
		return not M.is(v) or not M.taintedBy()
	end
	G.canaccesssecrets = function()
		return not M.taintedBy()
	end
	G.issecrettable = function(t)
		if rawType(t) ~= "table" then
			return false
		end
		for k, v in next, t do
			if M.is(k) or M.is(v) then
				return true
			end
		end
		return false
	end
	G.canaccesstable = function(t)
		return not G.issecrettable(t) or not M.taintedBy()
	end
	G.secretwrap = function(...)
		local out = { ... }
		for i = 1, select("#", ...) do
			out[i] = wrap(out[i])
		end
		return unpack(out, 1, select("#", ...))
	end
	G.scrubsecretvalues = function(...)
		local out = { ... }
		for i = 1, select("#", ...) do
			if M.is(out[i]) then
				out[i] = nil
			end
		end
		return unpack(out, 1, select("#", ...))
	end
	G.scrub = G.scrubsecretvalues
end

return M
