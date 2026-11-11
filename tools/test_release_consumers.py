"""Tests for tools/release_consumers.py: the release decision and its dispatch, with no network."""

import contextlib
import io
import os
import subprocess
import unittest
from unittest import mock

import release_consumers as release

SHA = "0123456789abcdef0123456789abcdef01234567"
SYNC_ENTRY = (
    "# Changelog\n\n"
    "## [Unreleased]\n\n"
    "## [1.4.3] - 2026-11-11\n\n"
    "<!-- forever-core-sync -->\n\n"
    "- Ships with the same shared code as your other Forever addons, so they keep working together.\n\n"
    "## [1.4.2] - 2026-11-10\n\n"
    "- A hand-written entry.\n"
)


def runs(*items):
    return {"workflow_runs": list(items)}


def ci_run(status, conclusion, sha=SHA, branch="main", started="2026-11-11T10:00:00Z"):
    return {
        "head_sha": sha,
        "head_branch": branch,
        "status": status,
        "conclusion": conclusion,
        "run_started_at": started,
    }


def release_run(status, conclusion, sha=SHA):
    return {"head_sha": sha, "status": status, "conclusion": conclusion}


class EntryTest(unittest.TestCase):
    def test_the_newest_release_is_found_with_its_body(self):
        version, body = release.newest_entry(SYNC_ENTRY)
        self.assertEqual(version, "1.4.3")
        self.assertIn(release.MARKER, body)
        self.assertNotIn("A hand-written entry", body)

    def test_the_newest_release_is_compared_numerically(self):
        text = "## [1.9.0] - 2026-11-01\n\n- Older.\n\n## [1.10.0] - 2026-11-02\n\n- Newer.\n"
        self.assertEqual(release.newest_entry(text)[0], "1.10.0")

    def test_a_changelog_without_a_release_heading_has_no_entry(self):
        self.assertIsNone(release.newest_entry("## [Unreleased]\n\n- Notes only.\n"))


class CiStateTest(unittest.TestCase):
    def test_a_successful_push_run_on_main_is_the_green_state(self):
        self.assertEqual(release.ci_state(runs(ci_run("completed", "success")), SHA), "completed/success")

    def test_a_running_run_names_its_status(self):
        self.assertEqual(release.ci_state(runs(ci_run("in_progress", None)), SHA), "in_progress")

    def test_no_run_for_the_sha_is_none(self):
        self.assertEqual(release.ci_state(runs(ci_run("completed", "success", sha="f" * 40)), SHA), "none")

    def test_a_run_on_another_branch_does_not_count(self):
        self.assertEqual(release.ci_state(runs(ci_run("completed", "success", branch="feature")), SHA), "none")

    def test_the_newest_run_decides(self):
        text = runs(
            ci_run("completed", "failure", started="2026-11-11T12:00:00Z"),
            ci_run("completed", "success", started="2026-11-11T10:00:00Z"),
        )
        self.assertEqual(release.ci_state(text, SHA), "completed/failure")


class PendingReleaseTest(unittest.TestCase):
    def test_a_queued_or_running_release_is_pending(self):
        self.assertTrue(release.has_pending_release(runs({"status": "queued"})))
        self.assertTrue(release.has_pending_release(runs({"status": "in_progress"})))

    def test_finished_releases_are_not_pending(self):
        self.assertFalse(release.has_pending_release(runs({"status": "completed"})))

    def test_no_runs_is_not_pending(self):
        self.assertFalse(release.has_pending_release(runs()))


class FailedReleaseTest(unittest.TestCase):
    """A release that already failed at the head commit is never dispatched a second time."""

    def test_a_completed_failure_at_the_head_is_failed(self):
        self.assertTrue(release.has_failed_release(runs(release_run("completed", "failure")), SHA))
        self.assertTrue(release.has_failed_release(runs(release_run("completed", "cancelled")), SHA))

    def test_a_completed_success_at_the_head_is_not_failed(self):
        self.assertFalse(release.has_failed_release(runs(release_run("completed", "success")), SHA))

    def test_a_failure_at_another_commit_is_not_failed(self):
        self.assertFalse(release.has_failed_release(runs(release_run("completed", "failure", sha="f" * 40)), SHA))

    def test_a_running_release_is_not_failed(self):
        self.assertFalse(release.has_failed_release(runs(release_run("in_progress", None)), SHA))

    def test_no_runs_is_not_failed(self):
        self.assertFalse(release.has_failed_release(runs(), SHA))


