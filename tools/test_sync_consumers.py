"""Tests for tools/sync_consumers.py, run against throwaway core and consumer trees."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import check_consumers
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

    def test_full_sync_retires_wago_and_is_idempotent(self):
        self.write(self.root, sync.RELEASE_WORKFLOW, RELEASE_WORKFLOW + "          WAGO_API_TOKEN: token\n")
        self.write(self.root, "LegacyForever.toc", "## X-Wago-ID: old\n## X-Curse-Project-ID: 1\n")
        self.write(
            self.root,
            "README.md",
            "Install from [CurseForge](https://cf.test) or\n"
            "[Wago Addons](https://addons.wago.io/addons/x), or GitHub.\n"
            "Data: [wago.tools](https://wago.tools).\n",
        )
        self.write(self.root, "docs/curseforge.md", "CurseForge and Wago install core.\n")
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertNotIn("WAGO_API_TOKEN", self.release())
        self.assertEqual((self.root / "LegacyForever.toc").read_text(), "## X-Curse-Project-ID: 1\n")
        self.assertEqual(
            (self.root / "README.md").read_text(),
            "Install from [CurseForge](https://cf.test), or GitHub.\nData: [wago.tools](https://wago.tools).\n",
        )
        self.assertEqual((self.root / "docs/curseforge.md").read_text(), "CurseForge installs core.\n")
        code, out = self.run_sync()
        self.assertEqual(code, 0, out)
        self.assertIn("0 file(s) changed", out)

    def test_wago_cleanup_dry_run_and_nested_addon(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "addon/KilnForever/KilnForever.toc"
            self.write(root, str(path.relative_to(root)), "## X-Wago-ID: old\n")
            self.assertEqual(sync.sync_store_channels(root, "kiln-forever", True), 1)
            self.assertIn("X-Wago-ID", path.read_text())
            self.assertEqual(sync.sync_store_channels(root, "kiln-forever", False), 1)
            self.assertEqual(path.read_text(), "")

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


STALE_TAG_STEP = """name: Release

jobs:
  release:
    steps:
      - name: Tag a manual release
        if: github.event_name == 'workflow_dispatch'
        run: |
          gh api "repos/$GITHUB_REPOSITORY/git/refs" -f "ref=refs/tags/$RELEASE_TAG" -f "sha=$RELEASE_COMMIT"

          git tag "$RELEASE_TAG" "$RELEASE_COMMIT"
      # The packager uploads.
      - uses: BigWigsMods/packager@01e8631a69c69d7654c788d152630d5fed9e3812 # v2.7.0
"""


class TagStepTest(unittest.TestCase):
    """A consumer's manual-release tag step is core's own, carried by the sync and checked by the drift gate."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.checkouts = Path(self.tmp.name)
        self.root = self.checkouts / "legacy-forever"
        self.workflow = self.root / sync.RELEASE_WORKFLOW
        self.workflow.parent.mkdir(parents=True)
        self.workflow.write_text(STALE_TAG_STEP, encoding="utf-8")

    def check(self):
        return check_consumers.check_tag_step("legacy-forever", "main", self.checkouts)

    def test_the_sync_replaces_a_stale_step_with_cores_and_the_gate_passes(self):
        self.assertIn("differs from core's", self.check()[0])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sync.sync_tag_step(self.root, "legacy-forever", dry_run=False), 1)
        text = self.workflow.read_text(encoding="utf-8")
        core = (check_consumers.CORE_ROOT / sync.RELEASE_WORKFLOW).read_text(encoding="utf-8")
        start, end, _ = check_consumers.workflow_step(core, check_consumers.TAG_STEP)
        self.assertIn(core[start:end], text)
        # The comment and step after it survive, and nothing of the stale step is left.
        self.assertIn("      # The packager uploads.\n      - uses: BigWigsMods/packager@", text)
        self.assertEqual(text.count("- name: Tag a manual release"), 1)
        self.assertEqual(self.check(), [])
        self.assertEqual(sync.sync_tag_step(self.root, "legacy-forever", dry_run=False), 0)

    def test_a_workflow_without_the_step_is_left_alone(self):
        self.workflow.write_text(KILN_RELEASE_WORKFLOW, encoding="utf-8")
        self.assertEqual(sync.sync_tag_step(self.root, "legacy-forever", dry_run=False), 0)
        self.assertEqual(self.workflow.read_text(encoding="utf-8"), KILN_RELEASE_WORKFLOW)


