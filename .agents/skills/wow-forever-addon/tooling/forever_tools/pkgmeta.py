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

__all__ = ["FILES", "Layout", "Manifest", "layout", "localization_toc_files", "project_toc_files", "read"]

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


_YAML_BOOL = frozenset({"yes", "no", "true", "false", "on", "off"})


def _raw_move_syntax(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Move entries whose raw YAML the packager reads differently from the normalized key/value.

    `yaml_keyvalue` trims leading spaces but keeps trailing whitespace and a tab after the colon, and it turns an
    unquoted yes/no/true/false/on/off value into yes/no before move-folders sees it. Those forms do not name the
    folder the normalized mapping would, so they are refused instead of being silently repaired.
    """
    bad_sources = {}
    bad_targets = {}
    phase = ""
    for line in _lines(text):
        phase = _phase(line, phase)
        if phase != "move-folders" or not line.startswith(" "):
            continue
        stripped = line.lstrip(" ")
        if stripped.startswith("- "):
            continue
        raw_key, found, raw_value = stripped.partition(":")
        if not found:
            continue
        source = _unquote(raw_key.strip())
        target = _unquote(raw_value.strip())
        if raw_key != raw_key.rstrip(" \t"):
            bad_sources[source] = "move source has trailing whitespace the packager keeps"
        if raw_value != raw_value.rstrip():
            bad_targets[target] = "move destination has trailing whitespace the packager keeps"
        leading = raw_value.lstrip(" ")
        if leading[:1] == "\t":
            bad_targets[target] = "move destination starts with a tab the packager keeps"
        if leading[:1] not in ("'", '"') and leading.rstrip(" \t").casefold() in _YAML_BOOL:
            bad_targets[target] = "move destination is a YAML boolean the packager normalizes"
    return bad_sources, bad_targets


def _external_entries(text: str) -> tuple[tuple[str, str], ...]:
    """One top-level `externals:` mapping's first-level `(key, url)` pairs.

    BigWigs accepts both `ForeverCore: <url>` and a `ForeverCore:` block holding `url:` and `tag:` children. Only
    the first-level names are externals; a child key names a property, not a second addon. The first indented
    entry fixes the block's key indentation, so a nested child is never mistaken for a top-level key. A block
    form's `url:` child supplies that entry's URL.
    """
    entries: list[list[str]] = []
    phase = ""
    base = None
    current: list[str] | None = None
    for line in _lines(text):
        previous = phase
        phase = _phase(line, phase)
        if phase != previous:
            base = None
            current = None
        if phase != "externals" or not line.startswith(" "):
            continue
        stripped = line.lstrip(" ")
        if stripped.startswith("- "):
            continue
        indent = len(line) - len(stripped)
        if base is None:
            base = indent
        name, found, value = stripped.partition(":")
        if not found:
            continue
        if indent == base:
            key = _unquote(name.strip())
            if key:
                current = [key, _unquote(value.strip())]
                entries.append(current)
        elif current is not None and _unquote(name.strip()).casefold() == "url" and not current[1]:
            current[1] = _unquote(value.strip())
    return tuple((key, value) for key, value in entries)


def _external_keys(text: str) -> tuple[str, ...]:
    """One top-level `externals:` mapping's first-level keys."""
    return tuple(key for key, _ in _external_entries(text))


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
class Layout:
    """Where a package's source-owned folders install, and which top-level folders its externals bind.

    `owned` pairs each release folder with its checkout prefix: the package folder uses the empty prefix, and a
    moved source-owned folder uses its checkout-relative source. `external` names only the top-level folders a
    moved external installs; `external_sources` is every declared external's checkout-relative source, so a package
    walk never mistakes one for source-owned bytes. A layout with no non-empty owned prefix is `mapped == False`:
    the package still installs one folder and keeps the legacy single-folder identity.
    """

    package: str
    owned: tuple[tuple[str, str], ...]
    external: tuple[str, ...] = ()
    external_sources: tuple[str, ...] = ()

    @property
    def mapped(self) -> bool:
        """Whether `move-folders` installs a source-owned addon as a top-level sibling."""
        return any(prefix for _, prefix in self.owned)

    def release_path(self, name: str) -> str:
        """The release-relative path of a checkout-relative file, choosing the most specific owned prefix."""
        best = None
        for folder, prefix in self.owned:
            if prefix and name != prefix and not name.startswith(f"{prefix}/"):
                continue
            if best is None or len(prefix) > len(best[1]):
                best = (folder, prefix)
        if best is None:
            raise ValueError(f"{name}: no source-owned folder in the mapped layout owns this path")
        folder, prefix = best
        rest = name if not prefix else name[len(prefix) :].lstrip("/")
        return f"{folder}/{rest}" if rest else folder

    def in_external_source(self, name: str) -> bool:
        """Whether `name` sits inside a declared external's checkout-relative source."""
        return any(name == source or name.startswith(f"{source}/") for source in self.external_sources)


@dataclass(frozen=True)
class Manifest:
    """A checkout's package selection: `keeps` is the shipped set, `unchanged` the bytes-kept files.

    `ignored` is `.pkgmeta`'s list plus the paths git reports as untracked or ignored, as the packager combines
    them. `package`, `moved` and `externals` are `package-as`, `move-folders` and `externals`; `relocates` says
    whether a checkout path leaves the addon folder the proof names, and `layout` resolves every move.
    """

    ignored: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    package: str = ""
    moved: tuple[tuple[str, str], ...] = ()
    externals: tuple[str, ...] = ()

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

    def layout(self, root: Path) -> Layout | None:
        """This manifest's validated folder layout, or None when no move runs."""
        return layout(root, self)


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
        _external_keys(text),
    )


