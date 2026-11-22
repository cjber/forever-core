#!/usr/bin/env python3
"""Unpack every consumer's latest GitHub release, so a candidate ForeverCore can be loaded with the builds players have.

A core release reaches players before the addons that depend on it are re-released: the CurseForge app installs the
newest approved core, and a player can update core by itself. So a core release has to keep working with the addon
releases already on the stores, and this downloads exactly those. Each consumer is discovered the way
`tools/release_consumers.py` discovers it, its latest published release is read, and the release's addon zip (not the
packager's `release.json`) is unpacked under `tools/.cache/released`. A consumer with no release is skipped with a line
saying so, but a run that finds no consumer folder at all is an error, because the gate would otherwise pass on core
alone. A failed read, download or unpack is an error too, because a gate that cannot see a consumer's build must not
pass.

The unpacked folders are what `tools/suite_load.py --released` passes to `forever_sim` and what a core smoke links
beside the candidate core. Each zip is untrusted data: it is unpacked member by member and a member with an
absolute path or a `..` step is refused rather than written. The bundled `ForeverCore` folder and
top-level `Lib*` folders are left out of the returned list, so the candidate core is the one loaded and the addon's own
folder is the only thing registered from that release.

    python3 tools/released_consumers.py            # unpack every consumer's latest release and list the folders
    python3 tools/released_consumers.py --cache DIR

Set `GH_TOKEN` to read a private consumer's release and to raise the anonymous API rate limit; without one the public
releases are read anonymously. A repository with no release, and one the token cannot read, both answer 404 and are
skipped with their own note.
"""

import argparse
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from check_consumers import authorized, remote_json
from release_consumers import consumer_repos, discover_tooling_repos
from sync_consumer_prs import OWNER, SyncError

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "tools/.cache/released"
# The packager names a release's addon asset `<Folder>-<tag>-forever.zip` and also uploads `release.json`, its metadata.
ARCHIVE = ".zip"
ASSET = "-forever.zip"
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
MAX_EXTRACTED_BYTES = 256 * 1024 * 1024
MAX_ZIP_MEMBERS = 20_000
# A consumer bundles core in its zip; the candidate core is the one under test, so that folder is dropped. Top-level
# library folders are dropped too: they are not the addon whose release behaviour this checks.
BUNDLED = "ForeverCore"
LIBRARY = "Lib"
TOC = ".toc"
TAG = re.compile(r"[^A-Za-z0-9._-]")


class ReleasedError(RuntimeError):
    """A consumer's release could not be read, downloaded or unpacked."""


def tag_label(release: dict) -> str:
    """A release's tag as a cache-folder suffix: anything but a name character becomes an underscore."""
    return TAG.sub("_", str(release.get("tag_name") or "latest"))


def latest_release(repo: str) -> dict | None:
    """The repository's latest published release, or None when it has never released one."""
    url = f"https://api.github.com/repos/{OWNER}/{repo}/releases/latest"
    try:
        return remote_json(url)
    except urllib.error.HTTPError as error:
        error.close()
        if error.code == 404:
            return None
        raise ReleasedError(f"could not read {OWNER}/{repo}'s latest release: {error}") from None
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ReleasedError(f"could not read {OWNER}/{repo}'s latest release: {error}") from None


def addon_assets(release: dict) -> list[dict]:
    """The release's Forever addon zips, falling back to other zip assets.

    The packager's `-forever.zip` asset is preferred; any other `.zip` is the next choice. `release.json` and every
    other asset the packager uploads are never the addon.
    """
    assets = [asset for asset in release.get("assets") or [] if str(asset.get("name") or "").endswith(ARCHIVE)]
    forever = [asset for asset in assets if str(asset.get("name") or "").endswith(ASSET)]
    return sorted(forever or assets, key=lambda asset: str(asset.get("name")))


def addon_asset(release: dict) -> dict | None:
    """Choose one addon zip for the released suite loader."""
    return next(iter(addon_assets(release)), None)


def download(asset: dict, destination: Path, request=authorized) -> Path:
    """Fetch one release asset to `destination`, authenticated only when a token is set."""
    url = asset.get("browser_download_url") or asset.get("url")
    if not url:
        raise ReleasedError(f"release asset {asset.get('name')!r} has no download URL")
    try:
        with urllib.request.urlopen(request(url), timeout=120) as response:
            data = response.read(MAX_DOWNLOAD_BYTES + 1)
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise ReleasedError(f"{asset.get('name')}: download exceeds {MAX_DOWNLOAD_BYTES} byte limit")
        destination.write_bytes(data)
    except (OSError, urllib.error.URLError, TimeoutError) as error:
        raise ReleasedError(f"could not download {asset.get('name')}: {error}") from None
    return destination


