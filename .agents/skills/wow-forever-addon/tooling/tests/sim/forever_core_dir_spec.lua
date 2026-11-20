-- Sim.foreverCoreDir: the checkout beside a source tree, none beside a package that embeds ForeverCore.
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
local Sim = dofile(here .. "../../forever_sim/sim.lua")

local mktemp = assert(io.popen("mktemp -d"))
local root = assert(mktemp:read("*l"), "mktemp -d made no folder") .. "/"
mktemp:close()
os.execute("mkdir -p '" .. root .. "Libs/ForeverCore'")

local expected = os.getenv("FOREVER_CORE")
if expected == nil or expected == "" then
	expected = "../forever-core"
end
assert(Sim.foreverCoreDir(root) == expected, "a source tree loads the checkout")

local bundle = assert(io.open(root .. "Libs/ForeverCore/bundle.json", "wb"))
bundle:write("{}")
bundle:close()
assert(Sim.foreverCoreDir(root) == nil, "an embedded package loads no checkout")

os.execute("rm -r -- '" .. root .. "'")
print("ok forever_core_dir_spec")
