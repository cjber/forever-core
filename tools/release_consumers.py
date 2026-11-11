"""Release every consumer whose newest CHANGELOG.md entry came from the ForeverCore sync.

Every consumer's release zip carries ForeverCore in the same `ForeverCore` folder, so all of the addons' latest releases
must ship the same core: a core release has to re-release every consumer. `tools/sync_consumer_prs.py` moves each
consumer's pin to the new core release, rewrites its bundle and adds a release entry to `CHANGELOG.md` carrying the
`<!-- forever-core-sync -->` marker. This script, run every 20 minutes by
`.github/workflows/release-consumers.yml`, reads each consumer's `main` and dispatches that consumer's own
`release.yml` for the marked entry once all of these hold:

- the newest `## [X.Y.Z]` entry carries the marker, so it is the sync's, not a hand-written release;
- the tag `vX.Y.Z` does not exist yet;
- no `release.yml` run is queued or in progress;
- no `release.yml` run for `main`'s head already finished with a failure, which the cron would otherwise dispatch
  again every 20 minutes forever;
- the `ci.yml` push run on `main`'s head concluded success, which is the release's own gate.

The consumers are discovered the same way `tools/sync_consumer_prs.py` discovers them, so a new addon needs no edit
here. The run dispatches only, never tags or writes, so it is idempotent and safe on a 20-minute schedule: a consumer
whose release is queued, running or published is reported as waiting, and one whose release already failed at main's
head is reported as failed and turns the job red, so the cron does not retry that failure every 20 minutes. `main`'s
head is read first and the changelog at that exact commit, then the same commit is dispatched, so a merge landing
mid-run cannot release notes it does not carry.

    python3 tools/release_consumers.py

Set `GH_TOKEN` to the `CONSUMER_SYNC_TOKEN` secret, a fine-grained PAT with Contents, Pull requests, Workflows and
Actions write on the consumer repositories (Actions write is what dispatches their `release.yml`). The token must also
reach the private `kiln-forever` repository. Without a token the script prints a notice and exits 0, so the workflow
stays green until the owner adds the secret.
"""

import json
import os
import re
import sys
from dataclasses import dataclass

from sync_consumer_prs import OWNER, SyncError, api_json, consumer_repos, discover_tooling_repos, gh

MARKER = "<!-- forever-core-sync -->"
CHANGELOG = "CHANGELOG.md"
RELEASE_WORKFLOW = "release.yml"
CI_WORKFLOW = "ci.yml"
HEADING = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+)\][^\r\n]*$", re.MULTILINE)


class DispatchForbidden(SyncError):
    """The token may not run the consumer's release workflow."""


@dataclass(frozen=True)
class Decision:
    """What one consumer's state says: release `version` at `commit`, wait and say why, or fail its `release.yml`."""

    version: str | None = None
    commit: str | None = None
    reason: str = ""
    failed: bool = False

    @property
    def release(self) -> bool:
        """Whether this consumer's release should be dispatched now."""
        return self.version is not None and self.commit is not None


def version_key(version: str) -> tuple[int, int, int]:
    """A `X.Y.Z` version as numbers, so 1.10.0 is newer than 1.9.0."""
    return tuple(int(part) for part in version.split("."))


def newest_entry(text: str) -> tuple[str, str] | None:
    """The newest `## [X.Y.Z]` entry's version and body, or None when the changelog has no release."""
    matches = list(HEADING.finditer(text))
    if not matches:
        return None
    newest = max(matches, key=lambda match: version_key(match["version"]))
    following = re.search(r"^## ", text[newest.end() :], re.MULTILINE)
    end = newest.end() + following.start() if following else len(text)
    return newest["version"], text[newest.end() : end]


def ci_state(runs: dict, sha: str) -> str:
    """Full CI's state for `sha` on main, as `completed/success`, a running status, or `none` with no run yet."""
    matching = [
        run for run in runs.get("workflow_runs", []) if run.get("head_branch") == "main" and run.get("head_sha") == sha
    ]
    if not matching:
        return "none"
    newest = max(matching, key=lambda run: run.get("run_started_at") or "")
    if newest.get("status") != "completed":
        return newest.get("status") or "unknown"
    return f"completed/{newest.get('conclusion') or 'unknown'}"


def has_pending_release(runs: dict) -> bool:
    """Whether a release run is queued or in progress, so a second dispatch would only duplicate it."""
    return any(run.get("status") != "completed" for run in runs.get("workflow_runs", []))


def has_failed_release(runs: dict, sha: str) -> bool:
    """Whether a `release.yml` run on `sha` already finished with a conclusion other than success.

    A 20-minute cron would otherwise dispatch the same failing release again and again, forever, so a failure at the
    head commit is the maintainer's to fix and dispatch by hand.
    """
    return any(
        run.get("head_sha") == sha and run.get("status") == "completed" and run.get("conclusion") != "success"
        for run in runs.get("workflow_runs", [])
    )


