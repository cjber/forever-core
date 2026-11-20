"""Load ForeverCore and every published Forever addon together under forever_sim and exercise them.

Each addon's own CI exercises it alone. This runs `tests/suite/suite_scenario.lua`, which registers all of them in
one client, in the order their dependencies give the real client with ForeverCore first, and runs `sim:exercise()`:
every slash command of every addon twice, the world map, the same in combat, then a `/reload`. A clash between addons,
such as a shared global, a second owner of one slash command or one addon's taint reaching another's secure call,
fails it.

    python3 tools/suite_load.py                 # shallow clones of each addon's main under tools/.cache/suite
    python3 tools/suite_load.py --root ..       # the checkouts beside this one, as they are
    python3 tools/suite_load.py --released      # this checkout with every consumer's latest released build

`--released` is the core release gate: a core release reaches players before the consumers are re-released, so this
checkout's ForeverCore is loaded with the addon zips already on the stores (`tools/released_consumers.py`), and any
load or runtime error fails it. Run it on every core release candidate.

Fetch the Blizzard UI source first (`python3 .agents/skills/wow-forever-addon/tooling/forever_sim/fetch.py`).
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import released_consumers

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
    ("gathering-guide-forever", "GatheringGuideForever"),
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


def released_value(folders: list[tuple[str, Path]], core: Path = REPO) -> str:
    """FOREVER_SUITE for this checkout as ForeverCore and the consumers' released addon folders, core first.

    Consumers follow in `ADDONS` order, so the released run loads the suite the way the checkouts do; a released addon
    that list does not name follows alphabetically.
    """
    order = {folder: index for index, (_, folder) in enumerate(ADDONS)}
    released = sorted(folders, key=lambda entry: (order.get(entry[0], len(order)), entry[0]))
    return ";".join([f"{core}=ForeverCore", *(f"{path}={name}" for name, path in released)])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, help="use the checkouts under this folder instead of fresh clones")
    parser.add_argument(
        "--released",
        action="store_true",
        help="load this checkout with every consumer's latest released build, not the consumer checkouts",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="print the client's errors on a failure")
    arguments = parser.parse_args()

    if arguments.released:
        if arguments.root:
            parser.error("--released takes no --root: it loads the builds on the stores")
        try:
            value = released_value(released_consumers.released_folders())
        except released_consumers.ReleasedError as error:
            print(f"suite_load: {error}", file=sys.stderr)
            return 2
    else:
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
        value = suite_value(root)

    command = ["luajit", str(SIM / "run.lua"), "tests/suite"]
    if arguments.verbose:
        command.append("-v")
    environment = dict(os.environ, FOREVER_SUITE=value)
    return subprocess.run(command, cwd=REPO, env=environment, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
