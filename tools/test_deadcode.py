"""What the dead-code scan counts as source, and what it skips."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import deadcode


class CoreWorktreeTest(unittest.TestCase):
    def test_forever_core_checkout_is_not_scanned(self):
        with tempfile.TemporaryDirectory(prefix="cb-addon-") as directory:
            root = Path(directory)
            (root / "Addon.toc").write_text("Main.lua\n")
            (root / "Main.lua").write_text("local value = true\n")
            (root / "forever-core/UI").mkdir(parents=True)
            (root / "forever-core/UI/Report.lua").write_text('local icon = "media/Icon"\n')
            with patch.object(deadcode, "ROOT", root):
                self.assertEqual(deadcode.scan(), [])

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

    def test_only_patrol_run_subtrees_are_scratch(self):
        with tempfile.TemporaryDirectory(prefix="cb-core-") as directory:
            root = Path(directory)
            (root / "ForeverCore.toc").write_text("UI/Main.lua\n")
            (root / "UI").mkdir()
            (root / "UI/Main.lua").write_text("local value = true\n")
            (root / ".bugpatrol/instructions.md").parent.mkdir(parents=True)
            (root / ".bugpatrol/instructions.md").write_text("python3 tools/real.py\n")
            for path in (
                ".bugpatrol/runs/checkouts/base/ForeverCore.toc",
                ".sloppatrol/runs/checkouts/base/ForeverCore.toc",
                ".sloppatrol/script-tests/no-handwritten-creatures/invalid/head/UI/Fake.lua",
                ".speedpatrol/runs/checkouts/base/ForeverCore.toc",
                "scratch/ForeverCore.toc",
                ".release/ForeverCore.toc",
                "tools/.cache/ForeverCore.toc",
            ):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("UI/Fake.lua\n")
            with patch.object(deadcode, "ROOT", root):
                paths = {path.relative_to(root).as_posix() for path in deadcode.source_files("*.toc")}
                self.assertEqual(paths, {"ForeverCore.toc"})
                markdown = {path.relative_to(root).as_posix() for path in deadcode.source_files("*.md")}
                self.assertIn(".bugpatrol/instructions.md", markdown)
                # A patrol tool's script-test fixtures are deliberately broken Lua, never addon source.
                self.assertNotIn(
                    ".sloppatrol/script-tests/no-handwritten-creatures/invalid/head/UI/Fake.lua",
                    {path.relative_to(root).as_posix() for path in deadcode.source_files("*.lua")},
                )


class MediaPatternTest(unittest.TestCase):
    def test_a_formatted_texture_path_references_its_folder(self):
        with tempfile.TemporaryDirectory(prefix="cb-core-") as directory:
            root = Path(directory)
            (root / "ForeverCore.toc").write_text("UI/Main.lua\n")
            (root / "UI").mkdir()
            (root / "UI/Main.lua").write_text(
                'local path = string.format("Interface\\\\AddOns\\\\X\\\\media\\\\Numbers\\\\%d.tga", n)\n'
            )
            (root / "media/Numbers").mkdir(parents=True)
            (root / "media/Numbers/1.tga").write_bytes(b"")
            (root / "media/Numbers/2.blp").write_bytes(b"")
            with patch.object(deadcode, "ROOT", root):
                self.assertEqual(deadcode.scan(), [])

    def test_a_formatted_texture_path_with_no_files_is_an_error(self):
        with tempfile.TemporaryDirectory(prefix="cb-core-") as directory:
            root = Path(directory)
            (root / "ForeverCore.toc").write_text("UI/Main.lua\n")
            (root / "UI").mkdir()
            (root / "UI/Main.lua").write_text('local path = ("Interface\\AddOns\\X\\media\\Numbers\\%02d"):format(n)\n')
            with patch.object(deadcode, "ROOT", root):
                self.assertEqual(
                    deadcode.scan(),
                    [("UI/Main.lua", 1, "media reference does not exist: media/Numbers")],
                )

    def test_an_escaped_nested_texture_path_keeps_repeated_separators(self):
        with tempfile.TemporaryDirectory(prefix="cb-core-") as directory:
            root = Path(directory)
            (root / "ForeverCore.toc").write_text("UI/Main.lua\n")
            (root / "UI").mkdir()
            (root / "UI/Main.lua").write_text('local path = "media\\\\legacy-masks\\\\Mask000.tga"\n')
            (root / "media/legacy-masks").mkdir(parents=True)
            (root / "media/legacy-masks/Mask000.tga").write_bytes(b"")
            with patch.object(deadcode, "ROOT", root):
                self.assertEqual(deadcode.scan(), [])


if __name__ == "__main__":
    unittest.main()
