#!/usr/bin/env python3
"""Parse every Lua file reachable from an addon TOC with the WoW Lua 5.1 parser."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def toc_lua(root: Path) -> list[Path]:
    toc = next(root.glob("*.toc"))
    files: list[Path] = []
    for raw in toc.read_text(encoding="utf-8-sig").splitlines():
        name = raw.strip()
        if name and not name.startswith("#") and name.lower().endswith(".lua"):
            files.append(root / name.replace("\\", "/"))
    return files


def main(argv: list[str]) -> int:
    parser = Path(os.environ.get("LUA51_LUAC", "luac5.1"))
    if not parser.exists() and not parser.is_absolute():
        found = subprocess.run(["sh", "-c", f"command -v {parser}"], capture_output=True, text=True).stdout.strip()
        if found:
            parser = Path(found)
    if not parser.exists():
        print("LUA51_LUAC must point to the pinned Lua 5.1 luac", file=sys.stderr)
        return 2
    roots = [Path(arg) for arg in argv] or [Path.cwd()]
    files = [path for root in roots for path in (toc_lua(root) if root.is_dir() else [root])]
    for path in files:
        result = subprocess.run([str(parser), "-p", str(path)], capture_output=True, text=True)
        if result.returncode:
            print(result.stderr.strip() or f"{path}: Lua 5.1 parse failed", file=sys.stderr)
            return result.returncode
    print(f"Lua 5.1 parser: checked {len(files)} TOC Lua files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
