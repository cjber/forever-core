"""Open or update the per-consumer sync PR after a push to forever-core main or a release.

release.yml starts this sync itself once a release is published, so the pins below move to it straight away.

The consumers are the repositories in `check_core_shared.VENDORED`, plus every non-archived `cjber` repository that
vendors `tools/forever_tools/MANIFEST.json` or `tools/forever_sim/MANIFEST.json`. There is no second consumer list to
edit: the first comes from the vendoring map, the second from the repositories themselves.

For each consumer this clones `main`, runs the same three syncs a maintainer would (`tools/sync_consumers.py` for this
repository, then the consumer's own `forever_tools/sync.py update` and `forever_sim/sync.py update`, each preceded by a
copy of this checkout's own `sync.py` so the updater that runs is the one being installed), regenerates the consumer's
`Locales/phrases.txt` when it has `tools/phrases.py` and its README.md and docs/curseforge.md family block when it has
`tools/check_family.py`, and, if anything changed, creates the commit on a scratch branch through the GraphQL
`createCommitOnBranch` mutation from that `main` HEAD, then moves `forever-core-sync` to it in one ref update and opens
or refreshes the PR with squash auto-merge enabled. Building the commit on a scratch branch keeps `forever-core-sync`
away from a commit that equals `main`, which would make the PR empty and have GitHub close it. GitHub signs commits made
through the API, so the consumer's `required_signatures` ruleset accepts the sync. The consumer's own checks remain the
gate: a sync that breaks one stays open as a red PR and is named in the run summary.

The run also moves every consumer's ForeverCore pin, `tools/forever-core.txt`, to core's latest published release, so
the addon's specs and CI test against the core a player runs. The pin change rides in the same commit and PR, which
says what moved. A pin that is newer, equal or not a `vX.Y.Z` tag is left alone, and a run that cannot read the latest
release leaves every pin alone rather than failing the tooling sync.

The pin is the whole bundle, because every consumer's release zip carries ForeverCore in one folder and the addons share
it: every run points the `.pkgmeta` ForeverCore external at the pin and sets the root TOC's `## X-Forever-Core:` line
(adding it after `## Dependencies:` when absent), so a consumer that pins v1.5.0 while its zip still downloads v1.4.1 is
repaired even when the pin does not move. When the tag the external downloads changes, whether the pin moved or a
lagging bundle was repaired, the run also gives the consumer a release entry in `CHANGELOG.md` so the core reaches
players. A consumer whose `.pkgmeta` ships no ForeverCore external (kiln-forever has none) bundles no core, so its pin
and TOC field move with no entry. The entry goes above the newest released version, keeps any notes under
`## [Unreleased]` above it, raises that newest patch by one and carries the `<!-- forever-core-sync -->` marker;
`tools/release_consumers.py` releases every consumer whose newest entry carries it. A consumer whose newest entry
already carries the marker gets no second entry, and one with no `CHANGELOG.md`, no release entry or no
`## [Unreleased]` heading gets a notice and no entry.

    python3 tools/sync_consumer_prs.py

Set `GH_TOKEN` to the `CONSUMER_SYNC_TOKEN` secret, a fine-grained PAT with Contents, Pull requests, Workflows and
Actions write on the consumer repositories (Workflows because `.github/workflows/core-shared-drift.yml` is vendored,
Actions because `tools/release_consumers.py` dispatches each consumer's `release.yml`). The token must also reach the
private `kiln-forever` repository, which is in the vendoring map; without access its sync is reported as failed in the
run summary rather than silently leaving that consumer behind. Without a token at all the script prints a notice and
exits 0, so the workflow stays green until the owner adds the secret.
"""

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from check_consumers import (
    CORE_EXTERNAL,
    EXTERNAL_TAG,
    TOC_CORE_FIELD,
    core_external,
    pkgmeta_field,
)
from check_core_shared import VENDORED, consumer_path

