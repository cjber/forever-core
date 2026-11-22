"""Keep the copies of a consumer's ForeverCore release in step, against core's latest published release.

A consumer that bundles core commits the release tag in three places: `tools/forever-core.txt` (the tag its specs and
CI check out), the `.pkgmeta` ForeverCore external (the zip the packager ships) and the root TOC's
`## X-Forever-Core:` field (the tag a sibling addon compares). The packager and the client each read their own copy
literally, so no build step can derive one from another; this module is the one comparison every copy is checked
against.

    python3 -m tools.forever_tools.core_pin [root]            the three copies name one release
    python3 -m tools.forever_tools.core_pin --latest [root]   and that release is core's latest published one
    python3 -m tools.forever_tools.core_pin --latest-if-release-prep --base REF [root]
                                                              require latest only when CHANGELOG.md adds a version

`--latest` is the release gate. It reads `cjber/forever-core`'s latest published GitHub release (with `GH_TOKEN` or
`GITHUB_TOKEN` when either is set) and fails closed when that release cannot be read, so an unknown latest release can
never pass a stale pin. The consumer's package job compares the three copies offline; its PR CI runs
`--latest-if-release-prep --base origin/$BASE` so a release-prep PR fails before tagging while normal PRs stay
unaffected; its release workflow runs `--latest` directly before the packager uploads. A consumer whose `.pkgmeta`
ships no ForeverCore external bundles no core, so the bundle comparison is skipped; `--latest` still checks its pin
against the latest release.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

from . import changelog, require_slash
from . import pkgmeta as pkgmeta_reader

__all__ = [
    "CORE_EXTERNAL",
    "CORE_FIELD",
    "CORE_FOLDER",
    "EXTERNAL_TAG",
    "LATEST_RELEASE_URL",
    "LatestReleaseUnavailable",
    "PIN_PATH",
    "PKGMETA",
    "TOC_CORE_FIELD",
    "added_changelog_versions",
    "check",
    "check_latest",
    "check_latest_if_release_prep",
    "compare",
    "compare_latest",
    "core_external",
    "embed_problem",
    "embedded_packaging",
    "embeds",
    "external_ships_core",
    "external_tag",
    "latest_release",
    "main",
    "parse_args",
    "pkgmeta_field",
    "policy_package",
    "policy_path",
    "root_toc_name",
    "toc_name_for",
    "toc_field",
    "toc_fields",
]

# The release a consumer's specs and CI check ForeverCore out at, and the packaging files that decide how it ships.
PIN_PATH = "tools/forever-core.txt"
PKGMETA = ".pkgmeta"
CORE_FOLDER = "ForeverCore"
# The TOC header naming the core release the zip bundles, which a sibling addon compares to its own.
CORE_FIELD = "X-Forever-Core"
# The consumer-side bundle: the shipped core's `.pkgmeta` external and the tag inside its download URL.
CORE_EXTERNAL = re.compile(r"^(?P<indent>[ \t]*)ForeverCore:[ \t]*\S+[^\r\n]*", re.IGNORECASE | re.MULTILINE)
EXTERNAL_TAG = re.compile(r"/download/(?P<tag>[^/\s]+)/", re.IGNORECASE)
TOC_CORE_FIELD = re.compile(r"^##[ \t]*X-Forever-Core[ \t]*:[^\r\n]*", re.IGNORECASE | re.MULTILINE)
TOC_CORE_VALUE = re.compile(r"^##[ \t]*X-Forever-Core[ \t]*:[ \t]*(?P<value>\S+)", re.IGNORECASE | re.MULTILINE)
# A consumer that carries core under Libs/ForeverCore opts in with this TOC field. `embeds` is the one reader of it:
# forever_tools.embed, the vendored package check and core's drift and sync tools all call it.
EMBED_FIELD = "X-Forever-Core-Embed"
# One `## Name: value` TOC line, matched after the line is stripped.
TOC_FIELD_LINE = re.compile(r"^##\s*(?P<name>[^:]+?)\s*:\s*(?P<value>.*?)\s*$")
# Core's store project: its slug in a `.pkgmeta` relation, and its id in a store URL.
CORE_SLUG = "forevercore"
CORE_PROJECT_ID = "1796337"
# The release the whole suite bundles: every consumer's zip must carry this one, newest, published ForeverCore.
LATEST_RELEASE_URL = "https://api.github.com/repos/cjber/forever-core/releases/latest"


class LatestReleaseUnavailable(RuntimeError):
    """Core's latest published release could not be read, so no pin may be called current."""


