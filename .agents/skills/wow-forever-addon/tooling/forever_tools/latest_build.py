"""The newest WoW: Forever client build listed on wago.tools."""

import json
import urllib.request

BUILDS_URL = "https://wago.tools/api/builds"


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def latest(user_agent: str) -> str:
    """The highest Forever build; wow_classic_beta carries other Classic betas too, and Forever builds are 1.6x."""
    request = urllib.request.Request(BUILDS_URL, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=60) as response:
        builds = json.load(response)["wow_classic_beta"]
    forever: list[str] = [b["version"] for b in builds if b["version"].startswith("1.6")]
    if not forever:
        raise SystemExit("no Forever build listed on wago.tools")
    return max(forever, key=version_key)
