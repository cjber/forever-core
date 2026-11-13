"""Publish only a commit that passed the repository's complete CI workflow on main and its headless smoke.

Every release, manual or automatic, ships one commit and needs two records on that exact commit: the full CI push run
on main, and the `headless-smoke` commit status the headless client posts after it loaded that commit's build, ran
`/forever selftest` and found no Lua errors. A missing or pending status waits for `forever_client.py smoke`, and a
failed one prints what it found, so a release never ships a build nobody loaded.
"""

import argparse
import json
import os
import subprocess
import sys

CI_WORKFLOW = ".github/workflows/ci.yml"
# The commit status `python3 tools/headless/forever_client.py smoke --repo R --ref SHA` posts, which
# `tools/smoke_queue.py` fills in for every commit a release would ship.
SMOKE_CONTEXT = "headless-smoke"


def verified(runs: list[dict], commit: str) -> bool:
    return any(
        run.get("head_sha") == commit
        and run.get("head_branch") == "main"
        and run.get("path") == CI_WORKFLOW
        and run.get("event") == "push"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        for run in runs
    )


def headless_smoke(statuses: list[dict]) -> dict | None:
    """The newest `headless-smoke` status on the commit, or None; the statuses API lists the newest first."""
    return next((status for status in statuses if status.get("context") == SMOKE_CONTEXT), None)


def smoke_refusal(status: dict | None, repository: str, commit: str) -> str | None:
    """Why this commit may not be released yet, or None when its newest headless smoke passed."""
    state = (status or {}).get("state")
    if state == "success":
        return None
    if state in (None, "pending"):
        return (
            f"waiting for {SMOKE_CONTEXT} on {commit}: run forever_client.py smoke "
            f"--repo {repository.split('/', 1)[-1]} --ref {commit}"
        )
    return f"{SMOKE_CONTEXT} on {commit} is {state}: {(status or {}).get('description') or 'no description'}"


def statuses(repository: str, commit: str) -> list[dict]:
    """Every commit status on the commit, newest first."""
    pages = json.loads(
        subprocess.check_output(
            ["gh", "api", "--paginate", "--slurp", f"repos/{repository}/commits/{commit}/statuses"],
            text=True,
        )
    )
    return [status for page in pages for status in page]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    repository, commit = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_SHA")
    if not repository or not commit:
        parser.error("GITHUB_REPOSITORY and GITHUB_SHA must identify the release commit")
    pages = json.loads(
        subprocess.check_output(
            [
                "gh",
                "api",
                "--paginate",
                "--slurp",
                f"repos/{repository}/actions/workflows/ci.yml/runs?head_sha={commit}&event=push&per_page=100",
            ],
            text=True,
        )
    )
    runs = [run for page in pages for run in page["workflow_runs"]]
    if not verified(runs, commit):
        sys.exit("Release blocked: this exact commit needs a successful full CI run on main.")
    refusal = smoke_refusal(headless_smoke(statuses(repository, commit)), repository, commit)
    if refusal:
        sys.exit(f"Release blocked: {refusal}")
    print(f"Release verified: full CI passed on main and {SMOKE_CONTEXT} passed at {commit}")