OWNER = "cjber"
CORE_REPO = "forever-core"
BRANCH = "forever-core-sync"
SCRATCH_BRANCH = f"{BRANCH}-commit"
TITLE = "chore: sync shared files from forever-core"
# The release each consumer's specs and CI check ForeverCore out at: one line, a tag such as `v1.3.2`.
PIN_PATH = "tools/forever-core.txt"
# The only pin form this can compare and move; anything else is a maintainer's decision, not a bump.
RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
# The consumer-side bundle a moved pin rewrites: the shipped core's `.pkgmeta` external, the TOC field naming it, and
# the changelog release entry that `tools/release_consumers.py` finds by this marker.
PKGMETA = ".pkgmeta"
TOC_DEPENDENCIES = re.compile(r"^##[ \t]*Dependencies[ \t]*:[^\r\n]*", re.IGNORECASE | re.MULTILINE)
CHANGELOG = "CHANGELOG.md"
UNRELEASED = re.compile(r"^## \[Unreleased\][ \t]*$", re.MULTILINE)
RELEASED = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+)\]", re.MULTILINE)
SYNC_MARKER = "<!-- forever-core-sync -->"
SYNC_BULLET = "- Ships with the same shared code as your other Forever addons, so they keep working together."
TOOLING_MANIFESTS = ("tools/forever_tools/MANIFEST.json", "tools/forever_sim/MANIFEST.json")
# Where this checkout keeps each tooling package's producer, the PRODUCER_PATH both sync.py files carry.
TOOLING_PRODUCER_ROOT = ".agents/skills/wow-forever-addon/tooling"
PER_PAGE = 100
REPOSITORY_PAGES = 2
AUTO_MERGE_QUERY = """
mutation($pullRequestId: ID!) {
  enablePullRequestAutoMerge(input: {pullRequestId: $pullRequestId, mergeMethod: SQUASH}) {
    pullRequest { number }
  }
}
"""


class SyncError(RuntimeError):
    """A git, gh or sync command failed."""


@dataclass
class Result:
    repo: str
    status: str
    files: tuple[str, ...] = ()
    url: str | None = None
    detail: str | None = None


def run(
    command: list[str], cwd: Path | None = None, check: bool = True, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False, env=env)
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise SyncError(f"{' '.join(command)} failed: {detail}")
    return result


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", *args], cwd=root, check=check)


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["gh", *args], check=check)


