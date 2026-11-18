-- ForeverAuras import strings from Lua tables and back, with the installed addon's own libraries.
-- luajit fa.lua encode <Auras/X.lua> [id]   prints an import string for each spec the file declares with
--                                          ns.Aura({d = data, c = children?}), or only the one whose d.id is id
-- luajit fa.lua decode <file|->     prints the payload of an import string as a Lua table
local FA = os.getenv("FA_DIR") or (os.getenv("HOME")
  .. "/Games/battlenet/drive_c/Program Files (x86)/World of Warcraft/_forever_/Interface/AddOns/ForeverAuras")

local libs = {}
LibStub = setmetatable({
  NewLibrary = function(_, name) libs[name] = libs[name] or {}; return libs[name], nil end,
  GetLibrary = function(_, name) return libs[name] end,
}, {__call = function(self, name) return libs[name] end})
dofile(FA .. "/Libs/LibDeflate/LibDeflate.lua")
dofile(FA .. "/Libs/LibSerialize/LibSerialize.lua")
local LibDeflate, LibSerialize = libs.LibDeflate, libs.LibSerialize
assert(LibDeflate and LibSerialize, "libraries not found under " .. FA)

local function addonVersion()
  local f = io.open(FA .. "/ForeverAuras.toc")
  local v = f and f:read("*a"):match("## Version:%s*([^\r\n]+)") or "1.0.0"
  if f then f:close() end
  return v
end

local function internalVersion()
  local f = assert(io.open(FA .. "/ForeverAuras.lua"))
  local v = tonumber(f:read("*a"):match("local internalVersion = (%d+)"))
  f:close()
  return v
end

local function dump(v, indent)
  indent = indent or ""
  if type(v) == "string" then return string.format("%q", v) end
  if type(v) ~= "table" then return tostring(v) end
  local keys = {}
  for k in pairs(v) do keys[#keys + 1] = k end
  table.sort(keys, function(a, b)
    if type(a) == type(b) then return a < b end
    return type(a) == "number"
  end)
  local out, inner = {"{"}, indent .. "  "
  for _, k in ipairs(keys) do
    local key = type(k) == "string" and k:match("^[%a_][%w_]*$") and k or "[" .. dump(k) .. "]"
    out[#out + 1] = inner .. key .. " = " .. dump(v[k], inner) .. ","
  end
  out[#out + 1] = indent .. "}"
  return table.concat(out, "\n")
end

local mode, path = arg[1], arg[2]
local function encode(spec)
  local iv = internalVersion()
  local function stamp(d) d.internalVersion = d.internalVersion or iv end
  stamp(spec.d)
  for _, child in ipairs(spec.c or {}) do stamp(child) end
  local payload = {m = "d", d = spec.d, c = spec.c, v = spec.c and 2000 or 1421, s = addonVersion()}
  local serialized = LibSerialize:SerializeEx({errorOnUnserializableType = false}, payload)
  local compressed = LibDeflate:CompressDeflate(serialized, {level = 9})
  io.write("!WA:2!", LibDeflate:EncodeForPrint(compressed), "\n")
end

if mode == "encode" and path then
  local specs = {}
  assert(loadfile(path))("DevAuras", {Aura = function(spec) specs[#specs + 1] = spec end})
  for _, spec in ipairs(specs) do
    if not arg[3] or spec.d.id == arg[3] then encode(spec) end
  end
elseif mode == "decode" and path then
  local f = path == "-" and io.stdin or assert(io.open(path))
  local s = f:read("*a"):gsub("%s", "")
  local body = assert(s:match("^!%u%u:2!(.+)$"), "not a version 2 import string")
  local decompressed = assert(LibDeflate:DecompressDeflate(assert(LibDeflate:DecodeForPrint(body))))
  local ok, t = LibSerialize:Deserialize(decompressed)
  assert(ok, t)
  io.write(dump(t), "\n")
else
  io.stderr:write("usage: luajit fa.lua encode <Auras/X.lua> [id] | decode <file|->\n")
  os.exit(2)
end
