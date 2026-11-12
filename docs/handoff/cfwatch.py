#!/usr/bin/env python3
"""Fetch every CurseForge comment and reply (all pages) for the Forever addons.

Seen comment IDs live outside any checkout, under
${XDG_STATE_HOME:-~/.local/state}/forever-core/cfwatch-seen.json. `--unanswered` prints instead every
thread whose latest post is not the owner's: one never answered, or one followed up after the owner's last reply.

`--settle THREAD REASON` records that a thread needs no answer (a thank-you, a question another player answered).
Settled threads live beside the seen IDs in cfwatch-settled.json with the thread's latest post, so `--unanswered`
skips one only until somebody posts in it again.

An issue filed from a comment carries the line `CurseForge thread <id> (<addon>)`. `--unanswered` reads those lines
from every Forever issue and prints a linked thread as waiting on its issue and the issue's state. `--due` lists the
threads whose issues all closed as completed and whose fix is in a released tag, with that version, unless the owner
has already replied since that release.

The watched projects are every addon in `forever_tools.family.ADDONS` plus ForeverCore. Each project's ID comes from
its own root TOC's `## X-Curse-Project-ID` line, read from the sibling checkout, or through `gh api` when that
checkout is missing, so a new addon is watched with no list to keep here.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

CORE = Path(__file__).resolve().parents[2]
TOOLING = CORE / ".agents" / "skills" / "wow-forever-addon" / "tooling"
sys.path.insert(0, str(TOOLING))
sys.path.insert(0, str(CORE / "tools"))

from check_core_shared import CONSUMER_ROOT  # noqa: E402
from forever_tools.family import ADDONS  # noqa: E402

PROJECT_ID = re.compile(r"^## X-Curse-Project-ID:\s*(\d+)\s*$", re.MULTILINE)
LINK = re.compile(r"^CurseForge thread (\d+) \(([a-z0-9-]+)\)\s*$", re.MULTILINE)
OWNER = "cjber"


def state_path(name="cfwatch-seen.json"):
    root = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(root, "forever-core", name)


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1)


def build_parser():
    """The command line: the output modes, and each `--settle THREAD REASON` pair."""
    parser = argparse.ArgumentParser(
        prog=Path(__file__).name,
        description=__doc__.splitlines()[0],
        allow_abbrev=False,
    )
    parser.add_argument("--mark", action="store_true", help="remember every fetched comment as seen")
    parser.add_argument("--unanswered", action="store_true", help="print threads whose latest post is not the owner's")
    parser.add_argument("--due", action="store_true", help="print threads whose fix is in a released tag")
    parser.add_argument(
        "--settle",
        nargs=2,
        action="append",
        default=[],
        metavar=("THREAD", "REASON"),
        help="record that a thread needs no answer, until somebody posts in it again; repeatable",
    )
    return parser


def settle_requests(parser, values):
    """Each `--settle THREAD REASON` pair from the command line, as (thread id, reason)."""
    pairs = []
    for thread, reason in values:
        if not thread.lstrip("#").isdigit() or not reason.strip():
            parser.error("--settle needs a thread id and a reason")
        pairs.append((thread.lstrip("#"), reason))
    return pairs


def get(url):
    for attempt in range(4):
        result = subprocess.run(
            ["curl", "-sS", "-m", "30", "-H", "Accept: application/json", url], capture_output=True, text=True
        )
        try:
            return json.loads(result.stdout)
        except Exception:
            time.sleep(2**attempt)
    raise SystemExit("fetch failed: " + url + " " + result.stdout[:200] + result.stderr[:200])


def suite_root():
    """The folder that holds this checkout and its siblings: the main worktree's parent, else this checkout's parent."""
    result = subprocess.run(
        ["git", "-C", str(CORE), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    first = result.stdout.splitlines()[0] if result.returncode == 0 and result.stdout else ""
    if first.startswith("worktree "):
        return Path(first[len("worktree ") :]).parent
    return CORE.parent


def slug_list():
    """Every published Forever addon, then ForeverCore itself."""
    return [slug for _, slug, _ in ADDONS] + ["forever-core"]


def toc_folder(root, slug):
    """The checkout folder whose root TOC names the CurseForge project."""
    return Path(root) / slug / CONSUMER_ROOT.get(slug, "")


def local_toc(root, slug):
    """The single root TOC in the sibling checkout, or None when the checkout is not there."""
    folder = toc_folder(root, slug)
    tocs = sorted(folder.glob("*.toc")) if folder.is_dir() else []
    if len(tocs) > 1:
        names = [toc.name for toc in tocs]
        raise SystemExit(f"{folder}: more than one TOC, so X-Curse-Project-ID is ambiguous: {names}")
    return tocs[0] if tocs else None


def gh(*args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if result.returncode:
        raise SystemExit(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def gh_json(*args):
    return json.loads(gh(*args))


def github_toc(slug):
    """A sibling checkout's root TOC, fetched from cjber/<slug> when the checkout is not on this machine."""
    folder = CONSUMER_ROOT.get(slug, "")
    listing = f"repos/{OWNER}/{slug}/contents" + (f"/{folder}" if folder else "")
    entries = json.loads(gh("api", listing))
    tocs = [entry["path"] for entry in entries if entry.get("type") == "file" and entry["name"].endswith(".toc")]
    if len(tocs) != 1:
        raise SystemExit(f"cjber/{slug}: expected one root TOC, found {tocs}")
    return gh("api", "-H", "Accept: application/vnd.github.raw", f"repos/{OWNER}/{slug}/contents/{tocs[0]}")