class DecideTest(unittest.TestCase):
    """The four conditions, and nothing else, release a consumer."""

    def decide(
        self,
        changelog=SYNC_ENTRY,
        head=SHA,
        tag_exists=False,
        pending=False,
        state="completed/success",
        failed=False,
    ):
        return release.decide(changelog, head, tag_exists, pending, state, failed)

    def test_a_marked_entry_with_a_missing_tag_idle_release_and_green_ci_is_released(self):
        decision = self.decide()
        self.assertTrue(decision.release)
        self.assertEqual((decision.version, decision.commit), ("1.4.3", SHA))

    def test_a_changelog_is_required(self):
        self.assertEqual(self.decide(changelog=None).reason, "main has no CHANGELOG.md")

    def test_a_changelog_without_a_release_entry_waits(self):
        self.assertFalse(self.decide(changelog="## [Unreleased]\n").release)

    def test_an_unmarked_newest_entry_waits(self):
        text = "## [Unreleased]\n\n## [1.4.3] - 2026-11-11\n\n- A hand-written entry.\n"
        decision = self.decide(changelog=text)
        self.assertFalse(decision.release)
        self.assertIn("the newest entry, v1.4.3, is not a ForeverCore sync", decision.reason)

    def test_an_existing_tag_waits(self):
        decision = self.decide(tag_exists=True)
        self.assertFalse(decision.release)
        self.assertIn("v1.4.3 is already released", decision.reason)

    def test_a_queued_or_running_release_waits(self):
        decision = self.decide(pending=True)
        self.assertFalse(decision.release)
        self.assertIn("release.yml is queued or running", decision.reason)

    def test_missing_ci_waits(self):
        decision = self.decide(state="none")
        self.assertFalse(decision.release)
        self.assertIn("ci.yml on main's head 0123456 is none", decision.reason)

    def test_failed_ci_waits(self):
        self.assertFalse(self.decide(state="completed/failure").release)

    def test_a_release_that_failed_at_the_head_is_not_dispatched_again(self):
        decision = self.decide(failed=True)
        self.assertFalse(decision.release)
        self.assertTrue(decision.failed)
        self.assertEqual(decision.reason, "release.yml failed at 0123456; fix it and dispatch by hand")

    def test_a_missing_head_waits(self):
        decision = self.decide(head=None)
        self.assertFalse(decision.release)
        self.assertIn("main has no head commit", decision.reason)


class PlanTest(unittest.TestCase):
    def test_the_changelog_is_read_at_the_head_that_is_released(self):
        with (
            mock.patch.object(release, "main_head", return_value=SHA),
            mock.patch.object(release, "read_changelog", return_value=SYNC_ENTRY) as read,
            mock.patch.object(release, "tag_exists", return_value=False),
            mock.patch.object(release, "release_runs", return_value=runs({"status": "completed"})),
            mock.patch.object(release, "ci_runs", return_value=runs(ci_run("completed", "success"))),
        ):
            decision = release.plan("legacy-forever")
        read.assert_called_once_with("legacy-forever", SHA)
        self.assertTrue(decision.release)
        self.assertEqual(decision.commit, SHA)

    def test_an_unmarked_entry_reads_no_workflow_state(self):
        text = "## [Unreleased]\n\n## [1.4.3] - 2026-11-11\n\n- A hand-written entry.\n"
        with (
            mock.patch.object(release, "main_head", return_value=SHA),
            mock.patch.object(release, "read_changelog", return_value=text),
            mock.patch.object(release, "tag_exists") as tag,
            mock.patch.object(release, "release_runs") as pending,
            mock.patch.object(release, "ci_runs") as ci,
        ):
            decision = release.plan("legacy-forever")
        self.assertFalse(decision.release)
        tag.assert_not_called()
        pending.assert_not_called()
        ci.assert_not_called()

    def test_an_existing_tag_is_checked_before_the_workflows(self):
        with (
            mock.patch.object(release, "main_head", return_value=SHA),
            mock.patch.object(release, "read_changelog", return_value=SYNC_ENTRY),
            mock.patch.object(release, "tag_exists", return_value=True),
            mock.patch.object(release, "release_runs") as pending,
            mock.patch.object(release, "ci_runs") as ci,
        ):
            decision = release.plan("legacy-forever")
        self.assertFalse(decision.release)
        pending.assert_not_called()
        ci.assert_not_called()

    def test_a_pending_release_is_checked_before_ci(self):
        with (
            mock.patch.object(release, "main_head", return_value=SHA),
            mock.patch.object(release, "read_changelog", return_value=SYNC_ENTRY),
            mock.patch.object(release, "tag_exists", return_value=False),
            mock.patch.object(release, "release_runs", return_value=runs({"status": "in_progress"})),
            mock.patch.object(release, "ci_runs") as ci,
        ):
            decision = release.plan("legacy-forever")
        self.assertFalse(decision.release)
        ci.assert_not_called()

    def test_a_failed_release_at_the_head_reads_no_ci_and_asks_for_a_hand_dispatch(self):
        with (
            mock.patch.object(release, "main_head", return_value=SHA),
            mock.patch.object(release, "read_changelog", return_value=SYNC_ENTRY),
            mock.patch.object(release, "tag_exists", return_value=False),
            mock.patch.object(release, "release_runs", return_value=runs(release_run("completed", "failure"))),
            mock.patch.object(release, "ci_runs") as ci,
        ):
            decision = release.plan("legacy-forever")
        self.assertFalse(decision.release)
        self.assertTrue(decision.failed)
        self.assertIn("release.yml failed at 0123456", decision.reason)
        ci.assert_not_called()


