"""The release gate: full CI on main, the release smoke, and the manual visual-proof skip."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
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


NO_PROOF = ".visual-proof.json: missing"


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

    def release(self, arguments, runs, jobs, statuses, proof=NO_PROOF):
        """Run main over recorded API answers, returning its output or the reason it exited.

        `jobs` is None for a run whose jobs are never read, and `proof` is what `proof_refusal` says of the checkout:
        a verified proof (None) reads no statuses.
        """
        answers = [json.dumps([{"workflow_runs": runs}])]
        if jobs is not None:
            answers.append(json.dumps([{"jobs": jobs}]))
        if proof is not None:
            answers.append(json.dumps([statuses]))
        # The releases listing: no GitHub release carries v1.0.0 yet.
        answers.append(json.dumps([[]]))
        environ = {
            "GITHUB_REPOSITORY": "cjber/forever-core",
            "GITHUB_SHA": COMMIT,
            "GITHUB_REF": "refs/tags/v1.0.0",
            "GITHUB_REF_NAME": "v1.0.0",
        }
        with (
            patch.dict("os.environ", environ),
            patch.object(release_check, "curseforge_projects", return_value=[]),
            patch.object(release_check, "proof_refusal", return_value=proof),
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
        self.assertEqual(request.call_count, 4)
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
        self.assertEqual(
            refusal,
            f"Release blocked: headless-smoke on {COMMIT} is failure: 2 Lua errors; "
            f"the committed visual proof does not stand in for it: {NO_PROOF}",
        )

    def test_a_verified_proof_releases_without_reading_the_smoke(self):
        refusal, request, out = self.release([], [run()], None, [], proof=None)
        self.assertIsNone(refusal)
        self.assertEqual(request.call_count, 2, "the runs and the releases listing, no statuses")
        self.assertIn(".visual-proof.json proves the build", out)

    def test_a_proof_that_does_not_verify_falls_back_to_the_smoke(self):
        refusal, request, out = self.release(
            [], [run()], None, [{"context": "headless-smoke", "state": "success"}], proof="visual proof selftest failed"
        )
        self.assertIsNone(refusal)
        self.assertEqual(request.call_count, 3)
        self.assertIn("headless-smoke passed", out)

    def test_main_refuses_another_failed_job_even_with_the_flag(self):
        failing = run(conclusion="failure")
        jobs = [job("check", "failure"), job(release_check.VISUAL_PROOF_JOB, "failure")]
        refusal, _request, out = self.release(
            ["--skip-visual-proof"], [failing], jobs, [{"context": "headless-smoke", "state": "success"}]
        )
        self.assertIn("successful full CI run", refusal)
        self.assertNotIn("skipping", out)


# The three files CurseForge listed for SkillUp 1.14.10: the first was built before the fix it announced, and the tag
# was then moved and released again under the same version (cjber/skillup-forever#901).
SKILLUP_FILES = [
    "SkillUpForever-v1.14.10-forever.zip",
    "SkillUpForever-v1.14.10-forever.zip",
    "SkillUpForever-v1.14.10-forever.zip",
    "SkillUpForever-v1.14.9-forever.zip",
    "SkillUpForever-v1.14.9-forever.zip",
]


class PublishedOnceTest(unittest.TestCase):
    """A version publishes once: a second build under a number players already installed is refused."""

    def test_the_skillup_1_14_10_rerelease_is_refused(self):
        refusal = release_check.published_refusal("v1.14.10", ["release.json"], {"1705762": SKILLUP_FILES})
        self.assertIn("v1.14.10 is already on CurseForge project 1705762", refusal)
        self.assertIsNone(release_check.published_refusal("v1.14.11", None, {"1705762": SKILLUP_FILES}))

    def test_a_github_package_for_the_tag_is_refused(self):
        refusal = release_check.published_refusal("v1.0.0", ["release.json", "Addon-v1.0.0-forever.zip"], {})
        self.assertIn("already published on GitHub (Addon-v1.0.0-forever.zip)", refusal)
        # A release with no package yet (a draft, or one whose upload never ran) has shipped nothing.
        self.assertIsNone(release_check.published_refusal("v1.0.0", [], {}))
        self.assertIsNone(release_check.published_refusal("v1.0.0", ["release.json"], {}))

    def test_a_file_name_names_only_its_own_version(self):
        self.assertTrue(release_check.names_version("SkillUpForever-v1.14.10-forever.zip", "v1.14.10"))
        self.assertTrue(release_check.names_version("Kiln-v1.14.10.zip", "v1.14.10"))
        self.assertFalse(release_check.names_version("SkillUpForever-v1.14.10-forever.zip", "v1.14.1"))
        self.assertFalse(release_check.names_version("SkillUpForever-v1.14.100-forever.zip", "v1.14.10"))

    def test_the_tag_comes_from_the_push_or_the_manual_version(self):
        self.assertEqual(
            release_check.release_tag({"GITHUB_REF": "refs/tags/v2.0.1", "GITHUB_REF_NAME": "v2.0.1"}), "v2.0.1"
        )
        with tempfile.TemporaryDirectory() as folder:
            event = Path(folder) / "event.json"
            event.write_text(json.dumps({"inputs": {"version": "2.0.2", "commit": ""}}), encoding="utf-8")
            environ = {"GITHUB_REF": "refs/heads/main", "GITHUB_REF_NAME": "main", "GITHUB_EVENT_PATH": str(event)}
            self.assertEqual(release_check.release_tag(environ), "v2.0.2")
            event.write_text(json.dumps({}), encoding="utf-8")
            self.assertIsNone(release_check.release_tag(environ))
        self.assertIsNone(release_check.release_tag({"GITHUB_REF": "refs/heads/main"}))

    def test_the_projects_come_from_the_root_tocs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "Addon.toc").write_text(
                "\ufeff## Interface: 16001\n## X-Curse-Project-ID: 1705762\n## X-Wago-ID: abc\nCore.lua\n",
                encoding="utf-8",
            )
            (root / "Addon_Vanilla.toc").write_text("## X-Curse-Project-ID: 1705762\n", encoding="utf-8")
            self.assertEqual(release_check.curseforge_projects(root), ["1705762"])
            (root / "Addon.toc").write_text("## Interface: 16001\n", encoding="utf-8")
            (root / "Addon_Vanilla.toc").unlink()
            self.assertEqual(release_check.curseforge_projects(root), [])

    def test_the_store_listing_is_read_to_the_end(self):
        # CurseForge's pageIndex counts pages: with two files a page, the third file is on page 1.
        pages = {
            0: {"data": [{"fileName": "A-v1.0.1-forever.zip"}, {"fileName": "A-v1.0.0-forever.zip"}]},
            1: {"data": [{"fileName": "A-v0.9.0-forever.zip"}]},
        }
        requested = []

        def fetch(url):
            requested.append(url)
            page = int(url.split("pageIndex=")[1].split("&")[0])
            return {**pages[page], "pagination": {"totalCount": 3}}

        names = release_check.curseforge_files("42", fetch=fetch)
        self.assertEqual(names, ["A-v1.0.1-forever.zip", "A-v1.0.0-forever.zip", "A-v0.9.0-forever.zip"])
        self.assertEqual(len(requested), 2)
        self.assertTrue(requested[0].startswith("https://www.curseforge.com/api/v1/mods/42/files?"))

    def test_the_github_release_is_found_by_its_tag(self):
        pages = [[{"tag_name": "v1.0.1", "assets": []}], [{"tag_name": "v1.0.0", "assets": [{"name": "A.zip"}]}]]
        with patch.object(release_check.subprocess, "check_output", return_value=json.dumps(pages)):
            self.assertEqual(release_check.github_release_assets("cjber/a", "v1.0.0"), ["A.zip"])
            self.assertIsNone(release_check.github_release_assets("cjber/a", "v2.0.0"))

    def test_main_refuses_a_version_already_on_curseforge(self):
        answers = [
            json.dumps([{"workflow_runs": [run()]}]),
            json.dumps([[{"context": "headless-smoke", "state": "success"}]]),
            json.dumps([[{"tag_name": "v1.14.10", "assets": [{"name": "release.json"}]}]]),
        ]
        environ = {
            "GITHUB_REPOSITORY": "cjber/skillup-forever",
            "GITHUB_SHA": COMMIT,
            "GITHUB_REF": "refs/tags/v1.14.10",
            "GITHUB_REF_NAME": "v1.14.10",
        }
        with (
            patch.dict("os.environ", environ),
            patch.object(release_check, "curseforge_projects", return_value=["1705762"]),
            patch.object(release_check, "curseforge_files", return_value=SKILLUP_FILES),
            patch.object(release_check.subprocess, "check_output", side_effect=answers),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as refused,
        ):
            release_check.main([])
        self.assertIn("v1.14.10 is already on CurseForge project 1705762", refused.exception.code)

    def test_main_refuses_a_run_that_names_no_version(self):
        answers = [
            json.dumps([{"workflow_runs": [run()]}]),
            json.dumps([[{"context": "headless-smoke", "state": "success"}]]),
        ]
        with (
            patch.dict("os.environ", {"GITHUB_REPOSITORY": "cjber/a", "GITHUB_SHA": COMMIT}, clear=True),
            patch.object(release_check.subprocess, "check_output", side_effect=answers),
            self.assertRaises(SystemExit) as refused,
        ):
            release_check.main([])
        self.assertIn("names the release", refused.exception.code)