def latest_release(fetch=None):
    """The tag of cjber/forever-core's latest published GitHub release.

    `fetch` replaces the network read in tests and must return the tag. Any read failure, an unreadable body or a
    missing tag raises `LatestReleaseUnavailable` with the reason, so callers fail closed instead of skipping the gate.
    """
    if fetch is not None:
        try:
            tag = fetch()
        except LatestReleaseUnavailable:
            raise
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise LatestReleaseUnavailable(str(error)) from error
    else:
        request = urllib.request.Request(
            LATEST_RELEASE_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "forever-core-pin"},
        )
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                tag = json.loads(response.read()).get("tag_name")
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, AttributeError) as error:
            raise LatestReleaseUnavailable(str(error)) from error
    if not isinstance(tag, str) or not tag.strip():
        raise LatestReleaseUnavailable(f"{LATEST_RELEASE_URL} named no release tag")
    return tag.strip()


def compare_latest(pin, latest, *, pin_path=PIN_PATH):
    """The failure when `pin` does not name `latest`, core's latest published release."""
    pin = (pin or "").strip()
    if pin == latest:
        return []
    return [
        f"{pin_path}: pin {pin or '(empty)'}, core's latest release is {latest}; move it to {latest}"
        " so this addon ships the ForeverCore every other Forever addon has"
    ]


def pkgmeta_field(text, name):
    """A `.pkgmeta`'s scalar value for `name`, unquoted, or "" when the file does not set it."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or line[:1].isspace() or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition(":")
        if separator and key.strip() == name:
            return value.strip().strip("'\"")
    return ""


def core_external(pin):
    """The `.pkgmeta` external a consumer of `pin` downloads, the ForeverCore release zip for that tag."""
    return f"https://github.com/cjber/forever-core/releases/download/{pin}/{CORE_FOLDER}-{pin}-forever.zip"


def external_line(pkgmeta):
    """The `.pkgmeta` line shipping ForeverCore, or "" when the consumer bundles no core."""
    match = CORE_EXTERNAL.search(pkgmeta)
    return match.group(0) if match else ""


def external_url(pkgmeta):
    """The URL after the ForeverCore external's colon, unquoted, or "" when the consumer bundles no core."""
    line = external_line(pkgmeta)
    return line.split(":", 1)[1].strip().strip("'\"") if line else ""


def external_tag(pkgmeta):
    """The tag the consumer's `.pkgmeta` ForeverCore external downloads, or None when it ships none."""
    tag = EXTERNAL_TAG.search(external_line(pkgmeta))
    return tag["tag"] if tag else None


def toc_field(toc):
    """A TOC's `## X-Forever-Core:` value, or None when the TOC does not set it."""
    match = TOC_CORE_VALUE.search(toc or "")
    return match["value"] if match else None


def compare(
    pin,
    pkgmeta,
    toc,
    *,
    pin_path=PIN_PATH,
    pkgmeta_path=PKGMETA,
    toc_path="the root TOC",
    require_external=False,
):
    """Failures when the pin, the `.pkgmeta` external and the TOC field name different releases.

    A consumer with no ForeverCore external bundles no core, so it is skipped unless `require_external` says its TOC
    depends on core and must ship it. A missing pin, external or TOC field is a disagreement like any other: every
    copy has to name the same tag in the same commit.
    """
    external = external_line(pkgmeta)
    if not external and not require_external:
        return []
    pin = pin.strip()
    if not pin:
        return [f"{pin_path}: a dependency of the TOC, but no pin names the release to ship"]
    expected = core_external(pin)
    failures = []
    if not external:
        failures.append(
            f"{pkgmeta_path}: a dependency of the TOC, but `externals:` does not ship ForeverCore;"
            f" add `ForeverCore: {expected}`"
        )
    elif external_url(pkgmeta) != expected:
        failures.append(
            f"{pkgmeta_path}: `externals:` ships ForeverCore from {external_url(pkgmeta)}; {pin_path} pins {pin},"
            f" so it must be {expected}"
        )
    declared = toc_field(toc)
    if not declared:
        failures.append(
            f"{toc_path}: a dependency of the TOC, but no `## {CORE_FIELD}:` line names the core release"
            f" the zip bundles; add `## {CORE_FIELD}: {pin}`"
        )
    elif declared != pin:
        failures.append(f"{toc_path}: `## {CORE_FIELD}:` is {declared}; {pin_path} pins {pin}, so it must be {pin}")
    return failures


