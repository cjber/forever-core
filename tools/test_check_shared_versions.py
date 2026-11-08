"""Tests for tools/check_shared_versions.py: a shared file's version and bytes stay pinned together."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import check_shared_versions as gate

SOURCES = {
    "Core/PeerStats.lua": "local MANAGER_VERSION = 6\nlocal PREFIX = 'WFAStats'\n",
    "UI/ForeverFamily.lua": "local VERSION = 6\nlocal LINK_NAME = 'ForeverFamilyLink'\n",
    "UI/Leaderboards.lua": "local LEADERBOARDS_VERSION = 2\nlocal OVERALL = 'overall'\n",
}


class SharedVersionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.record_path = self.root / gate.RECORD_FILE
        for path, text in SOURCES.items():
            self.write(path, text)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def recorded(self):
        return json.loads(self.record_path.read_text(encoding="utf-8"))

    def test_record_pins_every_file_and_the_check_passes(self):
        gate.record(self.root, self.record_path)
        recorded = self.recorded()
        self.assertEqual(set(recorded), set(gate.VERSION_LINES))
        self.assertEqual(recorded["UI/Leaderboards.lua"]["version"], 2)
        self.assertEqual(recorded["Core/PeerStats.lua"]["version"], 6)
        self.assertEqual(
            recorded["UI/ForeverFamily.lua"]["sha256"],
            hashlib.sha256(SOURCES["UI/ForeverFamily.lua"].encode("utf-8")).hexdigest(),
        )
        self.assertEqual(gate.check(self.root, self.record_path), [])

    def test_a_change_without_a_raised_version_fails(self):
        gate.record(self.root, self.record_path)
        self.write("UI/Leaderboards.lua", SOURCES["UI/Leaderboards.lua"] + "local EXTRA = true\n")
        findings = gate.check(self.root, self.record_path)
        self.assertEqual(len(findings), 1)
        self.assertIn("UI/Leaderboards.lua: shared-version: sha256 changed", findings[0])
        self.assertIn("LEADERBOARDS_VERSION stayed 2", findings[0])
        self.assertIn("raise it", findings[0])

    def test_a_raised_version_must_be_recorded(self):
        gate.record(self.root, self.record_path)
        self.write("UI/Leaderboards.lua", "local LEADERBOARDS_VERSION = 3\nlocal OVERALL = 'overall'\n")
        findings = gate.check(self.root, self.record_path)
        self.assertEqual(len(findings), 1)
        self.assertIn("LEADERBOARDS_VERSION is 3 but the record has 2", findings[0])
        self.assertIn("--record", findings[0])

    def test_a_raised_version_and_hash_pass_once_recorded(self):
        gate.record(self.root, self.record_path)
        source = "local LEADERBOARDS_VERSION = 3\nlocal OVERALL = 'overall'\n"
        self.write("UI/Leaderboards.lua", source)
        self.assertEqual(gate.check(self.root, self.record_path)[0].split(": ", 1)[0], "UI/Leaderboards.lua")
        gate.record(self.root, self.record_path)
        self.assertEqual(gate.check(self.root, self.record_path), [])
        recorded = self.recorded()
        self.assertEqual(recorded["UI/Leaderboards.lua"]["version"], 3)
        self.assertEqual(recorded["UI/Leaderboards.lua"]["sha256"], hashlib.sha256(source.encode("utf-8")).hexdigest())

    def test_a_version_that_goes_down_fails(self):
        gate.record(self.root, self.record_path)
        self.write("Core/PeerStats.lua", "local MANAGER_VERSION = 5\nlocal PREFIX = 'WFAStats'\n")
        findings = gate.check(self.root, self.record_path)
        self.assertEqual(len(findings), 1)
        self.assertIn("Core/PeerStats.lua: shared-version: MANAGER_VERSION went down from 6 to 5", findings[0])

    def test_a_missing_record_entry_fails(self):
        gate.record(self.root, self.record_path)
        recorded = self.recorded()
        del recorded["UI/ForeverFamily.lua"]
        self.record_path.write_text(json.dumps(recorded), encoding="utf-8")
        findings = gate.check(self.root, self.record_path)
        self.assertEqual(len(findings), 1)
        self.assertIn("UI/ForeverFamily.lua: shared-version: not recorded", findings[0])

    def test_an_unknown_record_entry_fails(self):
        gate.record(self.root, self.record_path)
        recorded = self.recorded()
        recorded["UI/Other.lua"] = {"version": 1, "sha256": "0" * 64}
        self.record_path.write_text(json.dumps(recorded), encoding="utf-8")
        findings = gate.check(self.root, self.record_path)
        self.assertEqual(len(findings), 1)
        self.assertIn("UI/Other.lua: shared-version: recorded but no exact version line", findings[0])

    def test_a_missing_record_file_fails(self):
        findings = gate.check(self.root, self.record_path)
        self.assertEqual(len(findings), 1)
        self.assertIn("cannot read the record", findings[0])
        self.assertIn("--record", findings[0])

    def test_the_version_line_must_match_exactly(self):
        self.write("UI/Leaderboards.lua", "local LEADERBOARDS_VERSION=2\n")
        with self.assertRaises(ValueError) as caught:
            gate.measure(self.root, "UI/Leaderboards.lua")
        self.assertIn("expected exactly one `local LEADERBOARDS_VERSION = N` line", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
