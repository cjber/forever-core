"""Verify the in-game visual proof a runtime UI change carries.

The proof is `.visual-proof.json`: the flows checked in the WoW: Forever client with the candidate build installed,
their screenshots at full-SHA gist URLs (the same images the pull request shows) with each image's sha256, and the
digests below that bind them to the exact runtime the session loaded. A flow's `steps` is the slash command it typed,
or a Lua snippet by file name and sha256: a caller's absolute path names a machine and a scratch folder that is gone
with the session. A proof this change records or rewrites may not carry an absolute `.lua` step (#591).

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

`checks` is what the release smoke would have found on that same session: the `/forever selftest` surfaces and the
ones that failed, each linked addon folder's Lua error count, and the released addons a core proof links beside it
that never registered. `verify` fails a proof whose checks failed; `proof_problems(..., release=True)` also requires
them, so a release takes a proof whose contents match its commit in place of a `headless-smoke` status. The TOC
`## Version:` line is outside both digests, so a release preparation's version bump keeps the proof valid.

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
addon folders without claiming their bytes. An addon that embeds core (`## X-Forever-Core-Embed: 1`) installs the
embed step's output, so the proof compares the installed folder with the checkout's tracked files after
that same step using the ForeverCore source supplied with `--core`. The comparison reports the checkout candidate
for proof verification and an embedded candidate that hashes the core files actually installed.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.request import Request, urlopen

from . import core_archive, core_pin, embed, pkgmeta, toc

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
EMBEDDED_BUNDLE = embed.PREFIX + "bundle.json"
EMBEDDED_SHIMS = frozenset({embed.HOST_BEGIN, embed.HOST_RUN, embed.READY})
BEGIN_STAMP = re.compile(
    r'host\.ForeverCoreCopy = ForeverCoreLoader\.Begin\(addon, ([0-9]+), "([0-9a-f]{64})"(?:, [1-9][0-9]*)?\)'
)
HEX64 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class _EmbeddedBuild:
    folder: str
    version: str
    source_digest: str
    saved_variable: str
    root_toc: str
    toc_bytes: bytes
    wrapped: frozenset[str]
    manifest: dict


def _is_embedded_path(name: str) -> bool:
    return name.startswith(embed.PREFIX) or name in EMBEDDED_SHIMS


def _has_embedded_artifacts(root: Path) -> bool:
    return (root / embed.PREFIX).exists() or any((root / name).exists() for name in EMBEDDED_SHIMS)


def _unwrap_host_chunk(data: bytes) -> bytes | None:
    """Strip `embed.wrap`'s exact host-chunk wrapper from LF-normalised Lua bytes; None when not wrapped."""
    bom = data.startswith(embed.BOM)
    body = data[len(embed.BOM) :] if bom else data
    if (
        len(body) >= len(embed.HEADER) + len(embed.FOOTER)
        and body.startswith(embed.HEADER)
        and body.endswith(embed.FOOTER)
    ):
        return (embed.BOM if bom else b"") + body[len(embed.HEADER) : -len(embed.FOOTER)]
    return None


def _expected_core_loads(source_order: list[str]) -> list[str]:
    return [
        embed.PREFIX + source_order[0],
        embed.PREFIX + "Begin.lua",
        *(embed.PREFIX + name for name in source_order[1:]),
        embed.PREFIX + "End.lua",
    ]


def _canonical_embedded_source_toc(toc_bytes: bytes) -> bytes:
    """Canonical consumer TOC bytes matching `embed.transform`'s formatting."""
    text = toc_bytes.decode("utf-8")
    headers = [line for line in text.splitlines() if line.startswith("##")]
    loads = embed._loads(text)
    return ("\n".join(headers) + "\n\n" + "\n".join(name.replace("/", "\\") for name in loads) + "\n").encode("utf-8")


def _unwrap_embedded_toc(toc_bytes: bytes, source_order: list[str]) -> tuple[bytes, list[str]]:
    """Strip the core and host load entries `embed.transform` adds around the consumer's TOC loads."""
    text = toc_bytes.decode("utf-8")
    headers = [line for line in text.splitlines() if line.startswith("##")]
    order = embed._loads(text)
    rebuilt = "\n".join(headers) + "\n\n" + "\n".join(name.replace("/", "\\") for name in order) + "\n"
    if rebuilt != text:
        raise ValueError("embedded TOC does not match embed.transform formatting")
    prefix = [*_expected_core_loads(source_order), embed.HOST_BEGIN]
    suffix = [embed.HOST_RUN, embed.READY]
    if len(order) < len(prefix) + len(suffix) or order[: len(prefix)] != prefix or order[-len(suffix) :] != suffix:
        raise ValueError("embedded TOC load order disagrees with bundle.json")
    consumer_loads = order[len(prefix) : -len(suffix)]
    canonical = (
        "\n".join(headers) + "\n\n" + "\n".join(name.replace("/", "\\") for name in consumer_loads) + "\n"
    ).encode("utf-8")
    return canonical, consumer_loads