_INTERFACE_BASE = re.compile(r"^## Interface:[ \t]*(.*)$")
_INTERFACE_FLAVOR = re.compile(r"^## Interface-([A-Za-z]+):[ \t]*(.*)$", re.IGNORECASE)
_INTERFACE_VALUE = re.compile(r"^[0-9]+(?:,[0-9]+)*$")
_CONDITIONAL_BLOCK = re.compile(r"^\s*#@(?P<end>end-)?(?P<non>non-)?(?P<kind>alpha|debug)@")
# release.sh's game_flavor keys; an unknown Interface-Foo: is ignored by the vendor loop.
_GAME_FLAVORS = frozenset(
    {
        "retail",
        "classic",
        "bcc",
        "mainline",
        "tbc",
        "vanilla",
        "wrath",
        "wotlkc",
        "cata",
        "mists",
        "titan",
        "forever",
        "camelot",
    }
)


def _conditional_interface(text: str) -> bool:
    """Whether an Interface line sits in an alpha or debug block release.sh may include or remove."""
    active: list[tuple[str, bool]] = []
    for line in text.splitlines():
        directive = _CONDITIONAL_BLOCK.match(line)
        if directive:
            token = (directive.group("kind"), bool(directive.group("non")))
            if directive.group("end"):
                for index in range(len(active) - 1, -1, -1):
                    if active[index] == token:
                        active.pop(index)
                        break
            else:
                active.append(token)
            continue
        if active:
            stripped = line.lstrip(" \t")
            if stripped.startswith("# "):
                stripped = stripped[2:]
            if stripped.startswith("## Interface"):
                return True
    return False


def _interface_filter_eligible(path: Path) -> bool:
    """Whether release.sh's localization filter can run on this project TOC, refusing unsupported forms.

    A nonempty base `## Interface:` value is the common case. A flavor-only TOC is supported when a known
    `## Interface-<flavor>:` line has a nonempty value, because release.sh fills `si_game_type_interface_all` from
    it even without a base (the `Interface-Forever: 16001` form). An empty base/flavor set is not eligible; if such
    a TOC still carries `@localization`, it is refused so the unknown filter outcome is never silently omitted.
    Alpha or debug blocks around an Interface line are refused: release.sh's build-type filters decide whether
    those lines exist before it reads the metadata, which this narrow check does not model.
    """
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    except OSError:
        return False
    if _conditional_interface(text):
        raise ValueError(f"{path}: alpha/debug conditional Interface metadata is not modelled")
    base = ""
    for line in text.splitlines():
        match = _INTERFACE_BASE.match(line)
        if match:
            base = match.group(1).strip(" \t")
            break
    values = [base] if base else []
    for line in text.splitlines():
        match = _INTERFACE_FLAVOR.match(line)
        if match and match.group(1).casefold() in _GAME_FLAVORS:
            values.append(match.group(2).strip(" \t"))
    if any(values):
        for value in values:
            if value and _INTERFACE_VALUE.fullmatch(value) is None:
                raise ValueError(f"{path}: unsupported Interface metadata {value!r}")
        return True
    if "@localization" in text:
        raise ValueError(f"{path}: no nonempty Interface metadata, so the vendor localization filter would not run")
    return False


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
    """The project TOCs that reach the packager's `@localization@` filter.

    Every `.lua` file and these TOCs receive that filter; other text suffixes (`.md`, `.txt`, `.xml`) do not. A
    nonempty base `## Interface:` is the common case, and a known `## Interface-<flavor>:` value is enough on its
    own because release.sh fills the same interface map from it. An empty metadata set is omitted unless the TOC
    carries `@localization`, which is refused rather than silently left out. Alpha/debug conditional Interface
    lines and non-numeric Interface values are refused because release.sh's build-type filters decide them before
    the localization check.
    """
    return [path for path in project_toc_files(root) if _interface_filter_eligible(path)]


