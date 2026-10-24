import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from forever_tools import generated

PACKAGE = Path(__file__).resolve().parent.parent / "forever_tools"
GENERATOR = """from pathlib import Path

Path("Data").mkdir(exist_ok=True)
Path("Data/X.lua").write_text("ns.A = {\\n\\t[1] = true,\\n}\\n")
"""
DRIFT = """import sys
from pathlib import Path

body = "ns.A = {\\n\\t[1] = true,\\n}\\n"
Path("Data/X.lua").write_text(body if "--offline" not in sys.argv else body + "-- drift\\n")
"""


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def repository(directory, tracked):
    root = Path(directory)
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    for name, text in tracked.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    git(root, "add", "-A")
    git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "x")
    return root


class GeneratedTest(unittest.TestCase):
    def test_compare_names_files_and_attaches_a_semantic_report(self):
        old, new = b"ns.A = {\n\t[1] = true,\n}\n", b"ns.A = {\n\t[1] = true,\n\t[2] = true,\n}\n"
        generated.compare({"Data/X.lua": old}, {"Data/X.lua": old}, "label")
        with self.assertRaises(SystemExit) as raised:
            generated.compare({"Data/X.lua": old}, {"Data/X.lua": new}, "stale")
        self.assertIn("Data/X.lua", str(raised.exception))
        self.assertIn("+1 added", str(raised.exception))

    def run_gate(self, generator, offline=True):
        with tempfile.TemporaryDirectory() as directory:
            root = repository(directory, {"Data/X.lua": "ns.A = {\n\t[1] = true,\n}\n", "gen.py": generator})
            generated.check_generated(
                root,
                outputs=lambda r: {"Data/X.lua": (r / "Data/X.lua").read_bytes()},
                regenerate=lambda scratch, off: subprocess.run(
                    [sys.executable, "gen.py", *(["--offline"] if off else [])], cwd=scratch, check=True
                ),
                offline=offline,
                success="ok",
            )

    def test_gate_passes_for_a_fresh_reproducible_generator(self):
        self.run_gate(GENERATOR)

    def test_gate_rejects_a_generator_whose_second_pass_differs(self):
        with self.assertRaisesRegex(SystemExit, "not byte-for-byte reproducible"):
            self.run_gate(DRIFT, offline=False)

    def test_gate_rejects_stale_committed_output(self):
        with self.assertRaisesRegex(SystemExit, "Stale generated files"):
            self.run_gate(GENERATOR.replace("ns.A = {", "ns.A = {\\n\\t[2] = true,"))

    def test_data_report_compares_a_revision_with_the_working_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = repository(directory, {"Data/X.lua": "ns.A = {\n\t[1] = true,\n}\n"})
            (root / "Data/X.lua").write_text("ns.A = {\n\t[1] = true,\n\t[2] = true,\n}\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                generated.data_report(root, ["Data/X.lua"], argv=["--base", "HEAD"])
            self.assertIn("+1 added", out.getvalue())


class SyncTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.copy = Path(directory.name) / "forever_tools"
        shutil.copytree(PACKAGE, self.copy, ignore=shutil.ignore_patterns("__pycache__"))

    def sync(self, *args):
        return subprocess.run(
            [sys.executable, str(self.copy / "sync.py"), *args], capture_output=True, text=True, check=False
        )

    def test_manifest_refuses_a_module_gitleaks_would_flag(self):
        (self.copy / "secret_store.py").write_text("")
        result = self.sync("manifest")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rename secret_store.py", result.stderr)
        (self.copy / "secret_store.py").unlink()
        self.assertEqual(self.sync("manifest").returncode, 0)

    def test_unpinned_copy_passes_only_with_the_allowance(self):
        self.assertEqual(self.sync("check", "--allow-unpinned").returncode, 0)
        refused = self.sync("check")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("UNPINNED", refused.stderr)

    def test_a_changed_or_extra_file_fails_the_offline_check(self):
        (self.copy / "csvtable.py").write_text("# edited\n")
        self.assertIn("csvtable.py", self.sync("check", "--allow-unpinned").stderr)
        shutil.copy(PACKAGE / "csvtable.py", self.copy / "csvtable.py")
        (self.copy / "extra.py").write_text("")
        self.assertIn("extra.py", self.sync("check", "--allow-unpinned").stderr)

    def test_pin_records_a_full_sha_and_the_check_then_passes(self):
        self.assertNotEqual(self.sync("pin", "abc").returncode, 0)
        sha = "a" * 40
        self.assertEqual(self.sync("pin", sha).returncode, 0)
        self.assertEqual(self.sync("check").returncode, 0)
        self.assertEqual(json.loads((self.copy / "MANIFEST.json").read_text())["source"]["revision"], sha)

    def test_update_copies_a_committed_producer_and_pins_its_head(self):
        with tempfile.TemporaryDirectory() as directory:
            root = repository(directory, {"README": "x"})
            producer = root / ".agents" / "skills" / "wow-forever-addon" / "tooling" / "forever_tools"
            shutil.copytree(PACKAGE, producer, ignore=shutil.ignore_patterns("__pycache__"))
            git(root, "add", "-A")
            git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "producer")
            head = git(root, "rev-parse", "HEAD")
            (self.copy / "csvtable.py").write_text("# stale\n")
            result = self.sync("update", "--source", str(root))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.sync("check", "--source", str(root)).returncode, 0)
            self.assertEqual(json.loads((self.copy / "MANIFEST.json").read_text())["source"]["revision"], head)
            (producer / "csvtable.py").write_text("# dirty\n")
            self.assertIn("uncommitted", self.sync("update", "--source", str(root)).stderr)


if __name__ == "__main__":
    unittest.main()
