"""Verify human-recorded in-game visual proof for runtime UI changes.

The proof separates what the checkout supplies from what a release installs:

- `input_digest` is the source identity: every runtime file the TOC graph reaches, including artwork that only the
  store uses, the Core pin and the packaging policy (`.pkgmeta` or `pkgmeta.yaml`). Any change to it, even to a
  file no package ships, or to which files the policy ships, invalidates a recorded session.
- `candidate` is the canonical packaged runtime: the same graph after the packager's selection (`.pkgmeta`'s
  `ignore` plus git's untracked and ignored files, which a release build does not ship), with the packager's
  line-ending
  filter on `*.lua`, `*.md`, `*.toc`, `*.txt` and `*.xml` and its project-version substitution in the TOC's
  `## Version:` line accounted for. This is the bytes a release zip installs at the addon's folder, and
  `candidate_digest` gives the same answer for a package extraction, which carries no `.pkgmeta`: the canonical
  form is uniform, so it never needs the checkout's policy to be reproduced. A `plain-copy` file ships raw, but
  an extraction carries nothing that says so, and line endings do not change how the client runs Lua.
- `tested_artifact` records how the session's addon was installed: `release-package` is the zip, `source-tree` is
  the checkout folder in `Interface/AddOns`. A source-tree install carries development extras (a store icon) and
  is not a packaged install, so `compare_installed` proves the shipped files match one by one instead of the proof
  claiming a packaged run that never happened.

Anything the packager does to shipped bytes beyond those two rules depends on the build (alpha versus release,
the Core pin, a localization export) and is refused rather than hashed.

The runtime graph is every TOC under the checkout, each addon's auto-loaded `Bindings.xml` and the XML script
graph it names (the client reads the file without a TOC entry, WFA-37), and the artwork. Every TOC addon
contributes, so a second addon the checkout holds (a library with its own TOC) cannot escape the identity.
Candidate keys are checkout-relative: the installed path for the addon rooted at the checkout, and the secondary
addon's own checkout path otherwise. `.pkgmeta`'s `move-folders` is not modelled: an entry that relocates a shipped
runtime file makes the candidate and the comparison refuse, naming the file, because its installed path cannot be
derived, and `move-folders` with no `package-as` is refused because its keys name a release folder the proof cannot
derive; an entry whose source the checkout does not hold (the Core external's placement) relocates no runtime
file. A file the TOC/XML graph loads but `.pkgmeta` ignores is refused too: the package would not run, so it is not
a package graph the proof may hash. A project TOC's leading UTF-8 BOM and `## Interface-` lines are stripped by the
packager, so a TOC carrying either is refused instead of hashed. The embedded Core external is not in the checkout,
and the Core pin in `input_digest` binds it.
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
    rb"|@localization[^@]*@"
)
ARTIFACTS = ("release-package", "source-tree")


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


def packaged_runtime_files(root: Path) -> dict[str, Path]:
    """The runtime files a release installs at the addon's folder, keyed by their installed path.

    A checkout's `.pkgmeta` decides, with the packager's own `ignore` rules. A package extraction has no
    `.pkgmeta`, so every runtime file it holds is shipped. An ignored store asset is simply not shipped, but an
    ignored file the TOC/XML graph loads would leave a package that cannot run, so it is refused.
    """
    root = root.resolve()
    files = _runtime_map(root)
    manifest = pkgmeta.read(root)
    if manifest is None:
        return files
    excluded = _excluded_runtime(files, manifest)
    if excluded:
        raise ValueError("; ".join(excluded))
    return {name: path for name, path in files.items() if manifest.keeps(name)}


def _selected_runtime(root: Path) -> dict[str, Path]:
    """The shipped runtime without refusing an excluded load: `unsupported` reports that before this is read."""
    files = _runtime_map(root)
    manifest = pkgmeta.read(root)
    if manifest is None:
        return files
    return {name: path for name, path in files.items() if manifest.keeps(name)}


def _shipped_bytes(path: Path, data: bytes) -> bytes:
    if path.suffix not in TEXT_SUFFIXES:
        return data
    lines = [line[:-1] if line.endswith(b"\r") else line for line in data.split(b"\n")]
    data = b"\n".join(lines)
    return SHIPPED_VERSION.sub(b"## Version: <packager-version>", data) if path.suffix == ".toc" else data


def _digest(files: dict[str, Path], canonical) -> str:
    digest = hashlib.sha256()
    for name in sorted(files):
        data = canonical(files[name], files[name].read_bytes())
        key = name.encode()
        digest.update(len(key).to_bytes(4, "big"))
        digest.update(key)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def input_digest(root: Path) -> str:
    """The source identity: the runtime graph plus the Core pin, version-stamped TOC line aside."""
    root = root.resolve()
    files = _runtime_map(root)
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
    return _digest(packaged_runtime_files(root), _shipped_bytes)


def unsupported(root: Path) -> list[str]:
    """Packaging directives the candidate cannot model, mostly `.pkgmeta`'s `move-folders`.

    A relocated shipped runtime file leaves the addon folder the proof names, so the candidate would invent a
    path the client never installs. An entry whose source the checkout does not hold (the Core external's
    placement) relocates no runtime file and is not reported. `move-folders` without `package-as` is refused
    outright: its keys are relative to a release folder the proof cannot name.
    """
    manifest = pkgmeta.read(root)
    if manifest is None:
        return []
    files = _runtime_map(root)
    problems = _excluded_runtime(files, manifest)
    if manifest.moved and not manifest.package:
        problems.append(pkgmeta.MOVE_WITHOUT_PACKAGE)
        return problems
    problems.extend(
        f"{name}: .pkgmeta move-folders relocates this shipped runtime file, which visual proof cannot model"
        for name in sorted(files)
        if manifest.keeps(name) and manifest.relocates(name)
    )
    return problems


def unmodeled_directives(root: Path) -> list[str]:
    """Shipped runtime text files carrying a packager change this checker cannot derive.

    The candidate accounts for the line-ending filter and the TOC project version. Any other token changes the
    packaged bytes with the build type, the Core pin or a localization export, and every project TOC loses a
    leading UTF-8 BOM and its `## Interface-` lines. The proof refuses to claim an installed identity it would be
    guessing rather than hashing bytes the release changes.
    """
    root = root.resolve()
    manifest = pkgmeta.read(root)
    problems = []
    for name, path in sorted(_selected_runtime(root).items()):
        if path.suffix not in TEXT_SUFFIXES or (manifest is not None and manifest.kept_bytes(name)):
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
    installed side to force a match. An extra Lua, XML or TOC file is client content the package does not
    describe, so it makes the two non-equivalent; an extra asset (a source-tree install's store icon) is reported
    and harmless. Development trees and packaged non-runtime files (a README, a licence) are not extras. Missing
    or differing shipped files also make the two non-equivalent.
    """

    equivalent: bool
    candidate: str
    missing: tuple[str, ...]
    differing: tuple[str, ...]
    extra: tuple[str, ...]


def compare_installed(source: Path, installed: Path) -> Comparison:
    """Compare a checkout's shipped runtime with an installed addon folder."""
    source = source.resolve()
    installed = installed.resolve()
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
    if not relocations and not unmodelled and proof.get("candidate") != candidate_digest(root):
        problems.append("visual proof candidate does not match the canonical packaged runtime SHA-256")
    if proof.get("tested_artifact") not in ARTIFACTS:
        problems.append("visual proof tested_artifact must be release-package or source-tree")
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
        help="compare the checkout's shipped runtime with an installed folder "
        "(extra assets are reported; extra runtime scripts fail)",
    )
    args = parser.parse_args()
    root = Path(".")
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