def _parse_bundle_manifest(root: Path) -> dict:
    bundle_path = root / EMBEDDED_BUNDLE
    try:
        manifest = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{EMBEDDED_BUNDLE}: invalid JSON ({error})") from None
    if not isinstance(manifest, dict):
        raise ValueError(f"{EMBEDDED_BUNDLE}: must be a JSON object")
    if manifest.get("schema") != 1 or manifest.get("standalone") is not False:
        raise ValueError(f"{EMBEDDED_BUNDLE}: invalid embedded bundle schema")
    version = manifest.get("version")
    if not isinstance(version, str):
        raise ValueError(f"{EMBEDDED_BUNDLE}: missing version")
    major, minor, patch = core_archive.version(version)
    build = major * 1000000 + minor * 1000 + patch
    digest = manifest.get("source_digest")
    if (
        minor >= 1000
        or patch >= 1000
        or manifest.get("build") != build
        or not isinstance(digest, str)
        or not HEX64.fullmatch(digest)
    ):
        raise ValueError(f"{EMBEDDED_BUNDLE}: invalid version, build or source_digest")
    folder = manifest.get("folder")
    saved_variable = manifest.get("saved_variable")
    if not all(
        isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value) for value in (folder, saved_variable)
    ):
        raise ValueError(f"{EMBEDDED_BUNDLE}: invalid folder or saved_variable")
    source_order = manifest.get("source_order")
    if (
        not isinstance(source_order, list)
        or not source_order
        or not all(isinstance(item, str) and item for item in source_order)
    ):
        raise ValueError(f"{EMBEDDED_BUNDLE}: invalid source_order")
    wrapped = manifest.get("wrapped")
    if not isinstance(wrapped, list) or not all(isinstance(item, str) and item for item in wrapped):
        raise ValueError(f"{EMBEDDED_BUNDLE}: invalid wrapped file list")
    files = manifest.get("files")
    if (
        not isinstance(files, dict)
        or not files
        or not all(isinstance(k, str) and isinstance(v, str) and HEX64.fullmatch(v) for k, v in files.items())
    ):
        raise ValueError(f"{EMBEDDED_BUNDLE}: invalid files hash map")
    for name in files:
        if name == EMBEDDED_BUNDLE or (name != embed.READY and not name.startswith(embed.PREFIX)):
            raise ValueError(f"{EMBEDDED_BUNDLE}: unexpected file entry {name}")
    required = {
        embed.READY,
        embed.PREFIX + "Begin.lua",
        embed.PREFIX + "End.lua",
        *(embed.PREFIX + item for item in source_order),
    }
    if any(
        PurePosixPath(name).as_posix() != name or ".." in PurePosixPath(name).parts or "\\" in name for name in files
    ):
        raise ValueError(f"{EMBEDDED_BUNDLE}: invalid embedded file path")
    if not required.issubset(files):
        raise ValueError(f"{EMBEDDED_BUNDLE}: missing required embedded core entries")
    return manifest


def _matches_bundle_hash(name: str, data: bytes, expected_sha: str) -> bool:
    if hashlib.sha256(data).hexdigest() == expected_sha:
        return True
    if Path(name).suffix in TEXT_SUFFIXES:
        return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest() == expected_sha
    return False