class MainTest(unittest.TestCase):
    def test_a_missing_token_is_a_green_notice(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"GH_TOKEN": ""}):
            with contextlib.redirect_stdout(out):
                self.assertEqual(release.main(), 0)
        self.assertIn("CONSUMER_SYNC_TOKEN is not set", out.getvalue())

    def test_one_line_per_consumer_and_a_dispatch_for_the_ready_one(self):
        decisions = {
            "legacy-forever": release.Decision(reason="v1.4.3 is already released"),
            "skillup-forever": release.Decision("1.4.3", SHA, f"releases v1.4.3 at {SHA}"),
        }
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": "token"}),
            mock.patch.object(release, "consumer_repos", return_value=sorted(decisions)),
            mock.patch.object(release, "discover_tooling_repos", return_value=set()),
            mock.patch.object(release, "plan", side_effect=lambda repo: decisions[repo]),
            mock.patch.object(release, "dispatch") as dispatched,
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(release.main(), 0)

        dispatched.assert_called_once_with("skillup-forever", "1.4.3", SHA)
        self.assertIn("legacy-forever: waiting: v1.4.3 is already released", out.getvalue())
        self.assertIn(f"skillup-forever: dispatched release.yml for v1.4.3 at {SHA}", out.getvalue())

    def test_a_failed_release_is_reported_and_fails_the_run_without_a_dispatch(self):
        detail = "release.yml failed at 0123456; fix it and dispatch by hand"
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": "token"}),
            mock.patch.object(release, "consumer_repos", return_value=["legacy-forever"]),
            mock.patch.object(release, "discover_tooling_repos", return_value=set()),
            mock.patch.object(release, "plan", return_value=release.Decision(reason=detail, failed=True)),
            mock.patch.object(release, "dispatch") as dispatched,
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(release.main(), 1)
        dispatched.assert_not_called()
        self.assertIn(f"legacy-forever: failed: {detail}", out.getvalue())

    def test_a_failed_read_names_the_consumer_and_fails_the_run(self):
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": "token"}),
            mock.patch.object(release, "consumer_repos", return_value=["legacy-forever"]),
            mock.patch.object(release, "discover_tooling_repos", return_value=set()),
            mock.patch.object(release, "plan", side_effect=release.SyncError("gh: Not Found (HTTP 404)")),
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(release.main(), 1)
        self.assertIn("legacy-forever: failed: gh: Not Found (HTTP 404)", out.getvalue())

    def test_a_failed_dispatch_names_the_consumer_and_fails_the_run(self):
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": "token"}),
            mock.patch.object(release, "consumer_repos", return_value=["legacy-forever"]),
            mock.patch.object(release, "discover_tooling_repos", return_value=set()),
            mock.patch.object(release, "plan", return_value=release.Decision("1.4.3", SHA)),
            mock.patch.object(release, "dispatch", side_effect=release.SyncError("gh: Resource not accessible")),
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(release.main(), 1)
        self.assertIn("legacy-forever: failed: gh: Resource not accessible", out.getvalue())

    def test_a_forbidden_dispatch_names_the_permission_and_continues(self):
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": "token"}),
            mock.patch.object(release, "consumer_repos", return_value=["legacy-forever", "skillup-forever"]),
            mock.patch.object(release, "discover_tooling_repos", return_value=set()),
            mock.patch.object(release, "plan", return_value=release.Decision("1.4.3", SHA)),
            mock.patch.object(
                release,
                "dispatch",
                side_effect=[release.DispatchForbidden("gh: Forbidden (HTTP 403)"), None],
            ) as dispatched,
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(release.main(), 1)
        self.assertEqual(dispatched.call_count, 2)
        self.assertIn(
            "::error::CONSUMER_SYNC_TOKEN lacks Actions: Read and write on cjber/legacy-forever",
            out.getvalue(),
        )
        self.assertIn(f"skillup-forever: dispatched release.yml for v1.4.3 at {SHA}", out.getvalue())

    def test_a_403_dispatch_is_forbidden(self):
        with mock.patch.object(release, "gh", side_effect=release.SyncError("gh: Forbidden (HTTP 403)")):
            with self.assertRaises(release.DispatchForbidden):
                release.dispatch("legacy-forever", "1.4.3", SHA)

    def test_a_failed_discovery_fails_the_run(self):
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": "token"}),
            mock.patch.object(release, "discover_tooling_repos", side_effect=release.SyncError("no token access")),
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(release.main(), 1)
        self.assertIn("::error::no token access", out.getvalue())


