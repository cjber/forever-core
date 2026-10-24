"""Check the folders the BigWigs packager built before anything uploads them.

The release workflow hands the packager's output straight to GitHub, CurseForge and Wago, and `.pkgmeta`'s ignore
list is never compared with the TOC. Run the packager without uploading (`release.sh -d -z`, or the action with
`args: -d -z`), then this reads its release directory and fails on:

- an addon folder that is missing, or has no TOC of its own name;
- a file a TOC or its XML loads (`Script`, `Include`), or an `Interface\\AddOns\\<packaged folder>\\...` path a TOC
  tag, XML attribute or whole Lua string names, that is not in the package;
- a development folder that shipped (`tests`, `tools`, `types`, `.agents` and the like), or a required file that
  did not (a licence file in every packaged folder, and `THIRD_PARTY.md` in the main addon);
- credits that do not ship with it (WFA-10, WFA-31): the main addon's `README.md` needs a `## Credits` section and
  its `THIRD_PARTY.md` an `## Ideas and contributors` section, each with some text under the heading;
- a spec that fails when run against the packaged files instead of the checkout: the package is copied to a scratch
  folder, the addon's test support (`tests/`) is laid over it, and each spec runs there under LuaJIT.

    python3 tools/check_package.py [--release-dir .release]
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .lua import LuaSyntaxError, tokenize

__all__ = ["Policy", "check", "has_section", "licence_file", "main", "run_specs"]

FORBIDDEN = (".agents", ".github", ".sift", "AGENTS.md", "tests", "tools", "types")
# What the client accepts for a texture, font or sound path given without its extension.
EXTENSIONS = ("", ".tga", ".blp", ".png", ".jpg", ".ttf", ".otf", ".ogg", ".mp3")
LOAD_TAGS = {"Include", "Script"}
SPEC_TIMEOUT = 900


@dataclass(frozen=True)
class Policy:
    """`addons`: every folder the package holds, the main addon first (`package-as`, then each `move-folders`
    target). `forbidden`: names that must not appear at any addon folder's top level. Every folder must ship a
    licence file (`licence_file`). `required`: other files the main addon folder must ship. `credits`: (file,
    heading) pairs the main addon folder must ship, each file holding that ATX heading (`has_section`) with text
    under it. `specs`: repository-relative specs to run on the packaged files, with `support` (paths in the checkout,
    never shipped) laid over a copy of the package first."""

    addons: tuple[str, ...]
    forbidden: tuple[str, ...] = FORBIDDEN
    required: tuple[str, ...] = ("THIRD_PARTY.md",)
    credits: tuple[tuple[str, str], ...] = (
        ("README.md", "## Credits"),
        ("THIRD_PARTY.md", "## Ideas and contributors"),
    )
    specs: tuple[str, ...] = ()
    support: tuple[str, ...] = ("tests",)


def addon_path(text: str, release: Path, addons: tuple[str, ...]) -> Path | None:
    """The packaged file an `Interface\\AddOns\\<folder>\\...` path names, or None when it names another addon."""
    parts = PurePosixPath(text.strip().replace("\\", "/")).parts
    if len(parts) < 4 or parts[0].lower() != "interface" or parts[1].lower() != "addons":
        return None
    folder = next((addon for addon in addons if addon.lower() == parts[2].lower()), None)
    return None if folder is None else release.joinpath(folder, *parts[3:])


def locate(path: Path, extensions: tuple[str, ...] = ("",)) -> Path | None:
    """The file the client would load for `path`: case ignored, as on Windows, with any of `extensions` added."""
    absolute = path.is_absolute()
    current = Path(path.anchor) if absolute else Path(".")
    for part in path.parent.parts[1 if absolute else 0 :]:
        step = current / part
        if not step.is_dir():
            children = current.iterdir() if current.is_dir() else ()
            step = next((child for child in children if child.is_dir() and child.name.lower() == part.lower()), None)
            if step is None:
                return None
        current = step
    files = {child.name.lower(): child for child in current.iterdir() if child.is_file()}
    return next((files[key] for key in ((path.name + e).lower() for e in extensions) if key in files), None)


def lua_strings(source: str) -> list[tuple[int, str]]:
    """Each whole string literal in a Lua file with its line, escapes for backslashes and quotes undone. A string
    joined to another value with `..` is only part of a path, so it is left out."""
    tokens, _ = tokenize(source)
    found = []
    for index, token in enumerate(tokens):
        if token.kind != "string" or token.text[:1] not in "\"'":
            continue
        if ".." in (tokens[index - 1].text if index else "", tokens[index + 1].text):
            continue
        body = token.text[1:-1]
        found.append((token.line, body.replace("\\\\", "\\").replace('\\"', '"').replace("\\'", "'")))
    return found


LICENCE_NAMES = frozenset({"LICENSE", "LICENCE", "COPYING", "UNLICENSE"})
HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
BREAK = re.compile(r"^ {0,3}([-*_=])(?:[ \t]*\1){2,}[ \t]*$")


def licence_file(name: str) -> bool:
    """A licence file by name: LICENSE, LICENCE, COPYING or UNLICENSE in any case, with or without an extension."""
    return name.split(".", 1)[0].upper() in LICENCE_NAMES


def _prose(text: str) -> list[str]:
    """`text`'s lines with HTML comments blanked and fenced code replaced by a "```" marker line, so a heading in a
    comment or a code block never counts and a code block still counts as content."""
    text = re.sub(r"<!--.*?(?:-->|\Z)", lambda match: "\n" * match.group(0).count("\n"), text, flags=re.S)
    lines, fence = [], ""
    for line in text.splitlines():
        found = FENCE.match(line)
        if fence:
            if (
                found
                and found.group(1)[0] == fence[0]
                and len(found.group(1)) >= len(fence)
                and not found.group(2).strip()
            ):
                fence = ""
            continue
        if found and not (found.group(1)[0] == "`" and "`" in found.group(2)):
            fence = found.group(1)
            lines.append("```")
            continue
        lines.append(line)
    return lines


def has_section(text: str, heading: str) -> bool:
    """Whether Markdown `text` has the ATX `heading` (such as `## Credits`) with some content under it, before the
    next heading of the same or a higher level. Up to three leading spaces, closing hashes and any case are allowed;
    headings inside HTML comments or fenced code don't count, and neither do thematic breaks as content. A repeated
    heading is checked again when an earlier copy is empty."""
    want = HEADING.match(heading)
    if want is None:
        raise ValueError(f"not an ATX Markdown heading: {heading!r}")
    level, title = len(want.group(1)), (want.group(2) or "").casefold()
    inside = False
    for line in _prose(text):
        found = HEADING.match(line)
        if found:
            if inside and len(found.group(1)) <= level:
                inside = False
            if len(found.group(1)) == level and (found.group(2) or "").casefold() == title:
                inside = True
            continue
        if inside and line.strip() and not BREAK.match(line):
            return True
    return False


def check(release: Path, policy: Policy) -> list[str]:
    """Every problem with the packaged folders under `release`, each as one line."""
    problems: list[str] = []
    for addon in policy.addons:
        folder = release / addon
        if not folder.is_dir():
            problems.append(f"{addon}: not in {release}; check package-as and move-folders in .pkgmeta")
            continue
        forbidden = {name.lower() for name in policy.forbidden}
        for child in sorted(folder.iterdir()):
            if child.name.lower() in forbidden:
                problems.append(f"{addon}/{child.name}: shipped; add it to .pkgmeta's ignore list")
        # The addon's own TOC, and any flavour TOC beside it (Addon_Vanilla.toc, Addon-Classic.toc).
        tocs = [
            toc
            for toc in sorted(folder.glob("*.toc"))
            if toc.stem.lower() == addon.lower()
            or toc.stem.lower().startswith((f"{addon}_".lower(), f"{addon}-".lower()))
        ]
        if not tocs:
            problems.append(f"{addon}/{addon}.toc: missing")
        for toc in tocs:
            problems += check_loaded(release, folder, toc, policy.addons)
        if not any(child.is_file() and licence_file(child.name) for child in folder.iterdir()):
            problems.append(f"{addon}/LICENSE: missing; every packaged folder ships its licence")
    if policy.addons and (release / policy.addons[0]).is_dir():
        main, name = release / policy.addons[0], policy.addons[0]
        # A licence named in `required` is the licence rule's to check, under any of its names.
        for file in dict.fromkeys(policy.required + tuple(file for file, _ in policy.credits)):
            if not licence_file(file) and not (main / file).exists():
                problems.append(f"{name}/{file}: missing; it must ship")
        for file, heading in policy.credits:
            if not (main / file).is_file():
                continue
            try:
                text = (main / file).read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                problems.append(f"{name}/{file}: not UTF-8")
                continue
            try:
                found = has_section(text, heading)
            except ValueError as error:
                problems.append(f"{name}/{file}: {error}; fix the policy's credits heading")
                continue
            if not found:
                problems.append(f"{name}/{file}: no `{heading}` section with text; credit what the addon uses")
    return problems


def check_loaded(release: Path, folder: Path, toc: Path, addons: tuple[str, ...]) -> list[str]:
    """The TOC's files, their XML includes, and the addon paths any of them name, that are not in the package."""
    problems: list[str] = []
    seen: set[Path] = set()

    def where(path: Path) -> str:
        return path.relative_to(release).as_posix()

    def named(source: Path, line: int, text: str) -> None:
        target = addon_path(text, release, addons)
        if target is not None and locate(target, EXTENSIONS) is None:
            at = f"{where(source)}:{line}" if line else where(source)
            problems.append(f"{at}: names {text.strip()}, which is not in the package")

    def visit(wanted: Path, by: str) -> None:
        path = locate(wanted)
        if path is None:
            problems.append(f"{where(wanted)}: missing (loaded by {by}); check .pkgmeta's ignore list")
            return
        if path in seen:
            return
        seen.add(path)
        if path.suffix.lower() == ".xml":
            try:
                elements = list(ET.parse(path).iter())
            except ET.ParseError as error:
                problems.append(f"{where(path)}: {error}")
                return
            for element in elements:
                if element.tag.rsplit("}", 1)[-1] in LOAD_TAGS and "file" in element.attrib:
                    file = element.attrib["file"]
                    target = addon_path(file, release, addons) or path.parent / file.replace("\\", "/")
                    visit(target, where(path))
                for value in element.attrib.values():
                    named(path, 0, value)
        elif path.suffix.lower() == ".lua":
            try:
                strings = lua_strings(path.read_text(encoding="utf-8"))
            except (LuaSyntaxError, UnicodeDecodeError) as error:
                problems.append(f"{where(path)}: {error}")
                return
            for line, text in strings:
                named(path, line, text)

    for number, line in enumerate(toc.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if line.startswith("##") and ":" in line:
            named(toc, number, line.split(":", 1)[1])
        elif line and not line.startswith("#"):
            visit(folder / line.replace("\\", "/"), where(toc))
    return problems


def run_specs(root: Path, release: Path, policy: Policy) -> list[str]:
    """Run each spec from a scratch copy of the package with the test support laid over it; failures as lines."""
    if not policy.specs:
        return []
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch) / policy.addons[0]
        shutil.copytree(release / policy.addons[0], work)
        for addon in policy.addons[1:]:
            shutil.copytree(release / addon, Path(scratch) / addon)
        for name in policy.support:
            source, target = root / name, work / name
            if target.exists():
                return [f"{name}: shipped in the package, so the specs cannot tell it from the checkout's"]
            if not source.exists():
                return [f"{name}: not in the checkout; fix the package policy's support paths"]
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        for spec in policy.specs:
            if shutil.which("luajit") is None:
                return ["luajit: not found on PATH; install it to run the specs on the package"]
            try:
                result = subprocess.run(
                    ["luajit", spec], cwd=work, capture_output=True, text=True, timeout=SPEC_TIMEOUT
                )
            except subprocess.TimeoutExpired:
                problems.append(f"{spec}: still running on the packaged files after {SPEC_TIMEOUT} s")
                continue
            if result.returncode:
                tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-20:])
                problems.append(f"{spec}: fails on the packaged files (exit {result.returncode}):\n{tail}")
            else:
                print(f"{spec}: passes on the packaged files")
    return problems


def main(root: Path, policy: Policy, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release-dir", type=Path, default=root / ".release", help="the packager's release folder")
    args = parser.parse_args(argv)
    problems = check(args.release_dir, policy)
    if not problems:
        problems = run_specs(root, args.release_dir, policy)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(
        f"Package: {', '.join(policy.addons)} ship every loaded file, a licence and the credits, "
        "and nothing from development"
    )
    return 0
