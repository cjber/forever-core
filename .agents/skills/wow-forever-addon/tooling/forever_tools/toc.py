"""The runtime Lua files an addon's TOC and XML load graph reaches, and the LuaLS coverage gate over them."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

LOAD_TAGS = {"Include", "Script"}
PRELOAD_BYTES = 10 * 1024 * 1024


def _toc_files(root: Path) -> list[Path]:
    return [
        toc
        for toc in sorted(root.rglob("*.toc"))
        if not any(part.startswith(".") or part == "node_modules" for part in toc.relative_to(root).parts)
    ]


def runtime_files(root: Path, runtime_dirs: tuple[str, ...] = ()) -> list[Path]:
    """Every Lua file a TOC loads, through nested XML. Lua under `root` or `runtime_dirs` that none loads is an error.

    `runtime_dirs` are the addon's folders of shipped Lua, never checker fixtures; they differ per addon.
    """
    root = root.resolve()
    files: set[Path] = set()

    def visit(path: Path) -> None:
        path = path.resolve()
        path.relative_to(root)
        if not path.is_file():
            raise ValueError(f"Missing runtime file: {path}")
        if path in files:
            return
        files.add(path)
        if path.suffix.lower() == ".xml":
            for element in ET.parse(path).iter():
                if element.tag.rsplit("}", 1)[-1] in LOAD_TAGS and "file" in element.attrib:
                    visit(path.parent / element.attrib["file"].replace("\\", "/"))

    for toc in _toc_files(root):
        for line in toc.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                visit(toc.parent / line.replace("\\", "/"))
    for folder in (root, *(root / name for name in runtime_dirs)):
        for path in folder.glob("*.lua") if folder == root else folder.rglob("*.lua"):
            if path.resolve() not in files:
                raise ValueError(f"Runtime Lua is not loaded by a TOC/XML: {path.relative_to(root)}")
    return sorted(path for path in files if path.suffix.lower() == ".lua")


def check_coverage(root: Path, runtime_dirs: tuple[str, ...] = ()) -> int:
    """Fail if the LuaLS configuration could silently omit a TOC-loaded Lua file."""
    root = root.resolve()
    config = json.loads((root / ".luarc.json").read_text())
    if config.get("workspace.useGitIgnore", True):
        raise ValueError("Set workspace.useGitIgnore=false so runtime coverage does not depend on local git ignores")
    files = runtime_files(root, runtime_dirs)
    if not files:
        raise ValueError("No TOC-loaded Lua files found")
    for path in files:
        relative = path.relative_to(root)
        for ignored in config.get("workspace.ignoreDir", []):
            if relative.match(ignored) or any(parent.match(ignored) for parent in relative.parents):
                raise ValueError(f"Runtime file excluded by {ignored}: {relative}")
        if path.stat().st_size > PRELOAD_BYTES:
            raise ValueError(f"Runtime file exceeds LuaLS's hard 10 MiB limit: {relative}")
        if path.stat().st_size / 1000 >= config["workspace.preloadFileSize"]:
            raise ValueError(f"Runtime file exceeds workspace.preloadFileSize: {relative}")
    if len(files) > config["workspace.maxPreload"]:
        raise ValueError("Runtime files exceed workspace.maxPreload")
    print(f"LuaLS coverage: {len(files)} TOC-loaded Lua files, including generated data and child addons")
    return 0
