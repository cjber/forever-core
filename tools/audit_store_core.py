"""Audit the ForeverCore copies in the latest GitHub and CurseForge consumer releases."""

import argparse
import json
import os
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from check_consumers import read_pkgmeta, root_toc
from check_core_shared import KILN_CONSUMERS

# check_consumers loads the producer tooling onto sys.path.
from forever_tools import core_archive, core_pin  # noqa: E402
from released_consumers import (
    OWNER,
    ReleasedError,
    addon_assets,
    addon_folders,
    consumer_repos,
    discover_tooling_repos,
    download,
    extract,
    latest_release,
    member_path,
)

CORE_REPO = "forever-core"
MIN_CORE = "v1.15.0"
# Sync PRs must merge, pass main CI and smoke, and reach the 20-minute release dispatcher and CurseForge moderation.
GRACE = timedelta(hours=24)
CF_APPROVED = 4
CF_RELEASE = 1
CF_FOREVER = 88568  # The Forever game-version type in BigWigs packager v2.7.0.
ISSUE_TITLE = "Store releases ship outdated ForeverCore"
READ_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    tarfile.TarError,
    zipfile.BadZipFile,
)


def discover():
    return consumer_repos(discover_tooling_repos(strict=True))


def cf_json(url, *, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def curseforge_asset(project, *, fetch=cf_json, key=None):
    """Resolve the newest stable Forever file players can download from this project."""
    base = f"https://www.curseforge.com/api/v1/mods/{project}/files"
    page = seen = 0
    while True:
        listing = fetch(f"{base}?pageIndex={page}&pageSize=50&releaseType=1")
        seen += len(listing["data"])
        for item in listing["data"]:
            if (
                item["releaseType"] != CF_RELEASE
                or item["status"] != CF_APPROVED
                or CF_FOREVER not in item["gameVersionTypeIds"]
            ):
                continue
            file_id, name = int(item["id"]), item["fileName"]
            if key:
                url = fetch(
                    f"https://api.curseforge.com/v1/mods/{project}/files/{file_id}/download-url",
                    headers={"x-api-key": key},
                )["data"]
            else:
                # The public listing includes no download URL. ForgeCDN splits the file ID into two path segments.
                url = f"https://edge.forgecdn.net/files/{file_id // 1000}/{file_id % 1000}/{quote(name, safe='')}"
            return {"name": name, "browser_download_url": url}
        # pageIndex counts pages, not files.
        page += 1
        if not listing["data"] or seen >= listing["pagination"]["totalCount"]:
            raise ReleasedError(f"CurseForge project {project} has no approved Forever release")


def extract_kiln(archive: Path, target: Path) -> Path:
    """Kiln's installer ships a tarball and installs only its addon/ subtree."""
    with tarfile.open(archive) as package:
        files = []
        for member in package.getmembers():
            path = member_path(member.name)
            if path.parts[:1] != ("addon",):
                continue
            if not (member.isdir() or member.isfile()):
                raise ReleasedError(f"refusing non-file Kiln member {member.name!r}")
            files.append(member)
        package.extractall(target, members=files, filter="data")
    return target / "addon"


def inspect_package(folder, latest, *, core_grace, allow_no_core=False, awaiting_approval=False):
    copies, failures = core_archive.inspect(folder)
    addons = addon_folders(folder)
    if not addons:
        failures.append("package contains no addon folder")
    projects = set()
    embedded = False
    for name, addon in addons:
        toc = (addon / f"{name}.toc").read_bytes()
        project = core_pin.toc_fields(toc).get("x-curse-project-id")
        if project:
            projects.add(int(project))
        if core_pin.embeds(toc):
            embedded = True
            expected = f"{name}/Libs/ForeverCore".casefold()
            if not any(copy.path.casefold() == expected for copy in copies):
                failures.append(f"{name}: opted in to embedding but is missing Libs/ForeverCore")
    if not copies and not allow_no_core:
        failures.append("package carries no ForeverCore")
    latest_version = core_archive.version(latest)
    for copy in copies:
        version = core_archive.version(copy.tag)
        if copy.layout == "bridge" and embedded:
            failures.append(f"{copy.path}: embed-only package still installs a top-level ForeverCore")
        if awaiting_approval:
            continue
        if version < core_archive.version(MIN_CORE):
            failures.append(f"{copy.path}: {copy.tag} is below the minimum {MIN_CORE}")
        if version < latest_version and (copy.layout == "bridge" or not core_grace):
            failures.append(f"{copy.path}: {copy.tag} is older than latest {latest}")
    report = ", ".join(f"{copy.layout} {copy.tag} ({copy.path})" for copy in copies) or "no readable ForeverCore copies"
    return report, failures, projects


def project_lookup(repo):
    """Find the project on main when the GitHub archive cannot provide its TOC."""
    path, pkgmeta, error = read_pkgmeta(repo, "main", None)
    if error:
        raise ReleasedError(f"{path}: {error}")
    _folder, toc, error = root_toc(repo, pkgmeta or "", "main", None, path)
    if error:
        raise ReleasedError(error)
    project = core_pin.toc_fields(toc).get("x-curse-project-id")
    if not project:
        raise ReleasedError("consumer TOC names no CurseForge project")
    return int(project)


def audit(
    cache,
    *,
    now,
    repos=discover,
    release=latest_release,
    fetch_asset=download,
    cf_asset=curseforge_asset,
    lookup_project=project_lookup,
):
    reports, failures = [], []
    try:
        core = release(CORE_REPO)
        latest = core["tag_name"]
        core_archive.version(latest)
        published = datetime.fromisoformat(core["published_at"].replace("Z", "+00:00"))
        core_grace = now - published < GRACE
        names = repos()
        if not names:
            raise ReleasedError("no consumer repositories discovered")
    except READ_ERRORS as error:
        return reports, [f"Could not establish audit inputs: {error}"]

    for repo in names:
        kiln = repo in KILN_CONSUMERS
        projects = set()
        release_tag = "(unavailable)"
        assets = []
        recent_github = False
        github_failures = []
        try:
            github = release(repo)
            if github is None:
                # Nothing is published, so no player download can carry a ForeverCore.
                reports.append(f"{repo}: no published release")
                continue
            if not github.get("tag_name"):
                raise ReleasedError("latest published release unavailable")
            release_tag = github["tag_name"]
            assets = addon_assets(github)
            if not assets and kiln:
                filename = f"kiln-forever-{release_tag.removeprefix('v')}.tar.gz"
                assets = [file for file in github["assets"] if file["name"] == filename]
            if not assets:
                raise ReleasedError(f"{release_tag} ships no downloadable addon archive")
            if github.get("published_at"):
                published = datetime.fromisoformat(github["published_at"].replace("Z", "+00:00"))
                recent_github = timedelta(0) <= now - published < GRACE
        except READ_ERRORS as error:
            github_failures.append(f"{repo} GitHub {release_tag}: {error}")

        for index, asset in enumerate(assets):
            label = f"{repo} GitHub {release_tag} ({asset['name']})"
            try:
                archive = fetch_asset(asset, cache / f"{repo}-{index}.github")
                folder = cache / f"{repo}-{index}-github"
                if kiln and asset["name"].endswith(".tar.gz"):
                    folder = extract_kiln(archive, folder)
                else:
                    extract(archive, folder)
                report, problems, asset_projects = inspect_package(
                    folder, latest, core_grace=core_grace, allow_no_core=kiln
                )
                projects.update(asset_projects)
                reports.append(f"{label}: {report}")
                github_failures.extend(f"{label}: {problem}" for problem in problems)
            except READ_ERRORS as error:
                github_failures.append(f"{label}: {error}")
        failures.extend(github_failures)
        github_names = {asset["name"] for asset in assets}
        if not projects and not kiln:
            try:
                projects.add(lookup_project(repo))
            except READ_ERRORS as error:
                failures.append(f"{repo} CurseForge: {error}")

        for project in sorted(projects):
            try:
                cf = cf_asset(project)
                archive = fetch_asset(cf, cache / f"{repo}-{project}.curseforge", request=urllib.request.Request)
                folder = cache / f"{repo}-{project}-curseforge"
                extract(archive, folder)
                file_name = cf["name"]
                mismatch = bool(github_names) and file_name not in github_names
                awaiting_approval = mismatch and recent_github and not github_failures
                report, problems, _projects = inspect_package(
                    folder, latest, core_grace=core_grace, awaiting_approval=awaiting_approval
                )
                reports.append(f"{repo} CurseForge {file_name} (GitHub {release_tag}): {report}")
                if mismatch and not awaiting_approval:
                    expected = ", ".join(sorted(github_names))
                    problems.append(f"file-name parity mismatch with GitHub {release_tag}: expected one of {expected}")
                failures.extend(f"{repo} CurseForge {file_name}: {problem}" for problem in problems)
            except READ_ERRORS as error:
                failures.append(f"{repo} CurseForge project {project}: {error}")
    return reports, failures


def issue_api(path, method="GET", data=None):
    token = os.environ["GITHUB_TOKEN"]
    request = urllib.request.Request(
        f"https://api.github.com/repos/{OWNER}/{CORE_REPO}/{path}",
        data=None if data is None else json.dumps(data).encode(),
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def update_issue(failures, *, api=issue_api):
    body = "\n".join(["The latest store audit failed.", "", *(f"- {failure}" for failure in failures)])
    page = 1
    while True:
        issues = api(f"issues?state=open&per_page=100&page={page}")
        for issue in issues:
            if "pull_request" not in issue and issue["title"] == ISSUE_TITLE:
                if issue.get("body") != body:
                    api(f"issues/{issue['number']}", "PATCH", {"body": body})
                return
        if len(issues) < 100:
            api("issues", "POST", {"title": ISSUE_TITLE, "body": body})
            return
        page += 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--update-issue", action="store_true")
    args = parser.parse_args(argv)
    args.cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="store-core-", dir=args.cache) as directory:
        reports, failures = audit(
            Path(directory),
            now=datetime.now(timezone.utc),
            cf_asset=lambda project: curseforge_asset(project, key=os.environ.get("CF_API_KEY")),
        )
    for report in reports:
        print(report)
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures and args.update_issue:
        try:
            update_issue(failures)
        except READ_ERRORS as error:
            print(f"Could not record the audit issue: {error}", file=sys.stderr)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
