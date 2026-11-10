"""Generate forever_tools' pre-Legion UI-chrome data from the pinned client listfile and UI source.

The rule is age based, not name based: a loose texture under `interface/` whose FileDataID is below
1,000,000 is pre-Legion chrome. FileDataIDs were assigned roughly in the order art was added: about
130,000-140,000 is the 2004 UI, and 200,000-1,000,000 is Cataclysm and Mists of Pandaria.

Run from the repository root when the pinned build's art changes:

    python3 tools/gen_legacy_chrome.py             # uses tools/.cache/legacy-chrome/
    python3 tools/gen_legacy_chrome.py --refresh   # download the listfile and Backdrop.lua again

The wago.tools endpoint is the pinned build's own file list (`version=`, plus `build=` so the
build is always explicit). Its unpaged CSV export times out, so this asks for the listfile's
`interface/` slice through the search API instead. The same listfile names the build's copy of
`Blizzard_SharedXML/Backdrop.lua`, whose FileDataID fetches its bytes from wago.tools, so the
backdrop globals and the paths they name come from the client itself. The data files are committed:

* `legacy_chrome.txt` -- the banned set, one lowercase extensionless path per line.
* `interface_paths.txt` -- a compact sorted, zlib-compressed set of every `interface/` path in the
  build, used for the "unverifiable client path" fallback.
* `backdrops.txt` -- each `BACKDROP_*` global and the `bgFile`/`edgeFile` paths it names, so the
  checker can follow a backdrop constant to the art it draws.
"""

import argparse
import base64
import json
import re
import sys
import textwrap
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents/skills/wow-forever-addon/tooling"))
from forever_tools import fsio, lua, wago  # noqa: E402

BUILD = "1.60.1.70124"
USER_AGENT = "ForeverCore/1.0 (+https://github.com/cjber/forever-core)"
DATA = ROOT / ".agents/skills/wow-forever-addon/tooling/forever_tools"
CACHE = ROOT / "tools/.cache/legacy-chrome" / f"listfile-{BUILD}.json"
URL = f"https://wago.tools/api/files?search=interface%2F&version={BUILD}&build={BUILD}"
BACKDROP_SOURCE = "interface/addons/blizzard_sharedxml/backdrop.lua"
BACKDROP_CACHE = CACHE.with_name(f"backdrop-{BUILD}.lua")
CASC_URL = f"https://wago.tools/api/casc/{{fdid}}?download&build={BUILD}"
BACKDROP_FIELDS = frozenset({"bgFile", "edgeFile"})

# --- category rules: data, not a path list -------------------------------------------------------
LEGACY_FDID_LIMIT = 1_000_000
TEXTURE_EXTENSIONS = (".blp", ".tga")
# Content, not chrome. Portraits and fonts are matched below because they are not one folder.
EXEMPT_PREFIXES = (
    "interface/icons/",
    "interface/worldmap/",  # includes the dungeon and zone map tiles
    "interface/cursor/",
    "interface/fontstyles/",
    # Minimap map content: quest and objective blobs, map tiles, pings, POI and unit markers,
    # arrows, vehicles and battleground props. Loose minimap chrome stays under the age rule, and
    # so do the 2004 tracking icons under interface/minimap/tracking/.
    "interface/minimap/argusvindicaar",
    "interface/minimap/compass",
    "interface/minimap/dungeon",
    "interface/minimap/humanuitile-timeindicator",
    "interface/minimap/mapfyrakkevent",
    "interface/minimap/mapquesthub",
    "interface/minimap/minimap-deadarrow",
    "interface/minimap/minimap-positionarrows",
    "interface/minimap/minimap-questarrow",
    "interface/minimap/minimap-vignettearrow",
    "interface/minimap/minimap-waypoint",
    "interface/minimap/minimap_chest",
    "interface/minimap/minimap_shield",
    "interface/minimap/minimap_skull",
    "interface/minimap/minimaparrow",
    "interface/minimap/minimapclock",
    "interface/minimap/minimapcompassring",
    "interface/minimap/minimapmailflipbook",
    "interface/minimap/minimaptrident",
    "interface/minimap/objecticons",
    "interface/minimap/override_art/",
    "interface/minimap/partyraidblips",
    "interface/minimap/ping",
    "interface/minimap/ui-minimap-ping",
    "interface/minimap/poiicons",
    "interface/minimap/raid",
    "interface/minimap/rotating-minimap",
    "interface/minimap/supertrackerarrow",
    "interface/minimap/suramar_door_icon",
    "interface/minimap/templeofkotmogu_ball",
    "interface/minimap/torghast/",
    "interface/minimap/trap",
    "interface/minimap/ui-archblob",
    "interface/minimap/ui-bonusobjectiveblob",
    "interface/minimap/ui-questblob",
    "interface/minimap/uieventpoiicons",
    "interface/minimap/vehicle-",
    "interface/taxiframe/",  # flight map nodes and route lines: map content
    # Empty equipment-slot art: the client hands these out itself through C_PaperDollInfo.GetInventorySlotInfo,
    # and its own character pane draws them, so an addon showing a slot draws exactly what the game does.
    "interface/paperdoll/ui-paperdoll-slot-",
    "interface/moneyframe/",  # coin icons
    "interface/lfgframe/lfgicon-",  # dungeon pictures
    "interface/targetingframe/ui-raidtargetingicon",  # raid marker icons
    "interface/buttons/white8x8",  # a solid fill primitive, not art
)
EXEMPT_PATTERNS = (
    re.compile(r"portrait"),
    re.compile(r"\.(?:ttf|otf)$"),
    re.compile(r"^interface/gossipframe/.*icon"),  # quest and gossip icons
)


