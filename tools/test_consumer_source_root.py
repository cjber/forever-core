"""Consumer sync and drift checks use the producer even when launched elsewhere."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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
        (self.tools / "check_core_shared.py").write_text(
            'VENDORED = {"UI/Shared.lua": ("consumer",)}\ndef source(path): return "UI/Canonical.lua"\n'
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


if __name__ == "__main__":
    unittest.main()
