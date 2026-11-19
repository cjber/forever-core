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
from check_core_shared import REQUIRED_GATE_CHECKS

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
        (self.repo / "tools/typecheck.sh").write_text("".join(f"python3 {script}\n" for script in REQUIRED_GATE_CHECKS))
        self.pin = self.repo / "tools" / "forever-core.txt"
        self.pin.write_text("v1.4.0\n", encoding="utf-8")

        self.patches = [
            mock.patch.object(check_consumers, "CORE_ROOT", self.core),
            mock.patch.object(check_consumers, "VENDORED", {"tools/check_core_shared.py": ("legacy-forever",)}),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_local_consumer_requires_gate_invocations(self):
        (self.repo / "tools/typecheck.sh").write_text("# python3 tools/lint_client_calls.py\n")
        with mock.patch.dict(check_consumers.VENDORED, {"tools/lint_client_calls.py": ("legacy-forever",)}):
            failures = check_consumers.check_consumer_gates("legacy-forever", "main", self.checkouts)
        self.assertTrue(
            any("tools/lint_client_calls.py: tools/typecheck.sh never runs it" in failure for failure in failures)
        )

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_consumers.main(["--local", str(self.checkouts)])
        return code, out.getvalue()

    def write_pkgmeta(self, text):
        (self.repo / ".pkgmeta").write_text(text, encoding="utf-8")

    def write_toc(self, text):
        (self.repo / "LegacyForever.toc").write_text(text, encoding="utf-8")

    def write_core_toc(self, pin="v1.4.0", optional="ForeverCore"):
        """The root TOC of a consumer that loads ForeverCore when installed and names the core its zip bundles."""
        self.write_toc(f"## Interface: 16001\n## OptionalDeps: {optional}\n## X-Forever-Core: {pin}\n")

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

    def test_retired_wago_toc_field_fails(self):
        self.write_core_pkgmeta()
        self.write_core_toc()
        with (self.repo / "LegacyForever.toc").open("a") as stream:
            stream.write("## X-Wago-ID: old\n")
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("retired X-Wago-ID", out)

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

    def write_embedded(self, pkgmeta_extra="", relation="embedded-libraries", pin="v1.4.0", toc_pin="v1.4.0"):
        """A consumer that carries core under Libs/ForeverCore, in the decided end state unless a test changes it."""
        self.write_toc(
            "## Interface: 16001\n## OptionalDeps: ForeverCore\n"
            f"## X-Forever-Core: {toc_pin}\n## X-Forever-Core-Embed: 1\n"
        )
        self.write_pkgmeta(
            "package-as: LegacyForever\n\n" + pkgmeta_extra + (f"\n{relation}:\n  - forevercore\n" if relation else "")
        )

    def embedded_failures(self):
        return check_consumers.check_packaging("legacy-forever", "v1.4.0", "main", self.checkouts)

    def test_an_embedded_consumer_in_the_end_state_passes(self):
        self.write_embedded()
        self.assertEqual(self.embedded_failures(), [])

    def test_an_embedded_consumer_still_shipping_the_top_level_external_fails(self):
        self.write_embedded(
            "externals:\n  ForeverCore: https://github.com/cjber/forever-core/releases/download/v1.4.0/"
            "ForeverCore-v1.4.0-forever.zip\n"
        )
        self.assertTrue(any("ships a second ForeverCore" in failure for failure in self.embedded_failures()))

    def test_an_embedded_consumer_still_moving_the_top_level_folder_fails(self):
        self.write_embedded("move-folders:\n  LegacyForever/ForeverCore: ForeverCore\n")
        self.assertTrue(any("at the top-level ForeverCore" in failure for failure in self.embedded_failures()))

    def test_an_embedded_consumer_requiring_the_standalone_fails(self):
        self.write_embedded(relation="required-dependencies")
        failures = self.embedded_failures()
        self.assertTrue(any("move it to `embedded-libraries:`" in failure for failure in failures))
        self.assertTrue(any("under `embedded-libraries:`" in failure and "list" in failure for failure in failures))

    def test_an_embedded_consumer_without_the_relation_fails(self):
        self.write_embedded(relation="")
        self.assertTrue(any("(spaces, no trailing whitespace)" in failure for failure in self.embedded_failures()))

    def test_an_embedded_consumer_whose_toc_names_another_release_fails(self):
        self.write_embedded(toc_pin="v1.3.0")
        self.assertTrue(any("must be v1.4.0" in failure for failure in self.embedded_failures()))

    def test_an_embedded_consumer_moving_its_embedded_copy_out_fails(self):
        self.write_embedded("move-folders:\n  LegacyForever/Libs/ForeverCore: ForeverCore\n")
        failures = self.embedded_failures()
        self.assertTrue(any("at the top-level ForeverCore" in failure for failure in failures))

    def test_an_embedded_consumer_moving_the_libs_folder_fails(self):
        self.write_embedded("move-folders:\n  LegacyForever/Libs: SharedLibs\n")
        self.assertTrue(any("holds the embedded ForeverCore" in failure for failure in self.embedded_failures()))

    def test_an_embedded_consumer_moving_another_folder_to_forevercore_fails(self):
        self.write_embedded("move-folders:\n  LegacyForever/Vendor/Core: forevercore\n")
        self.assertTrue(any("at the top-level forevercore" in failure for failure in self.embedded_failures()))

    def test_an_embedded_consumer_with_a_block_form_core_external_fails(self):
        self.write_embedded(
            "externals:\n  Vendor/Core:\n    url: https://github.com/cjber/forever-core/releases/download/v1.4.0/"
            "ForeverCore-v1.4.0-forever.zip\n"
        )
        self.assertTrue(any("ships a second ForeverCore" in failure for failure in self.embedded_failures()))

    def test_an_embedded_consumer_with_an_unrelated_external_and_move_passes(self):
        self.write_embedded(
            "externals:\n  Libs/LibStub: https://repos.curseforge.com/wow/libstub/trunk\n\n"
            "move-folders:\n  LegacyForever/Data: LegacyForever_Data\n"
        )
        self.assertEqual(self.embedded_failures(), [])

    def test_an_embedded_relation_the_uploader_would_not_read_fails(self):
        for body in (
            "embedded-libraries:\n  - forevercore \n",
            "embedded-libraries: [forevercore]\n",
            "embedded-libraries:\n  forevercore: yes\n",
        ):
            with self.subTest(body=body):
                self.write_embedded(body, relation="")
                self.assertTrue(
                    any("(spaces, no trailing whitespace)" in failure for failure in self.embedded_failures())
                )

    def test_an_embedded_consumer_with_another_form_of_core_external_fails(self):
        for external in (
            "Vendor/Core: https://github.com/cjber/forever-core.git\n",
            "Vendor/Core: git@github.com:cjber/forever-core.git\n",
            "Vendor/Core:\n    url: https://repos.curseforge.com/wow/forevercore/trunk\n",
            "Vendor/Core: https://example.com/ForeverCore-v1.4.0-forever.zip\n",
        ):
            with self.subTest(external=external):
                self.write_embedded("externals:\n  " + external)
                self.assertTrue(any("ships a second ForeverCore" in failure for failure in self.embedded_failures()))

    def test_an_embedded_consumer_with_a_capitalised_relation_is_read_without_case(self):
        self.write_embedded("required-dependencies:\n  - ForeverCore\n", relation="")
        failures = self.embedded_failures()
        self.assertTrue(any("move it to `embedded-libraries:`" in failure for failure in failures))
        for entry in ("ForeverCore", "'ForeverCore'"):
            with self.subTest(entry=entry):
                self.write_embedded(f"embedded-libraries:\n  - {entry}\n", relation="")
                self.assertEqual(self.embedded_failures(), [])

    def test_an_embedded_consumer_moving_a_folder_to_core_in_another_form_fails(self):
        for destination, message in (
            ("/ForeverCore", "outside the zip's top level"),
            ("../ForeverCore", "outside the zip's top level"),
            ("ForeverCore.", "at the top-level ForeverCore."),
            ("Shared/ForeverCore", "ForeverCore ships only under Libs/ForeverCore"),
            ("LegacyForever/Libs/ForeverCore", "ForeverCore ships only under Libs/ForeverCore"),
            ("LegacyForever/Libs", "over the embedded ForeverCore"),
        ):
            with self.subTest(destination=destination):
                self.write_embedded(f"move-folders:\n  LegacyForever/Vendor/Core: {destination}\n")
                self.assertTrue(any(message in failure for failure in self.embedded_failures()), destination)

    def test_the_last_opt_in_line_decides_like_the_embed_step(self):
        self.write_embedded()
        toc = (self.repo / "LegacyForever.toc").read_text(encoding="utf-8")
        # A last value other than 1 is neither embedded nor quietly opted out: the line has to say 1 or go.
        (self.repo / "LegacyForever.toc").write_text(toc + "## X-Forever-Core-Embed: 0\n", encoding="utf-8")
        self.assertTrue(any("exactly 1" in failure for failure in self.embedded_failures()))
        (self.repo / "LegacyForever.toc").write_text(
            toc.replace("## X-Forever-Core-Embed: 1\n", "## X-Forever-Core-Embed: 0\n## X-Forever-Core-Embed: 1\n"),
            encoding="utf-8",
        )
        self.assertEqual(self.embedded_failures(), [])

    def test_a_pkgmeta_yaml_embedded_consumer_is_checked(self):
        self.write_embedded("required-dependencies:\n  - forevercore\n")
        (self.repo / ".pkgmeta").rename(self.repo / "pkgmeta.yaml")
        failures = self.embedded_failures()
        self.assertTrue(any("pkgmeta.yaml" in failure and "required-dependencies" in failure for failure in failures))

    def test_an_embedded_consumer_without_package_as_uses_the_shortest_root_toc(self):
        self.write_embedded("required-dependencies:\n  - forevercore\n")
        text = (self.repo / ".pkgmeta").read_text(encoding="utf-8").replace("package-as: LegacyForever\n", "")
        (self.repo / ".pkgmeta").write_text(text, encoding="utf-8")
        (self.repo / "LegacyForever_Vanilla.toc").write_text("## Interface: 11507\n", encoding="utf-8")
        self.assertTrue(any("required-dependencies" in failure for failure in self.embedded_failures()))

    def test_package_as_set_twice_fails(self):
        self.write_embedded()
        text = (self.repo / ".pkgmeta").read_text(encoding="utf-8")
        (self.repo / ".pkgmeta").write_text("package-as: Wrong\n" + text, encoding="utf-8")
        self.assertTrue(any("set 2 times" in failure for failure in self.embedded_failures()))

    def test_package_as_naming_a_missing_toc_fails(self):
        self.write_embedded()
        text = (self.repo / ".pkgmeta").read_text(encoding="utf-8").replace("LegacyForever", "Missing")
        (self.repo / ".pkgmeta").write_text(text, encoding="utf-8")
        self.assertTrue(any("Missing.toc, which does not exist" in failure for failure in self.embedded_failures()))

    def test_an_opted_in_consumer_without_a_policy_fails(self):
        self.write_embedded()
        (self.repo / ".pkgmeta").unlink()
        self.assertTrue(any("no .pkgmeta or pkgmeta.yaml" in failure for failure in self.embedded_failures()))

    def test_a_second_root_toc_beside_an_embedded_one_fails(self):
        self.write_embedded()
        (self.repo / "LegacyForever_Mainline.toc").write_text("## Interface: 110000\n", encoding="utf-8")
        self.assertTrue(any("LegacyForever_Mainline.toc" in failure for failure in self.embedded_failures()))

    def test_an_external_nested_deeper_than_its_sibling_is_still_an_external(self):
        self.write_embedded(
            "externals:\n  Libs/Foo: https://example.org/foo.git\n    ForeverCore: https://github.com/cjber/forever-core.git\n"
        )
        self.assertTrue(any("second ForeverCore" in failure for failure in self.embedded_failures()))

    def test_a_store_id_external_ships_core(self):
        self.write_embedded("externals:\n  Libs/Core: https://wow.curseforge.com/projects/1796337\n")
        self.assertTrue(any("second ForeverCore" in failure for failure in self.embedded_failures()))

    def test_a_later_relation_for_core_replaces_the_embedded_one(self):
        for relation in ("optional-dependencies", "tools-used"):
            with self.subTest(relation=relation):
                self.write_embedded(relation="")
                text = (self.repo / ".pkgmeta").read_text(encoding="utf-8")
                (self.repo / ".pkgmeta").write_text(
                    text + f"\nembedded-libraries:\n  - forevercore\n{relation}:\n  - ForeverCore\n",
                    encoding="utf-8",
                )
                self.assertTrue(any(f"under `{relation}:`" in failure for failure in self.embedded_failures()))

    def test_an_opt_in_value_other_than_1_fails(self):
        self.write_embedded()
        toc = (self.repo / "LegacyForever.toc").read_text(encoding="utf-8")
        (self.repo / "LegacyForever.toc").write_text(toc.replace("Embed: 1", "Embed: true"), encoding="utf-8")
        self.assertTrue(any("exactly 1" in failure for failure in self.embedded_failures()))

    def test_a_tab_indented_pkgmeta_fails_as_the_packager_refuses_it(self):
        self.write_embedded("embedded-libraries:\n\t- forevercore\n", relation="")
        self.assertTrue(any("leading tab" in failure for failure in self.embedded_failures()))

    def test_a_required_dependency_alongside_the_transition_bundle_passes(self):
        self.write_core_pkgmeta(declares_required=True)
        self.write_core_toc()
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

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
        self.write_toc("## Interface: 16001\n## OptionalDeps: ForeverCore\n")
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
        self.write_toc("## Interface: 16001\n## OptionalDeps: ForeverCore\n## x-forever-core: v1.4.0\n")
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_the_optional_deps_header_is_read_case_insensitively(self):
        self.write_core_pkgmeta()
        self.write_toc("## Interface: 16001\n## optionaldeps: ForeverCore\n## X-Forever-Core: v1.4.0\n")
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_a_dependencies_line_naming_core_fails(self):
        self.write_core_pkgmeta()
        self.write_toc(
            "## Interface: 16001\n## Dependencies: ForeverCore\n## OptionalDeps: Questie\n## X-Forever-Core: v1.4.0\n"
        )
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("lists ForeverCore in `## Dependencies`", out)
        self.assertIn("move it to `## OptionalDeps`", out)

    def test_a_bundled_consumer_without_optional_deps_fails(self):
        self.write_core_pkgmeta()
        self.write_toc("## Interface: 16001\n## OptionalDeps: Questie\n## X-Forever-Core: v1.4.0\n")
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("no `## OptionalDeps: ForeverCore`", out)

    def test_optional_deps_keeps_other_addons_on_the_same_line(self):
        self.write_core_pkgmeta()
        self.write_toc("## Interface: 16001\n## OptionalDeps: Questie, ForeverCore\n## X-Forever-Core: v1.4.0\n")
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_a_consumer_that_does_not_require_core_needs_no_relation(self):
        self.write_pkgmeta("package-as: LegacyForever\n\noptional-dependencies:\n  - questie\n")
        self.write_toc("## Interface: 16001\n## OptionalDeps: Questie\n")
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_an_unreadable_latest_release_fails_the_pin_check(self):
        self.pin.write_text("v1.3.2\n", encoding="utf-8")
        out = io.StringIO()
        with (
            mock.patch.object(check_consumers, "local_latest_tag", return_value=None),
            contextlib.redirect_stdout(out),
        ):
            code = check_consumers.main(["--local", str(self.checkouts)])
        self.assertEqual(code, 1, out.getvalue())
        self.assertIn("the pin check cannot pass", out.getvalue())

    def test_the_pin_check_uses_the_shared_latest_release_read(self):
        with mock.patch.object(check_consumers.core_pin, "latest_release", return_value="v1.4.0") as latest:
            self.assertEqual(check_consumers.latest_tag(None), "v1.4.0")
        latest.assert_called_once_with()


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


class ReleaseGateCheckTest(unittest.TestCase):
    """The pin gate the sync inserts into a consumer's own release workflow, above the packager."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.checkouts = Path(self.tmp.name)
        self.workflow = self.checkouts / "legacy-forever" / ".github" / "workflows" / "release.yml"
        self.workflow.parent.mkdir(parents=True)

    def write(self, gate_before=True, gate=True, packager=True):
        lines = ["name: Release", "", "jobs:", "  release:", "    steps:"]
        if gate_before and gate:
            lines += [
                "      - name: Verify the ForeverCore pin is core's latest release",
                "        run: python3 -m tools.forever_tools.core_pin --latest",
            ]
        if packager:
            lines.append("      - uses: BigWigsMods/packager@01e8631a69c69d7654c788d152630d5fed9e3812 # v2.7.0")
        if not gate_before and gate:
            lines += [
                "      - name: Verify the ForeverCore pin is core's latest release",
                "        run: python3 -m tools.forever_tools.core_pin --latest",
            ]
        self.workflow.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def check(self):
        return check_consumers.check_release_gate("legacy-forever", "main", self.checkouts)

    def test_retired_wago_token_fails(self):
        self.write()
        with self.workflow.open("a") as stream:
            stream.write("          WAGO_API_TOKEN: token\n")
        self.assertTrue(any("retired WAGO_API_TOKEN" in failure for failure in self.check()))

    def test_the_gate_above_the_packager_passes(self):
        self.write()
        self.assertEqual(self.check(), [])

    def test_a_missing_gate_fails(self):
        self.write(gate=False)
        failures = self.check()
        self.assertEqual(len(failures), 1)
        self.assertIn("no ForeverCore pin gate", failures[0])
        self.assertIn("tools.forever_tools.core_pin --latest", failures[0])

    def test_a_gate_after_the_packager_fails(self):
        self.write(gate_before=False)
        failures = self.check()
        self.assertEqual(len(failures), 1)
        self.assertIn("after the packager", failures[0])

    def test_a_gate_without_the_latest_command_fails(self):
        self.workflow.write_text(
            "jobs:\n  release:\n    steps:\n"
            "      - name: Verify the ForeverCore pin is core's latest release\n"
            "        run: python3 -m tools.forever_tools.core_pin\n"
            "      - uses: BigWigsMods/packager@01e8631a69c69d7654c788d152630d5fed9e3812\n",
            encoding="utf-8",
        )
        failures = self.check()
        self.assertEqual(len(failures), 1)
        self.assertIn("must run `python3 -m tools.forever_tools.core_pin --latest`", failures[0])

    def test_a_workflow_without_a_packager_is_left_alone(self):
        self.write(packager=False, gate=False)
        self.assertEqual(self.check(), [])


class EmbedCheckTest(unittest.TestCase):
    """A consumer that opts in to the embedded core runs the embed step before every packager."""

    PACKAGER = "      - uses: BigWigsMods/packager@01e8631a69c69d7654c788d152630d5fed9e3812 # v2.7.0\n"
    EMBED = "      - name: Embed ForeverCore\n        run: python3 -m tools.forever_tools.embed\n"
    HOLD = "      - name: Hold for the fleet\n        run: python3 -m tools.forever_tools.fleet\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.checkouts = Path(self.tmp.name)
        self.repo = self.checkouts / "legacy-forever"
        (self.repo / ".github" / "workflows").mkdir(parents=True)
        (self.repo / ".pkgmeta").write_text("package-as: LegacyForever\n", encoding="utf-8")

    def write(self, embed_field=True, release=True, ci=True):
        field = "## X-Forever-Core-Embed: 1\n" if embed_field else ""
        (self.repo / "LegacyForever.toc").write_text(
            f"## Interface: 16001\n## OptionalDeps: ForeverCore\n{field}\nMain.lua\n", encoding="utf-8"
        )
        for name, embedded in (("release.yml", release), ("ci.yml", ci)):
            steps = (self.EMBED if embedded else "") + (self.HOLD if name == "release.yml" else "") + self.PACKAGER
            (self.repo / ".github" / "workflows" / name).write_text(
                f"jobs:\n  a:\n    steps:\n{steps}", encoding="utf-8"
            )

    def check(self):
        return check_consumers.check_embed("legacy-forever", "main", self.checkouts)

    def test_embed_before_each_packager_passes(self):
        self.write()
        self.assertEqual(self.check(), [])

    def test_a_consumer_that_does_not_opt_in_is_left_alone(self):
        self.write(embed_field=False, release=False, ci=False)
        self.assertEqual(self.check(), [])

    def test_a_release_without_the_embed_step_fails(self):
        self.write(release=False)
        failures = self.check()
        self.assertEqual(len(failures), 1)
        self.assertIn("release.yml: a packager step with no", failures[0])

    def test_an_embed_after_the_packager_fails(self):
        self.write()
        (self.repo / ".github" / "workflows" / "ci.yml").write_text(
            f"jobs:\n  a:\n    steps:\n{self.PACKAGER}{self.EMBED}", encoding="utf-8"
        )
        failures = self.check()
        self.assertEqual(len(failures), 1)
        self.assertIn("ci.yml: a packager step with no", failures[0])

    def test_an_embed_in_another_job_does_not_cover_the_packager(self):
        self.write()
        (self.repo / ".github" / "workflows" / "release.yml").write_text(
            f"jobs:\n  test:\n    steps:\n{self.EMBED}\n  release:\n    steps:\n{self.HOLD}{self.PACKAGER}",
            encoding="utf-8",
        )
        failures = self.check()
        self.assertEqual(len(failures), 1)
        self.assertIn("release.yml: a packager step with no", failures[0])

    def test_a_commented_embed_does_not_cover_the_packager(self):
        self.write()
        (self.repo / ".github" / "workflows" / "release.yml").write_text(
            f"jobs:\n  a:\n    steps:\n      # run: python3 -m tools.forever_tools.embed\n{self.HOLD}{self.PACKAGER}",
            encoding="utf-8",
        )
        self.assertEqual(len(self.check()), 1)

    def release(self, text):
        (self.repo / ".github" / "workflows" / "release.yml").write_text(text, encoding="utf-8")
        return [failure for failure in self.check() if "release.yml" in failure]

    def test_a_jobs_line_with_a_comment_still_splits_the_jobs(self):
        self.write()
        failures = self.release(
            f"jobs: # build and release\n  test:\n    steps:\n{self.EMBED}\n"
            f"  r:\n    steps:\n{self.HOLD}{self.PACKAGER}"
        )
        self.assertEqual(len(failures), 1)
        self.assertIn("a packager step with no", failures[0])

    def test_an_embed_named_only_in_a_shell_comment_embeds_nothing(self):
        self.write()
        step = "      - run: echo build # python3 -m tools.forever_tools.embed\n"
        self.assertEqual(len(self.release(f"jobs:\n  a:\n    steps:\n{step}{self.HOLD}{self.PACKAGER}")), 1)

    def test_an_embed_step_that_never_runs_embeds_nothing(self):
        self.write()
        step = "      - if: false\n        run: python3 -m tools.forever_tools.embed\n"
        self.assertEqual(len(self.release(f"jobs:\n  a:\n    steps:\n{step}{self.HOLD}{self.PACKAGER}")), 1)

    def test_a_block_run_embed_covers_the_packager(self):
        self.write()
        step = (
            "      - name: Embed\n        run: |\n          echo start\n"
            "          python3 -m tools.forever_tools.embed\n"
        )
        self.assertEqual(self.release(f"jobs:\n  a:\n    steps:\n{step}{self.HOLD}{self.PACKAGER}"), [])

    def test_a_release_without_the_fleet_hold_fails(self):
        self.write()
        failures = self.release(f"jobs:\n  a:\n    steps:\n{self.EMBED}{self.PACKAGER}")
        self.assertEqual(len(failures), 1)
        self.assertIn("tools.forever_tools.fleet", failures[0])

    def test_a_commented_out_packager_is_no_packager(self):
        self.write()
        failures = self.release(f"jobs:\n  a:\n    steps:\n{self.EMBED}      # - uses: BigWigsMods/packager@v2\n")
        self.assertEqual(len(failures), 1)
        self.assertIn("runs no BigWigs packager", failures[0])


if __name__ == "__main__":
    unittest.main()
