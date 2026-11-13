#!/usr/bin/env python3
"""Fetch what forever_sim runs against, at test time, into a cache that is never committed (stdlib only).

    python3 tools/forever_sim/fetch.py                 # UI source + enUS client data
    python3 tools/forever_sim/fetch.py --locale deDE   # also a locale's global strings
    python3 tools/forever_sim/fetch.py --offline       # fail instead of downloading
    python3 tools/forever_sim/fetch.py --refresh-restrictions   # rewrite the committed restrictions.txt
    python3 tools/forever_sim/fetch.py --refresh-restrictions \\
        --probe ~/path/SavedVariables/ForeverProbe.lua          # merge the live client's own blocks

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
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

# Gethe/wow-ui-source on the forever branch: 1.60.1 (70425), the build the addons' data is pinned to.
UI_REVISION = "b401e0332adfbf0460d319b06d8ea29279a941f1"
UI_REPOSITORY = "https://github.com/Gethe/wow-ui-source"
BUILD = "1.60.1.70425"
DB2_URL = "https://wago.tools/db2/{name}/csv?build={build}{locale}"
WIKI_URL = "https://warcraft.wiki.gg/api.php"
RESTRICTIONS = Path(__file__).resolve().with_name("restrictions.txt")
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


# Wiki classes the restrictedapi template uses, and how each becomes the simulator's one class. "always" is the one
# unconditional refusal, "protected": addon code may not call it at any time. The other tags restrict something the
# simulator does not model, so they stay untagged and keep today's combat-only rule:
#   * noscript blocks /run, /script and loadstring, not addon file code, which is what the sim runs;
#   * secureframe blocks calls on secure frames during combat;
#   * restrictedframe blocks calls on restricted frames such as nameplates;
#   * the state tags name an instance, a group, a free trial or an anchor family the sim has no notion of.
ALWAYS_TAGS = frozenset({"protected"})
UNMODELLED_TAGS = frozenset(
    {
        "noscript",
        "secureframe",
        "restrictedframe",
        "noinstance",
        "grouponly",
        "nopermission",
        "nofreetrial",
        "anchorfamily",
    }
)
KNOWN_TAGS = frozenset({"nocombat", "hwevent"}) | ALWAYS_TAGS | UNMODELLED_TAGS


def restriction_classes(tag, source):
    """Every simulator class a wiki `restrictedapi` tag carries, or ["untagged"] when none is modelled.

    A tag can name several classes (`protected,hwevent`, `nocombat,hwevent`), and the sim refuses a call when any of
    them applies, so the generator keeps each one it can model.
    """
    parts = [part.strip().lower() for part in tag.split(",") if part.strip()]
    if not parts:
        raise SystemExit(f"{source}: empty restrictedapi tag")
    unknown = sorted(part for part in parts if part not in KNOWN_TAGS)
    if unknown:
        raise SystemExit(f"{source}: unknown restrictedapi class {unknown[0]}")
    classes = []
    if "protected" in parts:
        classes.append("always")
    if "nocombat" in parts:
        classes.append("nocombat")
    if "hwevent" in parts:
        classes.append("hwevent")
    return classes or ["untagged"]


def wiki_title(kind, name):
    """The warcraft.wiki.gg page for a documented function (`F`) or widget method (`W`)."""
    if kind == "F":
        return "API_" + name
    system, _, method = name.partition("_")
    base = re.sub(r"^Simple", "", system)
    base = re.sub(r"API$", "", base)
    return f"API_{base}_{method}"


def wiki(params):
    query = urlencode({**params, "format": "json"})
    last = None
    for attempt in range(5):
        try:
            request = urllib.request.Request(WIKI_URL + "?" + query, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.loads(response.read())
        except Exception as error:  # noqa: BLE001 - network errors of every kind are retried
            last = error
            time.sleep(2 ** (attempt + 1))
    raise SystemExit(f"could not query the wiki for {params}: {last}")


def restricted_names(ui: Path) -> list[tuple[str, str]]:
    """(kind, name) for every documented HasRestrictions function and widget method, through the sim's docs loader."""
    script = """
local sim, ui = os.getenv("FOREVER_SIM_DIR"), os.getenv("FOREVER_SIM_UI")
package.path = sim .. "/?.lua;" .. package.path
local docs = require("docs").load(ui)
for _, system in ipairs(docs.systems) do
	for _, f in ipairs(system.Functions or {}) do
		if f.HasRestrictions then
			print("F\\t" .. (system.Namespace and (system.Namespace .. ".") or "") .. f.Name)
		end
	end
end
for system, doc in pairs(docs.widgets) do
	for _, f in ipairs(doc.Functions or {}) do
		if f.HasRestrictions then
			print("W\\t" .. system .. "_" .. f.Name)
		end
	end
end
"""
    result = subprocess.run(
        ["luajit", "-e", script],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env={
            **os.environ,
            "FOREVER_SIM_DIR": str(Path(__file__).resolve().parent),
            "FOREVER_SIM_UI": str(ui),
        },
    )
    if result.returncode:
        raise SystemExit("could not read the API documentation for restrictions:\n" + result.stderr)
    names = []
    for line in result.stdout.splitlines():
        kind, _, name = line.partition("\t")
        if kind in ("F", "W") and name:
            names.append((kind, name))
    return names


