"""Tests for tools/check_consumers.py's per-consumer pin and packaging checks, against throwaway trees."""

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import check_consumers

SHARED = b"# checker\n"


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class CheckConsumersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.core = base / "forever-core"
        (self.core / "tools").mkdir(parents=True)
        (self.core / "tools" / "check_core_shared.py").write_bytes(SHARED)
        # The latest release tag with --local is this checkout's newest v* tag, so the throwaway core is a git repo.
        git(self.core, "init", "--quiet", "--initial-branch=main")
        git(self.core, "config", "user.email", "test@example.com")
        git(self.core, "config", "user.name", "Test")
        git(self.core, "config", "commit.gpgsign", "false")
        git(self.core, "add", "-A")
        git(self.core, "commit", "--quiet", "-m", "core")
        git(self.core, "tag", "v1.4.0")

        self.checkouts = base / "consumers"
        self.repo = self.checkouts / "legacy-forever"
        (self.repo / "tools").mkdir(parents=True)
        (self.repo / "tools" / "check_core_shared.py").write_bytes(SHARED)
        self.pin = self.repo / "tools" / "forever-core.txt"
        self.pin.write_text("v1.4.0\n", encoding="utf-8")

        self.patches = [
            mock.patch.object(check_consumers, "CORE_ROOT", self.core),
            mock.patch.object(check_consumers, "VENDORED", {"tools/check_core_shared.py": ("legacy-forever",)}),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_consumers.main(["--local", str(self.checkouts)])
        return code, out.getvalue()

    def write_pkgmeta(self, text):
        (self.repo / ".pkgmeta").write_text(text, encoding="utf-8")

    def write_toc(self, text):
        (self.repo / "LegacyForever.toc").write_text(text, encoding="utf-8")

    def test_an_equal_pin_passes(self):
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_a_consumer_without_a_pin_is_not_checked(self):
        self.pin.unlink()
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_a_lagging_pin_fails(self):
        self.pin.write_text("v1.3.2\n", encoding="utf-8")
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("legacy-forever: tools/forever-core.txt: pin v1.3.2, core's latest release is v1.4.0", out)

    def test_the_pin_is_compared_numerically(self):
        git(self.core, "commit", "--quiet", "--allow-empty", "-m", "next")
        git(self.core, "tag", "v1.10.0")
        self.pin.write_text("v1.9.0\n", encoding="utf-8")
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("pin v1.9.0, core's latest release is v1.10.0", out)

    def test_an_externals_forevercore_entry_fails(self):
        self.write_pkgmeta(
            "package-as: LegacyForever\n\nexternals:\n  ForeverCore: https://example.test/ForeverCore.zip\n"
        )
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("legacy-forever: .pkgmeta: an externals entry ships ForeverCore", out)

    def test_a_missing_required_dependencies_entry_fails(self):
        self.write_pkgmeta("package-as: LegacyForever\n\noptional-dependencies:\n  - questie\n")
        self.write_toc("## Interface: 16001\n## Dependencies: ForeverCore\n")
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("required-dependencies:", out)
        self.assertIn("no `- forevercore`", out)

    def test_required_dependencies_and_no_externals_pass(self):
        self.write_pkgmeta("package-as: LegacyForever\n\nrequired-dependencies:\n  - forevercore\n")
        self.write_toc("## Interface: 16001\n## Dependencies: ForeverCore\n")
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_a_consumer_that_does_not_require_core_needs_no_relation(self):
        self.write_pkgmeta("package-as: LegacyForever\n\noptional-dependencies:\n  - questie\n")
        self.write_toc("## Interface: 16001\n## OptionalDeps: Questie\n")
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_an_unreadable_latest_release_skips_the_pin_check_without_failing(self):
        self.pin.write_text("v1.3.2\n", encoding="utf-8")
        out = io.StringIO()
        with (
            mock.patch.object(check_consumers, "local_latest_tag", return_value=None),
            contextlib.redirect_stdout(out),
        ):
            code = check_consumers.main(["--local", str(self.checkouts)])
        self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
