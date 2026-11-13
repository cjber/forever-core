"""The release gate: full CI on main, the headless smoke, and the manual visual-proof skip."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from forever_tools import release_check

COMMIT = "a" * 40


def run(**overrides):
    record = {
        "id": 7,
        "head_sha": COMMIT,
        "head_branch": "main",
        "path": ".github/workflows/ci.yml",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
    }
    record.update(overrides)
    return record


def job(name, conclusion):
    return {"name": name, "conclusion": conclusion}


class VisualProofSkipTest(unittest.TestCase):
    """`--skip-visual-proof` waives one named job, and nothing else."""

    def test_a_successful_run_passes_without_reading_jobs(self):
        def jobs_for(_run):
            raise AssertionError("a successful run needs no job lookup")

        self.assertTrue(release_check.verified([run()], COMMIT, jobs_for=jobs_for))
        self.assertTrue(release_check.verified([run()], COMMIT, jobs_for=jobs_for, skip_visual_proof=True))

    def test_a_visual_proof_only_failure_passes_only_with_the_flag(self):
        failing = run(conclusion="failure")
        jobs = [
            job("check", "success"),
            job(release_check.VISUAL_PROOF_JOB, "failure"),
            job("visual-proof-status", "skipped"),
        ]
        looked_up = []

        def jobs_for(candidate):
            looked_up.append(candidate)
            return jobs

        self.assertFalse(release_check.verified([failing], COMMIT, jobs_for=jobs_for))
        self.assertEqual(looked_up, [])
        self.assertTrue(release_check.verified([failing], COMMIT, jobs_for=jobs_for, skip_visual_proof=True))
        self.assertEqual(looked_up, [failing])

    def test_another_failed_job_blocks_the_skip(self):
        failing = run(conclusion="failure")
        jobs = [job("check", "failure"), job(release_check.VISUAL_PROOF_JOB, "failure")]
        self.assertFalse(release_check.verified([failing], COMMIT, jobs_for=lambda _: jobs, skip_visual_proof=True))

    def test_a_failure_no_job_explains_is_not_skipped(self):
        failing = run(conclusion="failure")
        for jobs in ([], [job("check", "success"), job("packaged", "skipped")]):
            with self.subTest(jobs=jobs):
                self.assertFalse(
                    release_check.verified(
                        [failing],
                        COMMIT,
                        jobs_for=lambda _, jobs=jobs: jobs,
                        skip_visual_proof=True,
                    )
                )

    def test_a_run_that_did_not_conclude_in_failure_is_not_skipped(self):
        jobs = [job(release_check.VISUAL_PROOF_JOB, "failure")]
        for conclusion in ("cancelled", "timed_out", "stale", None):
            with self.subTest(conclusion=conclusion):
                self.assertFalse(
                    release_check.verified(
                        [run(conclusion=conclusion)],
                        COMMIT,
                        jobs_for=lambda _: jobs,
                        skip_visual_proof=True,
                    )
                )

    def test_a_job_without_a_conclusion_counts_as_failed(self):
        failing = run(conclusion="failure")
        unnamed = [job("check", None)]
        self.assertFalse(release_check.verified([failing], COMMIT, jobs_for=lambda _: unnamed, skip_visual_proof=True))
        visual = [job(release_check.VISUAL_PROOF_JOB, None)]
        self.assertTrue(release_check.verified([failing], COMMIT, jobs_for=lambda _: visual, skip_visual_proof=True))

    def test_only_a_complete_green_main_push_for_the_commit_can_be_skipped(self):
        jobs = [job(release_check.VISUAL_PROOF_JOB, "failure")]
        for key, value in (
            ("head_sha", "b" * 40),
            ("head_branch", "dev"),
            ("path", ".github/workflows/visual-proof.yml"),
            ("event", "pull_request"),
            ("status", "in_progress"),
        ):
            with self.subTest(key=key):
                self.assertFalse(
                    release_check.verified(
                        [run(conclusion="failure", **{key: value})],
                        COMMIT,
                        jobs_for=lambda _: jobs,
                        skip_visual_proof=True,
                    )
                )

    def test_the_jobs_request_names_the_run(self):
        requests = []

        def fake(path, text=True):
            requests.append(path)
            return json.dumps([{"jobs": [job("check", "success")]}])

        with patch.object(release_check.subprocess, "check_output", side_effect=fake):
            self.assertEqual(len(release_check.jobs("cjber/forever-core", 7)), 1)
        self.assertEqual(requests[0][-1], "repos/cjber/forever-core/actions/runs/7/jobs?per_page=100")

    def release(self, arguments, runs, jobs, statuses):
        """Run main over recorded API answers, returning its output or the reason it exited."""
        answers = [json.dumps([{"workflow_runs": runs}]), json.dumps([{"jobs": jobs}]), json.dumps([statuses])]
        with (
            patch.dict("os.environ", {"GITHUB_REPOSITORY": "cjber/forever-core", "GITHUB_SHA": COMMIT}),
            patch.object(release_check.subprocess, "check_output", side_effect=answers) as request,
            contextlib.redirect_stdout(io.StringIO()) as out,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            try:
                release_check.main(arguments)
            except SystemExit as exit:
                return exit.code, request, out.getvalue()
        return None, request, out.getvalue()

    def test_main_prints_the_skip_and_still_checks_the_smoke(self):
        failing = run(conclusion="failure")
        jobs = [job("check", "success"), job(release_check.VISUAL_PROOF_JOB, "failure")]
        refusal, request, out = self.release(
            ["--skip-visual-proof"], [failing], jobs, [{"context": "headless-smoke", "state": "success"}]
        )
        self.assertIsNone(refusal)
        self.assertEqual(request.call_count, 3)
        self.assertIn("Release skips the failed visual-proof job", out)
        self.assertIn("--skip-visual-proof", out)
        self.assertIn("(skipping visual-proof)", out)
        self.assertIn("headless-smoke passed", out)

    def test_main_without_the_flag_refuses_and_never_reads_jobs(self):
        failing = run(conclusion="failure")
        refusal, request, _out = self.release([], [failing], [], [])
        self.assertIn("successful full CI run", refusal)
        self.assertEqual(request.call_count, 1)

    def test_main_never_skips_the_smoke(self):
        failing = run(conclusion="failure")
        jobs = [job(release_check.VISUAL_PROOF_JOB, "failure")]
        refusal, _request, _out = self.release(
            ["--skip-visual-proof"],
            [failing],
            jobs,
            [{"context": "headless-smoke", "state": "failure", "description": "2 Lua errors"}],
        )
        self.assertEqual(refusal, "Release blocked: headless-smoke on " + COMMIT + " is failure: 2 Lua errors")

    def test_main_refuses_another_failed_job_even_with_the_flag(self):
        failing = run(conclusion="failure")
        jobs = [job("check", "failure"), job(release_check.VISUAL_PROOF_JOB, "failure")]
        refusal, _request, out = self.release(
            ["--skip-visual-proof"], [failing], jobs, [{"context": "headless-smoke", "state": "success"}]
        )
        self.assertIn("successful full CI run", refusal)
        self.assertNotIn("skipping", out)
