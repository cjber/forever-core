-- luacheck: read globals scenario
-- Every published Forever addon and ForeverCore in one client, exercised together. tools/suite_load.py names the
-- checkouts in FOREVER_SUITE as `dir=Folder` pairs in load order, ForeverCore first.
local suite = assert(os.getenv("FOREVER_SUITE"), "run this through python3 tools/suite_load.py")
local addons = {}
for pair in suite:gmatch("[^;]+") do
	local dir, folder = pair:match("^(.+)=([%w_]+)$")
	addons[#addons + 1] = { assert(dir, "bad FOREVER_SUITE entry: " .. pair), folder }
end

scenario(
	"every Forever addon loaded together, in and out of combat and across a reload",
	{ addon = false },
	function(sim)
		for _, entry in ipairs(addons) do
			sim:addon(entry[1], entry[2])
		end
		-- The exercise itself can stop on an error in one addon, and that must not hide a consumer that never started:
		-- a Core/Require.lua refusal is one UIErrorsFrame line and no Lua error, so only Register can show it (#666).
		local ok, result = pcall(sim.exercise, sim)
		-- The reloaded client is the one to ask when the exercise finished; its pre-reload client registered the same
		-- addons, so a run that stopped early still answers.
		local after = ok and result or sim
		local core = after.G.ForeverCore
		assert(type(core) == "table", "ForeverCore did not publish itself in the reloaded client")
		assert(type(core.Registered) == "function", "ForeverCore does not publish Registered")
		local missing = {}
		for _, entry in ipairs(addons) do
			local folder = entry[2]
			if folder ~= "ForeverCore" and not core.Registered(folder) then
				missing[#missing + 1] = ("%s did not register with ForeverCore (it refused to start on this core)"):format(
					folder
				)
			end
		end
		if #missing > 0 then
			error(table.concat(missing, "\n"), 0)
		end
		if not ok then
			error(result, 0)
		end
		-- Native boot and panel errors have no addon attribution and must fail this suite too (#714).
		sim:expectNoErrors()
		after:expectNoErrors()
	end
)
