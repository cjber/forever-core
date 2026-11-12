"""Tests for tools/sync_consumers.py, run against throwaway core and consumer trees."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sync_consumers as sync

DEADCODE = b"# deadcode\n"
ALLOW = b"# allow\n"
CLIENT_LOAD = b"# client load\n"
CHECKER = b"# checker\n"
TOC = "## Interface: 16001\nCore\\Own.lua\n"
LUACHECK = 'read_globals = { "CreateFrame" }\n'


class SyncConsumersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.core = base / "forever-core"
        self.write(self.core, "tools/deadcode.py", DEADCODE)
        self.write(self.core, "tools/deadcode-allow.txt", ALLOW)
        self.write(self.core, "tools/check_client_load.py", CLIENT_LOAD)
        self.write(self.core, "tools/check_core_shared.py", CHECKER)
        self.checkouts = base / "checkouts"

    def write(self, root, path, data):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def consumer(self, name="legacy-forever"):
        root = self.checkouts / name
        self.write(root, "LegacyForever.toc", TOC.encode())
        self.write(root, ".luacheckrc", LUACHECK.encode())
        return root

    def kiln_consumer(self):
        root = self.checkouts / "kiln-forever"
        self.write(root, "addon/KilnForever/KilnForever.toc", TOC.encode())
        self.write(root, ".luacheckrc", LUACHECK.encode())
        return root

    def run_sync(self, *argv, only=("tools/deadcode.py",)):
        out = io.StringIO()
        arguments = [str(self.checkouts)]
        for path in only:
            arguments += ["--only", path]
        with mock.patch.object(sync, "CORE_ROOT", self.core), contextlib.redirect_stdout(out):
            code = sync.main([*arguments, *argv])
        return code, out.getvalue()

    def test_tooling_is_copied_and_nothing_else_changes(self):
        root = self.consumer()
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertEqual((root / "tools/deadcode.py").read_bytes(), DEADCODE)
        self.assertEqual((root / "LegacyForever.toc").read_text(), TOC)
        self.assertEqual((root / ".luacheckrc").read_text(), LUACHECK)
        self.assertIn("legacy-forever: tools/deadcode.py", out)

    def test_second_run_changes_nothing(self):
        root = self.consumer()
        self.run_sync()
        before = (root / "tools/deadcode.py").read_bytes()
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertEqual((root / "tools/deadcode.py").read_bytes(), before)
        self.assertIn("0 file(s) changed", out)

    def test_warning_is_copied_and_loaded_before_the_guard(self):
        root = self.consumer()
        self.write(root, ".pkgmeta", b"package-as: LegacyForever\n")
        self.write(self.core, "tools/consumer/ForeverRequire.lua", b"-- shared warning\n")
        toc = root / "LegacyForever.toc"
        original = b"## Interface: 16001\r\nCore\\Require.lua\r\nCore/ForeverRequire.lua\r\n"
        toc.write_bytes(original)
        only = ("Core/ForeverRequire.lua",)

        code, out = self.run_sync("--dry-run", only=only)
        self.assertEqual(code, 0, out)
        self.assertIn("2 file(s) would change", out)
        self.assertEqual(toc.read_bytes(), original)
        self.assertFalse((root / only[0]).exists())

        code, out = self.run_sync(only=only)
        self.assertEqual(code, 0, out)
        self.assertEqual((root / only[0]).read_bytes(), b"-- shared warning\n")
        self.assertEqual(toc.read_bytes(), b"## Interface: 16001\r\nCore\\ForeverRequire.lua\r\nCore\\Require.lua\r\n")

        code, out = self.run_sync(only=only)
        self.assertEqual(code, 0, out)
        self.assertIn("0 file(s) changed", out)

    def test_dry_run_writes_nothing(self):
        root = self.consumer()
        code, out = self.run_sync("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertFalse((root / "tools/deadcode.py").exists())
        self.assertIn("would change", out)

    def test_a_consumer_that_is_not_checked_out_is_skipped(self):
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertIn("legacy-forever: not checked out", out)
        self.assertIn("0 file(s) changed", out)

    def test_a_consumer_with_an_addon_folder_syncs_below_it(self):
        root = self.kiln_consumer()
        code, out = self.run_sync(only=("tools/check_core_shared.py",))
        self.assertEqual(code, 0, out)
        self.assertEqual((root / "addon/KilnForever/tools/check_core_shared.py").read_bytes(), CHECKER)
        self.assertFalse((root / "tools/check_core_shared.py").exists())
        self.assertIn("kiln-forever: tools/check_core_shared.py", out)

    def test_the_drift_workflow_keeps_its_consumer_path(self):
        self.write(self.core, "tools/core-shared-drift.yml", b"# workflow\n")
        root = self.consumer()
        code, out = self.run_sync(only=(".github/workflows/core-shared-drift.yml",))
        self.assertEqual(code, 0, out)
        self.assertEqual((root / ".github/workflows/core-shared-drift.yml").read_bytes(), b"# workflow\n")

    def test_the_visual_proof_workflow_keeps_its_consumer_path(self):
        self.write(self.core, "tools/visual-proof.yml", b"# visual workflow\n")
        root = self.consumer()
        code, out = self.run_sync(only=(".github/workflows/visual-proof.yml",))
        self.assertEqual(code, 0, out)
        self.assertEqual((root / ".github/workflows/visual-proof.yml").read_bytes(), b"# visual workflow\n")
        self.assertIn("full forever_tools sync", out)

    def test_kiln_does_not_take_the_drift_workflow(self):
        self.write(self.core, "tools/core-shared-drift.yml", b"# workflow\n")
        root = self.kiln_consumer()
        code, out = self.run_sync(only=(".github/workflows/core-shared-drift.yml",))
        self.assertEqual(code, 0, out)
        self.assertFalse((root / "addon/KilnForever/.github/workflows/core-shared-drift.yml").exists())

    def test_kiln_does_not_take_the_visual_proof_workflow(self):
        self.write(self.core, "tools/visual-proof.yml", b"# visual workflow\n")
        root = self.kiln_consumer()
        code, out = self.run_sync(only=(".github/workflows/visual-proof.yml",))
        self.assertEqual(code, 0, out)
        self.assertFalse((root / "addon/KilnForever/.github/workflows/visual-proof.yml").exists())
        self.assertFalse((root / ".github/workflows/visual-proof.yml").exists())

    def test_a_module_the_consumer_already_has_is_overwritten(self):
        root = self.consumer()
        self.write(root, "tools/deadcode.py", b"old\n")
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertEqual((root / "tools/deadcode.py").read_bytes(), DEADCODE)


if __name__ == "__main__":
    unittest.main()
