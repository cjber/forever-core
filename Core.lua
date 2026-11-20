local _, ns = ...

ns.isCore = true

-- ns.store is the one authoritative settings table for this runtime copy. All core files read it through ns.Store();
-- offered account globals mirror that table, including ForeverCoreDB when standalone is installed. The standalone path
-- resolves the authoritative table in Start, after the client has loaded SavedVariables, so a pre-start read never
-- caches a placeholder over the real table. The unwrapped standalone path is transitional.
---@return table?
function ns.Store()
	return ns.store
end

-- Work that changes the client (frames, frame pools, event registrations, hooks, the error handler) is queued here
-- and runs first in ns.Start, so defining a converted copy leaves the client untouched and the loader can still refuse
-- it. The unwrapped standalone has no step between its files and Start, so its work runs at once, as before.
local startWork = {}
---@param work fun()
function ns.AtStart(work)
	if ns.copy == nil or ns.started then
		work()
	else
		startWork[#startWork + 1] = work
	end
end
local function RunStartWork()
	ns.started = true
	local queued = startWork
	startWork = {}
	for index = 1, #queued do
		queued[index]()
	end
end

-- The standalone addon is a participant too: its ForeverCoreDB is offered by name so an embedded election can merge
-- it with the consumers' mirrors. A converted standalone does the same, and an elected copy never offers its host's
-- account table under the wrong name.
do
	local loader = rawget(_G, "ForeverCoreLoader")
	if loader ~= nil and type(loader.OfferStore) == "function" and (ns.mode == nil or ns.mode == "standalone") then
		loader.OfferStore("ForeverCore", "ForeverCoreDB")
	end
end

-- ForeverCore is the shared floor under the Forever addons: one objective-tracker column the suite docks into, the
-- header drag and Lock switch that move it, and the section order that stacks them. Every Forever addon requires this
-- addon (docs/adoption.md), so exactly one copy of each shared file loads in the game. This file is ForeverCore's own
-- install of the tracker contract: the settings the host reads, the one ns.Store() seam, and the explicit ns.Start()
-- a converted copy gets from the loader (with the transitional ADDON_LOADED handler for the unwrapped standalone).

-- One defaults constructor, used both for a throwaway table before the store exists and for the table kept in the
-- runtime store (ForeverCoreDB in the transitional standalone). The tracker scale, the Lock switch, the background
-- opacity and the column's position live in the host's own settings rather than an addon's defaults table, because the
-- host outlives whichever addon happened to load first.
---@return ForeverTrackerSettings
local function DefaultTrackerSettings()
	-- `attached = false` marks a fresh table as already past the host's one-time move off the quest tracker.
	return { attached = false, locked = false, scale = 1, backdropOpacity = 0 }
end

-- Repair one settings table, so a hand-edited or older value cannot break the host's layout.
---@param settings ForeverTrackerSettings
---@return ForeverTrackerSettings
local function NormalizeTrackerSettings(settings)
	if type(settings.scale) ~= "number" or settings.scale ~= settings.scale then
		settings.scale = 1
	end
	if type(settings.locked) ~= "boolean" then
		settings.locked = false
	end
	if type(settings.backdropOpacity) ~= "number" or settings.backdropOpacity ~= settings.backdropOpacity then
		settings.backdropOpacity = 0
	end
	return settings
end

-- Saved variables arrive after the TOC loads, so answer with a throwaway default until they do.
---@return ForeverTrackerSettings
function ns.TrackerHostSettings()
	local db = ns.Store()
	if type(db) ~= "table" then
		return DefaultTrackerSettings()
	end
	local settings = db.trackerHost
	if type(settings) ~= "table" then
		settings = DefaultTrackerSettings()
		db.trackerHost = settings
	end
	return NormalizeTrackerSettings(settings)
end

-- The store mirrors use one reserved key inside a consumer's account SavedVariables table, so core state never
-- overwrites a consumer's own `core` field. A standalone ForeverCoreDB is the store itself.
local STORE_KEY = "ForeverCoreStore"
local STORE_SCHEMA = 1
local MAX_STORE_ERRORS = 50
local MAX_STORE_LINES = 200
local MAX_ANCESTORS = 64

local MISSING = setmetatable({}, {
	__tostring = function()
		return "<absent>"
	end,
})

local function ToString(value)
	local ok, text = pcall(tostring, value)
	return ok and text or "?"
end

local function Canonical(value, seen)
	local kind = type(value)
	if kind == "nil" then
		return "nil"
	elseif kind == "boolean" then
		return value and "true" or "false"
	elseif kind == "number" then
		if value ~= value then
			return "nan"
		elseif value == math.huge then
			return "inf"
		elseif value == -math.huge then
			return "-inf"
		end
		if value == 0 then
			value = 0
		end
		return ("%.17g"):format(value)
	elseif kind == "string" then
		return ("s%d:%s"):format(#value, value)
	elseif kind == "table" then
		seen = seen or {}
		if seen[value] then
			return "cycle:" .. seen[value]
		end
		local id = #seen + 1
		seen[value] = id
		local keys = {}
		for key in pairs(value) do
			keys[#keys + 1] = key
		end
		table.sort(keys, function(a, b)
			return Canonical(a, seen) < Canonical(b, seen)
		end)
		local parts = { "{" }
		for _, key in ipairs(keys) do
			parts[#parts + 1] = Canonical(key, seen)
			parts[#parts + 1] = "="
			parts[#parts + 1] = Canonical(value[key], seen)
			parts[#parts + 1] = ";"
		end
		parts[#parts + 1] = "}"
		seen[value] = nil
		return table.concat(parts)
	end
	return kind .. ":" .. ToString(value)
end

local function DeepCopy(value, seen)
	if type(value) ~= "table" then
		return value
	end
	seen = seen or {}
	if seen[value] then
		return seen[value]
	end
	local copy = {}
	seen[value] = copy
	for key, item in pairs(value) do
		copy[DeepCopy(key, seen)] = DeepCopy(item, seen)
	end
	return copy
end

local function Same(a, b)
	return Canonical(a) == Canonical(b)
end

local function SortedKeys(value)
	local keys = {}
	for key in pairs(value) do
		keys[#keys + 1] = key
	end
	table.sort(keys, function(a, b)
		return Canonical(a) < Canonical(b)
	end)
	return keys
end

-- Escape separators and preserve numeric keys. Quest folds are indexed by numeric quest ID,
-- and character/zone names can contain periods. Plain dotted paths cannot round-trip them.
local function PathKey(key)
	if type(key) == "number" then
		return "~2:" .. (Canonical(key):gsub("%.", "~1"))
	elseif type(key) == "boolean" then
		return key and "~3:true" or "~3:false"
	end
	return key == "" and "~4" or (tostring(key):gsub("~", "~0"):gsub("%.", "~1"))
end

local function PathParts(path)
	local parts = {}
	for part in (tostring(path) .. "."):gmatch("(.-)%.") do
		if part == "~4" then
			parts[#parts + 1] = ""
		elseif part:sub(1, 3) == "~2:" then
			parts[#parts + 1] = tonumber((part:sub(4):gsub("~1", ".")))
		elseif part:sub(1, 3) == "~3:" then
			parts[#parts + 1] = part == "~3:true"
		else
			parts[#parts + 1] = (part:gsub("~1", "."):gsub("~0", "~"))
		end
	end
	return parts
end

local function GetPath(root, path)
	local value = root
	for _, part in ipairs(PathParts(path)) do
		if type(value) ~= "table" then
			return MISSING
		end
		value = rawget(value, part)
		if value == nil then
			return MISSING
		end
	end
	return value
end

local function SetPath(root, path, value)
	local parts = PathParts(path)
	local target = root
	for index = 1, #parts - 1 do
		local part = parts[index]
		local nextTarget = rawget(target, part)
		if type(nextTarget) ~= "table" then
			nextTarget = {}
			target[part] = nextTarget
		end
		target = nextTarget
	end
	target[parts[#parts]] = value
end

-- The settings half of a store: every root key except the two runtime histories and the store metadata. A table is
-- walked so a future nested setting is reconciled by path rather than replaced as one opaque blob.
local function CollectPaths(settings, prefix, out)
	for _, key in ipairs(SortedKeys(settings)) do
		local value = settings[key]
		local path = prefix == "" and PathKey(key) or (prefix .. "." .. PathKey(key))
		if type(value) == "table" and next(value) ~= nil then
			CollectPaths(value, path, out)
		else
			out[path] = true
		end
	end
end

local function SettingsOf(data)
	local settings = {}
	if type(data) ~= "table" then
		return settings
	end
	for key, value in pairs(data) do
		if key ~= "errors" and key ~= "log" and key ~= "_store" and key ~= STORE_KEY then
			settings[key] = DeepCopy(value)
		end
	end
	return settings
end

local function ConflictsOf(data)
	local conflicts = type(data) == "table" and type(data._store) == "table" and data._store.conflicts or nil
	return type(conflicts) == "table" and DeepCopy(conflicts) or {}
end

local function ValidMarker(marker)
	return type(marker) == "table"
		and marker.schema == STORE_SCHEMA
		and type(marker.node) == "string"
		and marker.node ~= ""
		and type(marker.snapshot) == "table"
		and type(marker.parents) == "table"
		and type(marker.ancestors) == "table"
end

local function SetOf(list)
	local set = {}
	for _, value in ipairs(type(list) == "table" and list or {}) do
		if type(value) == "string" then
			set[value] = true
		end
	end
	return set
end

local function SortedSet(set)
	local list = {}
	for value in pairs(set) do
		if type(value) == "string" then
			list[#list + 1] = value
		end
	end
	table.sort(list)
	return list
end

local nodeCounter = 0

---@return string
function ns.NewStoreNode()
	nodeCounter = nodeCounter + 1
	local wall = 0
	local clock = rawget(_G, "time")
	if type(clock) == "function" then
		local ok, value = pcall(clock)
		wall = ok and tonumber(value) or 0
	elseif type(os) == "table" and type(os.time) == "function" then
		wall = os.time()
	end
	local address = ToString({}):match("0x%x+") or "local"
	return ("%s:%s:%d"):format(ToString(wall), address, nodeCounter)
end

-- The error journal merges by signature. `count` is a lower bound under a fork: a shared ancestor is not counted
-- twice, so the result never invents an occurrence. One n-ary pass, then the existing cap once at the end.
local function MergeErrors(heads)
	local groups = {}
	for _, observed in ipairs(heads) do
		local head = observed.head or observed
		local errors = type(head.data.errors) == "table" and head.data.errors or {}
		for _, entry in ipairs(errors) do
			if type(entry) == "table" then
				local key = type(entry.signature) == "string" and entry.signature or Canonical(entry)
				local group = groups[key]
				if not group then
					group = { entries = {} }
					groups[key] = group
				end
				group.entries[#group.entries + 1] = {
					entry = entry,
					folder = head.folder,
					build = head.build,
				}
			end
		end
	end
	local merged = {}
	for key, group in pairs(groups) do
		table.sort(group.entries, function(a, b)
			local aLast = tonumber(a.entry.lastSeen) or 0
			local bLast = tonumber(b.entry.lastSeen) or 0
			if aLast ~= bLast then
				return aLast > bLast
			end
			if a.folder ~= b.folder then
				return a.folder < b.folder
			end
			return Canonical(a.entry) < Canonical(b.entry)
		end)
		local base = group.entries[1].entry
		local result = DeepCopy(base)
		result.signature = type(base.signature) == "string" and base.signature or key
		result.count = tonumber(base.count) or 1
		result.firstSeen = tonumber(base.firstSeen) or 0
		result.lastSeen = tonumber(base.lastSeen) or result.firstSeen
		for _, candidate in ipairs(group.entries) do
			local entry = candidate.entry
			result.count = math.max(result.count, tonumber(entry.count) or 1)
			local firstSeen = tonumber(entry.firstSeen)
			if firstSeen and (result.firstSeen == 0 or firstSeen < result.firstSeen) then
				result.firstSeen = firstSeen
			end
			local lastSeen = tonumber(entry.lastSeen)
			if lastSeen and lastSeen > result.lastSeen then
				result.lastSeen = lastSeen
			end
		end
		merged[#merged + 1] = result
	end
	table.sort(merged, function(a, b)
		local aLast = tonumber(a.lastSeen) or 0
		local bLast = tonumber(b.lastSeen) or 0
		if aLast ~= bLast then
			return aLast < bLast
		end
		if a.signature ~= b.signature then
			return a.signature < b.signature
		end
		return Canonical(a) < Canonical(b)
	end)
	local dropped = 0
	while #merged > MAX_STORE_ERRORS do
		table.remove(merged, 1)
		dropped = dropped + 1
	end
	return merged, dropped
end

local function LineKey(line)
	local date, seconds = tostring(line):match("^%s*(%d%d%d%d%-%d%d%-%d%d %d%d:%d%d:%d%d) %+([%d%.]+)s")
	return date or "", tonumber(seconds) or 0, tostring(line)
end

-- Log lines merge as a multiset: max occurrences across heads, so a shared ancestor line is not duplicated, while two
-- identical lines written in one session survive. One n-ary pass, then the existing 200-line cap once at the end.
local function MergeLogLines(heads)
	local counts = {}
	for _, observed in ipairs(heads) do
		local head = observed.head or observed
		local lines = type(head.data.log) == "table" and type(head.data.log.lines) == "table" and head.data.log.lines
			or {}
		local seen = {}
		for _, line in ipairs(lines) do
			if type(line) == "string" then
				seen[line] = (seen[line] or 0) + 1
			end
		end
		for line, count in pairs(seen) do
			counts[line] = math.max(counts[line] or 0, count)
		end
	end
	local merged = {}
	for line, count in pairs(counts) do
		for _ = 1, count do
			merged[#merged + 1] = line
		end
	end
	table.sort(merged, function(a, b)
		local aDate, aSeconds, aText = LineKey(a)
		local bDate, bSeconds, bText = LineKey(b)
		if aDate ~= bDate then
			return aDate < bDate
		end
		if aSeconds ~= bSeconds then
			return aSeconds < bSeconds
		end
		return aText < bText
	end)
	local dropped = 0
	while #merged > MAX_STORE_LINES do
		table.remove(merged, 1)
		dropped = dropped + 1
	end
	return merged, dropped
end

-- Observe one loaded mirror before any normalization or attachment mutates it. A mirror whose settings still equal its
-- recorded snapshot is the recorded node; a changed mirror is a new child of that node; a missing or broken marker is
-- an external node with no proven ancestry. The snapshot is what makes a copied WTF branch or a legacy edit visible
-- instead of being trusted because its metadata looks old.
local function Observe(head, nextNode)
	local settings = SettingsOf(head.data)
	local conflicts = ConflictsOf(head.data)
	local marker = head.data._store
	local baseline = ValidMarker(marker) and marker.snapshot or nil
	if ValidMarker(marker) and Same(settings, marker.snapshot) and Same(conflicts, marker.conflicts or {}) then
		return {
			head = head,
			node = marker.node,
			ancestors = SetOf(marker.ancestors),
			parents = SetOf(marker.parents),
			settings = settings,
			baseline = baseline,
			conflicts = conflicts,
		}
	end
	local ancestors = {}
	local parents = {}
	if ValidMarker(marker) then
		for _, node in ipairs(marker.ancestors) do
			if type(node) == "string" then
				ancestors[node] = true
			end
		end
		ancestors[marker.node] = true
		parents[marker.node] = true
	end
	local node = nextNode()
	ancestors[node] = true
	return {
		head = head,
		node = node,
		ancestors = ancestors,
		parents = parents,
		settings = settings,
		baseline = baseline,
		conflicts = conflicts,
	}
end

-- Reconcile every loaded head in one pass. A head is dropped only when another observed head proves it as an ancestor
-- (so its state is already included) or when it is the same unchanged node. A changed mirror is never discarded on
-- metadata alone. Differing setting leaves retain every distinct candidate in `_store.conflicts`; no folder order,
-- revision or clock decides which candidate is lost. The live value is chosen by build then folder only so the player
-- sees one value now, not so the others can be forgotten.
---@param heads { folder: string, build: number, data: table }[]
---@param options? ForeverCoreReconcileOptions
---@return table, table
function ns.ReconcileStore(heads, options)
	options = options or {}
	local nextNode = options.NextNode or ns.NewStoreNode
	local ordered = {}
	for _, head in ipairs(heads or {}) do
		if type(head) == "table" and type(head.data) == "table" then
			ordered[#ordered + 1] = {
				folder = tostring(head.folder or "?"),
				build = tonumber(head.build) or 0,
				data = head.data,
			}
		end
	end
	table.sort(ordered, function(a, b)
		if a.folder ~= b.folder then
			return a.folder < b.folder
		end
		if a.build ~= b.build then
			return a.build < b.build
		end
		return Canonical(a.data) < Canonical(b.data)
	end)

	local observed = {}
	local seenNodes = {}
	for _, head in ipairs(ordered) do
		local entry = Observe(head, nextNode)
		local existing = seenNodes[entry.node]
		if existing == nil then
			seenNodes[entry.node] = #observed + 1
			observed[#observed + 1] = entry
		else
			-- The same unchanged node offered by two addons is one logical head. Keep the first provenance.
			observed[existing].head.folders = observed[existing].head.folders or { observed[existing].head.folder }
			observed[existing].head.folders[#observed[existing].head.folders + 1] = entry.head.folder
		end
	end

	local accepted = {}
	local rejected = {}
	for index, entry in ipairs(observed) do
		local dominated = false
		for otherIndex, other in ipairs(observed) do
			if otherIndex ~= index and other.node ~= entry.node and other.ancestors[entry.node] then
				dominated = true
				break
			end
		end
		if dominated then
			rejected[#rejected + 1] = { folder = entry.head.folder, node = entry.node, reason = "ancestor" }
		else
			accepted[#accepted + 1] = entry
		end
	end
	if #accepted == 0 then
		accepted = observed
	end

	local result = {}
	local paths = {}
	for _, entry in ipairs(accepted) do
		CollectPaths(entry.settings, "", paths)
		if type(entry.baseline) == "table" then
			CollectPaths(entry.baseline, "", paths)
		end
		for _, conflict in ipairs(entry.conflicts) do
			if type(conflict) == "table" and type(conflict.path) == "string" then
				paths[conflict.path] = true
			end
		end
	end

	-- A scalar or empty table at a parent competes with the whole subtree. Drop its
	-- descendant paths so a later SetPath cannot overwrite the chosen parent value.
	local descendants = {}
	for path in pairs(paths) do
		local prefix = ""
		local parts = PathParts(path)
		for index = 1, #parts - 1 do
			prefix = index == 1 and PathKey(parts[index]) or (prefix .. "." .. PathKey(parts[index]))
			if paths[prefix] then
				descendants[path] = prefix
				break
			end
		end
	end
	for path in pairs(descendants) do
		paths[path] = nil
	end

	local candidates = {}
	local function Candidates(path)
		local list = candidates[path]
		if not list then
			list = {}
			candidates[path] = list
		end
		return list
	end
	local function Add(path, value, present, folder, build, live)
		local stored = MISSING
		if present then
			stored = DeepCopy(value)
		end
		local text = present and Canonical(value) or "missing"
		local list = Candidates(path)
		for _, candidate in ipairs(list) do
			if candidate.key == text then
				if build > candidate.build or (build == candidate.build and folder < candidate.folder) then
					candidate.folder, candidate.build = folder, build
				end
				candidate.present = candidate.present or present
				candidate.live = candidate.live or live == true
				if present and candidate.value == MISSING then
					candidate.value = DeepCopy(value)
				end
				return
			end
		end
		list[#list + 1] = {
			key = text,
			present = present,
			value = stored,
			folder = folder,
			build = build,
			live = live == true,
		}
	end

	-- Keep candidates retained by an earlier unresolved conflict, even when the live value is one of them.
	for _, entry in ipairs(accepted) do
		for _, conflict in ipairs(entry.conflicts) do
			if type(conflict) == "table" and type(conflict.path) == "string" then
				for _, value in ipairs(type(conflict.values) == "table" and conflict.values or {}) do
					if type(value) == "table" then
						local path = descendants[conflict.path] or conflict.path
						local candidate = value.value
						local present = value.present ~= false
						if path ~= conflict.path then
							-- Lift a historical child into the same subtree as the live parent.
							local historical = DeepCopy(entry.baseline or entry.settings)
							if present then
								SetPath(historical, conflict.path, candidate)
							else
								SetPath(historical, conflict.path, nil)
							end
							candidate = GetPath(historical, path)
							present = candidate ~= MISSING
						end
						Add(
							path,
							candidate,
							present,
							value.folder or entry.head.folder,
							tonumber(value.build) or entry.head.build
						)
					end
				end
			end
		end
	end

	-- Present leaves first. A head that lacks a path has an opinion only when its own recorded baseline had that path,
	-- so a one-sided addition is not a deletion and a one-sided deletion is a real tombstone.
	for _, entry in ipairs(accepted) do
		for path in pairs(paths) do
			local value = GetPath(entry.settings, path)
			if value ~= MISSING then
				Add(path, value, true, entry.head.folder, entry.head.build, true)
			end
		end
	end
	for _, entry in ipairs(accepted) do
		for path in pairs(paths) do
			local known = type(entry.baseline) == "table" and GetPath(entry.baseline, path) ~= MISSING
			for _, conflict in ipairs(entry.conflicts) do
				if type(conflict) == "table" and type(conflict.path) == "string" then
					local boundary = descendants[conflict.path] or conflict.path
					known = known or boundary == path
				end
			end
			if known and GetPath(entry.settings, path) == MISSING then
				Add(path, MISSING, false, entry.head.folder, entry.head.build, true)
			end
		end
	end

	local conflicts = {}
	local report = { accepted = accepted, rejected = rejected, conflicts = conflicts }
	local orderedPaths = {}
	for path in pairs(candidates) do
		orderedPaths[#orderedPaths + 1] = path
	end
	table.sort(orderedPaths)
	for _, path in ipairs(orderedPaths) do
		local list = candidates[path]
		table.sort(list, function(a, b)
			if a.build ~= b.build then
				return a.build > b.build
			end
			if a.folder ~= b.folder then
				return a.folder < b.folder
			end
			return a.key < b.key
		end)
		local chosen
		if options.preferredFolder ~= nil then
			for index, candidate in ipairs(list) do
				if candidate.folder == options.preferredFolder and candidate.live then
					chosen = index
					break
				end
			end
		end
		if chosen == nil then
			for index, candidate in ipairs(list) do
				if candidate.live then
					chosen = index
					break
				end
			end
		end
		if chosen == nil then
			chosen = 1
		end
		if list[chosen].present then
			SetPath(result, path, DeepCopy(list[chosen].value))
		end
		if #list > 1 then
			local values = {}
			for index, candidate in ipairs(list) do
				values[index] = {
					present = candidate.present,
					value = candidate.present and DeepCopy(candidate.value),
					folder = candidate.folder,
					build = candidate.build,
				}
			end
			conflicts[#conflicts + 1] = {
				path = path,
				chosen = chosen,
				values = values,
			}
		end
	end

	local pinnedValue = false
	for _, head in ipairs(ordered) do
		if type(head.data.log) == "table" and head.data.log.pinned == true then
			pinnedValue = true
			break
		end
	end

	local errors, droppedErrors = MergeErrors(ordered)
	local lines, droppedLines = MergeLogLines(ordered)
	result.errors = errors
	result.log = { lines = lines, pinned = pinnedValue }

	local resultNode = nextNode()
	local parents = {}
	local ancestors = {}
	for _, entry in ipairs(accepted) do
		parents[entry.node] = true
		for node in pairs(entry.ancestors) do
			ancestors[node] = true
		end
		ancestors[entry.node] = true
	end
	ancestors[resultNode] = true
	local ancestorList = SortedSet(ancestors)
	while #ancestorList > MAX_ANCESTORS do
		table.remove(ancestorList, 1)
	end
	result._store = {
		schema = STORE_SCHEMA,
		node = resultNode,
		parents = SortedSet(parents),
		ancestors = ancestorList,
		snapshot = SettingsOf(result),
		conflicts = #conflicts > 0 and conflicts or nil,
	}
	report.parents = result._store.parents
	report.node = resultNode
	report.droppedErrors = droppedErrors
	report.droppedLines = droppedLines
	report.conflicts = conflicts
	return result, report
end

-- Replace one table's settings with another's, deleting keys absent from the result and keeping the identity of every
-- table already held by the target. The error journal and log ring are runtime histories, so they merge in place
-- rather than being replaced: SafeCall and Log keep the tables they attached.
local function ApplySettings(target, source, nested)
	local wanted = nested and source or SettingsOf(source)
	for key in pairs(target) do
		if
			wanted[key] == nil
			and (nested or (key ~= "errors" and key ~= "log" and key ~= "_store" and key ~= STORE_KEY))
		then
			target[key] = nil
		end
	end
	for key, value in pairs(wanted) do
		local existing = rawget(target, key)
		if type(existing) == "table" and type(value) == "table" and next(existing) ~= nil and next(value) ~= nil then
			ApplySettings(existing, value, true)
		else
			target[key] = DeepCopy(value)
		end
	end
end

function ns.ApplyStore(target, source)
	if type(target) ~= "table" or type(source) ~= "table" then
		return target
	end
	ApplySettings(target, source)

	local errors = type(target.errors) == "table" and target.errors or {}
	for index = #errors, 1, -1 do
		errors[index] = nil
	end
	for index, entry in ipairs(type(source.errors) == "table" and source.errors or {}) do
		errors[index] = DeepCopy(entry)
	end
	target.errors = errors

	local log = type(target.log) == "table" and target.log or {}
	local lines = type(log.lines) == "table" and log.lines or {}
	for index = #lines, 1, -1 do
		lines[index] = nil
	end
	for index, line in
		ipairs(type(source.log) == "table" and type(source.log.lines) == "table" and source.log.lines or {})
	do
		lines[index] = line
	end
	log.lines = lines
	log.pinned = type(source.log) == "table" and source.log.pinned == true
	target.log = log

	if type(source._store) == "table" then
		target._store = DeepCopy(source._store)
	end
	return target
end

-- Resolve every offered account SavedVariables name at reconciliation, after a consumer may have replaced its table.
-- A mirror lives under the reserved key; the standalone's own global is the store itself.
function ns.StoreHeads()
	local heads = {}
	local seen = {}
	local function Add(folder, build, data)
		if type(data) == "table" and not seen[data] then
			seen[data] = true
			heads[#heads + 1] = { folder = folder, build = build, data = data }
		end
	end
	local loader = rawget(_G, "ForeverCoreLoader")
	local offers = loader ~= nil and type(loader.Offers) == "function" and loader.Offers() or {}
	for _, offer in ipairs(offers) do
		local db = rawget(_G, offer.globalName)
		if type(db) == "table" then
			local data
			if offer.folder == "ForeverCore" and offer.globalName == "ForeverCoreDB" then
				data = db
			else
				data = rawget(db, STORE_KEY)
				if type(data) ~= "table" then
					data = nil
				end
			end
			if data ~= nil then
				local build = 0
				if loader ~= nil and type(loader.Candidates) == "function" then
					for _, copy in ipairs(loader.Candidates()) do
						if copy.folder == offer.folder then
							build = tonumber(copy.build) or 0
							break
						end
					end
				end
				Add(offer.folder, build, data)
			end
		end
	end
	local store = ns.Store()
	if type(store) == "table" then
		-- Ready callbacks may replace a participant's account table. The live runtime
		-- remains a head even when no current offer still points to it.
		local copy = ns.copy
		local folder = copy and ns.folder or "ForeverCore"
		Add(folder, copy and copy.build or 0, store)
	end

	return heads
end

-- Reconcile the current heads into the one authoritative store and write a mirror into every participant. Every
-- participant gets the same table, so removing the addon that hosted the winning runtime leaves the state in each
-- survivor's own SavedVariables file.
---@param options? { preferredFolder?: string }
---@return table?
function ns.RefreshStore(options)
	local loader = rawget(_G, "ForeverCoreLoader")
	local selected = loader ~= nil and type(loader.Selected) == "function" and loader.Selected() or nil
	local heads = ns.StoreHeads()
	local result = ns.ReconcileStore(heads, {
		preferredFolder = options and options.preferredFolder or (selected and selected.folder),
	})
	if type(ns.Store()) ~= "table" then
		ns.store = result
	else
		ns.ApplyStore(ns.Store(), result)
	end
	for _, offer in ipairs(loader ~= nil and type(loader.Offers) == "function" and loader.Offers() or {}) do
		local db = rawget(_G, offer.globalName)
		if offer.folder == "ForeverCore" and offer.globalName == "ForeverCoreDB" then
			-- Standalone saves the store directly, including when an embedded copy wins.
			rawset(_G, offer.globalName, ns.Store())
		elseif type(db) == "table" then
			db[STORE_KEY] = ns.Store()
		end
	end
	if ns.TrackerHost ~= nil and type(ns.TrackerHost.MarkDirty) == "function" then
		pcall(ns.TrackerHost.MarkDirty, ns.TrackerHost)
	end
	return ns.Store()
end

-- One start body: adopt or accept the store, normalize it, attach core's journal and log, then run the one-time
-- tracker migration. Converted copies call it through ns.Start(); the unwrapped standalone path reaches it through its
-- ADDON_LOADED frame.
local function InitializeStore()
	-- Forever Leaderboards, peer stats and the Forever quest list are gone, and nothing migrates their saved data, so
	-- drop it: the leaderboard window's reach, and the list's switch, hint answer and per-character folds.
	local store = ns.Store()
	if type(store) == "table" then
		store.leaderboards = nil
		store.questList, store.questListHintDone, store.questListFold = nil, nil, nil
	end
	-- Building the host's table here is also the normalisation the host reads on every access.
	ns.TrackerHostSettings()
	if ns.AttachCoreDb then
		ns.AttachCoreDb()
	end
	if ns.MigrateTrackerSettings then
		ns.MigrateTrackerSettings()
	end
end

-- The loader calls this after the converted files have defined the runtime and before publishing the facade. An
-- elected copy reconciles the account mirrors it was offered, so registration order never decides which settings
-- survive. Only the standalone copy may adopt ForeverCoreDB, and only here.
function ns.Start()
	if ns.copy ~= nil then
		RunStartWork()
		if ns.mode == "standalone" then
			-- The converted standalone starts after election at PLAYER_LOGIN, with SavedVariables available.
			if type(ForeverCoreDB) ~= "table" then
				ForeverCoreDB = {}
			end
			ns.store = ForeverCoreDB
		elseif ns.mode == "elected" then
			ns.store = ns.RefreshStore({ preferredFolder = ns.folder })
		elseif type(ns.Store()) ~= "table" then
			error("ForeverCore elected Start requires a supplied ns.store table", 0)
		end
		InitializeStore()
		return
	end
	-- Transitional unwrapped standalone: Start always adopts the saved global as it stands now, replacing any
	-- placeholder a pre-saved-variables read might have left behind.
	if type(ForeverCoreDB) == "table" then
		ns.store = ForeverCoreDB
	else
		ForeverCoreDB = {}
		ns.store = ForeverCoreDB
	end
	InitializeStore()
end

-- The loader calls Login once at PLAYER_LOGIN after activation; the transitional standalone calls it from its own
-- frame. Reconcile after ready callbacks as well as Start: a consumer may replace its account table in its callback.
-- The live runtime remains a head and every current account table receives its mirror before login finishes.
function ns.Login()
	if ns.loginDone then
		return
	end
	ns.loginDone = true
	ns.RefreshStore()
	if ns.AttachCoreDb then
		ns.AttachCoreDb()
	end
	if ns.copy ~= nil and ns.DebugCaptureCatchUp then
		ns.DebugCaptureCatchUp()
	end
end

-- The one ADDON_LOADED handler for the transitional unwrapped standalone. Saved variables can be nil on a first
-- install, so the table and its tracker settings are made here, after the host and Expose have loaded but before any
-- consumer attaches. A converted copy gets ns.Start() from the loader instead and registers no self event.
local function InitializeSavedVariables()
	if type(ForeverCoreDB) ~= "table" then
		ForeverCoreDB = {}
	end
	ns.Start()
end

if ns.copy == nil and type(CreateFrame) == "function" then
	local frame = CreateFrame("Frame")
	frame:RegisterEvent("ADDON_LOADED")
	frame:RegisterEvent("PLAYER_LOGIN")
	frame:SetScript("OnEvent", function(_, event, addon)
		if event == "ADDON_LOADED" and addon == "ForeverCore" then
			InitializeSavedVariables()
		elseif event == "PLAYER_LOGIN" then
			ns.Login()
		end
	end)
end
