import contextlib
import importlib.util
import io
import re
import tempfile
import unittest
from pathlib import Path

from forever_tools import family

CHECK_COPY = Path(__file__).resolve().parents[2] / "check_copy.py"
URL = re.compile(r"^\| \[([^\]]+)\]\(https://www\.curseforge\.com/wow/addons/([a-z-]+)\) \| ([^|]+) \|$")


class FamilyTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "docs").mkdir()
        self.write("README.md", f"# Addon\n\n## Works alongside\n\nQuestie.\n\n{family.BLOCK}\n\n## Development\n")
        self.write("docs/curseforge.md", f"Pitch.\n\n{family.BLOCK}\n\nSource.\n")

    def write(self, name, text):
        (self.root / name).write_text(text, encoding="utf-8")

    def read(self, name):
        return (self.root / name).read_text(encoding="utf-8")

    def test_the_block_lists_the_five_addons_in_order(self):
        rows = [URL.match(line) for line in family.BLOCK.splitlines() if line.startswith("| [")]
        self.assertTrue(all(rows))
        self.assertEqual(
            [row[1] for row in rows],
            ["Shortest Path Forever", "Adventure Guide Forever", "SkillUp Forever", "Legacy Forever", "Tweaks Forever"],
        )
        for name, slug, line in ((row[1], row[2], row[3]) for row in rows):
            self.assertEqual(slug, name.lower().replace(" ", "-"))
            self.assertNotIn("!", line)
            self.assertNotIn("—", line)
        self.assertEqual(family.BLOCK.splitlines()[2], "## The Forever addons")
        self.assertTrue(family.BLOCK.startswith(family.START) and family.BLOCK.endswith(family.END))

    def test_an_exact_block_in_both_files_passes(self):
        self.assertEqual(family.check(self.root), [])

    def test_a_missing_block_or_file_fails(self):
        self.write("README.md", "# Addon\n")
        (self.root / "docs/curseforge.md").unlink()
        problems = family.check(self.root)
        self.assertEqual(len(problems), 2)
        self.assertTrue(problems[0].startswith("README.md: no <!-- forever-family:start -->"))
        self.assertEqual(problems[1], "docs/curseforge.md: missing")

    def test_an_edited_block_fails_with_its_line(self):
        self.write("docs/curseforge.md", "Pitch.\n\n" + family.BLOCK.replace("tracker.", "tracker!") + "\n")
        self.assertEqual(
            family.check(self.root),
            ["docs/curseforge.md:3: the family block differs from forever_tools.family; run --fix"],
        )

    def test_malformed_markers_fail(self):
        cases = {
            family.BLOCK + "\n" + family.BLOCK: "2 start and 2 end markers",
            family.END + "\n" + family.START: "comes before",
            family.START + "\n" + family.END: None,  # well formed, wrong text
            "Text " + family.BLOCK: "must be on a line of its own",
            family.BLOCK.replace(family.END, ""): "1 start and 0 end markers",
        }
        for text, expected in cases.items():
            with self.subTest(expected=expected):
                self.write("README.md", text + "\n")
                problem = family.check(self.root)[0]
                self.assertIn(expected or "differs", problem)

    def test_fix_rewrites_between_the_markers_and_keeps_the_rest(self):
        stale = f"{family.START}\n## Old\n\nOld list.\n{family.END}"
        readme = f"# Addon\n\nBefore.\n\n{stale}\n\nAfter.\n"
        self.write("README.md", readme)
        self.write("docs/curseforge.md", "No block here.\n")
        self.assertEqual(family.fix(self.root), ["README.md"])
        self.assertEqual(self.read("README.md"), readme.replace(stale, family.BLOCK))
        self.assertEqual(self.read("docs/curseforge.md"), "No block here.\n")
        self.assertEqual(family.fix(self.root), [])

    def test_fix_keeps_crlf_line_endings(self):
        stale = f"{family.START}\r\nOld.\r\n{family.END}"
        (self.root / "README.md").write_bytes(f"# Addon\r\n\r\n{stale}\r\n".encode())
        self.assertEqual(family.fix(self.root), ["README.md"])
        expected = f"# Addon\r\n\r\n{family.BLOCK}\r\n".replace("\n", "\r\n").replace("\r\r", "\r")
        self.assertEqual((self.root / "README.md").read_bytes().decode(), expected)
        self.assertEqual(family.check(self.root), [])
        self.assertEqual(family.fix(self.root), [])

    def test_main_reports_and_prints(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(family.main(self.root, []), 0)
            self.write("README.md", "# Addon\n")
            self.assertEqual(family.main(self.root, []), 1)
        self.assertIn("README.md: no", err.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(family.main(self.root, ["--print"]), 0)
        self.assertEqual(out.getvalue(), family.BLOCK + "\n")


class ProseWordsTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("check_copy", CHECK_COPY)
        assert spec and spec.loader
        self.copy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.copy)

    def test_the_family_block_and_markup_are_not_prose(self):
        page = "Plans a [route](https://example.com/a/b) `/x y`.\n\n![Alt words here](x.png)\n\n```sh\nluajit x\n```\n"
        self.assertEqual(self.copy.words(page), 3)
        badges = "[![CI][badge]][ci] See https://example.com/x.\n\n[ci]: https://example.com/ci.yml\n"
        self.assertEqual(self.copy.words(badges), 1)
        self.assertEqual(self.copy.words(page + "\n" + family.BLOCK + "\n"), 3)

    def test_the_block_passes_the_voice_check(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "README.md"
            path.write_text(family.BLOCK + "\n", encoding="utf-8")
            self.assertEqual(self.copy.hits(path) + self.copy.stacked(path), [])


if __name__ == "__main__":
    unittest.main()