def _verify_embedded_files(
    root: Path, manifest: dict, expected_wrapped: list[str], *, core: Path | None = None
) -> tuple[set[str], set[str], set[str]]:
    """Compare embedded core files and host shims in `root` against `manifest` (or a `core` checkout)."""
    missing: set[str] = set()
    differing: set[str] = set()
    extra: set[str] = set()

    begin_name = embed.PREFIX + "Begin.lua"
    begin_path = root / begin_name
    if begin_path.is_file():
        try:
            begin_text = begin_path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            differing.add(begin_name)
        else:
            stamped = [match.groups() for match in map(BEGIN_STAMP.fullmatch, begin_text.splitlines()) if match]
            if stamped != [(str(manifest["build"]), manifest["source_digest"])]:
                differing.add(begin_name)

    prefix_root = root / embed.PREFIX
    actual_files: dict[str, Path] = {}
    if prefix_root.is_dir():
        for path in prefix_root.rglob("*"):
            if path.is_file():
                name = path.relative_to(root).as_posix()
                if name != EMBEDDED_BUNDLE:
                    actual_files[name] = path
    ready_path = root / embed.READY
    if ready_path.is_file():
        actual_files[embed.READY] = ready_path

    if core is not None:
        builder = embed._builder(core)
        planned = builder.plan(core, manifest["folder"], manifest["version"], manifest["saved_variable"], b"")
        planned_manifest = json.loads(planned[EMBEDDED_BUNDLE])
        if (
            manifest["source_digest"] != planned_manifest["source_digest"]
            or manifest["source_order"] != planned_manifest["source_order"]
        ):
            differing.add(EMBEDDED_BUNDLE)
        expected_bytes = {
            name: data
            for name, data in planned.items()
            if (name.startswith(embed.PREFIX) and name != EMBEDDED_BUNDLE) or name == embed.READY
        }
        if manifest["files"] != {name: hashlib.sha256(data).hexdigest() for name, data in expected_bytes.items()}:
            differing.add(EMBEDDED_BUNDLE)
        missing |= set(expected_bytes) - set(actual_files)
        extra |= set(actual_files) - set(expected_bytes)
        for name in set(expected_bytes) & set(actual_files):
            path = actual_files[name]
            if _shipped_bytes(path, path.read_bytes()) != _shipped_bytes(path, expected_bytes[name]):
                differing.add(name)
    else:
        expected_hashes = manifest["files"]
        missing |= set(expected_hashes) - set(actual_files)
        extra |= set(actual_files) - set(expected_hashes)
        for name in set(expected_hashes) & set(actual_files):
            if not _matches_bundle_hash(name, actual_files[name].read_bytes(), expected_hashes[name]):
                differing.add(name)

    expected_shims = {
        embed.HOST_BEGIN: embed.BEGIN_SOURCE,
        embed.HOST_RUN: embed.RUN_SOURCE.replace(b"__WRAPPED__", str(len(expected_wrapped)).encode()),
    }
    for name, expected_data in expected_shims.items():
        path = root / name
        if not path.is_file():
            missing.add(name)
        elif _shipped_bytes(path, path.read_bytes()) != _shipped_bytes(path, expected_data):
            differing.add(name)

    return missing, differing, extra


def _read_embedded_build(root: Path) -> _EmbeddedBuild | None:
    """Validate and unwrap an embedded-core build folder; None when `root` has no embedded copy."""
    root = root.resolve()
    if not (root / EMBEDDED_BUNDLE).is_file():
        if _has_embedded_artifacts(root):
            raise ValueError(f"{EMBEDDED_BUNDLE}: missing for embedded ForeverCore")
        return None
    manifest = _parse_bundle_manifest(root)
    missing, differing, extra = _verify_embedded_files(root, manifest, manifest["wrapped"])
    problems = [
        *(f"{name}: missing from embedded ForeverCore" for name in sorted(missing)),
        *(f"{name}: disagrees with embedded ForeverCore bundle" for name in sorted(differing)),
        *(f"{name}: unexpected file in embedded ForeverCore" for name in sorted(extra)),
    ]
    if problems:
        raise ValueError("; ".join(problems))
    toc_name = f"{manifest['folder']}.toc"
    toc_path = root / toc_name
    if not toc_path.is_file():
        raise ValueError(f"{toc_name}: missing root TOC for embedded ForeverCore")
    other_tocs = sorted(path.name for path in root.glob("*.toc") if path.name != toc_name)
    if other_tocs:
        raise ValueError(f"{toc_name}: unexpected sibling root TOCs: {', '.join(other_tocs)}")
    raw_toc = toc_path.read_bytes()
    if not core_pin.embeds(raw_toc):
        raise ValueError(f"{toc_name}: embedded ForeverCore present without ## {embed.EMBED_FIELD}: 1")
    fields = core_pin.toc_fields(raw_toc)
    saved = [item.strip() for item in fields.get("savedvariables", "").split(",") if item.strip()]
    if saved != [manifest["saved_variable"]]:
        raise ValueError(f"{toc_name}: ## SavedVariables disagrees with {EMBEDDED_BUNDLE}")
    try:
        toc_bytes, consumer_loads = _unwrap_embedded_toc(_shipped_bytes(toc_path, raw_toc), manifest["source_order"])
    except ValueError as error:
        raise ValueError(f"{toc_name}: {error}") from None
    try:
        actual_wrapped = embed._lua_graph(root, consumer_loads)
    except embed.EmbedError as error:
        raise ValueError(f"{toc_name}: {error}") from None
    if actual_wrapped != manifest["wrapped"]:
        raise ValueError(f"{EMBEDDED_BUNDLE}: wrapped file list disagrees with {toc_name} load graph")
    for name in manifest["wrapped"]:
        path = root / name
        if _unwrap_host_chunk(_shipped_bytes(path, path.read_bytes())) is None:
            raise ValueError(f"{name}: missing expected ForeverCoreHostChunk wrapper")
    return _EmbeddedBuild(
        folder=manifest["folder"],
        version=manifest["version"],
        source_digest=manifest["source_digest"],
        saved_variable=manifest["saved_variable"],
        root_toc=toc_name,
        toc_bytes=toc_bytes,
        wrapped=frozenset(manifest["wrapped"]),
        manifest=manifest,
    )


