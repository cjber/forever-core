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
TOC_WITH_LOG = TOC.replace("Core\\Own.lua", "Core\\Log.lua\nCore\\Own.lua")
LUACHECK = 'read_globals = { "CreateFrame" }\n'
QUEST_TABS = b"-- shared quest log tabs\n"
QUEST_SPEC = b'-- UI/QuestLogTabs.lua\nassert(loadfile("UI/QuestLogTabs.lua"))\n'


class SyncConsumersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.core = base / "forever-core"
        self.write(self.core, "Core/Log.lua", LOG)
        self.write(self.core, "UI/QuestLogTabs.lua", QUEST_TABS)
        self.write(self.core, "tests/quest_log_tabs_spec.lua", QUEST_SPEC)
        self.write(self.core, "tools/deadcode.py", b"# deadcode\n")
        self.checkouts = base / "checkouts"

    def write(self, root, path, data):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def consumer(self, name="legacy-forever", toc=TOC, luacheck=LUACHECK, log=LOG):
        """A consumer that already carries Core/Log.lua, so its wiring can be tested."""
        root = self.checkouts / name
        self.write(root, "LegacyForever.toc", toc.encode())
        self.write(root, ".luacheckrc", luacheck.encode())
        if log is not None:
            self.write(root, "Core/Log.lua", log)
        return root

    def quest_consumer(self, toc=TOC):
        root = self.checkouts / "adventure-guide-forever"
        self.write(root, "AdventureGuideForever.toc", toc.encode())
        self.write(root, ".luacheckrc", LUACHECK.encode())
        return root

    def run_sync(self, *argv, only=("Core/Log.lua",)):
        out = io.StringIO()
        arguments = [str(self.checkouts)]
        for path in only:
            arguments += ["--only", path]
        with mock.patch.object(sync, "CORE_ROOT", self.core), contextlib.redirect_stdout(out):
            code = sync.main([*arguments, *argv])
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
        root = self.consumer(toc=TOC_WITH_LOG, log=None)
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

    def test_a_new_module_this_tool_wires_is_copied_and_wired(self):
        root = self.consumer(log=None)
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertEqual((root / "Core/Log.lua").read_bytes(), LOG)
        self.assertIn("Core\\Log.lua", (root / "LegacyForever.toc").read_text())
        self.assertNotIn("Core/Log.lua: skipped", out)

    def test_a_new_module_and_its_test_wait_until_the_consumer_toc_loads_it(self):
        root = self.quest_consumer()
        code, out = self.run_sync(only=("UI/QuestLogTabs.lua", "tests/quest_log_tabs_spec.lua"))
        self.assertEqual(code, 0, out)
        self.assertFalse((root / "UI/QuestLogTabs.lua").exists())
        self.assertFalse((root / "tests/quest_log_tabs_spec.lua").exists())
        self.assertIn("adventure-guide-forever: UI/QuestLogTabs.lua: skipped", out)
        self.assertIn("AdventureGuideForever.toc does not load it yet", out)
        self.assertIn("AdventureGuideForever.toc does not load UI/QuestLogTabs.lua yet", out)
        self.assertIn("0 file(s) changed", out)

    def test_a_new_module_and_its_test_are_copied_once_the_toc_loads_it(self):
        root = self.quest_consumer(toc=TOC.replace("Core\\Own.lua", "UI\\QuestLogTabs.lua\nCore\\Own.lua"))
        code, out = self.run_sync(only=("UI/QuestLogTabs.lua", "tests/quest_log_tabs_spec.lua"))
        self.assertEqual(code, 0, out)
        self.assertEqual((root / "UI/QuestLogTabs.lua").read_bytes(), QUEST_TABS)
        self.assertEqual((root / "tests/quest_log_tabs_spec.lua").read_bytes(), QUEST_SPEC)
        self.assertIn("2 file(s) changed", out)

    def test_a_module_the_consumer_already_has_keeps_syncing_without_a_toc_line(self):
        root = self.quest_consumer()
        self.write(root, "UI/QuestLogTabs.lua", b"old\n")
        code, out = self.run_sync(only=("UI/QuestLogTabs.lua",))
        self.assertEqual(code, 0, out)
        self.assertEqual((root / "UI/QuestLogTabs.lua").read_bytes(), QUEST_TABS)
        self.assertNotIn("UI/QuestLogTabs.lua: skipped", out)

    def test_a_new_tool_does_not_wait_for_a_toc(self):
        root = self.consumer()
        code, out = self.run_sync(only=("tools/deadcode.py",))
        self.assertEqual(code, 0, out)
        self.assertTrue((root / "tools/deadcode.py").is_file())


if __name__ == "__main__":
    unittest.main()
