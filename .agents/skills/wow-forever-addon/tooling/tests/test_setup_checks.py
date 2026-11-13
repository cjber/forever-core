import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from forever_tools import doctor, editorconfig

MANIFEST = {
    "schema": 1,
    "runtimes": {"python": {"version": "3.14", "upstream": {"kind": "github-release", "repo": "python/cpython"}}},
    "tools": {
        "luajit": {
            "commit": "a" * 40,
            "upstream": {"kind": "github-branch", "repo": "LuaJIT/LuaJIT", "branch": "v2.1"},
        },
        "luacheck": {
            "version": "1.1.2",
            "commit": "b" * 40,
            "upstream": {"kind": "github-tag", "repo": "lunarmodules/luacheck"},
        },
        "luals": {
            "version": "3.19.1",
            "sha256": "c" * 64,
            "upstream": {"kind": "github-release", "repo": "LuaLS/lua-language-server"},
        },
        "stylua": {
            "version": "2.5.2",
            "sha256": "d" * 64,
            "upstream": {"kind": "github-release", "repo": "JohnnyMorganz/StyLua"},
        },
        "gitleaks": {
            "version": "8.30.1",
            "sha256": "e" * 64,
            "upstream": {"kind": "github-release", "repo": "gitleaks/gitleaks"},
        },
        "annotations": {
            "commit": "f" * 40,
            "upstream": {"kind": "github-branch", "repo": "Ketho/vscode-wow-api", "branch": "master"},
        },
    },
}
PYPROJECT = """[project]
name = "tools"
version = "0.0.0"

[tool.uv]
package = false

[dependency-groups]
dev = [
  "actionlint-py==1.7.12.25",
  "ruff==0.16.8",
  "ty==0.0.83",
  "zizmor==1.30.1",
]
"""
TYPECHECK = "annotations=.types/vscode-wow-api\n"


class DoctorTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "tools").mkdir()
        (self.root / "toolchain.json").write_text(json.dumps(MANIFEST, indent=2) + "\n")
        (self.root / "pyproject.toml").write_text(PYPROJECT)
        (self.root / "tools/typecheck.sh").write_text(TYPECHECK)
        self.bin = self.root / "bin"
        self.bin.mkdir()

    def fake(self, name, output):
        path = self.bin / name
        path.write_text(f"#!/bin/sh\necho '{output}'\n")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def test_every_pin_is_read_from_the_manifest_and_the_dev_group(self):
        found = doctor.pins(self.root)
        self.assertEqual(
            {tool.name: tool.version for tool in found.tools},
            {
                "stylua": "2.5.2",
                "ruff": "0.16.8",
                "ty": "0.0.83",
                "actionlint": "1.7.12",
                "zizmor": "1.30.1",
                "gitleaks": "8.30.1",
                "lua-language-server": "3.19.1",
                "luajit": None,
                "luacheck": "1.1.2",
            },
        )
        self.assertEqual(found.annotations, (".types/vscode-wow-api", "f" * 40))

    def test_a_missing_manifest_or_pyproject_is_reported(self):
        (self.root / "toolchain.json").unlink()
        (self.root / "pyproject.toml").unlink()
        found = doctor.pins(self.root)
        self.assertEqual(len(found.missing), 2, found.missing)
        self.assertEqual(found.tools, [])

    def test_every_problem_is_reported_with_a_fix(self):
        self.fake("stylua", "stylua 2.5.2")
        self.fake("ruff", "ruff 0.15.0")
        self.fake("luajit", "LuaJIT 2.1")
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}):
            findings = doctor.check(self.root)
        failures = {f.text.split(":")[0]: f for f in findings if not f.ok}
        self.assertEqual(
            set(failures),
            {"ruff", "ty", "actionlint", "zizmor", "gitleaks", "lua-language-server", "luacheck"},
        )
        self.assertIn("0.15.0, CI pins 0.16.8", failures["ruff"].text)
        self.assertTrue(all(f.fix for f in failures.values()))
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}), contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(doctor.main(self.root), 1)

    def test_screenshot_prerequisites_never_fail_the_run(self):
        (self.root / "tools/screenshots.py").write_text('PILLOW = "0.0.1"\n')
        for name, output in (
            ("stylua", "stylua 2.5.2"),
            ("ruff", "ruff 0.16.8"),
            ("ty", "ty 0.0.83"),
            ("zizmor", "zizmor 1.30.1"),
            ("actionlint", "1.7.12"),
            ("gitleaks", "8.30.1"),
            ("lua-language-server", "3.19.1"),
            ("luajit", "LuaJIT 2.1"),
            ("luacheck", "Luacheck: 1.1.2"),
        ):
            self.fake(name, output)
        with mock.patch.dict(os.environ, {"PATH": str(self.bin), "FOREVER_CORE": str(self.root)}):
            findings = doctor.check(self.root)
        optional = [f for f in findings if not f.ok]
        self.assertTrue(optional and all(f.optional for f in optional), findings)
        with mock.patch.dict(os.environ, {"PATH": str(self.bin), "FOREVER_CORE": str(self.root)}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(doctor.main(self.root), 0)


class EditorconfigTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "stylua.toml").write_text('column_width = 120\nindent_type = "Tabs"\n')
        (self.root / "ruff.toml").write_text("line-length = 120\n")

    def test_the_template_agrees_with_the_family_settings(self):
        (self.root / ".editorconfig").write_text(editorconfig.TEMPLATE)
        self.assertEqual(editorconfig.check(self.root), [])

    def test_a_missing_file_section_or_disagreement_fails(self):
        self.assertIn("missing", editorconfig.check(self.root)[0])
        (self.root / ".editorconfig").write_text(editorconfig.TEMPLATE.replace("[*.md]", "[*.markdown]"))
        self.assertTrue(any("[*.md]" in p for p in editorconfig.check(self.root)))
        (self.root / ".editorconfig").write_text(editorconfig.TEMPLATE + "[*]\nend_of_line = crlf\n")
        self.assertEqual(editorconfig.check(self.root), [".editorconfig [*]: end_of_line = crlf, the family uses lf"])
        (self.root / ".editorconfig").write_text(editorconfig.TEMPLATE)
        (self.root / "stylua.toml").write_text('column_width = 100\nindent_type = "Spaces"\nindent_width = 2\n')
        problems = editorconfig.check(self.root)
        self.assertEqual(len(problems), 3, problems)
        self.assertTrue(all("stylua.toml" in p and "[{*.lua,.luacheckrc}]" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
