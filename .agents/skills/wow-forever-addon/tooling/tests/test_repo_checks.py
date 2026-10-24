import json
import tempfile
import unittest
from pathlib import Path

from forever_tools import changelog, release_check, toc

LOG = """# Changelog

## [Unreleased]

## [1.0.0] - 2026-01-01
- first
"""


class ChangelogTest(unittest.TestCase):
    def test_section_and_check(self):
        self.assertEqual(changelog.section(LOG, "1.0.0"), "- first")
        with self.assertRaises(SystemExit):
            changelog.section(LOG, "2.0.0")
        with self.assertRaises(SystemExit):
            changelog.check("## [1.0.0] - 2026-01-01\n- x\n", ["1.0.0"])
        changelog.check(LOG, ["1.0.0"])

    def test_subsections_pass_through_to_the_release_notes(self):
        log = (
            "## [Unreleased]\n\n## [1.1.0] - 2026-02-01\n- **A fix.** Players see it.\n\n"
            "### For addon authors\n\n- **`API.Thing` takes a map.** Callers pass one.\n\n"
            "## [1.0.0] - 2026-01-01\n- first\n"
        )
        notes = changelog.section(log, "1.1.0")
        self.assertTrue(notes.startswith("- **A fix.**"))
        self.assertIn("### For addon authors\n\n- **`API.Thing` takes a map.**", notes)
        self.assertNotIn("first", notes)

    def test_empty_section_fails(self):
        with self.assertRaisesRegex(SystemExit, "empty"):
            changelog.section("## [1.0.0] - 2026-01-01\n\n## [0.9.0] - 2025-01-01\n- y\n", "1.0.0")


class ReleaseCheckTest(unittest.TestCase):
    RUN = {
        "head_sha": "abc",
        "head_branch": "main",
        "path": ".github/workflows/ci.yml",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
    }

    def test_only_a_complete_green_main_push_for_the_commit_counts(self):
        self.assertTrue(release_check.verified([self.RUN], "abc"))
        self.assertFalse(release_check.verified([self.RUN], "other"))
        for key, value in (("conclusion", "failure"), ("head_branch", "dev"), ("event", "pull_request")):
            self.assertFalse(release_check.verified([{**self.RUN, key: value}], "abc"), key)


class TocTest(unittest.TestCase):
    def make(self, files):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text)
        return root

    def test_toc_and_nested_xml_are_followed(self):
        root = self.make(
            {
                "A.toc": "## Title: A\nCore\\a.lua\nUI\\load.xml\n",
                "Core/a.lua": "",
                "UI/load.xml": '<Ui><Script file="b.lua"/><Include file="more.xml"/></Ui>',
                "UI/b.lua": "",
                "UI/more.xml": '<Ui><Script file="c.lua"/></Ui>',
                "UI/c.lua": "",
            }
        )
        names = [p.relative_to(root.resolve()).as_posix() for p in toc.runtime_files(root, ("Core", "UI"))]
        self.assertEqual(names, ["Core/a.lua", "UI/b.lua", "UI/c.lua"])

    def test_orphan_lua_is_an_error_only_in_that_addons_runtime_dirs(self):
        root = self.make({"A.toc": "a.lua\n", "a.lua": "", "Map/orphan.lua": "", "Core/x.lua": ""})
        with self.assertRaisesRegex(ValueError, "not loaded"):
            toc.runtime_files(root, ("Map",))
        with self.assertRaisesRegex(ValueError, "not loaded"):
            toc.runtime_files(root, ("Core",))
        root = self.make({"A.toc": "a.lua\n", "a.lua": "", "tests/fixture.lua": ""})
        self.assertEqual(len(toc.runtime_files(root, ("Core",))), 1)

    def test_coverage_requires_git_ignore_off(self):
        root = self.make({"A.toc": "a.lua\n", "a.lua": "", ".luarc.json": json.dumps({})})
        with self.assertRaisesRegex(ValueError, "useGitIgnore"):
            toc.check_coverage(root)


if __name__ == "__main__":
    unittest.main()
