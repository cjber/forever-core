import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from forever_tools import visual_proof as check_visual_proof


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

    def test_docs_only_does_not_need_proof(self):
        self.assertEqual(check_visual_proof.verify(self.root(), ["docs/README.md"]), [])

    def test_runtime_change_requires_proof(self):
        root = self.root()
        problems = check_visual_proof.verify(root, ["UI/Main.lua"], root / ".visual-proof.json")
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
        problems = check_visual_proof.verify(root, ["UI/Main.lua"], path)
        self.assertTrue(any("input_digest" in problem for problem in problems))
        self.assertTrue(any("passing flow" in problem for problem in problems))
        self.assertTrue(any("image" in problem for problem in problems))

    @mock.patch.object(check_visual_proof, "image_hash", return_value="a" * 64)
    def test_accepts_pinned_matching_image(self, _image_hash):
        root = self.root()
        proof = {
            "input_digest": check_visual_proof.input_digest(root),
            "client_build": "16001",
            "candidate": check_visual_proof.candidate_digest(root),
            "runtime_sha256": check_visual_proof.input_digest(root),
            "flows": [{"name": "open", "steps": ["open"], "result": "pass"}],
            "images": [
                {
                    "url": "https://github.com/cjber/proof/raw/0123456789abcdef0123456789abcdef01234567/image.png",
                    "sha256": "a" * 64,
                }
            ],
        }
        path = root / ".visual-proof.json"
        path.write_text(json.dumps(proof), encoding="utf-8")
        self.assertEqual(check_visual_proof.verify(root, ["UI/Main.lua"], path), [])

    @mock.patch.object(check_visual_proof, "image_hash", return_value="a" * 64)
    def test_arbitrary_candidate_hash_is_rejected(self, _image_hash):
        root = self.root()
        digest = check_visual_proof.input_digest(root)
        proof = {
            "input_digest": digest,
            "runtime_sha256": digest,
            "candidate": "b" * 64,
            "client_build": "16001",
            "flows": [{"name": "open", "steps": ["open"], "result": "pass"}],
            "images": [{"url": "https://example.com/raw/" + "a" * 40 + "/image.png", "sha256": "a" * 64}],
        }
        path = root / ".visual-proof.json"
        path.write_text(json.dumps(proof))
        problems = check_visual_proof.verify(root, ["UI/Main.lua"], path)
        self.assertTrue(any("candidate" in problem for problem in problems))

    def test_metadata_and_tooling_do_not_require_proof(self):
        self.assertFalse(
            check_visual_proof.requires_proof(self.root(), ["README.md", "CHANGELOG.md", ".agents/tool.py"])
        )

    def test_relative_root_has_same_digest(self):
        root = self.root()
        self.assertEqual(check_visual_proof.input_digest(root), check_visual_proof.input_digest(root / "."))

    def test_toc_metadata_and_nested_xml_are_hashed(self):
        root = self.root()
        before = check_visual_proof.input_digest(root)
        (root / "ForeverCore.toc").write_text("## Interface: 16001\nCore.lua\nUI/Main.lua\n")
        self.assertNotEqual(before, check_visual_proof.input_digest(root))
        (root / "UI/Load.xml").write_text('<Ui><Script file="Child.lua"/></Ui>')
        (root / "UI/Child.lua").write_text("child")
        with (root / "ForeverCore.toc").open("a") as stream:
            stream.write("UI/Load.xml\n")
        before = check_visual_proof.input_digest(root)
        (root / "UI/Child.lua").write_text("changed child")
        self.assertNotEqual(before, check_visual_proof.input_digest(root))

    def test_packager_version_stamp_does_not_change_runtime(self):
        root = self.root()
        toc = root / "ForeverCore.toc"
        toc.write_text("## Version: @project-version@\n" + toc.read_text())
        before = check_visual_proof.candidate_digest(root)
        toc.write_text(toc.read_text().replace("@project-version@", "v1.7.4-dev+1234567"))
        self.assertEqual(before, check_visual_proof.candidate_digest(root))

    def test_artwork_changes_invalidate_digest(self):
        root = self.root()
        (root / "media").mkdir()
        art = root / "media/icon.blp"
        art.write_bytes(b"first")
        before = check_visual_proof.input_digest(root)
        art.write_bytes(b"second")
        self.assertNotEqual(before, check_visual_proof.input_digest(root))
        self.assertTrue(check_visual_proof.requires_proof(root, ["media/icon.blp"]))

    @mock.patch.object(check_visual_proof, "image_hash", return_value="a" * 64)
    def test_pin_change_cannot_reuse_old_digest(self, _image_hash):
        root = self.root()
        (root / "tools").mkdir()
        pin = root / "tools/forever-core.txt"
        pin.write_text("v1.7.3")
        old = check_visual_proof.input_digest(root)
        proof = {
            "input_digest": old,
            "runtime_sha256": old,
            "candidate": check_visual_proof.candidate_digest(root),
            "client_build": "16001",
            "flows": [{"name": "open", "steps": ["open"], "result": "pass"}],
            "images": [{"url": "https://example.com/raw/" + "a" * 40 + "/image.png", "sha256": "a" * 64}],
        }
        path = root / ".visual-proof.json"
        path.write_text(json.dumps(proof))
        pin.write_text("v1.7.4")
        problems = check_visual_proof.verify(root, ["tools/forever-core.txt"], path)
        self.assertTrue(any("input_digest" in problem for problem in problems))

    def test_top_level_list_fails_cleanly(self):
        root = self.root()
        path = root / ".visual-proof.json"
        path.write_text("[]")
        self.assertIn("object", check_visual_proof.verify(root, ["Core.lua"], path)[0])

    @mock.patch.object(check_visual_proof, "urlopen")
    def test_http_success_with_html_is_not_image_evidence(self, open_url):
        response = open_url.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = b"<html>not found</html>"
        with self.assertRaisesRegex(ValueError, "successful PNG"):
            check_visual_proof.image_hash("https://example.com/raw/" + "a" * 40 + "/image.png")


if __name__ == "__main__":
    unittest.main()
