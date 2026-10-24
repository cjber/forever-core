-- Marks every function an addon defines so the sim knows when the addon's code runs: after each function's
-- parameter list it inserts `__fst("Addon");` on the same line, so line numbers and error messages stay the
-- client's. Blizzard code is never rewritten and runs at full speed; only addon functions pay for the marker.
local M = {}

M.MARKER = "__fst"

local function longBracket(src, i)
	-- At "[", returns the closing position of a long bracket ([[...]], [==[...]==]) or nil.
	local eq = src:match("^%[(=*)%[", i)
	if not eq then
		return nil
	end
	local close = "]" .. eq .. "]"
	local _, e = src:find(close, i + #eq + 2, true)
	return e or #src
end

-- Returns src with the marker inserted into every function body.
function M.rewrite(src, addon)
	local out = {}
	local i, n = 1, #src
	local marker = " " .. M.MARKER .. "(" .. string.format("%q", addon) .. ");"
	local pendingFunction = false
	local depth = 0
	local last = 1
	while i <= n do
		local c = src:sub(i, i)
		if c == "-" and src:sub(i, i + 1) == "--" then
			local e = src:sub(i + 2, i + 2) == "[" and longBracket(src, i + 2)
			if e then
				i = e + 1
			else
				local nl = src:find("\n", i, true)
				i = nl and nl or n + 1
			end
		elseif c == '"' or c == "'" then
			local j = i + 1
			while j <= n do
				local d = src:sub(j, j)
				if d == "\\" then
					j = j + 2
				elseif d == c or d == "\n" then
					break
				else
					j = j + 1
				end
			end
			i = j + 1
		elseif c == "[" and (src:sub(i + 1, i + 1) == "[" or src:sub(i + 1, i + 1) == "=") then
			local e = longBracket(src, i)
			i = e and e + 1 or i + 1
		elseif c:match("[%a_]") then
			local word = src:match("^[%w_]+", i)
			if word == "function" then
				pendingFunction = true
				depth = 0
			end
			i = i + #word
		elseif c:match("%d") then
			local num = src:match("^0[xX]%x+", i)
				or src:match("^%d+%.?%d*[eE][%+%-]?%d+", i)
				or src:match("^%d+%.?%d*", i)
			i = i + #num
		elseif pendingFunction and c == "(" then
			depth = depth + 1
			i = i + 1
		elseif pendingFunction and c == ")" then
			depth = depth - 1
			i = i + 1
			if depth == 0 then
				out[#out + 1] = src:sub(last, i - 1)
				out[#out + 1] = marker
				last = i
				pendingFunction = false
			end
		else
			i = i + 1
		end
	end
	out[#out + 1] = src:sub(last)
	-- The main chunk itself runs as the addon too.
	return marker:sub(2) .. table.concat(out)
end

return M
