"""Verify actual-client evidence with the canonical shared checker."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/wow-forever-addon/tooling"))
from forever_tools.visual_proof import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
