"""Reject art drawn outside an addon's art helpers, where nothing keeps its shape.

An icon, atlas or texture is drawn at its own aspect, never pulled to a box of another shape (WFA-27). Each addon
keeps the ways to do that in one helper file under spec. A raw setter anywhere else, in Lua or XML, is refused
unless it takes the atlas's own size (`SetAtlas(atlas, true)`, `useAtlasSize="true"`) or its line, or the line
above, says why its shape is right: `-- art-ok: <reason>` in Lua, `<!-- art-ok: <reason> -->` in XML. An `art-ok`
that excuses nothing is refused too, so none outlives its call.
"""

import re
import sys
from pathlib import Path

__all__ = ["check", "run"]

# Texture and button setters that take art, the markup builders, and inline `|A` and `|T` markup.
RAW_LUA = re.compile(
    r":Set(?:Atlas|Texture|(?:Normal|Pushed|Highlight|Disabled|Checked|DisabledChecked)(?:Atlas|Texture))\s*\("
    r"|\bCreateAtlasMarkup\s*\(|\bCreateTextureMarkup\s*\(|\|[AT][^|\"']*:\d"
)
NATIVE_LUA = re.compile(r":SetAtlas\s*\([^()]*,\s*true\s*\)")
RAW_XML = re.compile(r"<\w*Texture\b[^>]*\b(?:atlas|file)\s*=")
NATIVE_XML = re.compile(r'useAtlasSize\s*=\s*"true"')
WAIVER = re.compile(r"art-ok:\s*\S")
MARK = re.compile(r"art-ok")


def check(source: str, xml: bool = False) -> list[tuple[int, str]]:
    """Each finding as (line, message)."""
    raw, native = (RAW_XML, NATIVE_XML) if xml else (RAW_LUA, NATIVE_LUA)
    lines = source.splitlines()
    findings, excused = [], set()
    for number, line in enumerate(lines, 1):
        code = line if xml else line.split("--", 1)[0]
        if not raw.search(code) or native.search(code):
            continue
        for at in (number, number - 1):
            if at >= 1 and WAIVER.search(lines[at - 1]):
                excused.add(at)
                break
        else:
            findings.append((number, "art-raw: draw art through the art helpers, or say why its shape is right"))
    for number, line in enumerate(lines, 1):
        if MARK.search(line) and number not in excused:
            reason = "names no reason" if not WAIVER.search(line) else "excuses no art call"
            findings.append((number, f"art-unused: this art-ok {reason}"))
    return sorted(findings)


def run(root: Path, files: list[Path], helpers: frozenset[str]) -> int:
    """Check `files` (Lua and XML) but for `helpers`, the addon's art helper files relative to `root`. A helper
    that does not exist fails: the exemption must name a real file. Exit status 1 on any finding."""
    failed = False
    for helper in sorted(helpers):
        if not (root / helper).is_file():
            print(f"{helper}: the art helper file does not exist", file=sys.stderr)
            failed = True
    checked = 0
    for path in sorted(files):
        if path.resolve().relative_to(root.resolve()).as_posix() in helpers:
            continue
        checked += 1
        try:
            hits = check(path.read_text(encoding="utf-8"), path.suffix == ".xml")
        except (OSError, UnicodeDecodeError) as error:
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
            continue
        for line, message in hits:
            print(f"{path}:{line}: {message}")
        failed |= bool(hits)
    if not failed:
        print(f"Art lint: {checked} files checked")
    return int(failed)
