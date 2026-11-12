#!/usr/bin/env python3
"""Parse every Lua file reachable from an addon TOC with the WoW Lua 5.1 parser."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def toc_files(root: Path) -> list[Path]:
    toc = next(root.glob("*.toc"))
    files: list[Path] = []
    pending = [root / raw.strip().replace("\\", "/") for raw in toc.read_text(encoding="utf-8-sig").splitlines() if raw.strip() and not raw.strip().startswith("#")]
    seen: set[Path] = set()
    while pending:
        path = pending.pop(0)
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        if path.suffix.lower() == ".lua":
            files.append(path)
        elif path.suffix.lower() == ".xml":
            try:
                tree = ET.parse(path)
            except ET.ParseError as error:
                raise ValueError(f"{path}: invalid XML: {error}") from error
            for element in tree.iter():
                for attribute in ("file", "virtualFile"):
                    name = element.attrib.get(attribute)
                    if name:
                        pending.append(path.parent / name.replace("\\", "/"))
    return files


def toc_lua(root: Path) -> list[Path]:
    return toc_files(root)


def main(argv: list[str]) -> int:
    parser = Path(os.environ.get("LUA51_LUAC", "luac5.1"))
    if not parser.exists() and not parser.is_absolute():
        found = shutil.which(str(parser))
        if found:
            parser = Path(found)
    if not parser.exists():
        print("LUA51_LUAC must point to the pinned Lua 5.1 luac", file=sys.stderr)
        return 2
    roots = [Path(arg) for arg in argv] or [Path.cwd()]
    try:
        files = [path for root in roots for path in (toc_lua(root) if root.is_dir() else [root])]
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    for path in files:
        result = subprocess.run([str(parser), "-p", str(path)], capture_output=True, text=True)
        if result.returncode:
            print(result.stderr.strip() or f"{path}: Lua 5.1 parse failed", file=sys.stderr)
            return result.returncode
    print(f"Lua 5.1 parser: checked {len(files)} TOC Lua files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