def api(path: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return gh("api", path, *args, check=check)


def api_json(path: str, *args: str):
    return json.loads(api(path, *args).stdout)


def list_repositories() -> list[dict]:
    """The owner's repositories over REST, two pages like the old `gh repo list --limit 200`."""
    repositories = []
    for page in range(1, REPOSITORY_PAGES + 1):
        batch = api_json(f"users/{OWNER}/repos?per_page={PER_PAGE}&page={page}")
        repositories.extend(batch)
        if len(batch) < PER_PAGE:
            break
    return repositories


def consumer_repos(discovered=()) -> list[str]:
    """VENDORED's repositories plus repositories found to vendor the tooling, never this repo."""
    vendored = {repo for repos in VENDORED.values() for repo in repos}
    return sorted((vendored | set(discovered)) - {CORE_REPO})


def latest_core_release() -> str | None:
    """Core's newest published release tag, read once for the whole run.

    A read that fails is a warning, not a failed run: the tooling sync still has work to do, and every pin simply
    stays where it is for this run.
    """
    try:
        return str(api_json(f"repos/{OWNER}/{CORE_REPO}/releases/latest")["tag_name"])
    except (SyncError, json.JSONDecodeError, OSError, KeyError, TypeError) as error:
        print(f"::warning::Could not read {OWNER}/{CORE_REPO}'s latest release ({error}); leaving every pin alone.")
        return None


def release_version(tag: str) -> tuple[int, int, int] | None:
    """A `vX.Y.Z` tag as numbers, so v1.10.0 is newer than v1.9.0, or None when the tag is not one."""
    match = RELEASE_TAG.match(tag.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def bump_pin(root: Path, latest: str | None, today: date | None = None) -> str | None:
    """Move the consumer's ForeverCore pin up to `latest`, returning the tag it moved from.

    `root` is a clone named after the consumer's repository, so a consumer whose addon lives below its root
    (kiln-forever) gets the pin at the path CONSUMER_ROOT names. A pin that is equal, newer, or not a `vX.Y.Z` tag is
    left exactly as it is: the pin never moves backwards, and a tag this cannot compare is a maintainer's call.

    Every run also points the bundle at the pin, moved or not: the `.pkgmeta` external and the root TOC's
    `## X-Forever-Core:` field name the release the pin ships, so a consumer that pins v1.5.0 while its zip still
    downloads v1.4.1 is repaired. A marked `CHANGELOG.md` entry is added only when the tag the external downloads
    changes, so a repair to an unchanged pin still gives the release that carries it a reason to ship.
    """
    path = root / consumer_path(root.name, PIN_PATH)
    if not path.is_file():
        return None
    current = path.read_text(encoding="utf-8").strip()
    current_version = release_version(current)
    if current_version is None:
        print(f"{root.name}: {consumer_path(root.name, PIN_PATH)} is not a vX.Y.Z tag ({current!r}); leaving it alone.")
        return None
    pinned = current
    bumped = None
    latest_version = release_version(latest) if latest else None
    if latest_version is not None and current_version < latest_version:
        pinned = latest
        bumped = current
        path.write_text(f"{latest}\n", encoding="utf-8")
    update_bundle(root, pinned, today, current)
    return bumped


def pkgmeta_path(root: Path) -> Path:
    """Where the consumer keeps its `.pkgmeta`, below its addon folder when that is not the repo root."""
    return root / consumer_path(root.name, PKGMETA)


def rewrite_core_external(root: Path, pin: str) -> bool:
    """Point the consumer's `.pkgmeta` ForeverCore external at `pin`, returning whether it changed.

    A consumer without a `.pkgmeta`, or one whose `externals:` does not ship ForeverCore, is left alone: the tooling
    sync does not decide that an addon bundles core.
    """
    path = pkgmeta_path(root)
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    if not CORE_EXTERNAL.search(text):
        return False
    updated = CORE_EXTERNAL.sub(lambda match: f"{match['indent']}ForeverCore: {core_external(pin)}", text, count=1)
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def root_toc_path(root: Path) -> Path | None:
    """The consumer's root TOC, named after `package-as` as the packager names it, or None when that is unknown."""
    path = pkgmeta_path(root)
    if not path.is_file():
        return None
    package = pkgmeta_field(path.read_text(encoding="utf-8"), "package-as")
    return root / consumer_path(root.name, f"{package}.toc") if package else None


def rewrite_toc_core_field(root: Path, pin: str) -> bool:
    """Set the root TOC's `## X-Forever-Core:` to `pin`, adding it after `## Dependencies:` when absent.

    The client reads the field at load, so a player's other Forever addon can name a sibling that bundles a different
    core. A TOC with no `## Dependencies:` line is left alone rather than guessed at.
    """
    path = root_toc_path(root)
    if path is None or not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    field = f"## X-Forever-Core: {pin}"
    if TOC_CORE_FIELD.search(text):
        updated = TOC_CORE_FIELD.sub(field, text, count=1)
    else:
        dependencies = TOC_DEPENDENCIES.search(text)
        if not dependencies:
            print(f"{root.name}: {path.name} has no `## Dependencies:` line; leaving out `## X-Forever-Core:`.")
            return False
        updated = f"{text[: dependencies.end()]}\n{field}{text[dependencies.end() :]}"
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def next_version(text: str) -> str | None:
    """The newest `## [X.Y.Z]` heading with its patch incremented, or None when the changelog has no release."""
    versions = [tuple(int(part) for part in match["version"].split(".")) for match in RELEASED.finditer(text)]
    if not versions:
        return None
    major, minor, patch = max(versions)
    return f"{major}.{minor}.{patch + 1}"


def newest_entry_body(text: str) -> str | None:
    """The newest `## [X.Y.Z]` entry's body, or None when the changelog has no release."""
    matches = list(RELEASED.finditer(text))
    if not matches:
        return None
    newest = max(matches, key=lambda match: tuple(int(part) for part in match["version"].split(".")))
    following = re.search(r"^## ", text[newest.end() :], re.MULTILINE)
    end = newest.end() + following.start() if following else len(text)
    return text[newest.end() : end]


def with_sync_entry(text: str, version: str, day: str) -> str | None:
    """`text` with a marked release entry for `version` at the top, the notes under `## [Unreleased]` kept above it."""
    unreleased = UNRELEASED.search(text)
    if not unreleased:
        return None
    after = text[unreleased.end() :]
    following = re.search(r"^## ", after, re.MULTILINE)
    end = following.start() if following else len(after)
    notes = after[:end].strip()
    rest = after[end:]
    entry = f"## [{version}] - {day}\n\n{SYNC_MARKER}\n\n{SYNC_BULLET}\n"
    head = f"{text[: unreleased.end()]}\n\n"
    body = f"{notes}\n\n" if notes else ""
    return f"{head}{body}{entry}\n{rest}".rstrip("\n") + "\n"


def add_changelog_entry(root: Path, today: date | None = None) -> bool:
    """Give a consumer whose bundled core changed a release entry the release workflow can find."""
    path = root / CHANGELOG
    if not path.is_file():
        print(f"{root.name}: no {CHANGELOG}; no release entry added for the core sync.")
        return False
    text = path.read_text(encoding="utf-8")
    if SYNC_MARKER in (newest_entry_body(text) or ""):
        print(f"{root.name}: {CHANGELOG} already has an unreleased ForeverCore sync entry; no second entry added.")
        return False
    version = next_version(text)
    if version is None:
        print(f"{root.name}: {CHANGELOG} has no `## [X.Y.Z]` release to raise; no release entry added.")
        return False
    day = (today or datetime.now(timezone.utc).date()).isoformat()
    updated = with_sync_entry(text, version, day)
    if updated is None:
        print(f"{root.name}: {CHANGELOG} has no `## [Unreleased]` heading; no release entry added.")
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def bundle_tag(root: Path) -> str | None:
    """The tag the consumer's `.pkgmeta` ForeverCore external downloads, or None when it ships none."""
    path = pkgmeta_path(root)
    if not path.is_file():
        return None
    match = CORE_EXTERNAL.search(path.read_text(encoding="utf-8"))
    tag = EXTERNAL_TAG.search(match.group(0)) if match else None
    return tag["tag"] if tag else None


def ships_core(root: Path) -> bool:
    """Whether the consumer's `.pkgmeta` ships ForeverCore as an external, so its release zip carries core."""
    path = pkgmeta_path(root)
    return path.is_file() and CORE_EXTERNAL.search(path.read_text(encoding="utf-8")) is not None


def update_bundle(root: Path, pin: str, today: date | None = None, previous_pin: str | None = None) -> None:
    """Point the bundle at `pin`, adding a release entry only when a consumer that ships core changes its tag.

    A consumer whose `.pkgmeta` has no ForeverCore external (kiln-forever has no `.pkgmeta` at all) bundles no core, so
    a pin that moves gives its own release nothing to carry: it still gets the pin and the TOC field, and no entry.
    """
    bundles = ships_core(root)
    before = bundle_tag(root) or previous_pin
    rewrite_core_external(root, pin)
    rewrite_toc_core_field(root, pin)
    after = bundle_tag(root) or pin
    if bundles and after != before:
        add_changelog_entry(root, today)


def repo_vendors_tooling(repo: str) -> bool:
    for path in TOOLING_MANIFESTS:
        if api(f"repos/{OWNER}/{repo}/contents/{path}", "--silent", check=False).returncode == 0:
            return True
    return False


def discover_tooling_repos() -> set[str]:
    """The live repositories that vendor the tooling, so a new consumer needs no edit here."""
    try:
        listed = list_repositories()
    except (SyncError, json.JSONDecodeError) as error:
        print(f"::warning::Could not list {OWNER}'s repositories ({error}); using VENDORED's consumers only.")
        return set()
    return {
        item["name"]
        for item in listed
        if not item.get("archived") and item["name"] != CORE_REPO and repo_vendors_tooling(item["name"])
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


def python_env(root: Path) -> dict[str, str]:
    """The environment for a consumer's own generator, with the checkout root importable as `tools`."""
    return {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(root), os.environ.get("PYTHONPATH")]))}


