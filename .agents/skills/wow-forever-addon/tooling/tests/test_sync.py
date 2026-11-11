import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "forever_tools"
PRODUCER = Path(".agents") / "skills" / "wow-forever-addon" / "tooling" / "forever_tools"


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def repository(directory, tracked):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    for name, text in tracked.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    git(root, "add", "-A")
    git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "x")
    return root


def commit(root):
    git(root, "add", "-A")
    git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "producer")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SyncUpdateTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "producer"
        self.root.mkdir()
        self.producer = self.root / PRODUCER
        shutil.copytree(PACKAGE, self.producer, ignore=shutil.ignore_patterns("__pycache__"))
        self.copy = Path(directory.name) / "consumer" / "forever_tools"
        shutil.copytree(PACKAGE, self.copy, ignore=shutil.ignore_patterns("__pycache__"))

    def sync(self, *args):
        return subprocess.run(
            [sys.executable, str(self.copy / "sync.py"), *args], capture_output=True, text=True, check=False
        )

    def manifest(self, directory):
        return json.loads((directory / "MANIFEST.json").read_text())

    def test_update_copies_a_file_only_the_producer_manifest_lists(self):
        repository(self.root, {"README": "x"})
        future = self.producer / "future_data.txt"
        future.write_text("future\n")
        manifest = self.manifest(self.producer)
        manifest["files"]["future_data.txt"] = digest(future)
        (self.producer / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
        commit(self.root)

        result = self.sync("update", "--source", str(self.root))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.copy / "future_data.txt").read_text(), "future\n")
        self.assertIn("future_data.txt", self.manifest(self.copy)["files"])

    def test_update_names_a_changed_file_in_a_stale_producer_manifest(self):
        repository(self.root, {"README": "x"})
        (self.producer / "csvtable.py").write_text("# drift\n")
        commit(self.root)

        result = self.sync("update", "--source", str(self.root))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("changed: csvtable.py", result.stderr)
        self.assertIn("sync.py manifest", result.stderr)


if __name__ == "__main__":
    unittest.main()
