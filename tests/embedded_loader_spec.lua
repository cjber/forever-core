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

-- A facade every consumer can use: API 2, Register and the tracker line with SetInteractive.
local function Facade()
	return {
		API = 2,
		Register = function() end,
		TrackerLine = { SetInteractive = function() end, template = "Test_ForeverCore_Line" },
		name = "ForeverCore",
	}
end

-- The release build formula: major * 1e6 + minor * 1e3 + patch.
local function build(major, minor, patch)
	return major * 1000000 + minor * 1000 + (patch or 0)
end

-- A fresh Lua environment is one client session: one loading frame list, one loader global and one facade. Loading
-- the loader file twice is what two embedded copies do when they are the first and the second copy in the same
-- session; the second must reuse the first copy's registry.
local function newSession(older, setup)
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
	-- The next frame: C_Timer.After(0) work waits for Tick, as it waits for the client's next frame.
	local queued = {}
	env.C_Timer = {
		After = function(_, callback)
			queued[#queued + 1] = callback
		end,
	}
	local function load(path)
		local chunk = assert(loadfile(path or "Core/Loader.lua"), path or "Core/Loader.lua")
		setfenv(chunk, env)
		chunk("ForeverCore", {})
	end
	if setup then
		setup(env)
	end
	if older then
		load(older)
	end
	load()
	local session = { env = env, frames = frames, boots = {}, identities = {}, starts = {}, logins = {} }
	function session.Tick()
		local run = queued
		queued = {}
		for _, callback in ipairs(run) do
			callback()
		end
	end
	session.loader = env.ForeverCoreLoader
	function session.ReloadLoader()
		load()
	end
	function session.Fire(event, ...)
		for _, frame in ipairs(frames) do
			if frame.events[event] and frame.scripts.OnEvent then
				frame.scripts.OnEvent(frame, event, ...)
			end
		end
	end
	-- A copy in the shape Begin.lua + wrapped files + End.lua will produce. Each wrapped file is called with the fixed
	-- identity "ForeverCore" and the namespace, exactly like the standalone main chunk. `opts.chunk` runs inside the
	-- winner's namespace before Start and publication, so a test can make a candidate fail or record what it saw.
	function session:Candidate(folder, version, opts)
		opts = opts or {}
		local copy = self.loader.Begin(folder, version, opts.digest, opts.chunks)
		copy:Define(function(...)
			local identity, ns = ...
			self.identities[folder] = identity
			self.boots[#self.boots + 1] = folder
			local core = Facade()
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
	ns.ForeverCore = Facade()
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

-- Standalone registers like every other copy and starts only after election.
session = newSession()
session:Candidate("ForeverCore", build(1, 9, 0))
session.Fire("ADDON_LOADED", "ForeverCore")
equal(#session.starts, 0, "standalone waits beyond its ADDON_LOADED")
equal(#session.logins, 0, "standalone Login waits for PLAYER_LOGIN")
session.Fire("PLAYER_LOGIN")
equal(session.identities.ForeverCore, "ForeverCore", "the standalone chunk sees the fixed identity")
equal(#session.starts, 1, "standalone Start runs at login")
equal(session.loader.Namespace() and session.loader.Namespace().mode, "standalone", "namespace mode is standalone")
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
	ns.ForeverCore = Facade()
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
local legacy = {
	API = 2,
	Register = function() end,
	TrackerLine = { SetInteractive = function() end },
	name = "ForeverCore",
}
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

-- A standalone participates in newest-wins; its own event cannot close election.
session = newSession()
session:Candidate("EmbeddedNewer", build(1, 9, 0))
local standalone = session:Candidate("ForeverCore", build(1, 5, 0))
check(standalone.sealed, "the standalone copy seals")
check(session.loader.Selected() == nil, "Seal alone does not activate the standalone")
equal(#session.boots, 0, "no chunk runs before login")
local frame = session.frames[1]
-- ADDON_LOADED before login never activates: it is only the late-host path (below).
check(frame.events.PLAYER_LOGIN == true, "the loading frame listens for PLAYER_LOGIN")
session.Fire("ADDON_LOADED", "SomeOtherAddon")
session.Fire("ADDON_LOADED", "ForeverCore")
check(session.loader.Selected() == nil, "own ADDON_LOADED before login does not activate it")
equal(#session.boots, 0, "and runs no chunk")
local later = session:Candidate("EmbeddedLater", build(1, 10, 0))
check(later.rejected == nil, "a later higher embedded copy remains eligible")
check(session.loader.OfferStore("ConsumerAfterStandalone", "ConsumerAccountDB"), "offers stay open until login")
check(session.loader.OfferStore("ConsumerAfterStandalone", "ConsumerAccountDB"), "identical offers are idempotent")
session.Fire("PLAYER_LOGIN")
selected = session.loader.Selected()
equal(selected and selected.mode, "elected", "higher embedded wins")
equal(selected and selected.folder, "EmbeddedLater", "the newest folder is recorded")
equal(selected and selected.root, "Interface\\AddOns\\EmbeddedLater\\Libs\\ForeverCore", "selected media root")
equal(#session.boots, 1, "one runtime boots")
equal(session.boots[1], "EmbeddedLater", "the highest build is the only runtime")
check(frame.events.PLAYER_LOGIN == nil, "no PLAYER_LOGIN listener remains")
check(frame.events.ADDON_LOADED == true, "ADDON_LOADED stays for a host that joins the running copy")
local standaloneOffers = session.loader.Offers()
equal(#standaloneOffers, 1, "the repeated offer is retained once")
equal(standaloneOffers[1].folder, "ConsumerAfterStandalone", "with its folder")
equal(standaloneOffers[1].globalName, "ConsumerAccountDB", "and its saved-variable name")
check(session.loader.OfferStore("JoinsLater", "JoinsLaterDB"), "an offer after activation is kept for reconciliation")
equal(#session.loader.Offers(), 2, "beside the startup offer")

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
	ns.Login = function() end
	session.env.ForeverCore = Facade()
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
check(session.loader.OfferStore("LateStore", "LateDB"), "a store offered after activation is kept for its host")

-- Candidate inspection includes unsealed/rejected registrations and cannot mutate the registry.
session = newSession()
session:Candidate("A", build(1, 9, 0))
local emptyCandidate = session.loader.Begin("Empty", build(1, 10, 0))
emptyCandidate:Seal()
local candidates = session.loader.Candidates()
equal(#candidates, 2, "diagnostics enumerate registered candidates")
equal(candidates[1].build, build(1, 9, 0), "candidate build is inspectable")
check(candidates[1].sealed, "complete candidate is sealed")
equal(candidates[2].rejected, "empty", "rejected candidate retains its reason")
candidates[1].build = build(9, 0, 0)
equal(session.loader.Candidates()[1].build, build(1, 9, 0), "diagnostic snapshots do not mutate candidates")

-- Every way a sess reaches activation, for every outcome: a registered copy is never left silent. After the event,
-- exactly one of Selected and Error answers, the runtime boots at most once and its Login runs at most once, and the
-- trace names the event that activated it. This is the guard for the class behind #837: a copy that registered and
-- sealed but was never activated, with Selected and Error both nil.
local paths = {
	{
		name = "PLAYER_LOGIN",
		run = function(sess)
			sess.Fire("PLAYER_LOGIN")
		end,
	},
	{
		name = "PLAYER_ENTERING_WORLD without PLAYER_LOGIN",
		run = function(sess)
			-- Every sealed host's own ADDON_LOADED has run, so every offered store is in.
			sess.Fire("ADDON_LOADED", "Host")
			sess.Fire("ADDON_LOADED", "Other")
			sess.Fire("PLAYER_ENTERING_WORLD", true, false)
			check(#sess.boots == 0, "the world-entry start waits for the next frame")
			sess.Tick()
		end,
	},
	{
		name = "PLAYER_ENTERING_WORLD without PLAYER_LOGIN",
		label = "PLAYER_ENTERING_WORLD before SavedVariables",
		run = function(sess)
			sess.Fire("PLAYER_ENTERING_WORLD", true, false)
			check(sess.loader.Selected() == nil and sess.loader.Error() == nil, "the stores are not loaded yet")
			check(#sess.boots == 0, "so nothing boots")
			sess.Fire("VARIABLES_LOADED")
			sess.Tick()
		end,
	},
	{
		name = "sealed after login",
		label = "a load-on-demand host after login",
		loggedIn = true,
		run = function(sess)
			sess.Fire("ADDON_LOADED", "SomeOtherAddon")
			sess.Fire("ADDON_LOADED", "Host")
			check(sess.loader.Selected() == nil and sess.loader.Error() == nil, "activation waits for the next frame")
			sess.Tick()
		end,
	},
	{
		name = "sealed after login",
		label = "a manual load after login with no ADDON_LOADED",
		loggedIn = true,
		run = function(sess)
			sess.Tick()
		end,
	},
	{
		name = "PLAYER_LOGIN, after combat",
		label = "PLAYER_LOGIN in combat lockdown",
		run = function(sess)
			local combat = true
			sess.env.InCombatLockdown = function()
				return combat
			end
			sess.Fire("PLAYER_LOGIN")
			check(sess.loader.Selected() == nil and #sess.boots == 0, "nothing boots in combat lockdown")
			combat = false
			sess.Fire("PLAYER_REGEN_ENABLED")
		end,
	},
}
local outcomes = {
	{ name = "a valid copy", expect = "elected" },
	{
		name = "a copy whose Start fails",
		chunk = function(ns)
			ns.Start = function()
				error("start failed", 0)
			end
		end,
		expect = "error",
	},
	{
		name = "a copy with an incomplete facade",
		chunk = function(_, core)
			core.Register = nil
		end,
		expect = "error",
		noStart = true,
	},
	{
		name = "a copy whose facade is not API 2",
		chunk = function(_, core)
			core.API = 1
		end,
		expect = "error",
		noStart = true,
	},
	{
		name = "a copy with no tracker line",
		chunk = function(_, core)
			core.TrackerLine = nil
		end,
		expect = "error",
		noStart = true,
	},
	{
		name = "a copy with no Login",
		chunk = function(ns)
			ns.Login = nil
		end,
		expect = "error",
		noStart = true,
	},
	{
		name = "a copy with no tracker line template",
		chunk = function(_, core)
			core.TrackerLine.template = nil
		end,
		expect = "error",
		noStart = true,
	},
	{ name = "two conflicting copies", conflict = true, expect = "error" },
}
for _, path in ipairs(paths) do
	for _, outcome in ipairs(outcomes) do
		local label = (path.label or path.name) .. " / " .. outcome.name
		local sess = newSession()
		sess.handled = {}
		sess.env.geterrorhandler = function()
			return function(message)
				sess.handled[#sess.handled + 1] = tostring(message)
			end
		end
		if path.loggedIn then
			sess.env.IsLoggedIn = function()
				return true
			end
		end
		sess:Candidate("Host", build(1, 9, 0), { digest = "a", chunk = outcome.chunk })
		if outcome.conflict then
			sess:Candidate("Other", build(1, 9, 0), { digest = "b" })
		end
		equal(#sess.boots, 0, label .. ": nothing runs before activation")
		path.run(sess)
		local picked, err = sess.loader.Selected(), sess.loader.Error()
		check((picked ~= nil) ~= (err ~= nil), label .. ": exactly one of Selected and Error answers")
		if outcome.expect == "elected" then
			equal(picked and picked.folder, "Host", label .. ": the copy is elected")
			equal(#sess.logins, 1, label .. ": its Login runs once")
		else
			check(err ~= nil, label .. ": the failure is reported")
			equal(#sess.handled, 1, label .. ": once, through the client's error handler")
			check(sess.handled[1]:find(err, 1, true) ~= nil, label .. ": naming the loader's error")
			equal(#sess.logins, 0, label .. ": no Login runs after a failed boot")
		end
		if outcome.noStart then
			equal(#sess.starts, 0, label .. ": Start never runs for a copy that fails validation")
		end
		local boots, logins = #sess.boots, #sess.logins
		sess.Fire("PLAYER_LOGIN")
		sess.Fire("PLAYER_ENTERING_WORLD")
		sess.Fire("ADDON_LOADED", "Host")
		sess.Tick()
		equal(#sess.boots, boots, label .. ": later loading events boot nothing more")
		equal(#sess.logins, logins, label .. ": and run no second Login")
		local activations = {}
		for _, entry in ipairs(sess.loader.Trace()) do
			if entry.kind == "activate" then
				activations[#activations + 1] = entry.detail
			end
		end
		equal(#activations, 1, label .. ": the trace records one activation")
		equal(activations[1], path.name, label .. ": named by the event that caused it")
		for _, event in ipairs({ "PLAYER_LOGIN", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED" }) do
			check(not sess.frames[1].events[event], label .. ": the loading frame drops " .. event)
		end
	end
end

-- A normal sess's trace, in order: each copy's begin and seal, then the activation and the boot result.
do
	local sess = newSession()
	sess:Candidate("AddonA", build(1, 7, 0))
	sess:Candidate("AddonB", build(1, 8, 0))
	sess.Fire("PLAYER_LOGIN")
	local kinds = {}
	for _, entry in ipairs(sess.loader.Trace()) do
		kinds[#kinds + 1] = entry.kind .. ":" .. tostring(entry.folder)
	end
	equal(
		table.concat(kinds, " "),
		"begin:AddonA seal:AddonA begin:AddonB seal:AddonB activate:nil boot:AddonB",
		"the trace lists the sess in order"
	)
	local copy = sess.loader.Trace()
	copy[1].kind = "changed"
	equal(sess.loader.Trace()[1].kind, "begin", "the trace is a copy")
end

-- A legacy table is adopted only when it serves the embedded consumers' ready step; an older one fails the sess
-- with its installed version named, and neither it nor any embedded copy is run or replaced.
for _, case in ipairs({
	{
		name = "API 1",
		core = { API = 1, Register = function() end, TrackerLine = { SetInteractive = function() end } },
	},
	{ name = "no Register", core = { API = 2, TrackerLine = { SetInteractive = function() end } } },
	{ name = "no TrackerLine", core = { API = 2, Register = function() end } },
	{ name = "no SetInteractive", core = { API = 2, Register = function() end, TrackerLine = {} } },
}) do
	local sess = newSession()
	sess.env.C_AddOns = {
		GetAddOnMetadata = function(name, key)
			if name == "ForeverCore" and key == "Version" then
				return "v1.7.0"
			end
		end,
	}
	sess.env.ForeverCore = case.core
	sess:Candidate("Embedded", build(1, 9, 0))
	sess.Fire("PLAYER_LOGIN")
	check(sess.loader.Selected() == nil, "legacy " .. case.name .. " is not adopted")
	local err = sess.loader.Error() or ""
	check(err:find("too old", 1, true) and err:find("v1.7.0", 1, true), "legacy " .. case.name .. " names its version")
	equal(#sess.boots, 0, "legacy " .. case.name .. " runs no embedded copy beside it")
	check(rawequal(sess.env.ForeverCore, case.core), "legacy " .. case.name .. " stays the published table")
end
do
	local sess = newSession()
	sess.env.C_AddOns = {
		GetAddOnMetadata = function()
			return "v1.15.0"
		end,
	}
	local shown = {}
	sess.env.StaticPopupDialogs = {}
	sess.env.StaticPopup_Show = function(which, message)
		shown[#shown + 1] = which .. ":" .. tostring(message)
	end
	local store = {}
	sess.env.ForeverCoreDB = store
	sess.env.ForeverCore = legacy
	sess:Candidate("Embedded", build(1, 16, 0))
	local picked = sess.loader.Selected()
	equal(picked.version, "v1.15.0", "a compatible legacy selection reports its installed version")
	equal(picked.build, build(1, 15, 0), "and its build")
	equal(picked.newest, build(1, 16, 0), "and the newer embedded build it runs in place of")
	local warning = sess.loader.Warning() or ""
	check(warning:find("v1.15.0", 1, true) and warning:find("1.16.0", 1, true), "the warning names both versions")
	check(
		warning:find("Update ForeverCore, or delete the ForeverCore folder in Interface/AddOns", 1, true),
		"and what to do"
	)
	sess.Tick()
	equal(#shown, 0, "the notice waits for the world entry")
	sess.Fire("PLAYER_ENTERING_WORLD", true, false)
	sess.Tick()
	equal(#shown, 1, "then shows once on screen")
	check(shown[1]:find("FOREVERCORE_OUTDATED", 1, true) == 1, "as the loader's own notice")
	sess:Candidate("EmbeddedNewer", build(1, 17, 0))
	sess.Tick()
	equal(#shown, 1, "and never a second time in the session")
	equal(store.outdatedNoticeVersion, "v1.15.0", "the standalone's store remembers the version it was shown for")

	-- A later session with the same standalone version shows nothing; Warning still reports it. A different
	-- installed version shows it once again.
	for _, case in ipairs({ { version = "v1.15.0", expect = 0 }, { version = "v1.15.1", expect = 1 } }) do
		local nextSession = newSession()
		local laterShown = 0
		nextSession.env.StaticPopupDialogs = {}
		nextSession.env.StaticPopup_Show = function()
			laterShown = laterShown + 1
		end
		nextSession.env.C_AddOns = {
			GetAddOnMetadata = function()
				return case.version
			end,
		}
		nextSession.env.ForeverCoreDB = store
		nextSession.env.ForeverCore = legacy
		nextSession:Candidate("Embedded", build(1, 16, 0))
		nextSession.Fire("PLAYER_ENTERING_WORLD", false, true)
		nextSession.Tick()
		equal(laterShown, case.expect, case.version .. ": the notice shows once per standalone version")
		check(nextSession.loader.Warning() ~= nil, case.version .. ": Warning still reports it")
	end
end

-- The loading frame records PLAYER_ENTERING_WORLD and VARIABLES_LOADED once seen, with the first entry's arguments, so
-- a runtime booted after them does not wait for them again. A loader first made after login counts both as past.
do
	local sess = newSession()
	sess:Candidate("AddonA", build(1, 7, 0))
	check(not sess.loader.Seen("PLAYER_ENTERING_WORLD"), "the world entry is not past before it fires")
	sess.Fire("PLAYER_LOGIN")
	check(not sess.loader.Seen("VARIABLES_LOADED"), "nor are the saved variables")
	for _, loadingFrame in ipairs(sess.frames) do
		if loadingFrame.events.PLAYER_ENTERING_WORLD and loadingFrame.scripts.OnEvent then
			loadingFrame.scripts.OnEvent(loadingFrame, "PLAYER_ENTERING_WORLD", true, false)
		end
	end
	sess.Fire("VARIABLES_LOADED")
	check(sess.loader.Seen("PLAYER_ENTERING_WORLD"), "the world entry is recorded after activation too")
	check(sess.loader.Seen("VARIABLES_LOADED"), "and the saved variables")
	local initial, reloading = sess.loader.WorldEntry()
	check(initial == true and reloading == false, "with the first entry's arguments")
	check(not sess.frames[1].events.PLAYER_ENTERING_WORLD, "then the frame stops listening for it")
	check(not sess.frames[1].events.VARIABLES_LOADED, "and for the saved variables")

	local lateSess = newSession()
	lateSess.env.IsLoggedIn = function()
		return true
	end
	lateSess:Candidate("LateHost", build(1, 7, 0))
	check(lateSess.loader.Seen("PLAYER_ENTERING_WORLD"), "a loader made after login counts the world entry as past")
	check(lateSess.loader.Seen("VARIABLES_LOADED"), "and the saved variables")
	lateSess.Fire("PLAYER_ENTERING_WORLD", false, true)
	local lateInitial, lateReloading = lateSess.loader.WorldEntry()
	check(lateInitial == false and lateReloading == true, "and still records an entry that fires later")
end

-- Same highest build with different digests is diagnosed and set aside; the next lower sealed build runs.
do
	local sess = newSession()
	sess:Candidate("TiedA", build(1, 9, 0), { digest = "a" })
	sess:Candidate("Lower", build(1, 8, 0), { digest = "c" })
	sess:Candidate("TiedB", build(1, 9, 0), { digest = "b" })
	sess.Fire("PLAYER_LOGIN")
	equal(sess.loader.Selected() and sess.loader.Selected().folder, "Lower", "the next lower build runs")
	check(sess.loader.Error() == nil, "with no boot error")
	local reasons = {}
	for _, entry in ipairs(sess.loader.Rejections()) do
		reasons[entry.folder .. ":" .. entry.reason] = true
	end
	check(reasons["TiedA:tie-conflict"] and reasons["TiedB:tie-conflict"], "both tied copies are diagnosed")
	equal(#sess.boots, 1, "and only the lower copy boots")
end

-- A copy that named its chunk count at Begin seals only with every chunk defined.
do
	local sess = newSession()
	local short = sess.loader.Begin("Short", build(1, 9, 0), "s", 3)
	short:Define(function() end)
	short:Define(function() end)
	local shortSealed, shortReason = short:Seal()
	check(not shortSealed and shortReason == "incomplete", "a package missing a file does not seal")
	local whole = sess.loader.Begin("Whole", build(1, 8, 0), "w", 1)
	whole:Define(function(_, ns)
		ns.Start, ns.Login, ns.ForeverCore = function() end, function() end, Facade()
	end)
	check(whole:Seal(), "a complete package seals")
	sess.Fire("PLAYER_LOGIN")
	equal(sess.loader.Selected() and sess.loader.Selected().folder, "Whole", "the complete package runs")
	local bad = sess.loader.Begin("BadCount", build(1, 9, 0), "b", 0)
	equal(bad.rejected, "chunks", "a chunk count below one is rejected")
end

-- With no sealed copy at login nothing ran, so the session stays open: the error is reported, and a host loaded
-- later activates.
do
	local sess = newSession()
	sess.loader.Begin("Unsealed", build(1, 9, 0))
	local readyCount = 0
	sess.loader.OnReady(function()
		readyCount = readyCount + 1
	end)
	sess.Fire("PLAYER_LOGIN")
	check(sess.loader.Selected() == nil, "nothing is selected")
	check((sess.loader.Error() or ""):find("no sealed", 1, true), "and the loader says why")
	equal(readyCount, 0, "ready callbacks wait")
	sess.env.IsLoggedIn = function()
		return true
	end
	sess:Candidate("LoadedLater", build(1, 8, 0))
	sess.Fire("ADDON_LOADED", "LoadedLater")
	sess.Tick()
	equal(sess.loader.Selected() and sess.loader.Selected().folder, "LoadedLater", "a host loaded later activates")
	check(sess.loader.Error() == nil, "and the earlier error clears")
	equal(readyCount, 1, "then ready callbacks run once")
	equal(#sess.logins, 1, "and its Login runs once")
end

-- A host that joins the running copy has its store reconciled once its SavedVariables and handlers are in.
do
	local sess = newSession()
	local refreshes = 0
	sess:Candidate("Running", build(1, 9, 0), {
		chunk = function(ns)
			ns.RefreshStore = function()
				refreshes = refreshes + 1
			end
		end,
	})
	sess.Fire("PLAYER_LOGIN")
	check(sess.loader.OfferStore("Joining", "JoiningDB"), "the joining host's offer is kept")
	sess.Fire("ADDON_LOADED", "Joining")
	equal(refreshes, 0, "reconciliation waits for the next frame")
	sess.Tick()
	equal(refreshes, 1, "then the live store is mirrored into its table")
	sess.Fire("ADDON_LOADED", "Joining")
	sess.Tick()
	equal(refreshes, 1, "once")
end

-- An older revision-1 loader that loaded first owns the registry. A newer copy supervises it from outside: Seen and
-- WorldEntry work, and a session whose PLAYER_LOGIN the old loader missed still activates at the world entry.
for _, case in ipairs({
	{ name = "PLAYER_LOGIN", events = { "PLAYER_LOGIN", "PLAYER_ENTERING_WORLD" } },
	{ name = "PLAYER_ENTERING_WORLD only", events = { "PLAYER_ENTERING_WORLD" } },
}) do
	local sess = newSession("tests/fixtures/loader_revision1.lua")
	check(sess.loader.revision == nil, case.name .. ": the revision 1 loader owns the registry")
	check(type(sess.loader.Seen) == "function", case.name .. ": the newer copy adds Seen")
	sess:Candidate("Embedded", build(1, 16, 0))
	check(not sess.loader.Seen("PLAYER_ENTERING_WORLD"), case.name .. ": the world entry is not past yet")
	for _, event in ipairs(case.events) do
		sess.Fire(event, true, false)
	end
	equal(sess.loader.Selected() and sess.loader.Selected().folder, "Embedded", case.name .. ": the copy activates")
	equal(#sess.boots, 1, case.name .. ": once")
	equal(#sess.logins, 1, case.name .. ": with one Login")
	check(sess.loader.Seen("PLAYER_ENTERING_WORLD"), case.name .. ": Seen records the world entry")
	local initial = sess.loader.WorldEntry()
	equal(initial, true, case.name .. ": with its arguments")
	local kinds = {}
	for _, entry in ipairs(sess.loader.Trace()) do
		kinds[#kinds + 1] = entry.kind
	end
	equal(kinds[1], "supervise", case.name .. ": the trace says the registry is supervised")
end

-- The notice reads in the client's language, every shipped locale naming both versions; any other locale gets English.
do
	local texts = {}
	for _, locale in ipairs({ "enUS", "deDE", "esES", "esMX", "frFR", "koKR", "ptBR", "ruRU", "zhCN", "zhTW", "itIT" }) do
		local sess = newSession()
		sess.env.GetLocale = function()
			return locale
		end
		sess.env.C_AddOns = {
			GetAddOnMetadata = function()
				return "v1.15.0"
			end,
		}
		sess.env.ForeverCore = legacy
		sess:Candidate("Embedded", build(1, 16, 0))
		local notice = sess.loader.Warning() or ""
		check(
			notice:find("v1.15.0", 1, true) and notice:find("1.16.0", 1, true),
			locale .. ": the notice names both versions"
		)
		texts[locale] = notice
	end
	for _, locale in ipairs({ "deDE", "esES", "esMX", "frFR", "koKR", "ptBR", "ruRU", "zhCN", "zhTW" }) do
		check(texts[locale] ~= texts.enUS, locale .. ": the notice is translated")
	end
	equal(texts.itIT, texts.enUS, "a locale with no line falls back to English")
end

-- A standalone at the same build as the newest embedded copy is not outdated: no notice, no warning, in either
-- registry.
for _, older in ipairs({ false, "tests/fixtures/loader_revision1.lua" }) do
	local label = older and "revision 1 registry" or "this registry"
	local sess = newSession(older or nil)
	local count = 0
	sess.env.StaticPopupDialogs = {}
	sess.env.StaticPopup_Show = function()
		count = count + 1
	end
	sess.env.C_AddOns = {
		GetAddOnMetadata = function()
			return "v1.16.0"
		end,
	}
	sess.env.ForeverCoreDB = {}
	sess.env.ForeverCore = legacy
	sess:Candidate("Embedded", build(1, 16, 0))
	sess.Fire("PLAYER_LOGIN")
	sess.Fire("PLAYER_ENTERING_WORLD", true, false)
	sess.Tick()
	equal(count, 0, label .. ": an up-to-date standalone gets no notice")
	check(sess.loader.Warning == nil or sess.loader.Warning() == nil, label .. ": and no warning")
end

-- The released 1.15.0 standalone: its revision 1 loader loads first and its pre-loader table is published at file load,
-- so revision 1 adopts it as legacy at the first Begin. The newer embedded copy's supervisor shows the outdated
-- notice once at the world entry.
do
	local sess = newSession("tests/fixtures/loader_revision1.lua")
	local shown = {}
	sess.env.StaticPopupDialogs = {}
	sess.env.StaticPopup_Show = function(which, message)
		shown[#shown + 1] = which .. ":" .. tostring(message)
	end
	sess.env.C_AddOns = {
		GetAddOnMetadata = function()
			return "v1.15.0"
		end,
	}
	local supervisedStore = { outdatedNoticeVersion = "v1.14.0" }
	sess.env.ForeverCoreDB = supervisedStore
	sess.env.ForeverCore = legacy
	sess:Candidate("Embedded", build(1, 16, 0))
	equal(sess.loader.Selected() and sess.loader.Selected().mode, "legacy", "revision 1 adopts the standalone")
	equal(#sess.boots, 0, "and runs no embedded copy beside it")
	sess.Fire("PLAYER_LOGIN")
	sess.Fire("PLAYER_ENTERING_WORLD", true, false)
	sess.Tick()
	equal(#shown, 1, "the outdated notice shows once")
	check(shown[1]:find("v1.15.0", 1, true) and shown[1]:find("1.16.0", 1, true), "naming both versions")
	check(
		(sess.loader.Warning() or ""):find("delete the ForeverCore folder in Interface/AddOns", 1, true),
		"and Warning reports it"
	)
	equal(supervisedStore.outdatedNoticeVersion, "v1.15.0", "the version it was shown for is remembered")
	equal(#sess.boots, 0, "still no second runtime")
end

-- A host first loaded after login with an older standalone already adopted gets the notice without waiting for a
-- loading screen.
do
	local count = 0
	local sess = newSession(nil, function(env)
		env.IsLoggedIn = function()
			return true
		end
		env.StaticPopupDialogs = {}
		env.StaticPopup_Show = function()
			count = count + 1
		end
		env.C_AddOns = {
			GetAddOnMetadata = function()
				return "v1.15.0"
			end,
		}
	end)
	sess.env.ForeverCore = legacy
	sess:Candidate("LoadedLate", build(1, 16, 0))
	sess.Tick()
	equal(count, 1, "a host loaded after login shows the notice on the next frame")
end

-- A revision 1 registry whose hosts both first load after login hears neither event; the newer copy settles it on the
-- next frame instead of leaving it silent.
do
	local sess = newSession("tests/fixtures/loader_revision1.lua", function(env)
		env.IsLoggedIn = function()
			return true
		end
	end)
	sess:Candidate("Embedded", build(1, 16, 0))
	check(sess.loader.Selected() == nil and sess.loader.Error() == nil, "nothing has run inside the file load")
	sess.Tick()
	equal(sess.loader.Selected() and sess.loader.Selected().folder, "Embedded", "the copy activates on the next frame")
	equal(#sess.logins, 1, "with one Login")
	sess.Tick()
	equal(#sess.boots, 1, "once")
end

-- A copy that began but never sealed is named in the report, and never counts as the newer build a notice names.
do
	local sess = newSession()
	sess.loader.Begin("HalfLoaded", build(1, 20, 0))
	sess:Candidate("Whole", build(1, 16, 0))
	sess.Fire("PLAYER_LOGIN")
	equal(sess.loader.Selected() and sess.loader.Selected().folder, "Whole", "the sealed copy runs")
	local reasons = {}
	for _, entry in ipairs(sess.loader.Rejections()) do
		reasons[entry.folder .. ":" .. entry.reason] = true
	end
	check(reasons["HalfLoaded:unsealed"], "the unsealed copy is reported")

	local legacySess = newSession()
	legacySess.env.C_AddOns = {
		GetAddOnMetadata = function()
			return "v1.16.0"
		end,
	}
	legacySess.env.ForeverCore = legacy
	legacySess:Candidate("Current", build(1, 16, 0))
	legacySess.loader.Begin("HalfNewer", build(1, 20, 0))
	check(legacySess.loader.Warning() == nil, "an unsealed newer copy does not make the standalone outdated")
end

print(("embedded_loader_spec: %d checks passed"):format(checks))
