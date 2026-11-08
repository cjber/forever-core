"""Open or update the per-consumer sync PR after a push to forever-core main.

The consumers are the repositories in `check_core_shared.VENDORED`, plus every non-archived `cjber` repository that
vendors `tools/forever_tools/MANIFEST.json` or `tools/forever_sim/MANIFEST.json`. There is no second consumer list to
edit: the first comes from the vendoring map, the second from the repositories themselves.

For each consumer this clones `main`, runs the same three syncs a maintainer would (`tools/sync_consumers.py` for this
repository, then the consumer's own `forever_tools/sync.py update` and `forever_sim/sync.py update`), and, if anything
changed, force-pushes `forever-core-sync` and opens or refreshes the PR with squash auto-merge enabled. The consumer's
own checks remain the gate: a sync that breaks one stays open as a red PR and is named in the run summary.

    python3 tools/sync_consumer_prs.py

Set `GH_TOKEN` to the `CONSUMER_SYNC_TOKEN` secret, a fine-grained PAT with Contents, Pull requests and Workflows
write on the consumer repositories (Workflows because `.github/workflows/core-shared-drift.yml` is vendored). Without
it the script prints a notice and exits 0, so the workflow stays green until the owner adds the secret.
"""

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from check_core_shared import VENDORED

OWNER = "cjber"
CORE_REPO = "forever-core"
BRANCH = "forever-core-sync"
TITLE = "chore: sync shared files from forever-core"
TOOLING_MANIFESTS = ("tools/forever_tools/MANIFEST.json", "tools/forever_sim/MANIFEST.json")
COMMIT_NAME = "github-actions[bot]"
COMMIT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


class SyncError(RuntimeError):
    """A git, gh or sync command failed."""


@dataclass
class Result:
    repo: str
    status: str
    files: tuple[str, ...] = ()
    url: str | None = None
    detail: str | None = None


def run(command: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise SyncError(f"{' '.join(command)} failed: {detail}")
    return result


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", *args], cwd=root, check=check)


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["gh", *args], check=check)


def consumer_repos(discovered=()) -> list[str]:
    """VENDORED's repositories plus repositories found to vendor the tooling, never this repo."""
    vendored = {repo for repos in VENDORED.values() for repo in repos}
    return sorted((vendored | set(discovered)) - {CORE_REPO})


def repo_vendors_tooling(repo: str) -> bool:
    for path in TOOLING_MANIFESTS:
        if gh("api", f"repos/{OWNER}/{repo}/contents/{path}", "--silent", check=False).returncode == 0:
            return True
    return False


def discover_tooling_repos() -> set[str]:
    """The live repositories that vendor the tooling, so a new consumer needs no edit here."""
    try:
        listed = json.loads(gh("repo", "list", OWNER, "--limit", "200", "--json", "name,isArchived").stdout)
    except (SyncError, json.JSONDecodeError) as error:
        print(f"::warning::Could not list {OWNER}'s repositories ({error}); using VENDORED's consumers only.")
        return set()
    return {
        item["name"]
        for item in listed
        if not item.get("isArchived") and item["name"] != CORE_REPO and repo_vendors_tooling(item["name"])
    }


def tooling_packages(root: Path) -> list[str]:
    """The tooling packages this checkout carries, in a stable order."""
    return [path.split("/")[1] for path in TOOLING_MANIFESTS if (root / path).is_file()]


def clone(repo: str, workspace: Path) -> Path:
    destination = workspace / repo
    run(
        [
            "git",
            "clone",
            "--depth=1",
            "--branch",
            "main",
            f"https://github.com/{OWNER}/{repo}.git",
            str(destination),
        ]
    )
    return destination


def sync_checkout(root: Path, core_root: Path) -> None:
    run([sys.executable, str(core_root / "tools/sync_consumers.py"), str(root.parent)])
    for package in tooling_packages(root):
        run(
            [sys.executable, str(root / "tools" / package / "sync.py"), "update", "--source", str(core_root)],
            cwd=root,
        )


def staged_files(root: Path) -> tuple[str, ...]:
    git(root, "add", "-A")
    return tuple(sorted(filter(None, git(root, "diff", "--cached", "--name-only").stdout.splitlines())))


def commit(root: Path, sha: str) -> None:
    git(
        root,
        "-c",
        f"user.name={COMMIT_NAME}",
        "-c",
        f"user.email={COMMIT_EMAIL}",
        "commit",
        "--quiet",
        "-m",
        f"{TITLE}\n\nCore commit: {sha}",
    )


