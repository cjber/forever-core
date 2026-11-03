"""Copy this repo's shared files into the consumer addons' working trees.

Fixing the column is one change here and one command, instead of four hand-edited copies. Each target file is
overwritten only when its content differs, so a run on an up-to-date checkout touches nothing and every change is
visible in `git status` for the consumer's own PR.
"""

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

from check_core_shared import VENDORED, source


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkouts", type=Path, help="the directory holding the consumer checkouts")
    parser.add_argument("--dry-run", action="store_true", help="report what would change and write nothing")
    parser.add_argument("--only", action="append", choices=VENDORED, help="sync only this shared path; may be repeated")
    arguments = parser.parse_args()

    changed = 0
    selected = arguments.only or VENDORED.keys()
    for path in selected:
        consumers = VENDORED[path]
        origin = Path(source(path))
        for repo in consumers:
            root = arguments.checkouts / repo
            target = root / path
            if not root.is_dir():
                print(f"{repo}: not checked out under {arguments.checkouts}, skipped")
                continue
            content = origin.read_bytes()
            if target.exists() and digest(target.read_bytes()) == digest(content):
                continue
            changed += 1
            print(f"{repo}: {path}")
            if not arguments.dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origin, target)
    if changed and not arguments.dry_run:
        print("Run each changed consumer's gates and open one PR per consumer for all shared files.")
    verb = "would change" if arguments.dry_run else "changed"
    print(f"{changed} file(s) {verb}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
