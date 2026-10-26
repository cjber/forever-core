"""Check every consuming Forever addon's vendored copy against this repo.

The four addons that draw sections into the shared column each carry a byte-identical copy of the files listed in
VENDORED: that is what lets them work alone, with no dependency to install. This gate is what stops the copies
drifting: it compares each repo's main branch (or a local checkout) with this repo's copy and names every mismatch.
The split follows visibility: public consumers are compared from this repo, while the private one cannot be read here
and instead compares itself against public core from its own core-shared-drift.yml workflow.
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
MICRO_CONSUMERS = ("adventure-guide-forever",)
# Core/Text.lua goes to the three addons that search by name (Hoard, Adventure Guide and Shortest Path); the two
# private ones among them are compared from their own repos.
TEXT_CONSUMERS = ("adventure-guide-forever", "shortest-path-forever")
# The settings canvas goes to every addon in the suite, which is the five public consumers plus the three private ones.
SETTINGS_CONSUMERS = ALL_CONSUMERS
# Private repos cannot be read over unauthenticated raw.githubusercontent.com, so this gate names them instead of
# fetching them: each one runs its own tools/check_core_shared.py from .github/workflows/core-shared-drift.yml,
# comparing its vendored copies against public core main. tools/sync_consumers.py still syncs them.
PRIVATE_CONSUMERS = ("field-guide-forever", "atlas-forever", "hoard-forever")
ALL_SUITE_CONSUMERS = ALL_CONSUMERS + PRIVATE_CONSUMERS
CHECKOUT_ALIASES = {"field-guide-forever": "bestiary-forever"}
VENDORED = {
    "tools/deadcode.py": ALL_SUITE_CONSUMERS,
    "tools/deadcode-allow.txt": ALL_SUITE_CONSUMERS,
    "Core/Text.lua": TEXT_CONSUMERS,
    "tests/text_spec.lua": TEXT_CONSUMERS,
    "UI/SettingsPage.lua": SETTINGS_CONSUMERS,
    "tests/settings_page_spec.lua": SETTINGS_CONSUMERS,
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
    skipped = 0
    for path, consumers in VENDORED.items():
        mine = Path(path).read_bytes()
        for repo in consumers:
            # A private repo's copies are read from a local checkout when one is given, and otherwise left to that
            # repo's own drift workflow rather than counted as a match this gate cannot see.
            if not arguments.local and repo in PRIVATE_CONSUMERS:
                skipped += 1
                continue
            comparisons += 1
            try:
                if arguments.local:
                    theirs = (arguments.local / CHECKOUT_ALIASES.get(repo, repo) / path).read_bytes()
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
    if skipped:
        print(
            f"{skipped} copies in private repos were not read from here; "
            "each of those repos gates them from its own core-shared-drift.yml."
        )
    for repo in PRIVATE_CONSUMERS:
        print(f"{repo}: private, gated from its own repo by core-shared-drift.yml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
