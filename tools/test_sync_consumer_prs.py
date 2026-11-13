"""Tests for tools/sync_consumer_prs.py: consumer derivation, PR text and summaries, no network."""

import base64
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import check_core_shared
import sync_consumer_prs as sync
from check_consumers import core_pin


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
                mock.patch.object(sync, "open_sync_prs", return_value=[]),
                mock.patch.object(sync, "git"),
                mock.patch.object(sync, "sync_checkout"),
                mock.patch.object(
                    sync, "staged_changes", return_value=([{"path": "UI/TrackerHost.lua", "contents": "eA=="}], [])
                ),
                mock.patch.object(sync, "point_branch"),
                mock.patch.object(sync, "create_commit"),
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

        def fake_git(root, *args, check=True):
            if "rev-parse" in args:
                return subprocess.CompletedProcess(args, 0, "sameoid\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(sync, "clone", return_value=root / "repo"),
                mock.patch.object(sync, "git", side_effect=fake_git),
                mock.patch.object(sync, "sync_checkout"),
                mock.patch.object(sync, "staged_changes", return_value=([], [])),
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


class CheckoutTest(unittest.TestCase):
    def test_a_synced_phrase_is_written_to_the_phrase_template(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "shortest-path-forever"
            (root / "tools").mkdir(parents=True)
            (root / "Locales").mkdir()
            (root / "UI").mkdir()
            (root / "Locales" / "phrases.txt").write_text("", encoding="utf-8")
            (root / "tools" / "phrases.py").write_text(
                "from pathlib import Path\n"
                "text = Path('UI/TrackerHost.lua').read_text()\n"
                "for phrase in sorted({part.split('\"')[0] for part in text.split('L[\"')[1:]}):\n"
                '    print(f\'L["{phrase}"] = "{phrase}"\')\n',
                encoding="utf-8",
            )
            real_run = sync.run

            def fake_run(command, cwd=None, check=True, env=None):
                if command[-1].endswith("phrases.py"):
                    return real_run(command, cwd=cwd, check=check, env=env)
                (root / "UI" / "TrackerHost.lua").write_text('L["new phrase"] = "new phrase"\n', encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch.object(sync, "run", side_effect=fake_run):
                sync.sync_checkout(root, root.parent)

            self.assertEqual(
                (root / "Locales" / "phrases.txt").read_text(encoding="utf-8"),
                'L["new phrase"] = "new phrase"\n',
            )

    def test_a_phrase_extractor_importing_the_tools_package_runs(self):
        # tweaks-forever's extractor imports `tools.forever_tools`, as `python3 -m tools.phrases` allows, while
        # skillup-forever's imports a sibling module in tools/. One run must serve both.
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            core = workspace / "core"
            (core / "tools").mkdir(parents=True)
            (core / "tools" / "sync_consumers.py").write_text("", encoding="utf-8")
            root = workspace / "tweaks-forever"
            (root / "tools" / "forever_tools").mkdir(parents=True)
            (root / "Locales").mkdir()
            (root / "tools" / "__init__.py").write_text("", encoding="utf-8")
            (root / "tools" / "forever_tools" / "__init__.py").write_text("", encoding="utf-8")
            (root / "tools" / "forever_tools" / "lua.py").write_text("WORD = 'package'\n", encoding="utf-8")
            (root / "tools" / "sibling.py").write_text("WORD = 'sibling'\n", encoding="utf-8")
            (root / "tools" / "phrases.py").write_text(
                "from tools.forever_tools.lua import WORD as A\nfrom sibling import WORD as B\nprint(A, B)\n",
                encoding="utf-8",
            )
            (root / "Locales" / "phrases.txt").write_text("stale\n", encoding="utf-8")

            sync.sync_checkout(root, core)

            self.assertEqual((root / "Locales" / "phrases.txt").read_text(encoding="utf-8"), "package sibling\n")

    def test_a_consumer_without_a_phrase_template_is_left_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "legacy-forever"
            (root / "tools").mkdir(parents=True)
            (root / "tools" / "phrases.py").write_text("# extractor\n", encoding="utf-8")
            calls = []

            def fake_run(command, cwd=None, check=True, env=None):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch.object(sync, "run", side_effect=fake_run):
                sync.sync_checkout(root, root.parent)

            self.assertFalse(any(command[-1].endswith("phrases.py") for command in calls))

    def test_a_failing_phrase_generator_fails_the_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            core = workspace / "core"
            (core / "tools").mkdir(parents=True)
            (core / "tools" / "sync_consumers.py").write_text("", encoding="utf-8")
            root = workspace / "shortest-path-forever"
            (root / "tools").mkdir(parents=True)
            (root / "Locales").mkdir()
            (root / "tools" / "phrases.py").write_text(
                "import sys\nprint('no TOC', file=sys.stderr)\nraise SystemExit(3)\n", encoding="utf-8"
            )
            (root / "Locales" / "phrases.txt").write_text("stale\n", encoding="utf-8")

            with self.assertRaises(sync.SyncError) as raised:
                sync.sync_checkout(root, core)

            self.assertIn("no TOC", str(raised.exception))
            self.assertEqual((root / "Locales" / "phrases.txt").read_text(encoding="utf-8"), "stale\n")

    def test_a_stale_family_block_is_rewritten_by_the_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "shortest-path-forever"
            (root / "tools").mkdir(parents=True)
            (root / "README.md").write_text("<!-- family -->\nstale\n<!-- /family -->\n", encoding="utf-8")
            (root / "tools" / "__init__.py").write_text("", encoding="utf-8")
            (root / "tools" / "block.py").write_text('TEXT = "current family block"\n', encoding="utf-8")
            (root / "tools" / "check_family.py").write_text(
                "import sys\n"
                "from pathlib import Path\n"
                "from tools.block import TEXT\n"
                "if '--fix' in sys.argv[1:]:\n"
                "    Path('README.md').write_text(TEXT + '\\n')\n",
                encoding="utf-8",
            )
            real_run = sync.run

            def fake_run(command, cwd=None, check=True, env=None):
                if command[1].endswith("check_family.py"):
                    return real_run(command, cwd=cwd, check=check, env=env)
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch.object(sync, "run", side_effect=fake_run):
                sync.sync_checkout(root, root.parent)

            self.assertEqual((root / "README.md").read_text(encoding="utf-8"), "current family block\n")

    def test_a_consumer_without_a_family_checker_is_left_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "legacy-forever"
            (root / "tools").mkdir(parents=True)
            (root / "README.md").write_text("stale\n", encoding="utf-8")
            calls = []

            def fake_run(command, cwd=None, check=True, env=None):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch.object(sync, "run", side_effect=fake_run):
                sync.sync_checkout(root, root.parent)

            self.assertFalse(any("check_family.py" in " ".join(command) for command in calls))
            self.assertEqual((root / "README.md").read_text(encoding="utf-8"), "stale\n")

    def test_a_failing_family_fix_fails_the_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            core = workspace / "core"
            (core / "tools").mkdir(parents=True)
            (core / "tools" / "sync_consumers.py").write_text("", encoding="utf-8")
            root = workspace / "legacy-forever"
            (root / "tools").mkdir(parents=True)
            (root / "README.md").write_text("stale\n", encoding="utf-8")
            (root / "tools" / "check_family.py").write_text(
                "import sys\nprint('family markers missing', file=sys.stderr)\nraise SystemExit(4)\n", encoding="utf-8"
            )

            with self.assertRaises(sync.SyncError) as raised:
                sync.sync_checkout(root, core)

            self.assertIn("family markers missing", str(raised.exception))
            self.assertEqual((root / "README.md").read_text(encoding="utf-8"), "stale\n")

    def test_the_updater_that_runs_is_the_one_being_installed(self):
        # A release that adds a vendored data file (#339's backdrops.txt) reaches a consumer whose older sync.py does
        # not list it: the producer's sync.py is copied over the vendored one before `update` runs.
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            core = workspace / "core"
            (core / "tools").mkdir(parents=True)
            (core / "tools" / "sync_consumers.py").write_text("", encoding="utf-8")
            producer = core / sync.TOOLING_PRODUCER_ROOT / "forever_tools"
            producer.mkdir(parents=True)
            (producer / "sync.py").write_text('FILES = ("backdrops.txt",)\n', encoding="utf-8")
            (producer / "backdrops.txt").write_text("new data\n", encoding="utf-8")
            (producer / "MANIFEST.json").write_text("{}", encoding="utf-8")
            (producer / "sync.py").chmod(0o755)

            root = workspace / "legacy-forever"
            vendored = root / "tools" / "forever_tools"
            vendored.mkdir(parents=True)
            (vendored / "MANIFEST.json").write_text("{}", encoding="utf-8")
            (vendored / "sync.py").write_text("FILES = ()\n", encoding="utf-8")

            def fake_run(command, cwd=None, check=True, env=None):
                # The vendored updater copies the data files it lists, and refuses a manifest it cannot account for.
                script = Path(command[1])
                if script.name == "sync.py" and "update" in command:
                    if "backdrops.txt" not in script.read_text(encoding="utf-8"):
                        raise sync.SyncError("the producer's MANIFEST.json is stale")
                    shutil.copyfile(producer / "backdrops.txt", script.parent / "backdrops.txt")
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch.object(sync, "run", side_effect=fake_run):
                sync.sync_checkout(root, core)

            self.assertEqual((vendored / "sync.py").read_text(encoding="utf-8"), 'FILES = ("backdrops.txt",)\n')
            self.assertEqual((vendored / "backdrops.txt").read_text(encoding="utf-8"), "new data\n")
            self.assertEqual((vendored / "sync.py").stat().st_mode & 0o777, 0o755)


class SignedCommitTest(unittest.TestCase):
    def test_sync_consumer_sends_one_create_commit_on_branch_and_never_pushes(self):
        api_calls = []
        run_calls = []
        diff = "M\tUI/TrackerHost.lua\nD\tUI/Gone.lua\nR100\tCore/Old.lua\tCore/New.lua\n"

        def fake_run(command, cwd=None, check=True):
            run_calls.append(command)
            if "rev-parse" in command:
                return subprocess.CompletedProcess(command, 0, "mainoid\n", "")
            if "diff" in command:
                return subprocess.CompletedProcess(command, 0, diff, "")
            return subprocess.CompletedProcess(command, 0, "", "")

        requests = []

        def fake_api(path, *args, check=True):
            api_calls.append((path, args, check))
            if path == "graphql" and "--input" in args:
                request = json.loads(Path(args[args.index("--input") + 1]).read_text(encoding="utf-8"))
                requests.append(request)
                if "createCommitOnBranch" in request["query"]:
                    made = {"data": {"createCommitOnBranch": {"commit": {"oid": "commitoid"}}}}
                    return subprocess.CompletedProcess((path, *args), 0, json.dumps(made), "")
            if path.startswith("repos/cjber/legacy-forever/pulls?"):
                return subprocess.CompletedProcess((path, *args), 0, "[]", "")
            if path == "repos/cjber/legacy-forever/pulls":
                created = {"number": 9, "html_url": "https://example.test/pull/9", "node_id": "PR_9"}
                return subprocess.CompletedProcess((path, *args), 0, json.dumps(created), "")
            return subprocess.CompletedProcess((path, *args), 0, "{}", "")

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "legacy-forever"
            (root / "UI").mkdir(parents=True)
            (root / "Core").mkdir()
            (root / "UI" / "TrackerHost.lua").write_bytes(b"shared tracker\n")
            (root / "Core" / "New.lua").write_bytes(b"new core\n")
            with (
                mock.patch.object(sync, "run", side_effect=fake_run),
                mock.patch.object(sync, "api", side_effect=fake_api),
            ):
                result = sync.sync_consumer("legacy-forever", workspace, workspace, "abc123")

        self.assertEqual(result.status, "opened")
        commits = [request for request in requests if "createCommitOnBranch" in request["query"]]
        self.assertEqual(len(commits), 1)
        given = commits[0]["variables"]["input"]
        self.assertEqual(
            given["branch"],
            {"repositoryNameWithOwner": "cjber/legacy-forever", "branchName": sync.SCRATCH_BRANCH},
        )
        self.assertEqual(given["expectedHeadOid"], "mainoid")
        self.assertEqual(given["message"], {"headline": sync.TITLE, "body": "Core commit: abc123"})
        tracker = base64.b64encode(b"shared tracker\n").decode()
        new_core = base64.b64encode(b"new core\n").decode()
        self.assertCountEqual(
            given["fileChanges"]["additions"],
            [{"path": "UI/TrackerHost.lua", "contents": tracker}, {"path": "Core/New.lua", "contents": new_core}],
        )
        self.assertEqual(given["fileChanges"]["deletions"], [{"path": "UI/Gone.lua"}, {"path": "Core/Old.lua"}])
        self.assertFalse(any(len(arg) > 4096 for call in api_calls for arg in call[1]), "file contents stay off argv")
        self.assertFalse(any("push" in " ".join(command) for command in run_calls))
        self.assertFalse(any("commit" in " ".join(command) for command in run_calls))

    def test_the_sync_branch_only_ever_moves_to_the_new_commit(self):
        api_calls = []

        def fake_git(root, *args, check=True):
            if "rev-parse" in args:
                return subprocess.CompletedProcess(args, 0, "mainoid\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        def fake_api(path, *args, check=True):
            api_calls.append((path, args, check))
            if path == "graphql" and "--input" in args:
                made = {"data": {"createCommitOnBranch": {"commit": {"oid": "commitoid"}}}}
                return subprocess.CompletedProcess((path, *args), 0, json.dumps(made), "")
            if path.startswith("repos/cjber/legacy-forever/pulls?"):
                return subprocess.CompletedProcess((path, *args), 0, "[]", "")
            if path == "repos/cjber/legacy-forever/pulls":
                created = {"number": 9, "html_url": "https://example.test/pull/9", "node_id": "PR_9"}
                return subprocess.CompletedProcess((path, *args), 0, json.dumps(created), "")
            return subprocess.CompletedProcess((path, *args), 0, "{}", "")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(sync, "clone", return_value=root / "repo"),
                mock.patch.object(sync, "git", side_effect=fake_git),
                mock.patch.object(sync, "sync_checkout"),
                mock.patch.object(
                    sync, "staged_changes", return_value=([{"path": "UI/TrackerHost.lua", "contents": "eA=="}], [])
                ),
                mock.patch.object(sync, "api", side_effect=fake_api),
            ):
                result = sync.sync_consumer("legacy-forever", root, root, "abc123")

        self.assertEqual(result.status, "opened")
        sync_path = f"repos/cjber/legacy-forever/git/refs/heads/{sync.BRANCH}"
        moves = [call for call in api_calls if call[0] == sync_path and any(arg.startswith("sha=") for arg in call[1])]
        self.assertEqual(len(moves), 1)
        self.assertIn("PATCH", moves[0][1])
        self.assertIn("sha=commitoid", moves[0][1])
        self.assertFalse(
            any("sha=mainoid" in call[1] for call in moves),
            "the sync branch must never point at main",
        )
        scratch_path = f"repos/cjber/legacy-forever/git/refs/heads/{sync.SCRATCH_BRANCH}"
        scratch_deletes = [call for call in api_calls if call[0] == scratch_path and "DELETE" in call[1]]
        self.assertEqual(len(scratch_deletes), 1)
        commit_index = next(
            index for index, call in enumerate(api_calls) if call[0] == "graphql" and "--input" in call[1]
        )
        # The commit, then the sync branch moves onto it, then the scratch ref goes: the commit is never unreferenced.
        self.assertLess(commit_index, api_calls.index(moves[0]))
        self.assertLess(api_calls.index(moves[0]), api_calls.index(scratch_deletes[0]))

    def test_a_missing_branch_ref_is_created_after_the_patch_fails(self):
        calls = []

        def fake_api(path, *args, check=True):
            calls.append((path, args, check))
            code = 1 if "PATCH" in args else 0
            return subprocess.CompletedProcess((path, *args), code, "", "")

        with mock.patch.object(sync, "api", side_effect=fake_api):
            sync.point_branch("legacy-forever", sync.BRANCH, "mainoid")

        self.assertIn("PATCH", calls[0][1])
        self.assertIn("force=true", calls[0][1])
        self.assertEqual(calls[1][0], "repos/cjber/legacy-forever/git/refs")
        self.assertIn("POST", calls[1][1])
        self.assertIn("ref=refs/heads/forever-core-sync", calls[1][1])
        self.assertIn("sha=mainoid", calls[1][1])


class InPlaceSyncTest(unittest.TestCase):
    """An open sync PR is updated by adding to its head, never by rewriting the branch from `main`."""

    PULL = {
        "number": 7,
        "html_url": "https://example.test/pull/7",
        "node_id": "PR_7",
        "auto_merge": {"merge_method": "squash"},
    }

    def run_sync(self, root, api, git_calls, pull=None):
        """One consumer sync with the network faked; `pull` is what the sync PR listing returns."""
        with (
            mock.patch.object(sync, "clone", return_value=root / "repo"),
            mock.patch.object(sync, "open_sync_prs", return_value=[] if pull is None else [pull]),
            mock.patch.object(sync, "git", side_effect=git_calls),
            mock.patch.object(sync, "sync_checkout"),
            mock.patch.object(
                sync,
                "staged_changes",
                return_value=([{"path": "UI/TrackerHost.lua", "contents": "eA=="}], []),
            ),
            mock.patch.object(sync, "api", side_effect=api),
        ):
            return sync.sync_consumer("legacy-forever", root, root, "abc123")

    def test_an_open_sync_pr_is_updated_on_top_of_its_own_head(self):
        calls = []
        requests = []

        def fake_git(root, *args, check=True):
            if args[:2] == ("rev-parse", "HEAD"):
                return subprocess.CompletedProcess(args, 0, "mainoid\n", "")
            if args[:2] == ("rev-parse", "FETCH_HEAD"):
                return subprocess.CompletedProcess(args, 0, "proid\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        def fake_api(path, *args, check=True):
            calls.append((path, args, check))
            if path == "graphql" and "--input" in args:
                requests.append(json.loads(Path(args[args.index("--input") + 1]).read_text(encoding="utf-8")))
                made = {"data": {"createCommitOnBranch": {"commit": {"oid": "commitoid"}}}}
                return subprocess.CompletedProcess((path, *args), 0, json.dumps(made), "")
            return subprocess.CompletedProcess((path, *args), 0, "{}", "")

        git_calls = []

        def recording_git(root, *args, check=True):
            git_calls.append(args)
            return fake_git(root, *args, check=check)

        with tempfile.TemporaryDirectory() as directory:
            result = self.run_sync(Path(directory), fake_api, recording_git, self.PULL)

        self.assertEqual((result.status, result.url), ("updated in place", "https://example.test/pull/7"))
        given = requests[0]["variables"]["input"]
        self.assertEqual(given["branch"]["branchName"], sync.BRANCH)
        self.assertEqual(given["expectedHeadOid"], "proid")
        # The sync ran on the PR's head rather than on main, so the commits already pushed to it are its parents.
        self.assertIn(("checkout", "-B", sync.BRANCH, "proid"), git_calls)
        # The branch moves only through the signed commit, never through a ref update that could drop a commit.
        self.assertFalse(
            [call for call in calls if call[0].endswith(f"refs/heads/{sync.BRANCH}")],
            "an open PR's branch is never pointed anywhere by a ref update",
        )

    def test_a_sync_that_cannot_update_the_open_pr_leaves_it_alone_and_says_why(self):
        calls = []

        def fake_git(root, *args, check=True):
            if args[:2] == ("rev-parse", "HEAD"):
                return subprocess.CompletedProcess(args, 0, "mainoid\n", "")
            if args[:2] == ("rev-parse", "FETCH_HEAD"):
                return subprocess.CompletedProcess(args, 0, "proid\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        def fake_api(path, *args, check=True):
            calls.append((path, args, check))
            if path == "graphql":
                raise sync.SyncError("graphql: Expected branch to point to proid but it did not")
            return subprocess.CompletedProcess((path, *args), 0, "", "")

        with tempfile.TemporaryDirectory() as directory:
            result = self.run_sync(Path(directory), fake_api, fake_git, self.PULL)

        self.assertEqual(result.status, "left alone")
        self.assertEqual(result.url, "https://example.test/pull/7")
        self.assertIn("Expected branch to point to proid", result.detail)
        comments = [call for call in calls if call[0] == "repos/cjber/legacy-forever/issues/7/comments"]
        self.assertEqual(len(comments), 1, "the PR is told why it was not updated")
        self.assertTrue(
            any(arg.startswith("body=") and "left the branch exactly as it is" in arg for arg in comments[0][1])
        )
        self.assertFalse(
            [call for call in calls if call[0].endswith(f"refs/heads/{sync.BRANCH}")],
            "a failed in-place update never force-moves the branch",
        )
        self.assertFalse([call for call in calls if "DELETE" in call[1]])

    def test_a_sync_pr_holding_other_commits_is_not_closed_when_nothing_changed(self):
        calls = []

        def fake_git(root, *args, check=True):
            if args[:2] == ("rev-parse", "HEAD"):
                return subprocess.CompletedProcess(args, 0, "mainoid\n", "")
            if args[:2] == ("rev-parse", "FETCH_HEAD"):
                return subprocess.CompletedProcess(args, 0, "proid\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        def fake_api(path, *args, check=True):
            calls.append((path, args, check))
            return subprocess.CompletedProcess((path, *args), 0, "{}", "")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(sync, "clone", return_value=root / "repo"),
                mock.patch.object(sync, "open_sync_prs", return_value=[self.PULL]),
                mock.patch.object(sync, "git", side_effect=fake_git),
                mock.patch.object(sync, "sync_checkout"),
                mock.patch.object(sync, "staged_changes", return_value=([], [])),
                mock.patch.object(sync, "api", side_effect=fake_api),
            ):
                result = sync.sync_consumer("legacy-forever", root, root, "abc123")

        self.assertEqual(result.status, "up to date")
        self.assertIn("already carries the newest shared files", result.detail)
        self.assertEqual(calls, [], "the PR keeps the commits pushed to it and is neither closed nor touched")

    def test_a_branch_that_cannot_be_read_fails_the_sync_instead_of_rebuilding_from_main(self):
        calls = []

        def fake_git(root, *args, check=True):
            if args[:2] == ("rev-parse", "HEAD"):
                return subprocess.CompletedProcess(args, 0, "mainoid\n", "")
            if args[0] == "fetch":
                return subprocess.CompletedProcess(args, 1, "", "fatal: unable to access origin")
            return subprocess.CompletedProcess(args, 0, "", "")

        def fake_api(path, *args, check=True):
            calls.append((path, args, check))
            return subprocess.CompletedProcess((path, *args), 0, "{}", "")

        with tempfile.TemporaryDirectory() as directory:
            result = self.run_sync(Path(directory), fake_api, fake_git, self.PULL)

        self.assertEqual(result.status, "failed")
        self.assertIn("could not fetch forever-core-sync", result.detail)
        self.assertFalse(any("--input" in call[1] for call in calls), "nothing is committed over an unread branch")

    def run_fresh(self, root, git_calls, listings, commit):
        """A sync whose open PR goes away mid-run; `listings` are the successive sync PR listings."""
        with (
            mock.patch.object(sync, "clone", side_effect=lambda repo, workspace: workspace / repo),
            mock.patch.object(sync, "open_sync_prs", side_effect=listings),
            mock.patch.object(sync, "git", side_effect=git_calls),
            mock.patch.object(sync, "sync_checkout"),
            mock.patch.object(
                sync, "staged_changes", return_value=([{"path": "UI/TrackerHost.lua", "contents": "eA=="}], [])
            ),
            mock.patch.object(sync, "create_commit", side_effect=commit) as create,
            mock.patch.object(sync, "point_branch") as point,
            mock.patch.object(sync, "delete_branch"),
            mock.patch.object(sync, "left_alone") as alone,
            mock.patch.object(
                sync, "open_or_update_pr", return_value=(8, "https://example.test/pull/8", "opened", None)
            ) as opened,
        ):
            result = sync.sync_consumer("legacy-forever", root, root, "abc123")
        return result, create, point, alone, opened

    def test_a_pr_whose_branch_is_already_gone_gets_a_fresh_branch_from_main(self):
        def fake_git(root, *args, check=True):
            if args[:2] == ("rev-parse", "HEAD"):
                return subprocess.CompletedProcess(args, 0, "mainoid\n", "")
            if args[0] == "fetch":
                return subprocess.CompletedProcess(args, 128, "", "fatal: couldn't find remote ref refs/heads/x")
            return subprocess.CompletedProcess(args, 0, "", "")

        with tempfile.TemporaryDirectory() as directory:
            result, create, point, alone, opened = self.run_fresh(
                Path(directory), fake_git, [[self.PULL]], lambda *args: "commitoid"
            )

        self.assertEqual((result.status, result.url), ("opened", "https://example.test/pull/8"))
        self.assertEqual(create.call_args.args[1:3], (sync.SCRATCH_BRANCH, "mainoid"))
        point.assert_any_call("legacy-forever", sync.BRANCH, "commitoid")
        alone.assert_not_called()
        self.assertIsNone(opened.call_args.args[2], "the merged PR is not refreshed; a new one is opened")

    def test_a_pr_that_merges_before_the_commit_is_synced_again_from_the_new_main(self):
        heads = iter(["mainoid\n", "newmainoid\n"])

        def fake_git(root, *args, check=True):
            if args[:2] == ("rev-parse", "HEAD"):
                return subprocess.CompletedProcess(args, 0, next(heads), "")
            if args[:2] == ("rev-parse", "FETCH_HEAD"):
                return subprocess.CompletedProcess(args, 0, "proid\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        def commit(repo, branch, expected, *rest):
            if branch == sync.BRANCH:
                raise sync.SyncError("gh api graphql failed: gh: Branch not found")
            return "commitoid"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, create, point, alone, opened = self.run_fresh(root, fake_git, [[self.PULL], [], []], commit)

        self.assertEqual(result.status, "opened")
        self.assertEqual(create.call_args.args[1:3], (sync.SCRATCH_BRANCH, "newmainoid"))
        alone.assert_not_called()
        self.assertIsNone(opened.call_args.args[2])


class ToolingTest(unittest.TestCase):
    def test_only_packages_with_a_manifest_are_synced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / "tools" / "forever_tools"
            tools.mkdir(parents=True)
            (tools / "MANIFEST.json").write_text("{}", encoding="utf-8")
            self.assertEqual(sync.tooling_packages(root), ["forever_tools"])


class PinTest(unittest.TestCase):
    """The ForeverCore pin each consumer checks its specs and CI against."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "legacy-forever"
        self.pin = self.root / "tools" / "forever-core.txt"
        self.pin.parent.mkdir(parents=True)

    def write_pin(self, text):
        self.pin.write_text(text, encoding="utf-8")

    def bump(self, root, latest):
        """`bump_pin` on a consumer with no changelog, whose skip notice is not under test here."""
        with contextlib.redirect_stdout(io.StringIO()):
            return sync.bump_pin(root, latest)

    def test_an_older_pin_moves_to_the_latest_release(self):
        self.write_pin("v1.3.2\n")
        self.assertEqual(self.bump(self.root, "v1.4.0"), "v1.3.2")
        self.assertEqual(self.pin.read_text(encoding="utf-8"), "v1.4.0\n")

    def test_an_equal_pin_is_left_alone(self):
        self.write_pin("v1.4.0\n")
        self.assertIsNone(self.bump(self.root, "v1.4.0"))
        self.assertEqual(self.pin.read_text(encoding="utf-8"), "v1.4.0\n")

    def test_a_newer_pin_never_moves_backwards(self):
        self.write_pin("v1.5.0\n")
        self.assertIsNone(self.bump(self.root, "v1.4.0"))
        self.assertEqual(self.pin.read_text(encoding="utf-8"), "v1.5.0\n")

    def test_versions_compare_numerically(self):
        self.write_pin("v1.9.0\n")
        self.assertEqual(sync.release_version("v1.10.0"), (1, 10, 0))
        self.assertGreater(sync.release_version("v1.10.0"), sync.release_version("v1.9.0"))
        self.assertEqual(self.bump(self.root, "v1.10.0"), "v1.9.0")
        self.assertEqual(self.pin.read_text(encoding="utf-8"), "v1.10.0\n")

    def test_a_pin_that_is_not_a_release_tag_is_left_alone_with_a_notice(self):
        self.write_pin("main\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertIsNone(sync.bump_pin(self.root, "v1.4.0"))
        self.assertEqual(self.pin.read_text(encoding="utf-8"), "main\n")
        self.assertIn("is not a vX.Y.Z tag", out.getvalue())

    def test_a_consumer_without_a_pin_file_is_untouched(self):
        self.assertIsNone(self.bump(self.root, "v1.4.0"))
        self.assertEqual(sorted(self.pin.parent.iterdir()), [])

    def test_a_prefixed_consumer_gets_its_pin_below_the_addon_folder(self):
        root = Path(self.tmp.name) / "kiln-forever"
        pin = root / "addon" / "KilnForever" / "tools" / "forever-core.txt"
        pin.parent.mkdir(parents=True)
        pin.write_text("v1.0.0\n", encoding="utf-8")
        self.assertEqual(self.bump(root, "v1.4.0"), "v1.0.0")
        self.assertEqual(pin.read_text(encoding="utf-8"), "v1.4.0\n")

    def test_a_failed_latest_release_read_warns_and_bumps_nothing(self):
        self.write_pin("v1.3.2\n")
        out = io.StringIO()
        with (
            mock.patch.object(sync, "api", side_effect=sync.SyncError("gh: no network")),
            contextlib.redirect_stdout(out),
        ):
            self.assertIsNone(sync.latest_core_release())
        self.assertIn("::warning::", out.getvalue())
        self.assertEqual(self.pin.read_text(encoding="utf-8"), "v1.3.2\n")

    def test_the_latest_release_is_read_for_the_run(self):
        requests = []

        def fake_api(path, *args, check=True):
            requests.append(path)
            return subprocess.CompletedProcess(path, 0, json.dumps({"tag_name": "v1.4.0"}), "")

        with mock.patch.object(sync, "api", side_effect=fake_api):
            self.assertEqual(sync.latest_core_release(), "v1.4.0")
        self.assertEqual(requests, ["repos/cjber/forever-core/releases/latest"])

    def test_sync_checkout_bumps_the_pin_after_the_syncs(self):
        self.write_pin("v1.3.2\n")
        with mock.patch.object(sync, "run"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sync.sync_checkout(self.root, self.root.parent, "v1.4.0"), "v1.3.2")
        self.assertEqual(self.pin.read_text(encoding="utf-8"), "v1.4.0\n")

    def test_the_pr_body_names_the_bump_the_sync_made(self):
        bodies = []

        def fake_open(repo, body, pull=None):
            bodies.append(body)
            return 9, "https://example.test/pull/9", "opened", None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(sync, "clone", return_value=root / "repo"),
                mock.patch.object(sync, "open_sync_prs", return_value=[]),
                mock.patch.object(sync, "git"),
                mock.patch.object(sync, "sync_checkout", return_value="v1.3.2"),
                mock.patch.object(
                    sync, "staged_changes", return_value=([{"path": "tools/forever-core.txt", "contents": "eA=="}], [])
                ),
                mock.patch.object(sync, "point_branch"),
                mock.patch.object(sync, "create_commit"),
                mock.patch.object(sync, "open_or_update_pr", side_effect=fake_open),
            ):
                sync.sync_consumer("legacy-forever", root, root, "abc123", "v1.4.0")

        self.assertEqual(len(bodies), 1)
        self.assertIn(
            "Moves the ForeverCore pin from v1.3.2 to v1.4.0, so this addon's CI runs against the latest release.",
            bodies[0],
        )


class BundleTest(unittest.TestCase):
    """What a moved pin takes with it: the shipped external, the TOC field and the changelog's shared-code note."""

    PKGMETA = (
        "package-as: LegacyForever\n\n"
        "externals:\n"
        "  ForeverCore: https://github.com/cjber/forever-core/releases/download/"
        "v1.3.2/ForeverCore-v1.3.2-forever.zip\n\n"
        "move-folders:\n"
        "  LegacyForever/ForeverCore: ForeverCore\n"
    )
    TOC = "## Interface: 16001\n## Dependencies: ForeverCore\n## Title: Legacy Forever\n"
    TOC_WITH_FIELD = (
        "## Interface: 16001\n## Dependencies: ForeverCore\n## X-Forever-Core: v1.3.2\n## Title: Legacy Forever\n"
    )
    CHANGELOG = (
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "- A note that waits for the next release.\n\n"
        "## [1.2.3] - 2026-11-01\n\n"
        "- An older entry.\n"
    )
    DAY = date(2026, 11, 11)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "legacy-forever"
        (self.root / "tools").mkdir(parents=True)
        self.pin = self.root / "tools" / "forever-core.txt"
        self.pin.write_text("v1.3.2\n", encoding="utf-8")
        self.pkgmeta = self.root / ".pkgmeta"
        self.pkgmeta.write_text(self.PKGMETA, encoding="utf-8")
        self.toc = self.root / "LegacyForever.toc"
        self.toc.write_text(self.TOC, encoding="utf-8")
        self.changelog = self.root / "CHANGELOG.md"
        self.changelog.write_text(self.CHANGELOG, encoding="utf-8")
        # These tests run offline: the released-tag reads are faked per test, and no tag is a released sync entry.
        for name, value in (("latest_release_tag", None), ("remote_tag_exists", False)):
            patcher = mock.patch.object(sync, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def bump(self, latest="v1.4.0"):
        """`bump_pin`, with its notices kept out of the test output."""
        with contextlib.redirect_stdout(io.StringIO()):
            return sync.bump_pin(self.root, latest, self.DAY)

    def test_a_moved_pin_points_the_external_at_the_new_release(self):
        self.assertEqual(self.bump(), "v1.3.2")
        self.assertIn(
            "  ForeverCore: https://github.com/cjber/forever-core/releases/download/"
            "v1.4.0/ForeverCore-v1.4.0-forever.zip\n",
            self.pkgmeta.read_text(encoding="utf-8"),
        )
        self.assertIn("  LegacyForever/ForeverCore: ForeverCore\n", self.pkgmeta.read_text(encoding="utf-8"))

    def test_a_moved_pin_adds_the_toc_field_after_dependencies(self):
        self.bump()
        self.assertEqual(
            self.toc.read_text(encoding="utf-8"),
            "## Interface: 16001\n## Dependencies: ForeverCore\n## X-Forever-Core: v1.4.0\n## Title: Legacy Forever\n",
        )

    def test_an_existing_toc_field_is_replaced_in_place(self):
        self.toc.write_text(
            "## Interface: 16001\n## X-Forever-Core: v1.0.0\n## Dependencies: ForeverCore\n", encoding="utf-8"
        )
        self.bump()
        self.assertEqual(
            self.toc.read_text(encoding="utf-8"),
            "## Interface: 16001\n## X-Forever-Core: v1.4.0\n## Dependencies: ForeverCore\n",
        )

    def test_a_moved_pin_puts_the_shared_bullet_under_the_unreleased_notes(self):
        self.assertEqual(self.bump(), "v1.3.2")
        self.assertEqual(
            self.changelog.read_text(encoding="utf-8"),
            "# Changelog\n\n"
            "## [Unreleased]\n\n"
            "- A note that waits for the next release.\n"
            f"{sync.SYNC_BULLET}\n\n"
            "## [1.2.3] - 2026-11-01\n\n"
            "- An older entry.\n",
        )

    def test_the_shared_bullet_goes_before_an_addon_authors_subsection(self):
        text = (
            "## [Unreleased]\n\n- **A player note.** What changed.\n\n### For addon authors\n\n- An API note.\n\n"
            "## [1.2.3] - 2026-11-01\n\n- An older entry.\n"
        )
        self.assertEqual(
            sync.with_sync_note(text),
            "## [Unreleased]\n\n- **A player note.** What changed.\n"
            f"{sync.SYNC_BULLET}\n\n"
            "### For addon authors\n\n- An API note.\n\n"
            "## [1.2.3] - 2026-11-01\n\n- An older entry.\n",
        )

    def test_unreleased_notes_leave_the_core_for_the_next_release_with_a_notice(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sync.bump_pin(self.root, "v1.4.0", self.DAY)
        self.assertIn("CHANGELOG.md has unreleased notes; the core ships in its next release", out.getvalue())
        text = self.changelog.read_text(encoding="utf-8")
        self.assertNotIn(sync.SYNC_MARKER, text)
        self.assertEqual(text.count(sync.SYNC_BULLET), 1)

    def test_a_second_run_adds_no_duplicate_shared_bullet(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(sync.add_changelog_entry(self.root, self.DAY))
        once = self.changelog.read_text(encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertFalse(sync.add_changelog_entry(self.root, self.DAY))
        self.assertEqual(self.changelog.read_text(encoding="utf-8"), once)
        self.assertEqual(once.count(sync.SYNC_BULLET), 1)
        self.assertIn("CHANGELOG.md has unreleased notes; the core ships in its next release", out.getvalue())

    def test_an_empty_unreleased_section_still_gets_the_marked_entry(self):
        self.changelog.write_text(
            "# Changelog\n\n## [Unreleased]\n\n## [1.2.3] - 2026-11-01\n\n- An older entry.\n", encoding="utf-8"
        )
        self.assertTrue(sync.add_changelog_entry(self.root, self.DAY))
        self.assertEqual(
            self.changelog.read_text(encoding="utf-8"),
            "# Changelog\n\n"
            "## [Unreleased]\n\n"
            "## [1.2.4] - 2026-11-11\n\n"
            f"{sync.SYNC_MARKER}\n\n"
            f"{sync.SYNC_BULLET}\n\n"
            "## [1.2.3] - 2026-11-01\n\n"
            "- An older entry.\n",
        )

    def test_the_newest_release_is_compared_numerically(self):
        self.changelog.write_text("## [Unreleased]\n\n## [1.10.0] - 2026-11-01\n\n- Older.\n", encoding="utf-8")
        self.bump()
        self.assertIn("## [1.10.1] - 2026-11-11\n", self.changelog.read_text(encoding="utf-8"))

    def test_a_changelog_without_unreleased_is_left_alone_with_a_notice(self):
        self.changelog.write_text("## [1.2.3] - 2026-11-01\n\n- An older entry.\n", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sync.bump_pin(self.root, "v1.4.0", self.DAY)
        self.assertEqual(self.changelog.read_text(encoding="utf-8"), "## [1.2.3] - 2026-11-01\n\n- An older entry.\n")
        self.assertIn("has no `## [Unreleased]` heading", out.getvalue())
        self.assertEqual(self.pin.read_text(encoding="utf-8"), "v1.4.0\n")

    def test_a_consumer_without_a_changelog_is_left_alone_with_a_notice(self):
        self.changelog.unlink()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sync.bump_pin(self.root, "v1.4.0", self.DAY)
        self.assertIn("no CHANGELOG.md; no release entry added", out.getvalue())
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), [".pkgmeta", "LegacyForever.toc", "tools"])

    def test_a_pin_that_does_not_move_still_repairs_the_toc(self):
        self.assertIsNone(sync.bump_pin(self.root, "v1.3.2", self.DAY))
        self.assertEqual(self.pkgmeta.read_text(encoding="utf-8"), self.PKGMETA)
        self.assertEqual(self.toc.read_text(encoding="utf-8"), self.TOC_WITH_FIELD)
        self.assertEqual(self.changelog.read_text(encoding="utf-8"), self.CHANGELOG)

    def test_a_moved_pin_changes_the_bundle_the_toc_and_the_notes(self):
        self.assertEqual(self.bump(), "v1.3.2")
        self.assertIn("v1.4.0/ForeverCore-v1.4.0-forever.zip", self.pkgmeta.read_text(encoding="utf-8"))
        self.assertIn("## X-Forever-Core: v1.4.0\n", self.toc.read_text(encoding="utf-8"))
        text = self.changelog.read_text(encoding="utf-8")
        self.assertNotIn(sync.SYNC_MARKER, text)
        self.assertIn(f"- A note that waits for the next release.\n{sync.SYNC_BULLET}\n", text)
        # The sync bot and the check that runs in the consumer read the same three copies, so they agree.
        self.assertEqual(core_pin.check(self.root), [])

    def test_an_unchanged_pin_repairs_a_lagging_bundle_with_the_shared_bullet(self):
        self.pin.write_text("v1.4.0\n", encoding="utf-8")
        self.assertIsNone(self.bump())
        self.assertIn("v1.4.0/ForeverCore-v1.4.0-forever.zip", self.pkgmeta.read_text(encoding="utf-8"))
        self.assertIn("## X-Forever-Core: v1.4.0\n", self.toc.read_text(encoding="utf-8"))
        text = self.changelog.read_text(encoding="utf-8")
        self.assertNotIn(sync.SYNC_MARKER, text)
        self.assertEqual(text.count(sync.SYNC_BULLET), 1)

    def test_a_bundle_that_already_matches_changes_nothing(self):
        self.toc.write_text(self.TOC_WITH_FIELD, encoding="utf-8")
        self.assertIsNone(self.bump("v1.3.2"))
        self.assertEqual(self.pkgmeta.read_text(encoding="utf-8"), self.PKGMETA)
        self.assertEqual(self.toc.read_text(encoding="utf-8"), self.TOC_WITH_FIELD)
        self.assertEqual(self.changelog.read_text(encoding="utf-8"), self.CHANGELOG)

    def test_an_unreleased_marked_entry_is_not_duplicated(self):
        self.pin.write_text("v1.4.0\n", encoding="utf-8")
        marked = (
            "# Changelog\n\n"
            "## [Unreleased]\n\n"
            "## [1.2.4] - 2026-11-11\n\n"
            f"{sync.SYNC_MARKER}\n\n"
            f"{sync.SYNC_BULLET}\n\n"
            "## [1.2.3] - 2026-11-01\n\n"
            "- An older entry.\n"
        )
        self.changelog.write_text(marked, encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sync.bump_pin(self.root, "v1.4.0", self.DAY)
        self.assertIn("v1.4.0/ForeverCore-v1.4.0-forever.zip", self.pkgmeta.read_text(encoding="utf-8"))
        self.assertIn("## X-Forever-Core: v1.4.0\n", self.toc.read_text(encoding="utf-8"))
        self.assertEqual(self.changelog.read_text(encoding="utf-8"), marked)
        self.assertIn("no second entry added", out.getvalue())

    MARKED_RELEASED = (
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "## [1.2.4] - 2026-11-11\n\n"
        f"{sync.SYNC_MARKER}\n\n"
        f"{sync.SYNC_BULLET}\n\n"
        "## [1.2.3] - 2026-11-01\n\n"
        "- An older entry.\n"
    )

    def test_an_already_released_marked_entry_gets_a_new_marked_entry_above_it(self):
        self.changelog.write_text(self.MARKED_RELEASED, encoding="utf-8")
        with mock.patch.object(sync, "remote_tag_exists", return_value=True):
            self.assertTrue(sync.add_changelog_entry(self.root, self.DAY))
        text = self.changelog.read_text(encoding="utf-8")
        self.assertIn(
            f"## [1.2.5] - 2026-11-11\n\n{sync.SYNC_MARKER}\n\n{sync.SYNC_BULLET}\n",
            text,
        )
        self.assertIn("## [1.2.4] - 2026-11-11\n", text)
        self.assertEqual(text.count(sync.SYNC_MARKER), 2)

    def test_an_unreleased_marked_entry_gets_no_second_entry(self):
        self.changelog.write_text(self.MARKED_RELEASED, encoding="utf-8")
        with mock.patch.object(sync, "remote_tag_exists", return_value=False):
            self.assertFalse(sync.add_changelog_entry(self.root, self.DAY))
        self.assertEqual(self.changelog.read_text(encoding="utf-8"), self.MARKED_RELEASED)

    def test_a_pin_that_already_matches_still_gets_an_entry_when_the_release_bundles_an_older_core(self):
        self.pin.write_text("v1.4.0\n", encoding="utf-8")
        self.pkgmeta.write_text(self.PKGMETA.replace("v1.3.2", "v1.4.0"), encoding="utf-8")
        self.toc.write_text(self.TOC_WITH_FIELD.replace("v1.3.2", "v1.4.0"), encoding="utf-8")
        self.changelog.write_text(self.MARKED_RELEASED, encoding="utf-8")
        with (
            mock.patch.object(sync, "latest_release_tag", return_value="v1.2.4"),
            mock.patch.object(sync, "released_core_tag", return_value="v1.3.2"),
            mock.patch.object(sync, "remote_tag_exists", return_value=True),
        ):
            self.assertIsNone(sync.bump_pin(self.root, "v1.4.0", self.DAY))
        text = self.changelog.read_text(encoding="utf-8")
        self.assertIn("## [1.2.5] - 2026-11-11\n", text)
        self.assertEqual(text.count(sync.SYNC_MARKER), 2)

    def test_a_latest_release_that_already_bundles_the_pin_gets_no_entry(self):
        self.pin.write_text("v1.4.0\n", encoding="utf-8")
        self.pkgmeta.write_text(self.PKGMETA.replace("v1.3.2", "v1.4.0"), encoding="utf-8")
        self.toc.write_text(self.TOC_WITH_FIELD.replace("v1.3.2", "v1.4.0"), encoding="utf-8")
        self.changelog.write_text(self.MARKED_RELEASED, encoding="utf-8")
        with (
            mock.patch.object(sync, "latest_release_tag", return_value="v1.2.4"),
            mock.patch.object(sync, "released_core_tag", return_value="v1.4.0"),
            mock.patch.object(sync, "remote_tag_exists", return_value=True),
        ):
            self.assertIsNone(sync.bump_pin(self.root, "v1.4.0", self.DAY))
        self.assertEqual(self.changelog.read_text(encoding="utf-8"), self.MARKED_RELEASED)

    def test_a_consumer_without_a_pkgmeta_moves_its_pin_and_gets_no_entry(self):
        self.pkgmeta.unlink()
        self.toc.unlink()
        self.assertEqual(self.bump(), "v1.3.2")
        self.assertEqual(self.pin.read_text(encoding="utf-8"), "v1.4.0\n")
        self.assertEqual(self.changelog.read_text(encoding="utf-8"), self.CHANGELOG)

    def test_a_toc_without_dependencies_is_not_guessed_at(self):
        self.toc.write_text("## Interface: 16001\n## Title: Legacy Forever\n", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sync.bump_pin(self.root, "v1.4.0", self.DAY)
        self.assertEqual(self.toc.read_text(encoding="utf-8"), "## Interface: 16001\n## Title: Legacy Forever\n")
        self.assertIn("has no `## Dependencies:` line", out.getvalue())

    def test_a_nested_addon_gets_its_bundle_below_its_addon_folder(self):
        root = Path(self.tmp.name) / "kiln-forever"
        addon = root / "addon" / "KilnForever"
        (addon / "tools").mkdir(parents=True)
        (addon / "tools" / "forever-core.txt").write_text("v1.3.2\n", encoding="utf-8")
        (addon / ".pkgmeta").write_text(self.PKGMETA.replace("LegacyForever", "KilnForever"), encoding="utf-8")
        (addon / "KilnForever.toc").write_text(self.TOC, encoding="utf-8")
        (root / "CHANGELOG.md").write_text(self.CHANGELOG, encoding="utf-8")

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sync.bump_pin(root, "v1.4.0", self.DAY), "v1.3.2")

        self.assertIn("v1.4.0/ForeverCore-v1.4.0-forever.zip", (addon / ".pkgmeta").read_text(encoding="utf-8"))
        self.assertIn("## X-Forever-Core: v1.4.0\n", (addon / "KilnForever.toc").read_text(encoding="utf-8"))
        self.assertIn(sync.SYNC_BULLET, (root / "CHANGELOG.md").read_text(encoding="utf-8"))


class RemoteReleaseTest(unittest.TestCase):
    """The facts the changelog decision reads, all from the consumer's remote rather than the shallow clone."""

    def test_a_tag_is_checked_on_origin(self):
        calls = []

        def fake_git(root, *args, check=True):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "abc\trefs/tags/v1.9.0\n", "")

        with mock.patch.object(sync, "git", side_effect=fake_git):
            self.assertTrue(sync.remote_tag_exists(Path("/tmp/legacy-forever"), "v1.9.0"))
        self.assertIn("ls-remote", calls[0])
        self.assertIn("origin", calls[0])
        self.assertIn("refs/tags/v1.9.0", calls[0])

    def test_the_newest_release_tag_is_compared_numerically(self):
        output = "a\trefs/tags/v1.9.0\nb\trefs/tags/v1.10.0\nc\trefs/tags/not-a-release\n"

        def fake_git(root, *args, check=True):
            return subprocess.CompletedProcess(args, 0, output, "")

        with mock.patch.object(sync, "git", side_effect=fake_git):
            self.assertEqual(sync.latest_release_tag(Path("/tmp/legacy-forever")), "v1.10.0")

    def test_the_released_bundle_is_read_from_that_tags_pkgmeta_external(self):
        pkgmeta = (
            "package-as: LegacyForever\n\n"
            "externals:\n"
            "  ForeverCore: https://github.com/cjber/forever-core/releases/download/"
            "v1.3.2/ForeverCore-v1.3.2-forever.zip\n"
        )

        def fake_git(root, *args, check=True):
            if args[0] == "fetch":
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[0] == "show" and args[1] == "v1.2.4:.pkgmeta":
                return subprocess.CompletedProcess(args, 0, pkgmeta, "")
            return subprocess.CompletedProcess(args, 1, "", "missing")

        with mock.patch.object(sync, "git", side_effect=fake_git):
            self.assertEqual(sync.released_core_tag(Path("/tmp/legacy-forever"), "v1.2.4"), "v1.3.2")

    def test_a_release_without_a_pkgmeta_external_uses_its_toc_field(self):
        pkgmeta = "package-as: LegacyForever\n"
        toc = "## Interface: 16001\n## X-Forever-Core: v1.3.2\n## Title: Legacy Forever\n"

        def fake_git(root, *args, check=True):
            if args[0] == "fetch":
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[0] == "show":
                text = {"v1.2.4:.pkgmeta": pkgmeta, "v1.2.4:LegacyForever.toc": toc}.get(args[1])
                return subprocess.CompletedProcess(args, 0 if text else 1, text or "", "")
            return subprocess.CompletedProcess(args, 1, "", "missing")

        with mock.patch.object(sync, "git", side_effect=fake_git):
            self.assertEqual(sync.released_core_tag(Path("/tmp/legacy-forever"), "v1.2.4"), "v1.3.2")


class BodyTest(unittest.TestCase):
    def test_body_names_the_core_commit_and_every_file(self):
        files = ("UI/TrackerHost.lua", "tools/forever_tools/sync.py")
        body = sync.pr_body("abc123", files)
        self.assertIn("https://github.com/cjber/forever-core/commit/abc123", body)
        for path in files:
            self.assertIn(f"`{path}`", body)

    def test_body_names_the_release_gate_when_the_release_workflow_changes(self):
        body = sync.pr_body("abc123", ("tools/forever-core.txt", sync.RELEASE_WORKFLOW))
        self.assertIn("inserts the ForeverCore pin gate directly above the packager", body)
        self.assertNotIn("inserts the ForeverCore pin gate", sync.pr_body("abc123", ("tools/forever-core.txt",)))

    def test_body_names_the_pin_bump(self):
        body = sync.pr_body("abc123", ("tools/forever-core.txt",), ("v1.3.2", "v1.4.0"))
        self.assertIn(
            "Moves the ForeverCore pin from v1.3.2 to v1.4.0, so this addon's CI runs against the latest release.", body
        )
        self.assertNotIn("Moves the ForeverCore pin", sync.pr_body("abc123", ("tools/forever-core.txt",)))


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
