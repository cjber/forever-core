"""Tests for tools/suite_load.py's addon list, read against tools/check_core_shared.py's consumer sets."""

import unittest

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


if __name__ == "__main__":
    unittest.main()