def normalise(path: str) -> str:
    """A listfile or source path as the data stores it: lowercase, forward slashes, no texture suffix."""
    path = re.sub(r"/+", "/", path.replace("\\", "/").lower())
    for extension in TEXTURE_EXTENSIONS:
        if path.endswith(extension):
            return path[: -len(extension)]
    return path


def exempt(path: str) -> bool:
    return path.startswith(EXEMPT_PREFIXES) or any(pattern.search(path) for pattern in EXEMPT_PATTERNS)


def validate(data: bytes) -> None:
    """Reject an HTML error page or an empty listfile before it is cached."""
    try:
        rows = json.loads(data)
    except json.JSONDecodeError as error:
        raise ValueError(f"wago.tools returned non-JSON listfile data: {error}") from error
    if not isinstance(rows, dict) or len(rows) < 1000:
        raise ValueError("wago.tools returned an empty or implausibly small listfile")


def load(refresh: bool) -> dict[str, str]:
    data = wago.fetch(URL, CACHE, user_agent=USER_AGENT, refresh=refresh, timeout=900, validate=validate)
    return json.loads(data)


def validate_backdrop(data: bytes) -> None:
    """Reject an HTML error page or anything that is not the client's backdrop definitions."""
    if b"BACKDROP_" not in data or b"bgFile" not in data:
        raise ValueError("wago.tools returned something other than Blizzard_SharedXML/Backdrop.lua")


def load_backdrop(rows: dict[str, str], refresh: bool) -> str:
    """The pinned build's Backdrop.lua, found by path in the same listfile and fetched by FileDataID."""
    fdid = next((fdid for fdid, raw in rows.items() if raw.replace("\\", "/").lower() == BACKDROP_SOURCE), None)
    if fdid is None:
        raise SystemExit(f"the pinned listfile does not name {BACKDROP_SOURCE}")
    data = wago.fetch(
        CASC_URL.format(fdid=fdid),
        BACKDROP_CACHE,
        user_agent=USER_AGENT,
        refresh=refresh,
        timeout=900,
        validate=validate_backdrop,
    )
    return data.decode("utf-8")


def _symbol(token, text: str) -> bool:
    return token.kind == "symbol" and token.text == text


