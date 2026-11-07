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
    "tools/deadcode.py": b"core deadcode\n",
    "tools/deadcode-allow.txt": b"core allow\n",
    "UI/SettingsPage.lua": b"core settings\n",
    "tests/settings_page_spec.lua": b"core settings spec\n",
    "Core/MinimapButton.lua": b"core minimap\n",
    "Core/PeerStats.lua": b"core peer stats\n",
    "tests/peer_stats_spec.lua": b"core peer stats spec\n",
    "Core/LeaderboardsData.lua": b"core leaderboards data\n",
    "UI/Leaderboards.lua": b"core leaderboards\n",
    "tests/leaderboards_spec.lua": b"core leaderboards spec\n",
    "tests/leaderboards_window_spec.lua": b"core leaderboards window spec\n",
    "tests/leaderboards_harness.lua": b"core leaderboards harness\n",
    "tests/minimap_button_spec.lua": b"core minimap spec\n",
    "tools/check_core_shared.py": b"core checker\n",
    "tools/check_client_load.py": b"core client load\n",
    "tools/blizzard_fonts.txt": b"core fonts\n",
    "tools/check_menu_scroll.py": b"core menu scroll\n",
    "tools/core-shared-drift.yml": b"core workflow\n",
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
        self.assertIn("18 vendored files match", out)

    def test_full_check_reports_a_consumer_that_lags_behind_core(self):
        self.core["UI/SettingsPage.lua"] = b"core settings, newer\n"
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("UI/SettingsPage.lua", out)

    def test_base_ignores_a_lag_the_branch_did_not_touch(self):
        self.core["UI/SettingsPage.lua"] = b"core settings, newer\n"
        self.write("Core/Own.lua", b"own, changed\n")
        self.commit("unrelated")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 0, out)
        self.assertIn("No vendored file changed", out)

    def test_base_fails_a_hand_edit_of_a_vendored_copy(self):
        self.write("Core/MinimapButton.lua", b"edited here\n")
        self.write("Core/Own.lua", b"own, changed\n")
        self.commit("hand edit")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 1)
        self.assertIn("Core/MinimapButton.lua: consumer", out)
        self.assertNotIn("UI/SettingsPage.lua", out)

    def test_base_fails_a_deleted_vendored_copy(self):
        (self.root / "tests/minimap_button_spec.lua").unlink()
        self.commit("delete")
        code, out = self.run_check("--base", "base")
        self.assertEqual(code, 1)
        self.assertIn("tests/minimap_button_spec.lua: missing here", out)

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
        self.assertIn("18 vendored files match", out)


if __name__ == "__main__":
    unittest.main()
