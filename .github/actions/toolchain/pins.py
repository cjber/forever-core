#!/usr/bin/env python3
"""Print the toolchain action's cache keys and runtime versions as GITHUB_OUTPUT lines.

    pins.py <tools/toolchain.json> <tool cache>

The path is the manifest the action resolved from its `manifest` input, the calling repository's
`tools/toolchain.json`, never a file beside this package. Each key hashes that tool's manifest entries and the action's
own build inputs, the `build.sh` and `install.sh` beside this file, so a bump and a change to either script each move the
cache as well as the download. The runtimes are exported so a workflow passes the manifest's Python, Node and Bun
versions to their setup actions.
"""

import hashlib
import json
import sys
from pathlib import Path

ACTION_DIR = Path(__file__).resolve().parent
BUILD_INPUTS = ("build.sh", "install.sh")

GROUPS = {
    "lua": ("lua51", "luajit", "luacheck", "argparse", "luafilesystem"),
    "luals": ("luals",),
    "stylua": ("stylua",),
    "gitleaks": ("gitleaks",),
}


def build_inputs() -> bytes:
    """The bytes of the scripts that build a cache, so an edited script never restores an entry it did not build."""
    parts = []
    for name in BUILD_INPUTS:
        parts.append(name.encode("utf-8"))
        parts.append((ACTION_DIR / name).read_bytes())
    return b"\0".join(parts)


def main(manifest_path: str, cache: str) -> int:
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    scripts = build_inputs()
    for name, entries in GROUPS.items():
        pins = {entry: manifest["tools"][entry] for entry in entries}
        blob = json.dumps(pins, sort_keys=True).encode("utf-8") + b"\0" + scripts
        print(f"{name}_key={hashlib.sha256(blob).hexdigest()[:24]}")
    print(f"lua_prefix={cache}/toolchain/lua")
    for name, entry in manifest["runtimes"].items():
        print(f"{name}={entry['version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