# The events ForeverProbe records (forever-dev ForeverProbe/blocked.lua) that name the call the client refused. A
# blocked call was refused at the time it was recorded; a forbidden one needs a hardware event, which the client
# reports separately from the combat state. ADDON_* names the addon in its first payload field and the call in its
# second; MACRO_* names only the call.
ADDON_EVENTS = frozenset({"ADDON_ACTION_BLOCKED", "ADDON_ACTION_FORBIDDEN"})
BLOCKED_EVENTS = frozenset({"ADDON_ACTION_BLOCKED", "MACRO_ACTION_BLOCKED"})
FORBIDDEN_EVENTS = frozenset({"ADDON_ACTION_FORBIDDEN", "MACRO_ACTION_FORBIDDEN"})
CLASS_ORDER = ("always", "nocombat", "hwevent")


@dataclass(frozen=True)
class ProbeHit:
    """One call ForeverProbe recorded: the event that named it, the combat state and the event's payload fields."""

    kind: str
    combat: bool
    args: tuple[str, ...]


def probe_hits(path: Path) -> list[ProbeHit]:
    """The calls ForeverProbe recorded, through LuaJIT.

    The file is a SavedVariables chunk, so LuaJIT reads it rather than a regex. Each hit carries the event that named
    it, the combat state and the event's payload fields. A "message" hit is DisplayInterfaceActionBlockedMessage,
    which the client calls with no arguments, so it names no call.
    """
    script = """
local path = assert(os.getenv("FOREVER_PROBE_FILE"), "no probe file")
assert(loadfile(path))()
local db = ForeverProbeBlockedDB or {}
local function field(value)
	if type(value) ~= "string" then
		return ""
	end
	return (value:gsub("[\\t\\r\\n]", " "))
end
for _, hit in ipairs(db.hits or {}) do
	local fields = { field(hit.kind), hit.combat and "combat" or "calm" }
	for _, arg in ipairs(hit.args or {}) do
		fields[#fields + 1] = field(arg)
	end
	print(table.concat(fields, "\\t"))
end
"""
    result = subprocess.run(
        ["luajit", "-e", script],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env={**os.environ, "FOREVER_PROBE_FILE": str(path)},
    )
    if result.returncode:
        raise SystemExit(f"could not read the probe at {path}:\n" + result.stderr)
    hits = []
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        hits.append(ProbeHit(kind=fields[0], combat=fields[1] == "combat", args=tuple(fields[2:])))
    return hits


def probe_name(payload: str) -> str | None:
    """The pin key of a refused call: its qualified function name, or a widget method's own name.

    The event names a call the way the client's own message does: `C_UI.Reload()`, or `SomeFrame:SetEnabled()` for a
    widget method. The sim keys a documented function by its qualified name and an observed method by its own name.
    """
    name = payload.partition("(")[0].strip()
    if ":" in name:
        name = name.rpartition(":")[2].strip()
    return name or None


def probe_classes(kind: str, combat: bool) -> list[str] | None:
    """The sim class a recorded refusal describes, or None for a hit that names no refused call."""
    if kind in FORBIDDEN_EVENTS:
        return ["hwevent"]
    if kind in BLOCKED_EVENTS:
        # A block the client applies in combat alone is nocombat; one it applied out of combat applies at any time.
        return ["nocombat"] if combat else ["always"]
    return None


def merge_classes(existing: list[str], observed: list[str]) -> list[str]:
    """The union of two class lists, in the pin's order, with `always` and any untagged fallback dropped for the one
    class that covers them."""
    found = {class_ for class_ in (*existing, *observed) if class_ != "untagged"}
    if "always" in found:
        return ["always"]
    return [class_ for class_ in CLASS_ORDER if class_ in found] or ["untagged"]


def probe_blocks(path: Path) -> dict[str, list[str]]:
    """name -> the classes the live client's own blocks give it."""
    blocks: dict[str, list[str]] = {}
    for hit in probe_hits(path):
        classes = probe_classes(hit.kind, hit.combat)
        if classes is None:
            continue
        args = hit.args
        # ADDON_*: addon name then call. MACRO_*: the call alone.
        payload = args[1] if hit.kind in ADDON_EVENTS and len(args) > 1 else (args[0] if args else "")
        name = probe_name(payload)
        if name is None:
            continue
        blocks[name] = merge_classes(blocks.get(name, []), classes)
    return blocks


