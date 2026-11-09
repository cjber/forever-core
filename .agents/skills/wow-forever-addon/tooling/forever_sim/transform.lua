-- A Lua 5.1 tokenizer, parser and source rewriter for field taint.
--
-- Every table field read (`t.k`, `t[k]`, a method call, and the walks `next`/`pairs` reach) becomes
-- `__fsi_get(t, k)`, and every field write (`t.k = v`, `t[k] = v`, `rawset`, a named method definition)
-- becomes `__fsi_set(t, k, v)`. The helpers in taint.lua record the writer's execution taint per (table,
-- key) slot and taint a secure reader of a tainted slot, which is the client's rule.
--
-- The parser is a real Lua 5.1 parser: it never looks at source with a pattern. The printer keeps every
-- original token on its original line (comments are dropped, their lines become blank), so error messages
-- and traces name the line the client would. Addon functions also get the `__fst` marker the taint tracker
-- uses to know which addon is running.
local M = {}

local KEYWORDS = {}
for word in
	("and break do else elseif end false for function if in local nil not or repeat return then true until while"):gmatch(
		"%a+"
	)
do
	KEYWORDS[word] = true
end

local function newlines(text)
	local _, n = text:gsub("\n", "\n")
	return n
end

local function syntax(src, line, message)
	error(string.format("%s:%d: %s", src, line, message), 0)
end

---------------------------------------------------------------------------
-- Tokenizer
---------------------------------------------------------------------------
local function longBracketLevel(src, i)
	local eq = src:match("^%[(=*)%[", i)
	return eq and #eq
end

