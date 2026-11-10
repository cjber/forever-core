"""Load ForeverCore and every published Forever addon together under forever_sim and exercise them.

Each addon's own CI exercises it alone. This runs `tests/suite/suite_scenario.lua`, which registers all of them in
one client, in the order their dependencies give the real client with ForeverCore first, and runs `sim:exercise()`:
every slash command of every addon twice, the world map, the same in combat, then a `/reload`. A clash between addons,
such as a shared global, a second owner of one slash command or one addon's taint reaching another's secure call,
fails it.

    python3 tools/suite_load.py                 # shallow clones of each addon's main under tools/.cache/suite
    python3 tools/suite_load.py --root ..       # the checkouts beside this one, as they are

Fetch the Blizzard UI source first (`python3 .agents/skills/wow-forever-addon/tooling/forever_sim/fetch.py`).
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SIM = REPO / ".agents/skills/wow-forever-addon/tooling/forever_sim"
CACHE = REPO / "tools/.cache/suite"

# Repository and addon folder, in load order: ForeverCore first, because every addon requires it.
ADDONS = (
    ("forever-core", "ForeverCore"),
    ("shortest-path-forever", "ShortestPathForever"),
    ("tweaks-forever", "TweaksForever"),
    ("skillup-forever", "SkillUpForever"),
    ("legacy-forever", "LegacyForever"),
    ("field-guide-forever", "FieldGuideForever"),
    ("commissions-forever", "CommissionsForever"),
    ("macro-assist-forever", "MacroAssistForever"),
    ("adventure-guide-forever", "AdventureGuideForever"),
)


def clone(repo: str, target: Path) -> None:
    """A shallow checkout of the repository's main, fetched again when it is already there."""
    url = f"https://github.com/cjber/{repo}.git"
    if (target / ".git").exists():
        subprocess.run(["git", "-C", str(target), "fetch", "-q", "--depth", "1", "origin", "main"], check=True)
        subprocess.run(["git", "-C", str(target), "reset", "-q", "--hard", "FETCH_HEAD"], check=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--depth", "1", url, str(target)], check=True)


def suite_value(root: Path) -> str:
    """FOREVER_SUITE for the scenario: `dir=Folder` pairs, separated by semicolons, in load order."""
    return ";".join(f"{root / repo}={folder}" for repo, folder in ADDONS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, help="use the checkouts under this folder instead of fresh clones")
    parser.add_argument("-v", "--verbose", action="store_true", help="print the client's errors on a failure")
    arguments = parser.parse_args()

    if arguments.root:
        root = arguments.root.resolve()
        missing = [repo for repo, _ in ADDONS if not (root / repo).is_dir()]
        if missing:
            print(f"suite_load: no checkout of {', '.join(missing)} under {root}", file=sys.stderr)
            return 2
    else:
        root = CACHE
        for repo, _ in ADDONS:
            clone(repo, root / repo)

    command = ["luajit", str(SIM / "run.lua"), "tests/suite"]
    if arguments.verbose:
        command.append("-v")
    environment = dict(os.environ, FOREVER_SUITE=suite_value(root))
    return subprocess.run(command, cwd=REPO, env=environment, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
