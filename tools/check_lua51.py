#!/usr/bin/env python3
"""Thin entrypoint for the canonical packaged Lua 5.1 parser gate."""

import sys
from pathlib import Path

TOOLING = Path(__file__).resolve().parents[1] / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))
from forever_tools import lua51  # noqa: E402


def main(argv: list[str]) -> int:
    roots = [Path(arg) for arg in argv] or [Path.cwd()]
    problems, count = [], 0
    for root in roots:
        if root.is_dir():
            count += len(lua51.loaded_lua(root))
            problems.extend(lua51.check(root))
        else:
            problems.extend(lua51.check(root.parent))
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(f"Lua 5.1 parser: checked {count} TOC Lua files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
