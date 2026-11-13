#!/usr/bin/env python3
"""Generate `client_names.txt`: the client function names the Forever client answers.

LuaLS checks against the retail `vscode-wow-api` annotations, which declare functions this client lacks; calling one
fails in game with `attempt to call a nil value`. `forever_tools/client_calls.py` checks every addon call against this
file instead.

The names come from the same pinned Blizzard UI source the simulator fetches (`forever_sim/fetch.py`, never a second
pin), and only names that can be called:

* every documented `C_X.Y` and documented global function, read through the simulator's own
  `Blizzard_APIDocumentationGenerated` loader (`forever_sim/docs.lua`);
* every global function Blizzard's own UI Lua defines, every bare global it calls, and every `C_X.Y` it reads,
  documented or not. Global tables, named frames, global strings, colors and constants are not callable, so they stay
  out: a plain read of one is not the error this list exists for;
* optionally, a `ForeverProbe.lua` SavedVariables dump (`--probe`), whose `ForeverProbeDB.api` carries the client's
  build, `globals` and `namespaces`. This is the only source for a real client function the documentation and
  Blizzard's Lua never name.

    python3 tools/gen_forever_api.py                  # fetch the pinned UI source, write client_names.txt
    python3 tools/gen_forever_api.py --ui DIR         # read an existing UI checkout (tests use a fixture)
    python3 tools/gen_forever_api.py --probe ForeverProbe.lua
    python3 tools/gen_forever_api.py --check          # fail when the committed file differs from a fresh generation

The file is committed: regenerate it when the UI pin moves or a probe arrives, and never edit it by hand.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLING = ROOT / ".agents" / "skills" / "wow-forever-addon" / "tooling"
sys.path.insert(0, str(TOOLING))

from forever_sim.fetch import BUILD, UI_REVISION, cache_dir, fetch_ui  # noqa: E402
from forever_tools import client_calls, luadata  # noqa: E402

OUTPUT = TOOLING / "forever_tools" / "client_names.txt"
DOCUMENTATION = Path("Interface") / "AddOns" / "Blizzard_APIDocumentationGenerated"
DOCUMENT_SCRIPT = """
package.path = os.getenv("FOREVER_SIM_DIR") .. "/?.lua;" .. package.path
local docs = require("docs").load(os.getenv("FOREVER_SIM_UI"))
for _, system in ipairs(docs.systems) do
	local namespace = system.Namespace
	for _, f in ipairs(system.Functions or {}) do
		print(namespace and (namespace .. "." .. f.Name) or f.Name)
	end
end
"""


def documented(ui: Path) -> set[str]:
    """Every documented `C_X.Y` and global function, through the simulator's documentation loader."""
    luajit = shutil.which("luajit")
    if luajit is None:
        raise SystemExit("luajit is needed to read Blizzard_APIDocumentationGenerated (forever_sim/docs.lua)")
    result = subprocess.run(
        [luajit, "-e", DOCUMENT_SCRIPT],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env={
            **os.environ,
            "FOREVER_SIM_DIR": str(TOOLING / "forever_sim"),
            "FOREVER_SIM_UI": str(ui),
        },
    )
    if result.returncode:
        raise SystemExit("could not read the API documentation:\n" + result.stderr)
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def blizzard(ui: Path) -> set[str]:
    """Every global function Blizzard's own UI Lua defines or calls, and every `C_X.Y` it reads.

    A name the client's own UI uses is one the client answers: `ClearOverrideBindings` is called from Blizzard's own
    code, and `C_Map.GetBestMapForUnit` may be read into a local before it is called. A global table, a named frame, a
    global string or a constant is not callable and is left out.
    """
    names: set[str] = set()
    for path in sorted(ui.rglob("*.lua")):
        if any(part.startswith(".") for part in path.relative_to(ui).parts):
            continue
        try:
            found = client_calls.analysis(path.read_text(encoding="utf-8", errors="replace"))
        except client_calls.LuaSyntaxError as error:
            raise SystemExit(f"{path}: {error}") from error
        names.update(found.functions)
        names.update(read.name for read in found.reads if read.name and read.call)
        names.update(read.qualified for read in found.reads if read.qualified)
    return names


def probe(path: Path) -> tuple[str, set[str]]:
    """The build and names in a ForeverProbe SavedVariables dump."""
    tables, _ = luadata.parse_tables(path.read_text(encoding="utf-8"))
    db = tables.get("ForeverProbeDB")
    if db is None or not isinstance(db.keyed.get("api"), luadata.Table):
        raise SystemExit(f"{path}: no ForeverProbeDB.api table")
    api = db.keyed["api"]
    build = api.keyed.get("build")
    if not isinstance(build, str):
        raise SystemExit(f"{path}: ForeverProbeDB.api.build is not a string")
    globals_ = api.keyed.get("globals")
    namespaces = api.keyed.get("namespaces")
    if not isinstance(globals_, luadata.Table) or not isinstance(namespaces, luadata.Table):
        raise SystemExit(f"{path}: ForeverProbeDB.api needs globals and namespaces tables")
    names = {name for name in globals_.array if isinstance(name, str)}
    for namespace, functions in namespaces.keyed.items():
        if not isinstance(namespace, str) or not isinstance(functions, luadata.Table):
            raise SystemExit(f"{path}: ForeverProbeDB.api.namespaces has a malformed entry")
        names.update(f"{namespace}.{function}" for function in functions.array if isinstance(function, str))
    return build, names


def render(names: set[str], probe_build: str | None) -> str:
    header = [
        "# The Forever client's callable names, one per line, sorted: generated by tools/gen_forever_api.py.",
        "# Never edit this file by hand; regenerate it from the pinned data.",
        f"# Blizzard UI source {UI_REVISION} (Gethe/wow-ui-source, the Forever build's), build {BUILD}.",
        "# Every documented C_X.Y and global function, every global function Blizzard's own UI defines or calls,",
        "# and every C_X.Y that UI reads, documented or not. Global tables, named frames, strings, colors and",
        "# constants are not callable and stay out: a plain read of one is not a nil call.",
    ]
    if probe_build:
        header.append(f"# Merged with a ForeverProbe dump from build {probe_build}.")
    return "\n".join([*header, *sorted(names)]) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ui", type=Path, default=None, help="an existing Blizzard UI checkout to read")
    parser.add_argument("--cache", type=Path, default=None, help="where to fetch the UI source")
    parser.add_argument("--offline", action="store_true", help="fail instead of downloading the UI source")
    parser.add_argument("--probe", type=Path, default=None, help="a ForeverProbe.lua SavedVariables dump")
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true", help="fail when --out differs from a fresh generation")
    args = parser.parse_args(argv)
    cache = args.cache or cache_dir()
    ui = args.ui or fetch_ui(cache, args.offline)
    if not (ui / DOCUMENTATION).is_dir():
        raise SystemExit(f"{ui} has no {DOCUMENTATION}; is it the Blizzard UI source?")
    names = documented(ui)
    names.update(blizzard(ui))
    probe_build = None
    if args.probe:
        probe_build, merged = probe(args.probe)
        names.update(merged)
    text = render(names, probe_build)
    if args.check:
        committed = args.out.read_text(encoding="utf-8") if args.out.is_file() else ""
        if committed != text:
            print(f"{args.out}: differs from a fresh generation; run python3 tools/gen_forever_api.py", file=sys.stderr)
            return 1
        print(f"{args.out}: matches a fresh generation of {len(names)} client names")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"{args.out}: {len(names)} client names from UI source {UI_REVISION[:12]} and build {BUILD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
