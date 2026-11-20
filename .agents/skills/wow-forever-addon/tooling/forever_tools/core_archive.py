"""Check the ForeverCore versions a built consumer package would install."""

import argparse
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import core_pin


@dataclass(frozen=True)
class Copy:
    path: str
    layout: str
    tag: str


def version(tag: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?([1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", tag)
    if not match:
        raise ValueError(f"invalid ForeverCore version {tag!r}")
    major, minor, patch = map(int, match.groups())
    return major, minor, patch


def tag(value: str) -> str:
    return "v" + ".".join(map(str, version(value)))


def installed_name(name: str) -> str:
    return name.rstrip(" .").casefold()


def embedded_tag(folder) -> str:
    manifest = json.loads((folder / "bundle.json").read_text(encoding="utf-8"))
    if manifest["schema"] != 1 or manifest["standalone"] is not False:
        raise ValueError("invalid embedded bundle schema")
    major, minor, patch = version(manifest["version"])
    build = major * 1000000 + minor * 1000 + patch
    digest = manifest["source_digest"]
    if minor >= 1000 or patch >= 1000 or manifest["build"] != build or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("invalid bundle version, build or source digest")
    # tools/build_embedded_core.py stamps Begin(addon, build, identity, chunks) since 1.15.4 and Begin(addon, build,
    # identity) before, which released packages still carry. The chunk count is the loader's own Seal check, so only
    # the build and the identity (bundle.json's source_digest) are compared here.
    begin = (folder / "Begin.lua").read_bytes().decode("utf-8")
    stamp = re.compile(
        r'host\.ForeverCoreCopy = ForeverCoreLoader\.Begin\(addon, ([0-9]+), "([0-9a-f]{64})"(?:, [1-9][0-9]*)?\)'
    )
    stamped = [match.groups() for match in map(stamp.fullmatch, begin.splitlines()) if match]
    if stamped != [(str(build), digest)]:
        raise ValueError("bundle build and digest disagree with Begin.lua")
    prefix = "Libs/ForeverCore/"
    expected = {name: sha for name, sha in manifest["files"].items() if name.startswith(prefix)}
    actual = set()
    pending = [(folder, prefix)]
    while pending:
        parent, base = pending.pop()
        for child in parent.iterdir():
            name = base + child.name
            if child.is_dir():
                pending.append((child, name + "/"))
            elif name != prefix + "bundle.json":
                actual.add(name)
                data = child.read_bytes()
                # BigWigs converts these text formats to CRLF by default, after the embed step hashes them.
                hashes = {hashlib.sha256(data).hexdigest()}
                if Path(name).suffix in {".lua", ".md", ".toc", ".txt", ".xml"}:
                    hashes.add(hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest())
                if expected.get(name) not in hashes:
                    raise ValueError(f"{name}: file disagrees with its bundle hash")
    if actual != expected.keys():
        raise ValueError("embedded files disagree with bundle hashes")
    return tag(manifest["version"])


def inspect(root) -> tuple[list[Copy], list[str]]:
    """Inspect all installed copies in a directory or a zipfile.Path."""
    copies, failures = [], []

    def read(folder, path, layout):
        try:
            if layout == "bridge":
                tocs = [item for item in folder.iterdir() if installed_name(item.name) == "forevercore.toc"]
                if len(tocs) != 1:
                    raise ValueError("expected one ForeverCore.toc")
                carried = tag(core_pin.toc_fields(tocs[0].read_bytes()).get("version", ""))
            else:
                carried = embedded_tag(folder)
            copies.append(Copy(path, layout, carried))
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            failures.append(f"{path}: cannot read carried ForeverCore version ({error})")

    for addon in sorted(root.iterdir(), key=lambda item: item.name):
        if not addon.is_dir():
            continue
        if installed_name(addon.name) == "forevercore":
            read(addon, addon.name, "bridge")
        for libs in addon.iterdir():
            if libs.is_dir() and installed_name(libs.name) == "libs":
                for core in libs.iterdir():
                    if core.is_dir() and installed_name(core.name) == "forevercore":
                        read(core, f"{addon.name}/{libs.name}/{core.name}", "embed")
    return copies, failures


def check(root: Path, packaged, latest: str | None = None) -> list[str]:
    """Compare the packaged versions and layout with the checkout's release policy."""
    try:
        policy = core_pin.policy_path(root)
        pkgmeta = policy.read_text(encoding="utf-8") if policy else ""
        name = core_pin.root_toc_name(root, core_pin.policy_package(pkgmeta))
        toc = (root / name).read_bytes() if name else b""
        packaged_toc = packaged / Path(name).stem / name if name else None
        built_toc = packaged_toc.read_bytes() if packaged_toc is not None and packaged_toc.is_file() else b""
        fields = core_pin.toc_fields(toc)
        pin_path = root / core_pin.PIN_PATH
        pin = pin_path.read_text(encoding="utf-8").strip() if pin_path.is_file() else ""
        copies, failures = inspect(packaged)
    except (OSError, ValueError) as error:
        return [str(error)]
    embedded = core_pin.embeds(toc) or core_pin.embeds(built_toc)
    if embedded and name:
        expected = f"{Path(name).stem}/Libs/ForeverCore"
        if not any(copy.path.casefold() == expected.casefold() for copy in copies):
            failures.append(f"package must carry the opted-in ForeverCore at {expected}")
    # A TOC dependency can point to an independently installed addon. Only bundle declarations require a copy.
    elif fields.get("x-forever-core") or core_pin.external_line(pkgmeta):
        if not any(copy.layout == "bridge" for copy in copies):
            failures.append("package must carry the bridge ForeverCore at the top level")
    for copy in copies:
        if embedded and copy.layout == "bridge":
            failures.append(f"{copy.path}: an embed-only consumer must not install a top-level ForeverCore")
        if copy.tag != pin:
            failures.append(f"{copy.path}: carries {copy.tag}, but {core_pin.PIN_PATH} pins {pin or '(missing)'}")
        if latest is not None and copy.tag != latest:
            failures.append(f"{copy.path}: carries {copy.tag}, but core's latest release is {latest}")
    return failures


def check_zip(root: Path, data: bytes, latest: str) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        paths = set()
        for info in archive.infolist():
            name = info.orig_filename
            # Keep explicit directory entries, but reject aliases before zipfile.Path builds its tree.
            parts = name.removesuffix("/").split("/")
            if any(part in ("", ".", "..") for part in parts) or any(char in name for char in "\\\x00:"):
                return [f"unsafe zip member {name!r}"]
            key = tuple(installed_name(part) for part in parts)
            if key in paths:
                return [f"duplicate installed zip member {info.filename!r}"]
            paths.add(key)
        return check(root, zipfile.Path(archive), latest)


def main(argv=None, *, fetch=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, default=Path(".release"))
    parser.add_argument(
        "--latest", action="store_true", help="check the built ZIP against the latest published release"
    )
    args = parser.parse_args(argv)
    try:
        if args.latest:
            archives = sorted(args.release_dir.glob("*.zip"))
            if len(archives) != 1:
                raise ValueError(f"{args.release_dir}: expected one built ZIP, found {len(archives)}")
            archive = archives[0]
            if "\r" in str(archive) or "\n" in str(archive):
                raise ValueError("release ZIP path cannot contain a line break")
            data = archive.read_bytes()
            latest = core_pin.latest_release(fetch)
            version(latest)
            failures = check_zip(Path.cwd(), data, latest)
            if not failures and (output := os.environ.get("GITHUB_OUTPUT")):
                with Path(output).open("a", encoding="utf-8") as stream:
                    stream.write(f"archive={archive.resolve()}\narchive_name={archive.name}\n")
                    stream.write(f"sha256={hashlib.sha256(data).hexdigest()}\n")
        else:
            failures = check(Path.cwd(), args.release_dir)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
        failures = [str(error)]
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("Packaged ForeverCore copies match release policy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
