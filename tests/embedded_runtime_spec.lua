-- Real TOC Lua sources under election. This harness checks runtime ownership, not XML/client rendering.
local FakeClient = dofile("tests/fake_client.lua")
local Toc = dofile(".agents/skills/wow-forever-addon/tooling/forever_sim/toc.lua")
local checks = 0
local function check(value, message)
	assert(value, message)
	checks = checks + 1
end
local function session(order, saved)
	local env, frames = FakeClient.new()
	local loaderChunk = assert(loadfile("Core/Loader.lua"))
	setfenv(loaderChunk, env)()
	local loader = env.ForeverCoreLoader
	local boots = 0
	for _, folder in ipairs(order) do
		local build = folder == "A" and 1012001 or 1012002
		local copy = loader.Begin(folder, build, "build-" .. build)
		copy:Define(function()
			boots = boots + 1
		end)
		for _, entry in ipairs(Toc.files(".", "ForeverCore.toc")) do
			if entry.kind == "lua" and entry.path ~= "Core/Loader.lua" then
				local chunk = setfenv(assert(loadfile(entry.path)), env)
				copy:Define(function(...)
					-- The fake client has no native objective-tracker templates.
					local native = env.ObjectiveTrackerFrame
					if entry.path == "UI/TrackerQuests.lua" then
						env.ObjectiveTrackerFrame = nil
					end
					chunk(...)
					env.ObjectiveTrackerFrame = native
				end)
			end
		end
		check(copy:Seal(), "real runtime seals")
		local name = folder .. "DB"
		env[name] = saved and saved[folder] or {}
		check(loader.OfferStore(folder, name), "account store is offered")
	end
	check(env.ForeverCore == nil and boots == 0, "registration runs no runtime code")
	local callbacks = 0
	loader.OnReady(function(core)
		check(core == env.ForeverCore, "ready sees the published facade")
		core.Register("Consumer")
		-- Consumer initialization may replace its account table during its ready callback.
		if #order > 1 then
			env.ADB = { ownSetting = true }
			loader.Namespace().Store().trackerHost.scale = 1.25
		end
		callbacks = callbacks + 1
	end)
	-- Snapshot listeners: a frame born during login is not guaranteed to receive that event.
	local listeners = {}
	for _, frame in ipairs(frames) do
		if frame.events.PLAYER_LOGIN then
			listeners[#listeners + 1] = frame
		end
	end
	for _, frame in ipairs(listeners) do
		frame.scripts.OnEvent(frame, "PLAYER_LOGIN")
	end
	check(loader.Error() == nil, "real runtime boots: " .. tostring(loader.Error()))
	check(loader.LoginError() == nil, "real runtime logs in: " .. tostring(loader.LoginError()))
	check(boots == 1 and callbacks == 1, "only one runtime and consumer startup run")
	check(loader.Namespace().loginDone, "explicit Login does not depend on redispatch")
	local runtime = loader.Namespace()
	local stack = "@" .. loader.Selected().root:gsub("\\", "/") .. "/Core/Log.lua:3"
	check(runtime.SafeCallFor("ForeverCore"):Own(stack), "core errors match the elected runtime root")
	-- #791: the elected copy lives in its host's folder, but a core error is core's alone.
	local host = runtime.SafeCallFor(loader.Selected().folder)
	check(not host:Own(stack), "a core error is not filed under the host addon")
	local hostLine = "@Interface/AddOns/" .. loader.Selected().folder .. "/UI/Window.lua:5"
	check(host:Own(hostLine), "the host's own files still match the host")
	check(host:Own(stack .. "\n" .. hostLine), "a host frame calling into core still matches the host")
	check(not runtime.SafeCallFor("ForeverCore"):Own(hostLine), "a host error is not filed under core")
	local icons = {}
	local icon = runtime.Art.Icon
	runtime.Art.Icon = function(texture, file, size)
		icons[#icons + 1] = file
		return icon(texture, file, size)
	end
	runtime.Report.Show("report")
	check(icons[#icons] == loader.Selected().root .. "\\media\\Icon", "core report portrait uses elected media")
	runtime.ProfileCode.Read = function()
		return { stats = { one = 1 } }
	end
	runtime.ProfileCode.Link = function()
		return "https://wow.cjber.dev/profile"
	end
	runtime.Profile.Show()
	check(icons[#icons] == loader.Selected().root .. "\\media\\Icon", "profile portrait uses elected media")
	runtime.Art.Icon = icon

	if #order > 1 then
		check(env.ADB.ownSetting, "mirroring preserves the consumer's own account settings")
		check(
			loader.Namespace().Store().trackerHost.scale == 1.25,
			"post-ready reconciliation keeps live runtime edits"
		)
	end

	check(env.ForeverCoreDB == nil, "embedded runtime creates no standalone saved variable")
	check(
		env.ForeverCore.Art.Marker(1) == loader.Selected().root .. "\\media\\Numbers\\1",
		"markers use the elected copy's media"
	)
	check(
		env.ForeverCore.Art.Ring() == loader.Selected().root .. "\\media\\Numbers\\Ring",
		"rings use the elected copy's media"
	)

	check(
		env.ForeverCore.Register("Consumer") == env.ForeverCore.Register("Consumer"),
		"consumer registration is stable after election"
	)
	for _, folder in ipairs(order) do
		check(env[folder .. "DB"].ForeverCoreStore == loader.Namespace().Store(), "each survivor owns a mirror")
	end
	loader.Activate()
	check(boots == 1 and callbacks == 1, "repeated activation cannot duplicate runtime or callbacks")
	return env, loader
end
for _, order in ipairs({ { "A", "B" }, { "B", "A" } }) do
	local env, loader = session(order)
	check(loader.Selected().folder == "B", "newest runtime wins either load order")
	loader.Namespace().Store().trackerHost.scale = 1.7
	-- A fresh session only has the older survivor, as after the winning host is uninstalled.
	local survivor, surviving = session({ "A" }, { A = env.ADB })
	check(surviving.Selected().folder == "A", "the surviving copy boots after winner removal")
	check(surviving.Namespace().Store().trackerHost.scale == 1.7, "settings survive winner removal")
	check(survivor.ADB.ForeverCoreStore.trackerHost.scale == 1.7, "the survivor keeps its own saved state")
end
print(("embedded_runtime_spec: %d checks passed"):format(checks))
