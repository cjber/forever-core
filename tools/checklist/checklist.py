#!/usr/bin/env python3
"""The in-game test checklist: rounds of checks, each addon's standing regression suite, the page the user ticks, and
the results the coordinator reads. See README.md beside this file."""

from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import fcntl
import hashlib
import html
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

HERE = Path(__file__).resolve().parent
REGRESSION_DIR = HERE / "regression"
PAGE_TEMPLATE = HERE / "page.html"
HANDOFF = Path(os.environ.get("CHECKLIST_HOME", Path.home() / "drive/proj/wow/wow-handoff"))
BUGGRABBER = Path(
    os.environ.get(
        "CHECKLIST_BUGGRABBER",
        Path.home()
        / "Games/battlenet/drive_c/Program Files (x86)/World of Warcraft/_forever_/WTF/Account/WORLDOFCILLIAN"
        / "SavedVariables/!BugGrabber.lua",
    )
)
HOST = "127.0.0.1"
PORT = int(os.environ.get("CHECKLIST_PORT", "8765"))
DEFAULT_MINUTES = 2
STATUSES = ("pass", "fail", "skip")
# What an answer is bound to: the commit, its runtime digest, the hash of the unpacked build linked and the client
# build. A change to any of them reopens the check, its screenshots included.
BOUND = ("sha", "digest", "artifact_sha256", "client_build")
ROUND_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d+)$")


def rounds_dir() -> Path:
    return HANDOFF / "rounds"


def results_dir() -> Path:
    return HANDOFF / "results"


def now() -> int:
    return int(time.time())


# ----------------------------------------------------------------------------------------------------------------
# Rounds and regression suites


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "check"


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    return data or {}


def dump_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=1000)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def round_sort_key(name: str) -> tuple:
    m = ROUND_NAME.match(name)
    return (m.group(1), int(m.group(2))) if m else (name, 0)


def round_names() -> list[str]:
    if not rounds_dir().is_dir():
        return []
    return sorted((p.stem for p in rounds_dir().glob("*.yaml")), key=round_sort_key)


def latest_round() -> str:
    names = round_names()
    if not names:
        raise SystemExit(f"no rounds under {rounds_dir()}: start one with 'checklist new'")
    return names[-1]


def round_path(name: str) -> Path:
    if not ROUND_NAME.match(name):
        raise SystemExit(f"round names are <yyyy-mm-dd>-<n>, such as 2026-11-19-2, not {name!r}")
    return rounds_dir() / f"{name}.yaml"


def load_round(name: str) -> dict:
    path = round_path(name)
    if not path.exists():
        raise SystemExit(f"no round {name} at {path}")
    data = load_yaml(path)
    data.setdefault("round", name)
    data.setdefault("builds", [])
    data.setdefault("checks", [])
    return data


def regression_suite(addon: str) -> dict:
    return load_yaml(REGRESSION_DIR / f"{addon}.yaml")


def addon_names() -> dict[str, str]:
    """Display name per addon key, from the regression files (every addon has one)."""
    names = {}
    for path in sorted(REGRESSION_DIR.glob("*.yaml")):
        names[path.stem] = load_yaml(path).get("name", path.stem)
    return names


def normalise_check(raw: dict, addon: str, sha: str, kind: str, digest: str = "") -> dict:
    steps = raw.get("steps") or []
    if isinstance(steps, str):
        steps = [steps]
    return {
        "id": raw["id"],
        "addon": addon,
        "sha": str(raw.get("sha") or sha or ""),
        "digest": str(digest or ""),
        "kind": kind,
        "title": raw["title"],
        "setup": raw.get("setup", ""),
        "steps": [str(s) for s in steps],
        "pass": raw.get("pass", ""),
        "picture": [raw["picture"]] if isinstance(raw.get("picture"), str) else list(raw.get("picture") or []),
        "pr": raw.get("pr", ""),
        "issue": raw.get("issue", ""),
        "minutes": int(raw.get("minutes") or DEFAULT_MINUTES),
        "optional": bool(raw.get("optional", False)),
    }


