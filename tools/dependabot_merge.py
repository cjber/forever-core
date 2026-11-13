#!/usr/bin/env python3
"""Arm auto-merge for every Dependabot pull request whose updates are all patch or minor.

    python3 tools/dependabot_merge.py            # arm auto-merge, and label a major for review
    python3 tools/dependabot_merge.py --dry-run  # print what would happen and change nothing
    python3 tools/dependabot_merge.py --repo tweaks-forever  # one repository, for a check by hand

This runs in one central job for forever-core and every consumer, not in a workflow inside each repository, for two
reasons. A merge enabled with `GITHUB_TOKEN` creates no push run on main, because GitHub does not trigger workflows from
`GITHUB_TOKEN` events, and `tools/release_check.py` publishes only a commit with a green CI push run, so such a merge
would leave the next release blocked; this job uses `CONSUMER_SYNC_TOKEN`, a fine-grained PAT, exactly as the consumer
sync does. A run triggered by Dependabot itself also cannot read Actions secrets, so the merge cannot be decided there.

For each repository it lists the open pull requests Dependabot opened, over REST, and reads each head commit's message.
Dependabot's trailers name every dependency in the pull request with its `update-type`, so a grouped update is judged
as a whole: auto-merge (squash) is armed only when every dependency is `version-update:semver-patch` or
`version-update:semver-minor`. One `major` anywhere leaves the pull request for review, labelled `major`. A message
without an `update-type` trailer, or with one this script does not know, is also left for review. Anything left for
review has auto-merge taken back, so a pull request that was armed as a patch and later force-pushed to a major cannot
land on the earlier decision.

The consumer list is `tools/check_core_shared.py`'s `VENDORED` map plus the live repositories found to vendor the
tooling, through `tools/sync_consumer_prs.py`, so a new addon needs no edit here.
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field

from sync_consumer_prs import CORE_REPO, OWNER, consumer_repos, discover_tooling_repos

PER_PAGE = 100
BOT = "dependabot[bot]"
LABEL = "major"
LABEL_COLOR = "d73a4a"
LABEL_DESCRIPTION = "A major dependency update that waits for review"
KNOWN_TYPES = {"patch", "minor", "major"}


class GhError(RuntimeError):
    """A `gh` command failed."""


@dataclass
class Dependency:
    """One entry of a Dependabot pull request's `updated-dependencies` trailer."""

    name: str
    update: str = "unknown"


@dataclass
class Decision:
    """What to do with one pull request, and why."""

    action: str
    dependencies: list[Dependency] = field(default_factory=list)
    reason: str = ""


def dependencies(message: str) -> list[Dependency]:
    """Every dependency Dependabot's commit trailers name, with its update type when it records one."""
    found: list[Dependency] = []
    current = None
    for line in message.splitlines():
        stripped = line.strip()
        if stripped.startswith("- dependency-name:"):
            name = stripped.split(":", 1)[1].strip().strip("'\"")
            current = Dependency(name)
            found.append(current)
        elif current is not None and stripped.startswith("update-type:"):
            update = stripped.split(":", 1)[1].strip()
            current.update = update.removeprefix("version-update:semver-")
    return found


def decide(message: str) -> Decision:
    """Auto-merge when every dependency is patch or minor, label a major, and leave anything else for review."""
    found = dependencies(message)
    if not found:
        return Decision("review", found, "no update-type trailer")
    if any(dependency.update == "major" for dependency in found):
        return Decision("major", found, "a major update")
    unknown = [dependency for dependency in found if dependency.update not in KNOWN_TYPES]
    if unknown:
        names = ", ".join(dependency.name for dependency in unknown)
        return Decision("review", found, f"an update type this job does not know ({names})")
    return Decision("merge", found, "every update is patch or minor")