def decide(
    changelog: str | None,
    head: str | None,
    tag_exists: bool,
    release_pending: bool,
    ci_state: str,
    release_failed: bool = False,
) -> Decision:
    """The release decision for one consumer, from what main holds and what its workflows report.

    Pure, so the whole rule is unit-tested without the network: only a marked newest entry whose tag is missing,
    whose release is idle, whose head has no failed release run and whose full CI on main's head passed is dispatched.
    """
    if changelog is None:
        return Decision(reason="main has no CHANGELOG.md")
    entry = newest_entry(changelog)
    if entry is None:
        return Decision(reason="CHANGELOG.md has no release entry")
    version, body = entry
    if MARKER not in body:
        return Decision(reason=f"the newest entry, v{version}, is not a ForeverCore sync")
    if tag_exists:
        return Decision(reason=f"v{version} is already released")
    if release_pending:
        return Decision(reason=f"{RELEASE_WORKFLOW} is queued or running")
    if head is None:
        return Decision(reason="main has no head commit")
    if release_failed:
        return Decision(
            reason=f"{RELEASE_WORKFLOW} failed at {head[:7]}; fix it and dispatch by hand",
            failed=True,
        )
    if ci_state != "completed/success":
        return Decision(reason=f"{CI_WORKFLOW} on main's head {head[:7]} is {ci_state}")
    return Decision(version, head, f"releases v{version} at {head}")


def read_changelog(repo: str, ref: str) -> str | None:
    """CHANGELOG.md at `ref` as text, or None when the repository has none there."""
    result = gh(
        "api",
        f"repos/{OWNER}/{repo}/contents/{CHANGELOG}?ref={ref}",
        "-H",
        "Accept: application/vnd.github.raw",
        check=False,
    )
    if result.returncode == 0:
        return result.stdout
    detail = (result.stderr or result.stdout).strip()
    if "404" in detail or "Not Found" in detail:
        return None
    raise SyncError(f"could not read {repo}'s {CHANGELOG}: {detail}")


def tag_exists(repo: str, tag: str) -> bool:
    """Whether the consumer already has `tag`; an API failure other than 404 is a SyncError."""
    result = gh("api", f"repos/{OWNER}/{repo}/git/ref/tags/{tag}", "--silent", check=False)
    if result.returncode == 0:
        return True
    detail = (result.stderr or result.stdout).strip()
    if "404" in detail or "Not Found" in detail:
        return False
    raise SyncError(f"could not check {tag} in {repo}: {detail}")


def release_runs(repo: str) -> dict:
    """The consumer's recent `release.yml` runs, newest first."""
    return api_json(f"repos/{OWNER}/{repo}/actions/workflows/{RELEASE_WORKFLOW}/runs?per_page=20")


def main_head(repo: str) -> str:
    """The full SHA of the consumer's `main` head."""
    return str(api_json(f"repos/{OWNER}/{repo}/commits/main")["sha"])


def ci_runs(repo: str, sha: str) -> dict:
    """The `ci.yml` push runs for `sha`, which `release.yml` checks before it publishes."""
    return api_json(f"repos/{OWNER}/{repo}/actions/workflows/{CI_WORKFLOW}/runs?head_sha={sha}&event=push&per_page=100")


def plan(repo: str) -> Decision:
    """Read one consumer's state and decide whether to release it now, with as few API reads as the rule allows.

    `main`'s head is read first and the changelog at that exact commit, so a merge that lands between two reads can
    never dispatch a release for an intent the commit does not carry. The commit CI is checked on is the same one.
    """
    head = main_head(repo)
    changelog = read_changelog(repo, head)
    entry = newest_entry(changelog) if changelog else None
    if entry is None or MARKER not in entry[1]:
        return decide(changelog, None, False, False, "none")
    version = entry[0]
    if tag_exists(repo, f"v{version}"):
        return decide(changelog, None, True, False, "none")
    runs = release_runs(repo)
    if has_pending_release(runs):
        return decide(changelog, None, False, True, "none")
    if has_failed_release(runs, head):
        return decide(changelog, head, False, False, "none", release_failed=True)
    return decide(changelog, head, False, False, ci_state(ci_runs(repo, head), head))


def dispatch(repo: str, version: str, commit: str) -> None:
    """Start the consumer's own release workflow for the marked entry, at the commit full CI passed."""
    try:
        gh(
            "workflow",
            "run",
            RELEASE_WORKFLOW,
            "-R",
            f"{OWNER}/{repo}",
            "--ref",
            "main",
            "-f",
            f"version={version}",
            "-f",
            f"commit={commit}",
        )
    except SyncError as error:
        if "403" in str(error):
            raise DispatchForbidden(str(error)) from error
        raise


def main() -> int:
    """Release every consumer that is ready, print one line per consumer, and fail on an error or a failed release."""
    if not os.environ.get("GH_TOKEN"):
        print("::notice::CONSUMER_SYNC_TOKEN is not set; skipping the consumer release check.")
        return 0

    try:
        repos = consumer_repos(discover_tooling_repos())
    except SyncError as error:
        print(f"::error::{error}")
        return 1

    failed = 0
    forbidden = 0
    for repo in repos:
        try:
            decision = plan(repo)
            if decision.failed:
                failed += 1
                print(f"{repo}: failed: {decision.reason}")
                continue
            if not decision.release:
                print(f"{repo}: waiting: {decision.reason}")
                continue
            dispatch(repo, decision.version, decision.commit)
        except DispatchForbidden:
            forbidden += 1
            print(f"::error::CONSUMER_SYNC_TOKEN lacks Actions: Read and write on {OWNER}/{repo}")
            continue
        except (SyncError, json.JSONDecodeError, OSError, KeyError, TypeError) as error:
            failed += 1
            print(f"{repo}: failed: {error}")
            continue
        print(f"{repo}: dispatched {RELEASE_WORKFLOW} for v{decision.version} at {decision.commit}")
    return int(failed > 0 or forbidden > 0)


if __name__ == "__main__":
    sys.exit(main())
