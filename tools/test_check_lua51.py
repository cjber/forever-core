"""Regression checks for the client Lua 5.1 parser gate."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


class Lua51GateTests(unittest.TestCase):
    def run_fixture(self, source: str) -> subprocess.CompletedProcess[str]:
        from tempfile import TemporaryDirectory

        parser = os.environ["LUA51_LUAC"]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Fixture.toc").write_text("Fixture.lua\n", encoding="utf-8")
            (root / "Fixture.lua").write_text(source, encoding="utf-8")
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
