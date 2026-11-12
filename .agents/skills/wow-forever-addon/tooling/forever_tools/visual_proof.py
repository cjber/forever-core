"""Verify human-recorded in-game visual proof for runtime UI changes.

The proof separates what the checkout supplies from what a release installs:

- `input_digest` is the source identity: every runtime file the TOC graph reaches, every other Lua or XML the
  package selection ships (loaded or not), including artwork that only the store uses, the Core pin and the
  packaging policy (`.pkgmeta` or `pkgmeta.yaml`). Any change to it, even to an asset no package ships, or to which
  files the policy ships, invalidates a recorded session.
- `candidate` is the canonical packaged runtime: the same graph after the packager's selection (`.pkgmeta`'s
  `ignore` plus git's untracked and ignored files, which a release build does not ship), with the packager's
  line-ending
  filter on `*.lua`, `*.md`, `*.toc`, `*.txt` and `*.xml` and its project-version substitution in the TOC's
  `## Version:` line accounted for. This is the bytes a release zip installs at the addon's folder, and
  `candidate_digest` gives the same answer for a package extraction, which carries no `.pkgmeta`: the canonical
  form is uniform, so it never needs the checkout's policy to be reproduced. A `plain-copy` file ships raw, but an
  extraction carries nothing that says so, so a packager token, a TOC BOM or a `## Interface-` line is refused there
  too: the supported identity is symmetric. Line endings do not change how the client runs Lua, so the canonical
  form still normalises them. The package's non-dot Lua and XML are part of the candidate whether the TOC/XML
  graph loads them or not, because the packager ships them either way; an ignored file the graph loads is still
  refused.
- `tested_artifact` records how the session's addon was installed: `release-package` is the zip, `source-tree` is
  the checkout folder in `Interface/AddOns`. A source-tree install carries development extras (a store icon) and
  is not a packaged install, so `compare_installed` proves the shipped files match one by one instead of the proof
  claiming a packaged run that never happened.

Anything the packager does to shipped bytes beyond those two rules depends on the build (alpha versus release,
the Core pin, a localization export) and is refused rather than hashed.

The runtime graph is every TOC under the checkout, each addon's auto-loaded `Bindings.xml` and the XML script
graph it names (the client reads the file without a TOC entry, WFA-37), and the artwork. Every TOC addon
contributes, so a second addon the checkout holds (a library with its own TOC) cannot escape the identity.
Candidate keys are checkout-relative when no source-owned `move-folders` entry runs: the installed path for the
addon rooted at the checkout, and the secondary addon's own checkout path otherwise, so existing candidates keep
their exact bytes. A source-owned move installs an addon as a top-level sibling, so keys become release-relative
(`package-as/name` or `target/name`) and the digest carries a mapped domain tag; `package_candidate_digest` reads
the same keys from a package extraction and is the only supported extraction identity for that layout. An
external-only move keeps the legacy single-folder identity; its bytes are absent from the checkout and the Core pin
in `input_digest` binds them. A move whose source is neither a checkout folder nor a declared external is refused
as stale, as is a folder that is both. A moved folder needs its own `<target>.toc`, and a root TOC or Bindings
graph may not load a path the move installs in another addon. A file the TOC/XML graph loads but `.pkgmeta`
ignores is refused too: the package would not run, so it is not a package graph the proof may hash. A project
TOC's leading UTF-8 BOM and `## Interface-` lines are stripped by the packager, so a TOC carrying either is refused
instead of hashed, whether or not the policy plain-copies it. `compare_installed` stays a single-folder comparison;
a mapped checkout must use `compare_package` on the packager's release root, which also checks the declared external
addon folders without claiming their bytes.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

from . import pkgmeta, toc

PROOF = Path(".visual-proof.json")
SHA = re.compile(r"/raw/[0-9a-f]{40}/", re.IGNORECASE)
NON_RUNTIME_PREFIXES = ("docs/", ".github/", "tools/", "tests/", ".agents/", "CHANGELOG.md", "THIRD_PARTY")
ASSET_SUFFIXES = {".png", ".tga", ".blp", ".jpg", ".ttf", ".otf", ".ogg", ".mp3"}
# The packager's keyword and line-ending filter, matched case-sensitively in a bash `case`.
TEXT_SUFFIXES = (".lua", ".md", ".toc", ".txt", ".xml")
SCRIPT_SUFFIXES = {".lua", ".xml", ".toc"}
# What an installed folder may carry besides the shipped runtime; a packaged README or licence is not runtime.
INSTALLED_SUFFIXES = ASSET_SUFFIXES | SCRIPT_SUFFIXES
# Development trees the runtime asset scan never treats as addon content, and an installed source tree still holds.
NON_RUNTIME_ROOTS = frozenset({"docs", "tools", "tests", "forever-core", "node_modules"})
# `types/` holds LuaLS declarations, which no TOC loads and a source-tree install still carries. A shipped asset
# under it is real client content, so only its scripts stay out of the extras.
NON_RUNTIME_SCRIPT_ROOTS = (*NON_RUNTIME_ROOTS, "types")
TOC_BOM = b"\xef\xbb\xbf"
TOC_INTERFACE_DASH = re.compile(rb"(?m)^## Interface-")
VERSION_LINE = re.compile(rb"(?m)^## Version:[^\r\n]*")
SHIPPED_VERSION = re.compile(rb"(?m)^## Version:[^\n]*")
# The substitutions the packager changes, from release.sh's vcs_filter, lua/xml/toc filters and localization
# filter. A literal `@word@` it does not know stays in the file and is not a hazard. `@no-lib-strip@` is only
# filtered in a nolib build and `@curseforge-project-slug@` is only read, so neither is listed.
_GAME_TYPES = rb"retail|classic|vanilla|bcc|wrath|cata|mists|titan|forever"
PACKAGER_TOKEN = re.compile(
    rb"@(?:project|file)-(?:revision|hash|abbreviated-hash|author|date-iso|date-integer|timestamp|version)@"
    rb"|@build-(?:date|date-iso|date-integer|timestamp)@"
    rb"|@(?:end-)?(?:non-)?(?:alpha|debug|do-not-package)@"
    rb"|@(?:end-)?(?:non-)?(?:" + _GAME_TYPES + rb")@"
    rb"|@(?:end-)?(?:non-)?version-(?:" + _GAME_TYPES + rb")@"
    # Split so consumer gates that grep the tree for the localization keyword do not match this vendored file.
    rb"|@local"
    rb"ization[^@]*@"
)
ARTIFACTS = ("release-package", "source-tree")
# A mapped package's keys already name the release root; the tag keeps that hash from ever equalling a legacy one.
MAPPED_DOMAIN = b"forever-mapped-candidate-v1\0"


def changed_files(base: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"], capture_output=True, text=True, check=True
    )
    return [line for line in result.stdout.splitlines() if line]


def requires_proof(root: Path, paths: list[str]) -> bool:
    root = root.resolve()
    graph = {path.relative_to(root).as_posix() for path in runtime_files(root)}
    return any(
        path in graph
        or path in pkgmeta.FILES
        or path == "tools/forever-core.txt"
        or (Path(path).suffix.lower() in ASSET_SUFFIXES and not path.startswith(NON_RUNTIME_PREFIXES))
        or (path.endswith((".lua", ".xml", ".toc")) and not path.startswith(NON_RUNTIME_PREFIXES))
        for path in paths
        if path != PROOF.as_posix()
    )


def _root_file(directory: Path, name: str) -> Path | None:
    """A file at the directory's root, matched the way the Windows client matches it: exact first, then casefold."""
    exact = directory / name
    if exact.is_file():
        return exact
    matches = [path for path in directory.iterdir() if path.is_file() and path.name.casefold() == name.casefold()]
    if len(matches) > 1:
        names = ", ".join(sorted(path.name for path in matches))
        raise ValueError(f"{directory}: ambiguous case duplicates for {name}: {names}")
    return matches[0] if matches else None


