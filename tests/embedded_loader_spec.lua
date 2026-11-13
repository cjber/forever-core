-- Core/Loader.lua, the one registry every embedded ForeverCore copy shares. The spec registers synthetic copies the
-- way a consumer's Begin/End pair will: no chunk runs at registration, the highest sealed build wins once, only the
-- winner boots, the facade and its namespace belong to the winner, and a late or duplicate copy is rejected without
-- disturbing the runtime that is already up.
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

-- The release build formula: major * 1e6 + minor * 1e3 + patch.
local function build(major, minor, patch)
	return major * 1000000 + minor * 1000 + (patch or 0)
end

-- A fresh Lua environment is one client session: one loading frame list, one loader global and one facade. Loading
-- the loader file twice is what two embedded copies do when they are the first and the second copy in the same
-- session; the second must reuse the first copy's registry.
local function newSession()
	local frames = {}
	local env = setmetatable({}, { __index = _G })
	env._G = env
	env.CreateFrame = function()
		local frame = { events = {}, scripts = {} }
		function frame:RegisterEvent(event)
			self.events[event] = true
		end
		function frame:UnregisterEvent(event)
			self.events[event] = nil
		end
		function frame:SetScript(name, callback)
			self.scripts[name] = callback
		end
		frames[#frames + 1] = frame
		return frame
	end
	local function load()
		local chunk = assert(loadfile("Core/Loader.lua"), "Core/Loader.lua")
		setfenv(chunk, env)
		chunk("ForeverCore", {})
	end
	load()
	local session = { env = env, frames = frames, boots = {}, identities = {}, starts = {}, logins = {} }
	session.loader = env.ForeverCoreLoader
	function session.ReloadLoader()
		load()
	end
	function session.Fire(event, addon)
		for _, frame in ipairs(frames) do
			if frame.events[event] and frame.scripts.OnEvent then
				frame.scripts.OnEvent(frame, event, addon)
			end
		end
	end
	-- A copy in the shape Begin.lua + wrapped files + End.lua will produce. Each wrapped file is called with the fixed
	-- identity "ForeverCore" and the namespace, exactly like the standalone main chunk. `opts.chunk` runs inside the
	-- winner's namespace before Start and publication, so a test can make a candidate fail or record what it saw.
	function session:Candidate(folder, version, opts)
		opts = opts or {}
		local copy = self.loader.Begin(folder, version, opts.digest)
		copy:Define(function(...)
			local identity, ns = ...
			self.identities[folder] = identity
			self.boots[#self.boots + 1] = folder
			local core = { API = 1, Register = function() end, name = "ForeverCore" }
			ns.Start = function()
				self.starts[#self.starts + 1] = folder
			end
			ns.Login = function()
				self.logins[#self.logins + 1] = folder
			end
			if opts.chunk then
				opts.chunk(ns, core, self, identity)
			end
			ns.ForeverCore = core
		end)
		if opts.seal ~= false then
			local ok, reason = copy:Seal()
			if opts.expectSeal ~= false then
				check(ok, "candidate " .. folder .. " seals: " .. tostring(reason))
			end
		end
		return copy
	end
	return session
end

-- One registry, one loading frame, however many copies ask for it.
local shared = newSession()
shared.ReloadLoader()
shared.ReloadLoader()
shared:Candidate("AddonOne", build(1, 6, 0))
shared:Candidate("AddonTwo", build(1, 7, 0))
equal(#shared.frames, 1, "the first Begin creates the one PLAYER_LOGIN frame every copy shares")

-- Every order of minor 5, 7 and 6 elects 7 before any chunk runs.
for _, order in ipairs({
	{ 5, 7, 6 },
	{ 5, 6, 7 },
	{ 6, 5, 7 },
	{ 6, 7, 5 },
	{ 7, 5, 6 },
	{ 7, 6, 5 },
}) do
	local session = newSession()
	local label = order[1] .. "/" .. order[2] .. "/" .. order[3]
	for _, minor in ipairs(order) do
		session:Candidate("Addon" .. minor, build(1, minor, 0))
	end
	equal(#session.boots, 0, "order " .. label .. " registers without running a chunk")
	session.Fire("PLAYER_LOGIN")
	local selected = session.loader.Selected()
	check(selected ~= nil, "order " .. label .. " elects a copy")
	equal(selected and selected.mode, "elected", "order " .. label .. " is an election")
	equal(selected and selected.folder, "Addon7", "order " .. label .. " elects minor 7")
	equal(selected and selected.build, build(1, 7, 0), "order " .. label .. " records the winning build")
	equal(
		selected and selected.root,
		"Interface\\AddOns\\Addon7\\Libs\\ForeverCore",
		"order " .. label .. " keeps the winner's media root"
	)
	equal(#session.boots, 1, "order " .. label .. " boots exactly one copy")
	equal(session.boots[1], "Addon7", "order " .. label .. " boots only the winner")
	local namespace = session.loader.Namespace()
	check(namespace ~= nil, "order " .. label .. " keeps the winner's namespace")
	equal(namespace and namespace.folder, "Addon7", "order " .. label .. " namespace belongs to the winner")
	equal(namespace and namespace.root, selected.root, "order " .. label .. " namespace carries the media root")
	check(
		namespace and namespace.ForeverCore == session.env.ForeverCore,
		"order " .. label .. " publishes the winner's facade once"
	)
end

-- The upgrade and uninstall path: removing the winner leaves the next sealed copy to run next session.
local function elect(folders)
	local session = newSession()
	for _, entry in ipairs(folders) do
		session:Candidate(entry[1], build(entry[2], entry[3], 0))
	end
	session.Fire("PLAYER_LOGIN")
	return session, session.loader.Selected()
end
local session, selected = elect({ { "AddonA", 1, 5 }, { "AddonB", 1, 6 }, { "AddonC", 1, 7 } })
equal(selected and selected.folder, "AddonC", "the newest copy wins with three installed")
equal(#session.boots, 1, "one runtime in the three-copy session")
session, selected = elect({ { "AddonA", 1, 5 }, { "AddonB", 1, 6 } })
equal(selected and selected.folder, "AddonB", "removing the winner elects the surviving newest copy")
equal(#session.boots, 1, "one runtime after the winner is removed")
session, selected = elect({ { "AddonA", 1, 5 } })
equal(selected and selected.folder, "AddonA", "removing another copy leaves the last one working")
equal(#session.boots, 1, "one runtime after two are removed")

-- One boot: a second PLAYER_LOGIN and a second Activate never run another chunk or replace the facade.
session = newSession()
session:Candidate("AddonA", build(1, 7, 0))
session.Fire("PLAYER_LOGIN")
local facade = session.env.ForeverCore
session.Fire("PLAYER_LOGIN")
session.loader.Activate()
equal(#session.boots, 1, "activation is idempotent")
check(rawequal(session.env.ForeverCore, facade), "the stable facade is the one table throughout the session")
check(rawequal(session.loader.Facade(), facade), "the loader keeps the facade it published")

-- A copy that begins after activation is late: it never seals into the election or runs a chunk.
session = newSession()
session:Candidate("AddonA", build(1, 6, 0))
session.Fire("PLAYER_LOGIN")
local late = session.loader.Begin("LateAddon", build(1, 9, 0))
equal(late.rejected, "late", "a copy beginning after activation is rejected")
local lateSeal, lateReason = late:Seal()
equal(lateSeal, false, "a late copy cannot seal")
equal(lateReason, "late", "and says why")
equal(#session.boots, 1, "a late copy never runs")
equal(session.loader.Selected().folder, "AddonA", "a late copy never replaces the selected runtime")
local rejection = session.loader.Rejections()[#session.loader.Rejections()]
equal(rejection.folder, "LateAddon", "the late copy is in the rejection log")
equal(rejection.reason, "late", "with the late reason")

-- A duplicate folder is rejected before it can compete, and a copy cannot seal twice or seal empty.
session = newSession()
local first = session.loader.Begin("AddonA", build(1, 7, 0))
first:Define(function(_, ns)
	ns.Start = function() end
	ns.Login = function() end
	ns.ForeverCore = { API = 1, Register = function() end, name = "ForeverCore" }
end)
check(first:Seal(), "the first copy seals")
local second = session.loader.Begin("AddonA", build(1, 9, 0))
equal(second.rejected, "duplicate", "a second copy of one folder is rejected")
local secondSeal, secondReason = second:Seal()
equal(secondSeal, false, "the duplicate cannot seal")
equal(secondReason, "duplicate", "and says it is a duplicate")
local again, againReason = first:Seal()
equal(again, false, "a copy cannot seal twice")
equal(againReason, "sealed", "and says it is already sealed")
local empty = session.loader.Begin("EmptyAddon", build(1, 9, 0))
local emptySeal, emptyReason = empty:Seal()
equal(emptySeal, false, "an empty copy cannot seal")
equal(emptyReason, "empty", "a truncated package is detected exactly")
session.Fire("PLAYER_LOGIN")
equal(session.loader.Selected().folder, "AddonA", "neither a duplicate nor an empty copy takes the election")

-- An incompatible build is rejected without taking the loader down.
session = newSession()
local zero = session.loader.Begin("Zero", 0)
equal(zero.rejected, "build", "build 0 is rejected")
local fractional = session.loader.Begin("Fractional", 1005.5)
equal(fractional.rejected, "build", "a fractional build is rejected")
local text = session.loader.Begin("Text", "1.7.0")
equal(text.rejected, "build", "a string build is rejected")
session:Candidate("Good", build(1, 6, 0))
session.Fire("PLAYER_LOGIN")
equal(session.loader.Selected().folder, "Good", "a valid copy still wins beside rejected builds")

-- Same highest build with different content digests is a real conflict: the loader refuses to choose by folder name
-- or load order and boots neither copy. Every candidate at the tied build is diagnosed, including two that share one
-- digest, in either registration order.
for _, order in ipairs({
	{ { "AddonA", "aaaa" }, { "AddonB", "aaaa" }, { "AddonC", "bbbb" } },
	{ { "AddonC", "bbbb" }, { "AddonB", "aaaa" }, { "AddonA", "aaaa" } },
}) do
	local conflicting = newSession()
	local label = order[1][1] .. "/" .. order[2][1] .. "/" .. order[3][1]
	for _, entry in ipairs(order) do
		conflicting:Candidate(entry[1], build(1, 9, 0), { digest = entry[2] })
	end
	conflicting.Fire("PLAYER_LOGIN")
	check(conflicting.loader.Selected() == nil, label .. " conflicting digests select nothing")
	equal(#conflicting.boots, 0, label .. " boots no copy")
	check(
		conflicting.loader.Error():find("conflicting", 1, true) ~= nil,
		label .. " records the conflict as the failure"
	)
	local conflictReasons = {}
	for _, entry in ipairs(conflicting.loader.Rejections()) do
		conflictReasons[entry.folder .. ":" .. entry.reason] = true
	end
	check(conflictReasons["AddonA:tie-conflict"], label .. " diagnoses the first A")
	check(conflictReasons["AddonB:tie-conflict"], label .. " diagnoses the repeated A")
	check(conflictReasons["AddonC:tie-conflict"], label .. " diagnoses B")
	check(conflicting.env.ForeverCore == nil, label .. " publishes no facade")
end

-- The same build and digest is the same package, so registration order is stable and harmless.
session = newSession()
session:Candidate("AddonB", build(1, 9, 0), { digest = "same" })
session:Candidate("AddonA", build(1, 9, 0), { digest = "same" })
session.Fire("PLAYER_LOGIN")
equal(
	session.loader.Selected() and session.loader.Selected().folder,
	"AddonB",
	"identical digests keep the first registration"
)
equal(#session.boots, 1, "identical digests boot once")

-- A lower build never takes part in a conflict.
session = newSession()
session:Candidate("AddonA", build(1, 9, 0), { digest = "new" })
session:Candidate("AddonB", build(1, 8, 0), { digest = "old" })
session.Fire("PLAYER_LOGIN")
equal(
	session.loader.Selected() and session.loader.Selected().folder,
	"AddonA",
	"the highest build wins across different digests"
)
equal(#session.boots, 1, "and boots once")

-- A digest is an opaque non-empty string when present.
session = newSession()
local badDigest = session.loader.Begin("BadDigest", build(1, 7, 0), 17)
equal(badDigest.rejected, "digest", "a non-string digest is rejected")
local emptyDigest = session.loader.Begin("EmptyDigest", build(1, 7, 0), "")
equal(emptyDigest.rejected, "digest", "an empty digest is rejected")
session:Candidate("GoodDigest", build(1, 7, 0), { digest = "abc" })
session.Fire("PLAYER_LOGIN")
equal(session.loader.Selected() and session.loader.Selected().folder, "GoodDigest", "a valid digest still competes")

-- The runtime contract: every wrapped file gets the fixed "ForeverCore" identity and the namespace, the namespace
-- carries its mode, Start runs before publication, and Login runs exactly once at PLAYER_LOGIN.
session = newSession()
local runtime = {}
session:Candidate("ConsumerA", build(1, 9, 0), {
	chunk = function(ns, _, _, identity)
		runtime.identity = identity
		runtime.namespace = ns
		runtime.mode = ns.mode
		ns.Start = function()
			runtime.started = (runtime.started or 0) + 1
			runtime.globalAtStart = session.env.ForeverCore
			runtime.facadeAtStart = ns.ForeverCore
			runtime.modeAtStart = ns.mode
		end
		ns.Login = function()
			runtime.logged = (runtime.logged or 0) + 1
			runtime.modeAtLogin = ns.mode
		end
	end,
})
session.Fire("PLAYER_LOGIN")
equal(runtime.identity, "ForeverCore", "a wrapped file sees the fixed identity vararg")
equal(session.identities.ConsumerA, "ForeverCore", "even though the consumer folder differs")
check(rawequal(runtime.namespace, session.loader.Namespace()), "and the winner's namespace")
equal(runtime.namespace and runtime.namespace.folder, "ConsumerA", "the namespace carries the copy folder")
check(runtime.namespace and runtime.namespace.copy ~= nil, "and the copy handle")
equal(runtime.mode, "elected", "the namespace carries its mode before the first chunk")
equal(runtime.started, 1, "Start runs once")
check(runtime.globalAtStart == nil, "Start runs before the global facade is published")
check(runtime.facadeAtStart ~= nil, "after the chunks built the namespace facade")
equal(runtime.modeAtStart, "elected", "Start sees the elected mode")
equal(runtime.logged, 1, "Login runs once at PLAYER_LOGIN")
equal(runtime.modeAtLogin, "elected", "Login sees the elected mode")
session.Fire("PLAYER_LOGIN")
session.loader.Activate()
equal(runtime.logged, 1, "a second login never runs Login again")

-- The same contract for the transitional standalone: Start at its ADDON_LOADED, Login only at PLAYER_LOGIN.
session = newSession()
session:Candidate("ForeverCore", build(1, 9, 0))
session.Fire("ADDON_LOADED", "ForeverCore")
equal(session.identities.ForeverCore, "ForeverCore", "the standalone chunk sees the fixed identity")
equal(#session.starts, 1, "standalone Start runs at its ADDON_LOADED")
equal(#session.logins, 0, "standalone Login waits for PLAYER_LOGIN")
equal(session.loader.Namespace() and session.loader.Namespace().mode, "standalone", "namespace mode is standalone")
session.Fire("PLAYER_LOGIN")
equal(#session.logins, 1, "standalone Login runs at PLAYER_LOGIN")
session.Fire("PLAYER_LOGIN")
equal(#session.logins, 1, "and only once")

-- Start runs before publication and a failed Start is terminal: no facade, no Login, no fallback.
session = newSession()
session:Candidate("BrokenStart", build(1, 9, 0), {
	chunk = function(ns)
		ns.Start = function()
			error("start failed")
		end
	end,
})
session.Fire("PLAYER_LOGIN")
check(session.loader.Selected() == nil, "a failed Start selects nothing")
equal(#session.boots, 1, "the chosen copy still ran its chunks")
check(session.loader.Error():find("start failed", 1, true) ~= nil, "the Start failure is the boot error")
check(session.env.ForeverCore == nil, "a failed Start publishes no facade")
equal(#session.logins, 0, "Login never runs after a failed Start")
check(session.loader.LoginError() == nil, "and no login error is recorded")
session.Fire("PLAYER_LOGIN")
equal(#session.logins, 0, "a later login does not run Login either")

-- A truncated package without namespace.Start is refused before publishing.
session = newSession()
local noStart = session.loader.Begin("NoStart", build(1, 9, 0))
noStart:Define(function(_, ns)
	ns.Login = function() end
	ns.ForeverCore = { API = 1, Register = function() end, name = "ForeverCore" }
end)
check(noStart:Seal(), "the Start-less copy seals")
session.Fire("PLAYER_LOGIN")
check(session.loader.Selected() == nil, "a copy without Start selects nothing")
check(session.loader.Error():find("namespace Start", 1, true) ~= nil, "and says Start is missing")
check(session.env.ForeverCore == nil, "and publishes no facade")

-- A Login failure reaches the native handler and its own field; the boot stays good and no other runtime starts.
session = newSession()
local loginHandled
local loginCalls = 0
session.env.geterrorhandler = function()
	return function(message)
		loginCalls = loginCalls + 1
		loginHandled = tostring(message)
		-- Deliberately returns nothing: WoW handlers commonly do.
	end
end
session:Candidate("AddonB", build(1, 8, 0))
session:Candidate("AddonA", build(1, 9, 0), {
	chunk = function(ns)
		ns.Login = function()
			error("login failed")
		end
	end,
})
session.Fire("PLAYER_LOGIN")
equal(#session.boots, 1, "a login error never falls back to another runtime")
equal(session.loader.Selected() and session.loader.Selected().folder, "AddonA", "the booted copy stays selected")
check(rawequal(session.env.ForeverCore, session.loader.Facade()), "and its facade stays published")
check(loginHandled and loginHandled:find("login failed", 1, true) ~= nil, "the native handler sees the login error")
check(
	session.loader.LoginError() and session.loader.LoginError():find("login failed", 1, true) ~= nil,
	"the original login error is recorded even when the handler returns nothing"
)
check(session.loader.Error() == nil, "the boot error stays empty")
check(session.loader.CallbackError() == nil, "and no callback error is invented")
session.Fire("PLAYER_LOGIN")
equal(loginCalls, 1, "the login failure is reported once")

-- Same capture rule for a callback error from a handler that returns nothing.
session = newSession()
local callbackHandled
session.env.geterrorhandler = function()
	return function(message)
		callbackHandled = tostring(message)
	end
end
session.loader.OnReady(function()
	error("callback nil handler")
end)
session:Candidate("AddonA", build(1, 9, 0))
session.Fire("PLAYER_LOGIN")
check(
	callbackHandled and callbackHandled:find("callback nil handler", 1, true) ~= nil,
	"the native handler sees the callback error"
)
check(
	session.loader.CallbackError() and session.loader.CallbackError():find("callback nil handler", 1, true) ~= nil,
	"the original callback error survives a handler that returns nothing"
)
check(session.loader.Error() == nil, "and the boot stays clean")

-- Legacy 1.8 is adopted, never neutralised and never run beside: its table stays the identity consumers already see.
session = newSession()
local legacy = { API = 1, Register = function() end, name = "ForeverCore" }
session.env.ForeverCore = legacy
session:Candidate("Embedded", build(1, 9, 0))
session.Fire("PLAYER_LOGIN")
selected = session.loader.Selected()
equal(selected and selected.mode, "legacy", "an existing 1.8 table selects legacy mode")
check(rawequal(selected and selected.core, legacy), "legacy mode reports the 1.8 table")
check(rawequal(session.env.ForeverCore, legacy), "legacy mode leaves the 1.8 global unchanged")
equal(#session.boots, 0, "no embedded chunk runs beside 1.8")
equal(#session.logins, 0, "legacy never runs a namespace Login")
check(session.loader.LoginError() == nil, "and records no login error")
local readyCore
session.loader.OnReady(function(core)
	readyCore = core
end)
check(rawequal(readyCore, legacy), "a late OnReady callback gets the legacy table")

-- A legacy copy that appears after Begin but before PLAYER_LOGIN is still adopted.
session = newSession()
session:Candidate("Embedded", build(1, 9, 0))
session.env.ForeverCore = legacy
session.Fire("PLAYER_LOGIN")
equal(session.loader.Selected() and session.loader.Selected().mode, "legacy", "legacy is detected at activation")
equal(#session.boots, 0, "the embedded chunk stays unrun when legacy arrives before activation")
equal(#session.logins, 0, "and no namespace Login runs")

-- A 1.8 table already loaded at the first Begin is active before the consumer's next line runs, so OnReady keeps the
-- file-load timing 1.8's Register and TrackerSection use expect.
session = newSession()
session.env.ForeverCore = legacy
local legacyCopy = session.loader.Begin("LegacyConsumer", build(1, 9, 0), "legacy-consumer")
check(legacyCopy.rejected == nil, "a copy may register beside an adopted 1.8 table")
legacyCopy:Define(function()
	session.boots[#session.boots + 1] = "LegacyConsumer"
end)
equal(legacyCopy:Seal(), true, "and still seals")
selected = session.loader.Selected()
equal(selected and selected.mode, "legacy", "Begin activates the loaded 1.8 table immediately")
check(rawequal(selected and selected.core, legacy), "with the loaded 1.8 table")
equal(#session.boots, 0, "and no embedded chunk runs")
local immediateLegacy
session.loader.OnReady(function(core)
	immediateLegacy = core
end)
check(rawequal(immediateLegacy, legacy), "OnReady after a legacy Begin runs inside the consumer's file load")
session.Fire("PLAYER_LOGIN")
equal(#session.boots, 0, "login does not boot a copy beside 1.8")

-- The standalone participant waits for its own ADDON_LOADED, which is after its SavedVariables, and suspends
-- newest-wins for the session. An unrelated ADDON_LOADED must not activate it.
session = newSession()
session:Candidate("EmbeddedNewer", build(1, 9, 0))
local standalone = session:Candidate("ForeverCore", build(1, 5, 0))
check(standalone.sealed, "the standalone copy seals")
check(session.loader.Selected() == nil, "Seal alone does not activate the standalone")
equal(#session.boots, 0, "no chunk runs before the standalone's own event")
local frame = session.frames[1]
check(frame.events.ADDON_LOADED == true, "the loading frame listens for ADDON_LOADED")
check(frame.events.PLAYER_LOGIN == true, "and for PLAYER_LOGIN")
session.Fire("ADDON_LOADED", "SomeOtherAddon")
check(session.loader.Selected() == nil, "another addon's ADDON_LOADED does not activate it")
equal(#session.boots, 0, "and runs no chunk")
session.Fire("ADDON_LOADED", "ForeverCore")
selected = session.loader.Selected()
equal(selected and selected.mode, "standalone", "its own ADDON_LOADED selects the standalone")
equal(selected and selected.folder, "ForeverCore", "the standalone folder is recorded")
equal(
	selected and selected.root,
	"Interface\\AddOns\\ForeverCore",
	"the standalone keeps the top-level addon root its TOC and media use"
)
equal(#session.boots, 1, "standalone boots exactly once")
equal(session.boots[1], "ForeverCore", "the standalone boot is the only runtime")
check(frame.events.ADDON_LOADED == nil, "standalone activation stops listening for ADDON_LOADED")
check(frame.events.PLAYER_LOGIN == true, "and keeps listening for PLAYER_LOGIN to close store offers")
local later = session.loader.Begin("EmbeddedLater", build(1, 10, 0))
equal(later.rejected, "late", "an embedded copy after standalone activation is late")
equal(#session.boots, 1, "a newer embedded copy cannot boot beside the standalone")

-- A standalone activates at its ADDON_LOADED, before consumers offer, so offers stay open until PLAYER_LOGIN.
check(
	session.loader.OfferStore("ConsumerAfterStandalone", "ConsumerAccountDB"),
	"a store offered after standalone activation but before login is accepted"
)
session.Fire("PLAYER_LOGIN")
local standaloneOffers = session.loader.Offers()
equal(#standaloneOffers, 1, "the late offer is retained")
equal(standaloneOffers[1] and standaloneOffers[1].folder, "ConsumerAfterStandalone", "with its folder")
equal(standaloneOffers[1] and standaloneOffers[1].globalName, "ConsumerAccountDB", "and its saved-variable name")
local closed, closedReason = session.loader.OfferStore("TooLate", "TooLateDB")
equal(closed, false, "PLAYER_LOGIN closes store offers")
equal(closedReason, "late", "as late")

-- A failing winner is reported once and is not retried; a lower copy is not booted over its partial side effects.
session = newSession()
session:Candidate("BrokenNewest", build(1, 7, 0), {
	chunk = function()
		error("candidate failed")
	end,
})
session:Candidate("Survivor", build(1, 6, 0))
session.Fire("PLAYER_LOGIN")
check(session.loader.Selected() == nil, "a failed election selects nothing")
check(session.loader.Error() ~= nil, "the failure is recorded")
check(session.loader.Error():find("candidate failed", 1, true) ~= nil, "the recorded failure names the error")
equal(#session.boots, 1, "the failed winner ran and the lower copy did not")
equal(session.boots[1], "BrokenNewest", "only the elected winner was attempted")
check(session.env.ForeverCore == nil, "a failed candidate publishes no facade")
session.Fire("PLAYER_LOGIN")
session.loader.Activate()
equal(#session.boots, 1, "a failed activation never retries")

-- A facade that claims another loader schema or a different build is refused before it is published.
session = newSession()
session:Candidate("BadSchema", build(1, 7, 0), {
	chunk = function(_, core)
		core.loaderSchema = 2
	end,
})
session.Fire("PLAYER_LOGIN")
check(session.loader.Selected() == nil, "an incompatible facade schema selects nothing")
check(session.loader.Error():find("incompatible loader schema", 1, true) ~= nil, "and names the incompatible schema")
check(session.env.ForeverCore == nil, "an incompatible facade is never published")

session = newSession()
session:Candidate("BadBuild", build(1, 7, 0), {
	chunk = function(_, core)
		core.build = build(1, 6, 0)
	end,
})
session.Fire("PLAYER_LOGIN")
check(session.loader.Selected() == nil, "a facade with a different build selects nothing")
check(session.loader.Error():find("not the sealed build", 1, true) ~= nil, "and names the build mismatch")

-- A copy must hand its facade to the loader on the namespace. A chunk that writes the global itself is refused, so
-- the loader remains the only publisher.
session = newSession()
local globalOnly = session.loader.Begin("GlobalOnly", build(1, 7, 0))
globalOnly:Define(function(_, ns)
	ns.Start = function() end
	session.env.ForeverCore = { API = 1, Register = function() end, name = "ForeverCore" }
end)
check(globalOnly:Seal(), "the global-only copy seals")
session.Fire("PLAYER_LOGIN")
check(session.loader.Selected() == nil, "a global-only facade selects nothing")
check(session.loader.Error():find("no namespace facade", 1, true) ~= nil, "and says the namespace facade is missing")

-- Defining after Seal is refused and leaves the sealed copy eligible.
session = newSession()
local sealed = session:Candidate("AddonA", build(1, 7, 0))
local defineAgain, defineReason = sealed:Define(function() end)
equal(defineAgain, false, "a sealed copy refuses another definition")
equal(defineReason, "sealed", "and says it is sealed")
session.Fire("PLAYER_LOGIN")
equal(session.loader.Selected().folder, "AddonA", "a refused late definition leaves the copy eligible")

-- An OnReady registered from inside a chunk waits for activation to finish, so it sees the facade and selection.
session = newSession()
local during
session:Candidate("AddonA", build(1, 7, 0), {
	chunk = function()
		session.loader.OnReady(function(core, chosen)
			during = { core = core, chosen = chosen }
		end)
	end,
})
session.Fire("PLAYER_LOGIN")
check(during ~= nil, "an OnReady from inside boot runs after activation")
check(during and during.chosen and during.chosen.folder == "AddonA", "and sees the selected copy")
check(during and rawequal(during.core, session.env.ForeverCore), "and the published facade")

-- OnReady runs in registration order after activation. A callback failure reaches the client's error handler and is
-- recorded separately from a boot failure. A nested OnReady queues behind the callbacks already waiting.
session = newSession()
local order = {}
local handled
session.env.geterrorhandler = function()
	return function(message)
		handled = tostring(message)
		return message
	end
end
session.loader.OnReady(function(core, chosen)
	order[#order + 1] = "first:" .. tostring(chosen and chosen.folder)
	check(core ~= nil, "OnReady gets the facade")
	session.loader.OnReady(function()
		order[#order + 1] = "nested"
	end)
end)
session.loader.OnReady(function()
	order[#order + 1] = "second"
	error("ready failed")
end)
session.loader.OnReady(function()
	order[#order + 1] = "third"
end)
session:Candidate("AddonA", build(1, 7, 0))
session.Fire("PLAYER_LOGIN")
equal(order[1], "first:AddonA", "the first ready callback runs first")
equal(order[2], "second", "a failing ready callback still runs in order")
equal(order[3], "third", "a nested OnReady queues behind the callbacks already registered")
equal(order[4], "nested", "and runs after them, in registration order")
check(
	handled ~= nil and handled:find("ready failed", 1, true) ~= nil,
	"a ready failure reaches the client's own error handler"
)
check(session.loader.CallbackError() ~= nil, "and is recorded as a callback error")
check(session.loader.Error() == nil, "while a clean boot leaves the boot error empty")
local immediate
session.loader.OnReady(function(core)
	immediate = core
end)
check(rawequal(immediate, session.env.ForeverCore), "OnReady after activation runs at once")

-- Without a client error handler the failure is still recorded, so /fcore and a report can show it.
session = newSession()
session.env.geterrorhandler = false
session.loader.OnReady(function()
	error("ready without handler")
end)
session:Candidate("AddonA", build(1, 7, 0))
session.Fire("PLAYER_LOGIN")
check(
	session.loader.CallbackError() ~= nil
		and session.loader.CallbackError():find("ready without handler", 1, true) ~= nil,
	"a callback failure is recorded when the client has no error handler"
)

-- OfferStore retains only the folder and the explicit account SavedVariables global name. The loader never captures a
-- table, looks the name up, or applies revision/merge policy; the runtime resolves rawget(_G, name) later.
session = newSession()
check(session.loader.OfferStore("AddonA", "AddonAAccountDB"), "AddonA offers its account DB name")
check(session.loader.OfferStore("AddonB", "AddonBAccountDB"), "AddonB offers its account DB name")
local offers = session.loader.Offers()
equal(#offers, 2, "Offers lists every accepted offer in offer order")
equal(offers[1].folder, "AddonA", "with the offering folder")
equal(offers[1].globalName, "AddonAAccountDB", "and the saved-variable global name")
equal(offers[2].folder, "AddonB", "for each offer")
equal(offers[2].globalName, "AddonBAccountDB", "and its global name")
check(offers[1].db == nil, "Offers captures no table")
check(offers[2].db == nil, "for any offer")
session:Candidate("AddonA", build(1, 7, 0))
session.Fire("PLAYER_LOGIN")
local afterLogin = session.loader.Offers()
equal(afterLogin[1].globalName, "AddonAAccountDB", "activation leaves the offered name alone")
equal(afterLogin[2].globalName, "AddonBAccountDB", "for every offer")

-- A name can be offered before the SavedVariables global exists, and a later replacement is still current: the entry
-- stays a name, not a captured table.
session = newSession()
check(session.loader.OfferStore("Early", "LaterAccountDB"), "a name is accepted before its global exists")
check(rawget(session.env, "LaterAccountDB") == nil, "offering creates no global")
session.env.LaterAccountDB = { settings = { scale = 2 } }
equal(session.loader.Offers()[1].globalName, "LaterAccountDB", "the registered name is retained")
session.env.LaterAccountDB = { settings = { scale = 3 } }
local replaced = session.loader.Offers()[1]
equal(replaced.globalName, "LaterAccountDB", "replacing the global changes no offered name")
check(replaced.db == nil, "and no captured table appears")
check(
	rawequal(rawget(session.env, replaced.globalName), session.env.LaterAccountDB),
	"the current global resolves by name"
)

-- The loader never indexes the offered global, so a protected/metatable saved table is not read during registration.
session = newSession()
session.env.PoisonAccountDB = setmetatable({}, {
	__index = function()
		error("loader read a saved table")
	end,
})
check(session.loader.OfferStore("Poison", "PoisonAccountDB"), "the protected name is accepted")
equal(session.loader.Offers()[1].globalName, "PoisonAccountDB", "and no field is read from its global")

-- Wrong folder and name types are rejected, including an empty name.
session = newSession()
local badFolder, folderReason = session.loader.OfferStore("", "SomeDB")
equal(badFolder, false, "an empty folder is rejected")
equal(folderReason, "store-folder", "as a store-folder")
local badFolderType, folderTypeReason = session.loader.OfferStore(5, "SomeDB")
equal(badFolderType, false, "a non-string folder is rejected")
equal(folderTypeReason, "store-folder", "as a store-folder")
local nilName, nilReason = session.loader.OfferStore("NoName", nil)
equal(nilName, false, "a nil global name is rejected")
equal(nilReason, "store-name", "as a store-name")
local emptyName, emptyNameReason = session.loader.OfferStore("EmptyName", "")
equal(emptyName, false, "an empty global name is rejected")
equal(emptyNameReason, "store-name", "as a store-name")
local tableName, tableReason = session.loader.OfferStore("TableName", {})
equal(tableName, false, "a table where a global name belongs is rejected")
equal(tableReason, "store-name", "as a store-name")
equal(#session.loader.Offers(), 0, "no rejected offer is retained")

session = newSession()
check(session.loader.OfferStore("AddonA", "AccountA"), "the first store offer is accepted")
local accepted, storeReason = session.loader.OfferStore("AddonA", "AccountB")
equal(accepted, false, "a second store offer for one folder is rejected")
equal(storeReason, "duplicate", "as a duplicate")
equal(session.loader.Offers()[1].globalName, "AccountA", "and it cannot replace the first name")
session:Candidate("AddonA", build(1, 7, 0))
session.Fire("PLAYER_LOGIN")
accepted, storeReason = session.loader.OfferStore("LateStore", "LateDB")
equal(accepted, false, "a store offered after activation is rejected")
equal(storeReason, "late", "as late")

print(("embedded_loader_spec: %d checks passed"):format(checks))