def merge_probe(classes: dict[str, list[str]], observed: dict[str, list[str]]) -> dict[str, list[str]]:
    """The wiki's classes with every block the live client recorded merged in; the client's own refusal wins."""
    merged = dict(classes)
    for name, observed_classes in observed.items():
        merged[name] = merge_classes(merged.get(name, []), observed_classes)
    return merged


def fetch_restrictions(ui: Path) -> dict[str, list[str]]:
    """name -> its classes for every documented restricted function or method, from the restrictedapi template."""
    names = restricted_names(ui)
    titles = {wiki_title(kind, name): (kind, name) for kind, name in names}
    pages = {}
    items = sorted(titles.items())
    for start in range(0, len(items), 50):
        batch = items[start : start + 50]
        data = wiki(
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": "|".join(title for title, _ in batch),
                "redirects": "1",
            }
        )
        query = data.get("query") or {}
        normalized = {entry["from"]: entry["to"] for entry in query.get("normalized", [])}
        redirects = {entry["from"]: entry["to"] for entry in query.get("redirects", [])}
        by_title = {page["title"]: page for page in query.get("pages", {}).values()}
        for title, (_, name) in batch:
            target = redirects.get(normalized.get(title, title), normalized.get(title, title))
            page = by_title.get(target)
            revisions = page and page.get("revisions")
            if revisions:
                pages[name] = revisions[0]["slots"]["main"]["*"]
            else:
                pages[name] = None
    classes = {}
    for _, name in names:
        text = pages.get(name)
        if text is None:
            classes[name] = ["untagged"]
            continue
        match = re.search(r"\{\{\s*restrictedapi\s*\|([^}|]*)", text, re.IGNORECASE)
        classes[name] = restriction_classes(match.group(1), f"API:{name}") if match else ["untagged"]
    return classes


def write_restrictions(classes: dict[str, list[str]], root: Path, probed: bool = False) -> None:
    """The committed pin beside fetch.py, and the build's data copy the sim can read."""
    observed = ", plus every block a live client recorded (fetch.py --refresh-restrictions --probe)" if probed else ""
    header = [
        "# The wiki's restrictedapi classes for each documented HasRestrictions function and widget method,",
        f"# build {BUILD}{observed}.",
        "# Generated by python3 forever_sim/fetch.py --refresh-restrictions from warcraft.wiki.gg.",
        "# The source wiki is CC BY-SA 4.0; this list of names and classes is derived from it.",
        "# One name per line, then its classes separated by commas: always, nocombat or hwevent, or untagged",
        "# (today's combat-only rule). The sim refuses the call when any listed class applies.",
        "# A function is keyed by its qualified name; a widget method by its documented system and name",
        "# (SimpleButtonAPI_SetEnabled), or by its own name for a block the live client recorded (SetEnabled).",
        "# Vendored from cjber/forever-core; regenerate it there.",
    ]
    lines = [f"{name} {','.join(classes_)}" for name, classes_ in sorted(classes.items())]
    RESTRICTIONS.write_text("\n".join(header + lines) + "\n", encoding="utf-8")
    entries = "".join(
        '["{}"]={{{}}},\n'.format(name, ",".join(f'"{class_}"' for class_ in classes_))
        for name, classes_ in sorted(classes.items())
    )
    write(root / "data" / BUILD / "restrictions.lua", "return {\n" + entries + "}\n")
    print(f"{RESTRICTIONS.name}: {len(classes)} restricted names from build {BUILD}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--locale", action="append", default=[], choices=LOCALES)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument(
        "--refresh-restrictions",
        action="store_true",
        help="rewrite forever_sim/restrictions.txt from the wiki's restrictedapi template",
    )
    parser.add_argument(
        "--probe",
        type=Path,
        help="a ForeverProbe SavedVariables file: merge every block the live client recorded into restrictions.txt",
    )
    args = parser.parse_args(argv)
    if args.probe and not args.refresh_restrictions:
        parser.error("--probe needs --refresh-restrictions")
    root = args.cache or cache_dir()
    ui = fetch_ui(root, args.offline)
    if args.refresh_restrictions:
        classes = fetch_restrictions(ui)
        if args.probe:
            classes = merge_probe(classes, probe_blocks(args.probe))
        write_restrictions(classes, root, probed=args.probe is not None)
        return 0
    build_undocumented(root, ui)
    build_data(root, ["enUS", *[x for x in args.locale if x != "enUS"]], args.offline)
    print(f"forever_sim: UI source {UI_REVISION[:12]} and build {BUILD} data in {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