def _case_dir(directory: Path, name: str) -> Path | None:
    """A folder at the directory's root, exact first, then a single case-insensitive match."""
    exact = directory / name
    if exact.is_dir():
        return exact
    if not directory.is_dir():
        return None
    matches = [path for path in directory.iterdir() if path.is_dir() and path.name.casefold() == name.casefold()]
    return matches[0] if len(matches) == 1 else None


def _casefold_problems(names) -> list[str]:
    """Release paths that collide on a case-insensitive client, where only one of them can install."""
    seen = {}
    problems = []
    for name in sorted(names):
        case = name.casefold()
        if case in seen:
            problems.append(f"{name}: case-collides with {seen[case]} in the package")
        else:
            seen[case] = name
    return problems


def runtime_files(root: Path) -> list[Path]:
    root = root.resolve()
    tocs = toc.toc_files(root)
    files = set(tocs)
    for toc_path in tocs:
        files.update(toc.loaded_files(toc_path, root))
        bindings = _root_file(toc_path.parent, "Bindings.xml")
        if bindings is not None:
            files.update(toc.xml_files(bindings, root))
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_file() and path.suffix.lower() in ASSET_SUFFIXES:
            if relative.parts[0] not in NON_RUNTIME_ROOTS and not any(part.startswith(".") for part in relative.parts):
                files.add(path)
    return sorted(files)


