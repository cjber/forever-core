"""Publish only a commit that passed the repository's complete CI workflow on main and its headless smoke.

Every release, manual or automatic, ships one commit and needs two records on that exact commit: the full CI push run
on main, and the `headless-smoke` commit status the headless client posts after it loaded that commit's build, ran
`/forever selftest` and found no Lua errors. A missing or pending status waits for `forever_client.py smoke`, and a
failed one prints what it found, so a release never ships a build nobody loaded.

A manual release may add `--skip-visual-proof` when the only job that failed is `visual-proof`, the recorded client
session a maintainer waives on purpose. Every other job must still pass, and the headless smoke is never skipped.
"""

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable

CI_WORKFLOW = ".github/workflows/ci.yml"
# The commit status `python3 tools/headless/forever_client.py smoke --repo R --ref SHA` posts, which
# `tools/smoke_queue.py` fills in for every commit a release would ship.
SMOKE_CONTEXT = "headless-smoke"
# The one job `--skip-visual-proof` accepts as a failure; it is the recorded client session, which a maintainer may
# choose to waive for a release whose change no capture covers yet.
VISUAL_PROOF_JOB = "visual-proof"
# A job with one of these conclusions did not fail its run; any other conclusion, including a missing one, did.
NOT_FAILED = frozenset({"success", "skipped", "neutral"})

# Reads one workflow run's jobs, so `verified` stays a pure decision over data the caller fetched.
JobsFor = Callable[[dict], list[dict]]


def failed_jobs(jobs: list[dict]) -> list[str]:
    """The names of the jobs that did not pass."""
    return [job.get("name") or "" for job in jobs if job.get("conclusion") not in NOT_FAILED]


def verified(
    runs: list[dict],
    commit: str,
    jobs_for: JobsFor | None = None,
    skip_visual_proof: bool = False,
) -> bool:
    """Whether a full CI push run on main for this exact commit passed.

    `jobs_for` reads one run's jobs and is consulted only when `skip_visual_proof` lets a run that failed solely in
    `visual-proof` pass: at least one job must have failed, and every failed job must be that one. A failure no job
    explains is not a visual-proof failure, so it never passes.
    """
    for run in runs:
        if not (
            run.get("head_sha") == commit
            and run.get("head_branch") == "main"
            and run.get("path") == CI_WORKFLOW
            and run.get("event") == "push"
            and run.get("status") == "completed"
        ):
            continue
        conclusion = run.get("conclusion")
        if conclusion == "success":
            return True
        if skip_visual_proof and conclusion == "failure" and jobs_for is not None:
            failed = failed_jobs(jobs_for(run))
            if failed and all(name == VISUAL_PROOF_JOB for name in failed):
                return True
    return False


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


def jobs(repository: str, run_id: int) -> list[dict]:
    """Every job in one workflow run, so a failed run can name the jobs that failed."""
    pages = json.loads(
        subprocess.check_output(
            ["gh", "api", "--paginate", "--slurp", f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100"],
            text=True,
        )
    )
    return [job for page in pages for job in page["jobs"]]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-visual-proof",
        action="store_true",
        help=f"accept a completed full CI run on main that failed only in the {VISUAL_PROOF_JOB} job",
    )
    arguments = parser.parse_args(argv)
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
    skipped = False
    if not verified(runs, commit):
        waived = arguments.skip_visual_proof and verified(
            runs,
            commit,
            jobs_for=lambda run: jobs(repository, run["id"]),
            skip_visual_proof=True,
        )
        if not waived:
            sys.exit("Release blocked: this exact commit needs a successful full CI run on main.")
        skipped = True
    refusal = smoke_refusal(headless_smoke(statuses(repository, commit)), repository, commit)
    if refusal:
        sys.exit(f"Release blocked: {refusal}")
    if skipped:
        print(f"Release skips the failed {VISUAL_PROOF_JOB} job on {commit}: --skip-visual-proof was given")
    detail = f" (skipping {VISUAL_PROOF_JOB})" if skipped else ""
    print(f"Release verified: full CI passed on main{detail} and {SMOKE_CONTEXT} passed at {commit}")
