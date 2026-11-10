"""Check an addon's published API against its docs/api.md.

`Core/API.lua` is the one list of what an addon publishes. A function is published as `function API.Name(...)`, as
`API.Name = function`, or as `API.Name = value` for any name or member path (`hub.Subscribe`), except the two value
fields docs/api-conventions.md defines, `version` and `minor`. `docs/api.md`
must name each published function as `Name(`. The API table's `minor = N` must also appear in the docs near the word
minor, so each addition's history is written down. An addon with no `Core/API.lua` passes, because ForeverCore itself
publishes no addon API.

    python3 tools/check_api_docs.py                # this repository's Core/API.lua and docs/api.md
    python3 tools/check_api_docs.py path/to/API.lua  # another file, checked against this repository's docs/api.md
"""

import argparse
import re
from pathlib import Path

FUNCTION = re.compile(r"^\s*function\s+API\.(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)
ASSIGNED_FUNCTION = re.compile(r"^\s*API\.(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*function\b", re.MULTILINE)
ASSIGNED = re.compile(
    r"^\s*API\.(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?!(?:function|nil|true|false)\b)"
    r"(?P<value>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*(?:--.*)?$",
    re.MULTILINE,
)
# The API table's value fields (docs/api-conventions.md); every other member it publishes is a function.
VALUE_FIELDS = {"version", "minor"}
MINOR = re.compile(r"\bminor\s*=\s*(?P<minor>\d+)")
MINOR_WORD = re.compile(r"\bminor\b", re.IGNORECASE)
# How far from the word minor a number may sit and still be its history. Adventure Guide's one-line history keeps
# every entry within about 150 characters of the word.
NEAR = 200


def published(source: str) -> list[str]:
    """Every name the API table publishes as a function, sorted."""
    names = {match["name"] for match in FUNCTION.finditer(source)}
    names |= {match["name"] for match in ASSIGNED_FUNCTION.finditer(source)}
    names |= {match["name"] for match in ASSIGNED.finditer(source)}
    return sorted(names - VALUE_FIELDS)


def minor_of(source: str) -> int | None:
    """The API table's `minor = N`, or None when it names no minor."""
    for line in source.splitlines():
        if line.lstrip().startswith("--"):
            continue
        match = MINOR.search(line)
        if match:
            return int(match["minor"])
    return None


def minor_documented(docs: str, minor: int) -> bool:
    """Whether the number sits near the word minor, as a history entry or `minor = N` does."""
    text = " ".join(docs.split())
    for match in MINOR_WORD.finditer(text):
        window = text[max(0, match.start() - NEAR) : match.end() + NEAR]
        if re.search(rf"\b{minor}\b", window):
            return True
    return False


def check(root: Path, api: Path) -> int:
    """Fail for each published name or minor that docs/api.md does not document. A missing API file passes."""
    shown = api.relative_to(root) if api.is_relative_to(root) else api
    if not api.is_file():
        print(f"API docs: no {shown}, nothing to check")
        return 0

    source = api.read_text(encoding="utf-8")
    docs_path = root / "docs/api.md"
    failures = []
    if not docs_path.is_file():
        failures.append("docs/api.md is missing")
        docs = ""
    else:
        docs = docs_path.read_text(encoding="utf-8")

    names = published(source)
    failures += [f"docs/api.md does not mention {name}(" for name in names if f"{name}(" not in docs]
    minor = minor_of(source)
    if minor is not None and not minor_documented(docs, minor):
        failures.append(f"docs/api.md's minor history does not mention minor {minor}")

    if failures:
        print("\n".join(failures))
        return 1
    print(f"API docs: {len(names)} published names and minor {minor} are documented")
    return 0


def main(root: Path, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Core/API.lua against docs/api.md.")
    parser.add_argument("api", nargs="?", type=Path, help="the addon's Core/API.lua (default: this repository's)")
    arguments = parser.parse_args(argv)
    return check(root, arguments.api or root / "Core/API.lua")


if __name__ == "__main__":
    raise SystemExit(main(Path.cwd()))
