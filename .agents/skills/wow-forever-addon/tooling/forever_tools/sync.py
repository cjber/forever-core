#!/usr/bin/env python3
"""Verify, update and pin a vendored copy of forever_tools against its producer (stdlib only, offline by default).

    sync.py check                     # every file matches MANIFEST.json, and the copy is pinned
    sync.py check --source ~/forever-core   # also match a producer checkout at the pinned revision
    sync.py update --source ~/forever-core  # copy the producer's files; the only command that writes them
    sync.py pin <40-hex revision>     # record the producer commit the files came from
    sync.py manifest                  # in the producer: refresh the hashes after an edit

(Run from the repository root as `python3 tools/forever_tools/sync.py`.)

MANIFEST.json lists each file's sha256 and the producer revision (`UNPINNED` until a commit is named). A vendored
copy is never changed by `check`; edit the producer and run `update`.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
PRODUCER_PATH = ".agents/skills/wow-forever-addon/tooling/forever_tools"
REPOSITORY = "https://github.com/cjber/forever-core"
UNPINNED = "UNPINNED"
MANIFEST = "MANIFEST.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.py"))


def hashes(directory: Path) -> dict[str, str]:
    return {path.name: digest(path) for path in sources(directory)}


def read_manifest(directory: Path) -> dict:
    return json.loads((directory / MANIFEST).read_text(encoding="utf-8"))


# gitleaks' generic-api-key reads `"<name>": "<64 hex>"` as a credential when the name holds one of these, and every
# addon's CI runs gitleaks over the vendored MANIFEST.json.
SECRET_WORDS = re.compile(r"access|auth|api|credential|creds|key|passw|pwd|secret|token", re.IGNORECASE)


def write_manifest(directory: Path, revision: str) -> None:
    manifest = {
        "package": "forever_tools",
        "source": {"repository": REPOSITORY, "path": PRODUCER_PATH, "revision": revision},
        "files": hashes(directory),
    }
    (directory / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def problems(directory: Path, expected: dict[str, str]) -> list[str]:
    found = hashes(directory)
    return [
        *(f"{name}: missing" for name in sorted(expected.keys() - found.keys())),
        *(f"{name}: not in {MANIFEST}" for name in sorted(found.keys() - expected.keys())),
        *(
            f"{name}: changed (edit the producer, then run update)"
            for name in sorted(found)
            if name in expected and found[name] != expected[name]
        ),
    ]


def git(source: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()


def producer(source: Path) -> Path:
    directory = source / PRODUCER_PATH
    if not directory.is_dir():
        raise SystemExit(f"{source} has no {PRODUCER_PATH}")
    return directory


def check(allow_unpinned: bool, source: Path | None) -> int:
    manifest = read_manifest(PACKAGE)
    revision = manifest["source"]["revision"]
    failures = problems(PACKAGE, manifest["files"])
    if revision == UNPINNED and not allow_unpinned:
        failures.append(f"{MANIFEST}: revision is {UNPINNED}; run `sync.py pin <producer commit>`")
    if source is not None:
        directory = producer(source)
        if git(source, "rev-parse", "HEAD") != revision:
            failures.append(f"{source} is not at the pinned revision {revision}")
        if git(source, "status", "--porcelain", "--", PRODUCER_PATH):
            failures.append(f"{source} has uncommitted changes under {PRODUCER_PATH}")
        failures += [
            f"{name}: differs from the producer"
            for name in sorted(hashes(directory).keys() | manifest["files"].keys())
            if hashes(directory).get(name) != manifest["files"].get(name)
        ]
    for failure in failures:
        print(failure, file=sys.stderr)
    if not failures:
        print(f"forever_tools: {len(manifest['files'])} files match {MANIFEST} (revision {revision})")
    return int(bool(failures))


def update(source: Path, revision: str | None) -> int:
    directory = producer(source)
    head = git(source, "rev-parse", "HEAD")
    if revision and revision != head:
        raise SystemExit(f"{source} is at {head}, not {revision}")
    if git(source, "status", "--porcelain", "--", PRODUCER_PATH):
        raise SystemExit(f"{source} has uncommitted changes under {PRODUCER_PATH}; commit the producer first")
    expected = read_manifest(directory)["files"]
    if hashes(directory) != expected:
        raise SystemExit("the producer's MANIFEST.json is stale; run `sync.py manifest` there and commit")
    for stale in sources(PACKAGE):
        if stale.name not in expected:
            stale.unlink()
    for name in expected:
        shutil.copyfile(directory / name, PACKAGE / name)
    write_manifest(PACKAGE, head)
    print(f"forever_tools: updated {len(expected)} files to {head}")
    return 0


def pin(revision: str) -> int:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise SystemExit("give the full 40-character producer commit")
    write_manifest(PACKAGE, revision)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("check", help="verify the copy offline")
    verify.add_argument("--allow-unpinned", action="store_true", help="accept revision UNPINNED (the producer itself)")
    verify.add_argument("--source", type=Path, help="a producer checkout at the pinned revision to compare with")
    refresh = commands.add_parser("update", help="copy the producer's files and pin its HEAD")
    refresh.add_argument("--source", type=Path, required=True)
    refresh.add_argument("--revision", help="the commit the source must be at")
    commands.add_parser("pin", help="record the producer commit").add_argument("revision")
    commands.add_parser("manifest", help="refresh the hashes in the producer's MANIFEST.json")
    args = parser.parse_args(argv)
    if args.command == "check":
        return check(args.allow_unpinned, args.source)
    if args.command == "update":
        return update(args.source, args.revision)
    if args.command == "pin":
        return pin(args.revision)
    if (PACKAGE / MANIFEST).exists() and read_manifest(PACKAGE)["source"]["revision"] != UNPINNED:
        raise SystemExit("this is a pinned vendored copy; edit the producer and run update")
    flagged = [path.name for path in sources(PACKAGE) if SECRET_WORDS.search(path.stem)]
    if flagged:
        raise SystemExit(f"rename {', '.join(flagged)}: gitleaks reads its MANIFEST.json hash as a credential")
    write_manifest(PACKAGE, UNPINNED)
    return 0


if __name__ == "__main__":
    sys.exit(main())
