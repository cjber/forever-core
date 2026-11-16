-- The runtime store contract: every available mirror is reconciled in one pass without dropping a changed value. A
-- stale unchanged mirror is proven stale by ancestry; an edited stale mirror, a copied WTF branch and a legacy edit
-- stay concurrent and keep both values in _store.conflicts. Applying the result deletes absent keys without replacing
-- the journal/log/settings tables the runtime already holds.
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end
local function equal(actual, expected, label)
	checks = checks + 1
	if actual ~= expected then
		error(("%s: expected %s, got %s"):format(label, tostring(expected), tostring(actual)), 2)
	end
end

local env = setmetatable({}, { __index = _G })
env._G = env
local ns = {}
setfenv(assert(loadfile("Core.lua")), env)("ForeverCore", ns)

local nextNode = 0
local function Node()
	nextNode = nextNode + 1
	return "n" .. nextNode
end

local function Head(folder, build, data)
	return { folder = folder, build = build, data = data }
end

local function Marker(node, ancestors, snapshot)
	return {
		schema = 1,
		node = node,
		parents = { node },
		ancestors = ancestors or { node },
		snapshot = snapshot,
	}
end

local function Conflicts(report, path)
	for _, conflict in ipairs(report.conflicts or {}) do
		if conflict.path == path then
			return conflict
		end
	end
end