def toc_fields(toc):
    """A TOC's `## Name: value` fields, names lowercased. A field set twice keeps its last value, as embed reads it."""
    if isinstance(toc, bytes):
        toc = toc.decode("utf-8-sig", "replace")
    fields = {}
    for line in (toc or "").lstrip("\ufeff").splitlines():
        match = TOC_FIELD_LINE.match(line.strip())
        if match:
            fields[match["name"].strip().lower()] = match["value"]
    return fields


def embeds(toc):
    """Whether a root TOC (text or bytes) opts in to carrying core under Libs/ForeverCore.

    The field's last value must be exactly `1`, the value the embed step acts on, so every checker agrees with the
    step that writes the zip: a TOC the embed step skips is never treated as embedded, and the reverse.
    """
    return toc_fields(toc).get(EMBED_FIELD.lower()) == "1"


def embed_problem(toc, toc_path="the root TOC"):
    """The failure for an opt-in line whose value is not exactly `1`, or None.

    `true`, `yes` or `1 # note` reads as not opted in everywhere, so a consumer that meant to embed would quietly
    keep the bridge rules and ship without its copy; the line has to say `1` or go.
    """
    value = toc_fields(toc).get(EMBED_FIELD.lower())
    if value is None or value == "1":
        return None
    return f"{toc_path}: `## {EMBED_FIELD}:` is {value!r}; set it to exactly 1 to embed ForeverCore, or remove the line"


def external_ships_core(key, url):
    """Whether one `.pkgmeta` external downloads ForeverCore, whatever host, scheme or form the URL takes.

    The key's folder named ForeverCore; a URL path or SSH segment naming the `forever-core` repository, the
    `forevercore` store project or its project id 1796337 (with or without `.git` or a trailing slash); or a
    `ForeverCore-*.zip` release asset.
    """
    if PurePosixPath(key).name.casefold() == CORE_FOLDER.casefold():
        return True
    address = url.strip().casefold().split("?", 1)[0].split("#", 1)[0].rstrip("/")
    address = address.removesuffix(".git").rstrip("/")
    parts = [part for part in re.split(r"[/:]", address) if part]
    if any(part in ("forever-core", "forevercore", CORE_PROJECT_ID) for part in parts):
        return True
    return bool(parts) and parts[-1].startswith("forevercore-") and parts[-1].endswith(".zip")


