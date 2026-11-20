import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from forever_tools import specs

# The specs below are Python run by `--interpreter`, so the runner is tested without LuaJIT.
PASS = 'print("{name}: ok")\n'
FAIL = 'import sys\nprint("{name}: broke")\nsys.exit(3)\n'
# Waits until its partner has started, so the pair finishes only when both run at once.
MEET = """import pathlib, time
pathlib.Path("{name}.started").touch()
deadline = time.monotonic() + 10
while not pathlib.Path("{other}.started").exists():
    assert time.monotonic() < deadline, "{name} ran alone"
    time.sleep(0.01)
print("{name}: met")
"""


class SpecsTest(unittest.TestCase):
    def run_specs(self, files, *extra):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            for name, body in files.items():
                (root / "tests" / name).write_text(body)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = specs.main(["--root", str(root), "--interpreter", sys.executable, *extra])
            return code, out.getvalue(), err.getvalue()

    def test_every_spec_runs_and_reports_in_glob_order(self):
        code, out, _ = self.run_specs(
            {"b_spec.lua": PASS.format(name="b"), "a_spec.lua": PASS.format(name="a"), "helper.lua": FAIL}
        )
        self.assertEqual(code, 0)
        self.assertLess(out.index("== tests/a_spec.lua ok"), out.index("== tests/b_spec.lua ok"))
        self.assertLess(out.index("a: ok"), out.index("== tests/b_spec.lua"))
        self.assertNotIn("helper", out)
        self.assertIn("2 specs, 0 failed", out)

    def test_a_failure_fails_the_run_after_every_spec_ran(self):
        code, out, err = self.run_specs({"a_spec.lua": FAIL.format(name="a"), "b_spec.lua": PASS.format(name="b")})
        self.assertEqual(code, 1)
        self.assertIn("== tests/a_spec.lua FAILED (exit 3)", out)
        self.assertIn("a: broke", out)
        self.assertIn("b: ok", out)
        self.assertIn("tests/a_spec.lua", err)

    def test_specs_run_at_the_same_time(self):
        code, out, _ = self.run_specs(
            {
                "a_spec.lua": MEET.format(name="a", other="b"),
                "b_spec.lua": MEET.format(name="b", other="a"),
            },
            "--jobs",
            "2",
        )
        self.assertEqual(code, 0, out)

    def test_a_pattern_selects_other_specs(self):
        code, out, _ = self.run_specs(
            {"a_spec.lua": FAIL.format(name="a"), "b_check.lua": PASS.format(name="b")},
            "--pattern",
            "tests/*_check.lua",
        )
        self.assertEqual(code, 0)
        self.assertIn("1 specs, 0 failed", out)

    def test_no_specs_is_a_failure(self):
        code, _, err = self.run_specs({})
        self.assertEqual(code, 1)
        self.assertIn("No specs match", err)


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def core_repository(root):
    """A ForeverCore stand-in: v1.0.0 says "pinned", and HEAD has moved on to "branch"."""
    root.mkdir(parents=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    (root / "ForeverCore.toc").write_text("## Title: ForeverCore\n")
    for text in ("pinned", "branch"):
        (root / "release.txt").write_text(text)
        git(root, "add", "-A")
        git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", text)
        if text == "pinned":
            git(root, "-c", "tag.gpgsign=false", "tag", "v1.0.0")
    return root


# Prints the release of the ForeverCore the runner hands the spec.
READ_CORE = """import os, pathlib
print("core:", (pathlib.Path(os.environ["FOREVER_CORE"]) / "release.txt").read_text())
"""


class PinnedCoreTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.core = core_repository(self.base / "forever-core")
        self.addon = self.base / "addon"
        (self.addon / "tests").mkdir(parents=True)
        (self.addon / "tools").mkdir()
        (self.addon / "tools" / "forever-core.txt").write_text("v1.0.0\n")
        (self.addon / "tests" / "core_spec.lua").write_text(READ_CORE)
        patcher = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.base / "cache")})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("FOREVER_CORE", None)
        os.environ.pop(specs.UNPINNED, None)

    def run_specs(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = specs.main(["--root", str(self.addon), "--interpreter", sys.executable])
        return code, out.getvalue(), err.getvalue()

    def test_a_sibling_checkout_on_another_commit_loads_the_pinned_release(self):
        code, out, _ = self.run_specs()
        self.assertEqual(code, 0, out)
        self.assertIn("core: pinned", out)
        self.assertIn("not the pinned v1.0.0", out)
        self.assertEqual((self.core / "release.txt").read_text(), "branch", "the checkout itself is left alone")

    def test_local_edits_at_the_pin_load_the_pinned_release(self):
        git(self.core, "checkout", "-q", "v1.0.0")
        (self.core / "release.txt").write_text("edited")
        code, out, _ = self.run_specs()
        self.assertEqual(code, 0, out)
        self.assertIn("core: pinned", out)
        self.assertIn("has local edits", out)

    def test_a_checkout_at_the_pin_is_used_as_it_is(self):
        git(self.core, "checkout", "-q", "v1.0.0")
        os.environ["FOREVER_CORE"] = str(self.core)
        code, out, _ = self.run_specs()
        self.assertEqual(code, 0, out)
        self.assertIn("core: pinned", out)
        self.assertNotIn("specs load", out)
        self.assertFalse((self.base / "cache").exists())

    def test_the_export_is_reused_only_for_the_same_release(self):
        self.assertEqual(self.run_specs()[0], 0)
        exports = list((self.base / "cache" / "forever-core").iterdir())
        self.assertEqual(len(exports), 1)
        self.assertEqual(self.run_specs()[0], 0)
        self.assertEqual(list((self.base / "cache" / "forever-core").iterdir()), exports)
        (exports[0] / specs.EXPORT_MARKER).write_text("v1.0.0 0000000\n")
        code, _, err = self.run_specs()
        self.assertEqual(code, 1)
        self.assertIn("does not hold ForeverCore v1.0.0", err)

    def test_a_branch_named_like_the_pin_is_not_the_release(self):
        git(self.core, "tag", "-d", "v1.0.0")
        git(self.core, "branch", "v1.0.0")
        code, out, err = self.run_specs()
        self.assertEqual(code, 1)
        self.assertIn("is not a tag", err)
        self.assertNotIn("core:", out)

    def test_a_checkout_of_another_repository_stops_before_any_spec(self):
        (self.core / "ForeverCore.toc").unlink()
        git(self.core, "-c", "commit.gpgsign=false", "commit", "-qam", "not core")
        code, _, err = self.run_specs()
        self.assertEqual(code, 1)
        self.assertIn("no ForeverCore.toc", err)

    def test_unpinned_runs_against_the_checkout_and_says_so(self):
        os.environ[specs.UNPINNED] = "1"
        code, out, _ = self.run_specs()
        self.assertEqual(code, 0, out)
        self.assertIn("core: branch", out)
        self.assertIn("FOREVER_CORE_UNPINNED=1", out)

    def test_a_missing_tag_stops_before_any_spec(self):
        (self.addon / "tools" / "forever-core.txt").write_text("v9.9.9\n")
        code, out, err = self.run_specs()
        self.assertEqual(code, 1)
        self.assertIn("v9.9.9", err)
        self.assertNotIn("core:", out)

    def test_a_folder_that_is_not_a_checkout_stops_before_any_spec(self):
        plain = self.base / "plain"
        plain.mkdir()
        (plain / "ForeverCore.toc").write_text("## Title: ForeverCore\n")
        os.environ["FOREVER_CORE"] = str(plain)
        code, _, err = self.run_specs()
        self.assertEqual(code, 1)
        self.assertIn("not a git checkout", err)


if __name__ == "__main__":
    unittest.main()
