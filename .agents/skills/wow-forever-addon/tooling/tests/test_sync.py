import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLING = Path(__file__).resolve().parent.parent
PRODUCER = Path(".agents") / "skills" / "wow-forever-addon" / "tooling"


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


def function_text(package, name):
    """The source of one function in a package's sync.py, to compare the two copies word for word."""
    text = (TOOLING / package / "sync.py").read_text(encoding="utf-8")
    start = text.index(f"\ndef {name}(") + 1
    end = text.find("\ndef ", start)
    return text[start:] if end == -1 else text[start:end]


class UpdateCases:
    """A consumer's `update`, run against a producer checkout of one package."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "producer"
        self.root.mkdir()
        self.producer = self.root / PRODUCER / self.package
        shutil.copytree(TOOLING / self.package, self.producer, ignore=shutil.ignore_patterns("__pycache__"))
        self.copy = Path(directory.name) / "consumer" / self.package
        shutil.copytree(TOOLING / self.package, self.copy, ignore=shutil.ignore_patterns("__pycache__"))

    def sync(self, *args):
        return subprocess.run(
            [sys.executable, str(self.copy / "sync.py"), *args], capture_output=True, text=True, check=False
        )

    def manifest(self, directory):
        return json.loads((directory / "MANIFEST.json").read_text())

    def data_file(self):
        """The first data file the package vendors beside its modules, such as restrictions.txt."""
        text = (self.producer / "sync.py").read_text(encoding="utf-8")
        return re.search(r'^DATA_FILES = \(\s*"([^"]+)"', text, re.MULTILINE).group(1)

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

    def test_update_does_not_fail_on_a_data_file_this_copy_does_not_know(self):
        """The updater that runs can lag the producer: it must not judge the producer by its own older walk (#467)."""
        repository(self.root, {"README": "x"})
        data = self.data_file()
        script = self.copy / "sync.py"
        text = script.read_text(encoding="utf-8")
        pattern = re.compile(r'(DATA_FILES = \(\s*)"' + re.escape(data) + '"')
        self.assertTrue(pattern.search(text), text)
        script.write_text(pattern.sub(r'\1"never_vendored.txt"', text, count=1))

        result = self.sync("update", "--source", str(self.root))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.copy / data).read_bytes(), (self.producer / data).read_bytes())
        self.assertIn(data, self.manifest(self.copy)["files"])
        # The producer's own sync.py came across with the files, so the updated copy's own walk now agrees.
        self.assertEqual(self.sync("check").returncode, 0)

    def test_update_names_a_changed_file_in_a_stale_producer_manifest(self):
        repository(self.root, {"README": "x"})
        name = sorted(entry for entry in self.manifest(self.producer)["files"] if entry.endswith(".py"))[0]
        (self.producer / name).write_text("# drift\n")
        commit(self.root)

        result = self.sync("update", "--source", str(self.root))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"changed: {name}", result.stderr)
        self.assertIn("sync.py manifest", result.stderr)

    def test_update_names_a_producer_file_the_manifest_leaves_out(self):
        repository(self.root, {"README": "x"})
        (self.producer / "unlisted.py").write_text("# never hashed\n")
        commit(self.root)

        result = self.sync("update", "--source", str(self.root))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not in MANIFEST.json: unlisted.py", result.stderr)


class ForeverToolsUpdateTest(UpdateCases, unittest.TestCase):
    package = "forever_tools"


class ForeverSimUpdateTest(UpdateCases, unittest.TestCase):
    package = "forever_sim"


class SharedWalkTest(unittest.TestCase):
    def test_both_packages_judge_a_producer_manifest_with_the_same_function(self):
        """Each package is copied into a consumer alone, so `stale` is duplicated; keep the copies identical."""
        self.assertEqual(function_text("forever_tools", "stale"), function_text("forever_sim", "stale"))


if __name__ == "__main__":
    unittest.main()