def _runtime_map(root: Path) -> dict[str, Path]:
    root = root.resolve()
    return {path.relative_to(root).as_posix(): path for path in runtime_files(root)}


def _excluded_runtime(files: dict[str, Path], manifest: pkgmeta.Manifest) -> list[str]:
    """Loaded Lua, XML or TOC files the package selection drops, which no installed addon can load."""
    return [
        f"{name}: .pkgmeta ignore excludes this TOC/XML-loaded runtime file from the package"
        for name in sorted(files)
        if not manifest.keeps(name) and Path(name).suffix.lower() in SCRIPT_SUFFIXES
    ]


def _script_map(root: Path, manifest: pkgmeta.Manifest | None) -> dict[str, Path]:
    """Every non-dot Lua or XML file the package selection ships, whether the TOC/XML graph loads it or not.

    The packager copies a script its policy keeps even when nothing loads it, so a release package carries it and
    the candidate must name it. Every other TOC is already a graph root, and a dot path is pruned by the packager.
    A loaded file the selection drops is a different case and stays refused by `_excluded_runtime`; a folder with
    no policy at all is an extraction, where every such script present is shipped.
    """
    root = root.resolve()
    scripts = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            path.is_file()
            and relative.suffix.lower() in (".lua", ".xml")
            and not any(part.startswith(".") for part in relative.parts)
        ):
            name = relative.as_posix()
            if manifest is None or manifest.keeps(name):
                scripts[name] = path
    return scripts


def _present_runtime(root: Path) -> dict[str, Path]:
    """Every runtime file an installed folder actually holds, without requiring its TOC graph to resolve.

    A package comparison must name a loaded file the extraction lacks as missing, not crash while reading the
    extraction's TOC. The selection is the same set a complete extraction holds: every TOC, every non-dot Lua or
    XML file, and every runtime asset outside the development roots.
    """
    root = root.resolve()
    files = {toc_path.relative_to(root).as_posix(): toc_path for toc_path in toc.toc_files(root)}
    files.update(_script_map(root, None))
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            path.is_file()
            and relative.suffix.lower() in ASSET_SUFFIXES
            and relative.parts[0] not in NON_RUNTIME_ROOTS
            and not any(part.startswith(".") for part in relative.parts)
        ):
            files[relative.as_posix()] = path
    return files


