import contextlib
import io
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from forever_tools import doctor, editorconfig

CI = """jobs:
  check:
    steps:
      - run: sudo apt-get update && sudo apt-get install -y luajit lua-check
      - run: pipx run ruff==0.16.8 check tools
      - uses: JohnnyMorganz/stylua-action@76fd70c03e6340ceaf673366712db9b20560b402 # v5.0.0
        with:
          token: x
          version: 2.5.2
      - run: pipx run --spec actionlint-py==1.7.12.25 actionlint
      - run: pipx run zizmor==1.30.1 --offline .github
      - run: |
          curl -sSfL -o g.tar.gz https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz
      - run: |
          curl -sSfL -o l.tar.gz https://github.com/LuaLS/lua-language-server/releases/download/3.19.1/x.tar.gz
"""
TYPECHECK = 'annotations=.types/vscode-wow-api\nrevision="' + "a" * 40 + '"\n'


class DoctorTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / ".github/workflows").mkdir(parents=True)
        (self.root / "tools").mkdir()
        (self.root / ".github/workflows/ci.yml").write_text(CI)
        (self.root / "tools/typecheck.sh").write_text(TYPECHECK)
        self.bin = self.root / "bin"
        self.bin.mkdir()

    def fake(self, name, output):
        path = self.bin / name
        path.write_text(f"#!/bin/sh\necho '{output}'\n")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def test_every_pin_is_read_from_ci_and_typecheck(self):
        found = doctor.pins(self.root)
        self.assertEqual(
            {tool.name: tool.version for tool in found.tools},
            {
                "stylua": "2.5.2",
                "ruff": "0.16.8",
                "actionlint": "1.7.12",
                "zizmor": "1.30.1",
                "gitleaks": "8.30.1",
                "lua-language-server": "3.19.1",
                "luajit": None,
                "luacheck": None,
            },
        )
        self.assertEqual(found.annotations, (".types/vscode-wow-api", "a" * 40))

    def test_every_problem_is_reported_with_a_fix(self):
        self.fake("stylua", "stylua 2.5.2")
        self.fake("ruff", "ruff 0.15.0")
        self.fake("luajit", "LuaJIT 2.1")
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}):
            findings = doctor.check(self.root)
        failures = {f.text.split(":")[0]: f for f in findings if not f.ok}
        self.assertEqual(set(failures), {"ruff", "actionlint", "zizmor", "gitleaks", "lua-language-server", "luacheck"})
        self.assertIn("0.15.0, CI pins 0.16.8", failures["ruff"].text)
        self.assertTrue(all(f.fix for f in failures.values()))
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}), contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(doctor.main(self.root), 1)

    def test_screenshot_prerequisites_never_fail_the_run(self):
        (self.root / "tools/screenshots.py").write_text('PILLOW = "0.0.1"\n')
        (self.root / ".github/workflows/ci.yml").write_text("jobs: {}\n")
        (self.root / "tools/typecheck.sh").write_text("")
        with mock.patch.dict(os.environ, {"WOWMOCK": ""}):
            findings = doctor.check(self.root)
        optional = [f for f in findings if not f.ok]
        self.assertTrue(optional and all(f.optional for f in optional), findings)
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