def _source_embed_info(source: Path) -> tuple[str, str, str, list[str], str | None] | None:
    """Return `(toc_name, folder, saved_variable, wrapped_lua, pin)` when `source` opts into embedding."""
    try:
        toc_path = embed._toc_path(source)
    except embed.EmbedError:
        return None
    toc_text = toc_path.read_text(encoding="utf-8-sig")
    if not core_pin.embeds(toc_text):
        return None
    if any(path.name != toc_path.name for path in source.glob("*.toc")):
        return None
    fields = core_pin.toc_fields(toc_text)
    saved = [item.strip() for item in fields.get("savedvariables", "").split(",") if item.strip()]
    if len(saved) != 1:
        return None
    try:
        wrapped = embed._lua_graph(source, embed._loads(toc_text))
    except embed.EmbedError:
        return None
    pin_file = source / embed.PIN_PATH
    pin = pin_file.read_text(encoding="utf-8").strip() if pin_file.is_file() else None
    return toc_path.name, toc_path.stem, saved[0], wrapped, pin


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
        f"{name}: {manifest.exclusion_reason(name)} excludes this TOC/XML-loaded runtime file from the package"
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


def packaged_runtime_files(root: Path, *, embedded: _EmbeddedBuild | None = None) -> dict[str, Path]:
    """The runtime files a release installs at the addon's folder, keyed by their installed path.

    A checkout's `.pkgmeta` decides, with the packager's own `ignore` rules. A package extraction has no
    `.pkgmeta`, so every runtime file it holds is shipped. An ignored store asset is simply not shipped, but an
    ignored file the TOC/XML graph loads would leave a package that cannot run, so it is refused.
    """
    root = root.resolve()
    if embedded is None:
        embedded = _read_embedded_build(root)
    files = _runtime_map(root)
    manifest = pkgmeta.read(root)
    if manifest is not None:
        excluded = _excluded_runtime(files, manifest)
        if excluded:
            raise ValueError("; ".join(excluded))
        files = {name: path for name, path in files.items() if manifest.keeps(name)}
    files.update(_script_map(root, manifest))
    if embedded is not None:
        files = {name: path for name, path in files.items() if not _is_embedded_path(name)}
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


def _selected_runtime(root: Path, *, embedded: _EmbeddedBuild | None = None) -> dict[str, Path]:
    """The shipped runtime without refusing an excluded load: `unsupported` reports that before this is read."""
    files = _runtime_map(root)
    manifest = pkgmeta.read(root)
    if manifest is not None:
        files = {name: path for name, path in files.items() if manifest.keeps(name)}
    files.update(_script_map(root, manifest))
    if embedded is not None:
        files = {name: path for name, path in files.items() if not _is_embedded_path(name)}
    return files


def _shipped_bytes(path: Path, data: bytes) -> bytes:
    if path.suffix not in TEXT_SUFFIXES:
        return data
    lines = [line[:-1] if line.endswith(b"\r") else line for line in data.split(b"\n")]
    data = b"\n".join(lines)
    return SHIPPED_VERSION.sub(b"## Version: <packager-version>", data) if path.suffix == ".toc" else data


