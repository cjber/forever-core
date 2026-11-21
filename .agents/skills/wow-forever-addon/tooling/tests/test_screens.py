import shutil
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


class SceneRecordsTest(unittest.TestCase):
    def tmp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def test_independent_scene_edits_change_disjoint_records(self):
        tmp_path = self.tmp()
        base = tmp_path / "base"
        base.mkdir()
        scenes = {"map.png": lambda: b"map", "tracker.gif": lambda: b"tracker"}
        for name in scenes:
            (base / name).write_bytes(b"original pixels")
        screens.record(base, scenes)
        original = dict.fromkeys(scenes, screens.sha256(b"original pixels"))
        expected = {name: (image, screens.sha256(scenes[name]())) for name, image in original.items()}
        records = base / "scenes"
        assert {path.name for path in records.iterdir()} == {"map.png.sha256", "tracker.gif.sha256"}
        for name, (image, dump) in expected.items():
            assert (records / f"{name}.sha256").read_text() == f"{image} {dump}\n"
        assert screens.read(base) == expected

        for name in scenes:
            branch = tmp_path / name
            shutil.copytree(base, branch)
            (branch / name).write_bytes(b"new pixels")
            screens.record(branch, scenes)
            changed = {
                path.name
                for path in (branch / "scenes").iterdir()
                if path.read_bytes() != (records / path.name).read_bytes()
            }
            assert changed == {f"{name}.sha256"}

    def test_legacy_records_fill_gaps_and_migrate(self):
        tmp_path = self.tmp()
        legacy = tmp_path / "scenes.sha256"
        records = tmp_path / "scenes"
        records.mkdir()
        image, dump = screens.sha256(b"pixels"), screens.sha256(b"dump")
        legacy.write_text(f"# old records\nmap.png {image} {dump}\ntracker.png {image} {screens.sha256(b'old')}\n")
        (records / "tracker.png.sha256").write_text(f"{image} {dump}\n")
        (records / "retired.png.sha256").write_text(f"{image} {dump}\n")
        (records / "notes.txt").write_text("keep")
        scenes = {"map.png": lambda: b"dump", "tracker.png": lambda: b"dump"}
        for name in scenes:
            (tmp_path / name).write_bytes(b"pixels")

        assert screens.read(tmp_path) == dict.fromkeys([*scenes, "retired.png"], (image, dump))
        screens.record(tmp_path, scenes)

        assert not legacy.exists()
        assert {path.name for path in records.iterdir()} == {"map.png.sha256", "tracker.png.sha256", "notes.txt"}
        assert screens.read(tmp_path) == dict.fromkeys(scenes, (image, dump))
        assert screens.check(tmp_path, scenes) == []

    def test_check_names_per_scene_records(self):
        tmp_path = self.tmp()
        scenes = dict.fromkeys(["stale.png", "changed.png", "removed.png"], lambda: b"original dump")
        for name in scenes:
            (tmp_path / name).write_bytes(b"original pixels")
        screens.record(tmp_path, scenes)

        scenes["stale.png"] = lambda: b"new dump"
        (tmp_path / "changed.png").write_bytes(b"new pixels")
        del scenes["removed.png"]
        (tmp_path / "removed.png").unlink()
        scenes["unrecorded.png"] = lambda: b"new dump"
        (tmp_path / "unrecorded.png").write_bytes(b"new pixels")
        (tmp_path / "unnamed.gif").write_bytes(b"new pixels")

        assert screens.check(tmp_path, scenes) == [
            "unnamed.gif: no scene in tools/check_screenshots.py; name what it is drawn from",
            "changed.png: differs from scenes/changed.png.sha256; run tools/check_screenshots.py --record",
            "stale.png: what it shows changed but the image did not; run tools/screenshots.py",
            "unrecorded.png: not in scenes/unrecorded.png.sha256; run tools/check_screenshots.py --record",
            "removed.png: recorded in scenes/removed.png.sha256 but no longer a scene; "
            "run tools/check_screenshots.py --record",
        ]


if __name__ == "__main__":
    unittest.main()
