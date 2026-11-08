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
    return [{"name": name, "archived": name in archived} for name in names]


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
            path = args[1] if len(args) > 1 else ""
            if path.startswith("users/cjber/repos"):
                output = json.dumps(repositories)
            elif "new-addon" in path and "forever_sim" in path:
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


class RestPrTest(unittest.TestCase):
    def test_an_open_pr_is_found_and_updated_with_a_patch(self):
        calls = []

        def fake_gh(*args, check=True):
            calls.append(args)
            path = args[1]
            if path == "repos/cjber/legacy-forever/pulls?head=cjber:forever-core-sync&state=open":
                output = json.dumps([{"number": 7, "html_url": "https://example.test/pull/7", "node_id": "PR_7"}])
                return subprocess.CompletedProcess(args, 0, output, "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with mock.patch.object(sync, "gh", side_effect=fake_gh):
            number, url, status, node_id = sync.open_or_update_pr("legacy-forever", "body")

        self.assertEqual((number, url, status, node_id), (7, "https://example.test/pull/7", "updated", "PR_7"))
        patches = [call for call in calls if "--method" in call and "PATCH" in call]
        self.assertEqual(len(patches), 1)
        self.assertIn("repos/cjber/legacy-forever/pulls/7", patches[0])
        self.assertIn("title=chore: sync shared files from forever-core", patches[0])
        self.assertIn("body=body", patches[0])
        self.assertFalse(any(call[1] == "repos/cjber/legacy-forever/pulls" for call in calls))

    def test_a_new_pr_is_created_with_a_post_and_returns_its_node(self):
        calls = []

        def fake_gh(*args, check=True):
            calls.append(args)
            path = args[1]
            if path.startswith("repos/cjber/legacy-forever/pulls?"):
                return subprocess.CompletedProcess(args, 0, "[]", "")
            if path == "repos/cjber/legacy-forever/pulls":
                output = json.dumps({"number": 9, "html_url": "https://example.test/pull/9", "node_id": "PR_9"})
                return subprocess.CompletedProcess(args, 0, output, "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with mock.patch.object(sync, "gh", side_effect=fake_gh):
            number, url, status, node_id = sync.open_or_update_pr("legacy-forever", "body")

        self.assertEqual((number, url, status, node_id), (9, "https://example.test/pull/9", "opened", "PR_9"))
        posts = [call for call in calls if "--method" in call and "POST" in call]
        self.assertEqual(len(posts), 1)
        self.assertIn("head=forever-core-sync", posts[0])
        self.assertIn("base=main", posts[0])
        self.assertIn("body=body", posts[0])

    def test_enabling_auto_merge_is_the_one_graphql_call(self):
        calls = []

        def fake_gh(*args, check=True):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "{}", "")

        with mock.patch.object(sync, "gh", side_effect=fake_gh):
            sync.enable_auto_merge("PR_9")

        self.assertEqual(calls[0][1], "graphql")
        self.assertIn("enablePullRequestAutoMerge", " ".join(calls[0]))

    def test_a_failed_auto_merge_is_a_warning_not_a_failure(self):
        def fake_gh(*args, check=True):
            if check:
                raise sync.SyncError("GraphQL: API rate limit already exceeded")
            return subprocess.CompletedProcess(args, 1, "", "")

        with mock.patch.object(sync, "gh", side_effect=fake_gh):
            warning = sync.auto_merge_warning("PR_9")

        self.assertIn("waiting for a manual merge", warning)
        self.assertIn("API rate limit already exceeded", warning)

    def test_a_new_pr_without_auto_merge_stays_opened_with_a_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(sync, "clone", return_value=root / "repo"),
                mock.patch.object(sync, "git"),
                mock.patch.object(sync, "sync_checkout"),
                mock.patch.object(sync, "staged_files", return_value=("UI/TrackerHost.lua",)),
                mock.patch.object(sync, "commit"),
                mock.patch.object(
                    sync,
                    "open_or_update_pr",
                    return_value=(9, "https://example.test/pull/9", "opened", "PR_9"),
                ),
                mock.patch.object(sync, "enable_auto_merge", side_effect=sync.SyncError("GraphQL: no quota")),
            ):
                result = sync.sync_consumer("legacy-forever", root, root, "abc123")

        self.assertEqual(result.status, "opened")
        self.assertEqual(result.url, "https://example.test/pull/9")
        self.assertIn("waiting for a manual merge", result.detail)
        self.assertIn("GraphQL: no quota", result.detail)

    def test_an_open_pr_is_armed_only_when_auto_merge_is_off(self):
        def listing(auto_merge):
            def fake_gh(*args, check=True):
                if args[1].startswith("repos/cjber/legacy-forever/pulls?"):
                    pull = {"number": 7, "html_url": "u", "node_id": "PR_7", "auto_merge": auto_merge}
                    return subprocess.CompletedProcess(args, 0, json.dumps([pull]), "")
                return subprocess.CompletedProcess(args, 0, "", "")

            return fake_gh

        with mock.patch.object(sync, "gh", side_effect=listing({"merge_method": "squash"})):
            self.assertIsNone(sync.open_or_update_pr("legacy-forever", "body")[3])
        with mock.patch.object(sync, "gh", side_effect=listing(None)):
            self.assertEqual(sync.open_or_update_pr("legacy-forever", "body")[3], "PR_7")

    def test_an_up_to_date_consumer_closes_the_stale_sync_pr(self):
        calls = []

        def fake_gh(*args, check=True):
            calls.append(args)
            if args[1].startswith("repos/cjber/legacy-forever/pulls?"):
                return subprocess.CompletedProcess(args, 0, json.dumps([{"number": 9}]), "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(sync, "clone", return_value=root / "repo"),
                mock.patch.object(sync, "git"),
                mock.patch.object(sync, "sync_checkout"),
                mock.patch.object(sync, "staged_files", return_value=()),
                mock.patch.object(sync, "gh", side_effect=fake_gh),
            ):
                result = sync.sync_consumer("legacy-forever", root, root, "abc123")

        self.assertEqual((result.status, result.detail), ("up to date", "closed #9"))
        self.assertTrue(any("state=closed" in call and "repos/cjber/legacy-forever/pulls/9" in call for call in calls))
        self.assertTrue(
            any(
                "DELETE" in call and "repos/cjber/legacy-forever/git/refs/heads/forever-core-sync" in call
                for call in calls
            )
        )

    def test_an_up_to_date_consumer_without_a_sync_pr_changes_nothing(self):
        def fake_gh(*args, check=True):
            self.assertNotIn("--method", args)
            return subprocess.CompletedProcess(args, 0, "[]", "")

        with mock.patch.object(sync, "gh", side_effect=fake_gh):
            self.assertEqual(sync.close_stale_prs("legacy-forever", "abc123"), [])


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
