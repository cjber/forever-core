"""Tests for tools/release_consumers.py: the release decision and its dispatch, with no network."""

import contextlib
import io
import os
import subprocess
import tarfile
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
        "id": 1,
        "head_sha": sha,
        "head_branch": branch,
        "status": status,
        "conclusion": conclusion,
        "run_started_at": started,
    }


def ci_job(name, conclusion="success", status="completed"):
    return {"name": name, "status": status, "conclusion": conclusion}


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

    def test_a_success_beside_a_failed_duplicate_is_not_failed(self):
        # A tag push also fires release.yml once; the dispatch duplicate can fail while the tag's own run shipped.
        shipped = {**release_run("completed", "success"), "run_started_at": "2026-11-22T03:20:00Z"}
        duplicate = {**release_run("completed", "failure"), "run_started_at": "2026-11-22T03:26:00Z"}
        self.assertFalse(release.has_failed_release(runs(shipped, duplicate), SHA))

    def test_a_cancelled_run_beside_a_success_is_not_failed(self):
        shipped = {**release_run("completed", "success"), "run_started_at": "2026-11-22T03:20:00Z"}
        cancelled = {**release_run("completed", "cancelled"), "run_started_at": "2026-11-22T03:27:00Z"}
        self.assertFalse(release.has_failed_release(runs(shipped, cancelled), SHA))

    def test_a_failure_rerun_to_success_is_not_failed(self):
        failed = {**release_run("completed", "failure"), "run_started_at": "2026-11-11T10:00:00Z"}
        passed = {**release_run("completed", "success"), "run_started_at": "2026-11-11T11:00:00Z"}
        self.assertFalse(release.has_failed_release(runs(failed, passed), SHA))

    def test_no_runs_is_not_failed(self):
        self.assertFalse(release.has_failed_release(runs(), SHA))


class DecideTest(unittest.TestCase):
    """The release conditions, and nothing else, release a consumer."""

    def decide(
        self,
        changelog=SYNC_ENTRY,
        head=SHA,
        tag_exists=False,
        pending=False,
        state="completed/success",
        failed=False,
        smoke="success",
        changes_pending=False,
    ):
        return release.decide(changelog, head, tag_exists, pending, state, failed, smoke, changes_pending)

    def test_a_marked_entry_with_a_missing_tag_idle_release_and_green_ci_is_released(self):
        decision = self.decide()
        self.assertTrue(decision.release)
        self.assertEqual((decision.version, decision.commit), ("1.4.3", SHA))

    def test_notes_merged_above_the_marked_entry_hold_it_for_the_addons_own_release(self):
        text = SYNC_ENTRY.replace(
            "## [Unreleased]\n\n", "## [Unreleased]\n\n- A note merged after the sync PR opened.\n\n"
        )
        decision = self.decide(changelog=text)
        self.assertFalse(decision.release)
        self.assertFalse(decision.failed)
        self.assertEqual(decision.reason, "unreleased notes sit above v1.4.3; its own release ships them")

    def test_a_blank_unreleased_section_still_releases_the_marked_entry(self):
        text = SYNC_ENTRY.replace("## [Unreleased]\n\n", "## [Unreleased]\n\n\n")
        self.assertTrue(self.decide(changelog=text).release)

    def test_pending_fragments_wait_for_their_own_release(self):
        decision = self.decide(changes_pending=True)
        self.assertFalse(decision.release)
        self.assertEqual(decision.reason, "change notes in changes/ sit above v1.4.3; its own release ships them")

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

    def test_a_commit_without_a_green_smoke_waits_and_is_not_failed(self):
        for smoke in ("missing", "pending", "failure"):
            with self.subTest(smoke=smoke):
                decision = self.decide(smoke=smoke)
                self.assertFalse(decision.release)
                self.assertFalse(decision.failed)
                self.assertEqual(decision.reason, f"waiting for headless-smoke on 0123456, which is {smoke}")

    def test_a_green_smoke_releases_the_commit_it_names(self):
        decision = self.decide(smoke="success")
        self.assertTrue(decision.release)
        self.assertEqual(decision.commit, SHA)