def parse_backdrops(source: str) -> dict[str, list[str]]:
    """Each global table with a `bgFile` or `edgeFile`, and the client paths that field names.

    Reads the definitions rather than trusting the global's name: a table is a backdrop because of its
    fields, and a path is normalised exactly as `legacy_chrome.txt` stores one.
    """
    tokens, _ = lua.tokenize(source)
    backdrops: dict[str, list[str]] = {}
    depth, at = 0, 0
    while at < len(tokens):
        token = tokens[at]
        if _symbol(token, "{"):
            depth += 1
        elif _symbol(token, "}"):
            depth -= 1
        elif (
            depth == 0
            and token.kind == "name"
            and at + 2 < len(tokens)
            and _symbol(tokens[at + 1], "=")
            and _symbol(tokens[at + 2], "{")
        ):
            name, files, inner_depth, cursor = token.text, [], 0, at + 2
            while cursor < len(tokens):
                current = tokens[cursor]
                if _symbol(current, "{"):
                    inner_depth += 1
                elif _symbol(current, "}"):
                    inner_depth -= 1
                    if inner_depth == 0:
                        break
                elif (
                    inner_depth == 1
                    and current.kind == "name"
                    and current.text in BACKDROP_FIELDS
                    and cursor + 2 < len(tokens)
                    and _symbol(tokens[cursor + 1], "=")
                    and tokens[cursor + 2].kind == "string"
                ):
                    files.append(normalise(tokens[cursor + 2].text[1:-1]))
                cursor += 1
            if files:
                backdrops[name] = sorted(set(files))
            at = cursor + 1
            continue
        at += 1
    return backdrops


def legacy_text(paths: list[str]) -> str:
    lines = [
        "# Pre-Legion UI chrome: interface/ textures with FileDataID < 1,000,000.",
        f"# Pinned client build {BUILD}. Lowercase, forward slashes, no .blp/.tga suffix.",
        "# Generated by tools/gen_legacy_chrome.py; do not edit by hand.",
        "",
        *paths,
    ]
    return "\n".join(lines) + "\n"


def known_text(paths: set[str]) -> str:
    raw = "\n".join(sorted(paths)).encode("utf-8")
    encoded = base64.b64encode(zlib.compress(raw, 9)).decode("ascii")
    lines = [
        f"# Every interface/ path in client build {BUILD}, sorted, newline-separated, then",
        "# zlib-compressed and base64-encoded. Lowercase, forward slashes, no .blp/.tga suffix.",
        "# Used to reject a path the listfile cannot resolve.",
        "# Generated by tools/gen_legacy_chrome.py; do not edit by hand.",
        "",
        *textwrap.wrap(encoded, width=120),
    ]
    return "\n".join(lines) + "\n"


def backdrop_text(backdrops: dict[str, list[str]]) -> str:
    lines = [
        "# The client's own backdrop globals, from Blizzard_SharedXML/Backdrop.lua.",
        f"# Pinned client build {BUILD}. Each line is the global, then the bgFile and edgeFile it names,",
        "# lowercased with forward slashes and no .blp/.tga suffix.",
        "# Generated by tools/gen_legacy_chrome.py; do not edit by hand.",
        "",
        *[f"{name} {' '.join(paths)}" for name, paths in sorted(backdrops.items())],
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--refresh", action="store_true", help="download the listfile and Backdrop.lua again instead of using the cache"
    )
    arguments = parser.parse_args()

    rows = load(arguments.refresh)
    legacy: set[str] = set()
    known: set[str] = set()
    for fdid, raw in rows.items():
        raw_path = raw.replace("\\", "/").lower()
        if not raw_path.startswith("interface/"):
            continue
        path = normalise(raw_path)
        known.add(path)
        if raw_path.endswith(TEXTURE_EXTENSIONS) and int(fdid) < LEGACY_FDID_LIMIT and not exempt(path):
            legacy.add(path)

    backdrops = parse_backdrops(load_backdrop(rows, arguments.refresh))

    outputs = {
        DATA / "legacy_chrome.txt": legacy_text(sorted(legacy)),
        DATA / "interface_paths.txt": known_text(known),
        DATA / "backdrops.txt": backdrop_text(backdrops),
    }
    fsio.publish(outputs)
    for path, text in outputs.items():
        print(f"{path.relative_to(ROOT)}: {len(text.encode('utf-8')):,} bytes")
    print(f"{len(legacy):,} legacy chrome paths, {len(known):,} known interface paths, {len(backdrops)} backdrops")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
