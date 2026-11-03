"""Core's source-only modules remain valid in arbitrarily named worktrees."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import deadcode


class CoreWorktreeTest(unittest.TestCase):
    def test_source_only_modules_use_toc_identity(self):
        with tempfile.TemporaryDirectory(prefix="cb-core-") as directory:
            root = Path(directory)
            (root / "UI").mkdir()
            (root / "ForeverCore.toc").write_text("## Interface: 16001\n")
            (root / "UI/Report.lua").write_text('local icon = "media/Icon"\n')
            with patch.object(deadcode, "ROOT", root):
                self.assertEqual(deadcode.scan(), [])
            (root / "ForeverCore.toc").unlink()
            with patch.object(deadcode, "ROOT", root):
                self.assertEqual(len(deadcode.scan()), 2)

    def test_scratch_checkouts_are_not_scanned_as_source(self):
        with tempfile.TemporaryDirectory(prefix="cb-core-") as directory:
            root = Path(directory)
            (root / "ForeverCore.toc").write_text("UI/Main.lua\n")
            (root / "UI").mkdir()
            (root / "UI/Main.lua").write_text("local value = true\n")
            checkout = root / ".speedpatrol/runs/checkouts/base/tests"
            checkout.mkdir(parents=True)
            (checkout / "fixture.lua").write_text("fixture = true\n")
            with patch.object(deadcode, "ROOT", root):
                self.assertEqual(deadcode.scan(), [])


if __name__ == "__main__":
    unittest.main()