_UNSAFE_COMPONENT = re.compile(r'[<>:"|?*]')
_ABSOLUTE_DRIVE = re.compile(r"^[A-Za-z]:")


def _relative_problem(value: str, what: str) -> str:
    """Why `value` is not a safe checkout-relative path, or "" when it is."""
    if not value:
        return f"{what}: empty path"
    if value.startswith(("/", "\\")):
        return f"{what}: absolute path"
    if "\\" in value:
        return f"{what}: backslash in path"
    if _ABSOLUTE_DRIVE.match(value):
        return f"{what}: absolute drive path"
    if any(part in ("", ".", "..") or part.startswith(".") for part in value.split("/")):
        return f"{what}: dot, parent or empty path component"
    return ""


def _component_problem(value: str, what: str) -> str:
    """Why `value` is not a safe single release-folder name, or "" when it is."""
    if not value:
        return f"{what}: empty folder name"
    if "/" in value or "\\" in value:
        return f"{what}: must be one folder name, not a path"
    if value in (".", "..") or value.startswith("."):
        return f"{what}: dot or parent folder name"
    if _ABSOLUTE_DRIVE.match(value):
        return f"{what}: absolute drive path"
    if _UNSAFE_COMPONENT.search(value):
        return f"{what}: contains a character Windows refuses in a folder name"
    if value.endswith((" ", ".")):
        return f"{what}: trailing space or dot"
    return ""


def _root_file(directory: Path, name: str) -> Path | None:
    """A file at the directory's root, exact first, then a single case-insensitive match."""
    exact = directory / name
    if exact.is_file():
        return exact
    if not directory.is_dir():
        return None
    matches = [path for path in directory.iterdir() if path.is_file() and path.name.casefold() == name.casefold()]
    return matches[0] if len(matches) == 1 else None


def _external_problem(root: Path, key: str, url: str) -> str:
    """Why a moved external is not the supported pinned ForeverCore bundle, or "" when it is.

    The candidate deliberately does not hash an external's bytes; only `tools/forever-core.txt` and the policy
    bind it. This slice therefore supports the one verified external, `ForeverCore`, and only when its declaration
    is exactly the official `cjber/forever-core` release URL for the pin. A tag alone is not a binding: a foreign
    host or another repository with the same tag would be labelled bound without the bytes the pin names.
    """
    if key != "ForeverCore":
        return f"external {key} is not the supported ForeverCore external"
    pin_path = root / "tools/forever-core.txt"
    pin = pin_path.read_text(encoding="utf-8", errors="replace").strip() if pin_path.is_file() else ""
    if not pin:
        return "external ForeverCore is not bound: tools/forever-core.txt is missing"
    if not pin.startswith("v"):
        return f"external ForeverCore pin {pin} is not an immutable release tag"
    expected = f"https://github.com/cjber/forever-core/releases/download/{pin}/ForeverCore-{pin}-forever.zip"
    if url != expected:
        return f"external ForeverCore URL is not the official pinned release {expected}"
    return ""


def _case_duplicates(root: Path, prefix: str) -> str:
    """A problem when a component of `prefix` exists more than once ignoring case, else ""."""
    current = root
    for part in prefix.split("/"):
        if not current.is_dir():
            return ""
        matches = [path for path in current.iterdir() if path.name.casefold() == part.casefold()]
        if len(matches) > 1:
            names = ", ".join(sorted(path.name for path in matches))
            return f"move-folders: {prefix} has case-duplicate folders ({names})"
        if not matches:
            return ""
        current = matches[0]
    return ""


