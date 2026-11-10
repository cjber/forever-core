"""Publish each addon's `docs/curseforge.md` from `origin/main` as its CurseForge project description.

CurseForge's upload API covers files only, so the description is set through the author site in the user's own
signed-in Chrome, driven by fastbrowse's extension. Each push is then read back from CurseForge's Core API, because
the author site's "Changes saved successfully" toast also shows for edits it did not store: the run passes only
when the stored description has exactly the markdown's words, in order, and links exactly its URLs. Links alone are
not enough, since a description stored twice over carries the same URLs.

A plain run only reads each stored description back and compares it with `main`. Pushing is opt-in with `--push`,
because the fastbrowse extension run saves wrong text for some pages (agent-labs-dev/fastbrowse#939): until that is
fixed, paste failing descriptions by hand and rerun the check. A state file remembers the hash of the markdown last
published per project, so `--push` pushes only addons whose description changed on `main`:

    export CURSEFORGE_CORE_API_KEY=$(pass show dev/CURSEFORGE_CORE_API_KEY)
    python3 tools/sync_curseforge.py ~/drive/proj/wow                 # verify every stored description
    python3 tools/sync_curseforge.py ~/drive/proj/wow --push          # push changed descriptions, then verify
    python3 tools/sync_curseforge.py ~/drive/proj/wow --push --all    # push every addon

fastbrowse reads `OPENROUTER_API_KEY` from the environment; the user's Chrome must have the fastbrowse extension and a
CurseForge sign-in. The read-back needs `CURSEFORGE_CORE_API_KEY` (pass `dev/CURSEFORGE_CORE_API_KEY`), a key from
https://console.curseforge.com/. cfwidget is not used for it: it serves a cached copy that lags a fresh save.
"""

import argparse
import difflib
import hashlib
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

STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "forever-core/curseforge-sync.json"
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


def fastbrowse(task: str, start: str) -> dict:
    command = ["fastbrowse", task, "--start", start, "--extension", "--authorize", "--json"]
    run = subprocess.run(command, capture_output=True, text=True, timeout=900)
    try:
        return json.loads(run.stdout)
    except json.JSONDecodeError:
        return {"status": "error", "answer": run.stderr[-2000:]}


def push(addon: Addon, markdown: str) -> dict:
    task = (
        f"Replace the CurseForge project description of project {addon.project_id} with the exact markdown between "
        "MARKDOWN START and MARKDOWN END, and save it. The description editor is a markdown textarea "
        "(textarea.mde-text): replace all of its text with the markdown, then click into the textarea, press ctrl+End "
        "and type one newline with real key input, because setting the value alone does not register. Then click "
        "Save. Change nothing else on the project.\n\nMARKDOWN START\n" + markdown + "MARKDOWN END"
    )
    return fastbrowse(task, f"https://authors.curseforge.com/#/projects/{addon.project_id}/description")


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
    parser.add_argument("--push", action="store_true", help="push descriptions through fastbrowse before verifying")
    parser.add_argument("--all", action="store_true", help="with --push, push every addon, not only changed ones")
    parser.add_argument("--only", nargs="*", default=[], help="repo folder names to limit the run to")
    args = parser.parse_args()

    key = os.environ.get("CURSEFORGE_CORE_API_KEY")
    if not key:
        parser.error("set CURSEFORGE_CORE_API_KEY: a CurseForge Core API key reads each description back")
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    failed = []
    for addon in addons(args.root):
        if args.only and addon.name not in args.only:
            continue
        markdown = addon.markdown()
        digest = hashlib.sha256(markdown.encode()).hexdigest()
        if args.push and not args.all and state.get(addon.project_id) == digest:
            print(f"{addon.name}: unchanged")
            continue
        if args.push:
            result = push(addon, markdown)
            print(f"{addon.name}: push {result.get('status')}")
        ok, detail = verify(addon, markdown, key)
        print(f"{addon.name}: {'ok' if ok else 'FAILED'}, {detail}")
        if ok:
            state[addon.project_id] = digest
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps(state, indent=2) + "\n")
        else:
            failed.append(addon.name)
    if failed:
        print("failed: " + ", ".join(failed), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
