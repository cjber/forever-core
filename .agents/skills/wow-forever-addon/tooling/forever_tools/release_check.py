"""Publish only a commit that passed the repository's complete CI workflow on main and its in-game checks.

Every release, manual or automatic, ships one commit and needs two things for it: the full CI push run on main for that
exact commit, and evidence that its build passed its pre-release checks with no Lua errors. The evidence is either the
committed `.visual-proof.json`, when it verifies against the commit's files and carries passing in-game checks, or the
`headless-smoke` commit status. The proof is bound to file contents, so the proof of a pull request also covers its
merge commit and a release preparation's version bump. A commit whose contents no proof covers waits for the smoke,
and a failed smoke prints what it found, so a release never ships a build that was not checked.

A version publishes once. The tag names one build, so a release whose GitHub release already carries a package, or
whose version CurseForge already lists, is refused: a re-tagged or re-run version would put a second, different build
under a number players already installed, and their clients never replace it (cjber/skillup-forever#901). Ship the
change as the next version instead.

A manual release may add `--skip-visual-proof` when the only job that failed is `visual-proof`, the recorded
visual proof a maintainer waives on purpose. Every other job must still pass, and the in-game evidence is never skipped.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

from . import visual_proof

CI_WORKFLOW = ".github/workflows/ci.yml"
# The commit status that records a commit's pre-release checks; a release needs it green on its exact commit.
SMOKE_CONTEXT = "headless-smoke"
# The one job `--skip-visual-proof` accepts as a failure; it is the recorded visual proof, which a maintainer may
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
    """Why this commit may not be released yet, or None when its newest release smoke passed."""
    state = (status or {}).get("state")
    if state == "success":
        return None
    if state in (None, "pending"):
        return f"waiting for {SMOKE_CONTEXT} on {commit}"
    return f"{SMOKE_CONTEXT} on {commit} is {state}: {(status or {}).get('description') or 'no description'}"


def proof_refusal(root: Path) -> str | None:
    """Why the checkout's committed proof does not stand in for the headless smoke, or None when it does."""
    problems = visual_proof.proof_problems(root, root / visual_proof.PROOF, release=True)
    return "; ".join(problems) if problems else None


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


def release_tag(environ: dict) -> str | None:
    """The tag this run publishes: the pushed tag, or `v` and the version a manual run was given."""
    if environ.get("GITHUB_REF", "").startswith("refs/tags/"):
        return environ.get("GITHUB_REF_NAME") or None
    event = environ.get("GITHUB_EVENT_PATH")
    if not event:
        return None
    version = (json.loads(Path(event).read_text(encoding="utf-8")).get("inputs") or {}).get("version")
    return f"v{version}" if version else None


def curseforge_projects(root: Path) -> list[str]:
    """The CurseForge project IDs the root TOC files name; none for an addon that ships only on GitHub."""
    projects = set()
    for toc in sorted(root.glob("*.toc")):
        for line in toc.read_text(encoding="utf-8-sig").splitlines():
            key, _, value = line.removeprefix("##").partition(":")
            if line.startswith("##") and key.strip() == "X-Curse-Project-ID" and value.strip():
                projects.add(value.strip())
    return sorted(projects)


def names_version(file_name: str, tag: str) -> bool:
    """Whether a package name carries this tag: the packager names files `<Package>-<tag>[-<label>].zip`."""
    return tag in file_name.removesuffix(".zip").split("-")


def curseforge_json(url: str) -> dict:
    """One page of CurseForge's public file listing, the one the store audit reads without a key."""
    with urllib.request.urlopen(urllib.request.Request(url), timeout=60) as response:
        return json.load(response)


# Reads one URL's JSON, so `curseforge_files` stays testable over recorded pages.
Fetch = Callable[[str], dict]


def curseforge_files(project: str, fetch: Fetch = curseforge_json) -> list[str]:
    """Every file name the project lists, in any release type or review state."""
    names, page = [], 0
    while True:
        # pageIndex counts pages, not files.
        listing = fetch(f"https://www.curseforge.com/api/v1/mods/{project}/files?pageIndex={page}&pageSize=50")
        names.extend(item["fileName"] for item in listing["data"])
        page += 1
        if not listing["data"] or len(names) >= listing["pagination"]["totalCount"]:
            return names


def github_release_assets(repository: str, tag: str) -> list[str] | None:
    """The asset names on the GitHub release for this tag, or None when it has no release, drafts included."""
    pages = json.loads(
        subprocess.check_output(
            ["gh", "api", "--paginate", "--slurp", f"repos/{repository}/releases?per_page=100"],
            text=True,
        )
    )
    for release in (release for page in pages for release in page):
        if release.get("tag_name") == tag:
            return [asset["name"] for asset in release.get("assets", [])]
    return None


def published_refusal(
    tag: str,
    github_assets: list[str] | None,
    store_files: dict[str, list[str]],
) -> str | None:
    """Why this version may not publish, or None when no GitHub package and no CurseForge file carries it yet."""
    packages = [name for name in github_assets or [] if name.endswith(".zip")]
    if packages:
        return f"{tag} is already published on GitHub ({', '.join(packages)}); release the change as the next version"
    for project, names in store_files.items():
        listed = [name for name in names if names_version(name, tag)]
        if listed:
            return (
                f"{tag} is already on CurseForge project {project} ({', '.join(listed)}); "
                "release the change as the next version"
            )
    return None


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
    proof = proof_refusal(Path.cwd())
    if proof:
        refusal = smoke_refusal(headless_smoke(statuses(repository, commit)), repository, commit)
        if refusal:
            sys.exit(f"Release blocked: {refusal}; the committed visual proof does not stand in for it: {proof}")
    tag = release_tag(dict(os.environ))
    if tag is None:
        sys.exit("Release blocked: neither a pushed tag nor a manual run's version names the release")
    store = {project: curseforge_files(project) for project in curseforge_projects(Path.cwd())}
    refusal = published_refusal(tag, github_release_assets(repository, tag), store)
    if refusal:
        sys.exit(f"Release blocked: {refusal}")
    if skipped:
        print(f"Release skips the failed {VISUAL_PROOF_JOB} job on {commit}: --skip-visual-proof was given")
    detail = f" (skipping {VISUAL_PROOF_JOB})" if skipped else ""
    evidence = f"{SMOKE_CONTEXT} passed" if proof else f"{visual_proof.PROOF} proves the build"
    print(
        f"Release verified: full CI passed on main{detail} and {evidence} at {commit}, and {tag} is not published yet"
    )
