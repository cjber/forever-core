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
            (root / "UI/Orphan.lua").write_text("local value = true\n")
            checkout = root / ".speedpatrol/runs/checkouts/base/tests"
            checkout.mkdir(parents=True)
            (checkout / "fixture.lua").write_text("fixture = true\n")
            with patch.object(deadcode, "ROOT", root):
                findings = deadcode.scan()
                self.assertIn(("UI/Orphan.lua", 1, "Lua file is not named by any TOC"), findings)
                self.assertNotIn(
                    (".speedpatrol/runs/checkouts/base/tests/fixture.lua", 1, "Lua file is not named by any TOC"),
                    findings,
                )

    def test_scratch_ancestor_does_not_hide_source(self):
        with tempfile.TemporaryDirectory(prefix="cb-core-") as directory:
            root = Path(directory) / ".speedpatrol" / "runs" / "checkouts" / "base"
            root.mkdir(parents=True)
            (root / "ForeverCore.toc").write_text("UI/Main.lua\n")
            (root / "UI").mkdir()
            (root / "UI/Main.lua").write_text("local value = true\n")
            (root / "UI/Orphan.lua").write_text("local value = true\n")
            with patch.object(deadcode, "ROOT", root):
                findings = deadcode.scan()
                self.assertIn(("UI/Orphan.lua", 1, "Lua file is not named by any TOC"), findings)

    def test_scratch_markdown_is_not_reference_input(self):
        with tempfile.TemporaryDirectory(prefix="cb-core-") as directory:
            root = Path(directory)
            (root / "README.md").write_text("root\n")
            scratch = root / ".bugpatrol/runs/checkouts/base"
            scratch.mkdir(parents=True)
            (scratch / "README.md").write_text("scratch\n")
            with patch.object(deadcode, "ROOT", root):
                self.assertEqual(
                    [path.relative_to(root).as_posix() for path in deadcode.source_files("*.md")],
                    ["README.md"],
                )


if __name__ == "__main__":
    unittest.main()
