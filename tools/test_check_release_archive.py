"""The release archive gate checks the zip runtime, including its own TOC."""

import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import check_release_archive as gate


class ReleaseArchiveTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.folder = self.root / "ForeverCore"
        self.folder.mkdir()
        self.files = {
            "ForeverCore.toc": "## Interface: 16001\nCore.lua\n",
            "Core.lua": "local loaded = true\n",
            "LICENSE": "GPL-3.0-or-later\n",
            "README.md": "## Credits\nContributors.\n",
            "THIRD_PARTY.md": "## Players\nContributors.\n",
        }
        for name, text in self.files.items():
            (self.folder / name).write_text(text)
        self.archive = self.root / "ForeverCore-v1-forever.zip"
        self.cache = self.root / "cache"
        self.build()

    def build(self):
        with zipfile.ZipFile(self.archive, "w") as archive:
            for path in self.folder.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(self.root))

    def check(self):
        return gate.check_archive(self.archive, self.root, self.cache)

    def test_missing_loaded_file_in_zip_fails_without_running_exercise(self):
        (self.folder / "Core.lua").unlink()
        self.build()
        with patch.object(gate.subprocess, "run") as run:
            problems = self.check()
        self.assertTrue(any("Core.lua: missing" in problem for problem in problems), problems)
        run.assert_not_called()

    def test_upload_folder_must_match_the_tested_zip(self):
        (self.folder / "Core.lua").write_text("error('not the tested runtime')")
        problems = self.check()
        self.assertIn("package folder differs from the built zip", problems[0])

    def test_runtime_failure_from_extracted_package_blocks_release(self):
        def exercise(command, *, cwd, env, **kwargs):
            self.assertNotEqual(cwd, self.folder)
            self.assertEqual((cwd / "Core.lua").read_text(), self.files["Core.lua"])
            self.assertFalse((cwd / "tests").exists())
            self.assertEqual(env["FOREVER_SIM_CACHE"], str(self.cache.resolve()))
            self.assertEqual(command, ["luajit", str(gate.TOOLING / "forever_sim/run.lua")])
            return subprocess.CompletedProcess(command, 1, "FAIL packaged login", "bad global")

        with (
            patch.object(gate.lua51, "check", return_value=[]),
            patch.object(gate.subprocess, "run", side_effect=exercise),
        ):
            problems = self.check()
        self.assertIn("packaged exercise failed", problems[0])
        self.assertIn("bad global", problems[0])

    def test_archive_cannot_escape_its_scratch_directory(self):
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr("../escaped.lua", "error('escaped')")
        self.assertIn("unsafe archive member", self.check()[0])
        self.assertFalse((self.root / "escaped.lua").exists())


if __name__ == "__main__":
    unittest.main()
