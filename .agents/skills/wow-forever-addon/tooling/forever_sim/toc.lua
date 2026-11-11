-- Reads an addon's TOC and the XML files it lists the way the client loads them: the file lines in order, each XML
-- replaced by its own entry plus its Script and Include children, and the virtual templates an XML defines. A spec
-- loader can then load every `kind == "lua"` and register every `kind == "xml"`'s templates, without a hand copy of the
-- client's rules.
local M = {}

local function readFile(path)
	local file = assert(io.open(path, "rb"), "cannot read " .. path)
	local text = file:read("*a")
	file:close()
	return text
end

-- Forward slashes, `.` and `..` resolved, and a leading `/` kept. A relative `..` that climbs above the start stays.
local function clean(path)
	path = (path or ""):gsub("\\", "/")
	local absolute = path:sub(1, 1) == "/"
	local parts = {}
	for part in path:gmatch("[^/]+") do
		if part == ".." then
			if #parts > 0 and parts[#parts] ~= ".." then
				parts[#parts] = nil
			elseif not absolute then
				parts[#parts + 1] = ".."
			end
		elseif part ~= "." then
			parts[#parts + 1] = part
		end
	end
	local joined = table.concat(parts, "/")
	if absolute then
		return "/" .. joined
	end
	return joined
end

local function join(base, path)
	path = clean(path)
	if path:sub(1, 1) == "/" then
		return path
	end
	base = clean(base)
	if base == "" then
		return path
	end
	return clean(base .. "/" .. path)
end

local function dirname(path)
	local directory = clean(path):match("^(.*)/[^/]*$")
	return directory or ""
end

local function extension(path)
	return (clean(path):match("%.([^./]+)$") or ""):lower()
end

local ENTITIES = { lt = "<", gt = ">", amp = "&", quot = '"', apos = "'" }
local function unescape(value)
	return (
		value:gsub("&(#?x?)(%w+);", function(kind, body)
			if kind == "" then
				return ENTITIES[body] or ("&" .. body .. ";")
			elseif kind == "#x" then
				return string.char((tonumber(body, 16) or 0) % 256)
			elseif kind == "#" then
				return string.char((tonumber(body) or 0) % 256)
			end
		end)
	)
end

-- An exact parse of the tags this reader needs: elements, quoted attributes, self-closing tags, comments, CDATA,
-- processing instructions and declarations. Text between elements is ignored. Returns the document's root element,
-- with `tag`, `attr` and `children` (a document with no root returns the `#document` node).
local function parse(text, name)
	local root = { tag = "#document", attr = {}, children = {} }
	local stack = { root }
	local position = 1
	local length = #text
	if text:sub(1, 3) == "\239\187\191" then
		position = 4
	end

	local function fail(message)
		error(string.format("%s byte %d: %s", name or "XML", position, message), 0)
	end

	while position <= length do
		local opening = text:find("<", position, true)
		if not opening then
			break
		end
		if text:sub(opening, opening + 3) == "<!--" then
			local closing = text:find("-->", opening + 4, true)
			if not closing then
				position = opening
				fail("unterminated comment")
			end
			position = closing + 3
		elseif text:sub(opening, opening + 8) == "<![CDATA[" then
			local closing = text:find("]]>", opening + 9, true)
			if not closing then
				position = opening
				fail("unterminated CDATA")
			end
			position = closing + 3
		elseif text:sub(opening, opening + 1) == "<?" then
			local closing = text:find("?>", opening + 2, true)
			if not closing then
				position = opening
				fail("unterminated processing instruction")
			end
			position = closing + 2
		elseif text:sub(opening, opening + 1) == "<!" then
			local closing = text:find(">", opening + 2, true)
			if not closing then
				position = opening
				fail("unterminated declaration")
			end
			position = closing + 1
		elseif text:sub(opening, opening + 1) == "</" then
			local closing = text:find(">", opening + 2, true)
			if not closing then
				position = opening
				fail("unterminated closing tag")
			end
			local tag = text:sub(opening + 2, closing - 1):match("^%s*([%w_:%.%-]+)%s*$")
			if not tag then
				position = opening
				fail("bad closing tag")
			end
			if stack[#stack].tag ~= tag then
				position = opening
				fail(string.format("</%s> closes <%s>", tag, stack[#stack].tag))
			end
			stack[#stack] = nil
			position = closing + 1
		else
			local tag, after = text:match("^<([%w_:%.%-]+)()", opening)
			if not tag then
				position = opening
				fail("bad tag")
			end
			local node = { tag = tag, attr = {}, children = {} }
			local cursor = after
			local selfClosing = false
			while true do
				cursor = text:match("^%s*()", cursor)
				local character = text:sub(cursor, cursor)
				if character == "/" then
					cursor = text:match("^%s*()", cursor + 1)
					if text:sub(cursor, cursor) ~= ">" then
						position = cursor
						fail("bad self-closing tag")
					end
					selfClosing = true
					cursor = cursor + 1
					break
				elseif character == ">" then
					cursor = cursor + 1
					break
				elseif character == "" then
					position = cursor
					fail("unterminated tag")
				end
				local key, quote, valueAt = text:match("^([%w_:%.%-]+)%s*=%s*([\"'])()", cursor)
				if not key then
					position = cursor
					fail("bad attribute in <" .. tag .. ">")
				end
				local closing = text:find(quote, valueAt, true)
				if not closing then
					position = cursor
					fail("unterminated attribute in <" .. tag .. ">")
				end
				node.attr[key] = unescape(text:sub(valueAt, closing - 1))
				cursor = closing + 1
			end
			stack[#stack].children[#stack[#stack].children + 1] = node
			node.parent = stack[#stack]
			if not selfClosing then
				stack[#stack + 1] = node
			end
			position = cursor
		end
	end

	if #stack ~= 1 then
		error(string.format("%s: unclosed <%s>", name or "XML", stack[#stack].tag), 0)
	end
	local child = root.children[1]
	if child then
		child.parent = nil
	end
	return child or root
end

-- Calls `visit` on `node` and then every element below it, in document order.
local function walk(node, visit)
	visit(node)
	for _, child in ipairs(node.children) do
		walk(child, visit)
	end
end

-- The virtual templates `path` defines, in document order: `{ name, type, inherits }`, where `type` is the element.
function M.templates(path)
	local document = parse(readFile(path), path)
	local templates = {}
	walk(document, function(node)
		if node.attr.virtual == "true" and node.attr.name then
			templates[#templates + 1] = {
				name = node.attr.name,
				type = node.tag,
				inherits = node.attr.inherits,
			}
		end
	end)
	return templates
end

-- The files the client loads from `tocName` under `root`, in order: `{ path, kind }`, with `kind` "lua" or "xml".
-- Each XML is listed, then its Script and Include children in document order, each include resolved from its XML's
-- folder and expanded the same way.
function M.files(root, tocName)
	if type(tocName) ~= "string" or tocName == "" then
		error("tocName is required", 2)
	end
	local tocPath = join(root, tocName)
	local tocDirectory = dirname(tocName)
	local output = {}

	local function expand(relative)
		local kind = extension(relative) == "xml" and "xml" or "lua"
		if kind == "lua" then
			output[#output + 1] = { path = join(root, relative), kind = "lua" }
			return
		end
		local path = join(root, relative)
		output[#output + 1] = { path = path, kind = "xml" }
		local document = parse(readFile(path), path)
		walk(document, function(node)
			if (node.tag == "Script" or node.tag == "Include") and node.attr.file then
				expand(join(dirname(relative), node.attr.file))
			end
		end)
	end

	local toc = readFile(tocPath)
	if toc:sub(1, 3) == "\239\187\191" then
		toc = toc:sub(4)
	end
	for line in toc:gmatch("[^\r\n]+") do
		line = line:match("^%s*(.-)%s*$")
		if line ~= "" and line:sub(1, 1) ~= "#" then
			expand(join(tocDirectory, line))
		end
	end
	return output
end

return M
