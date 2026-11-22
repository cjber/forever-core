import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

from forever_tools import changelog

BASE = "# Changelog\n\n## [1.0.0] - 2026-01-01\n\n- First.\n"


class FragmentsTest(unittest.TestCase):
    def repo(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.git(root, "init", "-b", "main")
        (root / "CHANGELOG.md").write_text(BASE)
        self.commit(root)
        self.git(root, "tag", "v1.0.0")
        return root

    def git(self, root, *args):
        return subprocess.run(
            [
                "git",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "tag.gpgsign=false",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                *args,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def commit(self, root):
        self.git(root, "add", ".")
        self.git(root, "commit", "-m", "test")

    def note(self, root, slug, body):
        (root / "changes").mkdir(exist_ok=True)
        (root / "changes" / f"{slug}.md").write_text(body)

    def test_independent_branches_merge_in_either_order_and_release_literal(self):
        for order in [("one", "two"), ("two", "one")]:
            root = self.repo()
            for name in order:
                self.git(root, "checkout", "-b", name, "main")
                self.note(root, name, f"### Fixed\n\n- {name}.\n  Continued.\n")
                self.commit(root)
                changelog.check_base(root, "main")
            self.git(root, "checkout", "main")
            for name in order:
                self.git(root, "merge", "--no-edit", name)
            changelog.main(root, ["release", "1.0.1", "--date", "2026-11-17"])
            expected = (
                "# Changelog\n\n## [1.0.1] - 2026-11-17\n\n### Fixed\n\n- one.\n  Continued.\n- two.\n  Continued.\n\n"
                + BASE.split("\n\n", 1)[1]
            )
            self.assertEqual((root / "CHANGELOG.md").read_text(), expected)
            self.assertEqual(list((root / "changes").glob("*.md")), [])
            self.commit(root)
            changelog.check_base(root, "v1.0.0")
            self.git(root, "tag", "v1.0.1")
            with self.assertRaises(SystemExit):
                changelog.check_base(root, "v1.0.0")

    def test_release_leaves_no_trailing_blank_line_and_check_tolerates_one(self):
        # #1054: release must not end the file with a blank line, and --check --base must not
        # fail just because the base had one (EOF blank lines carry no content).
        root = self.repo()
        blank = root / "CHANGELOG.md"
        blank.write_text(BASE + "\n")
        self.commit(root)
        self.note(root, "one", "### Added\n\n- One.\n")
        changelog.main(root, ["release", "1.0.1", "--date", "2026-11-17"])
        written = (root / "CHANGELOG.md").read_text()
        self.assertTrue(written.endswith("\n"))
        self.assertFalse(written.endswith("\n\n"), "release left a trailing blank line")
        self.commit(root)
        changelog.check_base(root, "v1.0.0")
        self.git(root, "tag", "v1.0.1")
        # A later branch that only normalises the base's stray blank line is not a changelog change.
        self.git(root, "checkout", "-b", "trim", "main")
        (root / "CHANGELOG.md").write_text(written.rstrip("\n") + "\n\n")
        self.note(root, "two", "### Fixed\n\n- Two.\n")
        changelog.main(root, ["release", "1.0.2", "--date", "2026-11-18"])
        self.commit(root)
        changelog.check_base(root, "main")

    def test_release_joins_fragments_to_an_untagged_section_in_preparation(self):
        root = self.repo()
        prepared = BASE.replace(
            "## [1.0.0]", "## [1.0.1] - 2026-11-16\n\n- Prepared.\n\n### Fixed\n\n- Earlier.\n\n## [1.0.0]"
        )
        (root / "CHANGELOG.md").write_text(prepared)
        self.commit(root)
        self.git(root, "checkout", "-b", "late")
        self.note(root, "late", "### Added\n\n- New.\n\n### Fixed\n\n- Late.\n")
        changelog.main(root, ["release", "1.0.1", "--date", "2026-11-17"])
        self.assertEqual(
            (root / "CHANGELOG.md").read_text(),
            BASE.replace(
                "## [1.0.0]",
                "## [1.0.1] - 2026-11-17\n\n- Prepared.\n\n### Added\n\n- New.\n\n"
                "### Fixed\n\n- Earlier.\n- Late.\n\n## [1.0.0]",
            ),
        )
        self.commit(root)
        changelog.check_base(root, "main")
        self.git(root, "tag", "v1.0.1")
        self.note(root, "after", "### Fixed\n\n- After.\n")
        with self.assertRaisesRegex(SystemExit, "newer than every existing section"):
            changelog.main(root, ["release", "1.0.1"])

    def test_first_changelog_on_a_new_repository_passes(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.git(root, "init", "-b", "main")
        (root / "README.md").write_text("Fresh.\n")
        self.commit(root)
        self.git(root, "checkout", "-b", "first")
        (root / "CHANGELOG.md").write_text(BASE)
        self.commit(root)
        changelog.check_base(root, "main")

    def test_first_release_after_an_intro_only_changelog(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.git(root, "init", "-b", "main")
        (root / "CHANGELOG.md").write_text("# Changelog\n\nWhat changed.\n")
        (root / "docs" / "screenshots").mkdir(parents=True)
        (root / "docs" / "screenshots" / "hero.png").write_bytes(b"png")
        self.note(root, "1", "<!-- discord-image: docs/screenshots/hero.png -->\n\n### Added\n\n- First.\n")
        self.commit(root)
        self.git(root, "checkout", "-b", "release")
        changelog.main(root, ["release", "0.1.0", "--date", "2026-11-20"])
        self.commit(root)
        changelog.check_base(root, "main")
        (root / "CHANGELOG.md").write_text(
            (root / "CHANGELOG.md").read_text().replace("What changed.", "What changed, edited.")
        )
        self.commit(root)
        with self.assertRaisesRegex(SystemExit, "changes/<slug>"):
            changelog.check_base(root, "main")

    def test_history_edits_rejected(self):
        for text in [
            BASE + "- Bad.\n",
            BASE.replace("## [1.0.0]", "## [1.0.1] - 2026-11-17\n\n- New.\n\n## [1.0.0]") + "- Bad.\n",
            BASE.replace("## [1.0.0]", "## [Unreleased]\n\n- Bad.\n\n## [1.0.0]"),
            BASE.replace("# Changelog", "# Changed"),
        ]:
            root = self.repo()
            (root / "CHANGELOG.md").write_text(text)
            self.commit(root)
            with self.assertRaisesRegex(SystemExit, "changes/<slug>"):
                changelog.check_base(root, "v1.0.0")

    def test_migrate_preserves_images_bullets_and_author_notes(self):
        root = self.repo()
        body = (
            "<!-- discord-image: docs/x.png -->\n\n- Player. Thanks to Name.\n  More.\n\n"
            "### For addon authors\n\n- API.\n"
        )
        (root / "CHANGELOG.md").write_text(BASE.replace("## [1.0.0]", "## [Unreleased]\n\n" + body + "\n## [1.0.0]"))
        changelog.main(root, ["fragment", "751"])
        self.assertEqual((root / "CHANGELOG.md").read_text(), BASE)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            changelog.main(root, ["unreleased"])
        self.assertEqual(output.getvalue(), body.replace("- Player.", "### Changed\n\n- Player."))
        with self.assertRaisesRegex(SystemExit, "overwrite"):
            changelog.main(root, ["fragment", "751"])

    def test_invalid_fragments_and_unreleased_heading_fail_check(self):
        root = self.repo()
        for body in [
            "",
            "text\n### Fixed\n- x",
            "### Unknown\n- x",
            "### Fixed\n",
            "### Fixed\n- x\n<!-- discord-image: x.png -->",
        ]:
            self.note(root, "bad", body)
            with self.assertRaisesRegex(SystemExit, "bad.md.*allowed sections"):
                changelog.main(root, ["--check"])
        (root / "changes/bad.md").unlink()
        for body in ["", "- x\n"]:
            (root / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n" + body + BASE)
            with self.assertRaisesRegex(SystemExit, "change notes now live"):
                changelog.main(root, ["--check"])

    def test_section_order_images_and_invalid_bodies(self):
        root = self.repo()
        image = "<!-- discord-image: docs/x.png -->"
        self.note(root, "z", f"{image}\n\n### Fixed\n\n- Z.\n\n### Added\n\n- New.\n")
        self.note(root, "a", f"{image}\n\n### Fixed\n\n- A.\n")
        self.assertEqual(changelog.pending(root)[1], f"{image}\n\n### Added\n\n- New.\n\n### Fixed\n\n- A.\n- Z.\n")
        for body in [
            "### Fixed\n",
            "### Fixed\n\ntext",
            "### Fixed\n- Fine\n### Other\n- Bad",
            "### Fixed\n- Fine\n" + image,
        ]:
            self.note(root, "bad", body)
            with self.assertRaisesRegex(SystemExit, "bad.md.*Added, Changed, Fixed, Removed, For addon authors"):
                changelog.main(root, ["--check"])

    def test_failed_release_leaves_files_untouched(self):
        root = self.repo()
        self.note(root, "x", "### Added\n\n- Feature.\n")
        for version in ["1.0.0", "0.9.0", "1.1.0"]:
            with self.assertRaises(SystemExit):
                changelog.main(root, ["release", version])
            self.assertEqual((root / "CHANGELOG.md").read_text(), BASE)
            self.assertTrue((root / "changes/x.md").exists())
        (root / "changes/x.md").unlink()
        with self.assertRaises(SystemExit):
            changelog.main(root, ["release", "1.0.1"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            changelog.main(root, ["unreleased"])
        self.assertEqual(output.getvalue(), "")

    def test_migration_commit_allows_only_removing_unreleased(self):
        for edit_release in (False, True):
            root = self.repo()
            (root / "CHANGELOG.md").write_text(
                BASE.replace("## [1.0.0]", "## [Unreleased]\n\n- Pending.\n\n## [1.0.0]")
            )
            self.commit(root)
            self.git(root, "checkout", "-b", "migration")
            changelog.main(root, ["fragment", "751"])
            if edit_release:
                (root / "CHANGELOG.md").write_text(BASE.replace("First.", "Edited."))
            self.commit(root)
            if edit_release:
                with self.assertRaises(SystemExit) as error:
                    changelog.check_base(root, "main")
                self.assertEqual(
                    str(error.exception),
                    "CHANGELOG.md changes in this PR must be whole new release sections written by "
                    "`python3 tools/changelog.py release X.Y.Z`; put change notes in changes/<slug>.md "
                    "(slug: your issue number). Notes under ## [Unreleased] move there with "
                    "`python3 tools/changelog.py fragment <slug>`.",
                )
            else:
                changelog.check_base(root, "main")

    def test_empty_unreleased_migration_removes_heading_without_fragment(self):
        root = self.repo()
        (root / "CHANGELOG.md").write_text(BASE.replace("## [1.0.0]", "## [Unreleased]\n\n## [1.0.0]"))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            changelog.main(root, ["fragment", "751"])
        self.assertEqual((root / "CHANGELOG.md").read_text(), BASE)
        self.assertFalse((root / "changes/751.md").exists())
        self.assertIn("no notes to move", output.getvalue())

    def test_fragment_errors_explain_the_problem_and_allowed_sections(self):
        for filename, body, reason in [
            ("bad.md", "", "empty fragment"),
            ("bad.md", "text", "text before the first heading"),
            ("bad.md", "### Unknown\n- x", "unknown heading Unknown"),
            ("bad.md", "### Fixed\n", "empty section Fixed"),
            ("bad.md", "### Fixed\n- x\n### Fixed\n- y", "duplicate section Fixed"),
            ("Bad.md", "### Fixed\n- x", "bad file name"),
        ]:
            with self.subTest(reason=reason), self.assertRaises(SystemExit) as error:
                changelog.parse_fragment(Path(filename), body)
            self.assertIn(reason, str(error.exception))
            self.assertIn("allowed sections: " + ", ".join(changelog.SECTIONS), str(error.exception))

    def test_a_release_commit_that_still_holds_fragments_fails_its_version_check(self):
        root = self.repo()
        self.note(root, "751", "### Fixed\n\n- Fix.\n")
        with contextlib.redirect_stdout(io.StringIO()):
            changelog.main(root, ["release", "1.0.1", "--date", "2026-11-17"])
            changelog.main(root, ["--check", "1.0.1"])
        self.note(root, "752", "### Added\n\n- Late.\n")
        with self.assertRaises(SystemExit) as error:
            changelog.main(root, ["--check", "v1.0.1"])
        self.assertIn("1.0.1 cannot be released while changes/ holds 752.md", str(error.exception))
        self.assertIn("python3 tools/changelog.py release 1.0.1", str(error.exception))

    def test_release_prints_only_written_section_and_check_prints_status(self):
        root = self.repo()
        self.note(root, "751", "### Fixed\n\n- Fix.\n")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            changelog.main(root, ["release", "1.0.1", "--date", "2026-11-17"])
        self.assertEqual(output.getvalue(), "Wrote ## [1.0.1] - 2026-11-17 from 1 fragment(s)\n")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            changelog.main(root, ["--check"])
        self.assertEqual(output.getvalue(), "CHANGELOG.md documents 1.0.0\n")
