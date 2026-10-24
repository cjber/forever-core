#!/usr/bin/env python3
"""Flag the mechanical AI tells voice.md bans in store copy and posts (WFA-24).

Usage: check_copy.py FILE... ; exits 1 and prints file:line: phrase for each hit, and each image
stacked under another with no text between (WFA-25).
Image alt text and code spans are skipped: they quote the game, not our voice.

check_copy.py --words FILE... also prints each file's prose words beside its WFA-10/11 limit (README.md
under 1,200, curseforge.md under 600), so every repo measures the same way. The count is a guide and never
fails. The shared forever-family block, code, images, link addresses and HTML tags are not counted:
the block is the same on every page and is not that page's prose.
"""

import re
import sys
from pathlib import Path

BANNED = [
    r"—",
    r" – ",
    r"\bseamless(ly)?\b",
    r"\belevat(e|es|ing)\b",
    r"\benhance your\b",
    r"\beffortless(ly)?\b",
    r"\bgame[- ]changer\b",
    r"\bsupercharge",
    r"\bunleash",
    r"\bunlock(s|ing)? (the|your|a)\b",
    r"\bdive (in|into)\b",
    r"\bdelv(e|es|ing)\b",
    r"\blook no further\b",
    r"\bwhether you'?re\b",
    r"\bit'?s not just\b",
    r"\bto the next level\b",
    r"\bsay goodbye to\b",
    r"\btailored\b",
    r"\brobust\b",
    r"\bstreamlin(e|ed|es|ing)\b",
    r"\bempower",
    r"\blevel up your\b",
    r"\bin today'?s\b",
    r"\bpowerful\b",
    r"\bultimate\b",
    r"\bamazing\b",
    r"\bstunning\b",
    r"\bsleek\b",
    r"\bcutting[- ]edge\b",
    r"\brevolutionary\b",
    r"\bkey features\b",
    r"^(in short|overall|in summary),",
    r"!(\s|$)",
]
PATTERN = re.compile("|".join(f"(?:{p})" for p in BANNED), re.IGNORECASE)
QUOTED = re.compile(r"!\[[^\]]*\]\([^)]*\)|`[^`]*`|alt=\"[^\"]*\"")


def hits(path: Path) -> list[str]:
    found = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for match in PATTERN.finditer(QUOTED.sub("", line)):
            found.append(f"{path}:{number}: {match.group(0).strip() or match.group(0)!r}")
    return found


IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]*)\)|<img\b[^>]*\bsrc=\"([^\"]*)\"[^>]*>", re.IGNORECASE)
BADGE = re.compile(r"badge\.svg|img\.shields\.io", re.IGNORECASE)
TAG = re.compile(r"<[^>]+>")


def stacked(path: Path) -> list[str]:
    """Two screenshots with no words between them (WFA-25), one above the other or in one row. A row that
    belongs together is one image composed by tools/screenshots.py; CI badges are not screenshots."""
    found = []
    last_image = 0  # line of the last screenshot since any words
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for match in IMAGE.finditer(line):
            if BADGE.search(match.group(1) or match.group(2)):
                continue
            if last_image:
                found.append(f"{path}:{number}: screenshot next to the one on line {last_image} with no text between")
            last_image = number
        if TAG.sub("", IMAGE.sub("", line)).strip():
            last_image = 0
    return found


LIMITS = {"README.md": 1200, "curseforge.md": 600}
NOT_PROSE = [
    re.compile(r"<!-- forever-family:start -->.*?<!-- forever-family:end -->", re.DOTALL),
    re.compile(r"^ {0,3}```.*?^ {0,3}```", re.DOTALL | re.MULTILINE),
    re.compile(r"<!--.*?-->", re.DOTALL),
    re.compile(r"`[^`\n]*`"),  # code spans quote the game, as hits() treats them
    re.compile(r"!\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])"),  # images, inline or by reference
    re.compile(r"^ {0,3}\[[^\]]+\]:.*$", re.MULTILINE),  # link reference definitions
    re.compile(r"<[^>]+>"),
]
LINK = re.compile(r"\[([^\]]*)\](?:\([^)]*\)|\[[^\]]*\])")
URL = re.compile(r"\bhttps?://\S+")  # a bare address, once links have become their text
WORD = re.compile(r"[^\W_]+(?:['’.-][^\W_]+)*")


def words(text: str) -> int:
    """Prose words as WFA-10/11 count them: link text counts; the family block and markup do not."""
    for pattern in NOT_PROSE:
        text = pattern.sub(" ", text)
    return len(WORD.findall(URL.sub(" ", LINK.sub(r"\1", text))))


def word_counts(paths: list[Path]) -> None:
    for path in paths:
        count, limit = words(path.read_text(encoding="utf-8")), LIMITS.get(path.name)
        note = "" if limit is None else f", limit {limit}" + (", over" if count >= limit else "")
        print(f"{path}: {count} prose words{note}")


def main() -> int:
    paths = [Path(name) for name in sys.argv[1:] if name != "--words"]
    found = [hit for path in paths for hit in hits(path) + stacked(path)]
    if "--words" in sys.argv[1:]:
        word_counts(paths)
    for hit in found:
        print(hit)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
