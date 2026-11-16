---@type string, ForeverTrackerNamespace
local _, ns = ...

-- The Forever quest list's order, kept pure so the spec runs it with no client: ready to turn in first, then the
-- current zone, then every other zone, each quest nearest first and every zone by its nearest quest. A quest with no
-- distance sorts after the ones with one, and ties fall to the title and then the quest ID, so two runs agree. One
-- title names one group, because the section keeps one block per title.

---@param record ForeverQuestRecord
---@return string
local function Title(record)
	return record.title or ""
end

---@param a ForeverQuestRecord
---@param b ForeverQuestRecord
---@return boolean
local function Before(a, b)
	local left, right = a.distanceSq, b.distanceSq
	if left ~= nil and right ~= nil then
		if left ~= right then
			return left < right
		end
	elseif left ~= nil then
		return true
	elseif right ~= nil then
		return false
	end
	local leftTitle, rightTitle = Title(a), Title(b)
	if leftTitle ~= rightTitle then
		return leftTitle < rightTitle
	end
	if type(a.questID) == "number" and type(b.questID) == "number" then
		return a.questID < b.questID
	end
	return tostring(a.questID or "") < tostring(b.questID or "")
end

---@param quests ForeverQuestRecord[]
local function Sort(quests)
	table.sort(quests, Before)
end

---@param records ForeverQuestRecord[]
---@return ForeverQuestGroup[]
function ns.QuestOrder(records)
	local ready, zones, current = {}, {}, {}
	for _, record in ipairs(records) do
		if record.ready then
			ready[#ready + 1] = record
		else
			local title = record.zone or ""
			if record.onMap then
				current[title] = true
			end
			local group = zones[title]
			if not group then
				group = { title = title, quests = {} }
				zones[title] = group
			end
			group.quests[#group.quests + 1] = record
		end
	end

	local groups = {}
	if #ready > 0 then
		Sort(ready)
		groups[#groups + 1] = { title = ns.L["Ready to turn in"], quests = ready }
	end
	local others = {}
	for _, group in pairs(zones) do
		Sort(group.quests)
		others[#others + 1] = group
	end
	table.sort(others, function(a, b)
		if (current[a.title] == true) ~= (current[b.title] == true) then
			return current[a.title] == true
		end
		if Before(a.quests[1], b.quests[1]) then
			return true
		end
		if Before(b.quests[1], a.quests[1]) then
			return false
		end
		return a.title < b.title
	end)
	for _, group in ipairs(others) do
		groups[#groups + 1] = group
	end
	-- The section keeps one tracker block per title (#521). Zone groups already include their on-map and off-map
	-- quests together; also merge a log heading that happens to match the translated ready-to-turn-in heading.
	local ordered, byTitle = {}, {}
	for _, group in ipairs(groups) do
		local first = byTitle[group.title]
		if first then
			for _, quest in ipairs(group.quests) do
				first.quests[#first.quests + 1] = quest
			end
			Sort(first.quests)
		else
			byTitle[group.title] = group
			ordered[#ordered + 1] = group
		end
	end
	return ordered
end
