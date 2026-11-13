#!/usr/bin/env python3
"""Smoke every commit the next release would ship that has no `headless-smoke` status, one client session at a time.

A release needs the `headless-smoke` commit status on its exact commit (`forever_tools/release_check.py`), and every
release of every Forever addon starts the same way: `release.yml` releases `main`'s head, and
`tools/release_consumers.py` dispatches that same commit for a consumer whose sync entry landed. This walks core and
every consumer, reads that commit, and for each one with no status yet builds it and runs
`tools/headless/forever_client.py smoke`, which posts the status itself. A commit that already carries a status of any
kind is left alone, so a green main head costs nothing and a failed one is not retried behind the maintainer's back.

    python3 tools/smoke_queue.py             # smoke every commit that needs it, then stop
    python3 tools/smoke_queue.py --dry-run   # print the commits that would be smoked

`tools/systemd/forever-smoke.timer` runs it every 30 minutes at `Nice=10` on the machine that has the client; see
`wow-forever-addon/in-game.md` for installing it. One client means one session: a smoke that exits 3 (the player's game
or another session holds the client) stops the run at once and leaves every later commit for the next timer, so the
queue never queues behind the player. It reads the same repository list, head commit and status as
`tools/release_consumers.py`, so a new addon needs no edit here.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from release_consumers import SyncError, consumer_repos, discover_tooling_repos, main_head, smoke_status
from sync_consumer_prs import CORE_REPO

CLIENT = Path(__file__).resolve().parent / "headless/forever_client.py"


def repositories() -> list[str]:
    """Every repository a release ships: core itself, then the consumers the sync keeps."""
    return [CORE_REPO, *consumer_repos(discover_tooling_repos())]


def next_release(repo: str) -> str:
    """The commit the next release would ship: `main`'s head, which `release.yml` tags and the consumer run dispatches.

    `tools/release_consumers.py` releases the head commit a marked `CHANGELOG.md` entry names, and a hand release tags
    a main commit that passed CI, so the head is the only commit either path can ship today.
    """
    return main_head(repo)


def smoke(repo: str, commit: str) -> int:
    """One smoke session through the client tool, which builds, tests and posts; 3 means the client is in use."""
    return subprocess.run(
        [sys.executable, str(CLIENT), "smoke", "--repo", repo, "--ref", commit], check=False
    ).returncode


def main(argv: list[str] | None = None) -> int:
    """Smoke each waiting commit in turn and print one line per repository; stop at the first client still in use."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="print the commits that would be smoked and write nothing"
    )
    args = parser.parse_args(argv)
    try:
        repos = repositories()
    except SyncError as error:
        print(f"::error::{error}")
        return 1
    failures = 0
    for repo in repos:
        try:
            commit = next_release(repo)
            state = smoke_status(repo, commit)
        except (SyncError, json.JSONDecodeError, OSError, KeyError, TypeError) as error:
            failures += 1
            print(f"{repo}: failed: {error}")
            continue
        if state != "missing":
            print(f"{repo}: {commit[:7]} already has {state} headless-smoke")
            continue
        if args.dry_run:
            print(f"{repo}: would smoke {commit[:7]}")
            continue
        code = smoke(repo, commit)
        if code == 3:
            print(f"{repo}: the client is in use; stopping until the next run")
            return 0
        if code == 1:
            failures += 1
            print(f"{repo}: {commit[:7]} recorded a failure")
            continue
        if code != 0:
            failures += 1
            print(f"{repo}: {commit[:7]} did not smoke (exit {code}); see the lines above")
            continue
        print(f"{repo}: {commit[:7]} is smoked")
    return int(failures > 0)


if __name__ == "__main__":
    sys.exit(main())