local function tokenize(text, name)
	local tokens = {}
	local i, n, line = 1, #text, 1
	local function push(kind, value, at)
		tokens[#tokens + 1] = { kind = kind, text = value, line = at }
	end
	while i <= n do
		local c = text:sub(i, i)
		if c == "\n" then
			line = line + 1
			i = i + 1
		elseif c == " " or c == "\t" or c == "\r" or c == "\v" or c == "\f" then
			i = i + 1
		elseif c == "-" and text:sub(i + 1, i + 1) == "-" then
			local level = longBracketLevel(text, i + 2)
			if level then
				local close = "]" .. string.rep("=", level) .. "]"
				local _, e = text:find(close, i + 2 + level + 2, true)
				if not e then
					syntax(name, line, "unfinished long comment")
				end
				line = line + newlines(text:sub(i, e))
				i = e + 1
			else
				local nl = text:find("\n", i + 2, true)
				i = nl or (n + 1)
			end
		elseif c == '"' or c == "'" then
			local j, at = i + 1, line
			while j <= n do
				local d = text:sub(j, j)
				if d == "\\" then
					if text:sub(j + 1, j + 1) == "\n" then
						line = line + 1
					end
					j = j + 2
				elseif d == c then
					j = j + 1
					break
				elseif d == "\n" then
					syntax(name, line, "unfinished string")
				else
					j = j + 1
				end
			end
			local value = text:sub(i, j - 1)
			push("string", value, at)
			line = line + newlines(value)
			i = j
		elseif c == "[" and (text:sub(i + 1, i + 1) == "[" or text:sub(i + 1, i + 1) == "=") then
			local level = longBracketLevel(text, i)
			if level then
				local close = "]" .. string.rep("=", level) .. "]"
				local _, e = text:find(close, i + level + 2, true)
				if not e then
					syntax(name, line, "unfinished long string")
				end
				local value = text:sub(i, e)
				push("string", value, line)
				line = line + newlines(value)
				i = e + 1
			else
				i = i + 1
			end
		elseif c:match("[%a_]") then
			local word = text:match("^[%a_][%w_]*", i)
			push(KEYWORDS[word] and "keyword" or "name", word, line)
			i = i + #word
		elseif c:match("%d") or (c == "." and text:sub(i + 1, i + 1):match("%d")) then
			local value
			if text:sub(i, i + 1):lower() == "0x" then
				value = text:match("^0[xX]%x+", i)
			else
				value = text:match("^%d+%.?%d*[eE][%+%-]?%d+", i)
					or text:match("^%d+%.?%d*", i)
					or text:match("^%.%d+", i)
			end
			if not value then
				syntax(name, line, "malformed number")
			end
			push("number", value, line)
			i = i + #value
		else
			local three = text:sub(i, i + 2)
			if three == "..." then
				push("symbol", three, line)
				i = i + 3
			else
				local two = text:sub(i, i + 1)
				if two == ".." or two == "==" or two == "~=" or two == "<=" or two == ">=" then
					push("symbol", two, line)
					i = i + 2
				elseif c:match("[%+%-%*/%%%^#<>=%(%){}%[%];:,%.]") then
					push("symbol", c, line)
					i = i + 1
				else
					syntax(name, line, "unexpected character " .. string.format("%q", c))
				end
			end
		end
	end
	push("eof", "<eof>", line)
	return tokens
end

M.tokenize = tokenize

---------------------------------------------------------------------------
-- Parser
---------------------------------------------------------------------------
local Parser = {}
Parser.__index = Parser

local BINARY = {
	["or"] = { 1, 1 },
	["and"] = { 2, 2 },
	["<"] = { 3, 3 },
	[">"] = { 3, 3 },
	["<="] = { 3, 3 },
	[">="] = { 3, 3 },
	["~="] = { 3, 3 },
	["=="] = { 3, 3 },
	[".."] = { 5, 4 },
	["+"] = { 6, 6 },
	["-"] = { 6, 6 },
	["*"] = { 7, 7 },
	["/"] = { 7, 7 },
	["%"] = { 7, 7 },
	["^"] = { 10, 9 },
}
local UNARY = 8

function Parser:peek(offset)
	return self.tokens[self.index + (offset or 0)]
end

function Parser:next()
	local token = self.tokens[self.index]
	self.index = self.index + 1
	return token
end

function Parser:check(text)
	return self:peek().text == text
end

function Parser:accept(text)
	if self:check(text) then
		return self:next()
	end
end

function Parser:expect(text)
	local token = self:next()
	if token.text ~= text then
		syntax(self.name, token.line, string.format("expected %q near %q", text, token.text))
	end
	return token
end

local function node(tag, ref, fields)
	fields = fields or {}
	fields.tag, fields.line = tag, ref.line or ref.token.line
	return fields
end

function Parser:expression(limit)
	local token = self:peek()
	local left
	if token.text == "not" or token.text == "-" or token.text == "#" then
		self:next()
		left = node("UnOp", token, { op = token.text, opTok = token, operand = self:expression(UNARY) })
	else
		left = self:simple()
	end
	while true do
		local op = self:peek()
		local prec = BINARY[op.text]
		if not prec or prec[1] <= limit then
			break
		end
		self:next()
		local right = self:expression(prec[2])
		left = node("BinOp", op, { op = op.text, opTok = op, left = left, right = right })
	end
	return left
end

function Parser:simple()
	local token = self:peek()
	if
		token.kind == "number"
		or token.kind == "string"
		or token.text == "nil"
		or token.text == "true"
		or token.text == "false"
	then
		self:next()
		return node("Literal", token, { token = token })
	elseif token.text == "..." then
		self:next()
		return node("Vararg", token)
	elseif token.text == "{" then
		return self:table()
	elseif token.text == "function" then
		self:next()
		return node("Function", token, self:funcBody(token))
	elseif token.text == "(" then
		self:next()
		local inner = self:expression(0)
		local close = self:expect(")")
		return self:suffixes(node("Paren", token, { expr = inner, openTok = token, closeTok = close }))
	elseif token.kind == "name" then
		self:next()
		return self:suffixes(node("Name", token, { token = token }))
	else
		syntax(self.name, token.line, "expected an expression near " .. string.format("%q", token.text))
	end
end

function Parser:suffixes(base)
	while true do
		local token = self:peek()
		if token.text == "." then
			self:next()
			local key = self:next()
			if key.kind ~= "name" then
				syntax(self.name, key.line, "expected a field name")
			end
			base = node("Index", base, { obj = base, key = node("Name", key, { token = key }), keyTok = key })
		elseif token.text == "[" then
			self:next()
			local key = self:expression(0)
			self:expect("]")
			base = node("Index", base, { obj = base, key = key })
		elseif token.text == ":" then
			self:next()
			local method = self:next()
			if method.kind ~= "name" then
				syntax(self.name, method.line, "expected a method name")
			end
			local args = self:args()
			base = node("Call", base, { callee = base, method = method, args = args })
		elseif token.text == "(" or token.text == "{" or token.kind == "string" then
			local args = self:args()
			base = node("Call", base, { callee = base, args = args })
		else
			return base
		end
	end
end

function Parser:args()
	local token = self:peek()
	if token.text == "(" then
		self:next()
		local args = {}
		if not self:check(")") then
			args = self:expressionList()
		end
		self:expect(")")
		return args
	elseif token.text == "{" then
		return { self:table() }
	elseif token.kind == "string" then
		self:next()
		return { node("Literal", token, { token = token }) }
	end
	syntax(self.name, token.line, "expected arguments")
end

function Parser:expressionList()
	local list = { self:expression(0) }
	while self:check(",") do
		self:next()
		list[#list + 1] = self:expression(0)
	end
	return list
end

function Parser:table()
	local open = self:expect("{")
	local fields = {}
	while not self:check("}") do
		local token = self:peek()
		if token.text == "[" then
			self:next()
			local key = self:expression(0)
			self:expect("]")
			self:expect("=")
			fields[#fields + 1] = { kind = "keyed", key = key, value = self:expression(0) }
		elseif token.kind == "name" and self:peek(1).text == "=" then
			self:next()
			self:next()
			fields[#fields + 1] = { kind = "named", keyTok = token, value = self:expression(0) }
		else
			fields[#fields + 1] = { kind = "array", value = self:expression(0) }
		end
		if not (self:accept(",") or self:accept(";")) then
			break
		end
	end
	local close = self:expect("}")
	return node("Table", open, { openTok = open, closeTok = close, fields = fields })
end

function Parser:funcBody(funcTok)
	local open = self:expect("(")
	local params, varargTok = {}, nil
	if not self:check(")") then
		while true do
			local token = self:next()
			if token.text == "..." then
				varargTok = token
				break
			end
			if token.kind ~= "name" then
				syntax(self.name, token.line, "expected a parameter name")
			end
			params[#params + 1] = token
			if not self:accept(",") then
				break
			end
		end
	end
	local close = self:expect(")")
	local body = self:block()
	local endTok = self:expect("end")
	return {
		funcTok = funcTok,
		openTok = open,
		closeTok = close,
		endTok = endTok,
		params = params,
		varargTok = varargTok,
		body = body,
	}
end

local BLOCK_END = { ["end"] = true, ["else"] = true, ["elseif"] = true, ["until"] = true, ["<eof>"] = true }

function Parser:block()
	local statements = {}
	while not BLOCK_END[self:peek().text] do
		if not self:accept(";") then
			statements[#statements + 1] = self:statement()
			self:accept(";")
		end
	end
	return statements
end

function Parser:statement()
	local token = self:peek()
	if token.text == "if" then
		return self:ifStatement()
	elseif token.text == "while" then
		self:next()
		local cond = self:expression(0)
		self:expect("do")
		local body = self:block()
		local endTok = self:expect("end")
		return node("While", token, { cond = cond, body = body, endTok = endTok })
	elseif token.text == "do" then
		self:next()
		local body = self:block()
		local endTok = self:expect("end")
		return node("Do", token, { body = body, endTok = endTok })
	elseif token.text == "repeat" then
		self:next()
		local body = self:block()
		self:expect("until")
		local cond = self:expression(0)
		return node("Repeat", token, { body = body, cond = cond })
	elseif token.text == "for" then
		return self:forStatement()
	elseif token.text == "function" then
		self:next()
		return self:functionStatement(token)
	elseif token.text == "local" then
		return self:localStatement()
	elseif token.text == "return" then
		self:next()
		local exprs = {}
		local nextToken = self:peek().text
		if not BLOCK_END[nextToken] and nextToken ~= ";" then
			exprs = self:expressionList()
		end
		return node("Return", token, { exprs = exprs })
	elseif token.text == "break" then
		self:next()
		return node("Break", token)
	end
	-- An expression statement: a call, or an assignment to names and fields.
	local first = self:suffixes(self:prefix())
	if self:check("=") or self:check(",") then
		local targets = { first }
		while self:accept(",") do
			targets[#targets + 1] = self:suffixes(self:prefix())
		end
		self:expect("=")
		local exprs = self:expressionList()
		return node("Assign", token, { targets = targets, exprs = exprs })
	end
	return node("CallStat", token, { call = first })
end

function Parser:prefix()
	local token = self:peek()
	if token.kind == "name" then
		self:next()
		return node("Name", token, { token = token })
	elseif token.text == "(" then
		self:next()
		local inner = self:expression(0)
		local close = self:expect(")")
		return node("Paren", token, { expr = inner, openTok = token, closeTok = close })
	end
	syntax(self.name, token.line, "expected a variable near " .. string.format("%q", token.text))
end

function Parser:ifStatement()
	local token = self:expect("if")
	local clauses = {}
	local cond = self:expression(0)
	self:expect("then")
	clauses[1] = { cond = cond, body = self:block() }
	while self:check("elseif") do
		self:next()
		local clauseCond = self:expression(0)
		self:expect("then")
		clauses[#clauses + 1] = { cond = clauseCond, body = self:block() }
	end
	local elseBody
	if self:accept("else") then
		elseBody = self:block()
	end
	local endTok = self:expect("end")
	return node("If", token, { clauses = clauses, elseBody = elseBody, endTok = endTok })
end

function Parser:forStatement()
	local token = self:expect("for")
	local first = self:next()
	if first.kind ~= "name" then
		syntax(self.name, first.line, "expected a loop variable")
	end
	if self:accept("=") then
		local start = self:expression(0)
		self:expect(",")
		local limit = self:expression(0)
		local step
		if self:accept(",") then
			step = self:expression(0)
		end
		self:expect("do")
		local body = self:block()
		local endTok = self:expect("end")
		return node("ForNum", token, {
			name = first,
			start = start,
			limit = limit,
			step = step,
			body = body,
			endTok = endTok,
		})
	end
	local names = { first }
	while self:accept(",") do
		local name = self:next()
		if name.kind ~= "name" then
			syntax(self.name, name.line, "expected a loop variable")
		end
		names[#names + 1] = name
	end
	self:expect("in")
	local exprs = self:expressionList()
	self:expect("do")
	local body = self:block()
	local endTok = self:expect("end")
	return node("ForIn", token, { names = names, exprs = exprs, body = body, endTok = endTok })
end

function Parser:functionStatement(funcTok)
	local first = self:next()
	if first.kind ~= "name" then
		syntax(self.name, first.line, "expected a function name")
	end
	local target = node("Name", first, { token = first })
	local method
	while self:check(".") do
		self:next()
		local key = self:next()
		if key.kind ~= "name" then
			syntax(self.name, key.line, "expected a field name")
		end
		target = node("Index", first, { obj = target, key = node("Name", key, { token = key }), keyTok = key })
	end
	if self:accept(":") then
		method = self:next()
		if method.kind ~= "name" then
			syntax(self.name, method.line, "expected a method name")
		end
	end
	local func = self:funcBody(funcTok)
	func.method = method ~= nil
	if method then
		target = node("Index", first, {
			obj = target,
			key = node("Name", method, { token = method }),
			keyTok = method,
		})
	end
	return node("FuncStat", funcTok, { target = target, func = func })
end

function Parser:localStatement()
	local token = self:expect("local")
	if self:accept("function") then
		local name = self:next()
		if name.kind ~= "name" then
			syntax(self.name, name.line, "expected a function name")
		end
		local func = self:funcBody(token)
		return node("LocalFunction", token, { name = name, func = func })
	end
	local names = {}
	while true do
		local name = self:next()
		if name.kind ~= "name" then
			syntax(self.name, name.line, "expected a local name")
		end
		names[#names + 1] = name
		if not self:accept(",") then
			break
		end
	end
	local exprs
	if self:accept("=") then
		exprs = self:expressionList()
	end
	return node("Local", token, { names = names, exprs = exprs })
end

function Parser:parse()
	local body = self:block()
	local eof = self:peek()
	if eof.text ~= "<eof>" then
		syntax(self.name, eof.line, "unexpected " .. string.format("%q", eof.text))
	end
	return body
end

local function parse(tokens, name)
	return setmetatable({ tokens = tokens, index = 1, name = name }, Parser):parse()
end

M.parse = function(text, name)
	return parse(tokenize(text, name or "=(chunk)"), name or "=(chunk)")
end

---------------------------------------------------------------------------
-- Printer
---------------------------------------------------------------------------
local Emitter = {}
Emitter.__index = Emitter

function Emitter:emit(text)
	if #self.out > 0 then
		self.out[#self.out + 1] = " "
	end
	self.out[#self.out + 1] = text
	self.line = self.line + newlines(text)
end

function Emitter:at(line)
	if line and line > self.line then
		self.out[#self.out + 1] = string.rep("\n", line - self.line)
		self.line = line
	end
end

function Emitter:token(token)
	self:at(token.line)
	self:emit(token.text)
end

function Emitter:raw(text)
	self:emit(text)
end

local function quoted(text)
	return string.format("%q", text)
end

function Emitter:name(node_)
	self:token(node_.token)
end

function Emitter:block(statements)
	for i, statement in ipairs(statements) do
		if i > 1 then
			self:raw(";")
		end
		self:statement(statement)
	end
end

function Emitter:statement(statement)
	self:at(statement.line)
	local tag = statement.tag
	if tag == "Local" then
		self:raw("local")
		for i, name in ipairs(statement.names) do
			if i > 1 then
				self:raw(",")
			end
			self:token(name)
		end
		if statement.exprs then
			self:raw("=")
			self:expressionList(statement.exprs)
		end
	elseif tag == "LocalFunction" then
		self:raw("local")
		self:raw("function")
		self:token(statement.name)
		self:functionBody(statement.func, false)
	elseif tag == "Assign" then
		self:assign(statement)
	elseif tag == "FuncStat" then
		self:functionStatement(statement)
	elseif tag == "CallStat" then
		self:expression(statement.call)
	elseif tag == "Do" then
		self:raw("do")
		self:block(statement.body)
		self:token(statement.endTok)
	elseif tag == "While" then
		self:raw("while")
		self:expression(statement.cond)
		self:raw("do")
		self:block(statement.body)
		self:token(statement.endTok)
	elseif tag == "Repeat" then
		self:raw("repeat")
		self:block(statement.body)
		self:raw("until")
		self:expression(statement.cond)
	elseif tag == "If" then
		self:raw("if")
		local first = statement.clauses[1]
		self:expression(first.cond)
		self:raw("then")
		self:block(first.body)
		for i = 2, #statement.clauses do
			local clause = statement.clauses[i]
			self:raw("elseif")
			self:expression(clause.cond)
			self:raw("then")
			self:block(clause.body)
		end
		if statement.elseBody then
			self:raw("else")
			self:block(statement.elseBody)
		end
		self:token(statement.endTok)
	elseif tag == "ForNum" then
		self:raw("for")
		self:token(statement.name)
		self:raw("=")
		self:expression(statement.start)
		self:raw(",")
		self:expression(statement.limit)
		if statement.step then
			self:raw(",")
			self:expression(statement.step)
		end
		self:raw("do")
		self:block(statement.body)
		self:token(statement.endTok)
	elseif tag == "ForIn" then
		self:raw("for")
		for i, name in ipairs(statement.names) do
			if i > 1 then
				self:raw(",")
			end
			self:token(name)
		end
		self:raw("in")
		self:expressionList(statement.exprs)
		self:raw("do")
		self:block(statement.body)
		self:token(statement.endTok)
	elseif tag == "Return" then
		self:raw("return")
		self:expressionList(statement.exprs)
	elseif tag == "Break" then
		self:raw("break")
	else
		error("transform: unknown statement " .. tostring(tag), 0)
	end
end

function Emitter:expressionList(exprs)
	for i, expr in ipairs(exprs) do
		if i > 1 then
			self:raw(",")
		end
		self:expression(expr)
	end
end

function Emitter:expression(expr)
	local tag = expr.tag
	if tag == "Literal" then
		self:token(expr.token)
	elseif tag == "Name" then
		self:token(expr.token)
	elseif tag == "Vararg" then
		self:raw("...")
	elseif tag == "Paren" then
		self:at(expr.line)
		self:raw("(")
		self:expression(expr.expr)
		self:raw(")")
	elseif tag == "Index" then
		self:at(expr.line)
		self:raw("__fsi_get(")
		self:expression(expr.obj)
		self:raw(",")
		if expr.keyTok then
			self:at(expr.keyTok.line)
			self:raw(quoted(expr.keyTok.text))
		else
			self:expression(expr.key)
		end
		self:raw(")")
	elseif tag == "Call" then
		self:at(expr.line)
		if expr.method then
			self:raw("__fsi_callm(")
			self:expression(expr.callee)
			self:raw(",")
			self:at(expr.method.line)
			self:raw(quoted(expr.method.text))
			for _, arg in ipairs(expr.args) do
				self:raw(",")
				self:expression(arg)
			end
			self:raw(")")
		else
			self:expression(expr.callee)
			self:raw("(")
			self:expressionList(expr.args)
			self:raw(")")
		end
	elseif tag == "Function" then
		self:at(expr.line)
		self:raw("function")
		self:functionBody(expr, false)
	elseif tag == "Table" then
		self:at(expr.line)
		self:raw("{")
		for i, field in ipairs(expr.fields) do
			if i > 1 then
				self:raw(",")
			end
			if field.kind == "keyed" then
				self:raw("[")
				self:expression(field.key)
				self:raw("]=")
				self:expression(field.value)
			elseif field.kind == "named" then
				self:token(field.keyTok)
				self:raw("=")
				self:expression(field.value)
			else
				self:expression(field.value)
			end
		end
		self:raw("}")
	elseif tag == "BinOp" then
		self:expression(expr.left)
		self:at(expr.opTok and expr.opTok.line)
		self:raw(expr.op)
		self:expression(expr.right)
	elseif tag == "UnOp" then
		self:at(expr.opTok and expr.opTok.line)
		self:raw(expr.op)
		self:expression(expr.operand)
	else
		error("transform: unknown expression " .. tostring(tag), 0)
	end
end

-- A function after its `function` keyword: its parameter list, marker and body.
function Emitter:functionBody(func, method)
	self:raw("(")
	if method then
		self:raw("self")
		if #func.params > 0 or func.varargTok then
			self:raw(",")
		end
	end
	for i, param in ipairs(func.params) do
		if i > 1 then
			self:raw(",")
		end
		self:token(param)
	end
	if func.varargTok then
		if #func.params > 0 then
			self:raw(",")
		end
		self:token(func.varargTok)
	end
	self:token(func.closeTok)
	if self.mark then
		self:raw("__fst(" .. quoted(self.mark) .. ");")
	end
	self:block(func.body)
	self:token(func.endTok)
end

-- `function t.k(...)` defines a field, so it goes through the write helper; `function t:k()` also gains self.
function Emitter:functionStatement(statement)
	local target, func = statement.target, statement.func
	if target.tag == "Name" then
		self:raw("function")
		self:token(target.token)
		self:functionBody(func, func.method)
		return
	end
	self:raw("__fsi_set(")
	self:expression(target.obj)
	self:raw(",")
	if target.keyTok then
		self:at(target.keyTok.line)
		self:raw(quoted(target.keyTok.text))
	else
		self:expression(target.key)
	end
	self:raw(",")
	self:raw("function")
	self:functionBody(func, func.method)
	self:raw(")")
end

function Emitter:assign(statement)
	local targets, exprs = statement.targets, statement.exprs
	local hasIndex = false
	for _, target in ipairs(targets) do
		if target.tag == "Index" then
			hasIndex = true
		end
	end
	if #targets == 1 and targets[1].tag == "Index" then
		local target = targets[1]
		self:raw("__fsi_set(")
		self:expression(target.obj)
		self:raw(",")
		if target.keyTok then
			self:at(target.keyTok.line)
			self:raw(quoted(target.keyTok.text))
		else
			self:expression(target.key)
		end
		self:raw(",")
		self:expression(exprs[1])
		self:raw(")")
		return
	end
	if not hasIndex then
		for i, target in ipairs(targets) do
			if i > 1 then
				self:raw(",")
			end
			self:expression(target)
		end
		self:raw("=")
		self:expressionList(exprs)
		return
	end
	-- A multiple assignment with a field target: keep Lua's evaluate-then-assign order through locals.
	self:raw("do")
	self:raw("local")
	local temps = {}
	for i = 1, #targets do
		temps[i] = "__fsi_t" .. i
		if i > 1 then
			self:raw(",")
		end
		self:raw(temps[i])
	end
	self:raw("=")
	self:expressionList(exprs)
	for i, target in ipairs(targets) do
		self:raw(";")
		if target.tag == "Index" then
			self:raw("__fsi_set(")
			self:expression(target.obj)
			self:raw(",")
			if target.keyTok then
				self:at(target.keyTok.line)
				self:raw(quoted(target.keyTok.text))
			else
				self:expression(target.key)
			end
			self:raw(",")
			self:raw(temps[i])
			self:raw(")")
		else
			self:expression(target)
			self:raw("=")
			self:raw(temps[i])
		end
	end
	self:raw("end")
end

---------------------------------------------------------------------------
-- Rewrite
---------------------------------------------------------------------------
-- `mark` is the addon name (addon code) or nil (Blizzard code). Returns the rewritten source.
function M.rewrite(text, mark)
	text = text:gsub("^\239\187\191", "")
	local tokens = tokenize(text, mark and ("@" .. mark) or "=(blizzard)")
	local body = parse(tokens, mark and ("@" .. mark) or "=(blizzard)")
	local emitter = setmetatable({ out = {}, line = 1, mark = mark }, Emitter)
	if mark then
		emitter:raw("__fst(" .. quoted(mark) .. ");")
	end
	-- No separator here: the marker already ends in `;`, and Lua 5.1 rejects an empty statement.
	emitter:block(body)
	return table.concat(emitter.out)
end

return M