def regenerate_phrases(root: Path) -> None:
    """Refresh the consumer's phrase template from its own extractor.

    `Locales/phrases.txt` is `tools/phrases.py`'s output and the consumer's locale spec asserts that, so the shared
    files' new or changed `L[...]` phrases would leave the sync PR red without this. The template is written only
    when the checkout carries both the extractor and the template, as the addons that have translations do.
    """
    script = root / "tools" / "phrases.py"
    template = root / "Locales" / "phrases.txt"
    if not script.is_file() or not template.is_file():
        return
    # Run by path, so a script importing its siblings in tools/ finds them, and with the root importable, so one
    # importing `tools.forever_tools` as a package (tweaks-forever documents `python3 -m tools.phrases`) does too.
    generated = run([sys.executable, str(script)], cwd=root, env=python_env(root))
    template.write_text(generated.stdout, encoding="utf-8")


def regenerate_family(root: Path) -> None:
    """Rewrite the consumer's README.md and docs/curseforge.md family block from its own checker.

    The text between the family markers is `forever_tools.family`'s and the consumer's typecheck job asserts that, so a
    core change to the block would leave the sync PR red without this. `--fix` rewrites in place and leaves the
    markers where they are; a consumer without `tools/check_family.py` is left alone.
    """
    script = root / "tools" / "check_family.py"
    if not script.is_file():
        return
    run([sys.executable, str(script), "--fix"], cwd=root, env=python_env(root))