def bind(check: dict, build: dict) -> dict:
    """The check stamped with the linked build's artifact hash and client build (see BOUND)."""
    check["artifact_sha256"] = str(build.get("artifact_sha256", ""))
    check["client_build"] = str(build.get("client_build", ""))
    return check


def compose(name: str) -> dict:
    """The round as the page and the gate see it: its own checks, then each shipping addon's regression suite."""
    data = load_round(name)
    builds = {b["addon"]: b for b in data["builds"]}
    names = addon_names()
    checks = []
    for raw in data["checks"]:
        addon = raw["addon"]
        build = builds.get(addon, {})
        checks.append(bind(normalise_check(raw, addon, build.get("sha", ""), "round", build.get("digest", "")), build))
    for addon, build in builds.items():
        if build.get("regression", True) is False:
            continue
        for raw in regression_suite(addon).get("checks", []):
            reg = dict(raw, id=f"reg:{addon}:{raw['id']}")
            checks.append(
                bind(normalise_check(reg, addon, build.get("sha", ""), "regression", build.get("digest", "")), build)
            )
    order = list(builds) + [c["addon"] for c in checks if c["addon"] not in builds]
    groups = []
    for addon in dict.fromkeys(order):
        own = [c for c in checks if c["addon"] == addon]
        if own:
            groups.append({"addon": addon, "name": names.get(addon, addon), "build": builds.get(addon), "checks": own})
    return {
        "round": name,
        "title": data.get("title") or f"Test round {name}",
        "linked": data.get("linked", ""),
        "notes": data.get("notes", ""),
        "builds": data["builds"],
        "names": names,
        "groups": groups,
        "checks": checks,
    }


def next_check_id(data: dict, title: str) -> str:
    base = slug(title)
    taken = {c["id"] for c in data["checks"]}
    cid, n = base, 2
    while cid in taken:
        cid, n = f"{base}-{n}", n + 1
    return cid


# ----------------------------------------------------------------------------------------------------------------
# Results


_lock = threading.Lock()