def _canonical_bytes(
    name: str,
    path: Path,
    data: bytes,
    *,
    embedded: _EmbeddedBuild | None = None,
    embedded_prefix: str = "",
) -> bytes:
    data = _shipped_bytes(path, data)
    if embedded is not None:
        local = name[len(embedded_prefix) :] if embedded_prefix and name.startswith(embedded_prefix) else name
        if not embedded_prefix or name.startswith(embedded_prefix):
            if local == embedded.root_toc:
                return embedded.toc_bytes
            if local in embedded.wrapped:
                unwrapped = _unwrap_host_chunk(data)
                if unwrapped is None:
                    raise ValueError(f"{name}: missing expected ForeverCoreHostChunk wrapper")
                return unwrapped
        return data
    if path.suffix == ".toc" and core_pin.embeds(data):
        return _canonical_embedded_source_toc(data)
    return data


def _digest(files: dict[str, Path], canonical, domain: bytes = b"") -> str:
    digest = hashlib.sha256()
    if domain:
        digest.update(domain)
    for name in sorted(files):
        data = canonical(name, files[name], files[name].read_bytes())
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
        lambda _name, path, data: (
            VERSION_LINE.sub(b"## Version: <packager-version>", data) if path.suffix == ".toc" else data
        ),
    )


def candidate_digest(root: Path) -> str:
    """The canonical packaged runtime: what a release zip installs at the addon's folder.

    For an embedded extraction the digest also includes its bundle files. The checkout digest describes consumer
    inputs, with the Core pin tracked by `input_digest`. A checkout
    whose `.pkgmeta` relocates a shipped runtime file, drops one the graph loads, or carries a TOC or packager
    substitution the canonical form cannot derive raises `ValueError` instead of naming bytes it would be guessing.
    """
    root = root.resolve()
    embedded = _read_embedded_build(root)
    problems = unsupported(root) + unmodeled_directives(root, embedded=embedded)
    if problems:
        raise ValueError("; ".join(problems))
    manifest = pkgmeta.read(root)
    layout = manifest.layout(root) if manifest is not None else None
    domain = MAPPED_DOMAIN if layout is not None and layout.mapped else b""
    files = packaged_runtime_files(root, embedded=embedded)
    if embedded is not None:
        files.update({name: root / name for name in embedded.manifest["files"]})
    return _digest(
        files,
        lambda name, path, data: _canonical_bytes(name, path, data, embedded=embedded),
        domain,
    )


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
    main_dir = _case_dir(release_root, layout.package)
    embedded = _read_embedded_build(main_dir) if main_dir is not None else None
    prefix = f"{layout.package}/"
    files = _package_files(release_root, layout)
    if embedded is not None:
        files = {
            name: path
            for name, path in files.items()
            if not (name.startswith(prefix) and _is_embedded_path(name[len(prefix) :]))
        }
        files.update({f"{prefix}{name}": main_dir / name for name in embedded.manifest["files"]})
    problems = _casefold_problems(files)
    if problems:
        raise ValueError("; ".join(problems))
    return _digest(
        files,
        lambda name, path, data: _canonical_bytes(name, path, data, embedded=embedded, embedded_prefix=prefix),
        MAPPED_DOMAIN,
    )


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


