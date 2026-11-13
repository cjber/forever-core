"""Tests for .github/actions/toolchain/pins.py: a cache key names the pins and the scripts that build them."""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ACTION = Path(__file__).resolve().parents[1] / ".github" / "actions" / "toolchain"
TOOLS = ("lua51", "luajit", "luacheck", "argparse", "luafilesystem", "luals", "stylua", "gitleaks")
GROUPS = ("lua", "luals", "stylua", "gitleaks")


def load_pins():
    """Import pins.py from the action's directory, where the calling repository's manifest never is."""
    spec = importlib.util.spec_from_file_location("toolchain_pins", ACTION / "pins.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ToolchainPinsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

        self.action = self.root / "toolchain"
        self.action.mkdir()
        for name in ("build.sh", "install.sh"):
            (self.action / name).write_text(f"# {name}\n", encoding="utf-8")

        manifest = {
            "tools": {name: {"version": "1.0.0"} for name in TOOLS},
            "runtimes": {
                "python": {"version": "3.12"},
                "node": {"version": "22"},
                "bun": {"version": "1.2"},
            },
        }
        self.manifest = self.root / "toolchain.json"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")

        self.pins = load_pins()
        patcher = mock.patch.object(self.pins, "ACTION_DIR", self.action)
        patcher.start()
        self.addCleanup(patcher.stop)

    def outputs(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.pins.main(str(self.manifest), "/toolcache")
        return dict(line.split("=", 1) for line in out.getvalue().splitlines())

    def keys(self):
        return {f"{group}_key": self.outputs()[f"{group}_key"] for group in GROUPS}

    def bump(self, tool):
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["tools"][tool]["version"] = "1.0.1"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")

    def test_every_group_has_a_key_beside_the_prefix_and_the_runtimes(self):
        outputs = self.outputs()
        for group in GROUPS:
            self.assertEqual(len(outputs[f"{group}_key"]), 24)
        self.assertEqual(outputs["lua_prefix"], "/toolcache/toolchain/lua")
        self.assertEqual(
            {name: outputs[name] for name in ("python", "node", "bun")},
            {"python": "3.12", "node": "22", "bun": "1.2"},
        )

    def test_the_same_pins_and_scripts_give_the_same_keys(self):
        self.assertEqual(self.keys(), self.keys())

    def test_moving_a_pin_moves_only_that_group_s_key(self):
        before = self.keys()
        self.bump("luals")
        after = self.keys()
        self.assertNotEqual(before["luals_key"], after["luals_key"])
        self.assertEqual(before["lua_key"], after["lua_key"])

    def test_editing_a_build_script_moves_every_key(self):
        before = self.keys()
        for script in ("build.sh", "install.sh"):
            with self.subTest(script=script):
                path = self.action / script
                path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                after = self.keys()
                for group in GROUPS:
                    self.assertNotEqual(before[f"{group}_key"], after[f"{group}_key"], group)
                before = after


if __name__ == "__main__":
    unittest.main()
