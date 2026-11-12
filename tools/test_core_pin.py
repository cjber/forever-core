"""Tests for the vendored ForeverCore pin comparison shared by check_consumers.py and the package job."""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLING = Path(__file__).resolve().parent.parent / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))

from forever_tools import core_pin, package  # noqa: E402


class CorePinTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "legacy-forever"
        (self.root / "tools").mkdir(parents=True)
        self.pin = self.root / "tools" / "forever-core.txt"
        self.pkgmeta = self.root / ".pkgmeta"
        self.toc = self.root / "LegacyForever.toc"

    def write(self, pin="v1.4.0", external="v1.4.0", toc="v1.4.0", package="LegacyForever"):
        self.pin.write_text(f"{pin}\n", encoding="utf-8")
        self.pkgmeta.write_text(
            f"package-as: {package}\n\n"
            "externals:\n"
            f"  ForeverCore: https://github.com/cjber/forever-core/releases/download/{external}/"
            f"ForeverCore-{external}-forever.zip\n",
            encoding="utf-8",
        )
        self.toc.write_text(f"## Interface: 16001\n## Dependencies: ForeverCore\n## X-Forever-Core: {toc}\n")

    def test_three_copies_of_one_release_pass(self):
        self.write()
        self.assertEqual(core_pin.check(self.root), [])
        self.assertEqual(core_pin.main(self.root), 0)

    def test_an_external_from_another_release_fails(self):
        self.write(external="v1.4.1")
        failures = core_pin.check(self.root)
        self.assertEqual(len(failures), 1)
        self.assertIn("`externals:` ships ForeverCore from", failures[0])
        self.assertIn("tools/forever-core.txt pins v1.4.0", failures[0])
        self.assertIn("/v1.4.0/ForeverCore-v1.4.0-forever.zip", failures[0])

    def test_a_toc_field_from_another_release_fails(self):
        self.write(toc="v1.3.2")
        failures = core_pin.check(self.root)
        self.assertEqual(len(failures), 1)
        self.assertIn("`## X-Forever-Core:` is v1.3.2", failures[0])
        self.assertIn("tools/forever-core.txt pins v1.4.0, so it must be v1.4.0", failures[0])

    def test_a_missing_toc_field_fails(self):
        self.write()
        self.toc.write_text("## Interface: 16001\n## Dependencies: ForeverCore\n", encoding="utf-8")
        failures = core_pin.check(self.root)
        self.assertEqual(len(failures), 1)
        self.assertIn("add `## X-Forever-Core: v1.4.0`", failures[0])

    def test_a_consumer_that_bundles_no_core_is_skipped(self):
        self.pin.write_text("v1.4.0\n", encoding="utf-8")
        self.pkgmeta.write_text("package-as: LegacyForever\n\noptional-dependencies:\n  - questie\n", encoding="utf-8")
        self.toc.write_text("## Interface: 16001\n## OptionalDeps: Questie\n", encoding="utf-8")
        self.assertEqual(core_pin.check(self.root), [])

    def test_a_consumer_without_a_pkgmeta_is_skipped(self):
        self.assertEqual(core_pin.check(self.root), [])

    def test_a_missing_pin_fails_when_core_is_bundled(self):
        self.write()
        self.pin.unlink()
        failures = core_pin.check(self.root)
        self.assertEqual(len(failures), 1)
        self.assertIn("no pin names the release to ship", failures[0])

    def test_the_standalone_command_reports_a_disagreement(self):
        self.write(external="v1.4.1")
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            self.assertEqual(core_pin.main(self.root), 1)
        self.assertIn("`externals:` ships ForeverCore from", out.getvalue())

    def test_the_latest_gate_passes_the_newest_pin(self):
        self.write()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(core_pin.main(self.root, True, fetch=lambda: "v1.4.0"), 0)
        self.assertIn("pin names core's latest published release", out.getvalue())

    def test_the_latest_gate_fails_an_older_pin(self):
        self.write()
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            self.assertEqual(core_pin.main(self.root, True, fetch=lambda: "v1.5.0"), 1)
        self.assertIn("pin v1.4.0, core's latest release is v1.5.0", out.getvalue())

    def test_the_latest_gate_reads_the_release_with_a_token(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"tag_name": "v1.5.0"}'
        response.__exit__.return_value = False
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": "secret-token"}, clear=True),
            mock.patch.object(core_pin.urllib.request, "urlopen", return_value=response) as urlopen,
        ):
            self.assertEqual(core_pin.latest_release(), "v1.5.0")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, core_pin.LATEST_RELEASE_URL)
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")

    def test_the_latest_gate_fails_closed_when_the_release_cannot_be_read(self):
        self.write()

        def unreadable():
            raise core_pin.LatestReleaseUnavailable("503")

        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            self.assertEqual(core_pin.main(self.root, True, fetch=unreadable), 1)
        self.assertIn("could not read cjber/forever-core's latest published release (503)", out.getvalue())
        self.assertIn("refusing to pass the pin against an unknown release", out.getvalue())

    def test_a_checkout_that_does_not_use_core_needs_no_network_read(self):
        def unreadable():
            raise AssertionError("a checkout without core must not read the latest release")

        self.assertEqual(core_pin.check_latest(self.root, fetch=unreadable), [])

    def test_an_empty_pin_file_fails_closed(self):
        self.write()
        self.pin.write_text("\n", encoding="utf-8")
        failures = core_pin.check(self.root, "v1.4.0")
        self.assertIn("pin (empty), core's latest release is v1.4.0", "\n".join(failures))
        self.assertTrue(any("no pin names the release to ship" in failure for failure in failures))

    def test_a_missing_pin_still_fails_closed_when_the_checkout_bundles_core(self):
        self.write()
        self.pin.unlink()
        failures = core_pin.check_latest(self.root, fetch=lambda: "v1.4.0")
        self.assertEqual(len(failures), 1)
        self.assertIn("no pin names the release to ship", failures[0])

    def test_a_consumer_without_a_bundle_still_checks_its_pin(self):
        self.pin.write_text("v1.3.2\n", encoding="utf-8")
        self.pkgmeta.write_text("package-as: KilnForever\n", encoding="utf-8")
        failures = core_pin.check(self.root, "v1.4.0")
        self.assertEqual(len(failures), 1)
        self.assertIn("pin v1.3.2, core's latest release is v1.4.0", failures[0])

    def test_the_package_job_passes_three_copies_of_one_release(self):
        self.write()
        policy = package.Policy(addons=("LegacyForever",))
        with (
            mock.patch.object(package, "check", return_value=[]),
            mock.patch.object(core_pin, "latest_release", return_value="v1.4.0"),
            mock.patch.object(package.lua51, "check", return_value=[]),
            mock.patch.object(package, "run_specs", return_value=[]),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(package.main(self.root, policy, []), 0)

    def test_the_package_job_fails_a_disagreeing_bundle(self):
        self.write(external="v1.4.1")
        policy = package.Policy(addons=("LegacyForever",))
        out = io.StringIO()
        with (
            mock.patch.object(package, "check", return_value=[]),
            mock.patch.object(core_pin, "latest_release", return_value="v1.4.0"),
            mock.patch.object(package.lua51, "check", return_value=[]),
            mock.patch.object(package, "run_specs", return_value=[]),
            contextlib.redirect_stderr(out),
        ):
            self.assertEqual(package.main(self.root, policy, []), 1)
        self.assertIn("`externals:` ships ForeverCore from", out.getvalue())

    def test_the_package_job_fails_a_pin_behind_the_latest_release(self):
        self.write()
        policy = package.Policy(addons=("LegacyForever",))
        out = io.StringIO()
        with (
            mock.patch.object(package, "check", return_value=[]),
            mock.patch.object(core_pin, "latest_release", return_value="v1.5.0"),
            mock.patch.object(package.lua51, "check", return_value=[]),
            mock.patch.object(package, "run_specs", return_value=[]),
            contextlib.redirect_stderr(out),
        ):
            self.assertEqual(package.main(self.root, policy, []), 1)
        self.assertIn("pin v1.4.0, core's latest release is v1.5.0", out.getvalue())

    def test_the_package_job_fails_closed_when_the_latest_release_is_unknown(self):
        self.write()
        policy = package.Policy(addons=("LegacyForever",))
        out = io.StringIO()
        with (
            mock.patch.object(package, "check", return_value=[]),
            mock.patch.object(core_pin, "latest_release", side_effect=core_pin.LatestReleaseUnavailable("404")),
            mock.patch.object(package.lua51, "check", return_value=[]),
            mock.patch.object(package, "run_specs", return_value=[]),
            contextlib.redirect_stderr(out),
        ):
            self.assertEqual(package.main(self.root, policy, []), 1)
        self.assertIn("could not read cjber/forever-core's latest published release (404)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
