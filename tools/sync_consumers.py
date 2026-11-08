"""Copy this repo's shared files into the consumer addons' working trees.

Fixing the column is one change here and one command, instead of four hand-edited copies. Each target file is
overwritten only when its content differs, so a run on an up-to-date checkout touches nothing and every change is
visible in `git status` for the consumer's own PR. A vendored runtime file also needs its consumer wiring (a TOC line
and the globals luacheck may not know yet), so that is applied even when the copy was already current.

A shared file that is new to a consumer waits until that consumer adopts it. A runtime module is copied only when the
consumer's own TOC already loads it or WIRING says how this tool loads it, and a test only when every vendored runtime
module it names is loaded either way; until then the run skips it and says so. Files the consumer already carries keep
syncing, because their adoption is done. That keeps a sync PR green on its own: the addon's adoption PR adds the TOC
line and its namespace wiring first, then the next sync carries the module.
"""

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path
from typing import NamedTuple

from check_core_shared import VENDORED, source

CORE_ROOT = Path(__file__).resolve().parent.parent


class Wiring(NamedTuple):
    """The consumer edits a vendored runtime file needs so its gates load and know it."""

    toc_after: str
    read_globals: tuple[str, ...]
    comment: str


WIRING = {
    "Core/Log.lua": Wiring(
        toc_after="Core\\SafeCall.lua",
        read_globals=("date",),
        comment="Core/Log.lua: the client's date, this session's seconds.",
    )
}


def digest(data):
    """The hex SHA-256 of `data`, to compare a copy with its source."""
    return hashlib.sha256(data).hexdigest()


def read_lines(path):
    """The file's lines without their endings, and whether it ended with a newline."""
    text = path.read_text(encoding="utf-8")
    return text.splitlines(), text.endswith("\n")


def write_lines(path, lines, trailing):
    """Write `lines` back with LF endings and the file's original trailing newline."""
    path.write_text("\n".join(lines) + ("\n" if trailing else ""), encoding="utf-8")


def find_toc(root):
    """The single `*.toc` at the consumer repo root, or None when there is not exactly one."""
    tocs = sorted(root.glob("*.toc"))
    return tocs[0] if len(tocs) == 1 else None


def toc_entries(toc):
    """The paths a TOC loads, with its metadata and comment lines left out."""
    lines, _ = read_lines(toc)
    return {line.strip().replace("\\", "/") for line in lines if line.strip() and not line.lstrip().startswith("#")}


def is_runtime(path):
    """Whether the client loads `path` as runtime code, which the consumer's TOC must name.

    `types/` holds LuaLS declarations, which only the typecheck reads, so they never wait for a TOC line.
    """
    return path.endswith(".lua") and path.split("/", 1)[0] not in {"tests", "tools", "types"}


def referenced_modules(path, seen=None):
    """Every vendored runtime module `path` names, following the vendored tests it names in turn."""
    seen = set() if seen is None else seen
    if path in seen:
        return set()
    seen.add(path)
    text = (CORE_ROOT / source(path)).read_text(encoding="utf-8")
    modules = set()
    for candidate in VENDORED:
        if candidate == path or candidate not in text:
            continue
        if is_runtime(candidate):
            modules.add(candidate)
        elif candidate.startswith("tests/"):
            modules |= referenced_modules(candidate, seen)
    return modules


def adoption_wait(root, path):
    """Why a `path` the consumer lacks must wait for adoption, or None when it may be copied."""
    toc = find_toc(root)
    name = toc.name if toc is not None else "its TOC"
    loaded = toc_entries(toc) if toc is not None else set()

    def loads(module):
        # A WIRING module gets its TOC line from apply_wiring in this same run, so it counts as loaded.
        return module in WIRING or module in loaded

    if is_runtime(path):
        return None if loads(path) else f"{name} does not load it yet"
    if not path.startswith("tests/"):
        return None
    missing = sorted(module for module in referenced_modules(path) if not loads(module))
    if not missing:
        return None
    return f"{name} does not load {', '.join(missing)} yet"


