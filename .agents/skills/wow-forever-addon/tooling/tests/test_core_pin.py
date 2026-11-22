"""Tests for release-prep pin gating in forever_tools.core_pin."""

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

from forever_tools import core_pin


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class ReleasePrepPinTest(unittest.TestCase):
    """--latest-if-release-prep requires core's latest release only when CHANGELOG.md adds a version heading."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "skillup-forever"
        (self.root / "tools").mkdir(parents=True)
        git(self.root, "init", "--quiet", "--initial-branch=main")
        git(self.root, "config", "user.email", "test@example.com")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "config", "commit.gpgsign", "false")
        self.write_consumer(pin="v1.15.0")
        (self.root / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [1.14.2] - 2026-11-10\n\n### Fixed\n\n- Prior fix.\n",
            encoding="utf-8",
        )
        git(self.root, "add", "-A")
        git(self.root, "commit", "--quiet", "-m", "base")
        git(self.root, "checkout", "--quiet", "-b", "pr-branch")

    def write_consumer(self, pin: str = "v1.15.0", toc_pin: str | None = None):
        toc_pin = pin if toc_pin is None else toc_pin
        (self.root / "tools/forever-core.txt").write_text(f"{pin}\n", encoding="utf-8")
        (self.root / ".pkgmeta").write_text(
            "package-as: SkillUpForever\n\nembedded-libraries:\n  - forevercore\n",
            encoding="utf-8",
        )
        (self.root / "SkillUpForever.toc").write_text(
            f"## Interface: 16001\n## OptionalDeps: ForeverCore\n## X-Forever-Core: {toc_pin}\n"
            "## X-Forever-Core-Embed: 1\n",
            encoding="utf-8",
        )

    def add_changelog_version(self, heading: str = "## [1.14.3] - 2026-11-18"):
        path = self.root / "CHANGELOG.md"
        before = path.read_text(encoding="utf-8")
        entry = f"{heading}\n\n### Fixed\n\n- Release fix.\n\n"
        path.write_text(before.replace("## [1.14.2]", entry + "## [1.14.2]"), encoding="utf-8")
        git(self.root, "add", "CHANGELOG.md")
        git(self.root, "commit", "--quiet", "-m", "prepare release")

    def test_release_prep_pr_with_stale_pin_fails(self):
        self.add_changelog_version()
        failures = core_pin.check_latest_if_release_prep(self.root, "main", fetch=lambda: "v1.15.1")
        self.assertEqual(len(failures), 1)
        self.assertIn("pin v1.15.0, core's latest release is v1.15.1", failures[0])

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = core_pin.main(
                self.root,
                latest_if_release_prep=True,
                base="main",
                fetch=lambda: "v1.15.1",
            )
        self.assertEqual(code, 1)
        self.assertIn("pin v1.15.0, core's latest release is v1.15.1", err.getvalue())

    def test_normal_pr_with_stale_pin_passes_without_network(self):
        (self.root / "changes").mkdir()
        (self.root / "changes/123.md").write_text("### Fixed\n\n- Ordinary change.\n", encoding="utf-8")
        git(self.root, "add", "changes/123.md")
        git(self.root, "commit", "--quiet", "-m", "normal pr")

        def must_not_fetch():
            raise AssertionError("normal PR must not query core's latest release")

        self.assertEqual(core_pin.check_latest_if_release_prep(self.root, "main", fetch=must_not_fetch), [])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = core_pin.main(
                self.root,
                latest_if_release_prep=True,
                base="main",
                fetch=must_not_fetch,
            )
        self.assertEqual(code, 0)
        self.assertIn("no new CHANGELOG.md version heading", out.getvalue())

    def test_release_prep_pr_with_latest_pin_passes(self):
        self.write_consumer(pin="v1.15.1")
        self.add_changelog_version()
        git(self.root, "add", "-A")
        git(self.root, "commit", "--quiet", "--allow-empty", "-m", "bump pin")
        self.assertEqual(core_pin.check_latest_if_release_prep(self.root, "main", fetch=lambda: "v1.15.1"), [])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = core_pin.main(
                self.root,
                latest_if_release_prep=True,
                base="main",
                fetch=lambda: "v1.15.1",
            )
        self.assertEqual(code, 0)
        self.assertIn("pin names core's latest published release", out.getvalue())

    def test_release_prep_pr_fails_closed_when_latest_cannot_be_read(self):
        self.add_changelog_version()

        def unreadable():
            raise core_pin.LatestReleaseUnavailable("503")

        failures = core_pin.check_latest_if_release_prep(self.root, "main", fetch=unreadable)
        self.assertEqual(len(failures), 1)
        self.assertIn("refusing to pass the pin against an unknown release", failures[0])

    def test_unbracketed_version_heading_counts_as_release_prep(self):
        self.add_changelog_version("## 1.14.3 - 2026-11-18")
        failures = core_pin.check_latest_if_release_prep(self.root, "main", fetch=lambda: "v1.15.1")
        self.assertEqual(len(failures), 1)
        self.assertIn("pin v1.15.0, core's latest release is v1.15.1", failures[0])

    def test_first_changelog_adding_a_version_heading_counts_as_release_prep(self):
        root = Path(self.tmp.name) / "new-addon"
        (root / "tools").mkdir(parents=True)
        git(root, "init", "--quiet", "--initial-branch=main")
        git(root, "config", "user.email", "test@example.com")
        git(root, "config", "user.name", "Test")
        git(root, "config", "commit.gpgsign", "false")
        (root / "tools/forever-core.txt").write_text("v1.15.0\n", encoding="utf-8")
        (root / ".pkgmeta").write_text(
            "package-as: NewAddon\n\nembedded-libraries:\n  - forevercore\n",
            encoding="utf-8",
        )
        (root / "NewAddon.toc").write_text(
            "## Interface: 16001\n## OptionalDeps: ForeverCore\n## X-Forever-Core: v1.15.0\n"
            "## X-Forever-Core-Embed: 1\n",
            encoding="utf-8",
        )
        git(root, "add", "-A")
        git(root, "commit", "--quiet", "-m", "initial")
        git(root, "checkout", "--quiet", "-b", "release-0-1-0")
        (root / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [0.1.0] - 2026-11-18\n\n### Added\n\n- First release.\n",
            encoding="utf-8",
        )
        git(root, "add", "CHANGELOG.md")
        git(root, "commit", "--quiet", "-m", "first release")
        failures = core_pin.check_latest_if_release_prep(root, "main", fetch=lambda: "v1.15.1")
        self.assertEqual(len(failures), 1)
        self.assertIn("pin v1.15.0, core's latest release is v1.15.1", failures[0])

    def test_editing_existing_section_without_new_heading_is_not_release_prep(self):
        path = self.root / "CHANGELOG.md"
        path.write_text(path.read_text(encoding="utf-8") + "- Typo fix.\n", encoding="utf-8")
        git(self.root, "add", "CHANGELOG.md")
        git(self.root, "commit", "--quiet", "-m", "edit existing section")

        def must_not_fetch():
            raise AssertionError("existing section edit must not query core's latest release")

        self.assertEqual(core_pin.check_latest_if_release_prep(self.root, "main", fetch=must_not_fetch), [])

    def test_normal_pr_still_checks_offline_bundle_agreement(self):
        self.write_consumer(pin="v1.15.0", toc_pin="v1.14.0")
        failures = core_pin.check_latest_if_release_prep(self.root, "main", fetch=lambda: self.fail("no network"))
        self.assertEqual(len(failures), 1)
        self.assertIn("must be v1.15.0", failures[0])

    def test_unreadable_base_ref_fails_closed(self):
        failures = core_pin.check_latest_if_release_prep(self.root, "origin/does-not-exist", fetch=lambda: "v1.15.0")
        self.assertEqual(len(failures), 1)
        self.assertIn("refusing to skip the release-prep pin check", failures[0])

    def test_cli_argument_validation(self):
        for bad_args in (
            ["--latest-if-release-prep"],
            ["--base", "origin/main"],
            ["--latest", "--latest-if-release-prep", "--base", "origin/main"],
        ):
            with self.subTest(bad_args=bad_args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    core_pin.parse_args(bad_args)
                self.assertEqual(raised.exception.code, 2)

        parsed = core_pin.parse_args(["--latest-if-release-prep", "--base", "origin/main", str(self.root)])
        self.assertTrue(parsed.latest_if_release_prep)
        self.assertEqual(parsed.base, "origin/main")
        self.assertFalse(parsed.latest)
        self.assertEqual(parsed.root, self.root)

    def test_module_cli_passes_normal_pr_without_network(self):
        tooling_root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [
                "python3",
                "-m",
                "forever_tools.core_pin",
                "--latest-if-release-prep",
                "--base",
                "main",
                str(self.root),
            ],
            cwd=tooling_root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no new CHANGELOG.md version heading", result.stdout)


if __name__ == "__main__":
    unittest.main()