def embedded_packaging(
    pin, toc, pkgmeta, package, *, root_tocs=(), pin_path=PIN_PATH, policy_path=PKGMETA, toc_path="the root TOC"
):
    """The end state for a consumer that carries ForeverCore under `Libs/ForeverCore/` (`## X-Forever-Core-Embed: 1`).

    The zip ships core only inside the addon, as Ace3 and LibStub libraries are embedded. A top-level `ForeverCore/`
    folder that several zips own is the #448 problem: removing or downgrading one addon deletes or rolls back core under
    the others. The store relation is `embedded-libraries`, so the CurseForge app links core on the project page and
    never installs it as a required dependency; the standalone stays its own optional download (#787).

    The `.pkgmeta` is read the way the pinned packager and uploader read it (`forever_tools.pkgmeta.packaging`), so an
    entry passes here only when the release would carry it the same way. The consumer's own core pin gate and core's
    drift check both call this, so a consumer cannot pass its own CI with a policy core's gate refuses.
    """
    if isinstance(toc, bytes):
        toc = toc.decode("utf-8-sig", "replace")
    path = policy_path
    try:
        shipped = pkgmeta_reader.packaging(pkgmeta)
    except ValueError as error:
        return [f"{path}: {error}"]
    failures = []
    others = sorted(name for name in root_tocs if name.casefold() != f"{package}.toc".casefold())
    if others:
        failures.append(
            f"{path}: embeds ForeverCore, which rewrites one root TOC, but the checkout also has {', '.join(others)};"
            " an addon loaded from another TOC would run without its core"
        )
    core = CORE_FOLDER.casefold()
    for key, url in shipped.externals:
        if external_ships_core(key, url):
            failures.append(
                f"{path}: `externals:` ships a second ForeverCore at {key}; the embed step is the only copy"
                " (cjber/forever-core#448)"
            )
    embedded = PurePosixPath(package.casefold(), "libs", core)
    for moved_from, destination in shipped.moves:
        source_path = PurePosixPath(moved_from.casefold())
        target = PurePosixPath(destination.casefold())
        parts = target.parts
        # Windows drops a trailing dot or space from a folder name, so `ForeverCore.` installs as `ForeverCore`.
        final = parts[-1].rstrip(" .") if parts else ""
        if target.is_absolute() or ".." in parts:
            failures.append(f"{path}: `move-folders:` sends {moved_from} to {destination}, outside the zip's top level")
        elif final == core:
            where = f"the top-level {destination}" if len(parts) == 1 else destination
            failures.append(
                f"{path}: `move-folders:` puts {moved_from} at {where}; ForeverCore ships only under Libs/ForeverCore"
                " (cjber/forever-core#448)"
            )
        elif len(parts) > 1 and (target == embedded or target in embedded.parents or embedded in target.parents):
            failures.append(
                f"{path}: `move-folders:` moves {moved_from} over the embedded ForeverCore at {destination}"
            )
        elif (
            source_path.parts[:1] == (package.casefold(),)
            and len(source_path.parts) > 1
            and (source_path in embedded.parents or source_path == embedded or embedded in source_path.parents)
        ):
            failures.append(f"{path}: `move-folders:` moves {moved_from}, which holds the embedded ForeverCore")
    # The uploader keeps one relation per slug, the last one in file order, and matches slugs without case. Core may
    # be named only under `embedded-libraries`: any other relation would replace it, and `required-dependencies` makes
    # the store install the standalone.
    named = [(relation, slug) for relation, slug in shipped.relations if slug.casefold() == CORE_SLUG]
    for relation, _slug in named:
        if relation == "required-dependencies":
            failures.append(
                f"{path}: embeds ForeverCore but lists `forevercore` under `required-dependencies:`; move it to"
                " `embedded-libraries:` so the store never installs the standalone as required"
            )
        elif relation != "embedded-libraries":
            failures.append(
                f"{path}: lists `forevercore` under `{relation}:`, which replaces its `embedded-libraries:` relation;"
                " name core only under `embedded-libraries:`"
            )
    if not named or named[-1][0] != "embedded-libraries":
        failures.append(
            f"{path}: embeds ForeverCore; list `  - forevercore` (spaces, no trailing whitespace) under"
            " `embedded-libraries:`"
        )
    failures += compare_embedded(pin, toc, pin_path=pin_path, toc_path=toc_path)
    return failures


def compare_embedded(pin, toc, *, pin_path=PIN_PATH, toc_path="the root TOC"):
    """Failures when an embedding consumer's pin and TOC field disagree: the embed step copies the pin, and a sibling
    addon reads the field to name an out-of-date core, so both have to name the same release."""
    pin = pin.strip()
    if not pin:
        return [f"{pin_path}: the TOC embeds ForeverCore, but no pin names the release to embed"]
    declared = toc_field(toc)
    if declared != pin:
        return [
            f"{toc_path}: `## {CORE_FIELD}:` is {declared or '(missing)'}; {pin_path} pins {pin}, the release the"
            f" embed step copies, so it must be {pin}"
        ]
    return []


def policy_path(root):
    """The checkout's packager policy, `.pkgmeta` or else `pkgmeta.yaml` as the packager reads it, or None."""
    for name in pkgmeta_reader.FILES:
        if (Path(root) / name).is_file():
            return Path(root) / name
    return None


def policy_package(text):
    """A policy's `package-as`, or "" when it sets none.

    Raises ValueError when the policy sets it more than once: the packager uses the last one while a first-match reader
    would take another, so a checker and the release would disagree about which folder and TOC ship.
    """
    values = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or line[:1].isspace() or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition(":")
        if separator and key.strip() == "package-as":
            values.append(value.strip().strip("'\""))
    if len(values) > 1:
        raise ValueError(f"`package-as` is set {len(values)} times; the packager uses the last, so keep exactly one")
    return values[0] if values else ""


