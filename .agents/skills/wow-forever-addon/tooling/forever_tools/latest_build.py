"""The newest WoW: Forever client build listed on wago.tools."""

import json
import urllib.request

BUILDS_URL = "https://wago.tools/api/builds"
# Wago publishes Forever under its own product key now (`wowf`); the builds before its creation sit in
# `wow_classic_beta`, which also carries other Classic betas. Read both and keep the Forever versions (1.6x).
PRODUCTS = ("wowf", "wow_classic_beta")
PREFIX = "1.6"


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def latest(user_agent: str) -> str:
    """The highest Forever build across every product wago.tools lists it under."""
    request = urllib.request.Request(BUILDS_URL, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=60) as response:
        builds = json.load(response)
    forever: list[str] = [
        build["version"]
        for product in PRODUCTS
        for build in builds.get(product, [])
        if build["version"].startswith(PREFIX)
    ]
    if not forever:
        raise SystemExit("no Forever build listed on wago.tools")
    return max(forever, key=version_key)
