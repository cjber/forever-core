"""Pure evidence checks, without opening a manager or contacting a provider."""

import tempfile
import unittest
from pathlib import Path

from .run import core_check, disk, markdown, tree_hash


class EvidenceTests(unittest.TestCase):
    def test_snapshot_tracks_contents_names_and_toc(self):
        with tempfile.TemporaryDirectory() as tmp:
            addons = Path(tmp)
            core = addons / "ForeverCore"
            core.mkdir()
            toc = core / "ForeverCore.toc"
            toc.write_text("## Interface: 16001\n## Version: 1.12.1\n## X-Curse-Project-ID: 1796337\nCore.lua\n")
            lua = core / "Core.lua"
            lua.write_text("return {}\n")
            snapshot = disk(addons)
            self.assertEqual(snapshot["ForeverCore"]["files"], 2)
            self.assertEqual(snapshot["ForeverCore"]["tocs"][toc.name]["Version"], "1.12.1")
            original = tree_hash(core)
            self.assertEqual(tree_hash(core), original)
            lua.write_text("return true\n")
            self.assertNotEqual(tree_hash(core), original)
            changed = tree_hash(core)
            lua.rename(core / "Other.lua")
            self.assertNotEqual(tree_hash(core), changed)
            self.assertTrue(core_check(snapshot, None)["core_toc_valid"])

    def test_report_names_missing_dependency_and_failed_action(self):
        snapshot = {"Consumer": {"tocs": {"Consumer.toc": {"Dependencies": "ForeverCore"}}}}
        check = core_check(snapshot, "Consumer")
        self.assertFalse(check["b_dependency_resolves"])
        self.assertEqual(check["unmet_dependents"], ["Consumer"])
        report = {
            "app": "wowup",
            "app_version": "2.25.5",
            "started": "test",
            "params": {"scenario": "U2"},
            "consumer_a": {"name": "A", "id": 1},
            "consumer_b": {"name": "B", "id": 2},
            "steps": [
                {
                    "step": "update-A",
                    "title": "update A",
                    "addons_folders": ["Consumer"],
                    "records": [],
                    "core_check": check,
                    "error": "update failed",
                    "app_view": "Ready",
                }
            ],
            "archives": {
                "zip": {
                    "url": "https://example.invalid/a.zip",
                    "sha256": "abc",
                    "top_level_folders": ["Consumer"],
                    "bundled_core_version": None,
                }
            },
            "processes_left": [],
        }
        rendered = markdown(report)
        self.assertIn("**no**", rendered)
        self.assertIn("**Consumer**", rendered)
        self.assertIn("update failed", rendered)
        self.assertIn("a.zip | `abc`", rendered)
        self.assertIn("Processes left after stop: []", rendered)


if __name__ == "__main__":
    unittest.main()
