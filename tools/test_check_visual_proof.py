"""CI entry point for the visual proof tests, whose producer owns the suite in the addon skill pack.

`ci.yml` discovers `tools/test_*.py`, while `forever-tools.yml` runs the canonical
`.agents/skills/wow-forever-addon/tooling/tests/test_visual_proof.py` directly. A `load_tests` wrapper keeps the
suite in one place: discovery here runs that canonical module instead of a second copy of its tests.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLING = ROOT / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))

CANONICAL = TOOLING / "tests/test_visual_proof.py"


def load_tests(loader, standard_tests, pattern):
    spec = importlib.util.spec_from_file_location("canonical_test_visual_proof", CANONICAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return loader.loadTestsFromModule(module)


if __name__ == "__main__":
    unittest.main()
