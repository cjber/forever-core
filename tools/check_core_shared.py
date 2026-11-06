"""Check this addon's vendored files against cjber/forever-core main.

Forever Core is the source of every file in VENDORED, this script included: core's tools/sync_consumers.py copies
them into each consumer and core's tools/check_consumers.py reads the same map. Run it from a consumer's root, whose
repository is inferred from its Git origin:

    python3 tools/check_core_shared.py             every file this repo vendors must match core main
    python3 tools/check_core_shared.py --base REF  only the vendored files that REF...HEAD changes

The `--base` form runs on pull requests: a PR that edits a vendored copy by hand fails, while a consumer that only
lags behind core does not block unrelated work. The full form runs on a schedule and reports the lag.
"""

import argparse
import hashlib
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

TRACKER_CONSUMERS = (
    "adventure-guide-forever",
    "legacy-forever",
    "shortest-path-forever",
    "skillup-forever",
)
ALL_CONSUMERS = TRACKER_CONSUMERS + ("tweaks-forever",)
MICRO_CONSUMERS = ("adventure-guide-forever", "field-guide-forever")
# Core/Text.lua goes to the addons that search by name.
TEXT_CONSUMERS = ("adventure-guide-forever", "shortest-path-forever")
# The settings canvas and the dead-code gate go to every addon with a settings page, Field Guide included.
SETTINGS_CONSUMERS = ALL_CONSUMERS + ("field-guide-forever",)
# This drift check reaches every addon in the suite.
SUITE_CONSUMERS = SETTINGS_CONSUMERS + ("commissions-forever",)
PEER_CONSUMERS = TRACKER_CONSUMERS + ("field-guide-forever", "commissions-forever")
MAP_CANVAS_CONSUMERS = ("adventure-guide-forever", "legacy-forever")

# Consumer path: the repos that carry it. A consumer keeps each file at the same path as core, except where SOURCES
# names the core file it is copied from.
VENDORED = {
    "UI/MapCanvas.lua": MAP_CANVAS_CONSUMERS,
    "tests/strict_map.lua": MAP_CANVAS_CONSUMERS,
    "tests/map_canvas_spec.lua": MAP_CANVAS_CONSUMERS,
    "tools/check_core_shared.py": SUITE_CONSUMERS,
    "tools/check_client_load.py": SUITE_CONSUMERS,
    "tools/blizzard_fonts.txt": SUITE_CONSUMERS,
    "tools/check_menu_scroll.py": SUITE_CONSUMERS,
    ".github/workflows/core-shared-drift.yml": SUITE_CONSUMERS,
    "tools/deadcode.py": SETTINGS_CONSUMERS,
    "tools/deadcode-allow.txt": SETTINGS_CONSUMERS,
    "Core/Text.lua": TEXT_CONSUMERS,
    "Core/PeerStats.lua": PEER_CONSUMERS,
    "tests/peer_stats_spec.lua": PEER_CONSUMERS,
    "tests/text_spec.lua": TEXT_CONSUMERS,
    "UI/SettingsPage.lua": SETTINGS_CONSUMERS,
    "tests/settings_page_spec.lua": SETTINGS_CONSUMERS,
    "Core/MicroButton.lua": MICRO_CONSUMERS,
    "tests/micro_button_spec.lua": MICRO_CONSUMERS,
    "UI/TrackerHost.lua": TRACKER_CONSUMERS,
    "UI/TrackerLock.lua": TRACKER_CONSUMERS,
    "UI/TrackerOrder.lua": TRACKER_CONSUMERS,
    "UI/TrackerQuestie.lua": TRACKER_CONSUMERS,
    "UI/TrackerEqot.lua": TRACKER_CONSUMERS,
    "tests/tracker_host_spec.lua": TRACKER_CONSUMERS,
    "tests/tracker_host_harness.lua": TRACKER_CONSUMERS,
    "tests/tracker_header_menu_spec.lua": TRACKER_CONSUMERS,
    "tests/tracker_combat_spec.lua": TRACKER_CONSUMERS,
    "tests/tracker_geometry_spec.lua": TRACKER_CONSUMERS,
    "tests/tracker_host_lock_spec.lua": TRACKER_CONSUMERS,
    "tests/tracker_questie_spec.lua": TRACKER_CONSUMERS,
    "tests/tracker_eqot_spec.lua": TRACKER_CONSUMERS,
    "tools/fetch_tracker_ui.py": TRACKER_CONSUMERS,
    "Core/SafeCall.lua": ALL_CONSUMERS,
    "UI/Report.lua": ALL_CONSUMERS,
    "tests/report_spec.lua": ALL_CONSUMERS,
    "UI/ForeverFamily.lua": ALL_CONSUMERS,
    "tests/forever_family_spec.lua": ALL_CONSUMERS,
}
# Core keeps the consumers' workflow out of its own .github/workflows, where it would run against core itself.
SOURCES = {".github/workflows/core-shared-drift.yml": "tools/core-shared-drift.yml"}


