"""One client icon per addon, declared once in the TOC and never repeated in shipped Lua.

Each Forever addon represents itself in game with a single client icon: its minimap button, Professions or
side tab, window portrait, leaderboard tab and addon compartment. The value lives in one place,
`## X-Forever-Icon: Interface\\Icons\\<name>`, and the runtime reads it with
`C_AddOns.GetAddOnMetadata(addonName, "X-Forever-Icon")`. This check fails an addon TOC (every TOC except
ForeverCore's) that omits the field, a value that is not a client icon in the pinned build, or the declared
path repeated in the addon's shipped Lua. A Forever addon is a TOC whose dependencies name ForeverCore; a library
shipped beside it, such as Tweaks' LibAHTab, has no identity of its own.
"""

import argparse
import re
from pathlib import Path

from . import assets, legacy_chrome, toc

FIELD = "X-Forever-Icon"
ICON = re.compile(r"(?i)^interface[\\/]+icons[\\/]+[^\\/]+$")


DEPENDENCY_FIELDS = {"## dependencies", "## requireddeps"}


def forever_addon(toc_path: Path) -> bool:
    """True when the TOC requires ForeverCore, which makes it a Forever addon with an identity."""
    for line in toc_path.read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.partition(":")
        if separator and name.strip().lower() in DEPENDENCY_FIELDS:
            if "forevercore" in (part.strip().lower() for part in value.split(",")):
                return True
    return False


def declared(toc_path: Path) -> str | None:
    """The X-Forever-Icon value in one TOC, or None when it does not declare it."""
    key = f"## {FIELD}".lower()
    for line in toc_path.read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.partition(":")
        if separator and name.strip().lower() == key:
            return value.strip()
    return None


def check(root: Path) -> list[str]:
    """Every problem with the repository's identity icons, as `file:line: message` or `file: message`."""
    root = root.resolve()
    problems = []
    for toc_path in toc.toc_files(root):
        if not forever_addon(toc_path):
            continue
        relative = toc_path.resolve().relative_to(root).as_posix()
        icon = declared(toc_path)
        if not icon:
            problems.append(f"{relative}: missing ## {FIELD}: Interface\\Icons\\<name>")
            continue
        if not ICON.match(icon):
            problems.append(f"{relative}: ## {FIELD} must be Interface\\Icons\\<name>, not {icon!r}")
            continue
        if not legacy_chrome.is_known(icon):
            problems.append(f"{relative}: ## {FIELD} {icon} is not in the {legacy_chrome.PINNED_BUILD} listfile")
            continue
        path = legacy_chrome.normalise(icon)
        try:
            loaded = toc.loaded_files(toc_path, root)
        except ValueError as error:
            problems.append(f"{relative}: {error}")
            continue
        for lua_path in (loaded_path for loaded_path in loaded if loaded_path.suffix.lower() == ".lua"):
            try:
                source = lua_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as error:
                problems.append(f"{lua_path.relative_to(root).as_posix()}: {error}")
                continue
            try:
                literals = assets.references(source, ".lua")
            except ValueError as error:  # forever_tools.lua.LuaSyntaxError
                problems.append(f"{lua_path.relative_to(root).as_posix()}: {error}")
                continue
            for line, value in literals:
                if legacy_chrome.normalise(value) == path:
                    problems.append(
                        f"{lua_path.relative_to(root).as_posix()}:{line}: "
                        f"repeats ## {FIELD} {icon}; read it from the TOC instead"
                    )
    return problems


def run(root: Path) -> int:
    root = root.resolve()
    problems = check(root)
    for problem in problems:
        print(problem)
    if not problems:
        count = sum(forever_addon(toc_path) for toc_path in toc.toc_files(root))
        print(f"Identity icon check: {count} addon TOC{'s' if count != 1 else ''} checked")
    return int(bool(problems))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return run(parser.parse_args(argv).root)


if __name__ == "__main__":
    raise SystemExit(main())
