"""Copy this repo's development tooling into the consumer addons' working trees.

Fixing a shared rule is one change here and one command, instead of eight hand-edited copies. Each target file is
overwritten only when its content differs, so a run on an up-to-date checkout touches nothing and every change is
visible in `git status` for the consumer's own PR.

Runtime files are no longer copied: every Forever addon requires ForeverCore with `## Dependencies: ForeverCore` and
runs the one copy the client loads.

A consumer whose addon lives below its repo root (kiln-forever, whose repository also carries a bridge) gets every file
under the addon folder CONSUMER_ROOT names.
"""

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

from check_core_shared import CONSUMER_ROOT, VENDORED, source

CORE_ROOT = Path(__file__).resolve().parent.parent


def consumer_path(repo, path):
    """Where `repo` keeps the vendored `path`, relative to that consumer repo's root."""
    folder = CONSUMER_ROOT.get(repo)
    return f"{folder}/{path}" if folder else path


def digest(data):
    """The hex SHA-256 of `data`, to compare a copy with its source."""
    return hashlib.sha256(data).hexdigest()


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
            target = root / consumer_path(repo, path)
            if not root.is_dir():
                print(f"{repo}: not checked out under {arguments.checkouts}, skipped")
                continue
            content = origin.read_bytes()
            if not (target.exists() and digest(target.read_bytes()) == digest(content)):
                changed += 1
                print(f"{repo}: {path}")
                if not arguments.dry_run:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(origin, target)
    if changed and not arguments.dry_run:
        print("Run each changed consumer's gates and open one PR per consumer for the shared tooling.")
    verb = "would change" if arguments.dry_run else "changed"
    print(f"{changed} file(s) {verb}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
