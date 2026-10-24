#!/usr/bin/env python3
"""Fetch what forever_sim runs against, at test time, into a cache that is never committed (stdlib only).

    python3 tools/forever_sim/fetch.py                 # UI source + enUS client data
    python3 tools/forever_sim/fetch.py --locale deDE   # also a locale's global strings
    python3 tools/forever_sim/fetch.py --offline       # fail instead of downloading

* Blizzard's UI source: Gethe/wow-ui-source at the pinned revision (the Forever build's), a shallow git fetch
  checked by commit hash.
* Client tables from wago.tools at the pinned build: GlobalStrings (per locale), GlobalColor and the texture
  atlas sizes, written as Lua data files the simulator loads. A copy already in the wow-mock-screenshots cache
  (~/.cache/wowmock/<build>/) is reused.

Nothing fetched here may be committed: the owner owns the game, and Blizzard's files stay test-time only.
"""

import argparse
import csv
import io
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# Gethe/wow-ui-source on the forever branch: 1.60.1 (70425), the build the addons' data is pinned to.
UI_REVISION = "b401e0332adfbf0460d319b06d8ea29279a941f1"
UI_REPOSITORY = "https://github.com/Gethe/wow-ui-source"
BUILD = "1.60.1.70425"
DB2_URL = "https://wago.tools/db2/{name}/csv?build={build}{locale}"
USER_AGENT = "forever_sim (+https://github.com/cjber/forever-core)"
LOCALES = ("enUS", "deDE", "esES", "esMX", "frFR", "itIT", "koKR", "ptBR", "ruRU", "zhCN", "zhTW")


def cache_dir() -> Path:
    return Path(os.environ.get("FOREVER_SIM_CACHE", "tools/.cache/forever_sim"))


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def fetch_ui(root: Path, offline: bool) -> Path:
    """The UI source checked out at UI_REVISION under root/wow-ui-source."""
    target = root / "wow-ui-source"
    if (target / ".git").exists():
        try:
            if git(target, "rev-parse", "HEAD") == UI_REVISION:
                return target
        except subprocess.CalledProcessError:
            pass
    if offline:
        raise SystemExit(f"{target} is missing or not at {UI_REVISION}; run without --offline")
    target.mkdir(parents=True, exist_ok=True)
    if not (target / ".git").exists():
        subprocess.check_call(["git", "init", "-q", str(target)])
        subprocess.check_call(["git", "-C", str(target), "remote", "add", "origin", UI_REPOSITORY])
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1")
    for attempt in range(5):
        try:
            subprocess.check_call(
                ["git", "-C", str(target), "fetch", "-q", "--depth", "1", "origin", UI_REVISION], env=env
            )
            break
        except subprocess.CalledProcessError:
            if attempt == 4:
                raise
            time.sleep(2 ** (attempt + 1))
    subprocess.check_call(["git", "-C", str(target), "checkout", "-q", "--force", "FETCH_HEAD"])
    if git(target, "rev-parse", "HEAD") != UI_REVISION:
        raise SystemExit("wow-ui-source checkout does not match the pinned revision")
    return target


def download(url: str) -> bytes:
    last = None
    for attempt in range(6):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read()
            if not data.strip() or data.lstrip().startswith(b"<"):
                raise ValueError(f"expected CSV, got empty data or HTML from {url}")
            return data
        except Exception as error:  # noqa: BLE001 - network errors of every kind are retried
            last = error
            time.sleep(2 ** (attempt + 1))
    raise SystemExit(f"could not download {url}: {last}")


def db2(root: Path, name: str, offline: bool, locale: str = "enUS") -> list[dict[str, str]]:
    suffix = "" if locale == "enUS" else f"-{locale}"
    path = root / "db2" / BUILD / f"{name}{suffix}.csv"
    shared = Path.home() / ".cache" / "wowmock" / BUILD / f"{name}.csv"
    if not path.exists():
        if locale == "enUS" and shared.exists():
            data = shared.read_bytes()
        elif offline:
            raise SystemExit(f"missing {path}; run without --offline")
        else:
            data = download(
                DB2_URL.format(name=name, build=BUILD, locale="" if locale == "enUS" else f"&locale={locale}")
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"), newline="")))
    if not rows:
        raise SystemExit(f"{path} has no rows")
    return rows


def lua_string(value: str) -> str:
    out = value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n")
    return '"' + out.replace("\0", "\\0") + '"'


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def build_data(root: Path, locales: list[str], offline: bool) -> None:
    out = root / "data" / BUILD
    for locale in locales:
        target = out / f"globalstrings-{locale}.lua"
        if target.exists():
            continue
        rows = db2(root, "GlobalStrings", offline, locale)
        lines = ["return {"]
        for row in rows:
            tag = row.get("BaseTag") or ""
            if tag.isidentifier():
                lines.append(f"[{lua_string(tag)}]={lua_string(row.get('TagText_lang') or '')},")
        lines.append("}")
        write(target, "\n".join(lines) + "\n")
    target = out / "globalcolors.lua"
    if not target.exists():
        lines = ["return {"]
        for row in db2(root, "GlobalColor", offline):
            argb = int(row["Color"]) & 0xFFFFFFFF
            a, r, g, b = (argb >> 24) & 255, (argb >> 16) & 255, (argb >> 8) & 255, argb & 255
            channels = ",".join(f"{c / 255:.4f}" for c in (r, g, b, a))
            lines.append(f"{{{lua_string(row['LuaConstantName'])},{channels}}},")
        lines.append("}")
        write(target, "\n".join(lines) + "\n")
    target = out / "atlas.lua"
    if not target.exists():
        lines = ["return {"]
        for row in db2(root, "UiTextureAtlasMember", offline):
            width = int(row.get("OverrideWidth") or 0) or int(row["Width"])
            height = int(row.get("OverrideHeight") or 0) or int(row["Height"])
            lines.append(f"[{lua_string(row['CommittedName'].lower())}]={{{width},{height}}},")
        lines.append("}")
        write(target, "\n".join(lines) + "\n")


API_CALL = re.compile(r"\b(C_[A-Za-z0-9]+)\.([A-Za-z0-9_]+)\s*\(")
# Quoted upper-case names with an underscore: the events Blizzard's Lua registers, among other constants.
EVENT_NAME = re.compile(r"[\"']([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)[\"']")


def build_undocumented(root: Path, ui: Path) -> None:
    """Every C_* function Blizzard's own Lua calls: the client has them even where the documentation does not."""
    target = root / "data" / BUILD / "api-calls.lua"
    if target.exists():
        return
    calls: set[tuple[str, str]] = set()
    events: set[str] = set()
    for path in (ui / "Interface" / "AddOns").rglob("*.lua"):
        if "APIDocumentation" in path.parts[-2]:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        calls.update(API_CALL.findall(text))
        events.update(EVENT_NAME.findall(text))
    lines = ["return {", "calls = {"] + [f"{lua_string(ns + '.' + name)}," for ns, name in sorted(calls)] + ["},"]
    lines += ["events = {"] + [f"{lua_string(e)}," for e in sorted(events)] + ["},", "}"]
    write(target, "\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--locale", action="append", default=[], choices=LOCALES)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--cache", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.cache or cache_dir()
    ui = fetch_ui(root, args.offline)
    build_undocumented(root, ui)
    build_data(root, ["enUS", *[x for x in args.locale if x != "enUS"]], args.offline)
    print(f"forever_sim: UI source {UI_REVISION[:12]} and build {BUILD} data in {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
