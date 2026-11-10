"""The generated pre-Legion chrome set and the few chrome paths it keeps.

`legacy_chrome.txt`, `interface_paths.txt` and `backdrops.txt` are produced by
`tools/gen_legacy_chrome.py` in forever-core and vendored with the rest of `forever_tools`. The age
rule itself lives in `assets.py`; this module only answers "is this path old chrome?", "is it in the
pinned build at all?", "which client files does this backdrop global name?" and "is it one of the few
pieces of old chrome that has no modern replacement?".
"""

import base64
import zlib
from bisect import bisect_left
from functools import lru_cache
from pathlib import Path

PINNED_BUILD = "1.60.1.70124"
LEGACY_FDID_LIMIT = 1_000_000
TEXTURE_EXTENSIONS = (".blp", ".tga")
DATA = Path(__file__).resolve().parent
TRACKING_ATLASES = {
    "ammunition": "Ammunition",
    "auctioneer": "Auctioneer",
    "banker": "Banker",
    "battlemaster": "BattleMaster",
    "class": "Class",
    "flightmaster": "FlightMaster",
    "food": "Food",
    "innkeeper": "Innkeeper",
    "mailbox": "Mailbox",
    "poisons": "Poisons",
    "profession": "Profession",
    "reagents": "Reagents",
    "repair": "Repair",
    "stablemaster": "StableMaster",
}

# Old chrome with no modern atlas or template. Keep one line per entry and say why it is still art
# the suite may draw. Everything else old is fixed, not allowlisted.
ALLOWLIST = {
    # wowmock reproduces these native widgets in screenshots. Each is the client's own piece and the
    # pinned build has no atlas for that exact art, so swapping one would draw a different widget.
    "interface/buttons/buttonhilight-square": "wowmock's native item-button hover overlay; no atlas is the same square",
    "interface/buttons/squarebuttontextures": "wowmock crops the world-map NavBar's own dropdown arrow from it",
    "interface/buttons/ui-checkbox-up": "wowmock's Edit Mode native checkbox face; no atlas is the 32x32 file",
    "interface/buttons/ui-checkbox-check": "wowmock's Edit Mode native checkbox tick; no atlas is the 32x32 file",
    "interface/chatframe/chatframeexpandarrow": "wowmock's native menu submenu arrow",
    "interface/common/shadowoverlay-left": "wowmock's native world-map NavBar shadow",
    "interface/common/ui-tooltipdivider-transparent": "wowmock's native menu divider",
    "interface/common/whiteiconframe": "the client's unframed-icon border, sanctioned by the asset registry",
    "interface/framegeneral/ui-background-marble": "wowmock's BasicFrameTemplate marble; no equivalent atlas",
    "interface/framegeneral/ui-background-rock": "wowmock's world-map rock backdrop; no equivalent atlas",
    "interface/helpframe/cs_helptextures": "wowmock's native world-map NavBar sheet",
    "interface/helpframe/cs_helptextures_tile": "wowmock's native world-map NavBar tile",
    "interface/minimap/minimap-trackingborder": "LibDBIcon's tracking-border art; no atlas is the same piece",
    "interface/minimap/ui-minimap-background": "LibDBIcon's button background art; no atlas is the same piece",
    "interface/minimap/ui-minimap-zoombutton-highlight": "LibDBIcon's button highlight art; no atlas is the same piece",
    "interface/questframe/ui-questlog-bookicon": "wowmock's native default world-map portrait",
    "interface/questframe/ui-questtitlehighlight": "wowmock's native menu row highlight",
}


def normalise(path: str) -> str:
    """A source path as the generated data stores it: lowercase, forward slashes, no .blp/.tga."""
    path = path.replace("\\", "/").lower()
    while "//" in path:
        path = path.replace("//", "/")
    for extension in TEXTURE_EXTENSIONS:
        if path.endswith(extension):
            return path[: -len(extension)]
    return path


def _data_lines(name: str) -> list[str]:
    lines = (DATA / name).read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line and not line.startswith("#")]


@lru_cache(maxsize=1)
def legacy_paths() -> frozenset[str]:
    return frozenset(_data_lines("legacy_chrome.txt"))


@lru_cache(maxsize=1)
def backdrops() -> dict[str, tuple[str, ...]]:
    """Each client backdrop global and the bgFile/edgeFile paths it names, from the pinned source."""
    return {name: tuple(paths) for name, *paths in (line.split() for line in _data_lines("backdrops.txt"))}


def backdrop_paths(name: str) -> tuple[str, ...]:
    """The client paths a backdrop global draws, or none when it is not one the pinned build defines."""
    return backdrops().get(name.strip(), ())


@lru_cache(maxsize=1)
def known_paths() -> tuple[str, ...]:
    raw = zlib.decompress(base64.b64decode("".join(_data_lines("interface_paths.txt"))))
    return tuple(raw.decode("utf-8").splitlines())


def is_legacy(path: str) -> bool:
    return normalise(path) in legacy_paths()


def is_known(path: str) -> bool:
    path = normalise(path)
    paths = known_paths()
    at = bisect_left(paths, path)
    return at < len(paths) and paths[at] == path


def is_path_prefix(path: str) -> bool:
    """Whether a known client path starts with this one, so a constant prefix is not called a typo."""
    path = normalise(path)
    paths = known_paths()
    at = bisect_left(paths, path)
    return at < len(paths) and paths[at].startswith(path)


def allowed(path: str) -> bool:
    return normalise(path) in ALLOWLIST


def _tracking_hint(path: str) -> str:
    """The atlas that replaced a 2004 minimap tracking icon."""
    if not path.startswith("interface/minimap/tracking/"):
        return ""
    atlas = TRACKING_ATLASES.get(path.rsplit("/", 1)[-1])
    return f" use the {atlas} atlas of the same name instead" if atlas else " use the atlas of the same name instead"


def reason(path: str) -> str | None:
    """Why this client path fails the age rule, or None when it is current, exempt or allowlisted."""
    path = normalise(path)
    if allowed(path):
        return None
    if is_legacy(path):
        hint = _tracking_hint(path)
        return f"pre-Legion UI chrome (FileDataID < {LEGACY_FDID_LIMIT});{hint or ' use an atlas'}"
    if not is_known(path):
        return f"unverifiable client path; not in the {PINNED_BUILD} listfile"
    return None
