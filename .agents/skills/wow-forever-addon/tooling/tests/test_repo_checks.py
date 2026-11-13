import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_a_released_section_must_match_its_tag(self):
        shipped = LOG.replace("[Unreleased]\n", "[Unreleased]\n- later\n")
        moved = LOG.replace("- first\n", "- first\n- later\n")
        changelog.check(LOG, ["1.0.0"], {"1.0.0": shipped}.get)
        changelog.check(LOG, ["1.0.0"], {}.get)
        changelog.check(LOG, ["1.0.0"], {"1.0.0": "## [Unreleased]\n"}.get)
        with self.assertRaisesRegex(SystemExit, r"1\.0\.0.*differs from its v1\.0\.0 tag"):
            changelog.check(moved, ["1.0.0"], {"1.0.0": LOG}.get)
        reworded = moved.replace("## [Unreleased]\n", "## [Unreleased]\n\n## [1.1.0] - 2026-02-01\n- next\n")
        changelog.check(reworded, ["1.0.0", "1.1.0"], {"1.0.0": LOG, "1.1.0": reworded}.get)

    def test_released_sections_are_read_at_their_tags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git = ["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", "-c", "user.email=t@example.com"]
            run = lambda *args: subprocess.run([*git, *args], cwd=root, check=True, capture_output=True)  # noqa: E731
            run("init", "-q")
            (root / "CHANGELOG.md").write_text(LOG)
            run("add", "CHANGELOG.md")
            run("-c", "user.name=t", "commit", "-q", "-m", "x")
            run("tag", "v1.0.0")
            self.assertEqual(changelog.at_tag(root, "1.0.0"), LOG)
            self.assertIsNone(changelog.at_tag(root, "9.9.9"))

    def test_empty_section_fails(self):
        with self.assertRaisesRegex(SystemExit, "empty"):
            changelog.section("## [1.0.0] - 2026-01-01\n\n## [0.9.0] - 2025-01-01\n- y\n", "1.0.0")

    def feature_repo(self, body, tags=("1.0.0",), files=()):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "CHANGELOG.md").write_text(f"# Changelog\n\n## [Unreleased]\n\n{body}")
        for name in files:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_bytes(b"\x89PNG\r\n\x1a\n")
        git = ["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", "-c", "user.email=t@example.com"]
        run = lambda *args: subprocess.run([*git, *args], cwd=root, check=True, capture_output=True)  # noqa: E731
        run("init", "-q")
        run("add", "CHANGELOG.md")
        run("-c", "user.name=t", "commit", "-q", "-m", "x")
        for tag in tags:
            run("tag", f"v{tag}")
        return root

    def test_feature_release_without_a_hero_image_fails(self):
        root = self.feature_repo("## [1.1.0] - 2026-02-01\n- **A feature.** It matters.\n")
        with (
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(SystemExit, "feature release with no hero image"),
        ):
            changelog.main(root, ["--check", "1.1.0"])

    def test_feature_release_with_a_missing_hero_image_fails(self):
        root = self.feature_repo(
            "## [1.1.0] - 2026-02-01\n\n<!-- discord-image: docs/screenshots/new.png -->\n\n"
            "- **A feature.** It matters.\n"
        )
        with (
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(SystemExit, "not a PNG in this repository"),
        ):
            changelog.main(root, ["--check", "1.1.0"])

    def test_feature_release_with_an_existing_png_passes(self):
        root = self.feature_repo(
            "## [1.1.0] - 2026-02-01\n\n<!-- discord-image: docs/screenshots/new.png -->\n\n"
            "- **A feature.** It matters.\n",
            files=("docs/screenshots/new.png",),
        )
        with contextlib.redirect_stdout(io.StringIO()):
            changelog.main(root, ["--check", "1.1.0"])

    def test_patch_release_needs_no_hero_image(self):
        root = self.feature_repo("## [1.0.1] - 2026-02-01\n- **A fix.** It matters.\n")
        with contextlib.redirect_stdout(io.StringIO()):
            changelog.main(root, ["--check", "1.0.1"])

    def test_first_release_is_a_feature_only_on_patch_zero(self):
        feature = self.feature_repo("## [0.1.0] - 2026-02-01\n- **A feature.** It matters.\n", tags=())
        with (
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(SystemExit, "feature release with no hero image"),
        ):
            changelog.main(feature, ["--check", "0.1.0"])
        patch = self.feature_repo("## [0.1.1] - 2026-02-01\n- **A fix.** It matters.\n", tags=())
        with contextlib.redirect_stdout(io.StringIO()):
            changelog.main(patch, ["--check", "0.1.1"])

    def test_plain_check_over_released_history_needs_no_hero_image(self):
        root = self.feature_repo(
            "## [1.1.0] - 2026-02-01\n- **A feature.** It matters.\n\n"
            "## [1.0.0] - 2026-01-01\n- **The first release.** It matters.\n",
            tags=("1.0.0", "1.1.0"),
        )
        with contextlib.redirect_stdout(io.StringIO()):
            changelog.main(root, ["--check"])


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