def source(path):
    """The path in forever-core that the consumer's `path` is copied from."""
    return SOURCES.get(path, path)


def paths_for(repo):
    return [path for path, consumers in VENDORED.items() if repo in consumers]


def repo_from_git():
    """Return the GitHub repo name, independent of the checkout directory or worktree name."""
    result = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=False)
    if result.returncode:
        return None
    remote = result.stdout.strip()
    if remote.startswith("git@github.com:"):
        name = remote.removeprefix("git@github.com:")
    else:
        parsed = urlparse(remote)
        if parsed.hostname != "github.com":
            return None
        name = parsed.path.lstrip("/")
    name = name.strip("/")
    if name.lower().endswith(".git"):
        name = name[:-4]
    owner, separator, repo = name.partition("/")
    repo = repo.lower()
    return repo if separator and owner.lower() == "cjber" and repo in SUITE_CONSUMERS else None


def changed_since(base):
    """Every path that `base...HEAD` adds, changes, renames or deletes."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise SystemExit(f"git diff {base}...HEAD failed: {result.stderr.strip()}")
    return set(result.stdout.split())


def core_main(path):
    url = f"https://raw.githubusercontent.com/cjber/forever-core/main/{source(path)}"
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def compare(root, paths, fetch=core_main):
    failures = []
    for path in paths:
        try:
            expected = fetch(path)
        except (OSError, urllib.error.URLError, TimeoutError) as error:
            failures.append(f"{path}: could not read core main: {error}")
            continue
        target = root / path
        if not target.is_file():
            failures.append(f"{path}: missing here, core {hashlib.sha256(expected).hexdigest()[:12]}")
            continue
        actual = target.read_bytes()
        if actual != expected:
            failures.append(
                f"{path}: consumer {hashlib.sha256(actual).hexdigest()[:12]} "
                f"core {hashlib.sha256(expected).hexdigest()[:12]}"
            )
    return failures


def main(argv=None, fetch=core_main):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", help="check only the vendored files that BASE...HEAD changes")
    parser.add_argument("--repo", help="this consumer's repo name (default: infer it from Git origin)")
    arguments = parser.parse_args(argv)

    root = Path.cwd()
    if arguments.repo and arguments.repo not in SUITE_CONSUMERS:
        raise SystemExit(f"Unknown consumer repo: {arguments.repo}")
    repo = arguments.repo or repo_from_git()
    if repo is None:
        raise SystemExit("Cannot identify a known cjber consumer from git remote; pass --repo explicitly.")
    paths = paths_for(repo)
    if arguments.base:
        touched = changed_since(arguments.base)
        paths = [path for path in paths if path in touched]
        if not paths:
            print(f"No vendored file changed since {arguments.base}.")
            return 0
    failures = compare(root, paths, fetch)
    if failures:
        print("Vendored files differ from forever-core main:\n  " + "\n  ".join(failures))
        print("Change the file in cjber/forever-core, then copy it here with its tools/sync_consumers.py.")
        return 1
    print(f"{len(paths)} vendored files match forever-core main.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
