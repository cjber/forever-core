"""Tests for tools/sync_consumers.py, run against throwaway core and consumer trees."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sync_consumers as sync

DEADCODE = b"# deadcode\n"
ALLOW = b"# allow\n"
CLIENT_LOAD = b"# client load\n"
CHECKER = b"# checker\n"
TOC = "## Interface: 16001\nCore\\Own.lua\n"
LUACHECK = 'read_globals = { "CreateFrame" }\n'


class SyncConsumersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.core = base / "forever-core"
        self.write(self.core, "tools/deadcode.py", DEADCODE)
        self.write(self.core, "tools/deadcode-allow.txt", ALLOW)
        self.write(self.core, "tools/check_client_load.py", CLIENT_LOAD)
        self.write(self.core, "tools/check_core_shared.py", CHECKER)
        self.checkouts = base / "checkouts"

    def write(self, root, path, data):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def consumer(self, name="legacy-forever"):
        root = self.checkouts / name
        self.write(root, "LegacyForever.toc", TOC.encode())
        self.write(root, ".luacheckrc", LUACHECK.encode())
        return root

    def kiln_consumer(self):
        root = self.checkouts / "kiln-forever"
        self.write(root, "addon/KilnForever/KilnForever.toc", TOC.encode())
        self.write(root, ".luacheckrc", LUACHECK.encode())
        return root

    def run_sync(self, *argv, only=("tools/deadcode.py",)):
        out = io.StringIO()
        arguments = [str(self.checkouts)]
        for path in only:
            arguments += ["--only", path]
        with mock.patch.object(sync, "CORE_ROOT", self.core), contextlib.redirect_stdout(out):
            code = sync.main([*arguments, *argv])
        return code, out.getvalue()

    def test_tooling_is_copied_and_nothing_else_changes(self):
        root = self.consumer()
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertEqual((root / "tools/deadcode.py").read_bytes(), DEADCODE)
        self.assertEqual((root / "LegacyForever.toc").read_text(), TOC)
        self.assertEqual((root / ".luacheckrc").read_text(), LUACHECK)
        self.assertIn("legacy-forever: tools/deadcode.py", out)

    def test_second_run_changes_nothing(self):
        root = self.consumer()
        self.run_sync()
        before = (root / "tools/deadcode.py").read_bytes()
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertEqual((root / "tools/deadcode.py").read_bytes(), before)
        self.assertIn("0 file(s) changed", out)

    def test_warning_is_copied_and_loaded_before_the_guard(self):
        root = self.consumer()
        self.write(root, ".pkgmeta", b"package-as: LegacyForever\n")
        self.write(self.core, "tools/consumer/ForeverRequire.lua", b"-- shared warning\n")
        toc = root / "LegacyForever.toc"
        original = b"## Interface: 16001\r\nCore\\Require.lua\r\nCore/ForeverRequire.lua\r\n"
        toc.write_bytes(original)
        only = ("Core/ForeverRequire.lua",)

        code, out = self.run_sync("--dry-run", only=only)
        self.assertEqual(code, 0, out)
        self.assertIn("2 file(s) would change", out)
        self.assertEqual(toc.read_bytes(), original)
        self.assertFalse((root / only[0]).exists())

        code, out = self.run_sync(only=only)
        self.assertEqual(code, 0, out)
        self.assertEqual((root / only[0]).read_bytes(), b"-- shared warning\n")
        self.assertEqual(toc.read_bytes(), b"## Interface: 16001\r\nCore\\ForeverRequire.lua\r\nCore\\Require.lua\r\n")

        code, out = self.run_sync(only=only)
        self.assertEqual(code, 0, out)
        self.assertIn("0 file(s) changed", out)

    def test_dry_run_writes_nothing(self):
        root = self.consumer()
        code, out = self.run_sync("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertFalse((root / "tools/deadcode.py").exists())
        self.assertIn("would change", out)

    def test_a_consumer_that_is_not_checked_out_is_skipped(self):
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertIn("legacy-forever: not checked out", out)
        self.assertIn("0 file(s) changed", out)

    def test_a_consumer_with_an_addon_folder_syncs_below_it(self):
        root = self.kiln_consumer()
        code, out = self.run_sync(only=("tools/check_core_shared.py",))
        self.assertEqual(code, 0, out)
        self.assertEqual((root / "addon/KilnForever/tools/check_core_shared.py").read_bytes(), CHECKER)
        self.assertFalse((root / "tools/check_core_shared.py").exists())
        self.assertIn("kiln-forever: tools/check_core_shared.py", out)

    def test_the_drift_workflow_keeps_its_consumer_path(self):
        self.write(self.core, "tools/core-shared-drift.yml", b"# workflow\n")
        root = self.consumer()
        code, out = self.run_sync(only=(".github/workflows/core-shared-drift.yml",))
        self.assertEqual(code, 0, out)
        self.assertEqual((root / ".github/workflows/core-shared-drift.yml").read_bytes(), b"# workflow\n")

    def test_the_visual_proof_workflow_keeps_its_consumer_path(self):
        self.write(self.core, "tools/visual-proof.yml", b"# visual workflow\n")
        root = self.consumer()
        code, out = self.run_sync(only=(".github/workflows/visual-proof.yml",))
        self.assertEqual(code, 0, out)
        self.assertEqual((root / ".github/workflows/visual-proof.yml").read_bytes(), b"# visual workflow\n")
        self.assertIn("full forever_tools sync", out)

    def test_kiln_does_not_take_the_drift_workflow(self):
        self.write(self.core, "tools/core-shared-drift.yml", b"# workflow\n")
        root = self.kiln_consumer()
        code, out = self.run_sync(only=(".github/workflows/core-shared-drift.yml",))
        self.assertEqual(code, 0, out)
        self.assertFalse((root / "addon/KilnForever/.github/workflows/core-shared-drift.yml").exists())

    def test_kiln_does_not_take_the_visual_proof_workflow(self):
        self.write(self.core, "tools/visual-proof.yml", b"# visual workflow\n")
        root = self.kiln_consumer()
        code, out = self.run_sync(only=(".github/workflows/visual-proof.yml",))
        self.assertEqual(code, 0, out)
        self.assertFalse((root / "addon/KilnForever/.github/workflows/visual-proof.yml").exists())
        self.assertFalse((root / ".github/workflows/visual-proof.yml").exists())

    def test_a_module_the_consumer_already_has_is_overwritten(self):
        root = self.consumer()
        self.write(root, "tools/deadcode.py", b"old\n")
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertEqual((root / "tools/deadcode.py").read_bytes(), DEADCODE)


RELEASE_WORKFLOW = """name: Release

