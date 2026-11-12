"""Parse packaged TOC and XML load graphs with the pinned Lua 5.1 client parser."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import toc


def loaded_lua(root: Path) -> list[Path]:
    toc_path = next(iter(toc.toc_files(root)))
    return [path for path in toc.loaded_files(toc_path, root) if path.suffix.lower() == ".lua"]


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
    except (OSError, StopIteration, ValueError) as error:
        return [f"{root}: invalid TOC/XML load graph: {error}"]
    problems = []
    for path in files:
        result = subprocess.run([str(parser), "-p", str(path)], capture_output=True, text=True)
        if result.returncode:
            problems.append(result.stderr.strip() or f"{path}: Lua 5.1 parse failed")
    return problems
