#!/usr/bin/env python3
"""Fetch every CurseForge comment and reply (all pages) for the Forever addons.

Seen comment IDs live outside any checkout, under
${XDG_STATE_HOME:-~/.local/state}/forever-core/cfwatch-seen.json. `--unanswered` prints instead every
thread whose latest post is not the owner's: one never answered, or one followed up after the owner's last reply.
"""

import datetime
import json
import os
import subprocess
import sys
import time

MODS = {
    "shortest-path-forever": 1708599,
    "adventure-guide-forever": 1711538,
    "legacy-forever": 1705879,
    "skillup-forever": 1705762,
    "tweaks-forever": 1708506,
    "field-guide-forever": 1786835,
}
OWNER = "cjber"


def state_path():
    root = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(root, "forever-core", "cfwatch-seen.json")


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


def when(comment):
    posted = datetime.datetime.fromtimestamp(comment["datePosted"] / 1000, datetime.timezone.utc)
    return posted.strftime("%Y-%m-%d %H:%M")


def format_comment(slug, comment):
    parent = comment.get("parentId")
    reply = f" (reply to #{parent})" if parent else ""
    return f"\n[{slug}] #{comment['id']} {when(comment)} {author(comment)}{reply}:\n  {comment['text'].strip()}"


def main(argv=None, fetch=None):
    argv = sys.argv[1:] if argv is None else argv
    fetch = fetch or get
    mark = "--mark" in argv
    show_unanswered = "--unanswered" in argv

    path = state_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            seen = json.load(handle)
    else:
        seen = {}
    raw, totals, new = {}, {}, []
    for slug, mod_id in MODS.items():
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

    if show_unanswered:
        waiting = [(rows[-1]["datePosted"], slug, rows) for slug, items in raw.items() for _, rows in unanswered(items)]
        for _, slug, rows in sorted(waiting, key=lambda row: row[0]):
            print(f"\n=== [{slug}] thread #{rows[0]['id']}, {len(rows)} posts, latest {when(rows[-1])}")
            for comment in rows:
                print(format_comment(slug, comment))
        print(f"\n{len(waiting)} unanswered")
    else:
        for _, slug, comment in sorted(new, key=lambda row: row[0]):
            print(format_comment(slug, comment))
        print(f"\n{len(new)} unseen")

    if mark:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(seen, handle, indent=1)


if __name__ == "__main__":
    main()
