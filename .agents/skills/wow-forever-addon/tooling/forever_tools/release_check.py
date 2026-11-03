"""Publish only a commit that passed the repository's complete CI workflow on main."""

import argparse
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
    print(f"Release verified: full CI passed on main at {commit}")
