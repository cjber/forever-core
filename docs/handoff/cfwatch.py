#!/usr/bin/env python3
"""Fetch every CurseForge comment and reply (all pages) for the five addons; print ones not seen before."""
import json, os, subprocess, sys, time, datetime
MODS = {"shortest-path-forever":1708599,"adventure-guide-forever":1711538,"legacy-forever":1705879,
        "skillup-forever":1705762,"tweaks-forever":1708506}
HERE = os.path.dirname(os.path.abspath(__file__)); SEEN = os.path.join(HERE, "seen.json")
def get(url):
    for a in range(4):
        r = subprocess.run(["curl","-sS","-m","30","-H","Accept: application/json",url],capture_output=True,text=True)
        try: return json.loads(r.stdout)
        except Exception: time.sleep(2**a)
    raise SystemExit("fetch failed: "+url+" "+r.stdout[:200]+r.stderr[:200])
seen = json.load(open(SEEN)) if os.path.exists(SEEN) else {}
mark = "--mark" in sys.argv; new = []; totals = {}
for slug, mid in MODS.items():
    items, page = [], 0
    while True:
        d = get(f"https://www.curseforge.com/api/v1/mods/{mid}/comments?page={page}&pageSize=20&ts={int(time.time())}")
        data = d.get("data", []); items += data
        tot = d.get("pagination",{}).get("totalCount",0)
        page += 1
        if not data or page > 50: break
    flat = []
    for c in items:
        flat.append(c); flat += c.get("replies") or []
    totals[slug] = (tot, len(items), len(flat))
    uniq = {}
    for c in flat: uniq[c["id"]] = c
    totals[slug] = (tot, len(items), len(uniq))
    for c in uniq.values():
        k = str(c["id"])
        if k in seen: continue
        who = c["author"].get("displayName") or c["author"].get("username")
        when = datetime.datetime.fromtimestamp(c["datePosted"]/1000, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
        new.append((c["datePosted"], slug, who, when, c.get("parentId"), c["text"]))
        if mark: seen[k] = {"slug":slug,"who":who,"when":when}
for slug,(t,n,f) in totals.items(): print(f"# {slug}: totalCount={t} fetched_top={n} with_replies={f}")
for _, slug, who, when, parent, text in sorted(new):
    print(f"\n[{slug}] {when} {who}{' (reply to '+str(parent)+')' if parent else ''}:\n  {text.strip()}")
print(f"\n{len(new)} unseen")
if mark: json.dump(seen, open(SEEN,"w"), indent=1)
