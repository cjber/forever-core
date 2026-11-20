import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from forever_tools import core_archive, package


class CoreArchiveTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.release = self.root / ".release"
        self.release.mkdir()
        (self.root / "tools").mkdir()
        self.pin = self.root / "tools/forever-core.txt"
        self.pin.write_text("v1.15.3\n")
        self.toc = self.root / "FieldGuideForever.toc"
        self.toc.write_text("## OptionalDeps: ForeverCore\n## X-Forever-Core: v1.15.3\n")

    def bridge(self, version):
        core = self.release / "ForeverCore"
        core.mkdir()
        (core / "ForeverCore.toc").write_text(f"## Version: {version}\n")

    def embed(self, version="1.15.3", chunks=", 42"):
        self.toc.write_text("## X-Forever-Core-Embed: 1\n")
        core = self.release / "FieldGuideForever/Libs/ForeverCore"
        core.mkdir(parents=True)
        major, minor, patch_version = core_archive.version(version)
        build = major * 1000000 + minor * 1000 + patch_version
        digest = "a" * 64
        runtime = f'host.ForeverCoreCopy = ForeverCoreLoader.Begin(addon, {build}, "{digest}"{chunks})\n'.encode()
        # BigWigs writes CRLF after embed hashes the source.
        (core / "Begin.lua").write_bytes(runtime.replace(b"\n", b"\r\n"))
        (core / "bundle.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "standalone": False,
                    "version": version,
                    "build": build,
                    "source_digest": digest,
                    "files": {"Libs/ForeverCore/Begin.lua": hashlib.sha256(runtime).hexdigest()},
                }
            )
        )
        return core

    def zip(self):
        (self.release / self.toc.stem).mkdir(exist_ok=True)
        (self.release / self.toc.stem / self.toc.name).write_bytes(self.toc.read_bytes())
        with zipfile.ZipFile(self.release / "FieldGuideForever-v0.8.15-forever.zip", "w") as archive:
            for path in sorted(self.release.rglob("*")):
                if path.is_file() and path.suffix != ".zip":
                    archive.write(path, path.relative_to(self.release))

    def test_field_guide_carries_stale_bridge_even_with_current_pin(self):
        self.bridge("v1.14.5")
        self.zip()
        failures = core_archive.check(self.root, self.release, "v1.15.3")
        self.assertTrue(any("carries v1.14.5" in failure and "pins" in failure for failure in failures))
        self.assertTrue(any("latest release is v1.15.3" in failure for failure in failures))
        with patch.object(Path, "cwd", return_value=self.root):
            self.assertEqual(
                core_archive.main(["--release-dir", str(self.release), "--latest"], fetch=lambda: "v1.15.3"), 1
            )

    def test_ci_package_entrypoint_rejects_stale_bridge(self):
        self.bridge("v1.14.5")
        with (
            patch.object(package, "check", return_value=[]),
            patch.object(package.core_pin, "check", return_value=[]),
            patch.object(package.widget_handlers, "check_root", return_value=[]),
            patch.object(package.lua51, "check", return_value=[]),
            patch.object(package, "run_specs", return_value=[]),
        ):
            self.assertEqual(package.main(self.root, package.Policy(addons=(self.toc.stem, "ForeverCore")), []), 1)

    def test_current_bridge_accepts_stamped_version_without_v(self):
        self.bridge("1.15.3")
        self.assertEqual(core_archive.check(self.root, self.release, "v1.15.3"), [])

    def test_embed_only_rejects_even_current_bridge_and_checks_additional_copies(self):
        self.embed()
        self.bridge("v1.15.3")
        other = self.release / "AnotherAddon/Libs/ForeverCore"
        other.mkdir(parents=True)
        failures = core_archive.check(self.root, self.release)
        self.assertTrue(any("must not install a top-level ForeverCore" in failure for failure in failures))
        self.assertTrue(any("AnotherAddon/Libs/ForeverCore" in failure for failure in failures))

    def test_embedded_stamp_and_hashes_are_checked(self):
        core = self.embed()
        self.assertEqual(core_archive.check(self.root, self.release, "v1.15.3"), [])
        begin = core / "Begin.lua"
        begin.write_bytes(begin.read_bytes() + b"-- unexpectedly changed\n")
        self.assertIn("file disagrees with its bundle hash", core_archive.check(self.root, self.release)[0])
        begin.write_bytes(b"stale begin file\n")
        self.assertIn("disagree with Begin.lua", core_archive.check(self.root, self.release)[0])

    def test_embedded_stamp_before_chunk_counts(self):
        # Packages built before ForeverCore 1.15.4 stamp Begin without the chunk count;
        # the store audit still reads them.
        self.embed(chunks="")
        self.assertEqual(core_archive.check(self.root, self.release, "v1.15.3"), [])

    def test_embedded_version_comes_from_copy(self):
        self.embed("1.15.2")
        self.assertIn("carries v1.15.2", core_archive.check(self.root, self.release)[0])

    def test_only_a_nonconsumer_can_ship_without_core(self):
        self.assertIn("must carry the bridge", core_archive.check(self.root, self.release)[0])
        self.toc.write_text("## X-Forever-Core-Embed: 1\n")
        self.assertIn("must carry the opted-in", core_archive.check(self.root, self.release)[0])
        self.toc.write_text("## Title: Independent addon\n")
        self.assertEqual(core_archive.check(self.root, self.release), [])

    def test_dependency_and_development_pin_do_not_imply_a_bundle(self):
        for dependency in ("OptionalDeps", "Dependencies"):
            with self.subTest(dependency=dependency):
                self.toc.write_text(f"## {dependency}: ForeverCore\n")
                self.assertEqual(core_archive.check(self.root, self.release), [])

    def test_zip_refuses_noncanonical_member_paths(self):
        self.embed()
        self.zip()
        original = next(self.release.glob("*.zip")).read_bytes()
        self.assertEqual(core_archive.check_zip(self.root, original, "v1.15.3"), [])
        for member in ("./ForeverCore/ForeverCore.toc", "Other/./file", "Other//file"):
            with self.subTest(member=member):
                data = io.BytesIO(original)
                with zipfile.ZipFile(data, "a") as archive:
                    archive.writestr(member, "## Version: 1.0.0")
                failures = core_archive.check_zip(self.root, data.getvalue(), "v1.15.3")
                self.assertTrue(any("unsafe zip member" in failure for failure in failures), failures)

    def test_latest_checks_zip_and_fails_closed_on_lookup_failure(self):
        self.bridge("v1.15.3")
        self.zip()

        def unavailable():
            raise OSError("release read failed")

        args = ["--release-dir", str(self.release), "--latest"]
        output = self.root / "outputs"
        with patch.object(Path, "cwd", return_value=self.root), patch.dict(os.environ, GITHUB_OUTPUT=str(output)):
            self.assertEqual(core_archive.main(args, fetch=unavailable), 1)
            self.assertFalse(output.exists())
            self.assertEqual(core_archive.main(args, fetch=lambda: "v1.15.3"), 0)
            self.assertIn("sha256=", output.read_text())
            self.assertEqual(core_archive.main(args, fetch=lambda: "v1.15.2"), 1)
