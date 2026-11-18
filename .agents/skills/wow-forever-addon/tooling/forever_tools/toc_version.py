"""Write the release version, without the tag's `v`, into every TOC right before the BigWigs packager runs.

    python3 -m tools.forever_tools.toc_version [ROOT]

Every addon TOC carries `## Version: @project-version@`, and the packager fills that keyword with the git tag name
(`v1.2.3`); it has no option to drop the prefix. The client then reports `v1.2.3` from
`C_AddOns.GetAddOnMetadata(addon, "Version")`, while each addon's What's New check, report and saved version compare it
with a bare `1.2.3`. Run this on the disposable checkout before every packager step (the Release workflow and the CI
package job): it writes the version the packager would (the pushed tag on a tagged commit, else
`git describe --tags --always --abbrev=7`) with the `v` removed, so the packager has no keyword left to fill.
`forever_tools.package.check` fails a packaged TOC whose `## Version` still starts with `v`.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .toc import toc_files

__all__ = ["KEYWORD", "bare", "described", "main", "stamp"]

KEYWORD = b"@project-version@"


def bare(tag: str) -> str:
    """A release tag (`v1.2.3`, or a describe form such as `v1.2.3-4-gabc1234`) as the TOC carries it: no `v`."""
    tag = tag.strip()
    return tag[1:] if tag[:1] in ("v", "V") and tag[1:2].isdigit() else tag


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout.strip()


def described(root: Path, ref: str | None = None) -> str:
    """The version the packager would read from git for `root`'s HEAD, without the tag's `v`.

    This follows the pinned packager's own choice: of the tags on HEAD, the one the workflow was pushed for
    (`GITHUB_REF`), else the newest; with no tag on HEAD, `git describe --tags --always --abbrev=7`."""
    ref = os.environ.get("GITHUB_REF", "") if ref is None else ref
    tags = git(
        root, "tag", "--points-at", "HEAD", "--sort=-committerdate", "--sort=-v:refname", "--sort=-taggerdate"
    ).splitlines()
    if tags:
        pushed = ref.removeprefix("refs/tags/") if ref.startswith("refs/tags/") else None
        return bare(pushed if pushed in tags else tags[0])
    return bare(git(root, "describe", "--tags", "--always", "--abbrev=7"))


def stamp(root: Path, version: str) -> list[Path]:
    """Replace the packager keyword in every addon TOC under `root` with `version`; return the TOCs changed.

    Each file keeps its own bytes otherwise, line endings and BOM included."""
    changed = []
    for toc in toc_files(root):
        raw = toc.read_bytes()
        if KEYWORD in raw:
            toc.write_bytes(raw.replace(KEYWORD, version.encode()))
            changed.append(toc)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        version = described(args.root)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"toc_version: could not read the version from git: {error}", file=sys.stderr)
        return 1
    changed = stamp(args.root, version)
    names = ", ".join(path.relative_to(args.root).as_posix() for path in changed) or "no TOC held the keyword"
    print(f"toc_version: {version}: {names}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