def layout(root: Path, manifest: Manifest | None = None) -> Layout | None:
    """Resolve `move-folders` into a checked release layout, or None when no move runs.

    Every source is a checkout-relative path under `package-as`; every destination is one top-level folder name.
    A source must be exactly one of a checkout directory (source-owned) or an `externals` key (bound by the pin,
    absent from the checkout). A source that is both or neither is refused rather than guessed. Source-owned
    moved folders must ship their own `<target>.toc`, and source overlap, destination collisions (ignoring case),
    unsafe path components and case-duplicate source folders are refused. An external-only move still returns a
    layout, but `mapped` is false so a single-folder package keeps its legacy identity. The only supported moved
    external is `ForeverCore`, and only when its declared `/download/<tag>/` is the immutable tag
    `tools/forever-core.txt` pins; any other external has no binding the candidate could honestly name, so it is
    refused.
    """
    root = root.resolve()
    if manifest is None:
        manifest = read(root)
    if manifest is None or not manifest.moved:
        return None
    if not manifest.package:
        raise ValueError(MOVE_WITHOUT_PACKAGE)
    problem = _component_problem(manifest.package, "package-as")
    if problem:
        raise ValueError(problem)
    package = manifest.package
    text = _policy_text(root)
    quoted = _quoted_mapping_keys(text, "move-folders")
    external_values = dict(_external_entries(text))
    bad_sources, bad_targets = _raw_move_syntax(text)
    problems: list[str] = []
    external_by_case: dict[str, str] = {}
    for key in manifest.externals:
        problem = _relative_problem(key, f"externals entry {key!r}")
        if problem:
            problems.append(problem)
            continue
        case = key.casefold()
        if case in external_by_case:
            problems.append(f"externals: {key} duplicates {external_by_case[case]} ignoring case")
        else:
            external_by_case[case] = key
    owned: list[tuple[str, str]] = [(package, "")]
    external_targets: list[str] = []
    external_sources: list[str] = []
    sources: list[tuple[str, str, str]] = []
    targets = {package.casefold(): f"package-as {package}"}
    source_cases: dict[str, str] = {}
    for source, target in manifest.moved:
        label = f"move-folders {source!r}"
        problem = _relative_problem(source, label)
        if problem:
            problems.append(problem)
            continue
        if source in quoted:
            problems.append(f"{label}: quoted move key is not supported by the pinned packager's raw key split")
            continue
        if source in bad_sources:
            problems.append(f"{label}: {bad_sources[source]}")
            continue
        if source == package:
            problems.append(f"{label}: moves the package folder itself")
            continue
        if not source.startswith(f"{package}/"):
            problems.append(f"{label}: source is outside package-as {package}")
            continue
        prefix = source[len(package) + 1 :]
        problem = _relative_problem(prefix, f"{label} source")
        if problem:
            problems.append(problem)
            continue
        problem = _component_problem(target, f"{label} destination")
        if problem:
            problems.append(problem)
            continue
        if target in bad_targets:
            problems.append(f"{label}: {bad_targets[target]}")
            continue
        case = target.casefold()
        if case in targets:
            problems.append(f"{label}: destination {target} collides with {targets[case]} ignoring case")
        else:
            targets[case] = f"destination {target}"
        source_case = source.casefold()
        if source_case in source_cases:
            problems.append(f"{label}: source duplicates {source_cases[source_case]} ignoring case")
        else:
            source_cases[source_case] = source
        sources.append((source, prefix, target))
        problem = _case_duplicates(root, prefix)
        if problem:
            problems.append(problem)
        local = root / prefix
        declared = prefix if prefix in manifest.externals else None
        if declared is not None and local.exists():
            problems.append(f"{label}: source {prefix} is both an externals entry and a checkout path")
            continue
        if declared is None and not local.exists():
            problems.append(f"{label}: stale source {prefix} is neither in the checkout nor an externals entry")
            continue
        if declared is not None:
            problem = _external_problem(root, declared, external_values.get(declared, ""))
            if problem:
                problems.append(f"{label}: {problem}")
                continue
            external_targets.append(target)
            external_sources.append(declared)
            continue
        if not local.is_dir():
            problems.append(f"{label}: source {prefix} is not a checkout folder")
            continue
        if _root_file(local, f"{target}.toc") is None or not manifest.keeps(f"{prefix}/{target}.toc"):
            problems.append(f"{label}: moved folder {prefix} has no shipped {target}.toc beside it")
        owned.append((target, prefix))
    for index, (left, left_prefix, _) in enumerate(sources):
        for right, right_prefix, _ in sources[index + 1 :]:
            left_case = left_prefix.casefold()
            right_case = right_prefix.casefold()
            if (
                left_case == right_case
                or left_case.startswith(f"{right_case}/")
                or right_case.startswith(f"{left_case}/")
            ):
                problems.append(f"move-folders: sources {left} and {right} overlap")
    if problems:
        raise ValueError("; ".join(problems))
    return Layout(package, tuple(owned), tuple(external_targets), tuple(external_sources))
