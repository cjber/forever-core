"""Print one version's section of CHANGELOG.md, or check that every release has one.

The release workflow hands what this prints to the packager, so GitHub and CurseForge show the same
words as the changelog in the repository. A tag with no entry, or an empty one, fails here rather than
publishing notes nobody wrote. CI runs `--check`, so a released version the changelog forgot fails on the
next push instead of going unnoticed, and so does a newest release whose section no longer reads as it did at its
tag (a merge that moved new bullets under it), since those words already shipped as that release's notes.

    python3 tools/changelog.py unreleased      # render pending changes/*.md
    python3 tools/changelog.py release 0.3.0   # validate, assemble and consume fragments
    python3 tools/changelog.py fragment 123    # migrate an open PR
    python3 tools/changelog.py --check --base origin/main  # enforce release-only history edits
    python3 tools/changelog.py 0.2.0           # that version's entry (a leading v is fine)
    python3 tools/changelog.py --check         # every v* tag has an entry, the newest as at its tag
    python3 tools/changelog.py --check 0.3.0   # that version has an entry, and its hero when it is a feature
"""

import argparse
import re
import subprocess
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

HEADING = re.compile(r"^## \[?(?P<version>\d+\.\d+\.\d+)\]? - \d{4}-\d{2}-\d{2}\s*$", re.MULTILINE)
UNRELEASED = re.compile(r"^## \[Unreleased\]\s*$", re.MULTILINE)
VERSION = re.compile(r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
IMAGE = re.compile(r"<!--\s*discord-image:\s*(\S+)\s*-->")


def find(text: str, version: str) -> str | None:
    """`version`'s section body, stripped, or None when the text has no heading for it."""
    matches = list(HEADING.finditer(text))
    for index, match in enumerate(matches):
        if match["version"] == version:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            return text[match.end() : end].strip()
    return None


def section(text: str, version: str) -> str:
    _check_unique_headings(text)
    body = find(text, version)
    if body is None:
        known = ", ".join(m["version"] for m in HEADING.finditer(text)) or "none"
        raise SystemExit(f"CHANGELOG.md has no section for {version} (has: {known})")
    if not body:
        raise SystemExit(f"CHANGELOG.md's section for {version} is empty")
    return body


def at_tag(root: Path, version: str) -> str | None:
    """CHANGELOG.md as it was at the `v<version>` tag, or None when the tag or the file is missing there."""
    shown = subprocess.run(
        ["git", "show", f"v{version}:CHANGELOG.md"], cwd=root, capture_output=True, text=True, check=False
    )
    return shown.stdout if shown.returncode == 0 else None


def released(root: Path) -> list[str]:
    """Every released version, from the repository's v* tags (CI checks out with fetch-depth 0)."""
    tags = subprocess.run(
        ["git", "tag", "--list", "v*"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.split()
    versions = [tag.removeprefix("v") for tag in tags if re.fullmatch(r"v\d+\.\d+\.\d+", tag)]
    return sorted(versions, key=lambda version: tuple(map(int, version.split("."))))


def _version_key(version: str) -> tuple[int, int, int]:
    match = VERSION.match(version)
    return (int(match["major"]), int(match["minor"]), int(match["patch"])) if match else (0, 0, 0)


def _check_unique_headings(text: str) -> None:
    if len(UNRELEASED.findall(text)) > 1:
        raise SystemExit("CHANGELOG.md has duplicate sections for Unreleased")
    counts: dict[str, int] = {}
    for match in HEADING.finditer(text):
        version = match["version"]
        counts[version] = counts.get(version, 0) + 1
    duplicates = sorted(version for version, count in counts.items() if count > 1)
    if duplicates:
        raise SystemExit(f"CHANGELOG.md has duplicate sections for {', '.join(duplicates)}")


def _check_unique_bullets(text: str) -> None:
    headings = sorted([*HEADING.finditer(text), *UNRELEASED.finditer(text)], key=lambda match: match.start())
    for index, heading in enumerate(headings):
        name = heading.groupdict().get("version") or "Unreleased"
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[heading.end() : end].strip()
        bullets: set[str] = set()
        for match in re.finditer(r"^[-*+] (.+(?:\n[ \t]+[^\n]+)*)", body, re.MULTILINE):
            bullet = " ".join(match[1].split())
            if bullet in bullets:
                raise SystemExit(f"CHANGELOG.md's section for {name} has duplicate bullet: {bullet}")
            bullets.add(bullet)


def is_feature(version: str, versions: list[str]) -> bool:
    """Whether `version` raises the major or minor over the newest of `versions` (oldest first).

    With no released version yet, the first release is a feature when it starts a patch line (patch 0),
    the same rule `classify_releases` uses in `tools/discord_digest.py`.
    """
    key = _version_key(version)
    if not versions:
        return key[2] == 0
    previous = _version_key(versions[-1])
    return key[0] > previous[0] or (key[0] == previous[0] and key[1] > previous[1])


def check_image(root: Path, text: str, version: str, versions: list[str]) -> None:
    """A feature release names a hero image, and every named image is a PNG in this repository."""
    images = IMAGE.findall(section(text, version))
    for path in images:
        target = (root / path.removeprefix("./").lstrip("/")).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            raise SystemExit(
                f"CHANGELOG.md's section for {version} names {path}, which is outside this repository"
            ) from None
        if target.suffix.lower() != ".png" or not target.is_file():
            raise SystemExit(
                f"CHANGELOG.md's section for {version} names {path}, which is not a PNG in this repository"
            )
    if not images and is_feature(version, versions):
        raise SystemExit(
            f"CHANGELOG.md's section for {version} is a feature release with no hero image; add"
            " `<!-- discord-image: docs/screenshots/<file>.png -->` naming a screenshot in this repository"
        )


def check(text: str, versions: list[str], tagged: Callable[[str], str | None] | None = None) -> None:
    """Require release entries, unique bullets and immutable notes for the newest tag.

    Pending notes belong in fragments, so even an empty Unreleased heading is invalid.
    """
    _check_unique_headings(text)
    _check_unique_bullets(text)
    if UNRELEASED.search(text):
        raise SystemExit(UNRELEASED_ERROR)
    for version in versions:
        section(text, version)
    if tagged is not None and versions:
        version = versions[-1]
        before = find(tagged(version) or "", version)
        if before is not None and before != find(text, version):
            raise SystemExit(
                f"CHANGELOG.md's section for {version} differs from its v{version} tag, whose notes already shipped;"
                f" put new notes in changes/<slug>.md (`git diff v{version} -- CHANGELOG.md` shows the change)"
            )


SECTIONS = ("Added", "Changed", "Fixed", "Removed", "For addon authors")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")
UNRELEASED_ERROR = (
    "CHANGELOG.md has notes under ## [Unreleased]; change notes now live in changes/<slug>.md. "
    "Run `python3 tools/changelog.py fragment <slug>` (slug: your issue number) to move them, "
    "then commit the new file."
)


def parse_fragment(path: Path, text: str) -> tuple[list[str], dict[str, str]]:
    """Read explicit section headings, preserving bullet continuation lines."""

    def invalid(reason: str) -> None:
        raise SystemExit(f"{path}: {reason}; allowed sections: {', '.join(SECTIONS)}")

    if not SLUG.fullmatch(path.stem):
        invalid("bad file name")
    images: list[str] = []
    sections: dict[str, str] = {}
    name: str | None = None
    lines: list[str] = []

    def finish() -> None:
        if name is not None:
            body = "\n".join(lines).strip("\n")
            if not body.strip():
                invalid(f"empty section {name}")
            if not body.startswith(("- ", "* ", "+ ")):
                invalid(f"section {name} must start with a bullet")
            for line in body.splitlines():
                if line.strip() and not line.startswith(("- ", "* ", "+ ", " ", "\t")):
                    invalid(f"invalid bullet continuation in section {name}")
            sections[name] = body

    for line in text.splitlines():
        if line.startswith("### "):
            finish()
            name = line[4:]
            if name not in SECTIONS:
                invalid(f"unknown heading {name}")
            if name in sections:
                invalid(f"duplicate section {name}")
            lines = []
        elif name is None:
            if IMAGE.fullmatch(line.strip()):
                images.append(line.strip())
            elif line.strip():
                invalid("text before the first heading")
        else:
            lines.append(line)
    finish()
    if not sections:
        invalid("empty fragment")
    return images, sections


def _join_sections(existing: str, added: str) -> str:
    """Add `added`'s lead lines and ### sections to the matching parts of `existing`, in SECTIONS order."""

    def split(body: str) -> tuple[str, dict[str, str]]:
        parts = re.split(r"^### (.+)$", body, flags=re.MULTILINE)
        return parts[0].strip(), {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}

    old_lead, old = split(existing)
    new_lead, new = split(added)
    names = [name for name in SECTIONS if name in old or name in new]
    names += [name for name in old if name not in names]
    bodies = {name: "\n".join(part for part in (old.get(name), new.get(name)) if part) for name in names}
    lead = "\n\n".join(part for part in (old_lead, new_lead) if part)
    return "\n\n".join(([lead] if lead else []) + [f"### {name}\n\n{bodies[name]}" for name in names])


def pending(root: Path) -> tuple[list[Path], str]:
    paths = sorted((root / "changes").glob("*.md"))
    images: list[str] = []
    sections: dict[str, list[str]] = {name: [] for name in SECTIONS}
    for path in paths:
        hero, bodies = parse_fragment(path, path.read_text(encoding="utf-8"))
        for image in hero:
            if image not in images:
                images.append(image)
        for name, body in bodies.items():
            sections[name].append(body)
    parts = ["\n".join(images)] if images else []
    parts.extend(f"### {name}\n\n" + "\n".join(bodies) for name, bodies in sections.items() if bodies)
    return paths, "\n\n".join(parts) + ("\n" if parts else "")


def check_base(root: Path, base: str) -> None:
    """Only whole, untagged release sections may precede the unchanged base changelog."""

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True).stdout

    ancestor = git("merge-base", base, "HEAD").strip()
    # A new repository's first pull request adds the changelog: the base has no released history to protect.
    if subprocess.run(["git", "cat-file", "-e", f"{ancestor}:CHANGELOG.md"], cwd=root, capture_output=True).returncode:
        return
    before = git("show", f"{ancestor}:CHANGELOG.md")
    match = UNRELEASED.search(before)
    if match is not None:
        following = re.search(r"^## ", before[match.end() :], re.MULTILINE)
        end = match.end() + following.start() if following else len(before)
        before = before[: match.start()] + before[end:]
    after = git("show", "HEAD:CHANGELOG.md")
    if before == after:
        return
    tags = set(released(root))
    # A section with no tag yet is a release still being prepared, so a release commit may rewrite it whole.
    old = HEADING.search(before)
    while old is not None and old["version"] not in tags:
        following = HEADING.search(before, old.end())
        before = before[: old.start()] + (before[following.start() :] if following else "")
        old = HEADING.search(before)
    first = HEADING.search(after)
    valid = old is not None and first is not None
    if valid:
        prefix = before[: old.start()]
        valid = after.startswith(prefix)
        tail = after.find(before[old.start() :], len(prefix))
        valid = valid and tail >= len(prefix) and after[tail:] == before[old.start() :]
        inserted = after[len(prefix) : tail] if valid else ""
        headings = list(HEADING.finditer(inserted))
        valid = valid and bool(headings) and headings[0].start() == 0
        for heading in headings:
            valid = (
                valid
                and bool(find(inserted, heading["version"]))
                and heading["version"] not in tags
                and _version_key(heading["version"]) > _version_key(old["version"])
            )
        valid = valid and len({h["version"] for h in headings}) == len(headings)
    if not valid:
        raise SystemExit(
            "CHANGELOG.md changes in this PR must be whole new release sections written by "
            "`python3 tools/changelog.py release X.Y.Z`; put change notes in changes/<slug>.md "
            "(slug: your issue number). Notes under ## [Unreleased] move there with "
            "`python3 tools/changelog.py fragment <slug>`."
        )


def migrate(root: Path, slug: str, default: str) -> None:
    if not SLUG.fullmatch(slug):
        raise SystemExit("fragment slug must match [a-z0-9][a-z0-9-]*")
    target = root / "changes" / f"{slug}.md"
    if target.exists():
        raise SystemExit(f"refusing to overwrite {target}")
    path = root / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    match = UNRELEASED.search(text)
    if match is None:
        raise SystemExit("CHANGELOG.md has no ## [Unreleased] heading to migrate")
    next_heading = re.search(r"^## ", text[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    body = text[match.end() : end].strip()
    if not body:
        path.write_text(text[: match.start()] + text[end:], encoding="utf-8")
        print("Removed ## [Unreleased], no notes to move")
        return
    lines = body.splitlines()
    images = []
    while lines and (not lines[0].strip() or IMAGE.fullmatch(lines[0].strip())):
        line = lines.pop(0)
        if line.strip():
            images.append(line.strip())
    if lines and not lines[0].startswith("### "):
        lines = [f"### {default}", "", *lines]
    fragment = "\n\n".join([*images, "\n".join(lines)]) + "\n"
    parse_fragment(target, fragment)
    target.parent.mkdir(exist_ok=True)
    target.write_text(fragment, encoding="utf-8")
    path.write_text(text[: match.start()] + text[end:], encoding="utf-8")
    print(f"Wrote {target.relative_to(root)}")


def main(root: Path, argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Render fragments and release changelog entries.")
    parser.add_argument("command", nargs="?")
    parser.add_argument("value", nargs="?")
    parser.add_argument("--check", nargs="?", const="", metavar="VERSION")
    parser.add_argument("--base")
    parser.add_argument("--date", default=time.strftime("%Y-%m-%d", time.gmtime()))
    parser.add_argument("--section", choices=SECTIONS, default="Changed")
    args = parser.parse_args(argv)
    if args.command == "fragment":
        if not args.value:
            parser.error("fragment requires a slug")
        migrate(root, args.value, args.section)
        return
    if args.command == "release":
        if not args.value or not VERSION.fullmatch(args.value):
            parser.error("release requires X.Y.Z")
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            parser.error("--date must be YYYY-MM-DD")
    paths, body = pending(root)
    if args.command == "unreleased":
        print(body, end="")
        return
    path = root / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    if args.command == "release":
        version = args.value.removeprefix("v")
        check(text, [])
        newest = HEADING.search(text)
        # An untagged newest section is a release still being prepared: its notes stay and the fragments join them.
        amend = newest is not None and newest["version"] == version and version not in released(root)
        if (
            not paths
            or (find(text, version) is not None and not amend)
            or (newest and not amend and _version_key(version) <= _version_key(newest["version"]))
        ):
            raise SystemExit(
                "release needs fragments and a version newer than every existing section, or the untagged newest one"
            )
        offset = newest.start() if newest else len(text)
        if amend:
            following = HEADING.search(text, newest.end())
            rest = text[following.start() :] if following else ""
            body = _join_sections(find(text, version) or "", body)
            candidate = text[:offset].rstrip() + f"\n\n## [{version}] - {args.date}\n\n{body}\n\n" + rest
        else:
            candidate = text[:offset].rstrip() + f"\n\n## [{version}] - {args.date}\n\n{body}\n" + text[offset:]
        check(candidate, [version])
        check_image(root, candidate, version, [v for v in released(root) if _version_key(v) < _version_key(version)])
        path.write_text(candidate, encoding="utf-8")
        for fragment in paths:
            fragment.unlink()
        print(f"Wrote ## [{version}] - {args.date} from {len(paths)} fragment(s)")
        return
    if args.check is not None:
        tags = released(root)
        if args.check:
            version = args.check.removeprefix("v")
            versions = [version]
            if paths:
                names = ", ".join(path.name for path in paths)
                raise SystemExit(
                    f"{version} cannot be released while changes/ holds {names}: run"
                    f" `python3 tools/changelog.py release {version}` so its section carries them, and commit that"
                )
            check(text, versions)
            check_image(root, text, version, [v for v in tags if _version_key(v) < _version_key(version)])
        else:
            versions = tags
            check(text, versions, lambda version: at_tag(root, version))
        if args.base:
            check_base(root, args.base)
        print(f"CHANGELOG.md documents {', '.join(versions) or 'no releases yet'}")
        return
    if not args.command:
        parser.error("give a version, unreleased, release, fragment or --check")
    print(section(text, args.command.removeprefix("v")))