def project_id(slug, text, source):
    match = PROJECT_ID.search(text)
    if not match:
        raise SystemExit(f"{source}: {slug} has no ## X-Curse-Project-ID line in its root TOC")
    return int(match.group(1))


def projects(root=None, remote=None):
    """Every watched CurseForge project as slug -> id, ids read from each addon's root TOC."""
    root = suite_root() if root is None else Path(root)
    remote = github_toc if remote is None else remote
    found = {}
    for slug in slug_list():
        toc = local_toc(root, slug)
        if toc is not None:
            found[slug] = project_id(slug, toc.read_text(encoding="utf-8"), toc)
        else:
            found[slug] = project_id(slug, remote(slug), f"cjber/{slug}")
    return found


def fetch_mod(fetch, mod_id):
    """Every top-level comment on one project, across all pages, plus the API's total count."""
    items, page, total = [], 0, 0
    while True:
        url = f"https://www.curseforge.com/api/v1/mods/{mod_id}/comments?page={page}&pageSize=20&ts={int(time.time())}"
        data = fetch(url)
        rows = data.get("data", [])
        items += rows
        total = data.get("pagination", {}).get("totalCount", 0)
        page += 1
        if not rows or page > 50:
            break
    return items, total


def flatten(items):
    """Every top-level comment and every reply at any depth, in API order."""
    flat = []
    for comment in items:
        flat.append(comment)
        flat += flatten(comment.get("replies") or [])
    return flat


def unique(flat):
    return {comment["id"]: comment for comment in flat}


def author(comment):
    writer = comment.get("author") or {}
    return writer.get("displayName") or writer.get("username") or "(unknown)"


def is_owner(comment):
    writer = comment.get("author") or {}
    names = {str(writer.get("username") or "").casefold(), str(writer.get("displayName") or "").casefold()}
    return OWNER.casefold() in names


def threads(items):
    """Every thread as its top-level comment and all its posts, oldest first.

    A post belongs to the thread it is nested under; a reply the API returns at the top level joins its thread through
    `parentId`, followed up to the top-level comment.
    """
    parent = {}

    def walk(rows, above):
        for row in rows:
            parent[row["id"]] = above if above is not None else row.get("parentId")
            walk(row.get("replies") or [], row["id"])

    walk(items, None)
    posts = unique(flatten(items))

    def root(comment_id):
        seen = set()
        while parent.get(comment_id) is not None and parent[comment_id] in posts and comment_id not in seen:
            seen.add(comment_id)
            comment_id = parent[comment_id]
        return comment_id

    grouped = {}
    for comment_id, comment in posts.items():
        grouped.setdefault(root(comment_id), []).append(comment)
    return [
        (posts[top], sorted(rows, key=lambda row: row["datePosted"]))
        for top, rows in grouped.items()
        if not posts[top].get("parentId")
    ]