on:
  push:
    tags: ["v*"]

jobs:
  release:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: BigWigsMods/packager@01e8631a69c69d7654c788d152630d5fed9e3812 # v2.7.0
        env:
          CF_API_KEY: ${{ secrets.CF_API_KEY }}
"""

KILN_RELEASE_WORKFLOW = """name: Release

jobs:
  release:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - name: Publish the release
        run: gh release create "$GITHUB_REF_NAME" dist/*.tar.gz
"""


class ReleaseGateTest(unittest.TestCase):
    """The ForeverCore pin gate the sync inserts directly above the packager in an addon's own release workflow."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.core = base / "forever-core"
        self.write(self.core, "tools/deadcode.py", DEADCODE)
        self.checkouts = base / "checkouts"
        self.root = self.checkouts / "legacy-forever"
        (self.root / "tools").mkdir(parents=True)

    def write(self, root, path, data):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data if isinstance(data, str) else data.decode())

    def run_sync(self, *argv):
        out = io.StringIO()
        with (
            mock.patch.object(sync, "CORE_ROOT", self.core),
            mock.patch.object(sync, "VENDORED", {"tools/deadcode.py": ("legacy-forever",)}),
            contextlib.redirect_stdout(out),
        ):
            code = sync.main([str(self.checkouts), *argv])
        return code, out.getvalue()

    def release(self):
        return (self.root / sync.RELEASE_WORKFLOW).read_text(encoding="utf-8")

    def test_the_gate_lands_directly_above_the_packager(self):
        self.write(self.root, sync.RELEASE_WORKFLOW, RELEASE_WORKFLOW)
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        text = self.release()
        self.assertEqual(text.count(sync.RELEASE_GATE_NAME), 1)
        gate = text.index(sync.RELEASE_GATE_NAME)
        packager = text.index("- uses: BigWigsMods/packager@")
        self.assertLess(gate, packager)
        # Nothing but the gate may sit between it and the packager step.
        self.assertIn(
            "run: python3 -m tools.forever_tools.core_pin --latest\n      - uses: BigWigsMods/packager@",
            text,
        )
        self.assertIn("GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}", text)

    def test_a_second_sync_does_not_add_a_second_gate(self):
        self.write(self.root, sync.RELEASE_WORKFLOW, RELEASE_WORKFLOW)
        self.run_sync()
        first = self.release()
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.release(), first)
        self.assertIn("0 file(s) changed", out)

    def test_a_dry_run_reports_the_gate_without_writing_it(self):
        self.write(self.root, sync.RELEASE_WORKFLOW, RELEASE_WORKFLOW)
        code, out = self.run_sync("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn(f"legacy-forever: {sync.RELEASE_WORKFLOW}", out)
        self.assertEqual(self.release(), RELEASE_WORKFLOW)

    def test_a_workflow_without_the_packager_is_left_alone_and_the_step_is_printed(self):
        self.write(self.root, sync.RELEASE_WORKFLOW, KILN_RELEASE_WORKFLOW)
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.release(), KILN_RELEASE_WORKFLOW)
        self.assertIn("has no BigWigs packager step", out)
        self.assertIn("python3 -m tools.forever_tools.core_pin --latest", out)

    def test_a_targeted_sync_leaves_the_release_workflow_alone(self):
        self.write(self.root, sync.RELEASE_WORKFLOW, RELEASE_WORKFLOW)
        code, out = self.run_sync("--only", "tools/deadcode.py")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.release(), RELEASE_WORKFLOW)


if __name__ == "__main__":
    unittest.main()