def toc_name_for(package, names):
    """The root TOC the packager names, from `package-as` and the root folder's TOC file names.

    `package-as` names it. Without it the packager takes the shortest visible root TOC name, ties broken by name, and
    refuses a flavor-suffixed one (`forever_tools.pkgmeta.project_toc_files`): that raises ValueError. None when there
    is no package name and no root TOC. Every reader of a consumer (embed, this gate, core's drift, sync and release
    tools) resolves the TOC here, so they cannot pick different ones.
    """
    if package:
        return f"{package}.toc"
    tocs = sorted((name for name in names if not name.startswith(".")), key=lambda name: (len(name), name))
    if not tocs:
        return None
    stem = tocs[0][: -len(".toc")]
    if any(stem.endswith(suffix) for suffix in pkgmeta_reader.PROJECT_TOC_VARIANTS if suffix):
        raise ValueError(f"no `package-as`, and the shortest root TOC {tocs[0]} is flavor-suffixed")
    return tocs[0]


def root_toc_name(root, package):
    """`toc_name_for` over a local checkout's root folder."""
    return toc_name_for(package, [path.name for path in Path(root).glob("*.toc")])


def check(root, latest=None):
    """Failures in a consumer checkout's ForeverCore pin and bundle, relative to `root`.

    With `latest`, the pin must name that release, whether or not the addon bundles core: a consumer without a
    ForeverCore external still tests and builds against the core its pin names. Without it, only the pin's agreement
    with the shipped external and the TOC field is checked, so the plain command needs no network.
    """
    root = Path(root)
    pin_path = root / PIN_PATH
    pin = pin_path.read_text(encoding="utf-8", errors="replace").strip() if pin_path.is_file() else ""
    failures = compare_latest(pin, latest) if latest is not None and pin_path.is_file() else []
    pkgmeta_path = policy_path(root)
    pkgmeta = pkgmeta_path.read_text(encoding="utf-8", errors="replace") if pkgmeta_path else ""
    policy_name = pkgmeta_path.name if pkgmeta_path else PKGMETA
    root_tocs = [path.name for path in root.glob("*.toc")]
    try:
        package = policy_package(pkgmeta)
        toc_name = toc_name_for(package, root_tocs)
    except ValueError as error:
        return failures + [f"{policy_name}: {error}; set exactly one `package-as` or add a plain fallback TOC"]
    toc_path = root / toc_name if toc_name else None
    if package and pkgmeta_path is not None and (toc_path is None or not toc_path.is_file()):
        return failures + [f"{policy_name}: `package-as: {package}` names {toc_name}, which the checkout does not have"]
    toc = toc_path.read_text(encoding="utf-8-sig", errors="replace") if toc_path and toc_path.is_file() else ""
    toc_name = toc_name or "the root TOC"
    problem = embed_problem(toc, toc_name)
    if problem:
        failures.append(problem)
    if toc_path is not None and toc_path.is_file():
        # The same gate keeps a stopped addon answering its own slash command (forever_tools.require_slash).
        failures += require_slash.check(root, toc_path.stem)
    if embeds(toc):
        if pkgmeta_path is None:
            return failures + [
                f"{toc_name}: embeds ForeverCore, but the checkout has no {PKGMETA} or {pkgmeta_reader.FALLBACK};"
                " the release would package it with no embedded-libraries relation"
            ]
        return failures + embedded_packaging(
            pin,
            toc,
            pkgmeta,
            package or toc_name[: -len(".toc")],
            root_tocs=root_tocs,
            pin_path=PIN_PATH,
            policy_path=policy_name,
            toc_path=toc_name,
        )
    if pkgmeta_path is None or not external_line(pkgmeta):
        return failures
    failures += compare(
        pin,
        pkgmeta,
        toc,
        pin_path=PIN_PATH,
        pkgmeta_path=pkgmeta_path.name,
        toc_path=toc_name,
    )
    return failures


