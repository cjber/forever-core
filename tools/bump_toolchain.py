#!/usr/bin/env python3
"""Bump every pin in toolchain.json from the upstream each entry records.

    python3 tools/bump_toolchain.py --dry-run   # print what would move, write nothing
    python3 tools/bump_toolchain.py             # rewrite toolchain.json
    python3 tools/bump_toolchain.py --publish   # commit every staged change and open or update the bump PR

An entry's `upstream.kind` says how to find a newer version, so a new tool needs a manifest entry and no code here:

- `github-release`: the newest non-prerelease release of a GitHub repository, read through `gh api`;
- `github-tag`: the newest tag, read through `gh api`, with the commit it points at;
- `github-branch`: the head commit of a branch, for a pin that tracks one;
- `npm`: the `latest` dist-tag of an npm package.

`upstream.strip` keeps only the major or the major.minor part of a tag (`node` is pinned to its major release line),
`upstream.series` restricts the versions a pin tracks (`lua51` is the 5.1 line, because the game client is Lua 5.1),
and `upstream.tag` is the tag
template an entry is named with (`v{version}`, or `{version}` for a repository whose tags carry no prefix), so a
tag of another shape is not a version of that tool. A release younger than `--cooldown`
days is skipped, so a broken release has a day to be yanked before the bump PR proposes it. An entry with a `sha256`
has its asset downloaded and hashed, so the manifest never carries a checksum nobody verified.

A major version is proposed like any other update, but `--publish` arms auto-merge only when no pin in the staged
manifest crosses a major version. A pull request that carries a major gets the `major` label, waits for review and has
auto-merge taken back; a branch head that moved (LuaJIT, the Ketho annotations) moves within its branch, so it is
always a minor change.
"""

import argparse
import base64
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from dependabot_merge import LABEL as MAJOR_LABEL
from dependabot_merge import LABEL_COLOR as MAJOR_COLOR
from dependabot_merge import LABEL_DESCRIPTION as MAJOR_DESCRIPTION

MANIFEST = Path(__file__).resolve().parent.parent / "toolchain.json"
COOLDOWN_DAYS = 1
TITLE = "chore(deps): bump the tool pins"
BRANCH = "toolchain-bump"
SCRATCH = "toolchain-bump-src"
LABEL = "dependencies"
MANIFEST_NAME = "toolchain.json"
SECTIONS = ("runtimes", "tools")
VERSION = re.compile(r"\d+(?:\.\d+)*")


@dataclass
class Update:
    """One pin that moved: the group it is in, its name, the fields to set and when upstream published it."""

    group: str
    name: str
    fields: dict[str, str]
    published: str | None = None


class Net:
    """The two reads the bumper needs. Tests pass a fake with the same two methods."""

    def github(self, path: str):
        result = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=False)
        if result.returncode:
            raise SystemExit(f"gh api {path} failed: {result.stderr.strip()}")
        return json.loads(result.stdout)

    def get(self, url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=300) as response:
            return response.read()


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def tag_pattern(template: str) -> re.Pattern:
    """The regex a tag of an entry's `tag` template must match, with the version in the `version` group."""
    prefix, _, suffix = template.partition("{version}")
    return re.compile(re.escape(prefix) + r"(?P<version>[0-9][0-9A-Za-z._\-]*?)" + re.escape(suffix))


def version_from_tag(tag: str, upstream: dict) -> str | None:
    """The version a tag names, after the entry's tag, strip and series rules, or None when it is not a version tag."""
    template = upstream.get("tag")
    if template:
        match = tag_pattern(template).fullmatch(tag)
        if match is None:
            return None
        text = match.group("version")
    else:
        text = tag.strip().removeprefix("v")
    text = text.replace("_", ".")
    if not VERSION.fullmatch(text):
        return None
    parts = text.split(".")
    strip = upstream.get("strip")
    if strip == "major":
        parts = parts[:1]
    elif strip == "minor":
        parts = parts[:2]
    version = ".".join(parts)
    series = upstream.get("series")
    if series and not re.search(series, version):
        return None
    return version


