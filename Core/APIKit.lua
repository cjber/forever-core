-- The shared shape of an addon's own public API (docs/api-conventions.md): a hub that tells callers the frame after a
-- change, the not-ready answer a read gives while there is nothing to answer, the error answer a read gives for a wrong
-- argument, and the one list of every addon's published API. Each addon publishes its own table and builds its hub
-- here, so every Forever addon is subscribed to and discovered the same way.

local _, ns = ...

local APIKit = {}
-- Raised with each addition to the kit, so a caller can check a member before using it.
APIKit.minor = 3

-- A hub for `addonName`. `channels` maps a change name to a function returning a comparable key, and the optional
-- `ready` returns false while the addon is still working, so no key is read until it settles.
---@param addonName string
---@param channels ForeverCoreAPIChannels
---@param ready? fun(): boolean
---@return ForeverCoreAPIHub
function APIKit.Hub(addonName, channels, ready)
	addonName = tostring(addonName or "?")
	local names = {}
	for name in pairs(channels) do
		names[#names + 1] = name
	end
	table.sort(names)
	local safe = ns.SafeCallFor(addonName)
	-- What the last dispatch saw of each channel; false is the answer of a channel still waiting for its baseline.
	---@type table<string, string|number|boolean>
	local last = {}
	---@type { callback: fun(changes: ForeverCoreAPIChanges)? }[]
	local subscriptions = {}
	local pending = false

	-- The first subscriber takes what the channels read now as the baseline, so it hears only later changes. While the
	-- addon is still working there is no baseline yet: every channel stays false until it settles.
	local function Baseline()
		if ready ~= nil and not ready() then
			for _, name in ipairs(names) do
				last[name] = false
			end
			return
		end
		for _, name in ipairs(names) do
			last[name] = channels[name]() or false
		end
	end

	-- One burst's changes, to every subscriber there when the dispatch began (one added by a callback waits for the
	-- next burst), each with its own fresh table and each under the addon's SafeCall, so an error in one reaches the
	-- error handler and the report without stopping the others. While the addon is still working nothing is read or
	-- sent: the addon's own next Queue asks again.
	local function Dispatch()
		pending = false
		if not subscriptions[1] then
			return
		end
		if ready ~= nil and not ready() then
			return
		end
		---@type ForeverCoreAPIChanges?
		local changed
		for _, name in ipairs(names) do
			local key = channels[name]() or false
			if key ~= last[name] then
				changed = changed or {}
				changed[name] = true
				last[name] = key
			end
		end
		if not changed then
			return
		end
		local current = {}
		for index, subscription in ipairs(subscriptions) do
			current[index] = subscription
		end
		for _, subscription in ipairs(current) do
			if subscription.callback then
				local changes = {}
				for _, name in ipairs(names) do
					if changed[name] then
						changes[name] = true
					end
				end
				safe:SafeCall("API subscriber", subscription.callback, changes)
			end
		end
	end

	-- Nobody listening: no timer and no key read. Subscribe takes the baseline when the first one joins.
	local function Queue()
		if not pending and subscriptions[1] then
			pending = true
			C_Timer.After(0, function()
				safe:SafeCall("API subscribers", Dispatch)
			end)
		end
	end

	-- Calls `callback(changes)` the frame after what the channels read changes, at most once per burst (docs/api.md).
	-- Returns a function that unsubscribes, safe to call twice.
	---@param callback fun(changes: ForeverCoreAPIChanges)
	---@return fun()
	local function Subscribe(callback)
		if type(callback) ~= "function" then
			error(addonName .. ".API.Subscribe: callback must be a function", 2)
		end
		if not subscriptions[1] then
			Baseline()
		end
		---@type { callback: fun(changes: ForeverCoreAPIChanges)? }
		local subscription = { callback = callback }
		subscriptions[#subscriptions + 1] = subscription
		return function()
			subscription.callback = nil
			for index, other in ipairs(subscriptions) do
				if other == subscription then
					table.remove(subscriptions, index)
					return
				end
			end
		end
	end

	return { Subscribe = Subscribe, Queue = Queue }
end

-- Every read that has nothing to answer returns `nil, reason`, so a caller can tell "ask again later" from "there is
-- nothing to ask about". The reasons are "loading" (the data is not built yet), "disabled" (the player turned the
-- feature off), "none" (nothing to answer, for example no journey is chosen), "combat" (the game refuses it in combat,
-- so ask again after) and "unreachable" (no way there with what the character knows).
---@param reason ForeverCoreAPIReason
---@return nil, ForeverCoreAPIReason
function APIKit.NotReady(reason)
	return nil, reason
