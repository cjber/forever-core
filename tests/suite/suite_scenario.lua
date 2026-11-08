-- luacheck: read globals scenario
-- Every published Forever addon and ForeverCore in one client, exercised together. tools/suite_load.py names the
-- checkouts in FOREVER_SUITE as `dir=Folder` pairs in load order; ForeverCore loads last, as its OptionalDeps on the
-- others make the client load it.
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
		sim:addon(".", "ForeverCore")
		sim:exercise()
	end
)