local function Values(conflict)
	local values = {}
	for _, value in ipairs(conflict and conflict.values or {}) do
		values[#values + 1] = value.present and tostring(value.value) or "<absent>"
	end
	table.sort(values)
	return table.concat(values, ",")
end

-- One-sided changes on separate leaves survive together; neither becomes a conflict.
local merged = ns.ReconcileStore({
	Head("A", 10, {
		trackerHost = { scale = 1.5 },
		_store = Marker("a1", nil, { trackerHost = { scale = 1.5 } }),
	}),
	Head("B", 10, {
		trackerHost = { locked = true },
		_store = Marker("b1", nil, { trackerHost = { locked = true } }),
	}),
}, { NextNode = Node })
equal(merged.trackerHost.scale, 1.5, "A's scale survives")
equal(merged.trackerHost.locked, true, "B's lock survives")
equal(#(merged._store.conflicts or {}), 0, "separate leaves are not a conflict")

-- The same leaf changed differently keeps both candidates; the preferred copy supplies the live value only.
local conflicting, conflictReport = ns.ReconcileStore({
	Head("A", 10, {
		trackerHost = { scale = 1.5 },
		_store = Marker("a2", nil, { trackerHost = { scale = 1.5 } }),
	}),
	Head("B", 10, {
		trackerHost = { scale = 2 },
		_store = Marker("b2", nil, { trackerHost = { scale = 2 } }),
	}),
}, { NextNode = Node, preferredFolder = "B" })
equal(conflicting.trackerHost.scale, 2, "the preferred copy supplies the live value")
local scaleConflict = Conflicts(conflictReport, "trackerHost.scale")
check(scaleConflict ~= nil, "the differing leaf is recorded as one conflict")
equal(Values(scaleConflict), "1.5,2", "both values are retained")

-- An unchanged old mirror is a proven ancestor: it is dropped without a conflict and its stale value never returns.
local ancestor = ns.ReconcileStore({
	Head("A", 10, {
		trackerHost = { scale = 2 },
		_store = Marker("a3", { "old", "a3" }, { trackerHost = { scale = 2 } }),
	}),
	Head("B", 10, {
		trackerHost = { scale = 1 },
		_store = Marker("old", { "old" }, { trackerHost = { scale = 1 } }),
	}),
}, { NextNode = Node })
equal(ancestor.trackerHost.scale, 2, "the current value stays")
equal(#(ancestor._store.conflicts or {}), 0, "an unchanged ancestor mirror creates no conflict")

-- The same old mirror edited offline is a new child of that old node, so it stays concurrent and is retained.
local edited, editedReport = ns.ReconcileStore({
	Head("A", 10, {
		trackerHost = { scale = 2 },
		_store = Marker("a4", { "old2", "a4" }, { trackerHost = { scale = 2 } }),
	}),
	Head("B", 10, {
		trackerHost = { scale = 1.3 },
		_store = Marker("old2", { "old2" }, { trackerHost = { scale = 1 } }),
	}),
}, { NextNode = Node })
local editedConflict = Conflicts(editedReport, "trackerHost.scale")
equal(edited.trackerHost.scale, 2, "the unchanged current head still supplies the live value")
equal(Values(editedConflict), "1.3,2", "the offline edit and the current value are both kept")

-- A second legacy edit has no reused external marker: the changed snapshot promotes a fresh node each time.
local legacy1 = ns.ReconcileStore({
	Head("ForeverCore", 10, {
		trackerHost = { scale = 4 },
		_store = Marker("legacy1", { "legacy1" }, { trackerHost = { scale = 3 } }),
	}),
}, { NextNode = Node })
equal(legacy1.trackerHost.scale, 4, "the legacy edit is the live value")
equal(#(legacy1._store.conflicts or {}), 0, "one changed mirror is still one state")
local legacy2 = ns.ReconcileStore({
	Head("ForeverCore", 10, {
		trackerHost = { scale = 5 },
		_store = Marker("legacy2", { "legacy1", "legacy2" }, { trackerHost = { scale = 4 } }),
	}),
}, { NextNode = Node })
equal(legacy2.trackerHost.scale, 5, "a later legacy edit is not dominated by an older marker")

-- The same unchanged node offered by several addons is one logical head, not a spurious conflict.
local sharedResult = ns.ReconcileStore({
	Head("A", 10, {
		trackerHost = { scale = 1.5 },
		_store = Marker("shared", nil, { trackerHost = { scale = 1.5 } }),
	}),
	Head("B", 10, {
		trackerHost = { scale = 1.5 },
		_store = Marker("shared", nil, { trackerHost = { scale = 1.5 } }),
	}),
}, { NextNode = Node })
equal(#(sharedResult._store.conflicts or {}), 0, "a shared unchanged mirror is not a conflict")
equal(sharedResult.trackerHost.scale, 1.5, "and keeps the shared value")

-- Logs merge as a multiset: repeated identical lines survive, while a shared ancestor is not doubled.
local logResult = ns.ReconcileStore({
	Head("A", 10, {
		log = { lines = {
			"2026-01-01 00:00:00 +1.0s same",
			"2026-01-01 00:00:00 +1.0s same",
		} },
		_store = Marker("logA", nil, {}),
	}),
	Head("B", 10, {
		log = { lines = {
			"2026-01-01 00:00:00 +1.0s same",
			"2026-01-01 00:00:00 +2.0s later",
		} },
		_store = Marker("logB", nil, {}),
	}),
}, { NextNode = Node })
local same, later = 0, 0
for _, line in ipairs(logResult.log.lines) do
	if line:find("same", 1, true) then
		same = same + 1
	elseif line:find("later", 1, true) then
		later = later + 1
	end
end
equal(same, 2, "two identical lines from one head are kept twice, not summed with the shared ancestor")
equal(later, 1, "the one-sided line survives")

-- A journal signature merges once: max count, earliest firstSeen, latest lastSeen, never the sum of a shared ancestor.
local journalResult = ns.ReconcileStore({
	Head("A", 10, {
		errors = { { signature = "s", kind = "error", message = "x", count = 2, firstSeen = 1, lastSeen = 5 } },
		_store = Marker("errA", nil, {}),
	}),
	Head("B", 10, {
		errors = {
			{ signature = "s", kind = "error", message = "x", count = 3, firstSeen = 1, lastSeen = 7 },
			{ signature = "t", kind = "error", message = "y", count = 1, firstSeen = 2, lastSeen = 3 },
		},
		_store = Marker("errB", nil, {}),
	}),
}, { NextNode = Node })
equal(#journalResult.errors, 2, "both signatures survive")
for _, entry in ipairs(journalResult.errors) do
	if entry.signature == "s" then
		equal(entry.count, 3, "the count is a lower bound, not a double count")
		equal(entry.firstSeen, 1, "the first sighting is the earliest")
		equal(entry.lastSeen, 7, "the last sighting is the latest")
	end
end

-- Saved quest folds use numeric quest IDs and character/realm keys, not dotted paths.
local keyed = ns.ReconcileStore({
	Head("A", 10, {
		questListFold = {
			["Player-Realm.With.Dot"] = { quests = { [123] = true, ["123"] = false }, zones = { ["A.B"] = true } },
		},
		["literal.key"] = "kept",
		["~2:123"] = "literal prefix",
	}),
}, { NextNode = Node })
local character = keyed.questListFold["Player-Realm.With.Dot"]
check(character ~= nil, "realm names containing periods remain one key")
equal(character.quests[123], true, "numeric quest IDs stay numeric")
equal(character.quests["123"], false, "string and numeric keys remain distinct")
equal(character.zones["A.B"], true, "zone names containing periods stay intact")
equal(keyed["literal.key"], "kept", "literal dotted keys survive")
equal(keyed["~2:123"], "literal prefix", "escaped keys do not collide with numeric encoding")

-- A scalar/table disagreement is one subtree conflict, not overlapping writes to parent/child paths.
local shaped, shapeReport = ns.ReconcileStore({
	Head("A", 10, { choice = false }),
	Head("B", 10, { choice = { nested = true } }),
}, { NextNode = Node, preferredFolder = "A" })
equal(shaped.choice, false, "the preferred scalar is not overwritten by a child path")
equal(#shapeReport.conflicts, 1, "the subtree disagreement is recorded once")
equal(shapeReport.conflicts[1].values[1].value, false, "false is retained in conflict provenance")

-- History is not covered by the settings snapshot: equal nodes can have different logs/errors.
local history = ns.ReconcileStore({
	Head("A", 10, {
		_store = Marker("same-history", nil, {}),
		errors = { { signature = "A", message = "A" } },
		log = { lines = { "A" } },
	}),
	Head("B", 10, {
		_store = Marker("same-history", nil, {}),
		errors = { { signature = "B", message = "B" } },
		log = { lines = { "B" }, pinned = true },
	}),
}, { NextNode = Node })
equal(#history.errors, 2, "equal settings nodes retain both journals")
equal(#history.log.lines, 2, "equal settings nodes retain both logs")
equal(history.log.pinned, true, "a history pin from either mirror survives")

-- Applying deletes keys absent from the result, while keeping the tables the runtime already attached.
local target = {
	trackerHost = { scale = 1, x = 5 },
	errors = {},
	log = { lines = {}, pinned = false },
	extra = true,
}
local trackerHost, errors, log, lines = target.trackerHost, target.errors, target.log, target.log.lines
local source = {
	trackerHost = { scale = 2 },
	errors = { { signature = "s", message = "kept", count = 1 } },
	log = { lines = { "line" }, pinned = true },
	_store = { schema = 1, node = "new" },
}
ns.ApplyStore(target, source)
check(target.trackerHost == trackerHost, "the tracker settings table keeps its identity")
equal(target.trackerHost.scale, 2, "and its new value")
equal(target.trackerHost.x, nil, "a key absent from the result is deleted")
equal(target.extra, nil, "an unknown key absent from the result is deleted")
check(target.errors == errors and target.errors[1].message == "kept", "the journal table keeps its identity")
check(target.log == log and target.log.lines == lines, "the log tables keep their identities")
equal(target.log.pinned, true, "the pin follows the result")

-- Every participant receives the reconciled table, so removing the addon that hosted the winner leaves a surviving
-- copy of the state. A second session with only the survivor still reads the same value.
env.ForeverCoreLoader = {
	Offers = function()
		return env._offers
	end,
	Candidates = function()
		return {
			{ folder = "AddonA", build = 10 },
			{ folder = "AddonB", build = 10 },
		}
	end,
	Selected = function()
		return { folder = "AddonA" }
	end,
}
env._offers = {
	{ folder = "AddonA", globalName = "AddonADB" },
	{ folder = "AddonB", globalName = "AddonBDB" },
}
env.AddonADB = {
	ForeverCoreStore = {
		trackerHost = { scale = 1.5 },
		_store = Marker("liveA", nil, { trackerHost = { scale = 1.5 } }),
	},
}
env.AddonBDB = {
	ForeverCoreStore = {
		trackerHost = { scale = 1 },
		_store = Marker("liveB", nil, { trackerHost = { scale = 1 } }),
	},
}
ns.copy = {}
ns.mode = "elected"
ns.folder = "AddonA"
ns.store = nil
ns.Start()
local store = ns.Store()
check(store ~= nil, "the elected runtime reconciles its offered stores")
check(env.AddonADB.ForeverCoreStore == store, "the winner's mirror is the canonical table")
check(env.AddonBDB.ForeverCoreStore == store, "the other participant receives the same table")
equal(store.trackerHost.scale, 1.5, "the preferred copy's live value is in both mirrors")

-- Remove AddonA: a later session runs only AddonB and still finds the reconciled value there.
env._offers = { { folder = "AddonB", globalName = "AddonBDB" } }
env.ForeverCoreLoader.Selected = function()
	return { folder = "AddonB" }
end
ns.store = nil
ns.storeReconciled = nil
ns.loginDone = nil
ns.mode = "elected"
ns.folder = "AddonB"
ns.Start()
equal(ns.Store().trackerHost.scale, 1.5, "the surviving addon still supplies the state after the winner is removed")

-- An embedded winner must also persist through the standalone account global. Only offered
-- globals belong to this runtime: an embedded-only installation must not create ForeverCoreDB.
do
	local function SavedCopy(value)
		if type(value) ~= "table" then
			return value
		end
		local copy = {}
		for key, item in pairs(value) do
			copy[key] = SavedCopy(item)
		end
		return copy
	end
	local function Session(saved, standaloneOnly)
		local runtime = setmetatable({}, { __index = _G })
		runtime._G = runtime
		runtime.ForeverCoreDB = SavedCopy(saved)
		runtime.AddonADB = { ownSetting = true, ForeverCoreStore = { trackerHost = { scale = 1.37 } } }
		local offers = { { folder = "ForeverCore", globalName = "ForeverCoreDB" } }
		if not standaloneOnly then
			offers[#offers + 1] = { folder = "AddonA", globalName = "AddonADB" }
		end
		runtime.ForeverCoreLoader = {
			Offers = function()
				return offers
			end,
			Selected = function()
				return { folder = standaloneOnly and "ForeverCore" or "AddonA" }
			end,
		}
		local context = { copy = {}, mode = standaloneOnly and "standalone" or "elected", folder = "AddonA" }
		setfenv(assert(loadfile("Core.lua")), runtime)("ForeverCore", context)
		context.Start()
		context.Login()
		return runtime, context, offers
	end
	local runtime, context = Session({ trackerHost = { scale = 1 } })
	check(runtime.ForeverCoreDB == context.Store(), "standalone global aliases the elected live store")
	check(runtime.AddonADB.ForeverCoreStore == context.Store(), "consumer mirror shares standalone live state")
	equal(runtime.AddonADB.ownSetting, true, "consumer settings outside the mirror survive")
	context.Store().trackerHost.scale = 1.37
	local settings = context.Store().trackerHost
	local journal, runtimeLog = context.Store().errors, context.Store().log
	context.RefreshStore()
	check(context.Store().trackerHost == settings, "refresh preserves live settings identity")
	check(
		context.Store().errors == journal and context.Store().log == runtimeLog,
		"refresh preserves attached history identity"
	)
	local _, survivor = Session(runtime.ForeverCoreDB, true)
	equal(survivor.Store().trackerHost.scale, 1.37, "standalone alone retains the embedded winner's latest setting")
	local firstInstall, fresh = Session(nil)
	check(firstInstall.ForeverCoreDB == fresh.Store(), "offered first-install standalone global receives live store")
	local embeddedOnly, embedded, offers = Session(nil)
	-- Simulate an installation without a standalone offer, then reconcile again.
	table.remove(offers, 1)
	embeddedOnly.ForeverCoreDB = nil
	embedded.RefreshStore()
	equal(embeddedOnly.ForeverCoreDB, nil, "no standalone offer means no standalone global is created")
end

-- Exercise each regression independently so one failure cannot hide another producer defect.
local regressions = {
	historicalDeletion = function()
		local prior = ns.ReconcileStore({ Head("A", 10, { x = 1 }), Head("B", 10, { x = 2 }) }, { NextNode = Node })
		prior.x = nil
		local current, report = ns.ReconcileStore({ Head("A", 10, prior) }, { NextNode = Node })
		equal(current.x, nil, "historical candidates cannot resurrect a deleted setting")
		local repeated = ns.ReconcileStore({ Head("A", 10, current) }, { NextNode = Node })
		equal(repeated.x, nil, "a saved deletion stays absent on another reconciliation")
		check(Values(Conflicts(report, "x")):find("<absent>", 1, true), "deletion remains a retained candidate")
	end,
	historicalSubtree = function()
		local prior = ns.ReconcileStore(
			{ Head("A", 10, { m = { x = { y = 1 } } }), Head("B", 10, { m = { x = { y = 2 } } }) },
			{ NextNode = Node }
		)
		prior.m.x = false
		local current, report = ns.ReconcileStore({ Head("A", 10, prior) }, { NextNode = Node })
		equal(current.m.x, false, "historical child cannot overwrite a live scalar")
		equal(#report.conflicts, 1, "historical subtree arbitrates once")
		local conflict = Conflicts(report, "m.x")
		check(conflict ~= nil, "historical values move to the competing parent")
		local retained = {}
		for _, value in ipairs(conflict.values) do
			if type(value.value) == "table" then
				retained[value.value.y] = true
			end
		end
		check(retained[1] and retained[2], "both historical subtrees survive arbitration")
	end,
	nestedReserved = function()
		local nestedTarget = {
			settings = {
				errors = { old = true },
				log = { old = true },
				_store = { old = true },
				ForeverCoreStore = { old = true },
			},
		}
		local held = nestedTarget.settings.errors
		local nestedSource = { settings = { errors = { fresh = true }, log = false, _store = 7 } }
		ns.ApplyStore(nestedTarget, nestedSource)
		check(nestedTarget.settings.errors == held, "nested settings keep table identity")
		equal(held.old, nil, "nested errors removes absent data")
		equal(held.fresh, true, "nested errors accepts new data")
		equal(nestedTarget.settings.log, false, "nested log is ordinary data")
		equal(nestedTarget.settings._store, 7, "nested metadata name is ordinary data")
		equal(nestedTarget.settings.ForeverCoreStore, nil, "nested store name can be deleted")
	end,
	fractionalKeys = function()
		local current = ns.ReconcileStore({
			Head(
				"A",
				10,
				{ keys = { [1.5] = "fraction", [-2.75] = false, ["~2:1~15"] = "literal", ["1.5"] = "string" } }
			),
		}, { NextNode = Node })
		equal(current.keys[1.5], "fraction", "fractional numeric key round trips")
		equal(current.keys[-2.75], false, "negative fractional numeric key round trips")
		equal(current.keys["~2:1~15"], "literal", "numeric escape syntax does not collide with strings")
		equal(current.keys["1.5"], "string", "fractional string key stays distinct")
		local again = ns.ReconcileStore({
			Head("A", 10, current),
			Head("B", 10, { keys = { [1.5] = "alternative" } }),
		}, { NextNode = Node, preferredFolder = "A" })
		equal(again.keys[1.5], "fraction", "fractional key survives conflict arbitration")
		local saved = ns.ReconcileStore({ Head("A", 10, again) }, { NextNode = Node })
		equal(saved.keys[1.5], "fraction", "encoded numeric conflict survives another reconciliation")
	end,
}
local failures = {}
for _, name in ipairs({ "historicalDeletion", "historicalSubtree", "nestedReserved", "fractionalKeys" }) do
	local ok, message = pcall(regressions[name])
	if not ok then
		failures[#failures + 1] = name .. ": " .. tostring(message)
	end
end
assert(#failures == 0, table.concat(failures, "\n"))

print(("store_contract_spec: %d checks passed"):format(checks))
