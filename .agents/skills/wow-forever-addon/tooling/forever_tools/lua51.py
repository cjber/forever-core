"""Parse packaged TOC and XML load graphs with the pinned Lua 5.1 client parser."""

from __future__ import annotations

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from . import toc


def loaded_lua(root: Path) -> list[Path]:
    root = root.resolve()
    tocs = toc.toc_files(root)
    if not tocs:
        raise ValueError("No addon TOC found")
    files = set()
    for toc_path in tocs:
        files.update(toc.loaded_files(toc_path, root))
    return sorted(path for path in files if path.suffix.lower() == ".lua")


def parser_path() -> Path | None:
    configured = os.environ.get("LUA51_LUAC", "luac5.1")
    path = Path(configured)
    return path if path.is_file() else (Path(found) if (found := shutil.which(configured)) else None)


def check(root: Path) -> list[str]:
    parser = parser_path()
    if parser is None:
        return ["Lua 5.1 parser is unavailable; set LUA51_LUAC to the pinned luac5.1"]
    try:
        files = loaded_lua(root)
    except (OSError, ValueError, ET.ParseError) as error:
        return [f"{root}: invalid TOC/XML load graph: {error}"]
    problems = []
    for path in files:
        result = subprocess.run([str(parser), "-p", str(path)], capture_output=True, text=True)
        if result.returncode:
            problems.append(result.stderr.strip() or f"{path}: Lua 5.1 parse failed")
    return problems
