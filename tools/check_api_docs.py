#!/usr/bin/env python3
"""Check docs/api.md names every function Core/API.lua publishes and its minor version.

The shared implementation lives in the addon skill pack's `forever_tools/docs_contract.py`.
"""

import sys
from pathlib import Path

TOOLING = Path(__file__).resolve().parent.parent / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))

from forever_tools.docs_contract import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(Path(__file__).resolve().parent.parent))
