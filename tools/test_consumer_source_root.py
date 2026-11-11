"""Consumer sync and drift checks use the producer even when launched elsewhere."""

import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import check_consumers


class ConsumerSourceRootTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.producer = root / "producer"
        self.consumer = root / "consumers" / "consumer"
        self.tools = self.producer / "tools"
        self.tools.mkdir(parents=True)
        for name in ("sync_consumers.py", "check_consumers.py"):
            shutil.copyfile(Path(__file__).parent / name, self.tools / name)
        # check_consumers.py compares the pin through the vendored tooling, as core itself does.
        tooling = self.producer / ".agents/skills/wow-forever-addon/tooling"
        shutil.copytree(
            Path(__file__).parent.parent / ".agents/skills/wow-forever-addon/tooling/forever_tools",
            tooling / "forever_tools",
        )
        (self.tools / "check_core_shared.py").write_text(
            'VENDORED = {"UI/Shared.lua": ("consumer",)}\n'
            "CONSUMER_ROOT = {}\n"
            'def source(path): return "UI/Canonical.lua"\n'
        )
        for directory in (self.producer, self.consumer):
            (directory / "UI").mkdir(parents=True)
        (self.producer / "UI/Canonical.lua").write_bytes(b"producer\n")
        (self.consumer / "UI/Canonical.lua").write_bytes(b"stale\n")
        self.target = self.consumer / "UI/Shared.lua"
        self.target.write_bytes(b"stale\n")

    def run_tool(self, name, *args):
        return subprocess.run(
            [sys.executable, str(self.tools / name), *map(str, args)],
            cwd=self.consumer,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_sync_from_consumer_cwd_copies_producer_and_dry_run_preserves_target(self):
        result = self.run_tool("sync_consumers.py", "..", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 file(s) would change", result.stdout)
        self.assertEqual(self.target.read_bytes(), b"stale\n")
        result = self.run_tool("sync_consumers.py", self.consumer.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), b"producer\n")

    def test_check_from_consumer_cwd_detects_drift_then_accepts_producer_copy(self):
        result = self.run_tool("check_consumers.py", "--local", "..")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("consumer: UI/Shared.lua", result.stdout)
        self.target.write_bytes(b"producer\n")
        result = self.run_tool("check_consumers.py", "--local", "..")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_prefixed_consumer_is_checked_below_its_addon_folder(self):
        self.prefixed_consumer()
        target = self.consumer / "addon/Consumer/UI/Shared.lua"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"stale\n")
        result = self.run_tool("check_consumers.py", "--local", "..")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("consumer: addon/Consumer/UI/Shared.lua", result.stdout)
        target.write_bytes(b"producer\n")
        result = self.run_tool("check_consumers.py", "--local", "..")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_missing_prefixed_consumer_file_is_reported_not_raised(self):
        self.prefixed_consumer()
        result = self.run_tool("check_consumers.py", "--local", "..")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("consumer: addon/Consumer/UI/Shared.lua: missing here", result.stdout)

    def prefixed_consumer(self):
        (self.tools / "check_core_shared.py").write_text(
            'VENDORED = {"UI/Shared.lua": ("consumer",)}\n'
            'CONSUMER_ROOT = {"consumer": "addon/Consumer"}\n'
            'def source(path): return "UI/Canonical.lua"\n'
        )


class MissingRemoteTest(unittest.TestCase):
    def test_a_private_or_unpublished_prefixed_consumer_reports_missing_paths(self):
        def missing(*args):
            error = urllib.error.HTTPError("https://example.test", 404, "Not Found", {}, None)
            error.close()
            raise error

        out = io.StringIO()
        with (
            mock.patch.object(check_consumers, "VENDORED", {"UI/TrackerHost.lua": ("kiln-forever",)}),
            mock.patch.object(check_consumers, "source", lambda path: path),
            mock.patch.object(check_consumers, "remote", side_effect=missing),
            contextlib.redirect_stdout(out),
        ):
            code = check_consumers.main([])

        self.assertEqual(code, 1)
        self.assertIn("kiln-forever: addon/KilnForever/UI/TrackerHost.lua: missing", out.getvalue())
        self.assertIn("private repo without a token", out.getvalue())


if __name__ == "__main__":
    unittest.main()
