-- Drives a generated ForeverCoreRun.lua (arg[1]) through each way an addon's files can start, with a fake client
-- frame registry, and checks that each frame the files registered gets every loading event it missed exactly once.
local runPath = assert(arg[1], "usage: luajit run_replay_harness.lua <ForeverCoreRun.lua>")

local function Session(opts)
	local frames, queued = {}, {}
	local env = setmetatable({}, { __index = _G })
	env.CreateFrame = function()
		local frame = { events = {}, scripts = {} }
		function frame:RegisterEvent(event)
			self.events[event] = true
		end
		function frame:UnregisterEvent(event)
			self.events[event] = nil
		end
		function frame:SetScript(name, script)
			self.scripts[name] = script
		end
		function frame:GetScript(name)
			return self.scripts[name]
		end
		frames[#frames + 1] = frame
		return frame
	end
	env.GetFramesRegisteredForEvent = function(event)
		local out = {}
		for _, frame in ipairs(frames) do
			if frame.events[event] then
				out[#out + 1] = frame
			end
		end
		return unpack(out)
	end
	env.C_Timer = {
		After = function(_, callback)
			queued[#queued + 1] = callback
		end,
	}
	env.IsLoggedIn = function()
		return opts.loggedIn == true
	end
	local ready
	env.ForeverCoreLoader = {
		OnReady = function(callback)
			if opts.inline then
				callback({}, {})
			else
				ready = callback
			end
		end,
		Seen = function(event)
			return event == "PLAYER_ENTERING_WORLD" and opts.worldSeen == true
		end,
		WorldEntry = function()
			return true, false
		end,
	}
	local got = {}
	local order = {}
	local host = {
		ForeverCoreHostChunks = {
			-- A file waiting for its own addon's load, as ns.OnFilesLoaded does: on the runner's queue when there is
			-- one, else through the client, which calls back at ADDON_LOADED.
			function(_, ns)
				local function callback()
					order[#order + 1] = "callback"
				end
				if ns.ForeverCoreHostAfter then
					table.insert(ns.ForeverCoreHostAfter, callback)
				else
					order[#order + 1] = "client"
				end
				order[#order + 1] = "first file"
			end,
			function(addon)
				order[#order + 1] = "last file"
				local listener = env.CreateFrame()
				for _, event in ipairs({ "ADDON_LOADED", "PLAYER_LOGIN", "PLAYER_ENTERING_WORLD" }) do
					listener:RegisterEvent(event)
				end
				listener:SetScript("OnEvent", function(_, event, a, b)
					got[#got + 1] = event .. ":" .. tostring(a) .. ":" .. tostring(b)
				end)
				return addon
			end,
		},
	}
	local chunk = assert(loadfile(runPath))
	setfenv(chunk, env)("Demo", host)
	local session = { got = got, order = order, host = host }
	function session.Activate()
		ready({}, {})
	end
	function session.Fire(event, ...)
		local listeners = { env.GetFramesRegisteredForEvent(event) }
		for _, frame in ipairs(listeners) do
			frame.scripts.OnEvent(frame, event, ...)
		end
	end
	function session.Tick()
		local run = queued
		queued = {}
		for _, callback in ipairs(run) do
			callback()
		end
	end
	return session
end

local function expect(session, wanted, label)
	local text = table.concat(session.got, " ")
	assert(text == wanted, label .. ": expected [" .. wanted .. "], got [" .. text .. "]")
end

-- Activated at PLAYER_LOGIN: the addon's ADDON_LOADED and the login itself, nothing for a world entry still to come.
local login = Session({})
login.Activate()
expect(login, "ADDON_LOADED:Demo:nil PLAYER_LOGIN:nil:nil", "activated at login")
-- The client already counts the addon as loaded, so a file waiting for its own load is called by the runner, after
-- the last file and not inside the file that asked.
assert(
	table.concat(login.order, ", ") == "first file, last file, callback",
	"a file's own-load callback runs after every file, got: " .. table.concat(login.order, ", ")
)
assert(login.host.ForeverCoreHostAfter == nil, "the queue is gone once it has run")
assert(login.host.ForeverCoreHostDeferred == true, "files run at activation stay marked as past the login")
assert(login.host.ForeverCoreHostIncomplete == nil, "every wrapped file registered")

-- Activated after the first world entry (a missed login, or after combat): the world entry with its arguments too.
local world = Session({ worldSeen = true, loggedIn = true })
world.Activate()
expect(
	world,
	"ADDON_LOADED:Demo:nil PLAYER_LOGIN:nil:nil PLAYER_ENTERING_WORLD:true:false",
	"activated after the world entry"
)

-- The standalone already running at startup: the files run inline and the client delivers every event itself.
local startup = Session({ inline = true })
assert(table.concat(startup.order, ", ") == "client, first file, last file", "inline, the client's own wait is used")
assert(startup.host.ForeverCoreHostDeferred == nil, "files run inline at startup are not marked")
startup.Fire("ADDON_LOADED", "Demo")
startup.Tick()
expect(startup, "ADDON_LOADED:Demo:nil", "inline at startup misses nothing")

-- A load-on-demand host joining a running copy after login: inline, its own ADDON_LOADED arrives from the client,
-- then the login and world entry it missed follow on the next frame, once.
local late = Session({ inline = true, loggedIn = true, worldSeen = true })
expect(late, "", "nothing is delivered inside the file load")
late.Fire("ADDON_LOADED", "Other")
late.Tick()
expect(late, "ADDON_LOADED:Other:nil", "another addon's load delivers nothing missed")
late.Fire("ADDON_LOADED", "Demo")
expect(late, "ADDON_LOADED:Other:nil ADDON_LOADED:Demo:nil", "the host's own ADDON_LOADED comes from the client")
late.Tick()
expect(
	late,
	"ADDON_LOADED:Other:nil ADDON_LOADED:Demo:nil PLAYER_LOGIN:nil:nil PLAYER_ENTERING_WORLD:true:false",
	"then the missed login and world entry, once"
)
late.Fire("ADDON_LOADED", "Demo")
late.Tick()
assert(#late.got == 5, "no second delivery")

print("run_replay_harness: passed")
