"""Tests for tools/smoke_queue.py: which commit each repository would release, and what it smokes, with no client."""

import contextlib
import io
import json
import sys
import unittest
from unittest import mock

import smoke_queue as queue

SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER = "fedcba9876543210fedcba9876543210fedcba98"


class QueueTest(unittest.TestCase):
    def run_queue(self, heads, states, codes=(0,), argv=()):
        """Run the queue over `heads` (repo to commit) with `states` (repo to headless-smoke state), no network."""
        smoked = []

        def smoke(repo, commit):
            smoked.append((repo, commit))
            return codes[min(len(smoked) - 1, len(codes) - 1)]

        out = io.StringIO()
        with (
            mock.patch.object(queue, "discover_tooling_repos", return_value=set()),
            mock.patch.object(queue, "consumer_repos", return_value=sorted(r for r in heads if r != "forever-core")),
            mock.patch.object(queue, "main_head", side_effect=lambda repo: heads[repo]),
            mock.patch.object(queue, "smoke_status", side_effect=lambda repo, sha: states[repo]),
            mock.patch.object(queue, "smoke", side_effect=smoke) as run,
            contextlib.redirect_stdout(out),
        ):
            code = queue.main(list(argv))
        return code, out.getvalue(), smoked, run

    def test_core_itself_is_smoked_first_then_the_consumers(self):
        heads = {"forever-core": SHA, "legacy-forever": OTHER}
        states = {"forever-core": "missing", "legacy-forever": "missing"}
        code, printed, smoked, _run = self.run_queue(heads, states)
        self.assertEqual(code, 0)
        self.assertEqual(smoked, [("forever-core", SHA), ("legacy-forever", OTHER)])
        self.assertIn(f"forever-core: {SHA[:7]} is smoked", printed)

    def test_a_commit_that_already_has_a_status_is_left_alone(self):
        heads = {"forever-core": SHA, "legacy-forever": OTHER}
        states = {"forever-core": "success", "legacy-forever": "failure"}
        code, printed, smoked, _run = self.run_queue(heads, states)
        self.assertEqual(code, 0)
        self.assertEqual(smoked, [])
        self.assertIn(f"forever-core: {SHA[:7]} already has success headless-smoke", printed)
        self.assertIn("legacy-forever: fedcba9 already has failure headless-smoke", printed)

    def test_a_client_in_use_stops_the_run_and_leaves_the_rest_for_the_next_timer(self):
        heads = {"forever-core": SHA, "legacy-forever": OTHER}
        states = {"forever-core": "missing", "legacy-forever": "missing"}
        code, printed, smoked, _run = self.run_queue(heads, states, codes=(3,))
        self.assertEqual(code, 0)
        self.assertEqual(smoked, [("forever-core", SHA)])
        self.assertIn("the client is in use; stopping until the next run", printed)

    def test_a_recorded_failure_does_not_stop_the_next_repository(self):
        heads = {"forever-core": SHA, "legacy-forever": OTHER}
        states = {"forever-core": "missing", "legacy-forever": "missing"}
        code, printed, smoked, _run = self.run_queue(heads, states, codes=(1, 0))
        self.assertEqual(code, 1)
        self.assertEqual(len(smoked), 2)
        self.assertIn(f"forever-core: {SHA[:7]} recorded a failure", printed)
        self.assertIn(f"legacy-forever: {OTHER[:7]} is smoked", printed)

    def test_a_smoke_that_could_not_run_is_named_and_the_queue_moves_on(self):
        heads = {"forever-core": SHA, "legacy-forever": OTHER}
        states = {"forever-core": "missing", "legacy-forever": "missing"}
        code, printed, smoked, _run = self.run_queue(heads, states, codes=(2, 0))
        self.assertEqual(code, 1)
        self.assertEqual(len(smoked), 2)
        self.assertIn(f"forever-core: {SHA[:7]} did not smoke (exit 2)", printed)
        self.assertIn(f"legacy-forever: {OTHER[:7]} is smoked", printed)

    def test_a_dry_run_names_every_commit_and_smokes_nothing(self):
        heads = {"forever-core": SHA}
        code, printed, smoked, run = self.run_queue(heads, {"forever-core": "missing"}, argv=("--dry-run",))
        self.assertEqual(code, 0)
        self.assertEqual(smoked, [])
        run.assert_not_called()
        self.assertIn(f"forever-core: would smoke {SHA[:7]}", printed)

    def test_a_repository_that_cannot_be_read_is_named_and_the_run_goes_red(self):
        out = io.StringIO()
        with (
            mock.patch.object(queue, "discover_tooling_repos", return_value=set()),
            mock.patch.object(queue, "consumer_repos", return_value=[]),
            mock.patch.object(queue, "main_head", side_effect=queue.SyncError("gh: Not Found (HTTP 404)")),
            mock.patch.object(queue, "smoke") as run,
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(queue.main([]), 1)
        run.assert_not_called()
        self.assertIn("forever-core: failed: gh: Not Found (HTTP 404)", out.getvalue())

    def test_a_failed_discovery_fails_the_run(self):
        out = io.StringIO()
        with (
            mock.patch.object(queue, "discover_tooling_repos", side_effect=queue.SyncError("no token access")),
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(queue.main([]), 1)
        self.assertIn("::error::no token access", out.getvalue())

    def test_the_smoke_is_the_client_tools_own_verb_for_that_commit(self):
        with mock.patch.object(queue.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            self.assertEqual(queue.smoke("legacy-forever", SHA), 0)
        self.assertEqual(
            run.call_args.args[0],
            [sys.executable, str(queue.CLIENT), "smoke", "--repo", "legacy-forever", "--ref", SHA],
        )

    def test_a_status_read_that_is_not_json_fails_the_repository(self):
        out = io.StringIO()
        with (
            mock.patch.object(queue, "discover_tooling_repos", return_value=set()),
            mock.patch.object(queue, "consumer_repos", return_value=[]),
            mock.patch.object(queue, "main_head", return_value=SHA),
            mock.patch.object(queue, "smoke_status", side_effect=json.JSONDecodeError("bad", "", 0)),
            mock.patch.object(queue, "smoke") as run,
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(queue.main([]), 1)
        run.assert_not_called()
        self.assertIn("forever-core: failed:", out.getvalue())


if __name__ == "__main__":
    unittest.main()