def published_at(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def too_young(text: str | None, now: datetime, days: int) -> bool:
    """True when upstream published `text` less than `days` ago, so the bumper waits for a later run."""
    moment = published_at(text)
    return moment is not None and now - moment < timedelta(days=days)


def checksum(net: Net, entry: dict, version: str) -> str:
    """The sha256 of the entry's release asset at `version`."""
    return hashlib.sha256(net.get(entry["url"].format(version=version))).hexdigest()


def newest(items: list[dict], name_key: str, upstream: dict) -> tuple[str, dict] | None:
    """The release or tag with the highest version that the entry tracks, skipping drafts and prereleases."""
    best = None
    for item in items:
        if item.get("draft") or item.get("prerelease"):
            continue
        version = version_from_tag(item.get(name_key, ""), upstream)
        if version is not None and (best is None or version_key(version) > version_key(best[0])):
            best = (version, item)
    return best


def plan_entry(group: str, name: str, entry: dict, net: Net, now: datetime, days: int) -> Update | None:
    """The update `entry` needs, or None when it is current, upstream cannot be read, or the release is too young."""
    upstream = entry["upstream"]
    kind = upstream["kind"]
    if kind == "github-release":
        found = newest(net.github(f"repos/{upstream['repo']}/releases?per_page=100"), "tag_name", upstream)
        if found is None:
            return None
        version, release = found
        current = entry.get("version")
        if current and version_key(version) <= version_key(current):
            return None
        published = release.get("published_at") or release.get("created_at")
        if too_young(published, now, days):
            return None
        fields = {"version": version}
        if "sha256" in entry:
            fields["sha256"] = checksum(net, entry, version)
        return Update(group, name, fields, published)
    if kind == "github-tag":
        found = newest(net.github(f"repos/{upstream['repo']}/tags?per_page=100"), "name", upstream)
        if found is None:
            return None
        version, tag = found
        commit = tag["commit"]["sha"]
        current = entry.get("version")
        if current:
            # A tag older than the pin is never a downgrade to propose; upstream trimmed its tags or moved the line.
            if version_key(version) <= version_key(current):
                return None
        elif entry.get("commit") == commit:
            return None
        published = net.github(f"repos/{upstream['repo']}/commits/{commit}")["commit"]["committer"]["date"]
        if too_young(published, now, days):
            return None
        fields = {"version": version}
        if "commit" in entry:
            fields["commit"] = commit
        if "sha256" in entry:
            fields["sha256"] = checksum(net, entry, version)
        return Update(group, name, fields, published)
    if kind == "github-branch":
        commit = net.github(f"repos/{upstream['repo']}/commits/{upstream['branch']}")
        sha = commit["sha"]
        if entry.get("commit") == sha:
            return None
        published = commit["commit"]["committer"]["date"]
        if too_young(published, now, days):
            return None
        return Update(group, name, {"commit": sha}, published)
    if kind == "npm":
        package = json.loads(net.get(f"https://registry.npmjs.org/{quote(upstream['package'])}"))
        version = package["dist-tags"]["latest"]
        current = entry.get("version")
        if current and version_key(version) <= version_key(current):
            return None
        published = package.get("time", {}).get(version)
        if too_young(published, now, days):
            return None
        return Update(group, name, {"version": version}, published)
    raise SystemExit(f"{name}: unknown upstream kind {kind}")


def plan(manifest: dict, net: Net, now: datetime, days: int = COOLDOWN_DAYS) -> list[Update]:
    """Every pin that needs to move, in manifest order."""
    updates = []
    for group in SECTIONS:
        for name, entry in manifest.get(group, {}).items():
            update = plan_entry(group, name, entry, net, now, days)
            if update is not None:
                updates.append(update)
    return updates


def apply(manifest: dict, updates: list[Update]) -> None:
    for update in updates:
        manifest[update.group][update.name].update(update.fields)


def write(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def describe(entry: dict, fields: dict[str, str]) -> str:
    """The pin as a person reads it: the version, else the commit, with a short checksum when it moved."""
    shown = {key: value[:12] if key in {"commit", "sha256"} else value for key, value in fields.items()}
    before = {key: (entry.get(key) or "")[:12] if key in {"commit", "sha256"} else entry.get(key) for key in shown}
    return ", ".join(f"{key} {before[key]} -> {value}" for key, value in shown.items())


def version_major(entry: dict) -> int | None:
    """The major part of a pin's version, or None for a pin that tracks a commit instead."""
    version = entry.get("version")
    if not version:
        return None
    return int(version.split(".")[0])


def changes(before: dict, after: dict) -> tuple[list[str], list[str]]:
    """Every pin that moved from `before` to `after` as a line to read, and the pins among them that cross a major.

    A commit-only pin tracks a branch head, so a move there stays inside its branch and is always minor; only a
    version pin can cross a major.
    """
    lines, majors = [], []
    for group in SECTIONS:
        for name, entry in after.get(group, {}).items():
            old = before.get(group, {}).get(name, {})
            fields = {key: value for key, value in entry.items() if isinstance(value, str) and old.get(key) != value}
            if not fields:
                continue
            lines.append(f"{group}.{name}: {describe(old, fields)}")
            old_major, new_major = version_major(old), version_major(entry)
            if old_major is not None and new_major is not None and new_major > old_major:
                majors.append(f"{group}.{name}")
    return lines, majors


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def api(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["gh", "api", *args], capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise SystemExit(f"gh api {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def repository() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "cjber/forever-core")


def staged_changes() -> tuple[list[dict], list[dict]]:
    """The additions and deletions git has staged, as the GraphQL mutation wants them."""
    git("add", "-A")
    additions, deletions = [], []
    for line in git("diff", "--cached", "--name-status").splitlines():
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
        contents = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        additions.append({"path": path, "contents": contents})
    return additions, deletions


CREATE_COMMIT = """
mutation($input: CreateCommitOnBranchInput!) {
  createCommitOnBranch(input: $input) {
    commit { oid }
  }
}
"""


def create_commit(branch: str, base: str, additions: list[dict], deletions: list[dict], message: str) -> str:
    """Create the commit through GraphQL, so GitHub signs it and the repository's required_signatures accepts it."""
    request = {
        "query": CREATE_COMMIT,
        "variables": {
            "input": {
                "branch": {"repositoryNameWithOwner": repository(), "branchName": branch},
                "expectedHeadOid": base,
                "message": {"headline": TITLE, "body": message},
                "fileChanges": {"additions": additions, "deletions": deletions},
            }
        },
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(request, handle)
        body = handle.name
    try:
        result = api("graphql", "--input", body)
    finally:
        Path(body).unlink(missing_ok=True)
    try:
        return json.loads(result.stdout)["data"]["createCommitOnBranch"]["commit"]["oid"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise SystemExit(f"createCommitOnBranch returned no commit: {error}") from error


def point_branch(branch: str, oid: str) -> None:
    """Point `branch` at `oid`, force-moving an existing ref and creating it when it does not exist yet."""
    ref = f"repos/{repository()}/git/refs/heads/{branch}"
    if api(ref, "--method", "PATCH", "-f", f"sha={oid}", "-F", "force=true", check=False).returncode == 0:
        return
    api(f"repos/{repository()}/git/refs", "--method", "POST", "-f", f"ref=refs/heads/{branch}", "-f", f"sha={oid}")


def pull_requests() -> list[dict]:
    owner = repository().split("/")[0]
    return json.loads(api(f"repos/{repository()}/pulls?head={owner}:{BRANCH}&state=open").stdout)


def open_or_update_pr(body: str) -> tuple[int, str]:
    """Open the bump PR or refresh it, returning its number and its page URL."""
    listed = pull_requests()
    if listed:
        pull = listed[0]
        updated = api(
            f"repos/{repository()}/pulls/{pull['number']}",
            "--method",
            "PATCH",
            "-f",
            f"title={TITLE}",
            "-f",
            f"body={body}",
        )
        return pull["number"], json.loads(updated.stdout)["html_url"]
    created = json.loads(
        api(
            f"repos/{repository()}/pulls",
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
    return created["number"], created["html_url"]


def label(number: int, name: str, color: str, description: str) -> None:
    """Create the label if it is missing, then put it on the pull request."""
    api(
        f"repos/{repository()}/labels",
        "--method",
        "POST",
        "-f",
        f"name={name}",
        "-f",
        f"color={color}",
        "-f",
        f"description={description}",
        check=False,
    )
    api(f"repos/{repository()}/issues/{number}/labels", "--method", "POST", "-f", f"labels[]={name}")


def unlabel(number: int, name: str) -> None:
    """Drop a label the pull request no longer needs."""
    api(f"repos/{repository()}/issues/{number}/labels/{name}", "--method", "DELETE", check=False)


def head_manifest() -> dict:
    """toolchain.json as main has it, so a staged move can be compared with what it replaces."""
    try:
        return json.loads(git("show", f"HEAD:{MANIFEST_NAME}", check=False))
    except json.JSONDecodeError:
        return {}


def open_pr() -> int:
    """Commit the staged toolchain.json through the API, then open or update the bump PR.

    Auto-merge is armed only when no staged pin crosses a major version; a pull request that carries one gets the
    `major` label and waits for review.
    """
    additions, deletions = staged_changes()
    if not additions and not deletions:
        print(f"Nothing to publish: {MANIFEST_NAME} is current.")
        return 0
    lines, majors = changes(head_manifest(), json.loads(Path(MANIFEST_NAME).read_text(encoding="utf-8")))
    files = [entry["path"] for entry in additions]
    base = git("rev-parse", "HEAD").strip()
    message = "\n".join(lines) + "\n" if lines else "Updates " + ", ".join(files) + "\n"
    point_branch(SCRATCH, base)
    commit = create_commit(SCRATCH, base, additions, deletions, message)
    point_branch(BRANCH, commit)
    decision = (
        [
            "A major version moved in this run, so it waits for review and auto-merge is not armed:",
            *(f"- `{name}`" for name in majors),
            "",
            "Dismiss the `major` label and merge by hand once the update is checked.",
        ]
        if majors
        else ["Auto-merge is armed, so the repository's own checks decide when this lands."]
    )
    body = "\n".join(
        [
            f"Moves the pins in `{MANIFEST_NAME}` to their newest upstream releases.",
            "",
            *(f"- `{line}`" for line in lines),
            "",
            "Files:",
            *(f"- `{path}`" for path in files),
            "",
            "Prepared by `tools/bump_toolchain.py` in the bump-toolchain workflow. Every sha256 was downloaded and",
            "checked here.",
            "",
            *decision,
        ]
    )
    number, url = open_or_update_pr(body)
    label(number, LABEL, "0366d6", "Dependency updates")
    if majors:
        # The branch is force-moved on every run, so an earlier minor run may have armed auto-merge on this same PR.
        subprocess.run(["gh", "pr", "merge", "--disable-auto", url], capture_output=True, text=True, check=False)
        label(number, MAJOR_LABEL, MAJOR_COLOR, MAJOR_DESCRIPTION)
        print(f"toolchain-bump: pull request #{number} updated; {', '.join(majors)} waits for review")
        return 0
    unlabel(number, MAJOR_LABEL)
    merged = subprocess.run(
        ["gh", "pr", "merge", "--auto", "--squash", url], capture_output=True, text=True, check=False
    )
    if merged.returncode:
        print(f"auto-merge not enabled; the pull request waits for a manual merge ({merged.stderr.strip()})")
    print(f"toolchain-bump: pull request #{number} updated")
    return 0


def main(argv: list[str] | None = None, net: Net | None = None, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--dry-run", action="store_true", help="print the planned changes and write nothing")
    parser.add_argument(
        "--cooldown", type=int, default=COOLDOWN_DAYS, help="days a release must be published before it is proposed"
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="commit every staged change and open or update the bump PR, without reading upstream",
    )
    arguments = parser.parse_args(argv)

    if arguments.publish:
        return open_pr()
    manifest = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    updates = plan(manifest, net or Net(), now or datetime.now(timezone.utc), arguments.cooldown)
    moved = copy.deepcopy(manifest)
    apply(moved, updates)
    lines, _ = changes(manifest, moved)
    if not lines:
        print("toolchain.json is current")
    for line in lines:
        print(line)
    if arguments.dry_run or not updates:
        return 0
    write(arguments.manifest, moved)
    print(f"toolchain.json: {len(updates)} pin(s) moved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
