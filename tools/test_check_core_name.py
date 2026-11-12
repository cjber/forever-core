"""Tests for tools/check_core_name.py, the one-word rule every addon vendors.

The two-word spelling is assembled here so this file, which the rule reads like any other text, stays clean.
"""

import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import check_core_name

OLD = "Forever" + " Core"
UPPER = "FOREVER" + " CORE"
TABBED = "Forever" + "\t" + "Core"
CLEAN = "Every ForeverCore addon shares one library.\nThe forever-core repository keeps it.\n"


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class CheckCoreNameTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "docs").mkdir()
        (self.root / "README.md").write_text(CLEAN, encoding="utf-8")
        # Shipped entries are history. In this checkout the two-word spelling below is already in the base commit, so
        # the `--base` tests prove only lines a change adds are read.
        (self.root / "CHANGELOG.md").write_text(
            f"# Changelog\n\n## [1.0.0] - 2026-01-01\n\n- {OLD} shipped.\n", encoding="utf-8"
        )
        git(self.root, "init", "--quiet", "--initial-branch=main")
        git(self.root, "config", "user.email", "test@example.com")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "config", "commit.gpgsign", "false")
        self.commit("base")
        git(self.root, "branch", "base")
        self.cwd = Path.cwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.cwd)

    def commit(self, message):
        git(self.root, "add", "-A")
        git(self.root, "commit", "--quiet", "--allow-empty", "-m", message)

    def run_check(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_core_name.main(list(argv))
        return code, out.getvalue()

    def test_one_word_passes_and_the_slug_is_not_text(self):
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("spells the addon one word", out)

    def test_two_words_in_a_comment_or_doc_fail(self):
        (self.root / "docs" / "notes.md").write_text(f"{OLD} owns the tracker.\n", encoding="utf-8")
        code, out = self.run_check()
        self.assertEqual(code, 1, out)
        self.assertIn(f"docs/notes.md:1: write ForeverCore, not '{OLD}'", out)

    def test_the_rule_ignores_case(self):
        (self.root / "UI").mkdir()
        (self.root / "UI" / "Main.lua").write_text(f"-- {UPPER} loads first\n", encoding="utf-8")
        code, out = self.run_check()
        self.assertEqual(code, 1, out)
        self.assertIn("UI/Main.lua:1", out)
        self.assertIn(f"'{UPPER}'", out)

    def test_a_tab_between_the_words_fails(self):
        (self.root / "README.md").write_text(f"{TABBED}\n", encoding="utf-8")
        code, out = self.run_check()
        self.assertEqual(code, 1, out)

    def test_shipped_changelog_history_is_skipped(self):
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

    def test_the_base_form_catches_a_new_changelog_line(self):
        (self.root / "CHANGELOG.md").write_text(
            f"# Changelog\n\n## [1.0.0] - 2026-01-01\n\n- {OLD} shipped.\n\n## [Unreleased]\n\n- {OLD} is older.\n"
        )
        self.commit("new notes")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 1, out)
        self.assertIn("CHANGELOG.md:9: write ForeverCore", out)

    def test_the_base_form_leaves_shipped_history_alone(self):
        (self.root / "CHANGELOG.md").write_text(
            f"# Changelog\n\n## [1.0.0] - 2026-01-01\n\n- {OLD} shipped.\n\n## [Unreleased]\n\n- One word now.\n"
        )
        self.commit("changelog")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 0, out)
        self.assertIn("the lines base...HEAD adds spells the addon one word", out)

    def test_the_base_form_reads_only_added_lines_in_a_changed_file(self):
        (self.root / "CHANGELOG.md").write_text(
            f"# Changelog\n\n## [1.0.0] - 2026-01-01\n\n- {OLD} shipped.\n\n## [Unreleased]\n\n- ForeverCore stays.\n"
        )
        self.commit("changelog")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 0, out)

    def test_an_empty_base_is_refused(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            check_core_name.main(["--base", " "])

    def test_a_binary_file_is_skipped(self):
        (self.root / "media").mkdir()
        (self.root / "media" / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n\0" + OLD.encode())
        code, out = self.run_check()
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
