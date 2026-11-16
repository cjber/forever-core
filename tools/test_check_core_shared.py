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
    "tools/lint_client_calls.py": b"core client calls\n",
    "tools/check_core_name.py": b"core name\n",
    ".agents/skills/wow-forever-addon/check_copy.py": b"core copy\n",
    "tools/core-shared-drift.yml": b"core workflow\n",
    "tools/visual-proof.yml": b"core visual workflow\n",
    "tools/dependabot-consumer.yml": b"core dependabot\n",
    "tools/deadcode.py": b"core deadcode\n",
    "tools/deadcode-allow.txt": b"core allow\n",
    "tools/toolchain.json": b"core toolchain\n",
    "tools/pyproject.toml": b"core pyproject\n",
    "tools/uv.lock": b"core lock\n",
    "docs/discord-button.png": b"discord\n",
    "docs/github-sponsors-button.png": b"sponsors\n",
    "docs/kofi-button.png": b"kofi\n",
    ".github/FUNDING.yml": b"funding\n",
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
        self.write("tools/typecheck.sh", self.gate_script())
        self.write("Core/Own.lua", b"own\n")
        self.commit("base")
        git(self.root, "branch", "base")
        self.cwd = Path.cwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def gate_script(self):
        return "".join(f"python3 {script}\n" for script in check_core_shared.REQUIRED_GATE_CHECKS).encode()

    def test_missing_invocation_fails(self):
        self.write("tools/typecheck.sh", b"true\n")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("tools/lint_client_calls.py: tools/typecheck.sh never runs it", out)

    def test_comments_and_mentions_do_not_run_a_check(self):
        self.write("tools/typecheck.sh", self.gate_script().replace(b"python3 tools/lint", b"# python3 tools/lint"))
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("tools/lint_client_calls.py: tools/typecheck.sh never runs it", out)

    def test_base_checks_gate_changes_without_vendored_changes(self):
        self.write("tools/typecheck.sh", b"true\n")
        self.commit("remove invocations")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 1)
        self.assertIn("tools/lint_client_calls.py: tools/typecheck.sh never runs it", out)

    def test_base_checks_invocation_when_vendored_script_changes(self):
        script = "tools/lint_client_calls.py"
        self.write("tools/typecheck.sh", self.gate_script().replace(f"python3 {script}\n".encode(), b""))
        self.core[script] = b"updated lint\n"
        self.write(script, self.core[script])
        self.commit("sync lint without invocation")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 1)
        self.assertIn(f"{script}: tools/typecheck.sh never runs it", out)

    def test_missing_typecheck_fails(self):
        (self.root / "tools/typecheck.sh").unlink()
        self.assertEqual(self.run_check()[0], 1)

    def test_consumer_outside_vendored_is_skipped(self):
        self.assertEqual(check_core_shared.check_gate_invocations("other-consumer", ""), [])

    def test_base_skips_invocation_for_unrelated_change(self):
        self.write("tools/typecheck.sh", b"true\n")
        self.commit("base without invocation")
        git(self.root, "branch", "without-invocation")
        self.write("Core/Own.lua", b"changed\n")
        self.commit("unrelated")
        self.assertEqual(self.run_check("--base", "without-invocation")[0], 0)

    def test_exact_command_invocations(self):
        for line in (
            "python tools/lint_client_calls.py",
            "python3 tools/lint_client_calls.py",
            "uv run --project tools --frozen python3 tools/lint_client_calls.py",
        ):
            with self.subTest(line=line):
                self.assertEqual(list(check_core_shared.gate_commands(line)), ["tools/lint_client_calls.py"])
        for line in (
            "# python3 tools/lint_client_calls.py",
            "echo tools/lint_client_calls.py",
            "uv run tools/lint_client_calls.py",
            "python3 other/tools/lint_client_calls.py",
        ):
            self.assertNotIn("tools/lint_client_calls.py", check_core_shared.gate_commands(line))

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
        self.assertIn("22 vendored files match", out)

    def test_check_copy_comes_from_the_skill_pack(self):
        self.assertEqual(
            check_core_shared.source("tools/check_copy.py"),
            ".agents/skills/wow-forever-addon/check_copy.py",
        )
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("22 vendored files match", out)

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
        self.assertIn("22 vendored files match", out)

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

    def test_kiln_forever_takes_the_checker_and_the_tool_pins(self):
        paths = set(check_core_shared.paths_for("kiln-forever"))
        self.assertEqual(
            paths,
            {"tools/check_core_shared.py", "tools/toolchain.json", "tools/pyproject.toml", "tools/uv.lock"},
        )
        for path in sorted(paths - {"tools/check_core_shared.py"}):
            with self.subTest(path=path):
                self.assertEqual(check_core_shared.consumer_path("kiln-forever", path), f"addon/KilnForever/{path}")

    def test_the_tool_pins_reach_every_published_consumer(self):
        for path in ("tools/toolchain.json", "tools/pyproject.toml", "tools/uv.lock"):
            with self.subTest(path=path):
                self.assertEqual(
                    check_core_shared.VENDORED[path],
                    check_core_shared.SUITE_CONSUMERS + check_core_shared.KILN_CONSUMERS,
                )
                self.assertEqual(check_core_shared.source(path), path)
                for repo in check_core_shared.SUITE_CONSUMERS:
                    self.assertIn(path, check_core_shared.paths_for(repo))
                    self.assertEqual(check_core_shared.consumer_path(repo, path), path)
                self.assertIn(path, check_core_shared.paths_for("kiln-forever"))

    def test_the_dependabot_config_reaches_every_published_consumer(self):
        path = ".github/dependabot.yml"
        self.assertEqual(check_core_shared.VENDORED[path], check_core_shared.SUITE_CONSUMERS)
        self.assertEqual(check_core_shared.source(path), "tools/dependabot-consumer.yml")
        for repo in check_core_shared.SUITE_CONSUMERS:
            self.assertIn(path, check_core_shared.paths_for(repo))
            self.assertEqual(check_core_shared.consumer_path(repo, path), path)
        self.assertNotIn(path, check_core_shared.paths_for("kiln-forever"))

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
