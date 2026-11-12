"""Regression checks for the client Lua 5.1 parser gate."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
import sys


@unittest.skipUnless(os.environ.get("LUA51_LUAC"), "requires the pinned Lua 5.1 parser")
class Lua51GateTests(unittest.TestCase):
    def run_fixture(self, source: str, *, xml: str | None = None) -> subprocess.CompletedProcess[str]:
        from tempfile import TemporaryDirectory

        parser = os.environ["LUA51_LUAC"]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            entry = "Fixture.lua\n" if xml is None else "Fixture.xml\n"
            (root / "Fixture.toc").write_text(entry, encoding="utf-8")
            (root / "Fixture.lua").write_text(source, encoding="utf-8")
            if xml is not None:
                (root / "Fixture.xml").write_text(xml, encoding="utf-8")
            return subprocess.run(
                ["python3", "tools/check_lua51.py", str(root)],
                env={**os.environ, "LUA51_LUAC": parser},
                capture_output=True,
                text=True,
                check=False,
            )

    def test_parser_rejects_parenthesized_receiver(self) -> None:
        result = self.run_fixture("local provider = CreateDataProvider()\n(provider):Flush()\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ambiguous syntax", result.stderr)

    def test_parser_accepts_local_receiver(self) -> None:
        result = self.run_fixture("local provider = CreateDataProvider()\nprovider:Flush()\n")
        self.assertEqual(result.returncode, 0)

    def test_parser_follows_xml_virtual_file(self) -> None:
        result = self.run_fixture(
            "local provider = CreateDataProvider()\n(provider):Flush()\n",
            xml='<Ui><Script virtualFile="Fixture.lua" /></Ui>',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ambiguous syntax", result.stderr)

    def test_packaged_bad_artifact_is_rejected(self) -> None:
        from tempfile import TemporaryDirectory

        tooling = Path(__file__).resolve().parents[1] / ".agents/skills/wow-forever-addon/tooling"
        sys.path.insert(0, str(tooling))
        from forever_tools import lua51

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ForeverCore.toc").write_text("Core.lua\n", encoding="utf-8")
            (root / "Core.lua").write_text("local provider = CreateDataProvider()\n(provider):Flush()\n", encoding="utf-8")
            self.assertTrue(lua51.check(root))