@contextlib.contextmanager
def locked(name: str):
    """One writer at a time for a round's results, across the server's threads and a CLI run beside it."""
    results_dir().mkdir(parents=True, exist_ok=True)
    with _lock, open(results_dir() / f".{name}.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def results_path(name: str) -> Path:
    return results_dir() / f"{name}.json"


def load_results(name: str) -> dict:
    path = results_path(name)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.setdefault("round", name)
    data.setdefault("answers", {})
    return data


def save_results(name: str, data: dict) -> None:
    path = results_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def record_answer(name: str, check: str, status: str | None, note: str | None, shown: dict | None = None) -> dict:
    """Record an answer for the build now linked. `shown` holds the BOUND values the page rendered; a status from a
    page rendered for another build is refused, so a tab left open across a relink cannot pass the new build."""
    composed = {c["id"]: c for c in compose(name)["checks"]}
    if check not in composed:
        raise ValueError(f"no check {check} in round {name}")
    if status is not None:
        require_shown(composed[check], shown)
    if status not in (*STATUSES, None, ""):
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    with locked(name):
        data = load_results(name)
        data.setdefault("started", now())
        answer = current(data["answers"].get(check, {"images": []}), composed[check])
        data["answers"][check] = answer
        if status is not None:
            answer["status"] = status or None
        if note is not None:
            answer["note"] = note
        answer["addon"] = composed[check]["addon"]
        answer.update({k: composed[check][k] for k in BOUND})
        answer["at"] = now()
        save_results(name, data)
        return answer


def require_shown(check: dict, shown: dict | None) -> None:
    """Refuse a page's write when it was rendered for another build than the one linked now. None is a CLI call."""
    if shown is not None and any(str(shown.get(k) or "") != check[k] for k in BOUND):
        raise ValueError("the build for this check changed since the page loaded: reload the page and check again")


def record_image(name: str, check: str, data_url: str, shown: dict | None = None) -> str:
    composed = {c["id"]: c for c in compose(name)["checks"]}
    if check not in composed:
        raise ValueError(f"no check {check} in round {name}")
    require_shown(composed[check], shown)
    m = re.match(r"^data:image/(png|jpeg|webp);base64,(.+)$", data_url, re.S)
    if not m:
        raise ValueError("expected a PNG, JPEG or WebP data URL")
    ext = "jpg" if m.group(1) == "jpeg" else m.group(1)
    folder = results_dir() / name
    folder.mkdir(parents=True, exist_ok=True)
    with locked(name):
        data = load_results(name)
        data.setdefault("started", now())
        # A screenshot taken for an earlier build is no evidence for this one.
        answer = current(data["answers"].get(check, {"images": []}), composed[check])
        data["answers"][check] = answer
        images = answer.setdefault("images", [])
        # A fresh name each time, so a file a report already named is never overwritten by a later build's capture.
        fname = f"{slug(check)}-{len(images) + 1}-{uuid.uuid4().hex[:8]}.{ext}"
        (folder / fname).write_bytes(base64.b64decode(m.group(2)))
        images.append(fname)
        answer["addon"] = composed[check]["addon"]
        answer.update({k: composed[check][k] for k in BOUND})
        answer["at"] = now()
        save_results(name, data)
    return fname


# ----------------------------------------------------------------------------------------------------------------
# BugGrabber: its SavedVariables file is a Lua table literal; this reads exactly that grammar.


class LuaReader:
    ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v", "\\": "\\", '"': '"'}
    ESCAPES["'"] = "'"
    ESCAPES["\n"] = "\n"

    def __init__(self, text: str):
        self.s, self.i = text, 0

    def ws(self) -> None:
        while self.i < len(self.s):
            if self.s[self.i].isspace():
                self.i += 1
            elif self.s.startswith("--", self.i):
                end = self.s.find("\n", self.i)
                self.i = len(self.s) if end < 0 else end
            else:
                return

    def expect(self, tok: str) -> None:
        self.ws()
        if not self.s.startswith(tok, self.i):
            raise ValueError(f"expected {tok!r} at {self.i}")
        self.i += len(tok)

    def assignments(self) -> dict:
        out = {}
        while True:
            self.ws()
            if self.i >= len(self.s):
                return out
            m = re.compile(r"[A-Za-z_][A-Za-z0-9_]*").match(self.s, self.i)
            if not m:
                raise ValueError(f"expected a name at {self.i}")
            self.i = m.end()
            self.expect("=")
            out[m.group()] = self.value()

    def value(self):
        self.ws()
        c = self.s[self.i]
        if c == "{":
            return self.table()
        if c in "\"'":
            return self.string(c)
        if self.s.startswith("[[", self.i) or self.s.startswith("[=", self.i):
            return self.long_string()
        m = re.compile(r"-?(?:0x[0-9a-fA-F]+|\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+)").match(self.s, self.i)
        if m:
            self.i = m.end()
            t = m.group()
            return int(t, 16) if "x" in t else (float(t) if any(ch in t for ch in ".eE") else int(t))
        for word, val in (("true", True), ("false", False), ("nil", None)):
            if self.s.startswith(word, self.i):
                self.i += len(word)
                return val
        raise ValueError(f"unexpected {c!r} at {self.i}")

    def string(self, quote: str) -> str:
        """A quoted string; a decimal escape is one byte, so escaped UTF-8 sequences decode back to their text."""
        self.i += 1
        out = bytearray()
        while True:
            c = self.s[self.i]
            if c == quote:
                self.i += 1
                return out.decode("utf-8", errors="replace")
            if c == "\\":
                n = self.s[self.i + 1]
                if n.isdigit():
                    m = re.compile(r"\d{1,3}").match(self.s, self.i + 1)
                    out.append(int(m.group()) & 0xFF)
                    self.i = m.end()
                    continue
                out += self.ESCAPES.get(n, n).encode()
                self.i += 2
                continue
            out += c.encode()
            self.i += 1

    def long_string(self) -> str:
        m = re.compile(r"\[(=*)\[").match(self.s, self.i)
        close = "]" + m.group(1) + "]"
        end = self.s.index(close, m.end())
        self.i = end + len(close)
        return self.s[m.end() : end].removeprefix("\n")

    def table(self):
        self.i += 1
        items, keyed = [], {}
        while True:
            self.ws()
            if self.s[self.i] == "}":
                self.i += 1
                break
            if self.s[self.i] == "[" and not self.s.startswith("[[", self.i) and not self.s.startswith("[=", self.i):
                self.i += 1
                key = self.value()
                self.expect("]")
                self.expect("=")
                keyed[key] = self.value()
            else:
                m = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)").match(self.s, self.i)
                if m:
                    self.i = m.end()
                    keyed[m.group(1)] = self.value()
                else:
                    items.append(self.value())
            self.ws()
            if self.s[self.i] in ",;":
                self.i += 1
        if keyed and not items:
            return keyed
        if items and not keyed:
            return items
        keyed.update({i + 1: v for i, v in enumerate(items)})
        return keyed