class SmokeStatusTest(unittest.TestCase):
    """The pre-release status, read the way the release gate reads it."""

    def status(self, context="headless-smoke", state="success"):
        return {"context": context, "state": state}

    def test_the_newest_smoke_status_is_the_state(self):
        newest_first = [self.status(state="success"), self.status(state="failure"), self.status("ci", "failure")]
        with mock.patch.object(release, "api_json", return_value=newest_first):
            self.assertEqual(release.smoke_status("legacy-forever", SHA), "success")

    def test_no_smoke_status_is_missing(self):
        with mock.patch.object(release, "api_json", return_value=[self.status("ci", "failure")]):
            self.assertEqual(release.smoke_status("legacy-forever", SHA), "missing")

    def test_the_read_names_the_commit(self):
        requests = []
        with mock.patch.object(release, "api_json", side_effect=lambda path: requests.append(path) or []):
            release.smoke_status("legacy-forever", SHA)
        self.assertEqual(requests, [f"repos/cjber/legacy-forever/commits/{SHA}/statuses"])


class BuildEvidenceTest(unittest.TestCase):
    """A green smoke, or else a committed visual proof that verifies over the commit's own tree."""

    def test_a_green_smoke_reads_no_proof(self):
        with (
            mock.patch.object(release, "smoke_status", return_value="success"),
            mock.patch.object(release, "proof_covers") as covers,
        ):
            self.assertEqual(release.build_evidence("legacy-forever", SHA), "success")
        covers.assert_not_called()

    def test_a_proof_stands_in_for_a_missing_or_failed_smoke(self):
        for state in ("missing", "failure"):
            with (
                self.subTest(state),
                mock.patch.object(release, "smoke_status", return_value=state),
                mock.patch.object(release, "proof_covers", return_value=True),
            ):
                self.assertEqual(release.build_evidence("legacy-forever", SHA), "proof")
        with (
            mock.patch.object(release, "smoke_status", return_value="missing"),
            mock.patch.object(release, "proof_covers", return_value=False),
        ):
            self.assertEqual(release.build_evidence("legacy-forever", SHA), "missing")

    def test_a_commit_without_a_proof_downloads_nothing(self):
        with (
            mock.patch.object(release, "read_file", return_value=None) as read,
            mock.patch.object(release.subprocess, "run") as download,
        ):
            self.assertFalse(release.proof_covers("legacy-forever", SHA))
        read.assert_called_once_with("legacy-forever", ".visual-proof.json", SHA)
        download.assert_not_called()

    def tarball(self, files: dict[str, str], gate: dict[str, str] | None = None) -> bytes:
        """The commit's tarball the way GitHub serves it: one top folder named after the repository and commit.

        It vendors core's own proof gate unless `gate` replaces some of its files (None as a value drops one).
        """
        vendored = {
            f"tools/forever_tools/{name}": (release.TOOLING / "forever_tools" / name).read_text()
            for name in release.PROOF_GATE
        }
        vendored.update({f"tools/forever_tools/{name}": text for name, text in (gate or {}).items()})
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:gz") as bundle:
            for name, text in {**vendored, **files}.items():
                if text is None:
                    continue
                data = text.encode()
                info = tarfile.TarInfo(f"cjber-legacy-forever-0123456/{name}")
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
        return stream.getvalue()

    def test_the_proof_is_checked_over_the_commits_extracted_tree(self):
        seen = []

        def refusal(root):
            seen.append((root.name, (root / "LegacyForever.toc").read_text()))
            return None

        answer = subprocess.CompletedProcess([], 0, self.tarball({"LegacyForever.toc": "## Interface: 16001\n"}), b"")
        with (
            mock.patch.object(release, "read_file", return_value="{}"),
            mock.patch.object(release.subprocess, "run", return_value=answer) as download,
            mock.patch.object(release.release_check, "proof_refusal", side_effect=refusal),
        ):
            self.assertTrue(release.proof_covers("legacy-forever", SHA))
        self.assertEqual(download.call_args.args[0], ["gh", "api", f"repos/cjber/legacy-forever/tarball/{SHA}"])
        self.assertEqual(seen, [("cjber-legacy-forever-0123456", "## Interface: 16001\n")])

    def test_a_proof_that_does_not_verify_does_not_cover(self):
        answer = subprocess.CompletedProcess([], 0, self.tarball({"a.lua": ""}), b"")
        with (
            mock.patch.object(release, "read_file", return_value="{}"),
            mock.patch.object(release.subprocess, "run", return_value=answer),
            mock.patch.object(release.release_check, "proof_refusal", return_value="visual proof selftest failed"),
        ):
            self.assertFalse(release.proof_covers("legacy-forever", SHA))

    def test_a_consumer_vendoring_another_gate_waits_for_its_smoke(self):
        for gate in ({"release_check.py": "# predates proofs\n"}, {"visual_proof.py": None}):
            answer = subprocess.CompletedProcess([], 0, self.tarball({"a.lua": ""}, gate), b"")
            with (
                self.subTest(gate),
                mock.patch.object(release, "read_file", return_value="{}"),
                mock.patch.object(release.subprocess, "run", return_value=answer),
                mock.patch.object(release.release_check, "proof_refusal", return_value=None) as refusal,
            ):
                self.assertFalse(release.proof_covers("legacy-forever", SHA))
            refusal.assert_not_called()

    def test_a_failed_download_is_an_error(self):
        answer = subprocess.CompletedProcess([], 1, b"", b"HTTP 502")
        with (
            mock.patch.object(release, "read_file", return_value="{}"),
            mock.patch.object(release.subprocess, "run", return_value=answer),
            self.assertRaisesRegex(release.SyncError, "could not download legacy-forever at 0123456: HTTP 502"),
        ):
            release.proof_covers("legacy-forever", SHA)

    def test_a_proven_head_is_released(self):
        decision = release.decide(SYNC_ENTRY, SHA, False, False, "completed/success", smoke="proof")
        self.assertTrue(decision.release)


