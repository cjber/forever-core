import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from forever_tools import pkgmeta, visual_proof

IMAGE = {"url": "https://github.com/cjber/proof/raw/" + "a" * 40 + "/image.png", "sha256": "a" * 64}
PLAIN_PKGMETA = (
    "package-as: ForeverCore\n\nplain-copy:\n  - Vendor.lua\n\nignore:\n  - media/icon-400.png\n  - media/icon.svg\n"
)


class VisualProofTest(unittest.TestCase):
    def root(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "ForeverCore.toc").write_text("Core.lua\nUI/Main.lua\n", encoding="utf-8")
        (root / "Core.lua").write_text("core", encoding="utf-8")
        (root / "UI").mkdir()
        (root / "UI/Main.lua").write_text("ui", encoding="utf-8")
        return root

    def elsewhere(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def checkout(self, pkgmeta=None):
        """A checkout shaped like Core's: a store icon the release ignores and a texture it ships."""
        root = self.root()
        toc = root / "ForeverCore.toc"
        toc.write_text("## Interface: 16001\n## Version: @project-version@\n" + toc.read_text(), encoding="utf-8")
        (root / "media").mkdir()
        (root / "media/icon.tga").write_bytes(b"texture")
        (root / "media/icon-400.png").write_bytes(b"store icon")
        (root / "media/icon.svg").write_bytes(b"<svg/>")
        if pkgmeta is None:
            pkgmeta = "package-as: ForeverCore\n\nignore:\n  - media/icon-400.png\n  - media/icon.svg\n"
        (root / ".pkgmeta").write_text(pkgmeta, encoding="utf-8")
        return root

    def package(self, source, destination, version="v1.9.0"):
        """Write the files a release installs, the way the pinned packager lays them out.

        Deliberately independent of `forever_tools.pkgmeta`: CRLF text, the substituted TOC version and no
        ignored media, so the comparison against the source candidate is a real one.
        """
        destination.mkdir(parents=True)
        toc = (source / "ForeverCore.toc").read_text(encoding="utf-8").replace("@project-version@", version)
        (destination / "ForeverCore.toc").write_bytes(toc.replace("\n", "\r\n").encode())
        for name in ("Core.lua", "UI/Main.lua"):
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((source / name).read_bytes().replace(b"\n", b"\r\n"))
        (destination / "media").mkdir()
        (destination / "media/icon.tga").write_bytes((source / "media/icon.tga").read_bytes())
        return destination

    def proof(self, root, **overrides):
        digest = visual_proof.input_digest(root)
        candidate = overrides.pop("candidate", None)
        evidence = {
            "input_digest": digest,
            "runtime_sha256": digest,
            "candidate": candidate if candidate is not None else visual_proof.candidate_digest(root),
            "tested_artifact": "source-tree",
            "client_build": "16001",
            "flows": [{"name": "open", "steps": ["open"], "result": "pass"}],
            "images": [IMAGE],
        }
        evidence.update(overrides)
        return evidence

    def written(self, root, proof):
        path = root / ".visual-proof.json"
        path.write_text(json.dumps(proof), encoding="utf-8")
        return path

    def test_auto_loaded_bindings_and_their_script_graph_are_runtime(self):
        root = self.checkout()
        bindings = root / "Bindings.xml"
        bindings.write_text(
            '<Bindings><Script file="Bindings.lua"/><Binding name="TEST" key="ALT-G"/></Bindings>', encoding="utf-8"
        )
        (root / "Bindings.lua").write_text("-- bindings", encoding="utf-8")
        runtime = visual_proof.runtime_files(root)
        self.assertIn(bindings, runtime)
        self.assertIn(root / "Bindings.lua", runtime)
        candidate = visual_proof.candidate_digest(root)
        source = visual_proof.input_digest(root)
        self.assertTrue(visual_proof.requires_proof(root, ["Bindings.xml"]))
        bindings.write_text(
            '<Bindings><Script file="Bindings.lua"/><Binding name="TEST" key="ALT-H"/></Bindings>', encoding="utf-8"
        )
        self.assertNotEqual(candidate, visual_proof.candidate_digest(root))
        self.assertNotEqual(source, visual_proof.input_digest(root))
        (root / "Bindings.lua").write_text("-- changed bindings", encoding="utf-8")
        self.assertNotEqual(candidate, visual_proof.candidate_digest(root))

    def test_pkgmeta_reads_the_packagers_own_selection_rules(self):
        root = self.checkout("package-as: ForeverCore\n\n# ignored\nignore:\n  - 'media/icon-400.png'\n  - media\n")
        manifest = pkgmeta.read(root)
        self.assertFalse(manifest.keeps("media/icon-400.png"))
        self.assertFalse(manifest.keeps("media/icon.tga"))
        self.assertFalse(manifest.keeps(".agents/tool.py"))
        self.assertTrue(manifest.keeps("Core.lua"))
        self.assertIsNone(pkgmeta.read(self.elsewhere()))

    def test_a_second_toc_addon_cannot_escape_the_candidate(self):
        root = self.checkout()
        (root / "Lib").mkdir()
        (root / "Lib/Lib.toc").write_text("Lib.lua\n", encoding="utf-8")
        (root / "Lib/Lib.lua").write_text("lib", encoding="utf-8")
        self.assertIn("Lib/Lib.lua", visual_proof.packaged_runtime_files(root))
        candidate = visual_proof.candidate_digest(root)
        source = visual_proof.input_digest(root)
        (root / "Lib/Lib.lua").write_text("changed lib", encoding="utf-8")
        self.assertNotEqual(candidate, visual_proof.candidate_digest(root))
        self.assertNotEqual(source, visual_proof.input_digest(root))

    @unittest.skipUnless(shutil.which("git"), "git mirrors the packager's untracked rule")
    def test_a_release_leaves_out_untracked_and_gitignored_runtime_files(self):
        root = self.checkout()
        (root / ".gitignore").write_text("media/generated.png\n", encoding="utf-8")
        for command in (("init", "-q"), ("add", ".")):
            subprocess.run(["git", "-C", str(root), *command], check=True, capture_output=True)
        (root / "media/new.png").write_bytes(b"untracked")
        (root / "media/generated.png").write_bytes(b"gitignored")
        packaged = set(visual_proof.packaged_runtime_files(root))
        # release.sh adds every path `git ls-files --others` reports, untracked or ignored, to its ignore list.
        self.assertNotIn("media/new.png", packaged)
        self.assertNotIn("media/generated.png", packaged)
        self.assertIn("media/icon.tga", packaged)
        candidate = visual_proof.candidate_digest(root)
        (root / "media/icon.tga").write_bytes(b"tracked change")
        self.assertNotEqual(candidate, visual_proof.candidate_digest(root))

    def test_move_folders_relocating_a_runtime_file_is_refused(self):
        root = self.checkout(
            "package-as: ForeverCore\n\nmove-folders:\n  ForeverCore/Lib: Lib\n\n"
            "ignore:\n  - media/icon-400.png\n  - media/icon.svg\n"
        )
        (root / "Lib").mkdir()
        (root / "Lib/Lib.toc").write_text("Lib.lua\n", encoding="utf-8")
        (root / "Lib/Lib.lua").write_text("lib", encoding="utf-8")
        problems = visual_proof.unsupported(root)
        self.assertIn(
            "Lib/Lib.lua: .pkgmeta move-folders relocates this shipped runtime file, which visual proof cannot model",
            problems,
        )
        with self.assertRaises(ValueError):
            visual_proof.candidate_digest(root)
        with self.assertRaises(ValueError):
            visual_proof.compare_installed(root, root)

    def test_move_folders_relocating_an_unloaded_shipped_script_is_refused(self):
        root = self.checkout(
            "package-as: A\n\nmove-folders:\n  A/Mod: AMod\n\nignore:\n  - media/icon-400.png\n  - media/icon.svg\n"
        )
        (root / "A.toc").write_text("A.lua\n", encoding="utf-8")
        (root / "A.lua").write_text("a", encoding="utf-8")
        (root / "Mod").mkdir()
        (root / "Mod/Extra.lua").write_text("extra", encoding="utf-8")
        self.assertNotIn(root / "Mod/Extra.lua", visual_proof.runtime_files(root))
        self.assertIn("Mod/Extra.lua", visual_proof.packaged_runtime_files(root))
        self.assertEqual(
            visual_proof.unsupported(root),
            [
                "Mod/Extra.lua: .pkgmeta move-folders relocates this shipped runtime file, "
                "which visual proof cannot model"
            ],
        )
        with self.assertRaisesRegex(ValueError, "Mod/Extra.lua"):
            visual_proof.candidate_digest(root)
        with self.assertRaisesRegex(ValueError, "Mod/Extra.lua"):
            visual_proof.compare_installed(root, root)

    def test_move_folders_for_an_absent_external_is_not_a_relocation(self):
        root = self.checkout(
            "package-as: ForeverCore\n\nmove-folders:\n  ForeverCore/ForeverCore: ForeverCore\n\n"
            "ignore:\n  - media/icon-400.png\n  - media/icon.svg\n"
        )
        self.assertEqual(visual_proof.unsupported(root), [])
        self.assertTrue(visual_proof.candidate_digest(root))

    @mock.patch.object(visual_proof, "image_hash", return_value="a" * 64)
    def test_verify_reports_an_unmodelled_move_folders(self, _image_hash):
        root = self.checkout(
            "package-as: ForeverCore\n\nmove-folders:\n  ForeverCore/Lib: Lib\n\n"
            "ignore:\n  - media/icon-400.png\n  - media/icon.svg\n"
        )
        (root / "Lib").mkdir()
        (root / "Lib/Lib.toc").write_text("Lib.lua\n", encoding="utf-8")
        (root / "Lib/Lib.lua").write_text("lib", encoding="utf-8")
        problems = visual_proof.verify(root, ["UI/Main.lua"], self.written(root, self.proof(root, candidate="0" * 64)))
        self.assertTrue(any("move-folders" in problem for problem in problems))

    def test_package_extraction_matches_the_source_candidate(self):
        source = self.checkout()
        extracted = self.package(source, self.elsewhere() / "ForeverCore")
        self.assertEqual(visual_proof.candidate_digest(source), visual_proof.candidate_digest(extracted))

    def test_candidate_excludes_ignored_media_and_differs_from_the_source_digest(self):
        root = self.checkout()
        packaged = set(visual_proof.packaged_runtime_files(root))
        self.assertNotIn("media/icon-400.png", packaged)
        self.assertNotIn("media/icon.svg", packaged)
        self.assertIn("media/icon.tga", packaged)
        # The old source digest included the store icon, so it could not name an install.
        self.assertNotEqual(visual_proof.candidate_digest(root), visual_proof.input_digest(root))

    def test_ignored_media_changes_the_input_digest_but_not_the_candidate(self):
        root = self.checkout()
        candidate = visual_proof.candidate_digest(root)
        source = visual_proof.input_digest(root)
        (root / "media/icon-400.png").write_bytes(b"new store icon")
        self.assertEqual(candidate, visual_proof.candidate_digest(root))
        self.assertNotEqual(source, visual_proof.input_digest(root))
        self.assertTrue(visual_proof.requires_proof(root, ["media/icon-400.png"]))

    def test_a_packaging_policy_change_requires_fresh_proof(self):
        root = self.checkout()
        source = visual_proof.input_digest(root)
        self.assertTrue(visual_proof.requires_proof(root, [".pkgmeta"]))
        self.assertTrue(visual_proof.requires_proof(root, ["pkgmeta.yaml"]))
        (root / ".pkgmeta").write_text("package-as: ForeverCore\n\nignore:\n  - media/icon.tga\n", encoding="utf-8")
        self.assertNotEqual(source, visual_proof.input_digest(root))

    def test_core_pin_changes_source_provenance_only(self):
        root = self.checkout()
        (root / "tools").mkdir()
        pin = root / "tools/forever-core.txt"
        pin.write_text("v1.8.0", encoding="utf-8")
        candidate = visual_proof.candidate_digest(root)
        source = visual_proof.input_digest(root)
        pin.write_text("v1.8.1", encoding="utf-8")
        self.assertEqual(candidate, visual_proof.candidate_digest(root))
        self.assertNotEqual(source, visual_proof.input_digest(root))
        self.assertTrue(visual_proof.requires_proof(root, ["tools/forever-core.txt"]))

    def test_a_tagged_and_an_untagged_package_have_the_same_candidate(self):
        source = self.checkout()
        release = self.package(source, self.elsewhere() / "tagged", "v9.9.9")
        untagged = self.package(source, self.elsewhere() / "untagged", "v1.8.0-4-g262187d")
        self.assertEqual(visual_proof.candidate_digest(release), visual_proof.candidate_digest(untagged))

    def test_a_source_tree_install_is_equivalent_with_extras_reported(self):
        root = self.checkout()
        comparison = visual_proof.compare_installed(root, root)
        self.assertTrue(comparison.equivalent)
        self.assertEqual(comparison.missing, ())
        self.assertEqual(comparison.differing, ())
        self.assertIn("media/icon-400.png", comparison.extra)

    def test_an_installed_folder_reports_missing_differing_and_stale_files(self):
        source = self.checkout()
        installed = self.package(source, self.elsewhere() / "installed")
        (installed / "media/stale.tga").write_bytes(b"stale")
        (installed / "UI/Main.lua").write_bytes(b"edited")
        comparison = visual_proof.compare_installed(source, installed)
        self.assertFalse(comparison.equivalent)
        self.assertIn("media/stale.tga", comparison.extra)
        self.assertIn("UI/Main.lua", comparison.differing)
        (installed / "Core.lua").unlink()
        comparison = visual_proof.compare_installed(source, installed)
        self.assertIn("Core.lua", comparison.missing)

    def test_an_extra_lua_or_toc_in_the_installed_folder_is_not_equivalent(self):
        source = self.checkout()
        installed = self.package(source, self.elsewhere() / "installed")
        (installed / "Stale.lua").write_text("stale", encoding="utf-8")
        comparison = visual_proof.compare_installed(source, installed)
        self.assertIn("Stale.lua", comparison.extra)
        self.assertFalse(comparison.equivalent)
        (installed / "Stale.lua").unlink()
        (installed / "Stale.toc").write_text("Stale.lua\n", encoding="utf-8")
        self.assertFalse(visual_proof.compare_installed(source, installed).equivalent)

    def test_an_extra_asset_in_a_source_tree_install_is_harmless(self):
        root = self.checkout()
        self.assertTrue(visual_proof.compare_installed(root, root).equivalent)

    def test_an_unloaded_packaged_script_binds_both_digests_and_is_compared(self):
        source = self.checkout()
        (source / "Unused.lua").write_text("unused\n", encoding="utf-8")
        self.assertIn("Unused.lua", visual_proof.packaged_runtime_files(source))
        candidate = visual_proof.candidate_digest(source)
        source_digest = visual_proof.input_digest(source)
        installed = self.package(source, self.elsewhere() / "installed")
        # The packager's line-ending filter applies even though no TOC loads the file.
        (installed / "Unused.lua").write_bytes(b"unused\r\n")
        self.assertEqual(candidate, visual_proof.candidate_digest(installed))
        self.assertTrue(visual_proof.compare_installed(source, installed).equivalent)
        # A changed shipped script invalidates the identity even though nothing loads it.
        (source / "Unused.lua").write_text("changed\n", encoding="utf-8")
        self.assertNotEqual(candidate, visual_proof.candidate_digest(source))
        self.assertNotEqual(source_digest, visual_proof.input_digest(source))
        comparison = visual_proof.compare_installed(source, installed)
        self.assertIn("Unused.lua", comparison.differing)
        self.assertFalse(comparison.equivalent)

    def test_an_injected_unloaded_script_with_no_source_file_is_fatal(self):
        source = self.checkout()
        installed = self.package(source, self.elsewhere() / "installed")
        (installed / "Injected.lua").write_text("injected", encoding="utf-8")
        comparison = visual_proof.compare_installed(source, installed)
        self.assertEqual(comparison.extra, ("Injected.lua",))
        self.assertFalse(comparison.equivalent)

    @unittest.skipUnless(shutil.which("git"), "git mirrors the packager's untracked rule")
    def test_an_untracked_unloaded_script_is_not_shipped_or_equivalent(self):
        source = self.checkout()
        for command in (("init", "-q"), ("add", ".")):
            subprocess.run(["git", "-C", str(source), *command], check=True, capture_output=True)
        (source / "Unused.lua").write_text("untracked", encoding="utf-8")
        self.assertNotIn("Unused.lua", visual_proof.packaged_runtime_files(source))
        installed = self.package(source, self.elsewhere() / "installed")
        (installed / "Unused.lua").write_text("untracked", encoding="utf-8")
        comparison = visual_proof.compare_installed(source, installed)
        self.assertIn("Unused.lua", comparison.extra)
        self.assertFalse(comparison.equivalent)

    def test_a_plain_copy_crlf_file_has_the_same_candidate_everywhere(self):
        root = self.checkout(PLAIN_PKGMETA)
        vendor = root / "Vendor.lua"
        vendor.write_bytes(b"local vendor = true\r\n")
        with (root / "ForeverCore.toc").open("a") as stream:
            stream.write("Vendor.lua\n")
        installed = self.package(root, self.elsewhere() / "plain")
        # The packager copies a plain-copy file raw, and an extraction carries no .pkgmeta to say so.
        (installed / "Vendor.lua").write_bytes(vendor.read_bytes())
        self.assertEqual(visual_proof.candidate_digest(root), visual_proof.candidate_digest(installed))
        self.assertTrue(visual_proof.compare_installed(root, installed).equivalent)

    def test_a_plain_copy_file_is_asked_to_model_its_tokens(self):
        root = self.checkout(PLAIN_PKGMETA)
        vendor = root / "Vendor.lua"
        vendor.write_text("local hash = '@project-hash@'", encoding="utf-8")
        with (root / "ForeverCore.toc").open("a") as stream:
            stream.write("Vendor.lua\n")
        # An extraction has no .pkgmeta saying Vendor.lua is plain-copy, so the checkout refuses it too.
        self.assertEqual(
            visual_proof.unmodeled_directives(root),
            ["Vendor.lua: packager substitution @project-hash@ is not modelled by the candidate digest"],
        )
        with self.assertRaisesRegex(ValueError, "@project-hash@"):
            visual_proof.candidate_digest(root)
        with self.assertRaisesRegex(ValueError, "@project-hash@"):
            visual_proof.compare_installed(root, root)
        installed = self.package(root, self.elsewhere() / "plain")
        (installed / "Vendor.lua").write_bytes(vendor.read_bytes())
        with self.assertRaisesRegex(ValueError, "@project-hash@"):
            visual_proof.candidate_digest(installed)

    def test_a_plain_copy_toc_bom_and_interface_line_are_refused(self):
        root = self.checkout(PLAIN_PKGMETA.replace("Vendor.lua", "ForeverCore.toc"))
        toc = root / "ForeverCore.toc"
        toc.write_bytes(b"\xef\xbb\xbf" + toc.read_bytes())
        self.assertTrue(any("UTF-8 BOM" in problem for problem in visual_proof.unmodeled_directives(root)))
        toc.write_bytes(toc.read_bytes()[3:] + b"## Interface-Classic: 11507\n")
        self.assertTrue(any("## Interface-" in problem for problem in visual_proof.unmodeled_directives(root)))

    def test_a_literal_token_the_packager_does_not_replace_is_not_rejected(self):
        root = self.checkout()
        (root / "Core.lua").write_text("local note = 'see @readme@ and @no-lib-strip@'", encoding="utf-8")
        self.assertEqual(visual_proof.unmodeled_directives(root), [])

    def test_an_ignored_directory_is_not_shipped(self):
        root = self.checkout("package-as: ForeverCore\n\nignore:\n  - media\n")
        packaged = set(visual_proof.packaged_runtime_files(root))
        self.assertFalse(packaged & {"media/icon.tga", "media/icon-400.png", "media/icon.svg"})

    @mock.patch.object(visual_proof, "image_hash", return_value="a" * 64)
    def test_an_unmodelled_packager_substitution_fails_closed(self, _image_hash):
        root = self.checkout()
        (root / "Core.lua").write_text("local hash = '@project-hash@'", encoding="utf-8")
        self.assertEqual(
            visual_proof.unmodeled_directives(root),
            ["Core.lua: packager substitution @project-hash@ is not modelled by the candidate digest"],
        )
        path = self.written(root, self.proof(root, candidate="0" * 64))
        problems = visual_proof.verify(root, ["Core.lua"], path)
        self.assertTrue(any("@project-hash@" in problem for problem in problems))

    def test_the_toc_version_token_is_modelled(self):
        self.assertEqual(visual_proof.unmodeled_directives(self.checkout()), [])

    def test_docs_only_does_not_need_proof(self):
        self.assertEqual(visual_proof.verify(self.root(), ["docs/README.md"]), [])

    def test_runtime_change_requires_proof(self):
        root = self.root()
        problems = visual_proof.verify(root, ["UI/Main.lua"], root / ".visual-proof.json")
        self.assertIn("missing", problems[0])

    def test_rejects_stale_and_failed_proof(self):
        root = self.root()
        proof = {
            "input_digest": "wrong",
            "client_build": "16001",
            "candidate": "x",
            "flows": [{"result": "fail"}],
            "images": [],
        }
        path = root / ".visual-proof.json"
        path.write_text(json.dumps(proof), encoding="utf-8")
        problems = visual_proof.verify(root, ["UI/Main.lua"], path)
        self.assertTrue(any("input_digest" in problem for problem in problems))
        self.assertTrue(any("passing flow" in problem for problem in problems))
        self.assertTrue(any("image" in problem for problem in problems))

    @mock.patch.object(visual_proof, "image_hash", return_value="a" * 64)
    def test_accepts_pinned_matching_image(self, _image_hash):
        root = self.root()
        path = self.written(root, self.proof(root))
        self.assertEqual(visual_proof.verify(root, ["UI/Main.lua"], path), [])

    @mock.patch.object(visual_proof, "image_hash", return_value="a" * 64)
    def test_arbitrary_candidate_hash_is_rejected(self, _image_hash):
        root = self.root()
        path = self.written(root, self.proof(root, candidate="b" * 64))
        problems = visual_proof.verify(root, ["UI/Main.lua"], path)
        self.assertTrue(any("candidate" in problem for problem in problems))

    @mock.patch.object(visual_proof, "image_hash", return_value="a" * 64)
    def test_tested_artifact_is_required_and_limited(self, _image_hash):
        root = self.root()
        path = self.written(root, self.proof(root, tested_artifact=""))
        problems = visual_proof.verify(root, ["UI/Main.lua"], path)
        self.assertTrue(any("tested_artifact" in problem for problem in problems))
        path = self.written(root, self.proof(root, tested_artifact="release-package"))
        self.assertEqual(visual_proof.verify(root, ["UI/Main.lua"], path), [])

    def test_metadata_and_tooling_do_not_require_proof(self):
        self.assertFalse(visual_proof.requires_proof(self.root(), ["README.md", "CHANGELOG.md", ".agents/tool.py"]))

    def test_relative_root_has_same_digest(self):
        root = self.root()
        self.assertEqual(visual_proof.input_digest(root), visual_proof.input_digest(root / "."))

    def test_toc_metadata_and_nested_xml_are_hashed(self):
        root = self.root()
        before = visual_proof.input_digest(root)
        (root / "ForeverCore.toc").write_text("## Interface: 16001\nCore.lua\nUI/Main.lua\n")
        self.assertNotEqual(before, visual_proof.input_digest(root))
        (root / "UI/Load.xml").write_text('<Ui><Script file="Child.lua"/></Ui>')
        (root / "UI/Child.lua").write_text("child")
        with (root / "ForeverCore.toc").open("a") as stream:
            stream.write("UI/Load.xml\n")
        before = visual_proof.input_digest(root)
        (root / "UI/Child.lua").write_text("changed child")
        self.assertNotEqual(before, visual_proof.input_digest(root))

    def test_packager_version_stamp_does_not_change_runtime(self):
        root = self.root()
        toc = root / "ForeverCore.toc"
        toc.write_text("## Version: @project-version@\n" + toc.read_text())
        before = visual_proof.candidate_digest(root)
        toc.write_text(toc.read_text().replace("@project-version@", "v1.7.4-dev+1234567"))
        self.assertEqual(before, visual_proof.candidate_digest(root))

    def test_artwork_changes_invalidate_digest(self):
        root = self.root()
        (root / "media").mkdir()
        art = root / "media/icon.blp"
        art.write_bytes(b"first")
        before = visual_proof.input_digest(root)
        art.write_bytes(b"second")
        self.assertNotEqual(before, visual_proof.input_digest(root))
        self.assertTrue(visual_proof.requires_proof(root, ["media/icon.blp"]))

    def test_move_folders_without_package_as_is_refused(self):
        root = self.checkout(
            "move-folders:\n  ForeverCore/Lib: Lib\n\nignore:\n  - media/icon-400.png\n  - media/icon.svg\n"
        )
        (root / "Lib").mkdir()
        (root / "Lib/Lib.toc").write_text("Lib.lua\n", encoding="utf-8")
        (root / "Lib/Lib.lua").write_text("lib", encoding="utf-8")
        self.assertIn(pkgmeta.MOVE_WITHOUT_PACKAGE, visual_proof.unsupported(root))
        with self.assertRaisesRegex(ValueError, "move-folders needs package-as"):
            pkgmeta.read(root).relocates("Lib/Lib.lua")
        with self.assertRaises(ValueError):
            visual_proof.candidate_digest(root)
        with self.assertRaises(ValueError):
            visual_proof.compare_installed(root, root)

    def test_a_project_toc_bom_is_refused(self):
        root = self.checkout()
        toc = root / "ForeverCore.toc"
        toc.write_bytes(b"\xef\xbb\xbf" + toc.read_bytes())
        self.assertEqual(
            visual_proof.unmodeled_directives(root),
            [
                "ForeverCore.toc: TOC starts with a UTF-8 BOM, which the packager strips and the candidate digest "
                "cannot model"
            ],
        )

    @mock.patch.object(visual_proof, "image_hash", return_value="a" * 64)
    def test_a_project_toc_interface_dash_line_is_refused(self, _image_hash):
        root = self.checkout()
        toc = root / "ForeverCore.toc"
        toc.write_bytes(toc.read_bytes() + b"## Interface-Classic: 11507\n")
        self.assertEqual(
            visual_proof.unmodeled_directives(root),
            [
                "ForeverCore.toc: TOC has a '## Interface-' line, which the packager removes and the candidate "
                "digest cannot model"
            ],
        )
        problems = visual_proof.verify(root, ["UI/Main.lua"], self.written(root, self.proof(root, candidate="0" * 64)))
        self.assertTrue(any("## Interface-" in problem for problem in problems))

    def test_candidate_and_compare_refuse_an_unmodelled_token(self):
        root = self.checkout()
        (root / "Core.lua").write_text("local hash = '@project-hash@'", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "@project-hash@"):
            visual_proof.candidate_digest(root)
        with self.assertRaisesRegex(ValueError, "@project-hash@"):
            visual_proof.compare_installed(root, root)

    def test_candidate_and_compare_refuse_a_toc_bom(self):
        root = self.checkout()
        toc = root / "ForeverCore.toc"
        toc.write_bytes(b"\xef\xbb\xbf" + toc.read_bytes())
        with self.assertRaisesRegex(ValueError, "UTF-8 BOM"):
            visual_proof.candidate_digest(root)
        with self.assertRaisesRegex(ValueError, "UTF-8 BOM"):
            visual_proof.compare_installed(root, root)
        toc.write_bytes(toc.read_bytes()[3:] + b"## Interface-Classic: 11507\n")
        with self.assertRaisesRegex(ValueError, "## Interface-"):
            visual_proof.candidate_digest(root)

    def test_the_cli_refuses_a_packager_change_it_cannot_model(self):
        root = self.checkout()
        (root / "Core.lua").write_text("local hash = '@project-hash@'", encoding="utf-8")
        tooling = Path(__file__).resolve().parents[1]
        environment = {**os.environ, "PYTHONPATH": str(tooling)}
        for arguments in (["--digests"], ["--compare", "."]):
            result = subprocess.run(
                [sys.executable, "-m", "forever_tools.visual_proof", *arguments],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1, arguments)
            self.assertIn("@project-hash@", result.stderr)

    def test_an_upper_case_asset_is_shipped_and_compared(self):
        source = self.checkout()
        (source / "media/Icon.PNG").write_bytes(b"upper icon")
        installed = self.package(source, self.elsewhere() / "installed")
        (installed / "media/Icon.PNG").write_bytes(b"upper icon")
        comparison = visual_proof.compare_installed(source, installed)
        self.assertIn("media/Icon.PNG", visual_proof.packaged_runtime_files(source))
        self.assertTrue(comparison.equivalent, comparison)

    def test_upper_case_extra_scripts_are_not_equivalent(self):
        source = self.checkout()
        installed = self.package(source, self.elsewhere() / "installed")
        (installed / "shippedIcon.PNG").write_bytes(b"extra icon")
        (installed / "Extra.LUA").write_text("extra", encoding="utf-8")
        (installed / "Addon.TOC").write_text("Extra.LUA\n", encoding="utf-8")
        comparison = visual_proof.compare_installed(source, installed)
        for name in ("shippedIcon.PNG", "Extra.LUA", "Addon.TOC"):
            self.assertIn(name, comparison.extra)
        self.assertFalse(comparison.equivalent)

    def test_text_filter_stays_case_sensitive_like_the_packagers_bash_case(self):
        root = self.root()
        (root / "Core.LUA").write_bytes(b"local upper = 1\r\n")
        with (root / "ForeverCore.toc").open("a") as stream:
            stream.write("Core.LUA\n")
        extracted = self.elsewhere() / "extracted"
        extracted.mkdir()
        (extracted / "ForeverCore.toc").write_bytes((root / "ForeverCore.toc").read_bytes())
        (extracted / "Core.lua").write_bytes((root / "Core.lua").read_bytes())
        (extracted / "UI").mkdir()
        (extracted / "UI/Main.lua").write_bytes((root / "UI/Main.lua").read_bytes())
        (extracted / "Core.LUA").write_bytes(b"local upper = 1\r\n")
        self.assertEqual(visual_proof.candidate_digest(root), visual_proof.candidate_digest(extracted))
        # `.LUA` is copied unchanged, so a line-ending difference is real bytes in both, not normalised away.
        (extracted / "Core.LUA").write_bytes(b"local upper = 1\n")
        self.assertNotEqual(visual_proof.candidate_digest(root), visual_proof.candidate_digest(extracted))

    def test_an_ignored_loaded_lua_file_is_refused(self):
        root = self.checkout("package-as: ForeverCore\n\nignore:\n  - UI/Main.lua\n")
        self.assertEqual(
            visual_proof.unsupported(root),
            ["UI/Main.lua: .pkgmeta ignore excludes this TOC/XML-loaded runtime file from the package"],
        )
        with self.assertRaisesRegex(ValueError, "UI/Main.lua"):
            visual_proof.packaged_runtime_files(root)
        with self.assertRaises(ValueError):
            visual_proof.candidate_digest(root)
        with self.assertRaises(ValueError):
            visual_proof.compare_installed(root, root)

    def test_a_git_failure_inside_a_work_tree_is_not_swallowed(self):
        root = self.checkout()

        def fake_run(command, *args, **kwargs):
            if "rev-parse" in command:
                return subprocess.CompletedProcess(command, 0, "true\n", "")
            raise subprocess.CalledProcessError(128, command, stderr="fatal: cannot read the index")

        with mock.patch.object(pkgmeta.subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(ValueError, "git failed to list untracked paths"):
                pkgmeta.read(root)

    @unittest.skipUnless(shutil.which("git"), "git mirrors the packager's untracked rule")
    def test_a_git_checkout_without_pkgmeta_still_applies_git_ignores(self):
        root = self.root()
        (root / ".gitignore").write_text("media/generated.png\n", encoding="utf-8")
        (root / "media").mkdir()
        (root / "media/tracked.tga").write_bytes(b"tracked")
        for command in (("init", "-q"), ("add", ".")):
            subprocess.run(["git", "-C", str(root), *command], check=True, capture_output=True)
        (root / "Untracked.lua").write_text("untracked", encoding="utf-8")
        (root / "media/generated.png").write_bytes(b"ignored")
        (root / "media/untracked.png").write_bytes(b"untracked")
        manifest = pkgmeta.read(root)
        self.assertIsNotNone(manifest)
        for name in ("Untracked.lua", "media/generated.png", "media/untracked.png"):
            self.assertFalse(manifest.keeps(name))
        self.assertTrue(manifest.keeps("Core.lua"))
        packaged = set(visual_proof.packaged_runtime_files(root))
        self.assertNotIn("Untracked.lua", packaged)
        self.assertNotIn("media/generated.png", packaged)
        self.assertNotIn("media/untracked.png", packaged)
        self.assertIn("media/tracked.tga", packaged)

    @unittest.skipUnless(shutil.which("git"), "git mirrors the packager's untracked rule")
    def test_a_git_checkout_without_pkgmeta_refuses_an_untracked_loaded_script(self):
        root = self.root()
        (root / "ForeverCore.toc").write_text("Core.lua\nGenerated.lua\n", encoding="utf-8")
        for command in (("init", "-q"), ("add", ".")):
            subprocess.run(["git", "-C", str(root), *command], check=True, capture_output=True)
        (root / "Generated.lua").write_text("generated", encoding="utf-8")
        self.assertFalse(pkgmeta.read(root).keeps("Generated.lua"))
        with self.assertRaisesRegex(ValueError, "Generated.lua"):
            visual_proof.packaged_runtime_files(root)
        with self.assertRaisesRegex(ValueError, "Generated.lua"):
            visual_proof.candidate_digest(root)

    @unittest.skipUnless(shutil.which("git"), "git mirrors the packager's untracked rule")
    def test_an_extraction_nested_in_a_checkout_is_still_an_extraction(self):
        outer = self.elsewhere()
        subprocess.run(["git", "-C", str(outer), "init", "-q"], check=True, capture_output=True)
        (outer / ".gitignore").write_text("release/\n", encoding="utf-8")
        extraction = outer / "release/ForeverCore"
        extraction.mkdir(parents=True)
        (extraction / "ForeverCore.toc").write_text("Core.lua\n", encoding="utf-8")
        (extraction / "Core.lua").write_text("core", encoding="utf-8")
        self.assertIsNone(pkgmeta.read(extraction))
        self.assertIn("Core.lua", visual_proof.packaged_runtime_files(extraction))

    def test_a_non_git_package_fixture_is_still_supported(self):
        root = self.checkout()
        self.assertTrue(pkgmeta.read(root).keeps("Core.lua"))

    def test_git_cannot_read_a_work_tree_by_itself(self):
        root = self.checkout()
        (root / ".git").mkdir()
        failed = subprocess.CompletedProcess(["git", "rev-parse"], 128, "", "fatal: detected dubious ownership")
        with mock.patch.object(pkgmeta.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(ValueError, "git cannot read the work tree"):
                pkgmeta.read(root)

    def test_a_non_git_fixture_ignores_a_git_rev_parse_failure(self):
        root = self.checkout()
        failed = subprocess.CompletedProcess(["git", "rev-parse"], 128, "", "fatal: not a git repository")
        with mock.patch.object(pkgmeta.subprocess, "run", return_value=failed):
            self.assertTrue(pkgmeta.read(root).keeps("Core.lua"))

    def test_pkgmeta_yaml_phase_mirrors_release_sh(self):
        root = self.checkout(
            "package-as: ForeverCore\n\nignore:\n  - media/icon.tga\n- media/icon-400.png\n"
            "plain\n  - media/icon.svg\nplain-copy:\n  - Vendor.lua\n"
        )
        manifest = pkgmeta.read(root)
        # An unindented line without a colon is not a phase change, so both later items still belong to `ignore`.
        self.assertFalse(manifest.keeps("media/icon.tga"))
        self.assertFalse(manifest.keeps("media/icon.svg"))
        # An unindented list item is not a phase change and not an item.
        self.assertTrue(manifest.keeps("media/icon-400.png"))
        self.assertTrue(manifest.kept_bytes("Vendor.lua"))

    def test_a_tab_indented_pkgmeta_line_is_refused(self):
        root = self.checkout("package-as: ForeverCore\n\nignore:\n\t- media/icon.tga\n")
        with self.assertRaisesRegex(ValueError, "leading tab"):
            pkgmeta.read(root)

    def test_a_lower_case_bindings_xml_is_found(self):
        root = self.checkout()
        (root / "bindings.xml").write_text(
            '<Bindings><Script file="bindings.lua"/><Binding name="TEST" key="ALT-G"/></Bindings>',
            encoding="utf-8",
        )
        (root / "bindings.lua").write_text("-- bindings", encoding="utf-8")
        files = visual_proof.runtime_files(root)
        self.assertIn(root / "bindings.xml", files)
        self.assertIn(root / "bindings.lua", files)

    def test_exact_bindings_xml_is_preferred_over_case_duplicates(self):
        root = self.checkout()
        (root / "Bindings.xml").write_text('<Bindings><Script file="Bindings.lua"/></Bindings>', encoding="utf-8")
        (root / "bindings.xml").write_text("<Bindings/>", encoding="utf-8")
        (root / "Bindings.lua").write_text("-- bindings", encoding="utf-8")
        files = visual_proof.runtime_files(root)
        self.assertIn(root / "Bindings.lua", files)
        self.assertNotIn(root / "bindings.xml", files)

    def test_ambiguous_bindings_case_duplicates_are_refused(self):
        root = self.checkout()
        (root / "BINDINGS.XML").write_text("<Bindings/>", encoding="utf-8")
        (root / "Bindings.XML").write_text("<Bindings/>", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "ambiguous case duplicates for Bindings.xml"):
            visual_proof.runtime_files(root)

    def test_a_shipped_types_asset_is_compared_not_permanently_missing(self):
        source = self.checkout()
        (source / "types").mkdir()
        (source / "types/Icon.TGA").write_bytes(b"type icon")
        installed = self.package(source, self.elsewhere() / "installed")
        (installed / "types").mkdir()
        (installed / "types/Icon.TGA").write_bytes(b"type icon")
        comparison = visual_proof.compare_installed(source, installed)
        self.assertIn("types/Icon.TGA", visual_proof.packaged_runtime_files(source))
        self.assertNotIn("types/Icon.TGA", comparison.missing)
        self.assertTrue(comparison.equivalent, comparison)
        # A source-tree install's LuaLS declarations under types/ stay out of the extras.
        (installed / "types/Forever.lua").write_text("---@class Forever", encoding="utf-8")
        self.assertTrue(visual_proof.compare_installed(source, installed).equivalent)
