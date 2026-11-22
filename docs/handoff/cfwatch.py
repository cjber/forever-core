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
threads whose issues all closed as completed and whose fix is in a released tag, with that version, unless an owner
post in the thread is dated after that release, whether it is a top-level reply or nested at any depth. A player post
after that answer belongs to `--unanswered`, not `--due`. A release is found from the sibling checkout's git tags, not
one compare call per tag, and a closed issue's answer is cached in cfwatch-released.json beside the seen IDs, keyed by
its current close time so a reopened or reclosed issue recomputes.

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
RELEASED = "cfwatch-released.json"


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


def checkout(root, repo):
    """The local git checkout for `repo` under the suite folder, or None when it is not on this machine."""
    folder = Path(root) / repo
    return folder if (folder / ".git").exists() else None


def git(checkout, *args):
    """Run git in a sibling checkout; this reads ancestry and tags without spending a REST call."""
    return subprocess.run(
        ["git", "-C", str(checkout), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def tags_containing(checkout, sha, repository):
    """Every local tag whose history contains `sha`, or None when there is no usable checkout.

    Tags are fetched at most once per repository per run. `repository` is the run's cache entry for the repo. A failed
    fetch fails closed for that repository: stale tags never answer whether a release contains the fix.
    """
    if checkout is None or repository.get("fetch_failed"):
        return None
    if not repository["fetched"]:
        fetched = git(checkout, "fetch", "--tags", "--quiet")
        repository["fetched"] = True
        if fetched.returncode:
            repository["fetch_failed"] = True
            detail = f": {fetched.stderr.strip()}" if fetched.stderr.strip() else ""
            print(f"{checkout}: git fetch --tags failed{detail}; not using stale tags", file=sys.stderr)
            return None
    result = git(checkout, "tag", "--contains", sha, "--sort=creatordate")
    if result.returncode:
        return None
    return set(result.stdout.split())


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


def thread_of(items):
    """Every comment id in a thread, top-level or nested, to that thread's own id and all its posts.

    An issue filed from a comment records the id of the comment it came from, which is often a reply nested inside the
    thread rather than the thread's first post, so a link has to be read through the thread it belongs to.
    """
    index = {}
    for top, rows in threads(items):
        for row in rows:
            index[str(row["id"])] = (str(top["id"]), rows)
    return index


def unanswered(items):
    """Threads whose latest post is not the owner's: never answered, or followed up after the owner's last reply."""
    waiting = [(top, rows) for top, rows in threads(items) if not is_owner(rows[-1])]
    return sorted(waiting, key=lambda thread: thread[1][-1]["datePosted"])


def search_issues():
    """Every Forever issue that may carry a CurseForge thread line, open and closed.

    Asked of each watched repository on its own, because `gh search issues --owner` is one listing
    across an owner and a token scoped to a single repository owner cannot make it: the lookup then
    fails before a single thread is matched, and every thread reads as never filed.
    """
    issues = []
    for slug in slug_list():
        rows = gh_json(
            "issue",
            "list",
            "-R",
            f"{OWNER}/{slug}",
            "--state",
            "all",
            "--search",
            "CurseForge thread",
            "--limit",
            "1000",
            "--json",
            "number,state,body,closedAt",
        )
        for row in rows:
            row["repository"] = {"name": slug}
            issues.append(row)
    return issues


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


def released_in(repo, number, root=None, cache=None, releases=None) -> Release | None:
    """The first release that contains the merge of the PR that closed the issue, or None.

    An issue closed as not planned, still open, or fixed on main but not yet released answers None. The local checkout
    answers which tag contains the merge; `cache` remembers the answer per issue across runs, and `releases` holds each
    repository's release list for this run. The issue's current state and close time are read before a cached answer is
    used, so a reopened or reclosed issue is recomputed. A repository with no local checkout answers None, never a
    compare call.
    """
    key = f"{repo}#{number}"
    issue = gh_json("api", f"repos/{OWNER}/{repo}/issues/{number}")
    if issue.get("state") != "closed" or issue.get("state_reason") == "not_planned":
        if cache is not None:
            cache.pop(key, None)
        return None
    closed_at = issue.get("closed_at") or ""
    remembered = (cache or {}).get(key)
    if (
        isinstance(remembered, dict)
        and remembered.get("tag")
        and closed_at
        and remembered.get("closed_at") == closed_at
    ):
        return Release(remembered["tag"], remembered.get("published") or "")
    if cache is not None:
        cache.pop(key, None)
    events = gh_json("api", f"repos/{OWNER}/{repo}/issues/{number}/timeline", "--paginate")
    # Only a pull request in the issue's own repository can carry the fix into that repository's tags; a cross-repo
    # reference's number means a different pull request here. Every merged pull request that closed the issue is a
    # candidate, not just the last one: an issue fixed by an early PR and closed again by a later one names the release
    # that first carried any of them, which is the release that first shipped the fix.
    closing = []
    for event in events:
        source = (event.get("source") or {}).get("issue") or {}
        merged_at = (source.get("pull_request") or {}).get("merged_at")
        same_repo = (source.get("repository") or {}).get("full_name") == f"{OWNER}/{repo}"
        if event.get("event") == "cross-referenced" and same_repo and merged_at and merged_at <= closed_at:
            closing.append((merged_at, source.get("number")))
    shas = []
    close_sha = close_commit(events, closed_at)
    if close_sha:
        shas.append(close_sha)
    for _, pull in sorted(closing):
        merged_sha = gh_json("api", f"repos/{OWNER}/{repo}/pulls/{pull}").get("merge_commit_sha")
        if merged_sha and merged_sha not in shas:
            shas.append(merged_sha)
    if not shas:
        return None

    if releases is None:
        releases = {}
    repository = releases.setdefault(repo, {"rows": None, "fetched": False, "fetch_failed": False, "warned": False})
    suite = Path(root) if root is not None else suite_root()
    local = checkout(suite, repo)
    if local is None:
        if not repository["warned"]:
            print(f"{repo}: no local checkout under {suite}; --due cannot name its releases", file=sys.stderr)
            repository["warned"] = True
        return None
    containing = set()
    for candidate in shas:
        found_tags = tags_containing(local, candidate, repository)
        if found_tags:
            containing |= found_tags
    if not containing:
        return None
    if repository["rows"] is None:
        repository["rows"] = [
            release
            for release in gh_json("api", f"repos/{OWNER}/{repo}/releases?per_page=100")
            if not release.get("draft")
        ]
    found = next(
        (
            Release(release["tag_name"], release.get("published_at") or "")
            for release in sorted(repository["rows"], key=lambda release: release.get("published_at") or "")
            if release["tag_name"] in containing
        ),
        None,
    )
    if found is None:
        return None
    if cache is not None:
        cache[key] = {"tag": found.tag, "published": found.published, "closed_at": closed_at}
    return found


def moment(value):
    """A timezone-aware datetime for an API timestamp, or None when it is missing or unreadable."""
    try:
        parsed = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)


def close_commit(events, closed_at):
    """The commit_id of the close event at `closed_at`, or None when that closure had no commit.

    The latest close event is chosen before its commit is read, so a manual close after a reopen never falls back to
    an older close's commit; None then lets the cross-referenced pull request answer instead.
    """
    closed = [event for event in events if event.get("event") == "closed"]
    if not closed:
        return None
    current = moment(closed_at)
    if current is not None:
        for event in reversed(closed):
            created = moment(event.get("created_at"))
            if created is not None and created <= current:
                return event.get("commit_id")
    return closed[-1].get("commit_id")


def posted_after(comment, published):
    """True when the comment was posted later than the release's published timestamp."""
    release = moment(published)
    if release is None:
        return False
    return datetime.datetime.fromtimestamp(comment["datePosted"] / 1000, datetime.timezone.utc) > release


def answered_since(rows, published):
    """True when any owner post in the thread, at any depth, is dated after the release.

    A player post after that answer does not reopen the thread: it belongs to `--unanswered` instead.
    """
    return any(is_owner(comment) and posted_after(comment, published) for comment in rows)


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
    released_path = state_path(RELEASED)
    released_cache = load(released_path) if show_due else {}
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
        by_thread = {}
        for items in raw.values():
            by_thread.update(thread_of(items))
        root = suite_root() if links else None
        repositories = {}
        released = {}
        due = []
        answered = 0
        answered_threads = set()
        for thread, issues in links.items():
            versions = []
            for issue in issues:
                key = (issue["repo"], issue["number"])
                if key not in released:
                    released[key] = released_in(*key, root=root, cache=released_cache, releases=repositories)
                versions.append(released[key])
            if not all(versions):
                continue
            # An owner post after the release already answered the thread, so it is not due again, even when
            # the player has posted since (a thank-you belongs to --unanswered, not here).
            entry = by_thread.get(thread)
            shown, rows = entry if entry else (thread, [])
            # The issue was filed from the owner's own reply in the thread, so the player's post was already answered.
            linked = next((row for row in rows if str(row["id"]) == thread), None)
            shipped = max((version.published for version in versions if version.published), default="")
            if linked is not None and is_owner(linked) or answered_since(rows, shipped):
                answered += 1
                answered_threads.add(shown)
                continue
            for issue, version in zip(issues, versions, strict=True):
                due.append((shown, issue, version))
        for thread, issue, version in sorted(due, key=lambda row: (row[1]["slug"], int(row[0]))):
            print(
                f"[{issue['slug']}] thread #{thread}: cjber/{issue['repo']}#{issue['number']} released in {version.tag}"
            )
        due_threads = {thread for thread, _, _ in due}
        waiting = len(links) - len(due_threads | answered_threads)
        print(f"\n{len(due_threads)} due, {answered} answered, {waiting} still waiting")
        save(released_path, released_cache)
    else:
        for _, slug, comment in sorted(new, key=lambda row: row[0]):
            print(format_comment(slug, comment))
        print(f"\n{len(new)} unseen")

    if mark:
        save(path, seen)


if __name__ == "__main__":
    main()
