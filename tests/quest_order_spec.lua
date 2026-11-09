-- The Forever quest list's order: ready to turn in, then this zone, then every other zone, each nearest first. A quest
-- with no distance sorts after the ones with one, ties fall to the title and then the quest ID, and two runs agree.
local checks = 0
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local ns = {}
assert(loadfile("Locales/enUS.lua"))("ForeverCore", ns)
assert(loadfile("Core/QuestOrder.lua"))("ForeverCore", ns)

---@param record ForeverQuestRecord
local function record(questID, title, zone, distanceSq, extra)
	local value = { questID = questID, title = title, zone = zone, distanceSq = distanceSq }
	for key, field in pairs(extra or {}) do
		value[key] = field
	end
	return value
end

local function IDs(group)
	local out = {}
	for index, quest in ipairs(group.quests) do
		out[index] = quest.questID
	end
	return table.concat(out, ",")
end

-- Ready first, nearest first, then the current zone, then the other zones by their nearest quest.
local groups = ns.QuestOrder({
	record(1, "Ready far", "Durotar", 400, { ready = true }),
	record(2, "Ready near", "Durotar", 100, { ready = true }),
	record(3, "Ready unknown", "Durotar", nil, { ready = true }),
	record(4, "Here", "Durotar", 225, { onMap = true }),
	record(5, "Other far", "The Barrens", 900),
	record(6, "Other near", "The Barrens", 25),
	record(7, "Third", "Mulgore", 400),
})
equal(#groups, 4, "four groups")
equal(groups[1].title, "Ready to turn in", "the ready group comes first")
equal(IDs(groups[1]), "2,1,3", "ready quests are nearest first and a missing distance sorts last")
equal(groups[2].title, "Durotar", "the current zone follows, named by its quest log header")
equal(IDs(groups[2]), "4", "only the on-map quest is in the current zone")
equal(groups[3].title, "The Barrens", "the zone with the nearest other quest comes next")
equal(IDs(groups[3]), "6,5", "a zone's quests are nearest first")
equal(groups[4].title, "Mulgore", "then the rest by their nearest quest")
equal(IDs(groups[4]), "7", "with its quest")

-- A ready quest that is also on the map belongs to the ready group only.
groups = ns.QuestOrder({ record(10, "Turn in here", "Durotar", 16, { ready = true, onMap = true }) })
equal(#groups, 1, "a ready on-map quest makes one group")
equal(groups[1].title, "Ready to turn in", "and it is the ready group")
equal(IDs(groups[1]), "10", "with the quest in it")

-- Ties fall to the title, then the quest ID, so the order never changes between runs.
groups = ns.QuestOrder({
	record(20, "Beta", "Durotar", 100),
	record(21, "Alpha", "Durotar", 100),
	record(19, "Alpha", "Durotar", 100),
})
equal(IDs(groups[1]), "19,21,20", "equal distances sort by title and then by quest ID")

-- Empty groups are left out.
groups = ns.QuestOrder({ record(30, "Only here", "Durotar", 100, { onMap = true }) })
equal(#groups, 1, "no ready group and no other zones when there is nothing in them")
equal(groups[1].title, "Durotar", "the current zone still draws")
groups = ns.QuestOrder({ record(31, "Only other", "Mulgore", 100) })
equal(#groups, 1, "no ready or current group when there is nothing in them")
equal(groups[1].title, "Mulgore", "the other zone draws")
groups = ns.QuestOrder({})
equal(#groups, 0, "no records, no groups")

-- The same records in a different table order produce the same groups.
local records = {
	record(40, "C", "Mulgore", 300),
	record(41, "A", "Durotar", 100, { ready = true }),
	record(42, "B", "The Barrens", 100),
	record(43, "D", "Durotar", 200, { onMap = true }),
}
local first = ns.QuestOrder(records)
local reversed = {}
for index = #records, 1, -1 do
	reversed[#reversed + 1] = records[index]
end
local second = ns.QuestOrder(reversed)
equal(#first, #second, "determinism: same group count")
for index = 1, #first do
	equal(first[index].title, second[index].title, "determinism: group " .. index .. " title")
	equal(IDs(first[index]), IDs(second[index]), "determinism: group " .. index .. " quests")
end

print("quest_order_spec: " .. checks .. " checks passed")