def bug_errors(since: int, path: Path | None = None) -> list[dict]:
    """The BugGrabber errors whose last time is at or after since (the client writes the file on /reload or logout)."""
    path = path or BUGGRABBER
    if not path.exists():
        return []
    db = LuaReader(path.read_text(encoding="utf-8", errors="replace")).assignments().get("BugGrabberDB") or {}
    errors = db.get("errors") or []
    if isinstance(errors, dict):
        errors = [errors[k] for k in sorted(errors)]
    keep = []
    for err in errors:
        if isinstance(err, dict) and int(err.get("time") or 0) >= since:
            keep.append({k: err.get(k) for k in ("message", "stack", "locals", "time", "counter", "session")})
    return keep


def snapshot_bugs(name: str) -> list[dict]:
    with locked(name):
        data = load_results(name)
        since = int(data.get("started") or now())
        data["bugs"] = bug_errors(since)
        data["bugs_read"] = now()
        save_results(name, data)
        return data["bugs"]


# ----------------------------------------------------------------------------------------------------------------
# The page


def embed_picture(ref: str) -> str:
    """A picture reference as an image source: a URL stays a URL, a local file is inlined so the page stands alone."""
    if not ref or re.match(r"^(https?:|data:)", ref):
        return ref
    path = Path(ref).expanduser()
    if not path.is_absolute():
        path = HANDOFF / path
    if not path.exists():
        return ""
    mime = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp", ".gif": "gif"}.get(path.suffix.lower())
    if not mime:
        return ""
    return f"data:image/{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def render(name: str, served: bool) -> str:
    composed = compose(name)
    for check in composed["checks"]:
        check["picture"] = [embed_picture(p) for p in check["picture"]]
    results = load_results(name)
    by_id = {c["id"]: c for c in composed["checks"]}
    results["answers"] = {k: current(v, by_id[k]) for k, v in results["answers"].items() if k in by_id}
    payload = {
        "round": composed,
        "results": results,
        "served": served,
        "results_file": str(results_path(name)),
    }
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    page = PAGE_TEMPLATE.read_text(encoding="utf-8")
    return page.replace("__TITLE__", html.escape(composed["title"])).replace("__DATA__", data)


def server_up(port: int = PORT) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex((HOST, port)) == 0


