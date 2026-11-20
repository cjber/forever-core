"""Hold an embedded-core release until every Forever addon carries its own ForeverCore.

While any published addon still ships the shared top-level `ForeverCore` folder, removing or downgrading that addon
deletes or rolls back core under the others (cjber/forever-core#448). So an addon whose root TOC opts in with
`## X-Forever-Core-Embed: 1` releases only once every addon in `EMBED_FLEET` has opted in on its own `main`; after that
the release train releases them together (core's `tools/release_consumers.py` dispatches them as one batch).

    python3 -m tools.forever_tools.fleet [root]

A consumer's own release workflow runs this before the packager, so a hand-run release or a pushed tag holds too. It
passes at once for a checkout that does not embed core. Each addon's root TOC is read from its public `main` on
raw.githubusercontent.com, resolved as the packager resolves it (`core_pin.toc_name_for`). A read that fails is a
failure, never a pass. `GH_TOKEN` or `GITHUB_TOKEN`, when set, is sent only to api.github.com, for the one listing an
addon without `package-as` needs.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import core_pin
from . import pkgmeta as pkgmeta_reader

__all__ = ["EMBED_FLEET", "FleetUnreadable", "check", "main", "missing", "opted_in"]

OWNER = "cjber"
# The published addons that embed ForeverCore under Libs/ForeverCore.
EMBED_FLEET = (
    "adventure-guide-forever",
    "commissions-forever",
    "field-guide-forever",
    "legacy-forever",
    "macro-assist-forever",
    "shortest-path-forever",
    "skillup-forever",
    "tweaks-forever",
)


class FleetUnreadable(RuntimeError):
    """An addon's policy or root TOC could not be read, so the hold cannot be lifted."""


def opted_in(read, list_tocs):
    """Whether one addon's root TOC opts in, from `read(path) -> text | None` and `list_tocs() -> [names]`.

    The policy is `.pkgmeta`, else `pkgmeta.yaml`; the TOC is the one `package-as` names, else the packager's fallback.
    A missing TOC or an unresolvable policy raises FleetUnreadable.
    """
    policy = next((text for name in pkgmeta_reader.FILES if (text := read(name)) is not None), "")
    try:
        package = core_pin.policy_package(policy)
        name = core_pin.toc_name_for(package, [] if package else list_tocs())
    except ValueError as error:
        raise FleetUnreadable(str(error)) from None
    if name is None:
        return False
    toc = read(name)
    if toc is None:
        raise FleetUnreadable(f"no {name}")
    return core_pin.embeds(toc)


def missing(fleet_reader, fleet=EMBED_FLEET):
    """The fleet addons not opted in yet; `fleet_reader(repo)` returns that addon's `(read, list_tocs)`."""
    out = []
    for repo in fleet:
        read, list_tocs = fleet_reader(repo)
        try:
            if not opted_in(read, list_tocs):
                out.append(repo)
        except FleetUnreadable as error:
            raise FleetUnreadable(f"{repo}: {error}") from None
    return out


def _get(url, token=None):
    request = urllib.request.Request(url, headers={"User-Agent": "forever-fleet-hold"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8-sig", "replace")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise FleetUnreadable(f"{url}: HTTP {error.code}") from None
    except (OSError, urllib.error.URLError, TimeoutError) as error:
        raise FleetUnreadable(f"{url}: {error}") from None


def remote(repo, branch="main"):
    """`(read, list_tocs)` for one addon's public `branch`."""

    def read(path):
        return _get(f"https://raw.githubusercontent.com/{OWNER}/{repo}/{branch}/{path}")

    def list_tocs():
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        text = _get(f"https://api.github.com/repos/{OWNER}/{repo}/contents?ref={branch}", token)
        if text is None:
            raise FleetUnreadable(f"{repo}: no {branch} branch")
        try:
            return [entry["name"] for entry in json.loads(text) if entry.get("name", "").endswith(".toc")]
        except (ValueError, TypeError, KeyError) as error:
            raise FleetUnreadable(f"{repo}: unreadable listing: {error}") from None

    return read, list_tocs


def local(root):
    """`(read, list_tocs)` for a checkout on disk."""
    root = Path(root)

    def read(path):
        target = root / path
        return target.read_text(encoding="utf-8-sig", errors="replace") if target.is_file() else None

    return read, lambda: [path.name for path in root.glob("*.toc")]


def check(root, fleet_reader=remote):
    """Failures holding `root`'s release: none when it does not embed core or every fleet addon has opted in."""
    try:
        if not opted_in(*local(root)):
            return []
        waiting = missing(fleet_reader)
    except FleetUnreadable as error:
        return [f"embedded ForeverCore release hold: could not read {error}; refusing to release"]
    if not waiting:
        return []
    return [
        "embedded ForeverCore release hold: every Forever addon must embed ForeverCore on main before any of them"
        " releases (cjber/forever-core#448); not yet: " + ", ".join(waiting)
    ]


def main(root=None, fleet_reader=remote):
    failures = check(Path.cwd() if root is None else root, fleet_reader)
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    print("embedded ForeverCore release hold: clear")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd(), help="the consumer checkout (default: .)")
    sys.exit(main(parser.parse_args().root))
