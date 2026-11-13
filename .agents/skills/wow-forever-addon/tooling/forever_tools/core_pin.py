"""Keep the copies of a consumer's ForeverCore release in step, against core's latest published release.

A consumer that bundles core commits the release tag in three places: `tools/forever-core.txt` (the tag its specs and
CI check out), the `.pkgmeta` ForeverCore external (the zip the packager ships) and the root TOC's
`## X-Forever-Core:` field (the tag a sibling addon compares). The packager and the client each read their own copy
literally, so no build step can derive one from another; this module is the one comparison every copy is checked
against.

    python3 -m tools.forever_tools.core_pin [root]            the three copies name one release
    python3 -m tools.forever_tools.core_pin --latest [root]   and that release is core's latest published one

`--latest` is the release gate. It reads `cjber/forever-core`'s latest published GitHub release (with `GH_TOKEN` or
`GITHUB_TOKEN` when either is set) and fails closed when that release cannot be read, so an unknown latest release can
never pass a stale pin. The consumer's package job runs it, and its release workflow runs it again directly before the
packager uploads. A consumer whose `.pkgmeta` ships no ForeverCore external bundles no core, so the bundle comparison
is skipped; its pin is still checked against the latest release.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

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
    "check",
    "check_latest",
    "compare",
    "compare_latest",
    "core_external",
    "external_tag",
    "latest_release",
    "main",
    "pkgmeta_field",
    "toc_field",
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
    pkgmeta_path = root / PKGMETA
    if not pkgmeta_path.is_file():
        return failures
    pkgmeta = pkgmeta_path.read_text(encoding="utf-8", errors="replace")
    if not external_line(pkgmeta):
        return failures
    package = pkgmeta_field(pkgmeta, "package-as")
    toc_name = f"{package}.toc" if package else "the root TOC"
    toc_path = root / toc_name
    toc = toc_path.read_text(encoding="utf-8", errors="replace") if package and toc_path.is_file() else ""
    failures += compare(
        pin,
        pkgmeta,
        toc,
        pin_path=PIN_PATH,
        pkgmeta_path=PKGMETA,
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
    pkgmeta_path = root / PKGMETA
    pkgmeta = pkgmeta_path.read_text(encoding="utf-8", errors="replace") if pkgmeta_path.is_file() else ""
    if not (root / PIN_PATH).is_file() and not external_line(pkgmeta):
        return []
    try:
        latest = latest_release(fetch)
    except LatestReleaseUnavailable as error:
        return [
            f"{PIN_PATH}: could not read cjber/forever-core's latest published release ({error});"
            " refusing to pass the pin against an unknown release"
        ]
    return check(root, latest)


def main(root=None, latest=False, fetch=None):
    """Check `root` (the current directory by default) and report every copy that disagrees."""
    root = Path.cwd() if root is None else Path(root)
    failures = check_latest(root, fetch) if latest else check(root)
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    if latest:
        print("ForeverCore pin: the pin names core's latest published release, and the bundle agrees")
    else:
        print("ForeverCore pin: the pin, the .pkgmeta external and the TOC field agree, or this addon bundles no core")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd(), help="the consumer checkout (default: .)")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="also require the pin to name cjber/forever-core's latest published release (the release gate)",
    )
    arguments = parser.parse_args()
    sys.exit(main(arguments.root, arguments.latest))