class Gh:
    """The reads and writes this job makes, through the authenticated `gh`."""

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)
        if check and result.returncode:
            raise GhError(f"gh {' '.join(args[:2])} failed: {(result.stderr or result.stdout).strip()}")
        return result

    def api(self, path: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return self.run("api", path, *args, check=check)

    def json(self, path: str):
        return json.loads(self.api(path).stdout)

    def enable_auto_merge(self, repo: str, number: int) -> None:
        self.run("pr", "merge", "--auto", "--squash", "--repo", f"{OWNER}/{repo}", str(number))

    def disable_auto_merge(self, repo: str, number: int) -> None:
        """Take back an armed auto-merge, so a later major update cannot land on the old decision."""
        self.run("pr", "merge", "--disable-auto", "--repo", f"{OWNER}/{repo}", str(number), check=False)

    def label(self, repo: str, number: int, name: str) -> None:
        self.api(
            f"repos/{OWNER}/{repo}/labels",
            "--method",
            "POST",
            "-f",
            f"name={name}",
            "-f",
            f"color={LABEL_COLOR}",
            "-f",
            f"description={LABEL_DESCRIPTION}",
            check=False,
        )
        self.api(f"repos/{OWNER}/{repo}/issues/{number}/labels", "--method", "POST", "-f", f"labels[]={name}")


def open_prs(gh: Gh, repo: str) -> list[dict]:
    """Every open pull request in `repo`, over REST, one page at a time."""
    pulls = []
    page = 1
    while True:
        batch = gh.json(f"repos/{OWNER}/{repo}/pulls?state=open&per_page={PER_PAGE}&page={page}")
        pulls.extend(batch)
        if len(batch) < PER_PAGE:
            return pulls
        page += 1


def head_message(gh: Gh, repo: str, pull: dict) -> str:
    """The head commit's full message, which carries Dependabot's trailers."""
    sha = pull["head"]["sha"]
    return gh.json(f"repos/{OWNER}/{repo}/commits/{sha}")["commit"]["message"]


def handle(gh: Gh, repo: str, pull: dict, dry_run: bool) -> str:
    """Apply the decision to one pull request, returning the line to print."""
    number = pull["number"]
    decision = decide(head_message(gh, repo, pull))
    label = f"{OWNER}/{repo}#{number}"
    if decision.action == "merge":
        if not dry_run:
            gh.enable_auto_merge(repo, number)
        return f"{label}: {len(decision.dependencies)} update(s), {decision.reason} -> auto-merge"
    if not dry_run:
        # A pull request that was armed for a patch or minor and then moved to a major must not land on that decision.
        gh.disable_auto_merge(repo, number)
    if decision.action == "major":
        if not dry_run:
            gh.label(repo, number, LABEL)
        return f"{label}: {decision.reason} -> left for review, labelled {LABEL}"
    return f"{label}: {decision.reason} -> left for review"


def main(argv: list[str] | None = None, gh: Gh | None = None, repos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print what would happen and change nothing")
    parser.add_argument("--repo", action="append", help="one repository to check, instead of all of them")
    arguments = parser.parse_args(argv)

    if gh is None and not os.environ.get("GH_TOKEN"):
        print("::notice::CONSUMER_SYNC_TOKEN is not set; skipping Dependabot auto-merge.")
        return 0
    gh = gh or Gh()
    if repos is None:
        repos = arguments.repo or [CORE_REPO, *consumer_repos(discover_tooling_repos())]

    failures = 0
    for repo in repos:
        try:
            pulls = [pull for pull in open_prs(gh, repo) if pull.get("user", {}).get("login") == BOT]
        except (GhError, json.JSONDecodeError, KeyError, TypeError) as error:
            print(f"::error::{repo}: could not list Dependabot pull requests ({error})")
            failures += 1
            continue
        for pull in pulls:
            try:
                print(f"{repo}: {handle(gh, repo, pull, arguments.dry_run)}")
            except (GhError, json.JSONDecodeError, KeyError, TypeError) as error:
                print(f"::error::{repo}#{pull.get('number')}: {error}")
                failures += 1
    if failures:
        print(f"{failures} pull request(s) or repository/repositories could not be handled.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
