"""Publish only a commit that passed the repository's complete CI workflow on main."""

import sys
from pathlib import Path

TOOLING = Path(__file__).resolve().parent.parent / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))

from forever_tools.release_check import main, verified  # noqa: E402

__all__ = ["main", "verified"]

if __name__ == "__main__":
    main()