def check_latest(root, fetch=None):
    """The release gate: `root`'s pin names core's latest published release, and its bundle agrees.

    A latest release that cannot be read is a failure with its reason, never a skipped check: passing a pin against an
    unknown latest release is exactly how an addon shipped a core older than the one every player has. A checkout with
    neither a pin nor a ForeverCore external does not use core at all, so it is left alone without a network read.
    """
    root = Path(root)
    pkgmeta_path = policy_path(root)
    pkgmeta = pkgmeta_path.read_text(encoding="utf-8", errors="replace") if pkgmeta_path else ""
    if not (root / PIN_PATH).is_file() and not external_line(pkgmeta):
        # No pin and no external: nothing to compare with the latest release, but an embedding TOC still needs a pin.
        return check(root)
    try:
        latest = latest_release(fetch)
    except LatestReleaseUnavailable as error:
        return [
            f"{PIN_PATH}: could not read cjber/forever-core's latest published release ({error});"
            " refusing to pass the pin against an unknown release"
        ]
    return check(root, latest)


def added_changelog_versions(root, base):
    """Release version headings added to `CHANGELOG.md` compared with `git merge-base <base> HEAD`.

    Raises `RuntimeError` when git history against `base` cannot be read, so callers fail closed instead of quietly
    skipping the release-prep pin gate.
    """
    root = Path(root)

    def run_git(*args):
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise RuntimeError(f"CHANGELOG.md: git {' '.join(args)} failed ({detail})")
        return result.stdout

    ancestor = run_git("merge-base", base, "HEAD").strip()
    if run_git("ls-tree", "--name-only", ancestor, "--", "CHANGELOG.md").strip():
        before = run_git("show", f"{ancestor}:CHANGELOG.md")
    else:
        before = ""
    changelog_path = root / "CHANGELOG.md"
    after = changelog_path.read_text(encoding="utf-8", errors="replace") if changelog_path.is_file() else ""
    before_versions = {match["version"] for match in changelog.HEADING.finditer(before)}
    after_versions = {match["version"] for match in changelog.HEADING.finditer(after)}
    return sorted(after_versions - before_versions)


def _release_prep_check(root, base, fetch):
    """The failures, and whether `CHANGELOG.md` adds a version heading against `base`."""
    try:
        added = added_changelog_versions(root, base)
    except RuntimeError as error:
        return [f"{error}; refusing to skip the release-prep pin check"], False
    return (check_latest(root, fetch) if added else check(root)), bool(added)


def check_latest_if_release_prep(root, base, fetch=None):
    """Require core's latest release only when `CHANGELOG.md` adds a version heading against `base`.

    Normal pull requests still verify offline bundle agreement without querying GitHub, so a core release between
    unrelated PRs does not break them. A release-prep PR runs `check_latest` so a stale pin fails the PR rather than
    the release workflow after tagging. Unreadable git history fails closed.
    """
    return _release_prep_check(Path(root), base, fetch)[0]


def main(root=None, latest=False, fetch=None, *, latest_if_release_prep=False, base=None):
    """Check `root` (the current directory by default) and report every copy that disagrees."""
    root = Path.cwd() if root is None else Path(root)
    release_prep = False
    if latest_if_release_prep:
        failures, release_prep = _release_prep_check(root, base, fetch)
    else:
        failures = check_latest(root, fetch) if latest else check(root)
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    if latest or release_prep:
        print("ForeverCore pin: the pin names core's latest published release, and the bundle agrees")
    elif latest_if_release_prep:
        print("ForeverCore pin: no new CHANGELOG.md version heading against base; the bundle agrees offline")
    else:
        print("ForeverCore pin: the pin, the .pkgmeta external and the TOC field agree, or this addon bundles no core")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd(), help="the consumer checkout (default: .)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--latest",
        action="store_true",
        help="also require the pin to name cjber/forever-core's latest published release (the release gate)",
    )
    mode.add_argument(
        "--latest-if-release-prep",
        action="store_true",
        help=(
            "require the pin to name core's latest release only when CHANGELOG.md adds a version heading against --base"
        ),
    )
    parser.add_argument(
        "--base",
        help="git base ref to compare CHANGELOG.md against (required with --latest-if-release-prep)",
    )
    arguments = parser.parse_args(argv)
    if arguments.latest_if_release_prep and not arguments.base:
        parser.error("--latest-if-release-prep requires --base")
    if arguments.base and not arguments.latest_if_release_prep:
        parser.error("--base is only used with --latest-if-release-prep")
    return arguments


if __name__ == "__main__":
    arguments = parse_args()
    sys.exit(
        main(
            arguments.root,
            arguments.latest,
            latest_if_release_prep=arguments.latest_if_release_prep,
            base=arguments.base,
        )
    )
