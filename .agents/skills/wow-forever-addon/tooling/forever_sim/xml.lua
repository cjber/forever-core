-- A small XML parser for Blizzard's FrameXML: elements, attributes, text, comments, CDATA and the five entities.
-- parse(text, name) returns the root element { tag, attr, children, text, line }.
local M = {}

local ENTITIES = { lt = "<", gt = ">", amp = "&", quot = '"', apos = "'" }

local function unescape(s)
	return (
		s:gsub("&(#?x?)(%w+);", function(kind, body)
			if kind == "" then
				return ENTITIES[body] or ("&" .. body .. ";")
			elseif kind == "#" then
				return string.char(tonumber(body) % 256)
			end
			return string.char(tonumber(body, 16) % 256)
		end)
	)
end
M.unescape = unescape

function M.parse(text, name)
	-- Positions only move forward, so lines are counted incrementally.
	local countedTo, countedLine = 0, 1
	local function lineAt(_, at)
		if at > countedTo then
			for _ in text:sub(countedTo + 1, at):gmatch("\n") do
				countedLine = countedLine + 1
			end
			countedTo = at
		end
		return countedLine
	end
	local pos = 1
	local root = { tag = "#document", attr = {}, children = {} }
	local stack = { root }
	local len = #text
	-- Byte order mark.
	if text:sub(1, 3) == "\239\187\191" then
		pos = 4
	end
	while pos <= len do
		local lt = text:find("<", pos, true)
		local top = stack[#stack]
		if not lt then
			break
		end
		if lt > pos then
			local chunk = text:sub(pos, lt - 1)
			if chunk:find("%S") then
				top.textLine = top.textLine or lineAt(text, pos)
				top.text = (top.text or "") .. unescape(chunk)
			end
		end
		if text:sub(lt, lt + 3) == "<!--" then
			local close = text:find("-->", lt + 4, true)
			if not close then
				error(string.format("%s:%d: unterminated comment", name or "xml", lineAt(text, lt)))
			end
			pos = close + 3
		elseif text:sub(lt, lt + 8) == "<![CDATA[" then
			local close = text:find("]]>", lt + 9, true)
			if not close then
				error(string.format("%s:%d: unterminated CDATA", name or "xml", lineAt(text, lt)))
			end
			top.text = (top.text or "") .. text:sub(lt + 9, close - 1)
			top.textLine = top.textLine or lineAt(text, lt)
			pos = close + 3
		elseif text:sub(lt, lt + 1) == "<?" or text:sub(lt, lt + 1) == "<!" then
			local close = text:find(">", lt, true)
			pos = close + 1
		elseif text:sub(lt, lt + 1) == "</" then
			local close = text:find(">", lt, true)
			local tag = text:sub(lt + 2, close - 1):match("^%s*([%w_:%.%-]+)")
			if top.tag ~= tag then
				error(
					string.format(
						"%s:%d: </%s> closes <%s>",
						name or "xml",
						lineAt(text, lt),
						tostring(tag),
						tostring(top.tag)
					)
				)
			end
			stack[#stack] = nil
			pos = close + 1
		else
			local tag, after = text:match("^<([%w_:%.%-]+)()", lt)
			if not tag then
				error(string.format("%s:%d: bad tag", name or "xml", lineAt(text, lt)))
			end
			local node = { tag = tag, attr = {}, children = {}, line = lineAt(text, lt) }
			local p = after
			local selfClosing = false
			while true do
				local ws, k, q, nextp = text:match("^(%s*)([%w_:%.%-]+)%s*=%s*([\"'])()", p)
				if k then
					local close = text:find(q, nextp, true)
					node.attr[k] = unescape(text:sub(nextp, close - 1))
					p = close + 1
				else
					local rest = text:match("^%s*()", p)
					p = rest
					local c = text:sub(p, p)
					if c == "/" then
						selfClosing = true
						p = text:find(">", p, true) + 1
						break
					elseif c == ">" then
						p = p + 1
						break
					else
						error(string.format("%s:%d: bad attribute in <%s>", name or "xml", lineAt(text, p), tag))
					end
				end
				local _ = ws
			end
			top.children[#top.children + 1] = node
			node.parent = top
			if not selfClosing then
				stack[#stack + 1] = node
			end
			pos = p
		end
	end
	if #stack ~= 1 then
		error(string.format("%s: unclosed <%s>", name or "xml", stack[#stack].tag))
	end
	local child = root.children[1]
	if child then
		child.parent = nil
	end
	return child
end

return M
