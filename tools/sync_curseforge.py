"""Publish each addon's `docs/curseforge.md` from `origin/main` as its CurseForge project description.

CurseForge's upload API covers files only, so the description is set through the author site in the user's own
signed-in Chrome, driven by fastbrowse's extension. Each push is then read back through cfwidget (api.cfwidget.com),
because the author site's "Changes saved successfully" toast also shows for edits it did not store: the run passes only
when the stored description links exactly the URLs the markdown links.

A state file remembers the hash of the markdown last published per project, so a plain run pushes only addons whose
description changed on `main`. Run it after merging a PR that touches `docs/curseforge.md`:

    python3 tools/sync_curseforge.py ~/drive/proj/wow            # changed descriptions only
    python3 tools/sync_curseforge.py ~/drive/proj/wow --all      # every addon
    python3 tools/sync_curseforge.py ~/drive/proj/wow --check    # verify the stored descriptions, push nothing

fastbrowse reads `OPENROUTER_API_KEY` from the environment; the user's Chrome must have the fastbrowse extension and a
CurseForge sign-in. A failed read-back is retried with `--check` and pushed again by the next plain run.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
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


class _Urls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls: set[str] = set()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if (tag, name) in (("a", "href"), ("img", "src")) and value:
                self.urls.add(normalise(value))


def stored_links(addon: Addon) -> set[str]:
    """Every link and image URL in the description CurseForge stored, read through cfwidget, which needs no key."""
    request = Request(f"https://api.cfwidget.com/wow/addons/{addon.project_id}", headers={"User-Agent": "forever-core"})
    with urlopen(request, timeout=60) as response:
        html = json.load(response)["description"]
    parser = _Urls()
    parser.feed(html)
    return parser.urls


def verify(addon: Addon, markdown: str) -> tuple[bool, str]:
    live = stored_links(addon)
    want = expected_links(markdown)
    missing, extra = want - live, live - want
    if missing or extra:
        return False, f"missing {sorted(missing)} extra {sorted(extra)}"
    return True, "stored description links match"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("root", type=Path, help="folder holding the addon checkouts")
    parser.add_argument("--all", action="store_true", help="push every addon, not only changed descriptions")
    parser.add_argument("--check", action="store_true", help="verify the stored descriptions only")
    parser.add_argument("--only", nargs="*", default=[], help="repo folder names to limit the run to")
    args = parser.parse_args()

    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    failed = []
    for addon in addons(args.root):
        if args.only and addon.name not in args.only:
            continue
        markdown = addon.markdown()
        digest = hashlib.sha256(markdown.encode()).hexdigest()
        if not (args.check or args.all) and state.get(addon.project_id) == digest:
            print(f"{addon.name}: unchanged")
            continue
        if not args.check:
            result = push(addon, markdown)
            print(f"{addon.name}: push {result.get('status')}")
        ok, detail = verify(addon, markdown)
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
