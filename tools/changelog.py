#!/usr/bin/env python3
"""Print one version's CHANGELOG.md section, or check that every release has one (stdlib only).

    python3 tools/changelog.py 0.2.0           # that version's entry (a leading v is fine)
    python3 tools/changelog.py --check         # every v* tag has an entry, and Unreleased is there
    python3 tools/changelog.py --check 0.3.0   # that version has an entry, before it is tagged

The shared implementation lives in the addon skill pack's `forever_tools/changelog.py`.
"""

import sys
from pathlib import Path

TOOLING = Path(__file__).resolve().parent.parent / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))

from forever_tools.changelog import main  # noqa: E402

if __name__ == "__main__":
    main(Path(__file__).resolve().parent.parent)
