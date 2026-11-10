import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
