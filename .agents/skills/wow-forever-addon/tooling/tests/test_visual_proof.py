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

    def mapped_checkout(self):
        """A checkout whose `Lib` folder installs as a sibling and whose `Core` external does too."""
        root = self.elsewhere()
        (root / "Main.toc").write_text(
            "## Interface: 16001\n## Version: @project-version@\nMain.lua\n", encoding="utf-8"
        )
        (root / "Main.lua").write_text("main", encoding="utf-8")
        (root / "Lib").mkdir()
        (root / "Lib/Lib.toc").write_text(
            "## Interface: 16001\n## Version: @project-version@\nLib.lua\n", encoding="utf-8"
        )
        (root / "Lib/Lib.lua").write_text("lib", encoding="utf-8")
        (root / "Lib/Unused.lua").write_text("unused\n", encoding="utf-8")
        (root / "media").mkdir()
        (root / "media/icon.tga").write_bytes(b"texture")
        (root / "media/icon-400.png").write_bytes(b"store icon")
        (root / "tools").mkdir()
        (root / "tools/forever-core.txt").write_text("v1.0.0\n", encoding="utf-8")
        (root / ".pkgmeta").write_text(
            "package-as: Main\n\nmove-folders:\n  Main/Lib: Lib\n  Main/ForeverCore: Core\n\n"
            "externals:\n  ForeverCore: https://github.com/cjber/forever-core/releases/download/"
            "v1.0.0/ForeverCore-v1.0.0-forever.zip\n\n"
            "ignore:\n  - media/icon-400.png\n",
            encoding="utf-8",
        )
        return root

    def mapped_package(self, source):
        """The real BigWigs release root for `mapped_checkout`, written independently of the module."""
        release = self.elsewhere() / "release"
        main = release / "Main"
        main.mkdir(parents=True)
        toc = (source / "Main.toc").read_text(encoding="utf-8").replace("@project-version@", "v1.0.0")
        (main / "Main.toc").write_bytes(toc.replace("\n", "\r\n").encode())
        (main / "Main.lua").write_bytes((source / "Main.lua").read_bytes().replace(b"\n", b"\r\n"))
        (main / "media").mkdir()
        (main / "media/icon.tga").write_bytes((source / "media/icon.tga").read_bytes())
        lib = release / "Lib"
        lib.mkdir()
        lib_toc = (source / "Lib/Lib.toc").read_text(encoding="utf-8").replace("@project-version@", "v1.0.0")
        (lib / "Lib.toc").write_bytes(lib_toc.replace("\n", "\r\n").encode())
        for name in ("Lib.lua", "Unused.lua"):
            (lib / name).write_bytes((source / "Lib" / name).read_bytes().replace(b"\n", b"\r\n"))
        core = release / "Core"
        core.mkdir()
        (core / "Core.toc").write_text("## Interface: 16001\nCore.lua\n", encoding="utf-8")
        (core / "Core.lua").write_text("core", encoding="utf-8")
        return release

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

    def test_move_folders_installs_a_source_owned_sibling_with_release_keys(self):
        root = self.checkout(
            "package-as: ForeverCore\n\nmove-folders:\n  ForeverCore/Lib: Lib\n\n"
            "ignore:\n  - media/icon-400.png\n  - media/icon.svg\n"
        )
        (root / "Lib").mkdir()
        (root / "Lib/Lib.toc").write_text("## Interface: 16001\nLib.lua\n", encoding="utf-8")
        (root / "Lib/Lib.lua").write_text("lib", encoding="utf-8")
        self.assertEqual(visual_proof.unsupported(root), [])
        packaged = visual_proof.packaged_runtime_files(root)
        self.assertIn("ForeverCore/Core.lua", packaged)
        self.assertIn("Lib/Lib.lua", packaged)
        with self.assertRaisesRegex(ValueError, "compare_package"):
            visual_proof.compare_installed(root, root)

    def test_move_folders_binds_an_unloaded_sibling_script(self):
        root = self.checkout(
            "package-as: A\n\nmove-folders:\n  A/Mod: AMod\n\nignore:\n  - media/icon-400.png\n  - media/icon.svg\n"
        )
        (root / "A.toc").write_text("A.lua\n", encoding="utf-8")
        (root / "A.lua").write_text("a", encoding="utf-8")
        (root / "Mod").mkdir()
        (root / "Mod/AMod.toc").write_text("## Interface: 16001\n", encoding="utf-8")
        (root / "Mod/Extra.lua").write_text("extra", encoding="utf-8")
        self.assertNotIn(root / "Mod/Extra.lua", visual_proof.runtime_files(root))
        self.assertIn("AMod/Extra.lua", visual_proof.packaged_runtime_files(root))
        self.assertEqual(visual_proof.unsupported(root), [])
        candidate = visual_proof.candidate_digest(root)
        source = visual_proof.input_digest(root)
        (root / "Mod/Extra.lua").write_text("changed", encoding="utf-8")
        self.assertNotEqual(candidate, visual_proof.candidate_digest(root))
        self.assertNotEqual(source, visual_proof.input_digest(root))

    def test_external_only_move_keeps_the_legacy_single_folder_identity(self):
        root = self.checkout(
            "package-as: Main\n\nmove-folders:\n  Main/ForeverCore: ForeverCore\n\n"
            "externals:\n  ForeverCore: https://github.com/cjber/forever-core/releases/download/"
            "v1.0.0/ForeverCore-v1.0.0-forever.zip\n\n"
            "ignore:\n  - media/icon-400.png\n  - media/icon.svg\n"
        )
        (root / "tools").mkdir()
        (root / "tools/forever-core.txt").write_text("v1.0.0\n", encoding="utf-8")
        layout = pkgmeta.read(root).layout(root)
        self.assertFalse(layout.mapped)
        self.assertEqual(visual_proof.unsupported(root), [])
        packaged = visual_proof.packaged_runtime_files(root)
        self.assertIn("Core.lua", packaged)
        self.assertNotIn("ForeverCore/Core.lua", packaged)
        self.assertEqual(
            visual_proof.candidate_digest(root),
            "49ead3c803b4dc40d3b3170fb72843dedd5d15cf6d1e22d537157ff535dbb45c",
        )
        self.assertTrue(visual_proof.compare_installed(root, root).equivalent)

    @mock.patch.object(visual_proof, "image_hash", return_value="a" * 64)
    def test_verify_a_mapped_layout_requires_release_package(self, _image_hash):
        root = self.mapped_checkout()
        path = self.written(root, self.proof(root, tested_artifact="source-tree"))
        problems = visual_proof.verify(root, ["Main.lua"], path)
        self.assertTrue(any("release-package" in problem for problem in problems))
        path = self.written(root, self.proof(root, tested_artifact="release-package"))
        self.assertEqual(visual_proof.verify(root, ["Main.lua"], path), [])

    def test_mapped_candidate_is_symmetric_with_the_release_root(self):
        source = self.mapped_checkout()
        layout = pkgmeta.read(source).layout(source)
        self.assertTrue(layout.mapped)
        release = self.mapped_package(source)
        self.assertEqual(visual_proof.candidate_digest(source), visual_proof.package_candidate_digest(release, layout))
        comparison = visual_proof.compare_package(source, release)
        self.assertTrue(comparison.equivalent, comparison)
        self.assertEqual(comparison.missing, ())
        self.assertEqual(comparison.differing, ())
        self.assertEqual(comparison.extra, ())
        self.assertEqual(comparison.unexpected_folders, ())
        self.assertEqual(comparison.external_bound_by_pin, ("Core",))
        self.assertEqual(comparison.external_missing, ())

    def test_a_mapped_sibling_change_moves_both_identities(self):
        source = self.mapped_checkout()
        layout = pkgmeta.read(source).layout(source)
        release = self.mapped_package(source)
        candidate = visual_proof.candidate_digest(source)
        packaged = visual_proof.package_candidate_digest(release, layout)
        source_digest = visual_proof.input_digest(source)
        (source / "Lib/Unused.lua").write_text("changed\n", encoding="utf-8")
        self.assertNotEqual(candidate, visual_proof.candidate_digest(source))
        self.assertNotEqual(source_digest, visual_proof.input_digest(source))
        (release / "Lib/Unused.lua").write_text("changed\n", encoding="utf-8")
        self.assertNotEqual(packaged, visual_proof.package_candidate_digest(release, layout))

    def test_compare_package_reports_missing_extra_and_unexpected_entries(self):
        source = self.mapped_checkout()
        release = self.mapped_package(source)
        (release / "Lib/Lib.lua").unlink()
        comparison = visual_proof.compare_package(source, release)
        self.assertIn("Lib/Lib.lua", comparison.missing)
        self.assertFalse(comparison.equivalent)
        release = self.mapped_package(source)
        (release / "Lib/Extra.lua").write_text("extra", encoding="utf-8")
        comparison = visual_proof.compare_package(source, release)
        self.assertIn("Lib/Extra.lua", comparison.extra)
        self.assertFalse(comparison.equivalent)
        release = self.mapped_package(source)
        (release / "Lib/Lib.lua").write_bytes(b"edited")
        comparison = visual_proof.compare_package(source, release)
        self.assertIn("Lib/Lib.lua", comparison.differing)
        self.assertFalse(comparison.equivalent)
        release = self.mapped_package(source)
        (release / "Lib/Extra.tga").write_bytes(b"extra texture")
        self.assertTrue(visual_proof.compare_package(source, release).equivalent)
        release = self.mapped_package(source)
        (release / "Old").mkdir()
        comparison = visual_proof.compare_package(source, release)
        self.assertEqual(comparison.unexpected_folders, ("Old",))
        self.assertFalse(comparison.equivalent)

    def test_compare_package_checks_external_folder_and_toc_not_bytes(self):
        source = self.mapped_checkout()
        release = self.mapped_package(source)
        (release / "Core/Core.lua").write_text("different external bytes", encoding="utf-8")
        comparison = visual_proof.compare_package(source, release)
        self.assertTrue(comparison.equivalent, comparison)
        self.assertEqual(comparison.external_bound_by_pin, ("Core",))
        (release / "Core/Core.toc").unlink()
        comparison = visual_proof.compare_package(source, release)
        self.assertIn("Core/Core.toc: missing from the external addon folder", comparison.external_missing)
        self.assertFalse(comparison.equivalent)
        release = self.mapped_package(source)
        (release / "Core").rename(release / "Core-moved")
        comparison = visual_proof.compare_package(source, release)
        self.assertIn("Core: missing external addon folder", comparison.external_missing)
        self.assertFalse(comparison.equivalent)

    def test_externals_reads_first_level_keys_not_nested_properties(self):
        root = self.mapped_checkout()
        (root / ".pkgmeta").write_text(
            "package-as: Main\n\nmove-folders:\n  Main/ForeverCore: Core\n\n"
            "externals:\n  ForeverCore:\n    url: https://github.com/cjber/forever-core/releases/download/"
            "v1.0.0/ForeverCore-v1.0.0-forever.zip\n    tag: v1.0.0\n",
            encoding="utf-8",
        )
        manifest = pkgmeta.read(root)
        self.assertEqual(manifest.externals, ("ForeverCore",))
        layout = manifest.layout(root)
        self.assertEqual(layout.external, ("Core",))
        self.assertEqual(layout.external_sources, ("ForeverCore",))

    def test_arbitrary_or_unpinned_external_moves_are_refused(self):
        root = self.mapped_checkout()
        (root / ".pkgmeta").write_text(
            "package-as: Main\n\nmove-folders:\n  Main/Other: Other\n\n"
            "externals:\n  Other: https://example.invalid/download/v1.0.0/Other.zip\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "not the supported ForeverCore external"):
            pkgmeta.read(root).layout(root)
        root = self.mapped_checkout()
        (root / "tools/forever-core.txt").unlink()
        with self.assertRaisesRegex(ValueError, "not bound"):
            pkgmeta.read(root).layout(root)
        root = self.mapped_checkout()
        (root / "tools/forever-core.txt").write_text("v2.0.0\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "official pinned release"):
            pkgmeta.read(root).layout(root)
        root = self.mapped_checkout()
        (root / "tools/forever-core.txt").write_text("main\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not an immutable release tag"):
            pkgmeta.read(root).layout(root)

    def test_external_requires_the_official_repository_url_and_exact_key_case(self):
        official = "https://github.com/cjber/forever-core/releases/download/v1.0.0/ForeverCore-v1.0.0-forever.zip"
        for url in (
            "https://example.invalid/download/v1.0.0/ForeverCore-v1.0.0-forever.zip",
            "https://github.com/someone/forever-core/releases/download/v1.0.0/ForeverCore-v1.0.0-forever.zip",
        ):
            root = self.mapped_checkout()
            (root / ".pkgmeta").write_text(
                f"package-as: Main\n\nmove-folders:\n  Main/ForeverCore: Core\n\nexternals:\n  ForeverCore: {url}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "official pinned release"):
                pkgmeta.read(root).layout(root)
        root = self.mapped_checkout()
        (root / ".pkgmeta").write_text(
            f"package-as: Main\n\nmove-folders:\n  Main/ForeverCore: Core\n\nexternals:\n  forevercore: {official}\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "stale source"):
            pkgmeta.read(root).layout(root)

    def test_raw_move_whitespace_and_yaml_booleans_are_refused(self):
        cases = {
            "  Main/Lib : Lib\n": "trailing whitespace",
            "  Main/Lib: Lib \n": "trailing whitespace",
            "  Main/Lib:\tLib\n": "starts with a tab",
            "  Main/Lib: On\n": "YAML boolean",
            "  Main/Lib: No\n": "YAML boolean",
        }
        for move, message in cases.items():
            root = self.mapped_checkout()
            (root / ".pkgmeta").write_text(
                "package-as: Main\n\nmove-folders:\n" + move + "\nignore:\n  - media/icon-400.png\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, message, msg=move):
                pkgmeta.read(root).layout(root)

    @mock.patch.object(visual_proof, "image_hash", return_value="a" * 64)
    def test_dot_root_is_resolved_for_support_and_verify(self, _image_hash):
        root = self.mapped_checkout()
        self.written(root, self.proof(root, tested_artifact="release-package"))
        original = Path.cwd()
        self.addCleanup(os.chdir, original)
        os.chdir(root)
        self.assertEqual(visual_proof.unsupported(Path(".")), [])
        self.assertTrue(visual_proof.candidate_digest(Path(".")))
        self.assertEqual(visual_proof.verify(Path("."), ["Main.lua"], Path(".visual-proof.json")), [])

    def test_package_candidate_digest_refuses_a_missing_owned_folder(self):
        source = self.mapped_checkout()
        layout = pkgmeta.read(source).layout(source)
        release = self.mapped_package(source)
        (release / "Lib").rename(release / "Lib-old")
        with self.assertRaisesRegex(ValueError, "Lib: missing from the package root"):
            visual_proof.package_candidate_digest(release, layout)
        comparison = visual_proof.compare_package(source, release)
        self.assertIn("Lib/Lib.lua", comparison.missing)
        self.assertFalse(comparison.equivalent)

    def test_package_root_duplicate_case_folders_are_refused(self):
        source = self.mapped_checkout()
        layout = pkgmeta.read(source).layout(source)
        release = self.mapped_package(source)
        duplicate = release / "lib"
        duplicate.mkdir()
        (duplicate / "Lib.toc").write_text("## Interface: 16001\nInjected.lua\n", encoding="utf-8")
        (duplicate / "Injected.lua").write_text("injected", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate case-insensitive top-level entries"):
            visual_proof.package_candidate_digest(release, layout)
        with self.assertRaisesRegex(ValueError, "duplicate case-insensitive top-level entries"):
            visual_proof.compare_package(source, release)
        release = self.mapped_package(source)
        (release / "core").mkdir()
        (release / "core/Core.toc").write_text("## Interface: 16001\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate case-insensitive top-level entries"):
            visual_proof.package_candidate_digest(release, layout)
        with self.assertRaisesRegex(ValueError, "duplicate case-insensitive top-level entries"):
            visual_proof.compare_package(source, release)

    def test_bad_move_paths_targets_and_overlaps_are_refused(self):
        cases = {
            "outside package-as": ("  Other/Lib: Lib\n", "outside package-as"),
            "parent path": ("  Main/../Lib: Lib\n", "dot, parent"),
            "absolute path": ("  /Main/Lib: Lib\n", "absolute path"),
            "backslash path": ("  Main\\\\Lib: Lib\n", "backslash"),
            "quoted key": ('  "Main/Lib": Lib\n', "quoted move key"),
            "nested target": ("  Main/Lib: Lib/Sub\n", "one folder name"),
            "dot target": ("  Main/Lib: .Hidden\n", "dot or parent"),
            "parent target": ("  Main/Lib: ..\n", "dot or parent"),
            "package itself": ("  Main: Main\n", "moves the package folder itself"),
            "duplicate target": ("  Main/Lib: Lib\n  Main/Other: Lib\n", "collides"),
            "case duplicate target": ("  Main/Lib: Lib\n  Main/Other: LIB\n", "collides"),
        }
        for label, (move, message) in cases.items():
            root = self.mapped_checkout()
            (root / ".pkgmeta").write_text(
                "package-as: Main\n\nmove-folders:\n" + move + "\nignore:\n  - media/icon-400.png\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, message, msg=label):
                pkgmeta.read(root).layout(root)
        root = self.mapped_checkout()
        (root / ".pkgmeta").write_text(
            "package-as: Main\n\nmove-folders:\n  Main/Lib: Lib\n  Main/Lib/Sub: Sub\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "overlap"):
            pkgmeta.read(root).layout(root)
        root = self.mapped_checkout()
        (root / ".pkgmeta").write_text("package-as: Main\n\nmove-folders:\n  Main/Missing: Missing\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale"):
            pkgmeta.read(root).layout(root)
        root = self.mapped_checkout()
        (root / "ForeverCore").mkdir()
        (root / "ForeverCore/Core.toc").write_text("## Interface: 16001\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "both an externals entry and a checkout path"):
            pkgmeta.read(root).layout(root)
        root = self.mapped_checkout()
        (root / "lib").mkdir()
        (root / "lib/Lib.toc").write_text("## Interface: 16001\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "case-duplicate"):
            pkgmeta.read(root).layout(root)

    def test_mapped_release_paths_that_collide_ignoring_case_are_refused(self):
        source = self.mapped_checkout()
        (source / "Lib/Foo.lua").write_text("foo", encoding="utf-8")
        (source / "Lib/foo.lua").write_text("foo", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "case-collides"):
            visual_proof.packaged_runtime_files(source)
        with self.assertRaisesRegex(ValueError, "case-collides"):
            visual_proof.candidate_digest(source)

    def test_a_moved_folder_without_its_target_toc_is_refused(self):
        source = self.mapped_checkout()
        (source / "Lib/Lib.toc").unlink()
        problems = visual_proof.unsupported(source)
        self.assertTrue(any("no shipped Lib.toc" in problem for problem in problems), problems)
        with self.assertRaisesRegex(ValueError, "no shipped Lib.toc"):
            visual_proof.candidate_digest(source)

    def test_a_toc_loading_a_relocated_path_is_refused(self):
        source = self.mapped_checkout()
        with (source / "Main.toc").open("a") as stream:
            stream.write("Lib/Lib.lua\n")
        problems = visual_proof.unsupported(source)
        self.assertTrue(any("installs it under Lib" in problem for problem in problems), problems)
        with self.assertRaisesRegex(ValueError, "installs it under Lib"):
            visual_proof.candidate_digest(source)
        source = self.mapped_checkout()
        with (source / "Lib/Lib.toc").open("a") as stream:
            stream.write("../Main.lua\n")
        problems = visual_proof.unsupported(source)
        self.assertTrue(any("installs it under Main" in problem for problem in problems), problems)
        source = self.mapped_checkout()
        (source / "Bindings.xml").write_text('<Bindings><Script file="Lib/Lib.lua"/></Bindings>', encoding="utf-8")
        problems = visual_proof.unsupported(source)
        self.assertTrue(any("installs it under Lib" in problem for problem in problems), problems)

    def test_unmapped_candidate_hash_is_stable(self):
        root = self.checkout()
        self.assertEqual(
            visual_proof.candidate_digest(root),
            "49ead3c803b4dc40d3b3170fb72843dedd5d15cf6d1e22d537157ff535dbb45c",
        )

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

    def toc(self, path, text="Core.lua\n", interface=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(("## Interface: 16001\n" if interface else "") + text, encoding="utf-8")
        return path

    def test_project_toc_files_matches_the_packagers_exact_vendor_list(self):
        root = self.checkout(
            "package-as: ForeverCore\n\nmove-folders:\n  ForeverCore/LibAHTab: LibAHTab\n\n"
            "ignore:\n  - media/icon-400.png\n  - media/icon.svg\n"
        )
        self.toc(root / "ForeverCore-Mainline.toc")
        self.toc(root / "ForeverCore_Classic.toc")
        self.toc(root / "ForeverCore-Camelot.toc")
        self.toc(root / "ForeverCore-Bogus.toc")
        self.toc(root / "LibAHTab/LibAHTab.toc", "LibAHTab.lua\n")
        self.toc(root / "LibAHTab/LibAHTab-Wrath.toc", "LibAHTab.lua\n")
        self.toc(root / "LibAHTab/LibAHTab_wotlkc.toc", "LibAHTab.lua\n")
        self.toc(root / "LibAHTab/LibAHTab-Camelot.toc", "LibAHTab.lua\n")
        found = [path.relative_to(root).as_posix() for path in pkgmeta.project_toc_files(root)]
        self.assertEqual(
            found,
            [
                "ForeverCore.toc",
                "ForeverCore-Mainline.toc",
                "ForeverCore_Classic.toc",
                "ForeverCore-Camelot.toc",
                "LibAHTab/LibAHTab.toc",
                "LibAHTab/LibAHTab-Wrath.toc",
                "LibAHTab/LibAHTab-Camelot.toc",
            ],
        )
        self.assertEqual([path.relative_to(root).as_posix() for path in pkgmeta.localization_toc_files(root)], found)

    def test_project_toc_files_skips_a_nested_move_and_derives_an_implicit_package(self):
        root = self.checkout(
            "package-as: ForeverCore\n\nmove-folders:\n  ForeverCore/LibAHTab: Lib/Nested\n\n"
            "ignore:\n  - media/icon-400.png\n  - media/icon.svg\n"
        )
        self.toc(root / "LibAHTab/Nested.toc", "LibAHTab.lua\n")
        found = [path.relative_to(root).as_posix() for path in pkgmeta.project_toc_files(root)]
        self.assertEqual(found, ["ForeverCore.toc"])
        (root / ".pkgmeta").write_text("move-folders:\n  ForeverCore/LibAHTab: LibAHTab\n", encoding="utf-8")
        self.assertEqual(pkgmeta.project_toc_files(root), [root / "ForeverCore.toc"])
        self.toc(root / "A.toc")
        self.assertEqual(pkgmeta.project_toc_files(root), [root / "A.toc"])
        (root / "A.toc").unlink()
        (root / "ForeverCore.toc").rename(root / "ForeverCore-Camelot.toc")
        with self.assertRaisesRegex(ValueError, "Ambiguous addon name"):
            pkgmeta.project_toc_files(root)

    def test_project_toc_files_skips_move_key_syntax_the_vendor_cannot_resolve(self):
        for move in ("  LibAHTab: LibAHTab\n", '  "ForeverCore/LibAHTab": LibAHTab\n'):
            root = self.checkout(
                "package-as: ForeverCore\n\nmove-folders:\n"
                + move
                + "\nignore:\n  - media/icon-400.png\n  - media/icon.svg\n"
            )
            self.toc(root / "LibAHTab/LibAHTab.toc", "LibAHTab.lua\n")
            self.assertEqual(pkgmeta.project_toc_files(root), [root / "ForeverCore.toc"], move)

    def test_project_toc_files_ignores_a_hidden_root_toc_for_the_implicit_package(self):
        root = self.root()
        (root / "ForeverCore.toc").unlink()
        self.toc(root / ".Hidden.toc")
        self.toc(root / "Visible.toc")
        self.assertEqual(pkgmeta.project_toc_files(root), [root / "Visible.toc"])
        (root / "Visible.toc").unlink()
        with self.assertRaisesRegex(ValueError, "root addon TOC"):
            pkgmeta.project_toc_files(root)

    def test_project_toc_files_fails_closed_without_a_selected_root_toc(self):
        empty = self.elsewhere()
        with self.assertRaisesRegex(ValueError, "root addon TOC"):
            pkgmeta.project_toc_files(empty)
        root = self.checkout()
        (root / "ForeverCore.toc").unlink()
        with self.assertRaisesRegex(ValueError, "matching package-as"):
            pkgmeta.project_toc_files(root)

    def test_localization_toc_files_requires_interface_metadata(self):
        root = self.checkout()
        self.toc(root / "ForeverCore-Mainline.toc", interface=False)
        self.assertEqual(pkgmeta.project_toc_files(root), [root / "ForeverCore.toc", root / "ForeverCore-Mainline.toc"])
        self.assertEqual(pkgmeta.localization_toc_files(root), [root / "ForeverCore.toc"])
        (root / "ForeverCore.toc").write_text("Core.lua\n", encoding="utf-8")
        self.assertEqual(pkgmeta.localization_toc_files(root), [])

    def test_localization_toc_files_accepts_flavor_only_interface(self):
        root = self.checkout()
        (root / "ForeverCore.toc").write_text(
            '## Interface-Forever: 16001\n## Notes: @localization(locale="enUS", format="lua_additive_table")@\n'
            "Core.lua\n",
            encoding="utf-8",
        )
        self.assertEqual(pkgmeta.localization_toc_files(root), [root / "ForeverCore.toc"])
        (root / "ForeverCore.toc").write_text("## interface-forever: 16001\nCore.lua\n", encoding="utf-8")
        self.assertEqual(pkgmeta.localization_toc_files(root), [root / "ForeverCore.toc"])
        (root / "ForeverCore.toc").write_text("## Interface: 16001,16002\nCore.lua\n", encoding="utf-8")
        self.assertEqual(pkgmeta.localization_toc_files(root), [root / "ForeverCore.toc"])

    def test_localization_toc_files_refuses_unmodelled_interface_forms(self):
        root = self.checkout()
        (root / "ForeverCore.toc").write_text(
            '## Interface:\n## Notes: @localization(locale="enUS")@\nCore.lua\n', encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "would not run"):
            pkgmeta.localization_toc_files(root)
        (root / "ForeverCore.toc").write_text("## Interface: not-a-version\nCore.lua\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported Interface metadata"):
            pkgmeta.localization_toc_files(root)
        (root / "ForeverCore.toc").write_text("## Interface-Forever: nope\nCore.lua\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported Interface metadata"):
            pkgmeta.localization_toc_files(root)
        (root / "ForeverCore.toc").write_text(
            "#@alpha@\n## Interface: 16001\n#@end-alpha@\nCore.lua\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "conditional Interface metadata"):
            pkgmeta.localization_toc_files(root)

    def test_localization_toc_files_omits_an_empty_interface_without_tokens(self):
        root = self.checkout()
        (root / "ForeverCore.toc").write_text("## Interface:\nCore.lua\n", encoding="utf-8")
        self.assertEqual(pkgmeta.localization_toc_files(root), [])

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
