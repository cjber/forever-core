"""The files a checkout's `.pkgmeta` ships to the package, using the BigWigs packager's own selection rules.

`release.sh` turns every `ignore` and `plain-copy` list item into one or more shell globs and matches them with
bash's `case` against the checkout-relative path (so `*` crosses `/`): an item naming a directory becomes
`<item>/*`, one naming a file stays `<item>`, and one naming nothing yet becomes both. Every path with a
dot-prefixed component is pruned at any depth before matching. `plain-copy` matches are still shipped but keep
their bytes; the packager applies no line-ending or keyword filter to them.

This module only answers which files ship and which keep their bytes. It reads no other directive and applies no
substitution. `release.sh` also adds every path `git ls-files --others` reports, untracked and ignored alike, to
its ignore list at build time, and it does so whether or not the checkout has a policy file: a git checkout with
neither `.pkgmeta` nor `pkgmeta.yaml` still ships only what git tracks, while a non-git extraction has no such
paths and is read as-is.
"""

import fnmatch
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

__all__ = ["FILES", "Manifest", "localization_toc_files", "project_toc_files", "read"]

PKGMETA = ".pkgmeta"
FALLBACK = "pkgmeta.yaml"
FILES = (PKGMETA, FALLBACK)
# release.sh refuses a tab-indented line before it reads any directive.
LEADING_TAB = re.compile(r"^ *\t+[ \t]*\S")
MOVE_WITHOUT_PACKAGE = ".pkgmeta move-folders needs package-as; visual proof cannot derive the installed paths it moves"
# The vendor's project TOC suffixes, in release.sh's own order: the plain TOC, then one pair per game family.
PROJECT_TOC_VARIANTS = (
    "",
    "-Mainline",
    "_Mainline",
    "-Classic",
    "_Classic",
    "-Vanilla",
    "_Vanilla",
    "-BCC",
    "_BCC",
    "-TBC",
    "_TBC",
    "-Wrath",
    "_Wrath",
    "-WOTLKC",
    "_WOTLKC",
    "-Cata",
    "_Cata",
    "-Mists",
    "_Mists",
    "-Camelot",
    "_Camelot",
)


def _unquote(value: str) -> str:
    if value[:1] in "'\"":
        value = value[1:]
    if value[-1:] in "'\"":
        value = value[:-1]
    return value


def _lines(text: str):
    """The non-blank, non-comment lines release.sh's YAML reader sees, refusing a leading tab as it does."""
    for line in text.splitlines():
        line = line.rstrip("\r")
        if LEADING_TAB.match(line):
            raise ValueError("pkgmeta contains a leading tab; only spaces are allowed for indentation in YAML files")
        if not line.strip() or line.lstrip(" \t").startswith("#"):
            continue
        yield line


def _phase(line: str, phase: str) -> str:
    """release.sh changes phase only on an unindented line that names a key (`[! ]*: *`)."""
    return line.partition(":")[0] if not line.startswith(" ") and ":" in line else phase


def _entries(text: str, key: str) -> list[str]:
    """One top-level key's list entries, read the way release.sh's YAML reader does."""
    entries = []
    phase = ""
    for line in _lines(text):
        phase = _phase(line, phase)
        if phase != key or not line.startswith(" ") or not line.lstrip(" ").startswith("- "):
            continue
        entry = _unquote(line.lstrip(" ")[1:].lstrip())
        if entry:
            entries.append(entry)
    return entries


def _value(text: str, key: str) -> str:
    """One top-level scalar's value."""
    for line in _lines(text):
        if line.startswith(" "):
            continue
        name, _, value = line.partition(":")
        if name == key:
            return _unquote(value.strip())
    return ""


def _mapping(text: str, key: str) -> tuple[tuple[str, str], ...]:
    """One top-level key's `key: value` pairs, read the way release.sh's YAML reader does."""
    pairs = []
    phase = ""
    for line in _lines(text):
        phase = _phase(line, phase)
        if phase != key or not line.startswith(" "):
            continue
        stripped = line.lstrip(" ")
        if stripped.startswith("- "):
            continue
        name, found, value = stripped.partition(":")
        if found:
            pairs.append((_unquote(name.strip()), _unquote(value.strip())))
    return tuple(pairs)


