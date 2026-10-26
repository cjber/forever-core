-- Contract for the shared case- and accent-insensitive matching: what Fold does to the letters the suite's item names
-- actually contain, and the tier order Rank puts a match in. Everything here runs on the plain Lua that luajit gives a
-- spec; the module needs no client.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local ns = {}
assert(loadfile("Core/Text.lua"))("ForeverCore", ns)
local Fold, Rank = ns.Text.Fold, ns.Text.Rank

-- Fold: lower case and accents gone, in one pass, for the names the addons hold.
equal(Fold("ÉLÉPHANT"), "elephant", "an accented French name in capitals")
equal(Fold("São Tomé"), "sao tome", "the Portuguese tilde and acute")
equal(Fold("Ægir"), "aegir", "the Æ ligature")
equal(Fold("Straße"), "strasse", "the sharp s, which is two letters in a fold")
equal(Fold("Œuvre"), "oeuvre", "the Œ ligature, from Latin Extended-A")
equal(Fold("Þórshöfn"), "thorshofn", "thorn and o-umlaut")
equal(Fold("Dûn Garok"), "dun garok", "the circumflex Adventure Guide's search was written for")
equal(Fold("Dalaran's Crater"), "dalaran's crater", "punctuation is left alone, so a title reads normally")
equal(Fold(""), "", "nothing folds to nothing")
equal(Fold(nil), "", "a missing name folds to nothing, it does not error")
equal(Fold(1234), "1234", "a number reads as its text")
equal(Fold("×÷"), "×÷", "the two signs are not letters and stay")

-- Rank: exact, then prefix, then a word starting the query, then anywhere; nil when it does not match at all.
local function Tier(title, query)
	return Rank(Fold(title), Fold(query))
end
equal(Tier("Dûn Garok", "dun garok"), 1, "the whole title, accents folded on both sides")
equal(Tier("Dûn Garok", "Dun"), 2, "the title starts with the query")
equal(Tier("Dûn Garok", "garok"), 3, "a query word starts the title's second word")
equal(Tier("Dûn Garok", "un"), 4, "a substring inside a word is still a match, the lowest tier")
equal(Tier("Dûn Garok", "morogh"), nil, "a query word that appears nowhere is no match")
equal(Tier("Dalaran's Crater", "s crater"), 3, "punctuation is a word break, so a word can start after an apostrophe")
equal(Tier("Dûn Garok's Camp", "garok"), 3, "a word before an apostrophe still starts a word")
equal(Tier("Vargarok", "garok"), 4, "a tail of a longer word is a substring, never a word start")
equal(Tier("The Copper Dragon", "copper dragon"), 3, "every word of a two-word query starts a word")
equal(Tier("The Copper Dragon", "copper drago"), 3, "the query's last word may be a prefix of the title's")
equal(Tier("The Copper Dragon", "dragon copper"), 3, "the order of the query's words does not matter")
equal(Tier("The Copper Dragon", "copper wyrm"), nil, "one query word missing is no match")
equal(Tier("The Copper Dragon", "the copper dragon"), 1, "the whole title again, with its article")
equal(Tier("The Copper Dragon", ""), 0, "an empty query matches everything equally")
equal(Tier("Straße", "strasse"), 1, "the fold applies to the search as well as the title")
equal(Tier("Ægir", "aeg"), 2, "a folded ligature is a prefix")

-- The ordering a caller sorts by: rank first, then whatever tie-break it likes. This is the shape Hoard's item list
-- and Adventure Guide's quest list both sort with.
local names =
	{ "The Shattered Halls", "Hall of Legends", "Thrallmar", "Shattrath", "Auchindoun Halls", "Marshall's Post" }
local query = Fold("hall")
local ranked = {}
for _, name in ipairs(names) do
	local rank = Tier(name, query)
	if rank then
		table.insert(ranked, { rank, name })
	end
end
table.sort(ranked, function(a, b)
	if a[1] ~= b[1] then
		return a[1] < b[1]
	end
	return a[2] < b[2]
end)
equal(#ranked, 4, "four of the six names match 'hall'; Thrallmar and Shattrath have none of it")
equal(ranked[1][2], "Hall of Legends", "the title that starts with the query sorts first")
equal(ranked[2][2], "Auchindoun Halls", "then the word starts, alphabetically among their tier")
equal(ranked[3][2], "The Shattered Halls", "the other word start")
equal(ranked[4][2], "Marshall's Post", "and a 'hall' inside a word last")
equal(ranked[1][1], 2, "the top of that list is the prefix tier")
equal(ranked[2][1], 3, "the word starts next")
equal(ranked[3][1], 3, "both of them")
equal(ranked[4][1], 4, "and the substring tier at the bottom")

print(("text_spec: %d checks passed"):format(checks))
