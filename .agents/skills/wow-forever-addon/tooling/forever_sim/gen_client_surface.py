#!/usr/bin/env python3
"""Generate client_surface.lua: the cvar defaults and each widget type's scripts, as the Forever client reports them.

The client is the only full source for both. Its UI source names the cvars it reads but not their defaults, and
names every script but not which widget type takes which; the API annotations miss scripts the client accepts (a
FontString takes OnEnter, which every StaticPopup sets). ForeverProbe (cjber/forever-dev) records both at login in
ForeverProbeDB.clientSurface: every cvar from ConsoleGetAllCommands with C_CVar.GetCVarInfo's default, each cvar
the UI reads that the list leaves out, the ones the client does not define, and for each widget type the client can
make, every script name HasScript accepts. This turns one such dump into the data file the
simulator answers from, so an unknown cvar or script reads as it does in the client, never from a hand list.

    python3 .agents/skills/wow-forever-addon/tooling/forever_sim/gen_client_surface.py \\
        --probe ~/path/WTF/Account/ACCOUNT/SavedVariables/ForeverProbe.lua
    python3 .agents/skills/wow-forever-addon/tooling/forever_sim/sync.py manifest

The file is committed, like restrictions.txt: regenerate it from a fresh dump after a client patch, never by hand.
"""

import argparse
import os
import subprocess
import textwrap
from pathlib import Path

OUTPUT = Path(__file__).resolve().with_name("client_surface.lua")

READER = """
local path = assert(os.getenv("FOREVER_PROBE_FILE"), "no probe file")
assert(loadfile(path))()
local surface = assert(ForeverProbeDB and ForeverProbeDB.clientSurface, "the dump has no ForeverProbeDB.clientSurface")
assert(not surface.error, "the probe failed in the client: " .. tostring(surface.error))
for half, err in pairs(surface.errors or {}) do
	error("the probe's " .. half .. " half failed in the client: " .. tostring(err))
end
-- Every byte outside printable ASCII, and the backslash, as a Lua \\ddd escape: lines split only on "\\n" and the
-- Python side writes each value into a Lua literal as is.
local function esc(value)
	return (tostring(value):gsub(".", function(c)
		local b = c:byte()
		if b < 32 or b > 126 or c == "\\\\" then
			return string.format("\\\\%03d", b)
		end
	end))
end
print("interface\\t" .. tostring(surface.build))
-- A cvar starts at its default; one the client reports no default for starts at the value it reported.
local function usable(value)
	return type(value) == "string" and value ~= "<secret>" and value or nil
end
for name, info in pairs(surface.cvars or {}) do
	local start = usable(info.default) or usable(info.value)
	if start then
		print("cvar\\t" .. esc(name) .. "\\t" .. esc(start))
	else
		print("nodefault\\t" .. esc(name) .. "\\t" .. esc(info.error or info.default))
	end
end
for _, name in ipairs(surface.undefinedCvars or {}) do
	print("undefined\\t" .. esc(name))
end
for kind, names in pairs(surface.scripts or {}) do
	print("widget\\t" .. esc(kind))
	for _, name in ipairs(names) do
		print("script\\t" .. esc(kind) .. "\\t" .. esc(name))
	end
end
for kind, err in pairs(surface.failedWidgets or {}) do
	print("failed\\t" .. esc(kind) .. "\\t" .. esc(err))
end
"""


def read(path: Path) -> tuple[str, dict[str, str], dict[str, list[str]], dict[str, str], dict[str, str], list[str]]:
    """The dump's interface, cvar defaults (Lua \\ddd escaped), scripts per widget type, and what it could not read."""
    result = subprocess.run(
        ["luajit", "-e", READER],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env={**os.environ, "FOREVER_PROBE_FILE": str(path)},
    )
    if result.returncode:
        raise SystemExit(f"could not read the probe at {path}:\n" + result.stderr)
    interface, cvars, scripts, nodefault, failed, undefined = "", {}, {}, {}, {}, []
    for line in result.stdout.split("\n"):
        kind, _, rest = line.partition("\t")
        if kind == "interface":
            interface = rest
        elif kind == "cvar":
            name, _, value = rest.partition("\t")
            cvars[name] = value
        elif kind == "nodefault":
            name, _, value = rest.partition("\t")
            nodefault[name] = value
        elif kind == "undefined":
            undefined.append(rest)
        elif kind == "widget":
            scripts.setdefault(rest, [])
        elif kind == "script":
            widget, _, name = rest.partition("\t")
            scripts[widget].append(name)
        elif kind == "failed":
            widget, _, error = rest.partition("\t")
            failed[widget] = error
    if not cvars or not scripts:
        raise SystemExit(f"{path}: the clientSurface record has no cvars or no scripts")
    return interface, cvars, scripts, nodefault, failed, undefined


def quote(value: str) -> str:
    """A Lua string literal in StyLua's quote style; the reader already wrote backslashes and control bytes as \\ddd."""
    if '"' in value and "'" not in value:
        return "'" + value + "'"
    return '"' + value.replace('"', '\\"') + '"'


def render(interface: str, cvars: dict, scripts: dict, nodefault: dict, failed: dict, undefined: list) -> str:
    lines = [
        "-- Generated by gen_client_surface.py from a ForeverProbe clientSurface dump (cjber/forever-dev), not by",
        f"-- hand. Interface {interface}. cvars: every console variable the client defines, name -> starting value",
        "-- (its default, or the value the client reported when it reports no default).",
        "-- scripts: for each widget type the client makes, every script HasScript accepts (the full set).",
    ]
    if nodefault:
        listed = textwrap.wrap(", ".join(sorted(nodefault)) + ".", 116, break_on_hyphens=False)
        lines += ["-- Cvars the client reports no value for, left out:"] + [f"--   {line}" for line in listed]
    lines += ["return {", f"\tinterface = {int(interface) if interface.isdigit() else quote(interface)},"]
    lines.append(
        "\t-- Widget types the probe could not make or ask (no HasScript), with why; they take their parent's scripts."
    )
    lines.append("\tunmade = {")
    lines += [f"\t\t{kind} = {quote(error)}," for kind, error in sorted(failed.items())]
    lines += ["\t},", "\tcvars = {"]
    lines += [f"\t\t[{quote(name)}] = {quote(cvars[name])}," for name in sorted(cvars, key=str.lower)]
    lines += ["\t},"]
    lines.append("\t-- Cvars the UI reads that the client does not define: GetCVar answers nil for them.")
    lines.append("\tundefined = {")
    lines += [f"\t\t{quote(name)}," for name in sorted(set(undefined), key=str.lower)]
    lines += ["\t},", "\tscripts = {"]
    for kind in sorted(scripts):
        lines.append(f"\t\t{kind} = {{")
        lines += [f"\t\t\t{quote(name)}," for name in sorted(scripts[kind])]
        lines.append("\t\t},")
    lines += ["\t},", "}", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--probe", type=Path, required=True, help="a ForeverProbe.lua SavedVariables file")
    args = parser.parse_args()
    data = read(args.probe)
    OUTPUT.write_text(render(*data))
    print(f"{len(data[1])} cvars, {len(data[2])} widget types -> {OUTPUT}")


if __name__ == "__main__":
    main()
