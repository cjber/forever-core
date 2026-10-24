"""The shared "The Forever addons" block in every addon's README.md and docs/curseforge.md (WFA-32).

`BLOCK` is the one copy: a heading, a sentence and a table of the five addons in the family's order, each name linked
to its CurseForge page. Each repo places it once per file, between `START` and `END`, where it fits that page; `check`
fails when a file lacks the markers or the text between them differs, so a change here reaches every page through a
sync and nothing drifts.

    python3 tools/check_family.py          # check README.md and docs/curseforge.md
    python3 tools/check_family.py --fix    # rewrite the text between the markers (the markers stay where they are)
    python3 tools/check_family.py --print  # print the block, markers included, to place it the first time
"""

import argparse
import sys
from collections.abc import Iterator
from pathlib import Path

from .fsio import atomic_write

__all__ = ["ADDONS", "BLOCK", "END", "FILES", "START", "check", "fix", "main"]

START = "<!-- forever-family:start -->"
END = "<!-- forever-family:end -->"
FILES = ("README.md", "docs/curseforge.md")

# (name, CurseForge slug, one plain line in voice.md's style), in the family's order.
ADDONS = (
    (
        "Shortest Path Forever",
        "shortest-path-forever",
        "Plans journeys on foot, by air, by sea and through portals, with directions in the tracker.",
    ),
    (
        "Adventure Guide Forever",
        "adventure-guide-forever",
        "Suggests quests for your level and routes you from one to the next.",
    ),
    (
        "SkillUp Forever",
        "skillup-forever",
        "Shows skill-up chances, recipe costs and levelling routes in the Professions window.",
    ),
    (
        "Legacy Forever",
        "legacy-forever",
        "Shows your unfinished Legacy challenges on the world map and tracks the ones you choose.",
    ),
    (
        "Tweaks Forever",
        "tweaks-forever",
        "Adds quest automation, rare alerts and merchant options to the game's settings.",
    ),
)

BLOCK = "\n".join(
    [
        START,
        "",
        "## The Forever addons",
        "",
        "Each one works on its own, and they work together when you install more than one.",
        "",
        "| Addon | What it does |",
        "|---|---|",
        *(f"| [{name}](https://www.curseforge.com/wow/addons/{slug}) | {line} |" for name, slug, line in ADDONS),
        "",  # a blank line ends the table, so no renderer reads the end marker as a row
        END,
    ]
)


def _span(text: str) -> tuple[int, int] | str:
    """(start, end) offsets of the marked block, end past END; or why there is no single well-formed block."""
    starts, ends = text.count(START), text.count(END)
    if starts == 0 and ends == 0:
        return f"no {START} ... {END} block; place `tools/check_family.py --print` where the family list goes"
    if starts != 1 or ends != 1:
        return f"{starts} start and {ends} end markers; keep exactly one block"
    begin, finish = text.index(START), text.index(END)
    if finish < begin:
        return f"{END} comes before {START}"
    for marker, offset in ((START, begin), (END, finish)):
        line_start = text.rfind("\n", 0, offset) + 1
        line_end = text.find("\n", offset)
        line = text[line_start : len(text) if line_end < 0 else line_end]
        if line.strip() != marker:
            return f"{marker} must be on a line of its own"
    return begin, finish + len(END)


def _blocks(root: Path) -> Iterator[tuple[str, Path, str, tuple[int, int] | str | None]]:
    """(name, path, text, span) per file; span is None for a missing file. Text keeps its line endings."""
    for name in FILES:
        path = root / name
        if not path.is_file():
            yield name, path, "", None
            continue
        text = path.read_bytes().decode("utf-8")
        yield name, path, text, _span(text)


def check(root: Path) -> list[str]:
    problems = []
    for name, _, text, span in _blocks(root):
        if span is None:
            problems.append(f"{name}: missing")
        elif isinstance(span, str):
            problems.append(f"{name}: {span}")
        elif text[span[0] : span[1]].replace("\r\n", "\n") != BLOCK:
            line = text.count("\n", 0, span[0]) + 1
            problems.append(f"{name}:{line}: the family block differs from forever_tools.family; run --fix")
    return problems


def fix(root: Path) -> list[str]:
    """Rewrite each well-formed block to `BLOCK`, in the file's own line endings; return the files changed.
    A file with no block is left alone: where the block goes is the page's choice."""
    changed = []
    for name, path, text, span in _blocks(root):
        if span is None or isinstance(span, str):
            continue
        block = BLOCK.replace("\n", "\r\n") if "\r\n" in text else BLOCK
        if text[span[0] : span[1]] != block:
            atomic_write(path, text[: span[0]] + block + text[span[1] :])
            changed.append(name)
    return changed


def main(root: Path, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--print", action="store_true", help="print the block, markers included")
    action.add_argument("--fix", action="store_true", help="rewrite the text between existing markers")
    args = parser.parse_args(argv)
    if args.print:
        sys.stdout.write(BLOCK + "\n")
        return 0
    if args.fix:
        for name in fix(root):
            print(f"{name}: family block rewritten")
    problems = check(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"family block: matches forever_tools.family in {' and '.join(FILES)}")
    return 0