def unmodeled_directives(root: Path, *, embedded: _EmbeddedBuild | None = None) -> list[str]:
    """Shipped runtime text files carrying a packager change this checker cannot derive.

    The candidate accounts for the line-ending filter and the TOC project version. Any other token changes the
    packaged bytes with the build type, the Core pin or a localization export, and every project TOC loses a
    leading UTF-8 BOM and its `## Interface-` lines. The proof refuses to claim an installed identity it would be
    guessing rather than hashing bytes the release changes. A `plain-copy` file gets the same refusal: the
    extraction that carries it has no policy saying so, and the supported identity must be symmetric.
    """
    root = root.resolve()
    problems = []
    for name, path in sorted(_selected_runtime(root, embedded=embedded).items()):
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
        data = _canonical_bytes(name, path, raw, embedded=embedded)
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
    shipped files also make the two non-equivalent. When the installed folder carries an embedded ForeverCore copy,
    `embedded_core` reports its version, source digest and embedded candidate on a match.
    """

    equivalent: bool
    candidate: str
    missing: tuple[str, ...]
    differing: tuple[str, ...]
    extra: tuple[str, ...]
    embedded_core: dict[str, str] | None = None


def _compare_embedded_folder(
    source: Path,
    installed: Path,
    shipped_local: dict[str, Path],
    present_local: dict[str, Path],
    *,
    core: Path | None = None,
) -> tuple[set[str], set[str], set[str], set[str], dict[str, str] | None] | None:
    """Compare one embedded-core build folder against `source`; None when standard comparison should run."""
    if not _has_embedded_artifacts(installed):
        return None
    source_embed = _source_embed_info(source)
    if source_embed is None:
        return set(), {EMBEDDED_BUNDLE}, set(), set(), None
    toc_name, folder, saved_variable, expected_wrapped, source_pin = source_embed
    try:
        manifest = _parse_bundle_manifest(installed)
    except ValueError:
        return set(), {EMBEDDED_BUNDLE}, set(), set(), None
    embedded_core = {"version": manifest["version"], "source_digest": manifest["source_digest"]}
    emb_missing, emb_differing, emb_extra = _verify_embedded_files(installed, manifest, expected_wrapped, core=core)
    if (
        manifest["folder"] != folder
        or manifest["saved_variable"] != saved_variable
        or manifest["wrapped"] != expected_wrapped
    ):
        emb_differing.add(EMBEDDED_BUNDLE)
    if source_pin is not None and core_archive.tag(manifest["version"]) != source_pin:
        emb_differing.add(EMBEDDED_BUNDLE)

    present_consumer = {name: path for name, path in present_local.items() if not _is_embedded_path(name)}
    consumer_missing = set(shipped_local) - set(present_consumer)
    consumer_extra = {
        name
        for name in set(present_consumer) - set(shipped_local)
        if not (
            PurePosixPath(name).suffix.lower() in SCRIPT_SUFFIXES and name.split("/", 1)[0] in NON_RUNTIME_SCRIPT_ROOTS
        )
    }
    wrapped_set = set(expected_wrapped)
    consumer_differing: set[str] = set()
    for name in sorted(set(shipped_local) & set(present_consumer)):
        source_bytes = _shipped_bytes(shipped_local[name], shipped_local[name].read_bytes())
        installed_bytes = _shipped_bytes(present_consumer[name], present_consumer[name].read_bytes())
        if name == toc_name:
            expected_toc = _canonical_embedded_source_toc(source_bytes)
            try:
                actual_toc, _ = _unwrap_embedded_toc(installed_bytes, manifest["source_order"])
            except ValueError:
                consumer_differing.add(name)
            else:
                if actual_toc != expected_toc:
                    consumer_differing.add(name)
        elif name in wrapped_set:
            unwrapped = _unwrap_host_chunk(installed_bytes)
            if unwrapped is None or unwrapped != source_bytes:
                consumer_differing.add(name)
        elif source_bytes != installed_bytes:
            consumer_differing.add(name)
    if not (consumer_missing or consumer_differing or emb_missing or emb_differing or emb_extra) and not any(
        PurePosixPath(name).suffix.lower() in SCRIPT_SUFFIXES for name in consumer_extra
    ):
        if core is None:
            raise ValueError("embedded ForeverCore comparison needs --core pointing to the source used to build it")
        embedded_core["candidate"] = candidate_digest(installed)
    return (
        consumer_missing | emb_missing,
        consumer_differing | emb_differing,
        consumer_extra,
        emb_extra,
        embedded_core,
    )


def compare_installed(source: Path, installed: Path, *, core: Path | None = None) -> Comparison:
    """Compare a checkout's shipped runtime with one installed addon folder.

    A source-owned `move-folders` entry installs another top-level addon, which one folder cannot describe, so a
    mapped checkout is refused here and must use `compare_package` on the packager's release root. An external-only
    move installs no source-owned folder elsewhere and keeps this single-folder comparison. When `installed` embeds
    ForeverCore (`Libs/ForeverCore/bundle.json`), the host-chunk wrappers and rewritten root TOC are unwrapped with
    `embed`'s exact constants and the embedded core files are verified against the `core` source used by the build.
    """
    source = source.resolve()
    installed = installed.resolve()
    if core is not None:
        core = core.resolve()
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
    embedded_result = _compare_embedded_folder(source, installed, shipped, present, core=core)
    if embedded_result is not None:
        missing_set, differing_set, consumer_extra, emb_extra, embedded_core = embedded_result
        missing = tuple(sorted(missing_set))
        differing = tuple(sorted(differing_set))
        extra = tuple(sorted(consumer_extra | emb_extra))
        unshipped = any(PurePosixPath(name).suffix.lower() in SCRIPT_SUFFIXES for name in consumer_extra)
        return Comparison(
            not missing and not differing and not unshipped and not emb_extra,
            candidate_digest(source),
            missing,
            differing,
            extra,
            embedded_core,
        )
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
    differing_list = []
    for name in sorted(set(shipped) & set(present)):
        source_bytes = _shipped_bytes(shipped[name], shipped[name].read_bytes())
        installed_bytes = _shipped_bytes(present[name], present[name].read_bytes())
        if source_bytes != installed_bytes:
            differing_list.append(name)
    unshipped = any(PurePosixPath(name).suffix.lower() in SCRIPT_SUFFIXES for name in extra)
    return Comparison(
        not missing and not differing_list and not unshipped,
        candidate_digest(source),
        missing,
        tuple(differing_list),
        extra,
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
    embedded_core: dict[str, str] | None = None


def compare_package(source: Path, release_root: Path, *, core: Path | None = None) -> PackageComparison:
    """Compare a mapped checkout's shipped runtime with a packager release root holding every addon folder."""
    source = source.resolve()
    release_root = release_root.resolve()
    if core is not None:
        core = core.resolve()
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
    prefix = f"{layout.package}/"
    main_dir = _case_dir(release_root, layout.package)
    embedded_result = None
    if main_dir is not None:
        main_shipped = {name[len(prefix) :]: path for name, path in shipped.items() if name.startswith(prefix)}
        main_present = {name[len(prefix) :]: path for name, path in present.items() if name.startswith(prefix)}
        embedded_result = _compare_embedded_folder(source, main_dir, main_shipped, main_present, core=core)
    if embedded_result is not None:
        emb_missing, emb_differing, main_extra, emb_extra, embedded_core = embedded_result
        other_shipped = {name: path for name, path in shipped.items() if not name.startswith(prefix)}
        other_present = {name: path for name, path in present.items() if not name.startswith(prefix)}
        missing_set = {f"{prefix}{name}" for name in emb_missing} | (set(other_shipped) - set(other_present))
        consumer_extra = {f"{prefix}{name}" for name in main_extra} | (set(other_present) - set(other_shipped))
        emb_extra_prefixed = {f"{prefix}{name}" for name in emb_extra}
        differing_set = {f"{prefix}{name}" for name in emb_differing}
        for name in sorted(set(other_shipped) & set(other_present)):
            if _shipped_bytes(other_shipped[name], other_shipped[name].read_bytes()) != _shipped_bytes(
                other_present[name], other_present[name].read_bytes()
            ):
                differing_set.add(name)
        missing = tuple(sorted(missing_set))
        differing = tuple(sorted(differing_set))
        extra = tuple(sorted(consumer_extra | emb_extra_prefixed))
        unshipped = any(PurePosixPath(name).suffix.lower() in SCRIPT_SUFFIXES for name in consumer_extra)
        has_emb_extra = bool(emb_extra_prefixed)
    else:
        embedded_core = None
        missing = tuple(sorted(set(shipped) - set(present)))
        extra = tuple(sorted(set(present) - set(shipped)))
        differing_list = []
        for name in sorted(set(shipped) & set(present)):
            source_bytes = _shipped_bytes(shipped[name], shipped[name].read_bytes())
            package_bytes = _shipped_bytes(present[name], present[name].read_bytes())
            if source_bytes != package_bytes:
                differing_list.append(name)
        differing = tuple(differing_list)
        unshipped = any(PurePosixPath(name).suffix.lower() in SCRIPT_SUFFIXES for name in extra)
        has_emb_extra = False
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
    return PackageComparison(
        not missing
        and not differing
        and not unshipped
        and not has_emb_extra
        and not unexpected
        and not external_missing,
        candidate_digest(source),
        missing,
        differing,
        extra,
        unexpected,
        tuple(external_bound),
        tuple(external_missing),
        embedded_core,
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


def absolute_lua_step(step: str) -> bool:
    """Whether a recorded step is a Lua flow named by an absolute path, which a public proof may not carry (#591).

    A step is normally a Forever addon's slash command, which also starts with "/", so only a `.lua` step is a file.
    """
    # Accept both the digest-first format and existing name-first proofs.
    step = re.sub(r"^sha256:[0-9a-f]{64}\s+|\s+sha256:[0-9a-f]{64}$", "", step)
    if not step.endswith(".lua"):
        return False
    return PurePosixPath(step).is_absolute() or PureWindowsPath(step).is_absolute()


def checks_problems(checks: object, *, required: bool) -> list[str]:
    """Why the proof's in-game checks do not pass: the selftest, the Lua errors and the released addons' startup.

    The recorder runs the smoke's checks on the session it captured and records them as `checks`: the
    selftest's surface count and the ones that failed, each addon folder's Lua error count over the whole job, and the
    released addons (a core proof) that never registered. A proof without them (a checklist attestation, or one
    recorded before the checks existed) still proves the flows it shows, so only a release requires them.
    """
    if checks is None and not required:
        return []
    if not isinstance(checks, dict):
        return ["visual proof needs its recorded in-game checks (selftest and Lua errors)"]
    problems = []
    selftest = checks.get("selftest")
    if (
        not isinstance(selftest, dict)
        or not isinstance(selftest.get("surfaces"), int)
        or selftest["surfaces"] < 1
        or not isinstance(selftest.get("failed"), list)
    ):
        problems.append("visual proof checks need a selftest record with its surfaces and failures")
    elif selftest["failed"]:
        problems.append(f"visual proof selftest failed: {', '.join(map(str, selftest['failed']))}")
    errors = checks.get("errors")
    if (
        not isinstance(errors, dict)
        or not errors
        or any(not isinstance(count, int) or isinstance(count, bool) or count < 0 for count in errors.values())
    ):
        problems.append("visual proof checks need a Lua error count per addon folder")
    elif any(errors.values()):
        named = ", ".join(f"{count} {name}" for name, count in errors.items() if count)
        problems.append(f"visual proof recorded Lua errors: {named}")
    not_started = checks.get("not_started")
    if not isinstance(not_started, list):
        problems.append("visual proof checks need the list of released addons that did not start")
    elif not_started:
        problems.append(f"visual proof recorded addons that did not start: {', '.join(map(str, not_started))}")
    return problems


def verify(root: Path, paths: list[str], proof_path: Path = PROOF) -> list[str]:
    """Why a change's proof does not hold, when the changed paths reach the runtime; none when they do not."""
    root = root.resolve()
    if not requires_proof(root, paths):
        return []
    if not proof_path.is_file():
        return [f"{proof_path}: missing for runtime UI changes"]
    return proof_problems(root, proof_path, rewritten=PROOF.as_posix() in paths)


def proof_problems(
    root: Path, proof_path: Path = PROOF, *, rewritten: bool = False, release: bool = False
) -> list[str]:
    """Why the proof at `proof_path` does not prove the runtime at `root`; none when it does.

    The proof is bound to file contents, not to a commit, so a proof recorded on a pull request's head still holds for
    its squash-merge commit and for a release preparation that only bumps the TOC version and the changelog.
    `rewritten` is a change that records or rewrites the proof, which may not carry an absolute Lua step (#591).
    `release` requires the in-game checks, which stand in for the `headless-smoke` status at that commit.
    """
    root = root.resolve()
    if not proof_path.is_file():
        return [f"{proof_path}: missing"]
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
    problems.extend(checks_problems(proof.get("checks"), required=release))
    if rewritten and isinstance(flows, list):
        # A proof recorded before #591 can still name a Lua flow by the caller's absolute path. It stays valid until
        # it is re-recorded, because a runtime change requires a fresh proof anyway while a version bump only
        # revalidates the same one. A proof this change records or rewrites may not carry that path.
        absolute = sorted(
            {
                step
                for flow in flows
                if isinstance(flow, dict) and isinstance(flow.get("steps"), list)
                for step in flow["steps"]
                if isinstance(step, str) and absolute_lua_step(step)
            }
        )
        if absolute:
            problems.append(
                "visual proof may not record a Lua flow by an absolute path; "
                "use sha256:<digest> followed by its file name: " + ", ".join(absolute)
            )
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
    parser.add_argument(
        "--core",
        metavar="CORE_DIR",
        type=Path,
        help="ForeverCore source used to produce the embedded build, required for a matching comparison",
    )
    args = parser.parse_args()
    root = Path(".")
    if args.compare_package:
        try:
            package_comparison = compare_package(root, Path(args.compare_package), core=args.core)
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        print(json.dumps(asdict(package_comparison), indent=2))
        return 0 if package_comparison.equivalent else 1
    if args.compare:
        try:
            comparison = compare_installed(root, Path(args.compare), core=args.core)
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
