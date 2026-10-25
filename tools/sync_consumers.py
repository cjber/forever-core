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

ALL_CONSUMERS = (
    "adventure-guide-forever",
    "legacy-forever",
    "shortest-path-forever",
    "skillup-forever",
    "tweaks-forever",
)

TRACKER_CONSUMERS = ALL_CONSUMERS[:-1]
MICRO_CONSUMERS = ("adventure-guide-forever", "bestiary-forever")
VENDORED = {
    "Core/MicroButton.lua": MICRO_CONSUMERS,
    "tests/micro_button_spec.lua": MICRO_CONSUMERS,
    "UI/TrackerHost.lua": TRACKER_CONSUMERS,
    "UI/TrackerLock.lua": TRACKER_CONSUMERS,
    "UI/TrackerOrder.lua": TRACKER_CONSUMERS,
    "UI/TrackerQuestie.lua": TRACKER_CONSUMERS,
    "tests/tracker_host_spec.lua": TRACKER_CONSUMERS,
    "tests/tracker_host_harness.lua": TRACKER_CONSUMERS,
    "tests/tracker_questie_spec.lua": TRACKER_CONSUMERS,
    "tools/fetch_tracker_ui.py": TRACKER_CONSUMERS,
    "Core/SafeCall.lua": ALL_CONSUMERS,
    "UI/Report.lua": ALL_CONSUMERS,
    "tests/report_spec.lua": ALL_CONSUMERS,
    "UI/ForeverFamily.lua": ALL_CONSUMERS,
    "tests/forever_family_spec.lua": ALL_CONSUMERS,
}


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
        source = Path(path)
        for repo in consumers:
            root = arguments.checkouts / repo
            target = root / path
            if not root.is_dir():
                print(f"{repo}: not checked out under {arguments.checkouts}, skipped")
                continue
            content = source.read_bytes()
            if target.exists() and digest(target.read_bytes()) == digest(content):
                continue
            changed += 1
            print(f"{repo}: {path}")
            if not arguments.dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    if changed and not arguments.dry_run:
        print("Run each changed consumer's gates and open one PR per consumer for all shared files.")
    verb = "would change" if arguments.dry_run else "changed"
    print(f"{changed} file(s) {verb}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