class HeadlessSmokeTest(unittest.TestCase):
    """The commit status the smoke posts: the newest one decides, and only success releases."""

    RUN = ReleaseCheckTest.RUN

    def status(self, state, description="clean", context=release_check.SMOKE_CONTEXT):
        return {"context": context, "state": state, "description": description}

    def refuse(self, status):
        return release_check.smoke_refusal(status, "cjber/forever-core", "abc")

    def test_the_newest_smoke_status_is_the_one_read(self):
        statuses = [
            self.status("failure", "2 Lua errors"),
            self.status("success"),
            self.status("failure", context="ci"),
        ]
        self.assertEqual(release_check.headless_smoke(statuses)["state"], "failure")

    def test_a_commit_with_no_smoke_status_has_none(self):
        self.assertIsNone(release_check.headless_smoke([self.status("success", context="visual-proof")]))

    def test_a_passed_smoke_releases(self):
        self.assertIsNone(self.refuse(self.status("success")))

    def test_a_missing_or_pending_smoke_waits_with_the_command_to_run(self):
        for status in (None, self.status("pending")):
            with self.subTest(status=status):
                refused = self.refuse(status)
                self.assertEqual(
                    refused,
                    "waiting for headless-smoke on abc: run forever_client.py smoke --repo forever-core --ref abc",
                )

    def test_a_failed_smoke_prints_what_it_found(self):
        self.assertEqual(
            self.refuse(self.status("failure", "3 Lua errors: 3 LegacyForever")),
            "headless-smoke on abc is failure: 3 Lua errors: 3 LegacyForever",
        )
        self.assertIn("no description", self.refuse(self.status("error", description=None)))

    def test_main_needs_the_ci_run_and_then_the_smoke_status(self):
        ci = json.dumps([{"workflow_runs": [self.RUN]}])
        passing = json.dumps([[{"context": "headless-smoke", "state": "success"}]])
        failing = json.dumps([[{"context": "headless-smoke", "state": "failure", "description": "2 Lua errors"}]])
        with patch.dict("os.environ", {"GITHUB_REPOSITORY": "cjber/forever-core", "GITHUB_SHA": "abc"}):
            with (
                patch.object(release_check.subprocess, "check_output", side_effect=[ci, passing]),
                contextlib.redirect_stdout(io.StringIO()) as out,
            ):
                release_check.main([])
            self.assertIn("headless-smoke passed at abc", out.getvalue())
            with (
                patch.object(release_check.subprocess, "check_output", side_effect=[ci, failing]),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as result,
            ):
                release_check.main([])
            self.assertEqual(result.exception.code, "Release blocked: headless-smoke on abc is failure: 2 Lua errors")
            with (
                patch.object(release_check.subprocess, "check_output", side_effect=[ci, json.dumps([[]])]),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as missing,
            ):
                release_check.main([])
            self.assertIn("waiting for headless-smoke on abc", missing.exception.code)

    def test_main_refuses_before_reading_the_smoke_when_ci_did_not_pass(self):
        ci = json.dumps([{"workflow_runs": []}])
        with (
            patch.dict("os.environ", {"GITHUB_REPOSITORY": "cjber/forever-core", "GITHUB_SHA": "abc"}),
            patch.object(release_check.subprocess, "check_output", side_effect=[ci]) as request,
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as result,
        ):
            release_check.main([])
        self.assertIn("successful full CI run", result.exception.code)
        request.assert_called_once()

    def test_the_status_request_names_the_commit(self):
        requests = []

        def fake(path, text=True):
            requests.append(path)
            return json.dumps([[{"context": "headless-smoke", "state": "success"}]])

        with patch.object(release_check.subprocess, "check_output", side_effect=fake):
            self.assertEqual(len(release_check.statuses("cjber/forever-core", "abc")), 1)
        self.assertEqual(requests[0][-1], "repos/cjber/forever-core/commits/abc/statuses")


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

    def test_tooling_tocs_are_ignored_but_nested_child_addons_are_kept(self):
        root = self.make(
            {
                "A.toc": "a.lua\n",
                "a.lua": "",
                "Child/Child.toc": "child.lua\n",
                "Child/child.lua": "",
                "tools/forever_sim/stubs/Auctionator/Auctionator.toc": "Auctionator.lua\n",
                "tools/forever_sim/stubs/Auctionator/Auctionator.lua": "",
                "forever-core/ForeverCore.toc": "Core.lua\n",
                "forever-core/Core.lua": "",
            }
        )
        names = [p.relative_to(root.resolve()).as_posix() for p in toc.runtime_files(root)]
        self.assertEqual(names, ["Child/child.lua", "a.lua"])


if __name__ == "__main__":
    unittest.main()
