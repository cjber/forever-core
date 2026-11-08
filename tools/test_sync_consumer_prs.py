"""Tests for tools/sync_consumer_prs.py: consumer derivation, PR text and summaries, no network."""

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import check_core_shared
import sync_consumer_prs as sync


def listed(*names, archived=()):
    return [{"name": name, "isArchived": name in archived} for name in names]


class ConsumerTest(unittest.TestCase):
    def test_vendored_repositories_are_the_base(self):
        expected = {repo for repos in check_core_shared.VENDORED.values() for repo in repos}
        self.assertEqual(set(sync.consumer_repos()), expected)

    def test_discovered_tooling_repos_join_and_core_is_never_a_consumer(self):
        repos = sync.consumer_repos({"new-addon", "forever-core"})
        self.assertIn("new-addon", repos)
        self.assertNotIn("forever-core", repos)
        self.assertEqual(repos, sorted(repos))


class DiscoveryTest(unittest.TestCase):
    def test_live_tooling_repos_are_found_and_archived_ones_are_skipped(self):
        repositories = listed(
            "adventure-guide-forever",
            "archived-addon",
            "forever-core",
            "new-addon",
            archived=("archived-addon",),
        )

        def fake_gh(*args, check=True):
            code = 0
            output = ""
            if args[:2] == ("repo", "list"):
                output = json.dumps(repositories)
            elif "new-addon" in " ".join(args) and "forever_sim" in " ".join(args):
                code = 0
            else:
                code = 1
            return subprocess.CompletedProcess(args, code, output, "")

        with mock.patch.object(sync, "gh", side_effect=fake_gh):
            with contextlib.redirect_stdout(io.StringIO()):
                found = sync.discover_tooling_repos()
        self.assertEqual(found, {"new-addon"})

    def test_a_failed_repo_listing_falls_back_to_the_vendoring_map(self):
        def fake_gh(*args, check=True):
            raise sync.SyncError("no token access")

        with mock.patch.object(sync, "gh", side_effect=fake_gh):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sync.discover_tooling_repos(), set())


class ToolingTest(unittest.TestCase):
    def test_only_packages_with_a_manifest_are_synced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / "tools" / "forever_tools"
            tools.mkdir(parents=True)
            (tools / "MANIFEST.json").write_text("{}", encoding="utf-8")
            self.assertEqual(sync.tooling_packages(root), ["forever_tools"])


class BodyTest(unittest.TestCase):
    def test_body_names_the_core_commit_and_every_file(self):
        files = ("UI/TrackerHost.lua", "tools/forever_tools/sync.py")
        body = sync.pr_body("abc123", files)
        self.assertIn("https://github.com/cjber/forever-core/commit/abc123", body)
        for path in files:
            self.assertIn(f"`{path}`", body)


class SummaryTest(unittest.TestCase):
    def test_summary_names_failures_and_open_prs(self):
        results = [
            sync.Result("legacy-forever", "updated", ("UI/TrackerHost.lua",), "https://example.test/pull/7"),
            sync.Result("tweaks-forever", "failed", detail="push rejected | protected"),
        ]
        summary = sync.summary_markdown("abc123", results)
        self.assertIn("Core commit: `abc123`", summary)
        self.assertIn("[PR](https://example.test/pull/7)", summary)
        self.assertIn("failed: push rejected \\| protected", summary)


class MainTest(unittest.TestCase):
    def test_a_missing_token_is_a_green_notice(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"GH_TOKEN": ""}):
            with contextlib.redirect_stdout(out):
                self.assertEqual(sync.main(), 0)
        self.assertIn("CONSUMER_SYNC_TOKEN is not set", out.getvalue())


if __name__ == "__main__":
    unittest.main()
