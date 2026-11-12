"""Parse packaged TOC and XML load graphs with the pinned Lua 5.1 client parser."""

from __future__ import annotations

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


def loaded_lua(root: Path) -> list[Path]:
    toc = next(root.glob("*.toc"))
    pending = [
        root / line.strip().replace("\\", "/")
        for line in toc.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    seen, result = set(), []
    while pending:
        path = pending.pop(0)
        if path in seen:
            continue
        if not path.is_file():
            raise ValueError(f"{path}: XML/TOC child is missing from the packaged addon")
        seen.add(path)
        if path.suffix.lower() == ".lua":
            result.append(path)
        elif path.suffix.lower() == ".xml":
            for element in ET.parse(path).iter():
                for key in ("file", "virtualFile"):
                    if element.attrib.get(key):
                        pending.append(path.parent / element.attrib[key].replace("\\", "/"))
    return result


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
    except (OSError, ET.ParseError, StopIteration, ValueError) as error:
        return [f"{root}: invalid TOC/XML load graph: {error}"]
    problems = []
    for path in files:
        result = subprocess.run([str(parser), "-p", str(path)], capture_output=True, text=True)
        if result.returncode:
            problems.append(result.stderr.strip() or f"{path}: Lua 5.1 parse failed")
    return problems