def member_path(name: str) -> PurePosixPath:
    """A zip member's path, refusing one that would escape the folder it is unpacked into."""
    path = PurePosixPath(name.replace("\\", "/"))
    drive = bool(path.parts) and path.parts[0].endswith(":")
    if path.is_absolute() or drive or ".." in path.parts:
        raise ReleasedError(f"refusing unsafe zip member {name!r}")
    return path


def extract(archive: Path, destination: Path) -> None:
    """Unpack an addon zip under a fresh `destination`, member by member, with unsafe names refused.

    Nothing is written outside `destination`: a member is joined to it only after `member_path` accepted it, and every
    entry is written as a regular file, so an archive cannot create a link out of the cache.
    """
    try:
        with zipfile.ZipFile(archive) as package:
            infos = package.infolist()
            if len(infos) > MAX_ZIP_MEMBERS:
                raise ReleasedError(f"{archive.name}: member count exceeds {MAX_ZIP_MEMBERS} limit")
            if sum(info.file_size for info in infos) > MAX_EXTRACTED_BYTES:
                raise ReleasedError(f"{archive.name}: extracted size exceeds {MAX_EXTRACTED_BYTES} byte limit")
            members = [(member_path(info.filename), info) for info in infos]
            if destination.exists():
                shutil.rmtree(destination)
            destination.mkdir(parents=True)
            installed = set()
            for path, info in members:
                if not path.parts:
                    continue
                key = tuple(part.rstrip(" .").casefold() for part in path.parts)
                if key in installed:
                    raise ReleasedError(f"refusing duplicate installed member {info.filename!r}")
                installed.add(key)
                target = destination.joinpath(*path.parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(info) as source, target.open("wb") as sink:
                    shutil.copyfileobj(source, sink)
    except (OSError, zipfile.BadZipFile) as error:
        raise ReleasedError(f"could not unpack {archive.name}: {error}") from None


def addon_folders(root: Path) -> list[tuple[str, Path]]:
    """The addon folders a release ships, as their name and folder: its own code, never core or a library.

    A release zip holds the addon's folder beside the `ForeverCore` folder it bundles and any library the packager
    moved in. Only a folder whose `<name>.toc` sits inside it is an addon, and the bundled core and `Lib*` folders are
    left out of the list, so the candidate core is the one the caller loads.
    """
    folders = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        if folder.name == BUNDLED or folder.name.startswith(LIBRARY):
            continue
        if (folder / f"{folder.name}{TOC}").is_file():
            folders.append((folder.name, folder))
    return folders


def released_folders(destination: Path | None = None) -> list[tuple[str, Path]]:
    """Download and unpack every consumer's latest release, returning its addon folders.

    A consumer with no release, or a release with no addon zip, is skipped with a line saying so. A failed read,
    download or unpack raises `ReleasedError`, and so does a run that found no consumer folder at all: the caller is a
    release gate, and one it cannot check must fail it.
    """
    destination = destination or CACHE
    destination.mkdir(parents=True, exist_ok=True)
    try:
        repos = consumer_repos(discover_tooling_repos())
    except SyncError as error:
        raise ReleasedError(f"could not discover the consumers: {error}") from None
    folders: list[tuple[str, Path]] = []
    for repo in repos:
        release = latest_release(repo)
        if release is None:
            print(f"{repo}: no release; skipped")
            continue
        asset = addon_asset(release)
        if asset is None:
            print(f"{repo}: release {release.get('tag_name')} ships no addon zip; skipped")
            continue
        target = destination / f"{repo}-{tag_label(release)}"
        downloaded = download(asset, target.parent / f"{target.name}.zip")
        try:
            extract(downloaded, target)
        finally:
            downloaded.unlink(missing_ok=True)
        addons = addon_folders(target)
        if not addons:
            raise ReleasedError(f"{asset.get('name')} holds no addon folder")
        for name, _path in addons:
            print(f"{repo}: {release.get('tag_name')} {name}")
        folders.extend(addons)
    if not folders:
        raise ReleasedError("no released consumer found: the gate cannot check anything")
    return folders


def main(argv: list[str] | None = None) -> int:
    """Unpack every release and print the folders, failing on any read, download, unpack or empty release."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cache", type=Path, default=CACHE, help=f"where the releases are unpacked (default {CACHE})")
    arguments = parser.parse_args(argv)
    try:
        folders = released_folders(arguments.cache)
    except ReleasedError as error:
        print(f"released_consumers: {error}", file=sys.stderr)
        return 1
    for name, path in folders:
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