def open_in_chrome(target: str) -> None:
    subprocess.Popen(
        ["google-chrome-stable", target],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "checklist"

    def log_message(self, fmt, *args):  # noqa: D401 - quiet unless asked
        if os.environ.get("CHECKLIST_VERBOSE"):
            sys.stderr.write(fmt % args + "\n")

    def send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, code: int = 200) -> None:
        self.send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

    def local_host(self) -> bool:
        """Refuse a Host other than this machine's, so a page on a rebound DNS name cannot read or write results."""
        host = urlparse("//" + (self.headers.get("Host") or "")).hostname
        if host in (HOST, "localhost"):
            return True
        self.send_json({"error": "unknown host"}, 403)
        return False

    def do_GET(self):
        if not self.local_host():
            return
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/":
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", f"/round/{latest_round()}")
                self.end_headers()
                return
            m = re.fullmatch(r"/round/([\w-]+)", path)
            if m:
                name = m.group(1)
                load_round(name)
                with locked(name):
                    data = load_results(name)
                    if "started" not in data:
                        data["started"] = now()
                        save_results(name, data)
                return self.send(200, render(name, served=True).encode(), "text/html; charset=utf-8")
            m = re.fullmatch(r"/api/results/([\w-]+)", path)
            if m:
                load_round(m.group(1))
                return self.send_json(load_results(m.group(1)))
            m = re.fullmatch(r"/shots/(\d{4}-\d{2}-\d{2}-\d+)/([\w-]+\.(?:png|jpg|webp))", path)
            if m:
                f = results_dir() / m.group(1) / m.group(2)
                if f.is_file():
                    ctype = "image/" + {"jpg": "jpeg"}.get(f.suffix[1:], f.suffix[1:])
                    return self.send(200, f.read_bytes(), ctype)
            self.send_json({"error": "not found"}, 404)
        except SystemExit as e:
            self.send_json({"error": str(e)}, 404)

    def do_POST(self):
        if not self.local_host():
            return
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host')}":
            return self.send_json({"error": "cross-origin request refused"}, 403)
        path = urlparse(self.path).path
        m = re.fullmatch(r"/api/(answer|image|submit)/([\w-]+)", path)
        if not m:
            return self.send_json({"error": "not found"}, 404)
        kind, name = m.groups()
        try:
            load_round(name)
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict) or not isinstance(body.get("check", ""), str):
                raise ValueError("expected a JSON object with a string check")
            if kind == "answer":
                shown = {k: body.get(k) for k in BOUND}
                return self.send_json(record_answer(name, body["check"], body.get("status"), body.get("note"), shown))
            if kind == "image":
                shown = {k: body.get(k) for k in BOUND}
                return self.send_json({"file": record_image(name, body["check"], body["data"], shown)})
            with locked(name):
                data = load_results(name)
                data["submitted"] = now()
                save_results(name, data)
            bugs = snapshot_bugs(name)
            return self.send_json({"bugs": len(bugs), "submitted": True})
        except (ValueError, KeyError, TypeError, SystemExit) as e:
            return self.send_json({"error": str(e)}, 400)