class ApiTest(unittest.TestCase):
    def test_a_missing_changelog_is_none_and_another_failure_is_an_error(self):
        missing = subprocess.CompletedProcess([], 1, "", "gh: Not Found (HTTP 404)")
        broken = subprocess.CompletedProcess([], 1, "", "gh: Server Error (HTTP 502)")
        with mock.patch.object(release, "gh", return_value=missing):
            self.assertIsNone(release.read_changelog("legacy-forever", SHA))
        with mock.patch.object(release, "gh", return_value=broken):
            with self.assertRaises(release.SyncError):
                release.read_changelog("legacy-forever", SHA)

    def test_the_changelog_request_names_the_commit(self):
        calls = []

        def fake_gh(*args, check=True):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "# Changelog\n", "")

        with mock.patch.object(release, "gh", side_effect=fake_gh):
            self.assertEqual(release.read_changelog("legacy-forever", SHA), "# Changelog\n")
        self.assertIn(f"repos/cjber/legacy-forever/contents/CHANGELOG.md?ref={SHA}", calls[0])

    def test_a_missing_tag_is_absent_and_another_failure_is_an_error(self):
        missing = subprocess.CompletedProcess([], 1, "", "gh: Not Found (HTTP 404)")
        broken = subprocess.CompletedProcess([], 1, "", "gh: Bad credentials (HTTP 401)")
        with mock.patch.object(release, "gh", return_value=missing):
            self.assertFalse(release.tag_exists("legacy-forever", "v1.4.3"))
        with mock.patch.object(release, "gh", return_value=broken):
            with self.assertRaises(release.SyncError):
                release.tag_exists("legacy-forever", "v1.4.3")

    def test_an_existing_tag_is_present(self):
        with mock.patch.object(release, "gh", return_value=subprocess.CompletedProcess([], 0, "{}", "")):
            self.assertTrue(release.tag_exists("legacy-forever", "v1.4.3"))

    def test_the_dispatch_names_the_workflow_version_and_commit(self):
        calls = []

        def fake_gh(*args, check=True):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with mock.patch.object(release, "gh", side_effect=fake_gh):
            release.dispatch("legacy-forever", "1.4.3", SHA)
        self.assertEqual(
            calls[0],
            (
                "workflow",
                "run",
                "release.yml",
                "-R",
                "cjber/legacy-forever",
                "--ref",
                "main",
                "-f",
                "version=1.4.3",
                "-f",
                f"commit={SHA}",
            ),
        )

    def test_workflow_runs_are_read_as_json(self):
        requests = []

        def fake_api_json(path):
            requests.append(path)
            return {"workflow_runs": []}

        with mock.patch.object(release, "api_json", side_effect=fake_api_json):
            self.assertEqual(release.release_runs("legacy-forever"), {"workflow_runs": []})
            self.assertEqual(release.ci_runs("legacy-forever", SHA), {"workflow_runs": []})
        self.assertEqual(
            requests,
            [
                "repos/cjber/legacy-forever/actions/workflows/release.yml/runs?per_page=20",
                f"repos/cjber/legacy-forever/actions/workflows/ci.yml/runs?head_sha={SHA}&event=push&per_page=100",
            ],
        )

    def test_main_head_is_the_full_sha(self):
        with mock.patch.object(release, "api_json", return_value={"sha": SHA}):
            self.assertEqual(release.main_head("legacy-forever"), SHA)


if __name__ == "__main__":
    unittest.main()