def unanswered(items):
    """Threads whose latest post is not the owner's: never answered, or followed up after the owner's last reply."""
    waiting = [(top, rows) for top, rows in threads(items) if not is_owner(rows[-1])]
    return sorted(waiting, key=lambda thread: thread[1][-1]["datePosted"])


def search_issues():
    """Every Forever issue that may carry a CurseForge thread line, open and closed."""
    return gh_json(
        "search",
        "issues",
        "CurseForge thread",
        "--owner",
        OWNER,
        "--limit",
        "1000",
        "--json",
        "repository,number,state,body,closedAt",
    )


def linked_issues(search=None):
    """Thread id -> the issues that name it, from the exact line `CurseForge thread <id> (<addon>)`."""
    search = search_issues if search is None else search
    linked = {}
    for issue in search():
        repo = issue["repository"]["name"]
        for thread, slug in LINK.findall(issue.get("body") or ""):
            linked.setdefault(thread, []).append(
                {
                    "repo": repo,
                    "slug": slug,
                    "number": issue["number"],
                    "state": issue.get("state") or "open",
                    "closed_at": issue.get("closedAt") or "",
                }
            )
    return linked


class Release(NamedTuple):
    """A published release tag and the moment it was published."""

    tag: str
    published: str


def released_in(repo, number) -> Release | None:
    """The first release that contains the merge of the PR that closed the issue, or None.

    An issue closed as not planned, still open, or fixed on main but not yet released answers None.
    """
    issue = gh_json("api", f"repos/{OWNER}/{repo}/issues/{number}")
    if issue.get("state") != "closed" or issue.get("state_reason") == "not_planned":
        return None
    closed_at = issue.get("closed_at") or ""
    events = gh_json("api", f"repos/{OWNER}/{repo}/issues/{number}/timeline", "--paginate")
    sha = next(
        (event.get("commit_id") for event in events if event.get("event") == "closed" and event.get("commit_id")), None
    )
    closing = []
    for event in events:
        source = (event.get("source") or {}).get("issue") or {}
        merged_at = (source.get("pull_request") or {}).get("merged_at")
        if event.get("event") == "cross-referenced" and merged_at and merged_at <= closed_at:
            closing.append((merged_at, source.get("number")))
    if sha is None and closing:
        sha = gh_json("api", f"repos/{OWNER}/{repo}/pulls/{max(closing)[1]}").get("merge_commit_sha")
    if not sha:
        return None
    releases = [
        release for release in gh_json("api", f"repos/{OWNER}/{repo}/releases?per_page=100") if not release.get("draft")
    ]
    for release in sorted(releases, key=lambda release: release.get("published_at") or ""):
        status = gh_json("api", f"repos/{OWNER}/{repo}/compare/{sha}...{release['tag_name']}").get("status")
        if status in ("ahead", "identical"):
            return Release(release["tag_name"], release.get("published_at") or "")
    return None


def moment(value):
    """A timezone-aware datetime for an API timestamp, or None when it is missing or unreadable."""
    try:
        parsed = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)


def posted_after(comment, published):
    """True when the comment was posted later than the release's published timestamp."""
    release = moment(published)
    if release is None:
        return False
    return datetime.datetime.fromtimestamp(comment["datePosted"] / 1000, datetime.timezone.utc) > release


def when(comment):
    posted = datetime.datetime.fromtimestamp(comment["datePosted"] / 1000, datetime.timezone.utc)
    return posted.strftime("%Y-%m-%d %H:%M")


def format_comment(slug, comment):
    parent = comment.get("parentId")
    reply = f" (reply to #{parent})" if parent else ""
    return f"\n[{slug}] #{comment['id']} {when(comment)} {author(comment)}{reply}:\n  {comment['text'].strip()}"