def declares_read_global(text, name):
    """Whether a luacheck config already reads global `name` from a table or an append line."""
    quoted = rf"""["']{re.escape(name)}["']"""
    for match in re.finditer(r"read_globals\s*=\s*\{([^}]*)\}", text, re.S):
        if re.search(quoted, match.group(1)):
            return True
    appended = rf"read_globals\[#read_globals \+ 1\]\s*=\s*{quoted}"
    return re.search(appended, text) is not None


def wire_toc(toc, repo, path, wiring, dry_run):
    """Insert `path`'s TOC line after its anchor; return True when the TOC changes."""
    toc_line = path.replace("/", "\\")
    lines, trailing = read_lines(toc)
    if any(line.strip() == toc_line for line in lines):
        return False
    anchor = next((index for index, line in enumerate(lines) if line.strip() == wiring.toc_after), None)
    if anchor is None:
        print(f"{repo}: warning: {toc.name} has no {wiring.toc_after} line, cannot add {toc_line}")
        return False
    lines.insert(anchor + 1, toc_line)
    print(f"{repo}: {toc.name}: {toc_line}")
    if not dry_run:
        write_lines(toc, lines, trailing)
    return True


def wire_luacheck(luacheck, repo, path, wiring, dry_run):
    """Append the file's missing read globals to `.luacheckrc`; return True when it changes."""
    text = luacheck.read_text(encoding="utf-8")
    missing = [name for name in wiring.read_globals if not declares_read_global(text, name)]
    if not missing:
        return False
    lines = [f"-- {wiring.comment}"]
    lines.extend(f'read_globals[#read_globals + 1] = "{name}"' for name in missing)
    addition = "\n".join(lines) + "\n"
    if text and not text.endswith("\n"):
        addition = "\n" + addition
    print(f"{repo}: .luacheckrc: {', '.join(missing)}")
    if not dry_run:
        luacheck.write_text(text + addition, encoding="utf-8")
    return True


def apply_wiring(root, repo, path, dry_run):
    """Apply `path`'s TOC and luacheck wiring; return how many files it changes or would change."""
    wiring = WIRING.get(path)
    if wiring is None:
        return 0
    changed = 0
    toc = find_toc(root)
    if toc is None:
        print(f"{repo}: warning: no single *.toc at its root, cannot add {path}")
    else:
        changed += wire_toc(toc, repo, path, wiring, dry_run)
    luacheck = root / ".luacheckrc"
    if luacheck.is_file():
        changed += wire_luacheck(luacheck, repo, path, wiring, dry_run)
    else:
        print(f"{repo}: warning: no .luacheckrc, cannot wire {path}")
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkouts", type=Path, help="the directory holding the consumer checkouts")
    parser.add_argument("--dry-run", action="store_true", help="report what would change and write nothing")
    parser.add_argument("--only", action="append", choices=VENDORED, help="sync only this shared path; may be repeated")
    arguments = parser.parse_args(argv)

    changed = 0
    selected = arguments.only or VENDORED.keys()
    for path in selected:
        consumers = VENDORED[path]
        origin = CORE_ROOT / source(path)
        for repo in consumers:
            root = arguments.checkouts / repo
            target = root / path
            if not root.is_dir():
                print(f"{repo}: not checked out under {arguments.checkouts}, skipped")
                continue
            content = origin.read_bytes()
            if not target.exists():
                wait = adoption_wait(root, path)
                if wait is not None:
                    print(f"{repo}: {path}: skipped, {wait}")
                    continue
            if not (target.exists() and digest(target.read_bytes()) == digest(content)):
                changed += 1
                print(f"{repo}: {path}")
                if not arguments.dry_run:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(origin, target)
            changed += apply_wiring(root, repo, path, arguments.dry_run)
    if changed and not arguments.dry_run:
        print("Run each changed consumer's gates and open one PR per consumer for all shared files.")
    verb = "would change" if arguments.dry_run else "changed"
    print(f"{changed} file(s) {verb}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