def packaged_runtime_files(root: Path) -> dict[str, Path]:
    """The runtime files a release installs at the addon's folder, keyed by their installed path.

    A checkout's `.pkgmeta` decides, with the packager's own `ignore` rules. A package extraction has no
    `.pkgmeta`, so every runtime file it holds is shipped. An ignored store asset is simply not shipped, but an
    ignored file the TOC/XML graph loads would leave a package that cannot run, so it is refused.
    """
    root = root.resolve()
    files = _runtime_map(root)
    manifest = pkgmeta.read(root)
    if manifest is not None:
        excluded = _excluded_runtime(files, manifest)
        if excluded:
            raise ValueError("; ".join(excluded))
        files = {name: path for name, path in files.items() if manifest.keeps(name)}
    files.update(_script_map(root, manifest))
    layout = manifest.layout(root) if manifest is not None else None
    if layout is not None:
        files = {name: path for name, path in files.items() if not layout.in_external_source(name)}
    if layout is not None and layout.mapped:
        mapped = {layout.release_path(name): path for name, path in files.items()}
        problems = _casefold_problems(mapped)
        if problems:
            raise ValueError("; ".join(problems))
        return mapped
    return files


def _selected_runtime(root: Path) -> dict[str, Path]:
    """The shipped runtime without refusing an excluded load: `unsupported` reports that before this is read."""
    files = _runtime_map(root)
    manifest = pkgmeta.read(root)
    if manifest is not None:
        files = {name: path for name, path in files.items() if manifest.keeps(name)}
    files.update(_script_map(root, manifest))
    return files


def _shipped_bytes(path: Path, data: bytes) -> bytes:
    if path.suffix not in TEXT_SUFFIXES:
        return data
    lines = [line[:-1] if line.endswith(b"\r") else line for line in data.split(b"\n")]
    data = b"\n".join(lines)
    return SHIPPED_VERSION.sub(b"## Version: <packager-version>", data) if path.suffix == ".toc" else data


def _digest(files: dict[str, Path], canonical, domain: bytes = b"") -> str:
    digest = hashlib.sha256()
    if domain:
        digest.update(domain)
    for name in sorted(files):
        data = canonical(files[name], files[name].read_bytes())
        key = name.encode()
        digest.update(len(key).to_bytes(4, "big"))
        digest.update(key)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def input_digest(root: Path) -> str:
    """The source identity: the runtime graph, the package's other scripts, the Core pin, TOC version aside."""
    root = root.resolve()
    files = _runtime_map(root)
    files.update(_script_map(root, pkgmeta.read(root)))
    pin = root / "tools/forever-core.txt"
    if pin.is_file():
        files["tools/forever-core.txt"] = pin
    for name in pkgmeta.FILES:
        policy = root / name
        if policy.is_file():
            files[name] = policy
    return _digest(
        files,
        lambda path, data: VERSION_LINE.sub(b"## Version: <packager-version>", data) if path.suffix == ".toc" else data,
    )


def candidate_digest(root: Path) -> str:
    """The canonical packaged runtime: what a release zip installs at the addon's folder.

    Run it on a checkout to derive the installed identity, and on a package extraction to check one. A checkout
    whose `.pkgmeta` relocates a shipped runtime file, drops one the graph loads, or carries a TOC or packager
    substitution the canonical form cannot derive raises `ValueError` instead of naming bytes it would be guessing.
    """
    root = root.resolve()
    problems = unsupported(root) + unmodeled_directives(root)
    if problems:
        raise ValueError("; ".join(problems))
    manifest = pkgmeta.read(root)
    layout = manifest.layout(root) if manifest is not None else None
    domain = MAPPED_DOMAIN if layout is not None and layout.mapped else b""
    return _digest(packaged_runtime_files(root), _shipped_bytes, domain)


def _case_duplicate_entries(release_root: Path, layout: pkgmeta.Layout) -> list[str]:
    """Top-level owned or external folder names that collide ignoring case in a package root."""
    problems = []
    if not release_root.is_dir():
        return problems
    entries = list(release_root.iterdir())
    for name in [folder for folder, _ in layout.owned] + list(layout.external):
        matches = [entry.name for entry in entries if entry.name.casefold() == name.casefold()]
        if len(matches) > 1:
            problems.append(f"{name}: duplicate case-insensitive top-level entries ({', '.join(sorted(matches))})")
    return problems