def main(argv=None, fetch=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    arguments = parser.parse_args(argv)
    requests = settle_requests(parser, arguments.settle)
    fetch = fetch or get
    mark = arguments.mark
    show_unanswered = arguments.unanswered
    show_due = arguments.due

    path = state_path()
    seen = load(path)
    settled_path = state_path("cfwatch-settled.json")
    settled = load(settled_path)
    raw, totals, new = {}, {}, []
    for slug, mod_id in projects().items():
        items, total = fetch_mod(fetch, mod_id)
        flat = flatten(items)
        raw[slug] = items
        fresh = unique(flat)
        totals[slug] = (total, len(items), len(fresh))
        for comment in fresh.values():
            key = str(comment["id"])
            if key in seen:
                continue
            new.append((comment["datePosted"], slug, comment))
            if mark:
                seen[key] = {"slug": slug, "who": author(comment), "when": when(comment)}

    for slug, (total, top, flat_count) in totals.items():
        print(f"# {slug}: totalCount={total} fetched_top={top} with_replies={flat_count}")

    if requests:
        found = {str(top["id"]): (slug, rows) for slug, items in raw.items() for top, rows in threads(items)}
        for thread, reason in requests:
            if thread not in found:
                raise SystemExit(f"no thread #{thread} on the watched projects")
            slug, rows = found[thread]
            settled[thread] = {"slug": slug, "latest": rows[-1]["id"], "reason": reason, "when": when(rows[-1])}
            print(f"settled [{slug}] thread #{thread}: {reason}")
        save(settled_path, settled)

    if show_unanswered:
        links = linked_issues()
        waiting, quiet, on_issue = [], 0, 0
        for slug, items in raw.items():
            for _, rows in unanswered(items):
                entry = settled.get(str(rows[0]["id"]))
                if entry and entry.get("latest") == rows[-1]["id"]:
                    quiet += 1
                    continue
                issues = links.get(str(rows[0]["id"]))
                if issues:
                    on_issue += 1
                    print(f"\n=== [{slug}] thread #{rows[0]['id']}, {len(rows)} posts, latest {when(rows[-1])}")
                    for issue in issues:
                        print(f"waiting on cjber/{issue['repo']}#{issue['number']} ({issue['state']})")
                    continue
                waiting.append((rows[-1]["datePosted"], slug, rows))
        for _, slug, rows in sorted(waiting, key=lambda row: row[0]):
            print(f"\n=== [{slug}] thread #{rows[0]['id']}, {len(rows)} posts, latest {when(rows[-1])}")
            for comment in rows:
                print(format_comment(slug, comment))
        print(f"\n{len(waiting)} unanswered, {on_issue} waiting on an issue, {quiet} settled")
    elif show_due:
        links = linked_issues()
        by_thread = {str(top["id"]): rows for items in raw.values() for top, rows in threads(items)}
        released = {}
        due = []
        answered = 0
        for thread, issues in links.items():
            versions = []
            for issue in issues:
                key = (issue["repo"], issue["number"])
                if key not in released:
                    released[key] = released_in(*key)
                versions.append(released[key])
            if not all(versions):
                continue
            # An owner reply after the release already answered the thread, so it is not due again.
            rows = by_thread.get(thread)
            latest = rows[-1] if rows else None
            shipped = max((version.published for version in versions if version.published), default="")
            if latest and is_owner(latest) and posted_after(latest, shipped):
                answered += 1
                continue
            for issue, version in zip(issues, versions, strict=True):
                due.append((thread, issue, version))
        for thread, issue, version in sorted(due, key=lambda row: (row[1]["slug"], int(row[0]))):
            print(
                f"[{issue['slug']}] thread #{thread}: cjber/{issue['repo']}#{issue['number']} released in {version.tag}"
            )
        due_threads = {thread for thread, _, _ in due}
        waiting = len(links) - len(due_threads) - answered
        print(f"\n{len(due_threads)} due, {answered} answered, {waiting} still waiting")
    else:
        for _, slug, comment in sorted(new, key=lambda row: row[0]):
            print(format_comment(slug, comment))
        print(f"\n{len(new)} unseen")

    if mark:
        save(path, seen)


if __name__ == "__main__":
    main()