def _policy_text(root: Path) -> str:
    """The checkout's `.pkgmeta` or fallback text, or "" when it has neither."""
    for name in FILES:
        path = root / name
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")
    return ""


def _quoted_mapping_keys(text: str, key: str) -> set[str]:
    """Mapping keys release.sh leaves quoted, which its raw `#*/` path split then cannot resolve."""
    quoted = set()
    phase = ""
    for line in _lines(text):
        phase = _phase(line, phase)
        if phase != key or not line.startswith(" "):
            continue
        stripped = line.lstrip(" ")
        if stripped.startswith("- "):
            continue
        name, found, _ = stripped.partition(":")
        if found and name.strip()[:1] in "'\"":
            quoted.add(_unquote(name.strip()))
    return quoted


def _globs(root: Path, entries: list[str]) -> tuple[str, ...]:
    """The packager's colon-separated globs, resolved against the files that exist in `root`."""
    globs = []
    for entry in entries:
        entry = entry.removesuffix("/*")
        if (root / entry).is_dir():
            globs.append(f"{entry}/*")
        elif (root / entry).is_file():
            globs.append(entry)
        else:
            # The item may name a file or a directory at package time, so the packager matches both.
            globs.extend((entry, f"{entry}/*"))
    return tuple(globs)


def _work_tree(root: Path) -> bool:
    """Whether `root` sits in a git work tree, without asking git (which may itself be failing)."""
    return any((directory / ".git").exists() for directory in (root, *root.parents))


def _checkout_root(root: Path) -> bool:
    """Whether `root` is itself a git checkout, not a package extraction nested inside another repository."""
    return (root / ".git").exists()


def _untracked(root: Path) -> tuple[str, ...]:
    """The packager's extra ignores, from `release.sh`'s `vcs_addignore`: git's untracked and ignored paths.

    A checkout outside a git work tree carries no such paths, so an extraction fixture reads as empty. Inside one,
    a git failure would silently ship files the release leaves out, so it is reported instead.
    """
    try:
        inside = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
        )
    except OSError as error:
        if not _work_tree(root):
            return ()
        raise ValueError(f"{root}: cannot run git to read untracked paths: {error}") from error
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        if not _work_tree(root):
            return ()
        detail = inside.stderr.strip() or f"git rev-parse exited {inside.returncode}"
        raise ValueError(f"{root}: git cannot read the work tree: {detail}")
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--directory"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise ValueError(f"{root}: git failed to list untracked paths: {detail.strip()}") from error
    patterns = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        if line.endswith("/") or (root / line).is_dir():
            patterns.append(f"{line.rstrip('/')}/*")
        else:
            patterns.append(line)
    return tuple(patterns)


def _matches(name: str, globs: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in globs)


@dataclass(frozen=True)
class Manifest:
    """A checkout's package selection: `keeps` is the shipped set, `unchanged` the bytes-kept files.

    `ignored` is `.pkgmeta`'s list plus the paths git reports as untracked or ignored, as the packager combines
    them. `package` and `moved` are `package-as` and `move-folders`, so `relocates` can say whether a checkout
    path leaves the addon folder the proof names.
    """

    ignored: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    package: str = ""
    moved: tuple[tuple[str, str], ...] = ()

    def keeps(self, name: str) -> bool:
        """Whether a checkout-relative path ships, dot paths excepted."""
        return not any(part.startswith(".") for part in PurePosixPath(name).parts) and not _matches(name, self.ignored)

    def kept_bytes(self, name: str) -> bool:
        """Whether the packager copies `name` without its line-ending and keyword filters."""
        return _matches(name, self.unchanged)

    def relocates(self, name: str) -> bool:
        """Whether `move-folders` moves the checkout path `name` out of the packaged addon folder."""
        if self.moved and not self.package:
            raise ValueError(MOVE_WITHOUT_PACKAGE)
        release = f"{self.package}/{name}"
        return any(release == source or release.startswith(f"{source}/") for source, _ in self.moved)