def _package_files(release_root: Path, layout: pkgmeta.Layout) -> dict[str, Path]:
    """The source-owned runtime files a release root holds, keyed by their release-relative path."""
    files = {}
    for folder, _ in layout.owned:
        directory = _case_dir(release_root, folder)
        if directory is None:
            continue
        for name, path in _present_runtime(directory).items():
            if folder == layout.package and layout.in_external_source(name):
                continue
            files[f"{folder}/{name}"] = path
    return files


def package_candidate_digest(release_root: Path, layout: pkgmeta.Layout) -> str:
    """The canonical source-owned runtime a mapped package root installs, with the mapped domain tag.

    `release_root` is the BigWigs packager's output folder: the owned release folders are hashed by their
    release-relative keys and the declared external folders are left to the Core pin. Every owned folder must be
    present, and release keys that collide ignoring case are refused. A checkout's `candidate_digest` for the same
    layout yields the same value; compare the two directly.
    """
    if not layout.mapped:
        raise ValueError("package_candidate_digest needs a source-owned move-folders layout")
    release_root = release_root.resolve()
    problems = _case_duplicate_entries(release_root, layout)
    if problems:
        raise ValueError("; ".join(problems))
    for folder, _ in layout.owned:
        if _case_dir(release_root, folder) is None:
            raise ValueError(f"{folder}: missing from the package root {release_root}")
    files = _package_files(release_root, layout)
    problems = _casefold_problems(files)
    if problems:
        raise ValueError("; ".join(problems))
    return _digest(files, _shipped_bytes, MAPPED_DOMAIN)


def _relocated_loads(root: Path, layout: pkgmeta.Layout, manifest: pkgmeta.Manifest) -> list[str]:
    """TOC or Bindings graph edges that cross into another installed addon after `move-folders` runs."""
    problems = set()
    for toc_path in toc.toc_files(root):
        relative = toc_path.relative_to(root).as_posix()
        if not manifest.keeps(relative) or layout.in_external_source(relative):
            continue
        owner = layout.release_path(relative).split("/", 1)[0]
        loaded = set(toc.loaded_files(toc_path, root))
        bindings = _root_file(toc_path.parent, "Bindings.xml")
        if bindings is not None:
            loaded.update(toc.xml_files(bindings, root))
        for path in sorted(loaded):
            name = path.relative_to(root).as_posix()
            if layout.in_external_source(name):
                continue
            release = layout.release_path(name).split("/", 1)[0]
            if release != owner:
                problems.add(
                    f"{name}: loaded by {relative}, but move-folders installs it under {release} instead of {owner}"
                )
    return sorted(problems)


def unsupported(root: Path) -> list[str]:
    """`move-folders` and package selections the candidate cannot model.

    Every move is resolved by `pkgmeta.layout`: a stale source, an unsafe path, overlapping sources, colliding
    destinations, a source that is both local and external, and a source-owned folder without its own shipped
    `<target>.toc` are refused. A mapped layout also refuses a TOC or Bindings graph that loads a path installed
    in another addon, and release keys that collide on a case-insensitive client. An external-only move is
    harmless: it installs no source-owned addon elsewhere and keeps the legacy single-folder identity.
    """
    root = root.resolve()
    manifest = pkgmeta.read(root)
    if manifest is None:
        return []
    files = _runtime_map(root)
    problems = _excluded_runtime(files, manifest)
    if manifest.moved and not manifest.package:
        problems.append(pkgmeta.MOVE_WITHOUT_PACKAGE)
        return problems
    try:
        layout = manifest.layout(root)
    except ValueError as error:
        problems.append(str(error))
        return problems
    if layout is None:
        return problems
    problems.extend(_relocated_loads(root, layout, manifest))
    if layout.mapped:
        shipped = {name for name in files if manifest.keeps(name) and not layout.in_external_source(name)}
        shipped.update(
            name for name in _script_map(root, manifest) if manifest.keeps(name) and not layout.in_external_source(name)
        )
        mapped = {layout.release_path(name): name for name in shipped}
        problems.extend(_casefold_problems(mapped))
    return problems


