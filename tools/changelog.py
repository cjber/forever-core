#!/usr/bin/env python3
"""Render release notes from changelog fragments, print a version, or validate a changelog (stdlib only).

    python3 tools/changelog.py 0.2.0           # that version's entry (a leading v is fine)
    python3 tools/changelog.py unreleased      # pending fragment notes, without a heading
    python3 tools/changelog.py release 0.3.0   # write the release section and consume fragments
    python3 tools/changelog.py fragment 751    # migrate an old Unreleased section
    python3 tools/changelog.py --check         # every v* tag has an entry
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