def make_server(port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((HOST, port), Handler)


# ----------------------------------------------------------------------------------------------------------------
# Status and the release gate


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def build_matches(recorded: str, asked: str) -> bool:
    """The gate's build test: the round records the full SHA, and the caller may give it whole or abbreviated."""
    recorded, asked = (recorded or "").lower(), (asked or "").lower()
    return bool(FULL_SHA.match(recorded)) and len(asked) >= 7 and recorded.startswith(asked)


def current(answer: dict, check: dict) -> dict:
    """The answer as it stands for the build now linked: a status or screenshot given against another build (see BOUND)
    no longer counts; the note stays."""
    stale = any(answer.get(k, "") != check[k] for k in BOUND)
    if stale and (answer.get("status") or answer.get("images")):
        return {k: v for k, v in answer.items() if k not in ("status", "images", *BOUND)}
    return answer


def status_rows(name: str) -> tuple[dict, list[dict]]:
    composed = compose(name)
    answers = load_results(name)["answers"]
    rows = []
    for check in composed["checks"]:
        ans = current(answers.get(check["id"], {}), check)
        rows.append(dict(check, status=ans.get("status"), note=ans.get("note", ""), images=ans.get("images", [])))
    return composed, rows


def gate(addon: str, sha: str, names: list[str] | None = None) -> tuple[bool, list[dict], str]:
    """True when some round holds checks for this exact build and every one of them passed."""
    for name in reversed(names or round_names()):
        _, rows = status_rows(name)
        mine = [r for r in rows if r["addon"] == addon and build_matches(r["sha"], sha)]
        if mine:
            return all(r["status"] == "pass" or (r["optional"] and r["status"] == "skip") for r in mine), mine, name
    return False, [], ""


# ----------------------------------------------------------------------------------------------------------------
# CLI


def cmd_new(a):
    if round_path(a.round).exists():
        raise SystemExit(f"round {a.round} already exists")
    if not ROUND_NAME.match(a.round):
        raise SystemExit("round names are <yyyy-mm-dd>-<n>, such as 2026-11-19-2")
    dump_yaml(round_path(a.round), {"round": a.round, "title": a.title or "", "linked": "", "builds": [], "checks": []})
    print(round_path(a.round))


def full_sha(addon: str, sha: str) -> str:
    """The full commit SHA, so the gate never matches a different commit by a shared abbreviation."""
    if FULL_SHA.match(sha.lower()):
        return sha.lower()
    checkout = HANDOFF.parent / addon
    for cmd in (
        ["git", "-C", str(checkout), "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"],
        ["gh", "api", f"repos/cjber/{addon}/commits/{sha}", "--jq", ".sha"],
    ):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out.returncode == 0 and FULL_SHA.match(out.stdout.strip()):
            return out.stdout.strip()
    raise SystemExit(f"cannot resolve {addon} {sha} to a full commit SHA: fetch the checkout or pass all 40 characters")


def artifact_root(artifact: str) -> Path:
    """A recorded artifact path; a relative one is under the workspace that holds the handoff folder."""
    root = Path(artifact)
    return root if root.is_absolute() else HANDOFF.parent / root


def artifact_digest(artifact: str) -> str:
    """The sha256 over every file of an unpacked build (relative path and bytes), so a later rebuild in place shows."""
    root = artifact_root(artifact)
    if not root.is_dir():
        return ""
    h = hashlib.sha256()
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(f.relative_to(root).as_posix().encode() + b"\0")
        h.update(hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


def cmd_build(a):
    name = a.round or latest_round()
    data = load_round(name)
    build = next((b for b in data["builds"] if b["addon"] == a.addon), None)
    if build is None:
        build = {"addon": a.addon}
        data["builds"].append(build)
    if a.sha:
        a.sha = full_sha(a.addon, a.sha)
    for key in ("sha", "version", "build", "artifact", "digest", "client_build"):
        if getattr(a, key):
            build[key] = getattr(a, key)
    if a.artifact:
        build["artifact_sha256"] = artifact_digest(a.artifact)
        if not build["artifact_sha256"]:
            raise SystemExit(f"no unpacked build at {a.artifact}")
    if a.pr:
        build["prs"] = sorted(set(build.get("prs", [])) | set(a.pr), key=str)
    if a.no_regression:
        build["regression"] = False
    if a.linked:
        data["linked"] = a.linked
    dump_yaml(round_path(name), data)
    print(f"{name}: {a.addon} {build.get('sha', '')}")


def check_from_args(a, data: dict | None) -> dict:
    check = {"id": a.id or (next_check_id(data, a.title) if data is not None else slug(a.title)), "title": a.title}
    for key in ("setup", "picture", "pr", "sha", "issue"):
        if getattr(a, key, None):
            check[key] = getattr(a, key)
    check["steps"] = a.step or []
    check["pass"] = a.pass_
    if a.minutes:
        check["minutes"] = a.minutes
    if getattr(a, "optional", False):
        check["optional"] = True
    return check


def cmd_add(a):
    name = a.round or latest_round()
    data = load_round(name)
    check = dict({"addon": a.addon}, **check_from_args(a, data))
    if any(c["id"] == check["id"] for c in data["checks"]):
        raise SystemExit(f"round {name} already has a check {check['id']}")
    data["checks"].append(check)
    dump_yaml(round_path(name), data)
    print(f"{name}: added {check['id']}")


def cmd_regression(a):
    path = REGRESSION_DIR / f"{a.addon}.yaml"
    data = load_yaml(path)
    if not data:
        raise SystemExit(f"no regression suite {path}: add the addon's file first (name: and checks:)")
    data.setdefault("checks", [])
    check = check_from_args(a, None)
    if any(c["id"] == check["id"] for c in data["checks"]):
        raise SystemExit(f"{a.addon} already has a check {check['id']}")
    data["checks"].append(check)
    dump_yaml(path, data)
    print(f"{path}: added {check['id']}")


def cmd_render(a):
    name = a.round or latest_round()
    out = Path(a.output) if a.output else results_dir() / f"{name}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(name, served=False), encoding="utf-8")
    print(out)
    return out


def cmd_open(a):
    name = a.round or latest_round()
    if server_up(a.port):
        target = f"http://{HOST}:{a.port}/round/{name}"
    else:
        a.output = None
        target = str(cmd_render(a))
        print("checklist serve is not running: answers stay in this browser until it is", file=sys.stderr)
    open_in_chrome(target)
    print(target)


def cmd_serve(a):
    server = make_server(a.port)
    print(f"serving http://{HOST}:{a.port}/ (results in {results_dir()})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def cmd_status(a):
    if a.addon or a.sha:
        if not (a.addon and a.sha):
            raise SystemExit("--addon and --sha go together")
        ok, rows, name = gate(a.addon, a.sha, [a.round] if a.round else None)
        if a.json:
            for r in rows:
                r["images"] = [str(results_dir() / name / i) for i in r["images"]]
            build = next((b for b in load_round(name)["builds"] if b["addon"] == a.addon), {}) if name else {}
            if build.get("artifact"):
                build["artifact_path"] = str(artifact_root(build["artifact"]))
                build["artifact_sha256_now"] = artifact_digest(build["artifact"])
            out = {"round": name, "addon": a.addon, "sha": a.sha, "passed": ok, "build": build, "checks": rows}
            print(json.dumps(out, indent=2))
            raise SystemExit(0 if ok else (2 if not rows else 1))
        if not rows:
            print(f"no round has checks for {a.addon} at {a.sha}")
            raise SystemExit(2)
        for r in rows:
            print(f"{(r['status'] or 'open').upper():5} {r['id']}  {r['title']}")
        print(f"{name}: {a.addon} {a.sha} {'passed' if ok else 'not passed'}")
        raise SystemExit(0 if ok else 1)
    name = a.round or latest_round()
    composed, rows = status_rows(name)
    results = load_results(name)
    if a.json:
        print(json.dumps({"round": name, "checks": rows, "bugs": results.get("bugs", [])}, indent=2))
        return
    done = sum(1 for r in rows if r["status"])
    print(f"{composed['title']} ({name}): {done}/{len(rows)} answered")
    for group in composed["groups"]:
        build = group["build"] or {}
        print(f"\n{group['name']} {build.get('sha', '')[:10]}")
        for r in rows:
            if r["addon"] != group["addon"]:
                continue
            print(f"  {(r['status'] or 'open').upper():5} {r['id']}  {r['title']}")
            if r["note"]:
                print("        note: " + r["note"].replace("\n", "\n              "))
            for img in r["images"]:
                print(f"        shot: {results_dir() / name / img}")
    bugs = results.get("bugs")
    if bugs is not None:
        print(f"\nBugGrabber errors during the round: {len(bugs)}")
        for b in bugs:
            print("  " + (b.get("message") or "").splitlines()[0][:200])
    if results.get("submitted"):
        print("\nsubmitted " + dt.datetime.fromtimestamp(results["submitted"]).strftime("%H:%M %d %b"))


def cmd_bugs(a):
    name = a.round or latest_round()
    bugs = snapshot_bugs(name)
    print(f"{len(bugs)} BugGrabber errors since the round started")
    for b in bugs:
        print("  " + (b.get("message") or "").splitlines()[0][:200])


def cmd_list(a):
    for name in round_names():
        rows = status_rows(name)[1]
        counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
        print(f"{name}  {len(rows)} checks  pass {counts['pass']}  fail {counts['fail']}  skip {counts['skip']}")


def check_args(p: argparse.ArgumentParser, regression: bool) -> None:
    p.add_argument("--title", required=True, help="what is checked, as a short sentence")
    p.add_argument("--setup", help="what to have in place first")
    p.add_argument("--step", action="append", help="one numbered step; repeat for each")
    p.add_argument("--pass", dest="pass_", required=True, help="what the user sees when it works")
    p.add_argument(
        "--picture",
        action="append",
        help="expected picture (repeatable): a URL at an immutable SHA, or a local image path",
    )
    p.add_argument("--minutes", type=int, help=f"estimated minutes (default {DEFAULT_MINUTES})")
    p.add_argument("--id", help="stable id (default: from the title)")
    p.add_argument("--issue", help="the issue this check guards, such as shortest-path-forever#978")
    p.add_argument("--optional", action="store_true", help="a skip still lets the build pass")
    if not regression:
        p.add_argument("--pr", help="the PR it checks, such as 876 or forever-core#842")
        p.add_argument("--sha", help="override the build SHA for this check")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="checklist", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="start a round file")
    p.add_argument("round")
    p.add_argument("--title")
    p.set_defaults(func=cmd_new)
    p = sub.add_parser("build", help="record the build linked for an addon")
    p.add_argument("--round")
    p.add_argument("--addon", required=True)
    p.add_argument("--sha")
    p.add_argument("--version")
    p.add_argument("--build", help="how it was built")
    p.add_argument("--artifact", help="the unpacked build linked into AddOns, such as test-artifacts/<repo>-<build>")
    p.add_argument("--digest", help="the runtime digest of that build (visual_proof --digests)")
    p.add_argument("--client-build", help="the client build it was tested in, such as '1.60.1.70959 (Interface 16001)'")
    p.add_argument("--pr", action="append", help="a PR the build carries; repeat")
    p.add_argument("--linked", help="the round's 'builds linked' line")
    p.add_argument("--no-regression", action="store_true", help="leave this addon's regression suite out")
    p.set_defaults(func=cmd_build)
    p = sub.add_parser("add", help="add a check to a round")
    p.add_argument("--round")
    p.add_argument("--addon", required=True)
    check_args(p, regression=False)
    p.set_defaults(func=cmd_add)
    p = sub.add_parser("regression", help="add a permanent check to an addon's regression suite")
    p.add_argument("addon")
    check_args(p, regression=True)
    p.set_defaults(func=cmd_regression)
    for verb, func in (("render", cmd_render), ("open", cmd_open)):
        p = sub.add_parser(verb, help=f"{verb} the round's page")
        p.add_argument("round", nargs="?")
        p.add_argument("-o", "--output")
        p.add_argument("--port", type=int, default=PORT)
        p.set_defaults(func=func)
    p = sub.add_parser("serve", help="serve the page and save answers as they are given")
    p.add_argument("--port", type=int, default=PORT)
    p.set_defaults(func=cmd_serve)
    p = sub.add_parser("status", help="print answers, or gate one build with --addon and --sha")
    p.add_argument("round", nargs="?")
    p.add_argument("--addon")
    p.add_argument("--sha")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)
    p = sub.add_parser("bugs", help="read BugGrabber's errors since the round started into the results")
    p.add_argument("round", nargs="?")
    p.set_defaults(func=cmd_bugs)
    p = sub.add_parser("list", help="every round with its counts")
    p.set_defaults(func=cmd_list)
    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
