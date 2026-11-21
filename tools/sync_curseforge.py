"""Check each addon's CurseForge project description against its `docs/curseforge.md` on `origin/main`.

CurseForge has no API to write a description, so a changed `docs/curseforge.md` is pasted on the author site with
Claude in Chrome (the recipe is in the `wow-addon-publish` skill under "Descriptions"). This script reads every stored
description back from CurseForge's Core API and fails when any word, link or image URL differs from `main`. The author
site's "Changes saved successfully" toast also shows for edits it did not store, so this read-back is the proof. The
`store-descriptions` workflow runs it daily and goes red on a stale page:

    export CURSEFORGE_CORE_API_KEY=$(pass show dev/CURSEFORGE_CORE_API_KEY)
    python3 tools/sync_curseforge.py ~/drive/proj/wow                      # every addon checkout in the folder
    python3 tools/sync_curseforge.py ~/drive/proj/wow --only tweaks-forever

The key is from https://console.curseforge.com/. The Core API lags a save by a minute or two. cfwidget is not used:
its cached copy lags further.
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import uuid
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

MARKER = "forever-family"  # comment lines the family sync keeps in the file; they are not description text
LINK = re.compile(r"\]\((https?://[^)\s]+)\)")
PROJECT_ID = re.compile(r"^## X-Curse-Project-ID:\s*(\d+)\s*$", re.M)


class Addon:
    def __init__(self, repo: Path):
        self.repo = repo
        self.name = repo.name
        toc = next(t for t in sorted(repo.glob("*.toc")) if PROJECT_ID.search(t.read_text(encoding="utf-8")))
        self.project_id = PROJECT_ID.search(toc.read_text(encoding="utf-8")).group(1)

    def markdown(self) -> str:
        subprocess.run(["git", "-C", self.repo, "fetch", "-q", "origin", "main"], check=True)
        text = subprocess.run(
            ["git", "-C", self.repo, "show", "origin/main:docs/curseforge.md"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        return "".join(line for line in text.splitlines(keepends=True) if MARKER not in line)


def addons(root: Path) -> list[Addon]:
    found = []
    for repo in sorted(p for p in root.iterdir() if (p / ".git").exists() and (p / "docs/curseforge.md").exists()):
        if any(PROJECT_ID.search(t.read_text(encoding="utf-8")) for t in repo.glob("*.toc")):
            found.append(Addon(repo))
    return found


def expected_links(markdown: str) -> set[str]:
    return {normalise(url) for url in LINK.findall(markdown)}


def normalise(url: str) -> str:
    """CurseForge wraps outgoing links in its linkout redirect, with the destination encoded twice; compare that."""
    parsed = urlparse(url)
    if parsed.path.rstrip("/").endswith("/linkout"):
        url = unquote(parse_qs(parsed.query)["remoteUrl"][0])
    return url.rstrip("/")


def words(text: str) -> list[str]:
    """The words a reader sees, lower case: markdown comments, images, link targets and markup characters go."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#*_`|>\-]+", " ", unescape(text))
    return re.findall(r"\w+", text.replace("\u2019", "").replace("'", "").lower())


class _Stored(HTMLParser):
    """The link and image URLs and the visible text of a stored description."""

    def __init__(self):
        super().__init__()
        self.urls: set[str] = set()
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if (tag, name) in (("a", "href"), ("img", "src")) and value:
                self.urls.add(normalise(value))

    def handle_data(self, data):
        self.text.append(data)


def stored(addon: Addon, key: str) -> _Stored:
    """The description CurseForge stored, read from its Core API."""
    request = Request(
        f"https://api.curseforge.com/v1/mods/{addon.project_id}/description",
        # CloudFront caches this endpoint for minutes, keyed partly on User-Agent and not on the query string, so a
        # User-Agent of its own per request is what reads the description as stored now.
        headers={"x-api-key": key, "Accept": "application/json", "User-Agent": f"forever-core/{uuid.uuid4()}"},
    )
    with urlopen(request, timeout=60) as response:
        html = json.load(response)["data"]
    parser = _Stored()
    parser.feed(html)
    return parser


def compare(markdown: str, live: _Stored) -> tuple[bool, str]:
    want, got = words(markdown), words(" ".join(live.text))
    if want != got:
        matcher = difflib.SequenceMatcher(None, want, got, autojunk=False)
        _, i1, i2, j1, j2 = next(op for op in matcher.get_opcodes() if op[0] != "equal")
        return False, (
            f"words differ ({len(want)} expected, {len(got)} stored), first at word {i1}: "
            f"expected {' '.join(want[i1:i2])[:200]!r}, stored {' '.join(got[j1:j2])[:200]!r}"
        )
    links = expected_links(markdown)
    missing, extra = links - live.urls, live.urls - links
    if missing or extra:
        return False, f"missing {sorted(missing)} extra {sorted(extra)}"
    return True, "stored description matches word for word"


def verify(addon: Addon, markdown: str, key: str) -> tuple[bool, str]:
    return compare(markdown, stored(addon, key))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("root", type=Path, help="folder holding the addon checkouts")
    parser.add_argument("--only", nargs="*", default=[], help="repo folder names to limit the run to")
    args = parser.parse_args()

    key = os.environ.get("CURSEFORGE_CORE_API_KEY")
    if not key:
        parser.error("set CURSEFORGE_CORE_API_KEY: a CurseForge Core API key reads each description back")
    failed = []
    for addon in addons(args.root):
        if args.only and addon.name not in args.only:
            continue
        ok, detail = verify(addon, addon.markdown(), key)
        print(f"{addon.name}: {'ok' if ok else 'FAILED'}, {detail}")
        if not ok:
            failed.append(addon.name)
    if failed:
        print("failed: " + ", ".join(failed), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
