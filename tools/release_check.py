"""Publish only a commit whose full CI run on main passed and whose newest headless smoke is green."""

import sys
from pathlib import Path

TOOLING = Path(__file__).resolve().parent.parent / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))

from forever_tools.release_check import headless_smoke, main, smoke_refusal, statuses, verified  # noqa: E402

__all__ = ["headless_smoke", "main", "smoke_refusal", "statuses", "verified"]

if __name__ == "__main__":
    main()
