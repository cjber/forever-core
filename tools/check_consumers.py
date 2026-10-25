"""Check every consuming Forever addon's vendored copy against this repo.

The four addons that draw sections into the shared column each carry a byte-identical copy of the files listed in
VENDORED: that is what lets them work alone, with no dependency to install. This gate is what stops the copies
drifting: it compares each repo's main branch (or a local checkout) with this repo's copy and names every mismatch.
"""

import argparse
import hashlib
import sys
import urllib.error
import urllib.request
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


def remote(repo, path, branch):
    url = f"https://raw.githubusercontent.com/cjber/{repo}/{branch}/{path}"
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", default="main", help="the consumers' branch to compare (default: main)")
    parser.add_argument("--local", type=Path, help="compare checkouts under this directory instead of GitHub")
    arguments = parser.parse_args()

    failures = []
    comparisons = 0
    for path, consumers in VENDORED.items():
        mine = Path(path).read_bytes()
        for repo in consumers:
            comparisons += 1
            try:
                if arguments.local:
                    theirs = (arguments.local / repo / path).read_bytes()
                else:
                    theirs = remote(repo, path, arguments.branch)
            except (OSError, urllib.error.URLError, TimeoutError) as error:
                failures.append(f"{repo}: {path}: could not be read: {error}")
                continue
            if digest(theirs) != digest(mine):
                failures.append(f"{repo}: {path}: {digest(theirs)[:12]} here {digest(mine)[:12]}")

    if failures:
        print("Vendored copies drifted from this repo's shared files:")
        for failure in failures:
            print(f"  {failure}")
        print("Fix with tools/sync_consumers.py, then commit the copies in the consumer repos.")
        return 1
    print(f"{comparisons} shared file copies match their consumer repos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
