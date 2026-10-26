"""Find unreferenced addon Lua, media and Python tooling without third-party dependencies."""

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED = ("types/", "tests/", "tools/", "docs/", ".agents/", "Nav/", ".types/", ".sift/", "reference/")
# Consumer-only shared modules are stored here as source for sync_consumers.py.
CORE_SOURCE_ONLY = {"UI/Report.lua", "UI/ForeverFamily.lua"}


def rel(path):
    return path.relative_to(ROOT).as_posix()


def source_files(pattern):
    return sorted(p for p in ROOT.rglob(pattern) if not any(x in {".git", ".venv"} for x in p.parts))


def ignored(path):
    name = rel(path)
    return any(name.startswith(prefix) for prefix in IGNORED) or name.startswith("tools/.cache/")


def scan():
    errors = []
    lua = [p for p in source_files("*.lua") if not ignored(p)]
    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in lua}

    allow = {}
    allow_path = ROOT / "tools/deadcode-allow.txt"
    if allow_path.exists():
        for number, raw in enumerate(allow_path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            entry, sep, reason = line.partition(" # ")
            if not sep or not reason.strip():
                errors.append(("tools/deadcode-allow.txt", number, "allowlist entry needs path:symbol # reason"))
            else:
                allow[entry] = reason.strip()

    definitions = []
    for path, content in texts.items():
        if ROOT.name == "forever-core" and rel(path) in CORE_SOURCE_ONLY:
            continue
        for match in re.finditer(
            r"\bfunction\s+ns\.([A-Za-z_]\w*)\s*\(|\bns\.([A-Za-z_]\w*)\s*=\s*function\b", content
        ):
            symbol = match.group(1) or match.group(2)
            definitions.append((path, content, match.start(), symbol))
    for path, content, offset, symbol in definitions:
        pattern = re.compile(rf"\bns\s*(?:\.\s*{re.escape(symbol)}\b|\[\s*['\"]{re.escape(symbol)}['\"]\s*\])")
        refs = sum(len(pattern.findall(source)) for source in texts.values())
        key = f"{rel(path)}:{symbol}"
        if refs <= 1 and key not in allow:
            errors.append((rel(path), content.count("\n", 0, offset) + 1, f"unreferenced namespace member ns.{symbol}"))

    toc_entries = set()
    for toc in source_files("*.toc"):
        for line in toc.read_text(encoding="utf-8", errors="replace").splitlines():
            entry = line.split("#", 1)[0].strip().replace("\\", "/").lstrip("./")
            if entry.lower().endswith(".lua"):
                toc_entries.add(entry)
    for path in source_files("*.lua"):
        name = rel(path)
        if ignored(path) or (ROOT.name == "forever-core" and name in CORE_SOURCE_ONLY):
            continue
        if not any(name == entry or name.endswith("/" + entry) for entry in toc_entries):
            errors.append((name, 1, "Lua file is not named by any TOC"))

    reference_sources = []
    for pattern in ("*.lua", "*.xml", "*.toc"):
        reference_sources.extend(source_files(pattern))
    references = "\n".join(
        p.read_text(encoding="utf-8", errors="replace").replace("\\", "/") for p in reference_sources
    )
    for media in (ROOT / "media").glob("*") if (ROOT / "media").is_dir() else ():
        stem = media.name.rsplit(".", 1)[0]
        media_reference = re.compile(rf"media/+{re.escape(stem)}(?:\b|/)", re.IGNORECASE)
        if media.is_file() and media.suffix.lower() in {".tga", ".blp"} and not media_reference.search(references):
            errors.append((rel(media), 1, "media file has no Lua, XML or TOC reference"))

    py = {p.stem: p for p in source_files("*.py") if p.parent == ROOT / "tools" and not p.stem.endswith("_test")}
    graph = {name: set() for name in py}
    entries = set()
    for name, path in py.items():
        content = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        if re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", content) or path.name.endswith("_test.py"):
            entries.add(name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                graph[name].update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                graph[name].add(node.module.split(".")[0])
    workflow_dir = ROOT / ".github/workflows"
    if workflow_dir.exists():
        for workflow in workflow_dir.glob("*.yml"):
            content = workflow.read_text(encoding="utf-8", errors="replace")
            entries.update(
                name for name in py if re.search(rf"python3?\s+(?:-m\s+)?tools/{re.escape(name)}(?:\.py)?\b", content)
            )
    for documentation in ROOT.rglob("*.md"):
        if ignored(documentation):
            continue
        content = documentation.read_text(encoding="utf-8", errors="replace")
        entries.update(
            name for name in py if re.search(rf"python3?\s+(?:-m\s+)?tools/{re.escape(name)}(?:\.py)?\b", content)
        )
    for name, path in py.items():
        token = f"tools/{path.name}"
        if any(token in other.read_text(encoding="utf-8", errors="replace") for other in py.values() if other != path):
            entries.add(name)
    reachable = set(entries)
    while True:
        newer = (
            reachable | set().union(*(graph.get(name, set()) & py.keys() for name in reachable))
            if reachable
            else reachable
        )
        if newer == reachable:
            break
        reachable = newer
    for name, path in py.items():
        if name not in reachable:
            errors.append((rel(path), 1, "Python module is unreachable from an entrypoint"))
    return sorted(errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if findings remain")
    args = parser.parse_args()
    errors = scan()
    for path, line, message in errors:
        print(f"{path}:{line}: {message}")
    print(f"Dead-code scan: {len(errors)} finding(s).")
    return 1 if args.check and errors else 0


if __name__ == "__main__":
    sys.exit(main())
