import unittest
from pathlib import Path

from forever_tools import pkgmeta

TOOLS = Path(__file__).resolve().parent.parent / "forever_tools"


class VendoredKeywordTest(unittest.TestCase):
    def test_no_vendored_tool_spells_the_localization_keyword(self):
        # Consumers vendor these files and grep their whole tree for the keyword, since a shipped file carrying it
        # fails the release. A literal copy here fails every consumer gate after a sync.
        found = [
            path.name for path in sorted(TOOLS.glob("*.py")) if pkgmeta.LOCALIZATION in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(found, [])

    def test_the_split_constant_is_the_keyword(self):
        self.assertEqual(pkgmeta.LOCALIZATION, "@" + "localization")


if __name__ == "__main__":
    unittest.main()
