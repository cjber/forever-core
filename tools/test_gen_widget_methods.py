"""The committed widget-method data (the methods that take parameters) matches the pinned API annotations.

Skipped when the annotations are not checked out: `tools/typecheck.sh` fetches them, and CI's typecheck job runs
that. The tooling's own tests cover the generator on a fixture either way.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLING = ROOT / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))

from forever_tools import widget_handlers  # noqa: E402

from tools.gen_widget_methods import pinned_revision  # noqa: E402

ANNOTATIONS = ROOT / ".types/vscode-wow-api"
DATA = TOOLING / "forever_tools" / widget_handlers.METHODS


class AnnotationPinTest(unittest.TestCase):
    def test_revision_matches_toolchain(self):
        toolchain = json.loads((ROOT / "tools/toolchain.json").read_text(encoding="utf-8"))
        self.assertEqual(pinned_revision(), toolchain["tools"]["annotations"]["commit"])


@unittest.skipUnless(ANNOTATIONS.is_dir(), "the pinned API annotations are not checked out")
class WidgetMethodsDataTest(unittest.TestCase):
    def test_the_committed_data_is_the_generated_data(self):
        methods = widget_handlers.annotation_methods(ANNOTATIONS / widget_handlers.ANNOTATIONS)
        self.assertEqual(DATA.read_text(encoding="utf-8"), widget_handlers.render(methods, pinned_revision()))
        self.assertEqual(widget_handlers.methods(), frozenset(methods))


if __name__ == "__main__":
    unittest.main()