def unmodeled_directives(root: Path) -> list[str]:
    """Shipped runtime text files carrying a packager change this checker cannot derive.

    The candidate accounts for the line-ending filter and the TOC project version. Any other token changes the
    packaged bytes with the build type, the Core pin or a localization export, and every project TOC loses a
    leading UTF-8 BOM and its `## Interface-` lines. The proof refuses to claim an installed identity it would be
    guessing rather than hashing bytes the release changes. A `plain-copy` file gets the same refusal: the
    extraction that carries it has no policy saying so, and the supported identity must be symmetric.
    """
    root = root.resolve()
    problems = []
    for name, path in sorted(_selected_runtime(root).items()):
        if path.suffix not in TEXT_SUFFIXES:
            continue
        raw = path.read_bytes()
        if path.suffix == ".toc":
            if raw.startswith(TOC_BOM):
                problems.append(
                    f"{name}: TOC starts with a UTF-8 BOM, which the packager strips and the candidate digest "
                    "cannot model"
                )
            if TOC_INTERFACE_DASH.search(raw):
                problems.append(
                    f"{name}: TOC has a '## Interface-' line, which the packager removes and the candidate digest "
                    "cannot model"
                )
        data = _shipped_bytes(path, raw)
        for token in sorted({match.group().decode() for match in PACKAGER_TOKEN.finditer(data)}):
            problems.append(f"{name}: packager substitution {token} is not modelled by the candidate digest")
    return problems


@dataclass(frozen=True)
class Comparison:
    """A checkout's shipped runtime against an installed addon folder, file by file.

    `extra` files are present in the installed folder but not in the shipped runtime, never dropped from the
    installed side to force a match. An extra Lua, XML or TOC file has no source file the package selection ships,
    so it is client content the package does not describe and makes the two non-equivalent; an extra asset (a
    source-tree install's store icon) is reported and harmless. A script the source holds and the policy keeps is
    shipped even when nothing loads it, so it is compared byte for byte rather than reported as an extra.
    Development trees and packaged non-runtime files (a README, a licence) are not extras. Missing or differing
    shipped files also make the two non-equivalent.
    """

    equivalent: bool
    candidate: str
    missing: tuple[str, ...]
    differing: tuple[str, ...]
    extra: tuple[str, ...]


def compare_installed(source: Path, installed: Path) -> Comparison:
    """Compare a checkout's shipped runtime with one installed addon folder.

    A source-owned `move-folders` entry installs another top-level addon, which one folder cannot describe, so a
    mapped checkout is refused here and must use `compare_package` on the packager's release root. An external-only
    move installs no source-owned folder elsewhere and keeps this single-folder comparison.
    """
    source = source.resolve()
    installed = installed.resolve()
    manifest = pkgmeta.read(source)
    layout = manifest.layout(source) if manifest is not None else None
    if layout is not None and layout.mapped:
        raise ValueError(
            f"{source}: .pkgmeta move-folders installs a source-owned addon as a sibling folder; "
            "compare the release root with compare_package(source, release_root) instead"
        )
    problems = unsupported(source) + unmodeled_directives(source)
    if problems:
        raise ValueError("; ".join(problems))
    shipped = packaged_runtime_files(source)
    present = {}
    for path in installed.rglob("*"):
        relative = path.relative_to(installed)
        if (
            path.is_file()
            and relative.suffix.lower() in INSTALLED_SUFFIXES
            and relative.parts[0] not in NON_RUNTIME_ROOTS
            and not any(part.startswith(".") for part in relative.parts)
        ):
            present[relative.as_posix()] = path
    missing = tuple(sorted(set(shipped) - set(present)))
    extra = tuple(
        sorted(
            name
            for name in set(present) - set(shipped)
            if not (
                PurePosixPath(name).suffix.lower() in SCRIPT_SUFFIXES
                and name.split("/", 1)[0] in NON_RUNTIME_SCRIPT_ROOTS
            )
        )
    )
    differing = []
    for name in sorted(set(shipped) & set(present)):
        source_bytes = _shipped_bytes(shipped[name], shipped[name].read_bytes())
        installed_bytes = _shipped_bytes(present[name], present[name].read_bytes())
        if source_bytes != installed_bytes:
            differing.append(name)
    unshipped = any(PurePosixPath(name).suffix.lower() in SCRIPT_SUFFIXES for name in extra)
    return Comparison(
        not missing and not differing and not unshipped, candidate_digest(source), missing, tuple(differing), extra
    )


