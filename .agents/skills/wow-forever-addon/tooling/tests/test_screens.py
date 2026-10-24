import tempfile
import unittest
from pathlib import Path

from forever_tools import screens


class ScreensTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.folder = self.root / "docs/screenshots"
        self.folder.mkdir(parents=True)
        (self.folder / "a.png").write_bytes(b"A1")
        (self.folder / "b.png").write_bytes(b"B1")
        self.dumps = {"a.png": {"x": 1}, "b.png": {"y": 1}}

    def scenes(self):
        return {name: (lambda name=name: screens.dump_json(self.dumps[name])) for name in self.dumps}

    def test_a_fresh_record_passes(self):
        screens.record(self.folder, self.scenes())
        self.assertEqual(screens.check(self.folder, self.scenes()), [])

    def test_a_moved_dump_with_the_same_image_is_stale(self):
        screens.record(self.folder, self.scenes())
        self.dumps["a.png"] = {"x": 2}
        problems = screens.check(self.folder, self.scenes())
        self.assertEqual(len(problems), 1)
        self.assertIn("a.png: what it shows changed but the image did not", problems[0])
        with self.assertRaisesRegex(SystemExit, "a.png: what it shows changed"):
            screens.record(self.folder, self.scenes())
        screens.record(self.folder, self.scenes(), force=True)
        self.assertEqual(screens.check(self.folder, self.scenes()), [])

    def test_a_new_image_without_a_record_fails_until_recorded(self):
        screens.record(self.folder, self.scenes())
        self.dumps["a.png"] = {"x": 2}
        (self.folder / "a.png").write_bytes(b"A2")
        self.assertIn("run tools/check_screenshots.py --record", screens.check(self.folder, self.scenes())[0])
        screens.record(self.folder, self.scenes())
        self.assertEqual(screens.check(self.folder, self.scenes()), [])

    def test_unknown_unrecorded_and_missing_images_fail(self):
        (self.folder / "c.png").write_bytes(b"C")
        problems = screens.check(self.folder, self.scenes())
        self.assertEqual(len(problems), 3, problems)
        self.assertIn("c.png: no scene", problems[0])
        (self.folder / "c.png").unlink()
        screens.record(self.folder, self.scenes())
        (self.folder / "b.png").unlink()
        self.assertIn("b.png: missing", screens.check(self.folder, self.scenes())[0])

    def test_dumps_ignore_key_order_and_files_hash_their_sources(self):
        self.assertEqual(screens.dump_json({"a": 1, "b": 2}), screens.dump_json({"b": 2, "a": 1}))
        (self.root / "UI").mkdir()
        (self.root / "UI/a.lua").write_text("x")
        before = screens.files(self.root, ["UI/*.lua"])
        (self.root / "UI/a.lua").write_text("y")
        self.assertNotEqual(before, screens.files(self.root, ["UI/*.lua"]))
        with self.assertRaisesRegex(ValueError, "matches no file"):
            screens.files(self.root, ["Gone/*.lua"])


if __name__ == "__main__":
    unittest.main()