def copy_preserving_mode(source: Path, target: Path) -> None:
    """Copy a file and carry its mode across, as the tooling's own sync.py does, so an executable stays one."""
    shutil.copyfile(source, target)
    shutil.copymode(source, target)


def install_updater(root: Path, core_root: Path, package: str) -> None:
    """Put the producer's own `sync.py` in the consumer before running it.

    The updater that runs is the one being installed. A release that adds a vendored file (backdrops.txt in #339) would
    otherwise be checked by the consumer's older copy, whose DATA_FILES does not list it, so it hashes fewer files than
    the producer's manifest names and every sync fails with "the producer's MANIFEST.json is stale".
    """
    source = core_root / TOOLING_PRODUCER_ROOT / package / "sync.py"
    target = root / "tools" / package / "sync.py"
    if not source.is_file():
        raise SyncError(f"{source} is missing: this checkout has no producer for {package}")
    copy_preserving_mode(source, target)


def sync_checkout(root: Path, core_root: Path, latest: str | None = None) -> str | None:
    """Sync the tooling and move the ForeverCore pin, returning the tag a moved pin came from.

    The pin is bumped last, so a consumer whose sync fails keeps its pin where it was.
    """
    run([sys.executable, str(core_root / "tools/sync_consumers.py"), str(root.parent)])
    for package in tooling_packages(root):
        install_updater(root, core_root, package)
        run(
            [sys.executable, str(root / "tools" / package / "sync.py"), "update", "--source", str(core_root)],
            cwd=root,
        )
    regenerate_phrases(root)
    regenerate_family(root)
    return bump_pin(root, latest)


def staged_changes(root: Path) -> tuple[list[dict], list[dict]]:
    """The staged additions (path and base64 contents) and deletions, with a rename as delete plus add."""
    git(root, "add", "-A")
    additions = []
    deletions = []
    for line in git(root, "diff", "--cached", "--name-status").stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[1]
        if status.startswith(("R", "C")) and len(parts) >= 3:
            if status.startswith("R"):
                deletions.append({"path": path})
            path = parts[2]
        elif status.startswith("D"):
            deletions.append({"path": path})
            continue
        contents = base64.b64encode((root / path).read_bytes()).decode("ascii")
        additions.append({"path": path, "contents": contents})
    return additions, deletions