@dataclass(frozen=True)
class PackageComparison:
    """A mapped checkout's shipped runtime against the packager's release root, file by file.

    Every owned addon folder is walked by its release-relative key, so a missing sibling, a source-tree install
    that still nests it under the main folder, and an extra unshipped script are visible. A top-level entry outside
    the owned and external folders is `unexpected_folders`. An external folder counts only when it exists and ships
    its own `<folder>.toc`; `external_bound_by_pin` names those folders, and its bytes are deliberately not compared:
    the Core pin in `input_digest` binds the external addon, not this comparison. `external_missing` reports a
    declared external whose folder or TOC is absent. Extra assets are reported and harmless, as in a single-folder
    comparison.
    """

    equivalent: bool
    candidate: str
    missing: tuple[str, ...]
    differing: tuple[str, ...]
    extra: tuple[str, ...]
    unexpected_folders: tuple[str, ...]
    external_bound_by_pin: tuple[str, ...]
    external_missing: tuple[str, ...]


def compare_package(source: Path, release_root: Path) -> PackageComparison:
    """Compare a mapped checkout's shipped runtime with a packager release root holding every addon folder."""
    source = source.resolve()
    release_root = release_root.resolve()
    manifest = pkgmeta.read(source)
    if manifest is None:
        raise ValueError(f"{source}: no package policy; compare_package needs a mapped checkout")
    layout = manifest.layout(source)
    if layout is None or not layout.mapped:
        raise ValueError(
            f"{source}: no source-owned move-folders layout; compare one installed folder with compare_installed"
        )
    problems = unsupported(source) + unmodeled_directives(source)
    if problems:
        raise ValueError("; ".join(problems))
    duplicates = _case_duplicate_entries(release_root, layout)
    if duplicates:
        raise ValueError("; ".join(duplicates))
    shipped = packaged_runtime_files(source)
    expected = {folder.casefold() for folder, _ in layout.owned}
    expected.update(folder.casefold() for folder in layout.external)
    unexpected = ()
    if release_root.is_dir():
        unexpected = tuple(
            sorted(
                entry.name
                for entry in release_root.iterdir()
                if entry.name.casefold() not in expected and not entry.name.startswith(".")
            )
        )
    present = _package_files(release_root, layout)
    missing = tuple(sorted(set(shipped) - set(present)))
    extra = tuple(sorted(set(present) - set(shipped)))
    differing = []
    for name in sorted(set(shipped) & set(present)):
        source_bytes = _shipped_bytes(shipped[name], shipped[name].read_bytes())
        package_bytes = _shipped_bytes(present[name], present[name].read_bytes())
        if source_bytes != package_bytes:
            differing.append(name)
    external_bound = []
    external_missing = []
    for folder in layout.external:
        directory = _case_dir(release_root, folder)
        if directory is None:
            external_missing.append(f"{folder}: missing external addon folder")
        elif _root_file(directory, f"{folder}.toc") is None:
            external_missing.append(f"{folder}/{folder}.toc: missing from the external addon folder")
        else:
            external_bound.append(folder)
    unshipped = any(PurePosixPath(name).suffix.lower() in SCRIPT_SUFFIXES for name in extra)
    return PackageComparison(
        not missing and not differing and not unshipped and not unexpected and not external_missing,
        candidate_digest(source),
        missing,
        tuple(differing),
        extra,
        unexpected,
        tuple(external_bound),
        tuple(external_missing),
    )


def image_hash(url: str) -> str:
    if not SHA.search(url):
        raise ValueError(f"image URL is not pinned to a full commit SHA: {url}")
    request = Request(url, headers={"User-Agent": "forever-visual-proof"})
    with urlopen(request, timeout=20) as response:
        data = response.read()
        if response.status != 200 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(f"visual proof image is not a successful PNG: {url}")
        return hashlib.sha256(data).hexdigest()


