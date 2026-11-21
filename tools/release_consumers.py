"""Release every consumer whose newest CHANGELOG.md entry came from the ForeverCore sync.

Every consumer's release zip carries its own copy of the pinned ForeverCore, so all of the addons' latest releases must
ship the same core: a core release has to re-release every consumer. `tools/sync_consumer_prs.py` moves each
consumer's pin to the new core release, rewrites its bundle and, when its latest released tag bundles a different core
than that pin and has no pending fragments, adds a release entry to `CHANGELOG.md` carrying the
`<!-- forever-core-sync -->` marker above a marked entry whose own tag is already released. This script, run every 20
minutes by `.github/workflows/release-consumers.yml`, reads each consumer's `main` and dispatches that consumer's own
`release.yml` for the marked entry once all of these hold:

- the newest `## [X.Y.Z]` entry carries the marker, so it is the sync's, not a hand-written release;
- no pending fragments sit in `changes/`: notes merged after the sync PR opened are that addon's
  own release notes, and this release would ship them under a maintenance line;
- the tag `vX.Y.Z` does not exist yet;
- no `release.yml` run is queued or in progress;
- no `release.yml` run for `main`'s head already finished with a failure, which the cron would otherwise dispatch
  again every 20 minutes forever;
- the `ci.yml` push run on `main`'s head concluded success, which is the release's own gate;
- the commit's build was loaded in the client: its newest `headless-smoke` commit status is `success`, or its committed
  `.visual-proof.json` verifies against its files with passing in-game checks, the same evidence `release.yml`'s
  `release_check` accepts. Either one records that the headless client loaded that build, ran `/forever selftest` and
  found no Lua errors in the addon's folders. A commit with neither is reported as waiting and retried by the next
  run, never as failed, so a release waits for the smoke instead of turning the job red.

A consumer whose root TOC opts in to the embedded core (`## X-Forever-Core-Embed: 1`) at the commit it would release
also waits until every addon in `EMBED_FLEET` has opted in on its own `main`, and the wait names the ones that have not.
Until then another addon's zip still ships the shared top-level `ForeverCore` folder. Once all have opted in, the embed
releases still go out as one batch: none is dispatched until every fleet addon is either ready to release in this run
or already has an embedded release published, so no addon ships its embed build alone while another waits on CI
(docs/dependency-transition.md, "Packaging"). Each consumer's own `release.yml` runs `forever_tools.fleet` too, so a
hand-run release or a pushed tag holds the same way.

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
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Run as a script, nothing has put the addon skill pack's tooling on the path yet.
TOOLING = Path(__file__).resolve().parent.parent / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))

from forever_tools import fleet, release_check, visual_proof  # noqa: E402
from sync_consumer_prs import (  # noqa: E402
    OWNER,
    SyncError,
    api_json,
    consumer_repos,
    discover_tooling_repos,
    gh,
    unreleased_notes,
)

MARKER = "<!-- forever-core-sync -->"
CHANGELOG = "CHANGELOG.md"
RELEASE_WORKFLOW = "release.yml"
CI_WORKFLOW = "ci.yml"
# The commit status `forever_client.py smoke` posts, which `tools/smoke_queue.py` fills in ahead of a release.
SMOKE_CONTEXT = "headless-smoke"
# The published addons that embed ForeverCore under Libs/ForeverCore (`forever_tools.fleet`, which each consumer's own
# release also runs). While any of them still ships the shared top-level ForeverCore folder, removing or downgrading
# that addon rolls core back under the others (cjber/forever-core#448).
EMBED_FLEET = fleet.EMBED_FLEET
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
    """Whether the newest finished `release.yml` run on `sha` ended in anything but success.

    A 20-minute cron would otherwise dispatch the same failing release again and again, forever, so a failure at the
    head commit is the maintainer's to fix and dispatch by hand. Only the newest finished run counts, so a failure
    rerun to success clears. A release tags its commit before the packager uploads, so this is read before the tag:
    a tag left by a failed upload is not a published release.
    """
    finished = [
        run for run in runs.get("workflow_runs", []) if run.get("head_sha") == sha and run.get("status") == "completed"
    ]
    if not finished:
        return False
    newest = max(finished, key=lambda run: run.get("run_started_at") or "")
    return newest.get("conclusion") != "success"


def decide(
    changelog: str | None,
    head: str | None,
    tag_exists: bool,
    release_pending: bool,
    ci_state: str,
    release_failed: bool = False,
    smoke: str = "success",
    changes_pending: bool = False,
) -> Decision:
    """The release decision for one consumer, from what main holds and what its workflows report.

    Pure, so the whole rule is unit-tested without the network: only a marked newest entry with no notes under
    `## [Unreleased]`, whose tag is missing, whose release is idle, whose head has no failed release run, whose full
    CI on main's head passed and whose head carries a green `headless-smoke` status or a verified visual proof
    (`smoke="proof"`) is dispatched. A missing smoke is a reason to wait for `tools/smoke_queue.py` and try again,
    never a failure.
    """
    if changelog is None:
        return Decision(reason="main has no CHANGELOG.md")
    entry = newest_entry(changelog)
    if entry is None:
        return Decision(reason="CHANGELOG.md has no release entry")
    version, body = entry
    if MARKER not in body:
        return Decision(reason=f"the newest entry, v{version}, is not a ForeverCore sync")
    if (unreleased_notes(changelog) or "").strip():
        # The addon's own next release carries those notes; this one would publish them under a maintenance line.
        return Decision(reason=f"unreleased notes sit above v{version}; its own release ships them")
    if changes_pending:
        return Decision(reason=f"change notes in changes/ sit above v{version}; its own release ships them")
    if release_pending:
        return Decision(reason=f"{RELEASE_WORKFLOW} is queued or running")
    if release_failed and head is not None:
        # Before the tag: a release tags its commit before it uploads, so a failed upload leaves a tag behind.
        return Decision(
            reason=f"{RELEASE_WORKFLOW} failed at {head[:7]}; fix it and dispatch by hand",
            failed=True,
        )
    if tag_exists:
        return Decision(reason=f"v{version} is already released")
    if head is None:
        return Decision(reason="main has no head commit")
    if ci_state != "completed/success":
        return Decision(reason=f"{CI_WORKFLOW} on main's head {head[:7]} is {ci_state}")
    if smoke not in ("success", "proof"):
        return Decision(reason=f"waiting for {SMOKE_CONTEXT} on {head[:7]}, which is {smoke}")
    return Decision(version, head, f"releases v{version} at {head}")


def read_file(repo: str, path: str, ref: str) -> str | None:
    """`path` at `ref` as text, or None when the repository has no such file there."""
    result = gh(
        "api",
        f"repos/{OWNER}/{repo}/contents/{path}?ref={ref}",
        "-H",
        "Accept: application/vnd.github.raw",
        check=False,
    )
    if result.returncode == 0:
        return result.stdout
    detail = (result.stderr or result.stdout).strip()
    if "404" in detail or "Not Found" in detail:
        return None
    raise SyncError(f"could not read {repo}'s {path}: {detail}")


def read_changelog(repo: str, ref: str) -> str | None:
    """CHANGELOG.md at `ref` as text, or None when the repository has none there."""
    return read_file(repo, CHANGELOG, ref)


def embeds_at(repo: str, ref: str) -> bool:
    """Whether the consumer's root TOC at `ref` opts in to the embedded core (`forever_tools.fleet.opted_in`).

    The root TOC is the one the packager names, as every other reader resolves it. A policy or TOC that cannot be read
    is a SyncError, never a pass, so the gate fails closed.
    """

    def list_tocs():
        listing = api_json(f"repos/{OWNER}/{repo}/contents?ref={ref}")
        return [entry["name"] for entry in listing if entry.get("name", "").endswith(".toc")]

    try:
        return fleet.opted_in(lambda path: read_file(repo, path, ref), list_tocs)
    except fleet.FleetUnreadable as error:
        raise SyncError(f"{repo} at {ref[:7]}: {error}") from None


def latest_release_embeds(repo: str) -> bool:
    """Whether the consumer's latest published release already embeds core, so the batch does not wait for it."""
    result = gh("api", f"repos/{OWNER}/{repo}/releases/latest", "--jq", ".tag_name", check=False)
    tag = result.stdout.strip() if result.returncode == 0 else ""
    return bool(tag) and embeds_at(repo, tag)