def read(root: Path) -> Manifest | None:
    """The package selection of a checkout, or None for a folder that is already an installed addon.

    A git checkout with no policy file still gets the packager's git selection: `release.sh` adds untracked and
    ignored paths to its ignore list before it looks at a `.pkgmeta`. Only a non-git extraction, which carries
    neither the policy nor a work tree of its own, is read as every file shipped. An extraction nested inside a
    larger repository is an extraction too, so the test is the folder's own `.git`, not any ancestor.
    """
    root = root.resolve()
    path = root / PKGMETA
    if not path.is_file():
        path = root / FALLBACK
        if not path.is_file():
            return Manifest(_untracked(root)) if _checkout_root(root) else None
    text = path.read_text(encoding="utf-8", errors="replace")
    ignored = _globs(root, _entries(text, "ignore")) + _untracked(root)
    return Manifest(
        ignored,
        _globs(root, _entries(text, "plain-copy")),
        _value(text, "package-as"),
        _mapping(text, "move-folders"),
    )


def _has_interface(path: Path) -> bool:
    """Whether a TOC carries the base `## Interface:` line release.sh reads before filtering it."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return False
    return any(line.startswith("## Interface:") for line in text.splitlines())


def project_toc_files(root: Path) -> list[Path]:
    """The project TOC files release.sh selects for an addon's package metadata.

    This mirrors release.sh's project TOC loops at the pinned BigWigs revision
    `01e8631a69c69d7654c788d152630d5fed9e3812` (lines 1424-1454): the root `<package-as>` TOC and each exact
    vendor variant, then, for every supported `move-folders` destination that is a single folder name, the files
    under the move's source directory named for that destination basename. The vendor list is exact and
    case-sensitive: the plain name plus `-` and `_` variants of Mainline, Classic, Vanilla, BCC, TBC, Wrath,
    WOTLKC, Cata, Mists and Camelot. Only existing files are returned, in that order, with duplicates kept once.

    Without `package-as`, release.sh uses the shortest visible root TOC name, breaking ties by name, and refuses a
    flavor-suffixed name without a plain fallback; a hidden TOC is never that fallback. No root TOC in that case
    is refused, and a project with no selected TOC at all is refused rather than reported as empty.

    A move key without `/` and a quoted move key are not the path release.sh's raw key split resolves, so this
    conservative helper skips them instead of reporting a TOC the packager never names. A nested move destination
    is skipped as release.sh skips it.

    Use `localization_toc_files` for the subset that carries `## Interface:` and therefore reaches the packager's
    `@localization@` filter (release.sh line 1946); a project TOC without that line is still discovered here.
    """
    root = root.resolve()
    manifest = read(root)
    text = _policy_text(root)
    package = manifest.package if manifest else ""
    if not package:
        tocs = sorted(
            (path for path in root.glob("*.toc") if not path.name.startswith(".")),
            key=lambda path: (len(path.name), path.name),
        )
        if not tocs:
            raise ValueError("Could not find a root addon TOC file; set package-as or supply one")
        package = tocs[0].stem
        if any(package.endswith(suffix) for suffix in PROJECT_TOC_VARIANTS if suffix):
            raise ValueError("Ambiguous addon name: set package-as or supply a plain fallback TOC")
    quoted = _quoted_mapping_keys(text, "move-folders")
    found: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        if path.is_file() and path not in seen:
            seen.add(path)
            found.append(path)

    for suffix in PROJECT_TOC_VARIANTS:
        add(root / f"{package}{suffix}.toc")
    for source, target in manifest.moved if manifest else ():
        if "/" in target or "/" not in source or source in quoted:
            continue
        directory = source.split("/", 1)[1]
        for suffix in PROJECT_TOC_VARIANTS:
            add(root / directory / f"{target}{suffix}.toc")
    if not found:
        raise ValueError(f"Could not find a project TOC matching package-as {package}")
    return found


def localization_toc_files(root: Path) -> list[Path]:
    """The project TOCs that reach the packager's `@localization@` filter: those with `## Interface:`.

    Every `.lua` file and these TOCs receive that filter; other text suffixes (`.md`, `.txt`, `.xml`) do not. A
    project TOC without a base `## Interface:` line is still a project TOC, but release.sh skips its localization
    filter (line 1946), so it is not returned here.
    """
    return [path for path in project_toc_files(root) if _has_interface(path)]