def verify(root: Path, paths: list[str], proof_path: Path = PROOF) -> list[str]:
    root = root.resolve()
    if not requires_proof(root, paths):
        return []
    if not proof_path.is_file():
        return [f"{proof_path}: missing for runtime UI changes"]
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{proof_path}: invalid JSON: {error}"]
    if not isinstance(proof, dict):
        return [f"{proof_path}: top-level proof must be an object"]
    problems = []
    if proof.get("input_digest") != input_digest(root):
        problems.append("visual proof input_digest does not match the runtime TOC graph and Core pin")
    if not isinstance(proof.get("client_build"), str) or not proof["client_build"].strip():
        problems.append("visual proof needs client_build")
    relocations = unsupported(root)
    problems.extend(relocations)
    unmodelled = unmodeled_directives(root)
    problems.extend(unmodelled)
    manifest = pkgmeta.read(root)
    try:
        layout = manifest.layout(root) if manifest is not None else None
    except ValueError:
        layout = None
    mapped = layout is not None and layout.mapped
    if not relocations and not unmodelled and proof.get("candidate") != candidate_digest(root):
        problems.append("visual proof candidate does not match the canonical packaged runtime SHA-256")
    artifact = proof.get("tested_artifact")
    if artifact not in ARTIFACTS:
        problems.append("visual proof tested_artifact must be release-package or source-tree")
    elif mapped and artifact != "release-package":
        problems.append(
            "visual proof tested_artifact must be release-package when move-folders installs a source-owned "
            "addon as a sibling folder"
        )
    if proof.get("runtime_sha256") != proof.get("input_digest"):
        problems.append("visual proof runtime_sha256 must equal the runtime input digest")
    flows = proof.get("flows")
    if (
        not isinstance(flows, list)
        or not flows
        or any(
            not isinstance(flow, dict)
            or not isinstance(flow.get("name"), str)
            or not flow["name"].strip()
            or not isinstance(flow.get("steps"), list)
            or not flow["steps"]
            or any(not isinstance(step, str) or not step.strip() for step in flow["steps"])
            or flow.get("result") != "pass"
            for flow in flows
        )
    ):
        problems.append("visual proof needs at least one passing flow")
    images = proof.get("images")
    if not isinstance(images, list) or not images:
        problems.append("visual proof needs full-SHA image evidence")
    else:
        for image in images:
            if (
                not isinstance(image, dict)
                or not isinstance(image.get("url"), str)
                or not isinstance(image.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", image["sha256"])
            ):
                problems.append("visual proof has malformed image evidence")
                continue
            try:
                actual = image_hash(image["url"])
                if actual != image["sha256"]:
                    problems.append(f"visual proof image hash mismatch: {image['url']}")
            except (OSError, ValueError) as error:
                problems.append(str(error))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--digests", action="store_true", help="print the source and packaged runtime digests")
    parser.add_argument(
        "--compare",
        metavar="INSTALLED",
        help="compare the checkout's shipped runtime with one installed folder "
        "(extra assets are reported; extra runtime scripts fail; a mapped checkout is refused)",
    )
    parser.add_argument(
        "--compare-package",
        metavar="RELEASE_ROOT",
        help="compare a mapped checkout's shipped runtime with the packager's release root holding every addon "
        "folder (external folders are checked for their TOC, never by bytes)",
    )
    args = parser.parse_args()
    root = Path(".")
    if args.compare_package:
        try:
            package_comparison = compare_package(root, Path(args.compare_package))
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        print(json.dumps(asdict(package_comparison), indent=2))
        return 0 if package_comparison.equivalent else 1
    if args.compare:
        try:
            comparison = compare_installed(root, Path(args.compare))
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        print(json.dumps(asdict(comparison), indent=2))
        return 0 if comparison.equivalent else 1
    if args.digests:
        try:
            candidate = candidate_digest(root)
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        print(json.dumps({"input_digest": input_digest(root), "candidate": candidate}, indent=2))
        return 0
    problems = verify(root, changed_files(args.base))
    if problems:
        print("\n".join(problems))
        return 1
    print("visual proof: not required or valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
