"""Tests for tools/check_core_shared.py, run against a throwaway consumer git repo."""

import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import check_core_shared

CORE = {
    "tools/check_core_shared.py": b"core checker\n",
    "tools/check_client_load.py": b"core client load\n",
    "tools/blizzard_fonts.txt": b"core fonts\n",
    "tools/check_slash_words.py": b"core slash words\n",
    "tools/client_slash_words.txt": b"core slash word list\n",
    "tools/check_menu_scroll.py": b"core menu scroll\n",
    "tools/check_core_name.py": b"core name\n",
    ".agents/skills/wow-forever-addon/check_copy.py": b"core copy\n",
    "tools/core-shared-drift.yml": b"core workflow\n",
    "tools/visual-proof.yml": b"core visual workflow\n",
    "tools/deadcode.py": b"core deadcode\n",
    "tools/deadcode-allow.txt": b"core allow\n",
    "docs/discord-button.png": b"discord\n",
    "docs/github-sponsors-button.png": b"sponsors\n",
    "docs/kofi-button.png": b"kofi\n",
    "tools/consumer/ForeverRequire.lua": b"core require\n",
}


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class CheckCoreSharedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "field-guide-forever"
        self.root.mkdir()
        git(self.root, "init", "--quiet", "--initial-branch=main")
        git(self.root, "config", "user.email", "test@example.com")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "config", "commit.gpgsign", "false")
        git(self.root, "remote", "add", "origin", "git@github.com:cjber/field-guide-forever.git")
        self.core = dict(CORE)
        for path in check_core_shared.paths_for(self.root.name):
            self.write(path, self.fetch(path))
        self.write("Core/Own.lua", b"own\n")
        self.commit("base")
        git(self.root, "branch", "base")
        self.cwd = Path.cwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def fetch(self, path):
        return self.core[check_core_shared.source(path)]

    def write(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self, message):
        git(self.root, "add", "-A")
        git(self.root, "commit", "--quiet", "--allow-empty", "-m", message)

    def run_check(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_core_shared.main(list(argv), fetch=self.fetch)
        return code, out.getvalue()

    def test_full_check_passes_when_every_copy_matches(self):
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("16 vendored files match", out)

    def test_check_copy_comes_from_the_skill_pack(self):
        self.assertEqual(
            check_core_shared.source("tools/check_copy.py"),
            ".agents/skills/wow-forever-addon/check_copy.py",
        )
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("16 vendored files match", out)

    def test_full_check_reports_a_consumer_that_lags_behind_core(self):
        self.core["tools/check_client_load.py"] = b"core client load, newer\n"
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("tools/check_client_load.py", out)

    def test_base_ignores_a_lag_the_branch_did_not_touch(self):
        self.core["tools/check_client_load.py"] = b"core client load, newer\n"
        self.write("Core/Own.lua", b"own, changed\n")
        self.commit("unrelated")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 0, out)
        self.assertIn("No vendored file changed", out)

    def test_base_fails_a_hand_edit_of_a_vendored_copy(self):
        self.write("tools/deadcode.py", b"edited here\n")
        self.write("Core/Own.lua", b"own, changed\n")
        self.commit("hand edit")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 1)
        self.assertIn("tools/deadcode.py: consumer", out)
        self.assertNotIn("tools/check_client_load.py", out)

    def test_base_fails_a_deleted_vendored_copy(self):
        (self.root / "tools/blizzard_fonts.txt").unlink()
        self.commit("delete")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 1)
        self.assertIn("tools/blizzard_fonts.txt: missing here", out)

    def test_base_passes_a_sync_to_core_main(self):
        self.core["tools/core-shared-drift.yml"] = b"core workflow, newer\n"
        self.write(".github/workflows/core-shared-drift.yml", b"core workflow, newer\n")
        self.commit("sync")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 0, out)
        self.assertIn("1 vendored files match", out)

    def test_every_core_source_exists(self):
        root = Path(__file__).resolve().parents[1]
        for path in check_core_shared.VENDORED:
            self.assertTrue((root / check_core_shared.source(path)).is_file(), path)

    def test_rejects_unknown_consumer(self):
        with self.assertRaisesRegex(SystemExit, "Unknown consumer repo: forever-core"):
            self.run_check("--repo", "forever-core")

    def test_repo_from_git_normalizes_supported_remote_forms(self):
        for remote in (
            "git@github.com:cjber/field-guide-forever.git/",
            "ssh://git@github.com/cjber/field-guide-forever.git/",
            "https://github.com/CJBER/FIELD-GUIDE-FOREVER.git/",
        ):
            with self.subTest(remote=remote):
                git(self.root, "remote", "set-url", "origin", remote)
                self.assertEqual(check_core_shared.repo_from_git(), "field-guide-forever")

    def test_worktree_uses_remote_repo_not_directory_name(self):
        worktree = Path(self.tmp.name) / "misleading-worktree-name"
        git(self.root, "worktree", "add", "--detach", str(worktree), "HEAD")
        os.chdir(worktree)
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("16 vendored files match", out)

    def test_a_consumer_with_an_addon_folder_uses_the_prefixed_paths(self):
        git(self.root, "remote", "set-url", "origin", "git@github.com:cjber/kiln-forever.git")
        paths = check_core_shared.paths_for("kiln-forever")
        for path in paths:
            self.write(check_core_shared.consumer_path("kiln-forever", path), self.fetch(path))
        self.commit("kiln files")

        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn(f"{len(paths)} vendored files match", out)

        self.write("addon/KilnForever/tools/check_core_shared.py", b"edited here\n")
        self.commit("hand edit")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 1)
        self.assertIn("addon/KilnForever/tools/check_core_shared.py: consumer", out)
        self.assertNotIn("tools/check_client_load.py", out)

    def test_only_the_checker_reaches_kiln_forever(self):
        paths = set(check_core_shared.paths_for("kiln-forever"))
        self.assertEqual(paths, {"tools/check_core_shared.py"})

    def test_the_visual_proof_workflow_reaches_every_published_consumer(self):
        path = ".github/workflows/visual-proof.yml"
        self.assertEqual(check_core_shared.VENDORED[path], check_core_shared.SUITE_CONSUMERS)
        self.assertEqual(check_core_shared.source(path), "tools/visual-proof.yml")
        for repo in check_core_shared.SUITE_CONSUMERS:
            with self.subTest(repo=repo):
                self.assertIn(path, check_core_shared.paths_for(repo))
                self.assertEqual(check_core_shared.consumer_path(repo, path), path)
        self.assertNotIn(path, check_core_shared.paths_for("kiln-forever"))

    def test_the_name_rule_reaches_every_published_consumer(self):
        path = "tools/check_core_name.py"
        self.assertEqual(check_core_shared.VENDORED[path], check_core_shared.SUITE_CONSUMERS)
        for repo in check_core_shared.SUITE_CONSUMERS:
            with self.subTest(repo=repo):
                self.assertIn(path, check_core_shared.paths_for(repo))
                self.assertEqual(check_core_shared.consumer_path(repo, path), path)
        self.assertNotIn(path, check_core_shared.paths_for("kiln-forever"))

    def test_base_fails_a_missing_visual_proof_workflow(self):
        (self.root / ".github/workflows/visual-proof.yml").unlink()
        self.commit("drop visual proof workflow")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 1)
        self.assertIn(".github/workflows/visual-proof.yml: missing here", out)

    def test_base_fails_a_drifted_visual_proof_workflow(self):
        self.write(".github/workflows/visual-proof.yml", b"old inline job\n")
        self.commit("drift visual proof workflow")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 1)
        self.assertIn(".github/workflows/visual-proof.yml: consumer", out)


if __name__ == "__main__":
    unittest.main()
