#!/usr/bin/env python3
"""Print the toolchain action's cache keys and runtime versions as GITHUB_OUTPUT lines.

    pins.py <toolchain.json> <tool cache>

The path is the manifest the action resolved from its `manifest` input, the calling repository's toolchain.json, never
a file beside this package. Each key hashes that tool's manifest entries, so a bump moves the cache as well as the
download. The runtimes are exported so a workflow passes the manifest's Python, Node and Bun versions to their setup
actions.
"""

import hashlib
import json
import sys

GROUPS = {
    "lua": ("lua51", "luajit", "luacheck", "argparse", "luafilesystem"),
    "luals": ("luals",),
    "stylua": ("stylua",),
    "gitleaks": ("gitleaks",),
}


def main(manifest_path: str, cache: str) -> int:
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    for name, entries in GROUPS.items():
        pins = {entry: manifest["tools"][entry] for entry in entries}
        blob = json.dumps(pins, sort_keys=True).encode("utf-8")
        print(f"{name}_key={hashlib.sha256(blob).hexdigest()[:24]}")
    print(f"lua_prefix={cache}/toolchain/lua")
    for name, entry in manifest["runtimes"].items():
        print(f"{name}={entry['version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
