"""Tests for tools/suite_load.py: the addon list, and the released-build mode the core release gate runs."""

import contextlib
import io
import unittest
from pathlib import Path
from unittest import mock

import check_core_shared
import suite_load


class SuiteLoadTest(unittest.TestCase):
    def test_suite_covers_every_published_consumer(self):
        # Kiln Forever is private and has no store package, so the suite never clones it.
        expected = set(check_core_shared.SUITE_CONSUMERS) - {"kiln-forever"}
        listed = {repo for repo, _ in suite_load.ADDONS}
        self.assertEqual(set(), expected - listed, "the suite omits these consumers")
        self.assertIn("forever-core", listed, "ForeverCore itself loads first")

    def test_forever_core_is_first(self):
        self.assertEqual(("forever-core", "ForeverCore"), suite_load.ADDONS[0])

    def test_every_addon_names_a_folder(self):
        for repo, folder in suite_load.ADDONS:
            self.assertTrue(repo and folder, f"bad suite entry: {repo!r}={folder!r}")


class ReleasedSuiteTest(unittest.TestCase):
    """`--released` loads this checkout as ForeverCore with the consumers' store releases beside it."""

    def test_forever_core_comes_first_and_consumers_follow_the_suite_order(self):
        folders = [
            ("LegacyForever", Path("/cache/LegacyForever")),
            ("SkillUpForever", Path("/cache/SkillUpForever")),
        ]
        value = suite_load.released_value(folders)
        self.assertEqual(
            value,
            f"{suite_load.REPO}=ForeverCore;/cache/SkillUpForever=SkillUpForever;/cache/LegacyForever=LegacyForever",
        )

    def test_an_unknown_released_addon_follows_alphabetically(self):
        folders = [("ZebraForever", Path("/cache/ZebraForever")), ("LegacyForever", Path("/cache/LegacyForever"))]
        self.assertEqual(
            suite_load.released_value(folders).split(";")[1:],
            ["/cache/LegacyForever=LegacyForever", "/cache/ZebraForever=ZebraForever"],
        )

    def test_released_mode_runs_the_scenario_over_the_unpacked_folders(self):
        folders = [("LegacyForever", Path("/cache/LegacyForever"))]
        with (
            mock.patch.object(suite_load.released_consumers, "released_folders", return_value=folders) as unpacked,
            mock.patch.object(suite_load.subprocess, "run", return_value=mock.Mock(returncode=0)) as run,
            mock.patch.object(suite_load.sys, "argv", ["suite_load.py", "--released", "-v"]),
        ):
            self.assertEqual(suite_load.main(), 0)
        unpacked.assert_called_once_with()
        self.assertEqual(
            run.call_args.kwargs["env"]["FOREVER_SUITE"],
            f"{suite_load.REPO}=ForeverCore;/cache/LegacyForever=LegacyForever",
        )
        self.assertEqual(run.call_args.args[0][-1], "-v")

    def test_a_released_build_that_cannot_be_unpacked_fails_the_run(self):
        with (
            mock.patch.object(
                suite_load.released_consumers,
                "released_folders",
                side_effect=suite_load.released_consumers.ReleasedError("could not read legacy-forever"),
            ),
            mock.patch.object(suite_load.subprocess, "run") as run,
            mock.patch.object(suite_load.sys, "argv", ["suite_load.py", "--released"]),
        ):
            self.assertEqual(suite_load.main(), 2)
        run.assert_not_called()

    def test_released_takes_no_checkout_root(self):
        with (
            mock.patch.object(suite_load.sys, "argv", ["suite_load.py", "--released", "--root", ".."]),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            suite_load.main()


if __name__ == "__main__":
    unittest.main()