CREATE_COMMIT_MUTATION = """
mutation($input: CreateCommitOnBranchInput!) {
  createCommitOnBranch(input: $input) {
    commit { oid }
  }
}
"""


def create_commit_input(
    repo: str, branch: str, oid: str, sha: str, additions: list[dict], deletions: list[dict]
) -> dict:
    """The createCommitOnBranch input: the branch, the head it must still be at, the message and the file changes."""
    return {
        "branch": {"repositoryNameWithOwner": f"{OWNER}/{repo}", "branchName": branch},
        "expectedHeadOid": oid,
        "message": {"headline": TITLE, "body": f"Core commit: {sha}"},
        "fileChanges": {"additions": additions, "deletions": deletions},
    }


def branch_ref(repo: str, branch: str) -> str:
    return f"repos/{OWNER}/{repo}/git/refs/heads/{branch}"


def point_branch(repo: str, branch: str, oid: str) -> None:
    """Point `branch` at `oid`, force-moving an existing ref and creating it when it does not exist yet."""
    patched = api(branch_ref(repo, branch), "--method", "PATCH", "-f", f"sha={oid}", "-F", "force=true", check=False)
    if patched.returncode == 0:
        return
    api(
        f"repos/{OWNER}/{repo}/git/refs",
        "--method",
        "POST",
        "-f",
        f"ref=refs/heads/{branch}",
        "-f",
        f"sha={oid}",
    )


def delete_branch(repo: str, branch: str) -> None:
    api(branch_ref(repo, branch), "--method", "DELETE", check=False)


