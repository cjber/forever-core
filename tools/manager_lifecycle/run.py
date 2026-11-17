#!/usr/bin/env python3
"""Replay the shared-library lifecycle (forever-core#650) against a real addon manager.

Resets a disposable `_forever_` client and the app's own state, drives the app's UI over the
DevTools protocol, and after every step records the AddOns folders (TOC version and project
id, a content hash per folder), the app's installed-addon records and a screenshot.

  python3 run.py --app curseforge|wowup [--a ID] [--b ID] [--channel release|beta|alpha]
                 [--remove-deps no|yes] [--cf-libs-separate no|yes]

Scenarios:
  S1  install consumer A
  S2  install consumer B
  S3  uninstall A (remove-deps answers WowUp's prompt / sets CurseForge's
      "Delete orphaned libraries")
  S4a rescan the AddOns folder in the app
  S4b reinstall B
  S4c install or reinstall ForeverCore as its own addon
  S5  uninstall B

Update scenarios (--scenario U1..U5; A has a release that bundles ForeverCore and a newer
alpha that does not, declaring ForeverCore a required dependency instead):
  U1  release channel: install A and B, switch A alone to alpha, update A, refresh/rescan,
      Update All; then U6a: reinstall or install ForeverCore itself (core first), then reinstall A
  U2  release channel: install A only, switch A to alpha, update A, rescan, restart the app,
      Update All; then U6b: reinstall A (consumer first), then reinstall or install ForeverCore
  U3  alpha channel from the start: install A
  U4  alpha channel: install A, install B, delete A, delete B
  U5  alpha channel: install A, delete A (run with --remove-deps no and yes)

Output: reports/<UTC stamp>-<app>-<scenario>-<variant>/{report.json,report.md,*.png}.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import signal
import sys
import time
import traceback
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from . import apps, drivers

CORE_ID = 1796337
NAMES = {
    1796337: "ForeverCore",
    1795141: "Macro Assist Forever",
    1786835: "Field Guide Forever",
    1711538: "Adventure Guide Forever",
    1708599: "Shortest Path Forever",
    1705762: "SkillUp Forever",
    1708506: "Tweaks Forever",
    1705879: "Legacy Forever",
    1794367: "Commissions Forever",
}
ARCHIVES = Path(os.environ.get("MANAGER_LIFECYCLE_ARCHIVES", str(apps.ROOT / "archives"))).expanduser().resolve()
REPORTS = Path(os.environ.get("MANAGER_LIFECYCLE_REPORTS", str(apps.ROOT / "reports"))).expanduser().resolve()


def toc_fields(folder):
    out = {}
    for toc in sorted(folder.glob("*.toc")):
        f = {}
        for line in toc.read_text(errors="replace").splitlines():
            m = re.match(r"^##\s*([^:]+):\s*(.*)$", line)
            if m and m.group(1).strip() in (
                "Title",
                "Version",
                "X-Curse-Project-ID",
                "Interface",
                "Dependencies",
                "RequiredDeps",
            ):
                f[m.group(1).strip()] = m.group(2).strip()
        out[toc.name] = f
    return out


def tree_hash(folder):
    h = hashlib.sha256()
    for p in sorted(x for x in folder.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(folder)).encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()[:16]


def disk(folder=None):
    out = {}
    for f in sorted((folder or apps.ADDONS).iterdir()):
        if f.is_dir():
            out[f.name] = {
                "tocs": toc_fields(f),
                "tree_sha256_16": tree_hash(f),
                "files": sum(1 for x in f.rglob("*") if x.is_file()),
            }
    return out


def core_check(snapshot_disk, b_folder):
    core = snapshot_disk.get("ForeverCore")
    toc = (core or {}).get("tocs", {}).get("ForeverCore.toc", {})
    ok = bool(core and toc.get("Interface") and toc.get("X-Curse-Project-ID") == str(CORE_ID))
    b = snapshot_disk.get(b_folder or "", {})
    b_deps = [t.get("Dependencies", "") + t.get("RequiredDeps", "") for t in b.get("tocs", {}).values()]
    needs = any("ForeverCore" in x for x in b_deps)
    return {
        "core_present": bool(core),
        "core_toc_valid": ok,
        "core_version": toc.get("Version"),
        "b_present": bool(b),
        "b_requires_core": needs,
        "b_dependency_resolves": (not needs) or ok,
        "unmet_dependents": []
        if ok
        else sorted(
            n
            for n, v in snapshot_disk.items()
            if any("ForeverCore" in t.get("Dependencies", "") + t.get("RequiredDeps", "") for t in v["tocs"].values())
        ),
    }


def archive_info(url):
    """Download a release archive once (public CDN) and record its hashes and top-level folders."""
    if not url:
        return None
    ARCHIVES.mkdir(parents=True, exist_ok=True)
    m = re.search(r"/files/(\d+)/(\d+)/([^/?]+)$", url)
    name = f"{m.group(1)}{m.group(2)}-{m.group(3)}" if m else Path(url).name
    p = ARCHIVES / name
    if not p.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "manager-lifecycle-harness"})
        with urllib.request.urlopen(req, timeout=60) as r:
            p.write_bytes(r.read())
    data = p.read_bytes()
    with zipfile.ZipFile(p) as z:
        tops = sorted({n.split("/")[0] for n in z.namelist() if "/" in n})
        tocs = {}
        for n in z.namelist():
            if re.fullmatch(r"ForeverCore/ForeverCore\.toc", n):
                for line in z.read(n).decode(errors="replace").splitlines():
                    if line.startswith("## Version:"):
                        tocs["ForeverCore"] = line.split(":", 1)[1].strip()
    return {
        "url": url,
        "sha256": hashlib.sha256(data).hexdigest(),
        "sha1": hashlib.sha1(data).hexdigest(),
        "md5": hashlib.md5(data).hexdigest(),
        "bytes": len(data),
        "top_level_folders": tops,
        "bundled_core_version": tocs.get("ForeverCore"),
        "local_path": str(p),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", required=True, choices=sorted(drivers.DRIVERS))
    ap.add_argument("--a", type=int, default=1795141, help="consumer A project id (default Macro Assist Forever)")
    ap.add_argument("--b", type=int, default=1786835, help="consumer B project id (default Field Guide Forever)")
    ap.add_argument("--a-name", help="search name for A, if not in the built-in table")
    ap.add_argument("--b-name", help="search name for B")
    ap.add_argument("--channel", default="release", choices=["release", "beta", "alpha"], help="global release channel")
    ap.add_argument("--remove-deps", default="no", choices=["no", "yes"])
    ap.add_argument(
        "--cf-libs-separate", default="no", choices=["no", "yes"], help="CurseForge 'Install libraries separately'"
    )
    ap.add_argument("--scenario", default="lifecycle", choices=["lifecycle", "U1", "U2", "U3", "U4", "U5"])
    ap.add_argument("--only", help="comma list of steps to run, e.g. S1,S2,S3")
    o = ap.parse_args()

    def terminate(signum, _frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    apps.validate_paths()
    for path in (ARCHIVES, REPORTS):
        if apps.ROOT not in path.parents:
            raise ValueError(f"Evidence paths must be beneath MANAGER_LIFECYCLE_ROOT: {path}")
    if o.scenario in ("U3", "U4", "U5"):
        o.channel = "alpha"
    a_name = o.a_name or NAMES[o.a]
    b_name = o.b_name or NAMES[o.b]
    variant = (
        ("" if o.scenario == "lifecycle" else o.scenario + "-")
        + f"{o.channel}-deps{o.remove_deps}"
        + (f"-libsep{o.cf_libs_separate}" if o.app == "curseforge" else "")
    )
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    o.out = REPORTS / f"{stamp}-{o.app}-{variant}"
    o.out.mkdir(parents=True)

    report: dict[str, Any] = {
        "app": o.app,
        "params": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(o).items()},
        "consumer_a": {"id": o.a, "name": a_name},
        "consumer_b": {"id": o.b, "name": b_name},
        "started": stamp,
        "fake_client": str(apps.FOREVER),
        "steps": [],
        "archives": {},
    }
    print(f"report dir: {o.out}", flush=True)
    if apps.stop(o.app):
        raise RuntimeError("Manager processes remain; refusing to reset the disposable client")
    apps.reset_fake_client()
    drv = drivers.DRIVERS[o.app](o)
    b_folder = None

    def snap(step, title, result=None, error=None):
        time.sleep(2)
        d = disk()
        recs = drv.records()
        for r in recs:
            u = r.get("download_url")
            if u and u not in report["archives"]:
                try:
                    report["archives"][u] = archive_info(u)
                except Exception as e:  # noqa: BLE001 - evidence gathering must not abort a run
                    report["archives"][u] = {"url": u, "error": str(e)}
        shot = o.out / f"{step}.png"
        try:
            drv.shot(str(shot))
        except Exception as e:  # noqa: BLE001
            shot = Path(f"screenshot failed: {e}")
        entry = {
            "step": step,
            "title": title,
            "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "result": result,
            "error": error,
            "addons_folders": sorted(d),
            "disk": d,
            "records": recs,
            "app_view": drv.view(),
            "core_check": core_check(d, b_folder),
            "screenshot": str(shot),
        }
        report["steps"].append(entry)
        cc = entry["core_check"]
        print(
            f"{step}: folders={entry['addons_folders']} records={[(r['name'], r['file_id']) for r in recs]}"
            f" core_present={cc['core_present']} unmet={cc['unmet_dependents']}" + (f" ERROR {error}" if error else ""),
            flush=True,
        )
        (o.out / "report.json").write_text(json.dumps(report, indent=1))

    core = lambda: drv.install_core(CORE_ID, NAMES[CORE_ID])  # noqa: E731
    ins_a = ("install-A", f"install A ({a_name})", lambda: drv.install(o.a, a_name))
    ins_b = ("install-B", f"install B ({b_name})", lambda: drv.install(o.b, b_name))
    alpha_a = ("A-alpha", "switch A alone to the alpha channel", lambda: drv.set_channel(o.a, a_name, "alpha"))
    upd_a = ("update-A", "update A (to its newest alpha)", lambda: drv.update(o.a, a_name))
    rescan = ("rescan", "refresh / rescan the AddOns folder", lambda: drv.rescan())
    upd_all = ("update-all", "Update All", lambda: drv.update_all())
    del_a = ("delete-A", f"delete A, remove-deps={o.remove_deps}", lambda: drv.uninstall(o.a, a_name))
    del_b = ("delete-B", f"delete B, remove-deps={o.remove_deps}", lambda: drv.uninstall(o.b, b_name))
    SCEN = {
        "lifecycle": [
            ("S1", f"install A ({a_name})", lambda: drv.install(o.a, a_name)),
            ("S2", f"install B ({b_name})", lambda: drv.install(o.b, b_name)),
            ("S3", f"uninstall A ({a_name}), remove-deps={o.remove_deps}", lambda: drv.uninstall(o.a, a_name)),
            ("S4a", "rescan AddOns folder in the app", lambda: drv.rescan()),
            ("S4b", f"reinstall B ({b_name})", lambda: drv.reinstall(o.b, b_name)),
            ("S4c", "install or reinstall ForeverCore as its own addon", core),
            ("S5", f"uninstall B ({b_name})", lambda: drv.uninstall(o.b, b_name)),
        ],
        "U1": [
            ins_a,
            ins_b,
            alpha_a,
            upd_a,
            rescan,
            upd_all,
            ("U6a-core", "U6a core first: reinstall/install ForeverCore", core),
            ("U6a-A", "U6a then reinstall A", lambda: drv.reinstall(o.a, a_name)),
        ],
        "U2": [
            ins_a,
            alpha_a,
            upd_a,
            rescan,
            ("restart", "quit and relaunch the app", lambda: drv.restart()),
            upd_all,
            ("U6b-A", "U6b consumer first: reinstall A", lambda: drv.reinstall(o.a, a_name)),
            ("U6b-core", "U6b then reinstall/install ForeverCore", core),
        ],
        "U3": [ins_a, rescan],
        "U4": [ins_a, ins_b, del_a, rescan, del_b, rescan],
        "U5": [ins_a, del_a, rescan],
    }
    steps, seen = [], {}
    for name, title, fn in SCEN[o.scenario]:
        seen[name] = seen.get(name, 0) + 1
        steps.append((name if seen[name] == 1 else f"{name}{seen[name]}", title, fn))
    only = set(o.only.split(",")) if o.only else None
    try:
        drv.setup()
        report["app_version"] = drv.version()
        if isinstance(drv, drivers.CurseForge):
            report["cf_settings_ui"] = drv.settings
            report["cf_instance_prefs"] = drv.instance_prefs()
        snap("S0", "app ready, client added, nothing installed")
        for step, title, fn in steps:
            if only and step not in only:
                continue
            try:
                res = fn()
                err = None
            except Exception as e:  # noqa: BLE001 - record the failure and keep the later steps' evidence
                res, err = None, f"{type(e).__name__}: {e}"
                traceback.print_exc()
            if not b_folder and not err:
                folders = {r["project_id"]: r["folders"] for r in drv.records()}
                b_folder = next((f for f in folders.get(o.b) or [] if f != "ForeverCore"), None)
            snap(step, title, res, err)
    finally:
        drv.close()
        left = apps.stop(o.app)
        report["processes_left"] = left
        report["finished"] = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (o.out / "report.json").write_text(json.dumps(report, indent=1))
        (o.out / "report.md").write_text(markdown(report))
        print(f"wrote {o.out / 'report.md'}; processes left: {left}", flush=True)

    return int(bool(left) or any(step["error"] for step in report["steps"]))


def markdown(r):
    L = [
        f"# {r['app']} lifecycle run {r['started']}",
        "",
        f"- App: {r.get('app_version')}",
        f"- Params: `{json.dumps({k: v for k, v in r['params'].items() if k != 'out'})}`",
        f"- Consumer A: {r['consumer_a']['name']} ({r['consumer_a']['id']}); "
        f"consumer B: {r['consumer_b']['name']} ({r['consumer_b']['id']})",
    ]
    if r.get("cf_settings_ui"):
        L.append(f"- CurseForge instance settings: `{json.dumps(r['cf_settings_ui'])}`")
    L += [
        "",
        "| Step | What | AddOns folders | App records (project: file id, folders) | ForeverCore on disk "
        "| Folders needing ForeverCore without it | Error |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in r["steps"]:
        recs = (
            "<br>".join(f"{x['name']}: {x['file_id']}, {','.join(x.get('folders') or [])}" for x in s["records"])
            or "none"
        )
        cc = s["core_check"]
        core = f"yes ({cc['core_version']})" if cc["core_present"] else "**no**"
        L.append(
            f"| {s['step']} | {s['title']} | {', '.join(s['addons_folders']) or 'none'} | {recs} | {core} |"
            f" {', '.join('**' + x + '**' for x in cc['unmet_dependents']) or 'none'} | {s['error'] or ''} |"
        )
    L += ["", "## Dialogs and app view", ""]
    for s in r["steps"]:
        res = s.get("result") or {}
        for dlg in res.get("dialogs", []) if isinstance(res, dict) else []:
            L.append(f"- {s['step']} dialog, answered `{dlg['answer']}`: {(dlg['dialog'] or '').strip()!r}")
        if isinstance(res, dict) and not res.get("dialogs"):
            L.append(f"- {s['step']} result: `{json.dumps(res)[:400]}`")
        L.append(f"- {s['step']} app view: {s['app_view']}")
    L += [
        "",
        "## Archives",
        "",
        "| File | sha256 | Top-level folders | Bundled ForeverCore |",
        "| --- | --- | --- | --- |",
    ]
    for a in r["archives"].values():
        if a and "sha256" in a:
            L.append(
                f"| {a['url'].rsplit('/', 1)[-1]} | `{a['sha256']}` | {', '.join(a['top_level_folders'])} | "
                f"{a['bundled_core_version']} |"
            )
    L += [
        "",
        f"Screenshots and report.json are beside this file. Processes left after stop: {r.get('processes_left')}",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