class PlanTest(unittest.TestCase):
    def setUp(self):
        fragments = mock.patch.object(release, "has_change_fragments", return_value=False)
        self.fragments = fragments.start()
        self.addCleanup(fragments.stop)

    def plan_with_ci_jobs(self, jobs, run=None):
        run = run or ci_run("completed", "failure")
        with (
            mock.patch.object(release, "main_head", return_value=SHA),
            mock.patch.object(release, "read_changelog", return_value=SYNC_ENTRY),
            mock.patch.object(release, "tag_exists", return_value=False),
            mock.patch.object(release, "release_runs", return_value=runs({"status": "completed"})),
            mock.patch.object(release, "ci_runs", return_value=runs(run)),
            mock.patch.object(release, "ci_jobs", return_value={"jobs": jobs}) as jobs_read,
            mock.patch.object(release, "build_evidence", return_value="success"),
        ):
            decision = release.plan("legacy-forever")
        return decision, jobs_read

    def test_a_failed_run_whose_only_failed_job_is_visual_proof_releases(self):
        jobs = [ci_job("test"), ci_job("visual-proof", "failure")]
        decision, jobs_read = self.plan_with_ci_jobs(jobs)
        self.assertTrue(decision.release)
        self.assertEqual(decision.commit, SHA)
        self.assertTrue(decision.skip_visual_proof)
        jobs_read.assert_called_once_with("legacy-forever", 1)

    def test_visual_proof_beside_another_failed_job_holds_the_release(self):
        jobs = [ci_job("visual-proof", "failure"), ci_job("test", "failure")]
        decision, _ = self.plan_with_ci_jobs(jobs)
        self.assertFalse(decision.release)
        self.assertFalse(decision.failed)
        self.assertIn("ci.yml on main's head 0123456 is completed/failure", decision.reason)

    def test_visual_proof_with_a_cancelled_job_holds_the_release(self):
        jobs = [ci_job("visual-proof", "failure"), ci_job("test", "cancelled")]
        decision, _ = self.plan_with_ci_jobs(jobs)
        self.assertFalse(decision.release)

    def test_a_run_whose_only_failing_job_is_another_job_holds_the_release(self):
        jobs = [ci_job("test", "failure"), ci_job("visual-proof")]
        decision, _ = self.plan_with_ci_jobs(jobs)
        self.assertFalse(decision.release)
        self.assertIn("ci.yml on main's head 0123456 is completed/failure", decision.reason)

    def test_a_failed_run_with_a_job_still_going_waits(self):
        for status in ("in_progress", "queued"):
            with self.subTest(status=status):
                jobs = [ci_job("visual-proof", "failure"), ci_job("test", None, status)]
                decision, _ = self.plan_with_ci_jobs(jobs)
                self.assertFalse(decision.release)
                self.assertIn("ci.yml on main's head 0123456 is completed/failure", decision.reason)

    def test_a_successful_run_is_unaffected_and_reads_no_jobs(self):
        decision, jobs_read = self.plan_with_ci_jobs([], run=ci_run("completed", "success"))
        self.assertTrue(decision.release)
        self.assertFalse(decision.skip_visual_proof)
        jobs_read.assert_not_called()

    def test_an_odd_jobs_payload_never_releases(self):
        for payload in (None, [], {}, {"jobs": "nope"}, {"jobs": [{"name": "visual-proof", "conclusion": "failure"}]}):
            with (
                self.subTest(payload=payload),
                mock.patch.object(release, "ci_jobs", return_value=payload),
            ):
                self.assertFalse(
                    release.only_visual_proof_failed("legacy-forever", runs(ci_run("completed", "failure")), SHA)
                )

    def test_pending_fragments_skip_a_marked_entry_before_any_workflow_read(self):
        self.fragments.return_value = True
        with (
            mock.patch.object(release, "main_head", return_value=SHA),
            mock.patch.object(release, "read_changelog", return_value=SYNC_ENTRY),
            mock.patch.object(release, "release_runs") as runs_read,
        ):
            decision = release.plan("legacy-forever")
        self.fragments.assert_called_once_with("legacy-forever", SHA)
        runs_read.assert_not_called()
        self.assertFalse(decision.release)
        self.assertIn("changes/", decision.reason)

    def test_the_changelog_is_read_at_the_head_that_is_released(self):
        with (
            mock.patch.object(release, "main_head", return_value=SHA),
            mock.patch.object(release, "read_changelog", return_value=SYNC_ENTRY) as read,
            mock.patch.object(release, "tag_exists", return_value=False),
            mock.patch.object(release, "release_runs", return_value=runs({"status": "completed"})),
            mock.patch.object(release, "ci_runs", return_value=runs(ci_run("completed", "success"))),
            mock.patch.object(release, "build_evidence", return_value="success"),
        ):
            decision = release.plan("legacy-forever")
        read.assert_called_once_with("legacy-forever", SHA)
        self.assertTrue(decision.release)
        self.assertEqual(decision.commit, SHA)

    def test_a_green_ci_without_a_smoke_waits_for_the_queue(self):
        with (
            mock.patch.object(release, "main_head", return_value=SHA),
            mock.patch.object(release, "read_changelog", return_value=SYNC_ENTRY),
            mock.patch.object(release, "tag_exists", return_value=False),
            mock.patch.object(release, "release_runs", return_value=runs({"status": "completed"})),
            mock.patch.object(release, "ci_runs", return_value=runs(ci_run("completed", "success"))),
            mock.patch.object(release, "build_evidence", return_value="missing") as smoke,
        ):
            decision = release.plan("legacy-forever")
        smoke.assert_called_once_with("legacy-forever", SHA)
        self.assertFalse(decision.release)
        self.assertFalse(decision.failed)
        self.assertIn("waiting for headless-smoke on 0123456, which is missing", decision.reason)

    def test_a_ci_run_that_did_not_pass_reads_no_smoke_status(self):
        with (
            mock.patch.object(release, "main_head", return_value=SHA),
            mock.patch.object(release, "read_changelog", return_value=SYNC_ENTRY),
            mock.patch.object(release, "tag_exists", return_value=False),
            mock.patch.object(release, "release_runs", return_value=runs({"status": "completed"})),
            mock.patch.object(release, "ci_runs", return_value=runs(ci_run("in_progress", None))),
            mock.patch.object(release, "build_evidence") as smoke,
        ):
            decision = release.plan("legacy-forever")
        smoke.assert_not_called()
        self.assertIn("ci.yml on main's head 0123456 is in_progress", decision.reason)

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
        self.fragments.assert_not_called()
        tag.assert_not_called()
        pending.assert_not_called()
        ci.assert_not_called()

    def test_an_existing_tag_with_a_finished_release_reads_no_ci(self):
        with (
            mock.patch.object(release, "main_head", return_value=SHA),
            mock.patch.object(release, "read_changelog", return_value=SYNC_ENTRY),
            mock.patch.object(release, "tag_exists", return_value=True),
            mock.patch.object(release, "release_runs", return_value=runs(release_run("completed", "success"))),
            mock.patch.object(release, "ci_runs") as ci,
        ):
            decision = release.plan("legacy-forever")
        self.assertFalse(decision.release)
        self.assertFalse(decision.failed)
        ci.assert_not_called()

    def test_a_tag_left_by_a_failed_upload_is_a_failed_release(self):
        with (
            mock.patch.object(release, "main_head", return_value=SHA),
            mock.patch.object(release, "read_changelog", return_value=SYNC_ENTRY),
            mock.patch.object(release, "tag_exists", return_value=True),
            mock.patch.object(release, "release_runs", return_value=runs(release_run("completed", "failure"))),
            mock.patch.object(release, "ci_runs"),
        ):
            decision = release.plan("legacy-forever")
        self.assertFalse(decision.release)
        self.assertTrue(decision.failed)

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
            mock.patch.object(release, "embeds_at", return_value=False),
            mock.patch.object(release, "dispatch") as dispatched,
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(release.main(), 0)

        dispatched.assert_called_once_with("skillup-forever", "1.4.3", SHA, skip_visual_proof=False)
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
            mock.patch.object(release, "embeds_at", return_value=False),
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
            mock.patch.object(release, "embeds_at", return_value=False),
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
            mock.patch.object(release, "embeds_at", return_value=False),
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