end

-- A read that refuses its argument returns `nil, "invalid"`. The argument is wrong, not missing: asking again with it
-- cannot help, so this is an error answer rather than a not-ready one. It is separate from the not-ready reasons so
-- NotReady keeps taking only those.
---@return nil, ForeverCoreAPIInvalid
function APIKit.Invalid()
	return nil, "invalid"
end

-- Every published API by addon name, the table the addon handed Publish.
---@type table<string, table>
local published = {}

-- An integer as this client's Lua has it: it has no math.type, so a number with no fractional part and no infinity.
---@param value any
---@return boolean
local function IsInteger(value)
	return type(value) == "number" and value == math.floor(value) and value > -math.huge and value < math.huge
end

-- An addon hands core its own public API table once at load, so a suite-wide reader can find it. Publishing the same
-- name again replaces the entry rather than adding a second one. A bad name or an api without an integer `version` is a
-- programming error, raised at the caller.
---@param addonName string
---@param api table
function APIKit.Publish(addonName, api)
	if type(addonName) ~= "string" or addonName == "" then
		error("ForeverCore.APIKit.Publish: addonName must be a non-empty string", 2)
	end
	if type(api) ~= "table" then
		error("ForeverCore.APIKit.Publish: api must be a table", 2)
	end
	if not IsInteger(api.version) then
		error("ForeverCore.APIKit.Publish: api.version must be an integer", 2)
	end
	published[addonName] = api
end

-- Every published addon, sorted by name, with `version` and `minor` read from its api table now (minor 0 when it has
-- none) and `api` the addon's own table, not a copy: it is the callable API. The list is fresh on every call, so a
-- caller may keep or change it.
---@return ForeverCoreAPIEntry[]
function APIKit.Addons()
	local names = {}
	for name in pairs(published) do
		names[#names + 1] = name
	end
	table.sort(names)
	---@type ForeverCoreAPIEntry[]
	local entries = {}
	for index, name in ipairs(names) do
		local api = published[name]
		entries[index] = { name = name, version = api.version, minor = api.minor or 0, api = api }
	end
	return entries
end

-- Every addon's world map markers reader by addon name (docs/api-conventions.md, World map markers).
---@type table<string, fun(map: table): table>
local markerReaders = {}

-- An addon registers the function that lists its own shown markers on a map, once at load. Registering the same name
-- again replaces it. `read(map)` takes the map frame and returns `{ x, y, kind }` entries, x and y being fractions of
-- `map:GetMapID()`.
---@param addonName string
---@param read fun(map: table): table
function APIKit.RegisterMapMarkers(addonName, read)
	if type(addonName) ~= "string" or addonName == "" then
		error("ForeverCore.APIKit.RegisterMapMarkers: addonName must be a non-empty string", 2)
	end
	if type(read) ~= "function" then
		error("ForeverCore.APIKit.RegisterMapMarkers: read must be a function", 2)
	end
	markerReaders[addonName] = read
end

-- The shown markers of every registered addon on `map`, a fresh list of fresh `{ addon, x, y, kind }` entries, without
-- the addon named `except` (a reader leaves out its own). A reader that errors, or an entry with no numeric place, is
-- left out rather than failing the caller.
-- A reader that asks for the others' markers while it is being read gets none, so two readers cannot call each other
-- without end.
local reading = false

---@param map table
---@param except? string
---@return ForeverCoreMapMarker[]
function APIKit.MapMarkers(map, except)
	if reading then
		return {}
	end
	reading = true
	local names = {}
	for name in pairs(markerReaders) do
		if name ~= except then
			names[#names + 1] = name
		end
	end
	table.sort(names)
	---@type ForeverCoreMapMarker[]
	local all = {}
	for _, name in ipairs(names) do
		local ok, list = pcall(markerReaders[name], map)
		if ok and type(list) == "table" then
			for _, marker in ipairs(list) do
				if type(marker) == "table" and type(marker.x) == "number" and type(marker.y) == "number" then
					all[#all + 1] = { addon = name, x = marker.x, y = marker.y, kind = marker.kind }
				end
			end
		end
	end
	reading = false
	return all
end

ns.APIKit = APIKit
