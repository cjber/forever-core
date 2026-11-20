import subprocess
import tempfile
import unittest
from pathlib import Path

from forever_tools import package, toc_version


def git(root, *args):
    identity = ["-c", "user.email=t@t", "-c", "user.name=t", "-c", "tag.gpgSign=false", "-c", "commit.gpgSign=false"]
    subprocess.run(["git", "-C", str(root), *identity, *args], check=True, capture_output=True)


class TocVersionTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        # A BOM and CRLF line endings, as some addon TOCs carry, must survive the stamp byte for byte.
        self.toc = self.root / "Addon.toc"
        self.toc.write_bytes(b"\xef\xbb\xbf## Interface: 16001\r\n## Version: @project-version@\r\nCore.lua\r\n")
        (self.root / "tools").mkdir()
        (self.root / "tools/Vendored.toc").write_bytes(b"## Version: @project-version@\n")
        git(self.root, "init", "-q")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "c")

    def test_bare_drops_only_a_version_v(self):
        self.assertEqual(toc_version.bare("v1.43.1\n"), "1.43.1")
        self.assertEqual(toc_version.bare("v1.2.3-4-gabc1234"), "1.2.3-4-gabc1234")
        self.assertEqual(toc_version.bare("1.2.3"), "1.2.3")
        self.assertEqual(toc_version.bare("abc1234"), "abc1234")
        self.assertEqual(toc_version.bare("vanilla"), "vanilla")

    def test_a_tagged_commit_is_stamped_with_the_bare_tag(self):
        git(self.root, "tag", "v2.5.0")
        self.assertEqual(toc_version.main([str(self.root)]), 0)
        self.assertEqual(self.toc.read_bytes(), b"\xef\xbb\xbf## Interface: 16001\r\n## Version: 2.5.0\r\nCore.lua\r\n")
        # Only addon TOCs are stamped: the dev folders the packager drops are left alone.
        self.assertEqual((self.root / "tools/Vendored.toc").read_bytes(), b"## Version: @project-version@\n")
        self.assertEqual(package.check_version(self.root, self.toc), [])

    def test_an_untagged_commit_is_stamped_with_its_short_sha(self):
        self.assertEqual(toc_version.main([str(self.root)]), 0)
        self.assertRegex(self.toc.read_bytes(), rb"## Version: [0-9a-f]{7}\r\n")

    def test_the_pushed_tag_wins_when_two_tags_name_the_commit(self):
        git(self.root, "tag", "-a", "-m", "old", "v1.16.0")
        git(self.root, "tag", "v1.16.1")
        self.assertEqual(toc_version.described(self.root, "refs/tags/v1.16.1"), "1.16.1")
        self.assertEqual(toc_version.described(self.root, "refs/tags/v1.16.0"), "1.16.0")

    def test_a_second_run_changes_nothing(self):
        git(self.root, "tag", "v2.5.0")
        toc_version.main([str(self.root)])
        self.assertEqual(toc_version.stamp(self.root, "9.9.9"), [])


class CheckVersionTest(unittest.TestCase):
    def check(self, line):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "Addon").mkdir()
        toc = root / "Addon/Addon.toc"
        toc.write_text(f"## Title: A\n{line}\nCore.lua\n", encoding="utf-8")
        return package.check_version(root, toc)

    def test_the_packaged_tag_form_fails(self):
        # The form the client returned for every published addon before the stamp step.
        problems = self.check("## Version: v1.43.1")
        self.assertEqual(len(problems), 1)
        self.assertIn("Addon/Addon.toc: ## Version is v1.43.1", problems[0])

    def test_an_unfilled_keyword_fails(self):
        self.assertIn("still holds @project-version@", self.check("## Version: @project-version@")[0])

    def test_a_bundled_folder_keeps_the_version_its_release_wrote(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for folder, version in (("Addon", "1.2.3"), ("ForeverCore", "v1.15.1")):
            (root / folder).mkdir()
            (root / folder / f"{folder}.toc").write_text(f"## Version: {version}\n", encoding="utf-8")
            (root / folder / "LICENSE").write_text("MIT", encoding="utf-8")
        problems = package.check(root, package.Policy(addons=("Addon", "ForeverCore")))
        self.assertFalse([problem for problem in problems if "Version" in problem], problems)
        (root / "Addon/Addon.toc").write_text("## Version: v1.2.3\n", encoding="utf-8")
        problems = package.check(root, package.Policy(addons=("Addon", "ForeverCore")))
        self.assertEqual(
            [problem for problem in problems if "Version" in problem],
            [
                "Addon/Addon.toc: ## Version is v1.2.3, the tag with its v; run python3 -m"
                " tools.forever_tools.toc_version before the packager"
            ],
        )

    def test_bare_and_dev_versions_pass(self):
        for line in (
            "## Version: 1.43.1",
            "## Version: 1.2.3-dev+abc1234",
            "## Version: abc1234",
            "## Title: no version",
        ):
            self.assertEqual(self.check(line), [], line)