class EmbedFleetTest(unittest.TestCase):
    READY = release.Decision("1.4.3", SHA, f"releases v1.4.3 at {SHA}")

    def run_main(self, opted):
        out = io.StringIO()
        heads = {repo: f"head-{repo}" for repo in release.EMBED_FLEET}

        def embeds_at(repo, ref):
            # The releasing addon is read at the commit it would release, the rest at their own main heads.
            self.assertIn(ref, (SHA, heads[repo]) if repo == "macro-assist-forever" else (heads[repo],))
            return opted[repo]

        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": "token"}),
            mock.patch.object(release, "consumer_repos", return_value=["macro-assist-forever"]),
            mock.patch.object(release, "discover_tooling_repos", return_value=set()),
            mock.patch.object(release, "plan", return_value=self.READY),
            mock.patch.object(release, "main_head", side_effect=lambda repo: heads[repo]),
            mock.patch.object(release, "embeds_at", side_effect=embeds_at),
            mock.patch.object(release, "dispatch") as dispatched,
            contextlib.redirect_stdout(out),
        ):
            code = release.main()
        return code, out.getvalue(), dispatched

    def test_an_opted_in_release_waits_for_the_rest_of_the_fleet_and_names_them(self):
        opted = {repo: repo == "macro-assist-forever" for repo in release.EMBED_FLEET}
        opted["skillup-forever"] = True
        code, out, dispatched = self.run_main(opted)
        self.assertEqual(code, 0, out)
        dispatched.assert_not_called()
        self.assertIn("macro-assist-forever: waiting: its embedded ForeverCore release waits", out)
        missing = sorted(set(release.EMBED_FLEET) - {"macro-assist-forever", "skillup-forever"})
        self.assertIn("not yet: " + ", ".join(missing), out)

    def test_an_opted_in_release_goes_once_every_addon_has_opted_in(self):
        code, out, dispatched = self.run_main(dict.fromkeys(release.EMBED_FLEET, True))
        self.assertEqual(code, 0, out)
        dispatched.assert_called_once_with("macro-assist-forever", "1.4.3", SHA, skip_visual_proof=False)

    def test_a_consumer_not_opted_in_releases_without_reading_the_fleet(self):
        code, out, dispatched = self.run_main(dict.fromkeys(release.EMBED_FLEET, False))
        self.assertEqual(code, 0, out)
        dispatched.assert_called_once_with("macro-assist-forever", "1.4.3", SHA, skip_visual_proof=False)

    def run_batch(self, ready, released):
        """Every addon opted in; `ready` names those whose own plan releases now, `released` those already embedded."""
        out = io.StringIO()
        waiting = release.Decision(reason="waiting for ci")
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": "token"}),
            mock.patch.object(release, "consumer_repos", return_value=list(release.EMBED_FLEET)),
            mock.patch.object(release, "discover_tooling_repos", return_value=set()),
            mock.patch.object(release, "plan", side_effect=lambda repo: self.READY if repo in ready else waiting),
            mock.patch.object(release, "main_head", side_effect=lambda repo: f"head-{repo}"),
            mock.patch.object(release, "embeds_at", return_value=True),
            mock.patch.object(release, "latest_release_embeds", side_effect=lambda repo: repo in released),
            mock.patch.object(release, "dispatch") as dispatched,
            contextlib.redirect_stdout(out),
        ):
            code = release.main()
        return code, out.getvalue(), dispatched

    def test_the_embed_releases_wait_for_every_addon_to_be_ready(self):
        ready = set(release.EMBED_FLEET) - {"tweaks-forever"}
        code, out, dispatched = self.run_batch(ready, set())
        self.assertEqual(code, 0, out)
        dispatched.assert_not_called()
        self.assertIn("go out together; not ready yet: tweaks-forever", out)

    def test_an_addon_already_released_embedded_does_not_hold_the_batch(self):
        ready = set(release.EMBED_FLEET) - {"tweaks-forever"}
        code, out, dispatched = self.run_batch(ready, {"tweaks-forever"})
        self.assertEqual(code, 0, out)
        self.assertEqual(dispatched.call_count, len(ready))

    def test_embeds_at_without_package_as_reads_the_listed_root_toc(self):
        files = {".pkgmeta": "ignore:\n  - tools\n", "MacroAssistForever.toc": "## X-Forever-Core-Embed: 1\n"}
        with (
            mock.patch.object(release, "read_file", side_effect=lambda repo, path, ref: files.get(path)),
            mock.patch.object(release, "api_json", return_value=[{"name": "MacroAssistForever.toc"}]),
        ):
            self.assertTrue(release.embeds_at("macro-assist-forever", SHA))

    def test_embed_hold_names_only_the_missing_addons(self):
        self.assertIsNone(release.embed_hold(dict.fromkeys(release.EMBED_FLEET, True)))
        self.assertTrue(release.embed_hold({}).endswith(", ".join(sorted(release.EMBED_FLEET))))

    def test_embeds_at_reads_the_toc_the_policy_names(self):
        files = {
            ".pkgmeta": "package-as: MacroAssistForever\n",
            "MacroAssistForever.toc": "## Interface: 16001\n## X-Forever-Core-Embed: 1\n",
        }
        with mock.patch.object(release, "read_file", side_effect=lambda repo, path, ref: files.get(path)):
            self.assertTrue(release.embeds_at("macro-assist-forever", SHA))
        files["MacroAssistForever.toc"] += "## X-Forever-Core-Embed: 0\n"
        with mock.patch.object(release, "read_file", side_effect=lambda repo, path, ref: files.get(path)):
            self.assertFalse(release.embeds_at("macro-assist-forever", SHA))

    def test_embeds_at_fails_closed_on_a_missing_toc(self):
        files = {".pkgmeta": "package-as: MacroAssistForever\n"}
        with mock.patch.object(release, "read_file", side_effect=lambda repo, path, ref: files.get(path)):
            with self.assertRaises(release.SyncError):
                release.embeds_at("macro-assist-forever", SHA)


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

    def test_missing_changes_directory_has_no_pending_fragments(self):
        missing = subprocess.CompletedProcess([], 1, "", "gh: Not Found (HTTP 404)")
        with mock.patch.object(release, "gh", return_value=missing):
            self.assertFalse(release.has_change_fragments("legacy-forever", SHA))

    def test_changes_directory_counts_markdown_files_only(self):
        listing = '[{"name":"751.md","type":"file"},{"name":"README.txt","type":"file"}]'
        with mock.patch.object(
            release,
            "gh",
            return_value=subprocess.CompletedProcess([], 0, listing, ""),
        ):
            self.assertTrue(release.has_change_fragments("legacy-forever", SHA))
        listing = '[{"name":"README.txt","type":"file"}]'
        with mock.patch.object(
            release,
            "gh",
            return_value=subprocess.CompletedProcess([], 0, listing, ""),
        ):
            self.assertFalse(release.has_change_fragments("legacy-forever", SHA))

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

    def test_the_dispatch_passes_the_visual_proof_waiver(self):
        with mock.patch.object(release, "gh") as gh:
            release.dispatch("legacy-forever", "1.4.3", SHA, skip_visual_proof=True)
        self.assertEqual(gh.call_args.args[-2:], ("-f", "skip_visual_proof=true"))

    def test_workflow_runs_are_read_as_json(self):
        requests = []

        def fake_api_json(path):
            requests.append(path)
            return {"workflow_runs": []}

        with mock.patch.object(release, "api_json", side_effect=fake_api_json):
            self.assertEqual(release.release_runs("legacy-forever"), {"workflow_runs": []})
            self.assertEqual(release.ci_runs("legacy-forever", SHA), {"workflow_runs": []})
            self.assertEqual(release.ci_jobs("legacy-forever", 42), {"workflow_runs": []})
        self.assertEqual(
            requests,
            [
                "repos/cjber/legacy-forever/actions/workflows/release.yml/runs?per_page=20",
                f"repos/cjber/legacy-forever/actions/workflows/ci.yml/runs?head_sha={SHA}&event=push&per_page=100",
                "repos/cjber/legacy-forever/actions/runs/42/jobs?per_page=100",
            ],
        )

    def test_main_head_is_the_full_sha(self):
        with mock.patch.object(release, "api_json", return_value={"sha": SHA}):
            self.assertEqual(release.main_head("legacy-forever"), SHA)


if __name__ == "__main__":
    unittest.main()
