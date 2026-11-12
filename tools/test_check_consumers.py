"""Tests for tools/check_consumers.py's per-consumer pin and packaging checks, against throwaway trees."""

import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import check_consumers

SHARED = b"# checker\n"
CORE = Path(__file__).resolve().parent.parent
WORKFLOW = CORE / "tools/visual-proof.yml"
TOOLING = CORE / ".agents/skills/wow-forever-addon/tooling/forever_tools"


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class CheckConsumersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.core = base / "forever-core"
        (self.core / "tools").mkdir(parents=True)
        (self.core / "tools" / "check_core_shared.py").write_bytes(SHARED)
        # The latest release tag with --local is this checkout's newest v* tag, so the throwaway core is a git repo.
        git(self.core, "init", "--quiet", "--initial-branch=main")
        git(self.core, "config", "user.email", "test@example.com")
        git(self.core, "config", "user.name", "Test")
        git(self.core, "config", "commit.gpgsign", "false")
        git(self.core, "add", "-A")
        git(self.core, "commit", "--quiet", "-m", "core")
        git(self.core, "tag", "v1.4.0")

        self.checkouts = base / "consumers"
        self.repo = self.checkouts / "legacy-forever"
        (self.repo / "tools").mkdir(parents=True)
        (self.repo / "tools" / "check_core_shared.py").write_bytes(SHARED)
        self.pin = self.repo / "tools" / "forever-core.txt"
        self.pin.write_text("v1.4.0\n", encoding="utf-8")

        self.patches = [
            mock.patch.object(check_consumers, "CORE_ROOT", self.core),
            mock.patch.object(check_consumers, "VENDORED", {"tools/check_core_shared.py": ("legacy-forever",)}),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_consumers.main(["--local", str(self.checkouts)])
        return code, out.getvalue()

    def write_pkgmeta(self, text):
        (self.repo / ".pkgmeta").write_text(text, encoding="utf-8")

    def write_toc(self, text):
        (self.repo / "LegacyForever.toc").write_text(text, encoding="utf-8")

    def write_core_toc(self, pin="v1.4.0", dependencies="ForeverCore"):
        """The root TOC of a consumer that depends on ForeverCore and names the core release its zip bundles."""
        self.write_toc(f"## Interface: 16001\n## Dependencies: {dependencies}\n## X-Forever-Core: {pin}\n")

    def write_core_pkgmeta(self, pin="v1.4.0", package="LegacyForever", declares_required=False):
        """The `.pkgmeta` of a consumer that ships `pin`'s ForeverCore, optionally also asking for it by name."""
        self.write_pkgmeta(
            f"package-as: {package}\n\n"
            "externals:\n"
            f"  ForeverCore: https://github.com/cjber/forever-core/releases/download/{pin}/"
            f"ForeverCore-{pin}-forever.zip\n\n"
            "move-folders:\n"
            f"  {package}/ForeverCore: ForeverCore\n"
            + ("\nrequired-dependencies:\n  - forevercore\n" if declares_required else "")
        )

    def test_an_equal_pin_passes(self):
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_a_consumer_without_a_pin_is_not_checked(self):
        self.pin.unlink()
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_a_lagging_pin_fails(self):
        self.pin.write_text("v1.3.2\n", encoding="utf-8")
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("legacy-forever: tools/forever-core.txt: pin v1.3.2, core's latest release is v1.4.0", out)

    def test_the_pin_is_compared_numerically(self):
        git(self.core, "commit", "--quiet", "--allow-empty", "-m", "next")
        git(self.core, "tag", "v1.10.0")
        self.pin.write_text("v1.9.0\n", encoding="utf-8")
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("pin v1.9.0, core's latest release is v1.10.0", out)

    def test_an_external_from_another_release_fails(self):
        self.write_core_pkgmeta(pin="v1.3.2")
        self.write_core_toc()
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("tools/forever-core.txt pins v1.4.0", out)
        self.assertIn(
            "it must be https://github.com/cjber/forever-core/releases/download/v1.4.0/ForeverCore-v1.4.0-forever.zip",
            out,
        )

    def test_a_missing_externals_entry_fails(self):
        self.write_pkgmeta("package-as: LegacyForever\n\nmove-folders:\n  LegacyForever/ForeverCore: ForeverCore\n")
        self.write_core_toc()
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("`externals:` does not ship ForeverCore", out)

    def test_a_missing_move_folders_entry_fails(self):
        self.write_pkgmeta(
            "package-as: LegacyForever\n\n"
            "externals:\n"
            "  ForeverCore: https://github.com/cjber/forever-core/releases/download/"
            "v1.4.0/ForeverCore-v1.4.0-forever.zip\n"
        )
        self.write_core_toc()
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("`move-folders:` must place ForeverCore at the zip's top level", out)
        self.assertIn("LegacyForever/ForeverCore: ForeverCore", out)

    def test_a_required_dependencies_forevercore_entry_fails(self):
        self.write_core_pkgmeta(declares_required=True)
        self.write_core_toc()
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("one owner for the folder", out)

    def test_a_consumer_that_requires_core_without_a_pin_fails(self):
        self.pin.unlink()
        self.write_core_pkgmeta()
        self.write_core_toc()
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("no pin names the release to ship", out)

    def test_shipping_core_from_the_pin_and_not_requiring_it_passes(self):
        self.write_core_pkgmeta()
        self.write_core_toc()
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_a_missing_x_forever_core_field_fails(self):
        self.write_core_pkgmeta()
        self.write_toc("## Interface: 16001\n## Dependencies: ForeverCore\n")
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("no `## X-Forever-Core:` line names the core release the zip bundles", out)
        self.assertIn("add `## X-Forever-Core: v1.4.0`", out)

    def test_an_x_forever_core_field_from_another_release_fails(self):
        self.write_core_pkgmeta()
        self.write_core_toc(pin="v1.3.0")
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("`## X-Forever-Core:` is v1.3.0", out)
        self.assertIn("tools/forever-core.txt pins v1.4.0, so it must be v1.4.0", out)

    def test_the_x_forever_core_field_is_read_case_insensitively(self):
        self.write_core_pkgmeta()
        self.write_toc("## Interface: 16001\n## Dependencies: ForeverCore\n## x-forever-core: v1.4.0\n")
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_a_consumer_that_does_not_require_core_needs_no_relation(self):
        self.write_pkgmeta("package-as: LegacyForever\n\noptional-dependencies:\n  - questie\n")
        self.write_toc("## Interface: 16001\n## OptionalDeps: Questie\n")
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_an_unreadable_latest_release_skips_the_pin_check_without_failing(self):
        self.pin.write_text("v1.3.2\n", encoding="utf-8")
        out = io.StringIO()
        with (
            mock.patch.object(check_consumers, "local_latest_tag", return_value=None),
            contextlib.redirect_stdout(out),
        ):
            code = check_consumers.main(["--local", str(self.checkouts)])
        self.assertEqual(code, 0, out.getvalue())


class VisualWorkflowCheckTest(unittest.TestCase):
    """The standalone workflow and the full tooling it imports, against a throwaway consumer checkout."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.core = base / "forever-core"
        (self.core / "tools").mkdir(parents=True)
        shutil.copyfile(WORKFLOW, self.core / "tools/visual-proof.yml")

        self.checkouts = base / "consumers"
        self.repo = self.checkouts / "legacy-forever"
        self.repo.mkdir(parents=True)
        shutil.copytree(TOOLING, self.repo / "tools/forever_tools")
        self.write_workflow(WORKFLOW.read_bytes())

        patcher = mock.patch.object(check_consumers, "VENDORED", {check_consumers.VISUAL_WORKFLOW: ("legacy-forever",)})
        patcher.start()
        self.addCleanup(patcher.stop)
        core_patcher = mock.patch.object(check_consumers, "CORE_ROOT", self.core)
        core_patcher.start()
        self.addCleanup(core_patcher.stop)

    def write_workflow(self, data):
        target = self.repo / check_consumers.VISUAL_WORKFLOW
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_consumers.main(["--local", str(self.checkouts)])
        return code, out.getvalue()

    def test_a_canonical_workflow_and_full_tooling_pass(self):
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_a_missing_workflow_is_red(self):
        (self.repo / check_consumers.VISUAL_WORKFLOW).unlink()
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("missing canonical visual-proof workflow", out)

    def test_a_drifted_workflow_is_red(self):
        self.write_workflow(b"name: old inline job\n")
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("drifted from tools/visual-proof.yml", out)

    def test_a_workflow_without_the_imported_tooling_is_red(self):
        shutil.rmtree(self.repo / "tools/forever_tools")
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("tools/forever_tools: missing; sync the full forever_tools package", out)

    def test_a_tooling_copy_missing_an_import_is_red(self):
        # Adventure Guide and SkillUp already carried visual_proof.py without the pkgmeta.py it imports.
        (self.repo / "tools/forever_tools/pkgmeta.py").unlink()
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("tools/forever_tools/pkgmeta.py: missing from the full forever_tools sync", out)
        self.assertNotIn("tools/forever_tools/visual_proof.py:", out)

    def test_remote_tooling_check_reads_the_folder_once_and_compares_blob_ids(self):
        names = sorted(check_consumers.tooling_sync.read_manifest(TOOLING)["files"])
        listing = [
            {
                "name": name,
                "type": "file",
                "sha": check_consumers.blob_sha((TOOLING / name).read_bytes()),
            }
            for name in names
        ]
        with mock.patch.object(check_consumers, "remote_json", return_value=listing) as remote_json:
            failures = check_consumers.tooling_sync_problems("legacy-forever", "main", None)
        self.assertEqual(failures, [])
        self.assertEqual(remote_json.call_count, 1)

    def test_remote_tooling_check_names_a_missing_import(self):
        names = sorted(check_consumers.tooling_sync.read_manifest(TOOLING)["files"])
        listing = [
            {"name": name, "type": "file", "sha": check_consumers.blob_sha((TOOLING / name).read_bytes())}
            for name in names
            if name != "pkgmeta.py"
        ]
        with mock.patch.object(check_consumers, "remote_json", return_value=listing):
            failures = check_consumers.tooling_sync_problems("legacy-forever", "main", None)
        self.assertTrue(
            any("tools/forever_tools/pkgmeta.py: missing from the full forever_tools sync" in item for item in failures)
        )


if __name__ == "__main__":
    unittest.main()
