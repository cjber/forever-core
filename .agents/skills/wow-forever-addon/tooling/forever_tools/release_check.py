"""Publish only a commit that passed the repository's complete CI workflow on main."""

import json
import os
import subprocess
import sys

CI_WORKFLOW = ".github/workflows/ci.yml"


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


def main() -> None:
    repository, commit = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
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
    print(f"Release verified: full CI passed on main at {commit}")