if __name__ == "__main__":
    unittest.main()


class VersionStepTest(unittest.TestCase):
    """The sync writes the bare version step above every packager in a consumer's release and CI workflows."""

    CI = """jobs:
  package:
    steps:
      - name: Package this commit as an untagged build
        run: git tag --points-at HEAD | xargs -r git tag --delete
      - name: Embed ForeverCore
        run: python3 -m tools.forever_tools.embed
      - uses: BigWigsMods/packager@01e8631a69c69d7654c788d152630d5fed9e3812 # v2.7.0
        with:
          args: -d -z
"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.checkouts = Path(self.tmp.name)
        self.root = self.checkouts / "legacy-forever"
        (self.root / ".github/workflows").mkdir(parents=True)
        (self.root / sync.RELEASE_WORKFLOW).write_text(RELEASE_WORKFLOW, encoding="utf-8")
        (self.root / sync.CI_WORKFLOW).write_text(self.CI, encoding="utf-8")

    def check(self):
        return check_consumers.check_version_step("legacy-forever", "main", self.checkouts)

    def run_sync(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return sync.sync_version_step(self.root, "legacy-forever", dry_run=False)

    def test_the_sync_inserts_the_step_above_each_packager_once(self):
        self.assertEqual(len(self.check()), 2)
        self.assertEqual(self.run_sync(), 2)
        self.assertEqual(self.check(), [])
        step = sync.version_step()
        release = (self.root / sync.RELEASE_WORKFLOW).read_text(encoding="utf-8")
        self.assertIn(step + "      - uses: BigWigsMods/packager@", release)
        ci = (self.root / sync.CI_WORKFLOW).read_text(encoding="utf-8")
        # The embed step keeps its place; the version step sits between it and the packager.
        self.assertIn("python3 -m tools.forever_tools.embed\n" + step + "      - uses: BigWigsMods/packager@", ci)
        self.assertEqual(self.run_sync(), 0)

    def test_a_commented_out_step_does_not_count(self):
        path = self.root / sync.RELEASE_WORKFLOW
        packager = "      - uses: BigWigsMods/packager@"
        commented = "      # - run: python3 -m tools.forever_tools.toc_version\n"
        path.write_text(RELEASE_WORKFLOW.replace(packager, commented + packager), encoding="utf-8")
        self.assertIn("release.yml: a packager step with no", self.check()[0])
        self.run_sync()
        self.assertIn(sync.version_step() + packager, path.read_text(encoding="utf-8"))
        self.assertEqual(self.check(), [])

    def test_the_pin_gate_stays_directly_above_the_packager(self):
        path = self.root / sync.RELEASE_WORKFLOW
        packager = "      - uses: BigWigsMods/packager@"
        path.write_text(RELEASE_WORKFLOW.replace(packager, sync.release_gate_step() + packager), encoding="utf-8")
        self.run_sync()
        text = path.read_text(encoding="utf-8")
        self.assertIn(sync.version_step() + sync.release_gate_step() + packager, text)
        self.assertEqual(self.check(), [])
        self.assertEqual(check_consumers.check_release_gate("legacy-forever", "main", self.checkouts), [])

    def test_a_workflow_without_a_packager_is_left_alone(self):
        (self.root / sync.RELEASE_WORKFLOW).write_text(KILN_RELEASE_WORKFLOW, encoding="utf-8")
        (self.root / sync.CI_WORKFLOW).unlink()
        self.assertEqual(self.check(), [])
        self.assertEqual(self.run_sync(), 0)
        self.assertEqual((self.root / sync.RELEASE_WORKFLOW).read_text(encoding="utf-8"), KILN_RELEASE_WORKFLOW)
