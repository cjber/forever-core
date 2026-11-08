"""Tests for tools/sync_consumers.py, run against throwaway core and consumer trees."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sync_consumers as sync

LOG = b"-- shared log\n"
TOC = "## Interface: 16001\nCore\\SafeCall.lua\nCore\\Own.lua\n"
LUACHECK = 'read_globals = { "CreateFrame" }\n'


class SyncConsumersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.core = base / "forever-core"
        self.write(self.core, "Core/Log.lua", LOG)
        self.checkouts = base / "checkouts"

    def write(self, root, path, data):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def consumer(self, name="legacy-forever", toc=TOC, luacheck=LUACHECK):
        root = self.checkouts / name
        self.write(root, "LegacyForever.toc", toc.encode())
        self.write(root, ".luacheckrc", luacheck.encode())
        return root

    def run_sync(self, *argv):
        out = io.StringIO()
        with mock.patch.object(sync, "CORE_ROOT", self.core), contextlib.redirect_stdout(out):
            code = sync.main([str(self.checkouts), "--only", "Core/Log.lua", *argv])
        return code, out.getvalue()

    def test_toc_line_is_inserted_after_the_anchor(self):
        root = self.consumer()
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        lines = (root / "LegacyForever.toc").read_text().splitlines()
        self.assertEqual(lines[lines.index("Core\\SafeCall.lua") + 1], "Core\\Log.lua")
        self.assertIn("legacy-forever: LegacyForever.toc: Core\\Log.lua", out)

    def test_second_run_leaves_the_toc_unchanged(self):
        root = self.consumer()
        self.run_sync()
        before = (root / "LegacyForever.toc").read_bytes()
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertEqual((root / "LegacyForever.toc").read_bytes(), before)
        self.assertIn("0 file(s) changed", out)

    def test_read_global_is_appended_to_luacheckrc(self):
        root = self.consumer()
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        text = (root / ".luacheckrc").read_text()
        self.assertIn("-- Core/Log.lua: the client's date, this session's seconds.", text)
        self.assertIn('read_globals[#read_globals + 1] = "date"', text)
        self.assertIn("legacy-forever: .luacheckrc: date", out)

    def test_second_run_leaves_luacheckrc_unchanged(self):
        root = self.consumer()
        self.run_sync()
        before = (root / ".luacheckrc").read_bytes()
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertEqual((root / ".luacheckrc").read_bytes(), before)
        self.assertIn("0 file(s) changed", out)

    def test_dry_run_writes_nothing(self):
        root = self.consumer()
        toc = (root / "LegacyForever.toc").read_bytes()
        luacheck = (root / ".luacheckrc").read_bytes()
        code, out = self.run_sync("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertEqual((root / "LegacyForever.toc").read_bytes(), toc)
        self.assertEqual((root / ".luacheckrc").read_bytes(), luacheck)
        self.assertFalse((root / "Core/Log.lua").exists())
        self.assertIn("would change", out)

    def test_missing_toc_anchor_warns_and_does_not_raise(self):
        root = self.consumer(toc="## Interface: 16001\nCore\\Own.lua\n")
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertIn("legacy-forever: warning:", out)
        self.assertIn("Core\\SafeCall.lua", out)
        self.assertEqual((root / "LegacyForever.toc").read_text(), "## Interface: 16001\nCore\\Own.lua\n")

    def test_wiring_applies_when_the_copy_is_already_current(self):
        root = self.consumer()
        self.write(root, "Core/Log.lua", LOG)
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertNotIn("legacy-forever: Core/Log.lua\n", out)
        self.assertIn("Core\\Log.lua", (root / "LegacyForever.toc").read_text())
        self.assertIn('read_globals[#read_globals + 1] = "date"', (root / ".luacheckrc").read_text())


if __name__ == "__main__":
    unittest.main()
