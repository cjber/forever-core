"""Focused producer and generated-load-graph integration checks."""

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from build_embedded_core import check_bundle, compose_bundle, plan, release_build, write_bundle

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "tools" / ".cache"
CACHE.mkdir(parents=True, exist_ok=True)
ENTRY = b"""local addon, ns, core, resources = ...
assert(resources.template == (core.TrackerLine.template or "ForeverTrackerInteractiveLineTemplate"))
assert(core == ForeverCore)
ns.context = core.Register(addon)
ConsumerStarts = (ConsumerStarts or 0) + 1
"""


def reordered_source(destination, files):
    """Copy actual canonical inputs, changing only the German locale's TOC position."""
    for name in json.loads(files["Libs/ForeverCore/bundle.json"])["source_files"]:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    lines = (ROOT / "ForeverCore.toc").read_text().splitlines()
    german = next(line for line in lines if line.replace("\\", "/") == "Locales/deDE.lua")
    lines.remove(german)
    english = next(line for line in lines if line.replace("\\", "/") == "Locales/enUS.lua")
    lines.insert(lines.index(english), german)
    (destination / "ForeverCore.toc").write_text("\n".join(lines) + "\n")


class GeneratedBundleTests(unittest.TestCase):
    def test_composition_contract(self):
        core = plan(ROOT, "ConsumerA", "1.12.1", "ConsumerADB", ENTRY)
        toc = core["ConsumerA.toc"].replace(b"ForeverCoreReady.lua", b"UI/Main.xml\nConsumer.lua\nForeverCoreReady.lua")
        consumer = {
            "LICENSE": b"consumer licence",
            "THIRD_PARTY.md": b"consumer notices",
            "Consumer.lua": b"-- deferred consumer",
            "UI/Main.xml": b'<Ui><Script file="Early.lua"/><Texture file="../media/icon.tga"/></Ui>',
            "UI/Early.lua": b"-- eager consumer",
            "media/icon.tga": b"pixels",
        }
        files = compose_bundle(core, consumer, toc)
        manifest_name = "Libs/ForeverCore/bundle.json"
        before, after = json.loads(core[manifest_name]), json.loads(files[manifest_name])
        self.assertEqual(
            {k: v for k, v in before.items() if k != "files"}, {k: v for k, v in after.items() if k != "files"}
        )
        self.assertEqual(
            after["files"], {n: hashlib.sha256(b).hexdigest() for n, b in files.items() if n != manifest_name}
        )
        for name, data in core.items():
            if name not in (manifest_name, "ConsumerA.toc", "LICENSE", "THIRD_PARTY.md"):
                self.assertEqual(files[name], data)
        for name in (
            "ForeverCoreReady.lua",
            "Libs/ForeverCore/End.lua",
            "Libs/ForeverCore/new.lua",
            "Nested/Other.toc",
            "../escape",
            "/absolute",
            "./alias",
            "a//b",
            "C:/escape",
            "media/ICON.tga",
            "MEDIA/other.tga",
            "Libs/ForeverCore",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                compose_bundle(core, dict(consumer, **{name: b"bad"}), toc)
        lines = toc.splitlines()
        first = lines.index(b"Libs\\ForeverCore\\Core\\Loader.lua")
        lines[first], lines[first + 1] = lines[first + 1], lines[first]
        for bad in (
            b"\n".join(lines) + b"\n",
            toc.replace(b"Libs\\ForeverCore\\Begin.lua", b""),
            toc.replace(b"Consumer.lua", b"Missing.lua"),
            toc.replace(b"Consumer.lua", b"Consumer.lua\nConsumer.lua"),
            toc.replace(b"ForeverCoreReady.lua", b"ForeverCoreReady.lua\nConsumer.lua"),
            toc.replace(b"Libs\\ForeverCore\\Begin.lua", b"Libs\\ForeverCore\\End.lua"),
        ):
            with self.subTest(toc=bad), self.assertRaises(ValueError):
                compose_bundle(core, consumer, bad)
        with self.assertRaises(ValueError):
            compose_bundle(core, {**consumer, "Unused.lua": b"-- unexplained"}, toc)
        with self.assertRaises(ValueError):
            compose_bundle(core, {**consumer, "UI/Main.xml": b'<Ui><Script file="Missing.lua"/></Ui>'}, toc)
        with tempfile.TemporaryDirectory(prefix="composed-gate-", dir=CACHE) as directory:
            package = Path(directory) / "ConsumerA"
            write_bundle(package, files)
            check_bundle(package, files)
            target = package / "Consumer.lua"
            target.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "bytes differ"):
                check_bundle(package, files)
            target.unlink()
            with self.assertRaisesRegex(ValueError, "missing="):
                check_bundle(package, files)
            target.write_bytes(files["Consumer.lua"])
            (package / "extra").write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "extra="):
                check_bundle(package, files)

    def test_source_order_identity_and_artifact_gate(self):
        original = plan(ROOT, "ConsumerA", "1.12.1", "ConsumerADB", ENTRY)
        with tempfile.TemporaryDirectory(prefix="embedded-order-", dir=CACHE) as directory:
            source = Path(directory) / "source"
            reordered_source(source, original)
            for standalone in (False, True):
                folder, saved, entry, prefix = (
                    ("ForeverCore", "ForeverCoreDB", b"", "")
                    if standalone
                    else ("ConsumerA", "ConsumerADB", ENTRY, "Libs/ForeverCore/")
                )
                before = plan(ROOT, folder, "1.12.1", saved, entry, standalone=standalone)
                after = plan(source, folder, "1.12.1", saved, entry, standalone=standalone)
                first = json.loads(before[prefix + "bundle.json"])
                second = json.loads(after[prefix + "bundle.json"])
                self.assertEqual(first["source_files"], second["source_files"])
                self.assertNotEqual(first["source_digest"], second["source_digest"])
                for files, manifest in ((before, first), (after, second)):
                    loads = [
                        line.replace("\\", "/").removeprefix(prefix)
                        for line in files[folder + ".toc"].decode().splitlines()
                        if line and not line.startswith("#")
                    ]
                    self.assertEqual(
                        manifest["source_order"],
                        [name for name in loads if name not in ("Begin.lua", "End.lua", "ForeverCoreReady.lua")],
                    )
                package = Path(directory) / folder
                write_bundle(package, before)
                check_bundle(package, before)
                with self.assertRaisesRegex(ValueError, "bundle bytes differ"):
                    check_bundle(package, after)
            sibling = plan(ROOT, "ConsumerB", "1.12.1", "ConsumerBDB", ENTRY)
            self.assertEqual(
                json.loads(original["Libs/ForeverCore/bundle.json"])["source_digest"],
                json.loads(sibling["Libs/ForeverCore/bundle.json"])["source_digest"],
            )

    def test_deterministic_owned_load_graph(self):
        files = plan(ROOT, "ConsumerA", "1.12.1", "ConsumerADB", ENTRY)
        self.assertEqual(files, plan(ROOT, "ConsumerA", "1.12.1", "ConsumerADB", ENTRY))
        self.assertEqual([p for p in files if p.endswith(".toc")], ["ConsumerA.toc"])
        toc = files["ConsumerA.toc"].decode()
        self.assertNotIn("Dependencies:", toc)
        for line in toc.splitlines():
            if line and not line.startswith("#"):
                self.assertIn(line.replace("\\", "/"), files)
        manifest = json.loads(files["Libs/ForeverCore/bundle.json"])
        self.assertEqual(manifest["build"], 1012001)
        self.assertEqual(manifest["schema"], 1)
        self.assertIn("ConsumerA_", manifest["templates"]["ForeverTrackerInteractiveLineTemplate"])
        self.assertEqual(files["Libs/ForeverCore/LICENSE"], (ROOT / "LICENSE").read_bytes())
        for name, data in files.items():
            if name.endswith(".lua") and name not in (
                "Libs/ForeverCore/Core/Loader.lua",
                "Libs/ForeverCore/Begin.lua",
                "Libs/ForeverCore/End.lua",
                "ForeverCoreReady.lua",
            ):
                self.assertTrue(
                    data.startswith(b"local _, host = ...\nhost.ForeverCoreCopy:Define(function(...)\n"), name
                )

    def test_standalone_metadata_and_graph(self):
        files = plan(ROOT, "ForeverCore", "1.12.3", "ForeverCoreDB", b"", standalone=True)
        toc = files["ForeverCore.toc"].decode()
        self.assertIn("## X-Curse-Project-ID: 1796337", toc)
        self.assertNotIn("X-Wago-ID", toc)
        self.assertIn("## Version: 1.12.3", toc)
        self.assertNotIn("Libs/ForeverCore", toc)
        self.assertIn("Begin.lua", files)
        self.assertIn("End.lua", files)
        self.assertTrue(any(name.startswith("media/Icon.") for name in files))
        for line in toc.splitlines():
            if line and not line.startswith("#"):
                self.assertIn(line.replace("\\", "/"), files)
        with self.assertRaises(ValueError):
            plan(ROOT, "ForeverCore", "1.12.3", "ForeverCoreDB", ENTRY, standalone=True)

    def test_invalid_inputs_and_no_overwrite(self):
        for version in ("1.1000.0", "1.0.1000", "1.02.3", "1.0", "0.1.0", "1.2.3-beta"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                release_build(version)
        for folder, saved in (("ForeverCore", "ADB"), ("A", "ForeverCoreDB"), ("../A", "ADB"), ("A", "a.b")):
            with self.subTest(folder=folder, saved=saved), self.assertRaises(ValueError):
                plan(ROOT, folder, "1.12.1", saved, ENTRY)
        with tempfile.TemporaryDirectory(prefix="embedded-producer-", dir=CACHE) as directory:
            with self.assertRaises(FileExistsError):
                write_bundle(Path(directory), {"new": b"never written"})
            self.assertFalse((Path(directory) / "new").exists())

    def test_runtime(self):
        with tempfile.TemporaryDirectory(prefix="embedded-producer-", dir=CACHE) as directory:
            root = Path(directory)
            canonical = plan(ROOT, "ConsumerA", "1.12.1", "ConsumerADB", ENTRY)
            source = root / "reordered-source"
            reordered_source(source, canonical)
            write_bundle(root / "conflict/ConsumerA", canonical)
            write_bundle(root / "conflict/ConsumerB", plan(source, "ConsumerB", "1.12.1", "ConsumerBDB", ENTRY))
            for folder, version in (("ConsumerA", "1.12.1"), ("ConsumerB", "1.12.2")):
                write_bundle(root / folder, plan(ROOT, folder, version, folder + "DB", ENTRY))
            write_bundle(
                root / "ForeverCore", plan(ROOT, "ForeverCore", "1.12.1", "ForeverCoreDB", b"", standalone=True)
            )
            newer = root / "newer"
            for folder, version in (("ConsumerA", "1.12.1"), ("ConsumerB", "1.12.2"), ("ForeverCore", "1.12.3")):
                write_bundle(
                    newer / folder,
                    plan(
                        ROOT,
                        folder,
                        version,
                        folder + "DB",
                        b"" if folder == "ForeverCore" else ENTRY,
                        standalone=folder == "ForeverCore",
                    ),
                )
            result = subprocess.run(
                ["luajit", "tests/generated_bundle_spec.lua", str(root)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("generated bundle", result.stdout)

    def test_artifact_gate_detects_missing_changed_and_extra_files(self):
        files = plan(ROOT, "ConsumerA", "1.12.1", "ConsumerADB", ENTRY)
        with tempfile.TemporaryDirectory(prefix="embedded-gate-", dir=CACHE) as directory:
            package = Path(directory) / "ConsumerA"
            write_bundle(package, files)
            check_bundle(package, files)
            target = package / "Libs/ForeverCore/End.lua"
            target.write_bytes(b"-- truncated release\n")
            with self.assertRaisesRegex(ValueError, "bundle bytes differ"):
                check_bundle(package, files)
            target.write_bytes(files["Libs/ForeverCore/End.lua"])
            extra = package / "ForeverCore.toc"
            extra.write_bytes(b"## Title: wrongly shared addon\n")
            with self.assertRaisesRegex(ValueError, "bundle file selection differs"):
                check_bundle(package, files)
            with self.assertRaisesRegex(ValueError, "missing="):
                check_bundle(package / "absent", files)

    def test_source_changes_and_unsupported_xml_fail_closed(self):
        original = plan(ROOT, "ConsumerA", "1.12.1", "ConsumerADB", ENTRY)
        with tempfile.TemporaryDirectory(prefix="embedded-source-", dir=CACHE) as directory:
            source = Path(directory)
            for name in json.loads(original["Libs/ForeverCore/bundle.json"])["source_files"]:
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            shutil.copyfile(ROOT / "ForeverCore.toc", source / "ForeverCore.toc")
            with (source / "Core.lua").open("a") as handle:
                handle.write("\n-- changed release source\n")
            changed = plan(source, "ConsumerA", "1.12.1", "ConsumerADB", ENTRY)
            self.assertNotEqual(original["Libs/ForeverCore/Begin.lua"], changed["Libs/ForeverCore/Begin.lua"])
            xml = source / "UI" / "TrackerSection.xml"
            xml.write_text(xml.read_text().replace('virtual="true"', 'virtual="false"'))
            with self.assertRaisesRegex(ValueError, "unsupported tracker XML"):
                plan(source, "ConsumerA", "1.12.1", "ConsumerADB", ENTRY)


if __name__ == "__main__":
    unittest.main()
