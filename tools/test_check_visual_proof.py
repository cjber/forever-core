import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import check_visual_proof


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
        problems = check_visual_proof.verify(self.root(), ["UI/Main.lua"])
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
            "candidate": "addon-build",
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


if __name__ == "__main__":
    unittest.main()