def embed_hold(opted: dict[str, bool]) -> str | None:
    """Why an opted-in consumer's release waits, naming every `EMBED_FLEET` addon not opted in yet, or None."""
    missing = sorted(repo for repo in EMBED_FLEET if not opted.get(repo))
    if not missing:
        return None
    return "its embedded ForeverCore release waits until every Forever addon opts in; not yet: " + ", ".join(missing)


def has_change_fragments(repo: str, ref: str) -> bool:
    """Whether `changes/` at `ref` contains markdown fragments."""
    result = gh("api", f"repos/{OWNER}/{repo}/contents/changes?ref={ref}", check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if "404" in detail or "Not Found" in detail:
            return False
        raise SyncError(f"could not read {repo}'s changes/: {detail}")
    try:
        entries = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SyncError(f"could not read {repo}'s changes/: invalid response") from error
    return any(
        isinstance(entry, dict) and entry.get("type") == "file" and str(entry.get("name", "")).endswith(".md")
        for entry in entries
    )


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


def smoke_status(repo: str, sha: str) -> str:
    """The state of the newest `headless-smoke` status on `sha`, or `missing` before any smoke has posted one.

    `tools/smoke_queue.py` reads the same status to choose what to smoke, and a release waits for it rather than
    failing, so a commit that has not been in the client yet is simply not released this run.
    """
    statuses = api_json(f"repos/{OWNER}/{repo}/commits/{sha}/statuses")
    for status in statuses:
        if status.get("context") == SMOKE_CONTEXT:
            return str(status.get("state") or "unknown")
    return "missing"


# The vendored modules `release_check` runs to judge a proof: itself and everything it imports from `forever_tools`.
PROOF_GATE = ("release_check.py", "visual_proof.py", "pkgmeta.py", "toc.py")


def proof_covers(repo: str, sha: str) -> bool:
    """Whether `sha`'s committed `.visual-proof.json` stands in for its headless smoke, as `release_check` decides.

    The proof is bound to the commit's file contents, so the check runs over the commit's own tree: its tarball,
    extracted outside any git work tree, where the packager has no untracked paths to leave out. Core's gate judges
    the proof, so it covers the commit only when the consumer vendors that same gate: a consumer whose release check
    still predates proofs, or differs in any other way, would refuse the dispatched release, so it waits for its smoke.
    """
    if read_file(repo, visual_proof.PROOF.as_posix(), sha) is None:
        return False
    result = subprocess.run(["gh", "api", f"repos/{OWNER}/{repo}/tarball/{sha}"], capture_output=True, check=False)
    if result.returncode:
        raise SyncError(f"could not download {repo} at {sha[:7]}: {result.stderr.decode(errors='replace').strip()}")
    with tempfile.TemporaryDirectory(prefix="forever-proof-") as scratch:
        archive = Path(scratch) / "tree.tar.gz"
        archive.write_bytes(result.stdout)
        tree = Path(scratch) / "tree"
        with tarfile.open(archive) as bundle:
            bundle.extractall(tree, filter="data")
        (top,) = tree.iterdir()
        vendored = top / "tools/forever_tools"
        if any(
            not (vendored / name).is_file()
            or (vendored / name).read_bytes() != (TOOLING / "forever_tools" / name).read_bytes()
            for name in PROOF_GATE
        ):
            return False
        return release_check.proof_refusal(top) is None


def build_evidence(repo: str, sha: str) -> str:
    """`success` when `sha` has a green headless smoke, `proof` when its visual proof covers it, else the smoke state.

    `release_check` accepts either one, and `tools/smoke_queue.py` reads the same answer to skip a commit whose proof
    already loaded it in the client.
    """
    state = smoke_status(repo, sha)
    if state != "success" and proof_covers(repo, sha):
        return "proof"
    return state


def plan(repo: str) -> Decision:
    """Read one consumer's state and decide whether to release it now, with as few API reads as the rule allows.

    `main`'s head is read first and the changelog at that exact commit, so a merge that lands between two reads can
    never dispatch a release for an intent the commit does not carry. CI and the build evidence are both read for that
    same commit, and the evidence only once CI is green, which is the only path to a dispatch.
    """
    head = main_head(repo)
    changelog = read_changelog(repo, head)
    entry = newest_entry(changelog) if changelog else None
    if entry is None or MARKER not in entry[1]:
        return decide(changelog, None, False, False, "none")
    if has_change_fragments(repo, head):
        return decide(changelog, None, False, False, "none", changes_pending=True)
    version = entry[0]
    runs = release_runs(repo)
    if has_pending_release(runs):
        return decide(changelog, None, False, True, "none")
    if has_failed_release(runs, head):
        return decide(changelog, head, False, False, "none", release_failed=True)
    if tag_exists(repo, f"v{version}"):
        return decide(changelog, None, True, False, "none")
    state = ci_state(ci_runs(repo, head), head)
    smoke = build_evidence(repo, head) if state == "completed/success" else "missing"
    return decide(changelog, head, False, False, state, smoke=smoke)


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
    opted: dict[str, bool] | None = None
    batch: str | None = None
    plans: dict[str, Decision] = {}

    def plan_of(name: str) -> Decision:
        if name not in plans:
            plans[name] = plan(name)
        return plans[name]

    for repo in repos:
        try:
            decision = plan_of(repo)
            if decision.failed:
                failed += 1
                print(f"{repo}: failed: {decision.reason}")
                continue
            if not decision.release:
                print(f"{repo}: waiting: {decision.reason}")
                continue
            if embeds_at(repo, decision.commit):
                # Read once per run, and only when an opted-in release is otherwise ready; this addon counts as the
                # commit it would release.
                if opted is None:
                    opted = {name: embeds_at(name, main_head(name)) for name in EMBED_FLEET}
                hold = embed_hold({**opted, repo: True})
                if not hold:
                    # Every addon has opted in: the batch goes only when every other one is ready now or already
                    # shipped its embedded release.
                    if batch is None:
                        waiting = [
                            name
                            for name in EMBED_FLEET
                            if name != repo and not plan_of(name).release and not latest_release_embeds(name)
                        ]
                        batch = (
                            "the embedded ForeverCore releases go out together; not ready yet: " + ", ".join(waiting)
                            if waiting
                            else ""
                        )
                    hold = batch or None
                if hold:
                    print(f"{repo}: waiting: {hold}")
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
