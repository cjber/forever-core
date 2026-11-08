#!/usr/bin/env python3
"""Fetch every CurseForge comment and reply (all pages) for the Forever addons.

Seen comment IDs live outside any checkout, under
${XDG_STATE_HOME:-~/.local/state}/forever-core/cfwatch-seen.json. `--unanswered` lists top-level
comments with no reply from the owner instead of unseen comments.
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


def unanswered(flat):
    """Top-level comments with no owner reply whose parentId matches them."""
    answered = {comment["parentId"] for comment in flat if is_owner(comment) and comment.get("parentId") is not None}
    return sorted(
        (comment for comment in flat if not comment.get("parentId") and comment["id"] not in answered),
        key=lambda comment: comment["datePosted"],
    )


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
    comments, totals, new = {}, {}, []
    for slug, mod_id in MODS.items():
        items, total = fetch_mod(fetch, mod_id)
        flat = flatten(items)
        comments[slug] = flat
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
        rows = [
            (comment["datePosted"], slug, comment) for slug, flat in comments.items() for comment in unanswered(flat)
        ]
        for _, slug, comment in sorted(rows, key=lambda row: row[0]):
            print(format_comment(slug, comment))
        print(f"\n{len(rows)} unanswered")
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
