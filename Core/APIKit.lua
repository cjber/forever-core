-- The shared shape of an addon's own public API (docs/api-conventions.md): a hub that tells callers the frame after a
-- change, and the not-ready answer a read gives while there is nothing to answer. Each addon publishes its own table
-- and builds its hub here, so every Forever addon is subscribed to the same way.

local _, ns = ...

local APIKit = {}
-- Raised with each addition to the kit, so a caller can check a member before using it.
APIKit.minor = 1

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
-- feature off) and "none" (nothing to answer, for example no journey is chosen).
---@param reason ForeverCoreAPIReason
---@return nil, ForeverCoreAPIReason
function APIKit.NotReady(reason)
	return nil, reason
end

ns.APIKit = APIKit