def pr_body(sha: str, files: tuple[str, ...]) -> str:
    lines = [
        "Syncs this addon's copy of the shared Forever Core files.",
        "",
        f"Core commit: https://github.com/{OWNER}/{CORE_REPO}/commit/{sha}",
        "",
        "Files:",
        *(f"- `{path}`" for path in files),
        "",
        "Opened by the sync-consumers workflow in cjber/forever-core. The addon's own checks are the gate.",
    ]
    return "\n".join(lines) + "\n"


def open_or_update_pr(repo: str, body: str) -> tuple[int, str, str]:
    listed = json.loads(
        gh(
            "pr",
            "list",
            "--repo",
            f"{OWNER}/{repo}",
            "--head",
            BRANCH,
            "--state",
            "open",
            "--json",
            "number,url",
        ).stdout
    )
    if listed:
        number, url, status = listed[0]["number"], listed[0]["url"], "updated"
        gh("pr", "edit", str(number), "--repo", f"{OWNER}/{repo}", "--title", TITLE, "--body", body)
        return number, url, status
    output = [
        line.strip()
        for line in gh(
            "pr",
            "create",
            "--repo",
            f"{OWNER}/{repo}",
            "--base",
            "main",
            "--head",
            BRANCH,
            "--title",
            TITLE,
            "--body",
            body,
        ).stdout.splitlines()
        if line.strip()
    ]
    url = output[-1]
    return int(url.rstrip("/").rsplit("/", 1)[-1]), url, "opened"


def enable_auto_merge(repo: str, number: int) -> None:
    view = json.loads(gh("pr", "view", str(number), "--repo", f"{OWNER}/{repo}", "--json", "autoMergeRequest").stdout)
    if view.get("autoMergeRequest") is None:
        gh("pr", "merge", str(number), "--repo", f"{OWNER}/{repo}", "--squash", "--auto")


def sync_consumer(repo: str, core_root: Path, workspace: Path, sha: str) -> Result:
    try:
        root = clone(repo, workspace)
        git(root, "checkout", "-B", BRANCH)
        sync_checkout(root, core_root)
        files = staged_files(root)
        if not files:
            return Result(repo, "up to date")
        commit(root, sha)
        git(root, "push", "--force", "origin", f"HEAD:refs/heads/{BRANCH}")
        number, url, status = open_or_update_pr(repo, pr_body(sha, files))
        enable_auto_merge(repo, number)
        return Result(repo, status, files, url)
    except (SyncError, json.JSONDecodeError, OSError) as error:
        return Result(repo, "failed", detail=str(error))


def summary_markdown(sha: str, results: list[Result]) -> str:
    lines = [
        "## Forever Core consumer sync",
        "",
        f"Core commit: `{sha}`",
        "",
        "| Consumer | Result | Files | PR |",
        "|---|---|---|---|",
    ]
    for result in results:
        outcome = result.status if not result.detail else f"{result.status}: {result.detail}"
        outcome = outcome.replace("|", "\\|").replace("\n", " ")
        pr = f"[PR]({result.url})" if result.url else "-"
        lines.append(f"| {result.repo} | {outcome} | {len(result.files)} | {pr} |")
    lines += [
        "",
        "A PR left open is waiting on that addon's own checks; a red check keeps it open rather than landing.",
    ]
    return "\n".join(lines) + "\n"


def write_summary(markdown: str) -> None:
    print(markdown)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with Path(path).open("a", encoding="utf-8") as summary:
            summary.write(markdown)


def main() -> int:
    if not os.environ.get("GH_TOKEN"):
        print("::notice::CONSUMER_SYNC_TOKEN is not set; skipping the consumer sync.")
        return 0

    core_root = Path(__file__).resolve().parent.parent
    try:
        sha = git(core_root, "rev-parse", "HEAD").stdout.strip()
        run(["gh", "auth", "setup-git"])
        repos = consumer_repos(discover_tooling_repos())
    except SyncError as error:
        print(f"::error::{error}")
        return 1

    results = []
    with tempfile.TemporaryDirectory(prefix="forever-core-sync-") as directory:
        workspace = Path(directory)
        for repo in repos:
            result = sync_consumer(repo, core_root, workspace, sha)
            results.append(result)
            suffix = f" {result.url}" if result.url else ""
            if result.detail:
                suffix += f" ({result.detail})"
            print(f"{repo}: {result.status}{suffix}")

    write_summary(summary_markdown(sha, results))
    return int(any(result.status == "failed" for result in results))


if __name__ == "__main__":
    sys.exit(main())