def created_oid(result: subprocess.CompletedProcess) -> str:
    """The commit `createCommitOnBranch` made, or a SyncError when the response carries none."""
    try:
        return json.loads(result.stdout)["data"]["createCommitOnBranch"]["commit"]["oid"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise SyncError(f"createCommitOnBranch returned no commit: {error}") from error


def create_commit(
    repo: str, branch: str, oid: str, sha: str, additions: list[dict], deletions: list[dict], workspace: Path
) -> str:
    """Create the sync commit through GraphQL, so GitHub signs it and required_signatures accepts it.

    The request goes in a file through `--input`: the base64 file contents can pass the kernel's 128 KiB limit on one
    command-line argument.
    """
    body = workspace / f"{repo}-commit.json"
    request = {
        "query": CREATE_COMMIT_MUTATION,
        "variables": {"input": create_commit_input(repo, branch, oid, sha, additions, deletions)},
    }
    body.write_text(json.dumps(request), encoding="utf-8")
    return created_oid(api("graphql", "--input", str(body)))


def pr_body(sha: str, files: tuple[str, ...], pin_bump: tuple[str, str] | None = None) -> str:
    lines = ["Syncs this addon's copy of Forever Core's development tooling.", ""]
    if pin_bump:
        lines += [
            f"Moves the ForeverCore pin from {pin_bump[0]} to {pin_bump[1]}, so this addon's CI runs against the"
            " latest release.",
            "",
            "The same commit points the bundled ForeverCore external and `## X-Forever-Core:` at that tag, and adds a"
            " marked CHANGELOG.md release entry for the release-consumers workflow to publish.",
            "",
        ]
    lines += [
        f"Core commit: https://github.com/{OWNER}/{CORE_REPO}/commit/{sha}",
        "",
        "Files:",
        *(f"- `{path}`" for path in files),
        "",
        "Opened by the sync-consumers workflow in cjber/forever-core. The addon's own checks are the gate.",
    ]
    return "\n".join(lines) + "\n"


def open_sync_prs(repo: str) -> list[dict]:
    return api_json(f"repos/{OWNER}/{repo}/pulls?head={OWNER}:{BRANCH}&state=open")


def close_stale_prs(repo: str, sha: str) -> list[int]:
    """Close the sync PR an earlier run left open once the consumer already matches core, and drop its branch."""
    closed = []
    for pull in open_sync_prs(repo):
        number = pull["number"]
        api(
            f"repos/{OWNER}/{repo}/issues/{number}/comments",
            "--method",
            "POST",
            "-f",
            f"body=main already matches forever-core {sha}; nothing left to sync.",
        )
        api(f"repos/{OWNER}/{repo}/pulls/{number}", "--method", "PATCH", "-f", "state=closed")
        closed.append(number)
    if closed:
        delete_branch(repo, BRANCH)
    return closed


def open_or_update_pr(repo: str, body: str) -> tuple[int, str, str, str | None]:
    listed = open_sync_prs(repo)
    if listed:
        pull = listed[0]
        number, url = pull["number"], pull["html_url"]
        api(
            f"repos/{OWNER}/{repo}/pulls/{number}",
            "--method",
            "PATCH",
            "-f",
            f"title={TITLE}",
            "-f",
            f"body={body}",
        )
        # Arm it again only when it is not armed: a first attempt that failed, or a merge disabled by hand.
        return number, url, "updated", None if pull.get("auto_merge") else pull.get("node_id")
    created = json.loads(
        api(
            f"repos/{OWNER}/{repo}/pulls",
            "--method",
            "POST",
            "-f",
            f"title={TITLE}",
            "-f",
            f"head={BRANCH}",
            "-f",
            "base=main",
            "-f",
            f"body={body}",
        ).stdout
    )
    return created["number"], created["html_url"], "opened", created.get("node_id")


def enable_auto_merge(node_id: str) -> None:
    """Auto-merge has no REST endpoint, so it is a GraphQL call too."""
    api("graphql", "-f", f"query={AUTO_MERGE_QUERY}", "-f", f"pullRequestId={node_id}")


def auto_merge_warning(node_id: str) -> str | None:
    """Arm auto-merge, or return the warning that the PR waits for a manual merge."""
    try:
        enable_auto_merge(node_id)
    except (SyncError, OSError) as error:
        return f"auto-merge not enabled; waiting for a manual merge ({error})"
    return None


def sync_consumer(repo: str, core_root: Path, workspace: Path, sha: str, latest: str | None = None) -> Result:
    """Sync one consumer; `latest` is core's newest release tag, whose pin bump rides in the same commit."""
    try:
        root = clone(repo, workspace)
        head = git(root, "rev-parse", "HEAD").stdout.strip()
        git(root, "checkout", "-B", BRANCH)
        bumped = sync_checkout(root, core_root, latest)
        additions, deletions = staged_changes(root)
        if not additions and not deletions:
            closed = close_stale_prs(repo, sha)
            return Result(repo, "up to date", detail=", ".join(f"closed #{n}" for n in closed) or None)
        point_branch(repo, SCRATCH_BRANCH, head)
        try:
            commit = create_commit(repo, SCRATCH_BRANCH, head, sha, additions, deletions, workspace)
            # Move the sync branch while the scratch ref still holds the commit, so it is never unreferenced.
            point_branch(repo, BRANCH, commit)
        finally:
            delete_branch(repo, SCRATCH_BRANCH)
        files = tuple(sorted([item["path"] for item in additions] + [item["path"] for item in deletions]))
        pin_bump = (bumped, latest) if bumped and latest else None
        number, url, status, node_id = open_or_update_pr(repo, pr_body(sha, files, pin_bump))
        warning = auto_merge_warning(node_id) if node_id else None
        return Result(repo, status, files, url, warning)
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
    # One read for the whole run: every consumer's pin moves to the same release, or none of them do.
    latest = latest_core_release()

    results = []
    with tempfile.TemporaryDirectory(prefix="forever-core-sync-") as directory:
        workspace = Path(directory)
        for repo in repos:
            result = sync_consumer(repo, core_root, workspace, sha, latest)
            results.append(result)
            suffix = f" {result.url}" if result.url else ""
            if result.detail:
                suffix += f" ({result.detail})"
            print(f"{repo}: {result.status}{suffix}")

    write_summary(summary_markdown(sha, results))
    return int(any(result.status == "failed" for result in results))


if __name__ == "__main__":
    sys.exit(main())
