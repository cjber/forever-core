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

CONSUMERS = (
    "adventure-guide-forever",
    "legacy-forever",
    "shortest-path-forever",
    "skillup-forever",
)

VENDORED = (
    "UI/TrackerHost.lua",
    "UI/TrackerLock.lua",
    "UI/TrackerOrder.lua",
    "UI/TrackerQuestie.lua",
    "tests/tracker_host_spec.lua",
    "tests/tracker_questie_spec.lua",
    "tools/fetch_tracker_ui.py",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkouts", type=Path, help="the directory holding the consumer checkouts")
    parser.add_argument("--dry-run", action="store_true", help="report what would change and write nothing")
    arguments = parser.parse_args()

    changed = 0
    for repo in CONSUMERS:
        root = arguments.checkouts / repo
        if not root.is_dir():
            print(f"{repo}: not checked out under {arguments.checkouts}, skipped")
            continue
        for path in VENDORED:
            source = Path(path)
            target = root / path
            content = source.read_bytes()
            if target.exists() and digest(target.read_bytes()) == digest(content):
                continue
            changed += 1
            print(f"{repo}: {path}")
            if not arguments.dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        if not arguments.dry_run:
            print(f"{repo}: run its gates (luacheck, stylua, the specs) and open one PR for all shared files")
    verb = "would change" if arguments.dry_run else "changed"
    print(f"{changed} file(s) {verb}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
