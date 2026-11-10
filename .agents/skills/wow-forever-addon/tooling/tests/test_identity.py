import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from forever_tools import assets, identity

ICON = "Interface\\Icons\\INV_Misc_Map_01"
DEPENDS = "## Dependencies: ForeverCore\n"


class IdentityTest(unittest.TestCase):
    def make(self, files):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text)
        return root

    def test_a_declared_icon_that_ships_passes(self):
        root = self.make({"Addon.toc": DEPENDS + f"## X-Forever-Icon: {ICON}\nCore.lua\n", "Core.lua": ""})
        self.assertEqual(identity.check(root), [])

    def test_an_addon_toc_must_declare_it(self):
        root = self.make({"Addon.toc": DEPENDS + "## Title: Addon\nCore.lua\n", "Core.lua": ""})
        problems = identity.check(root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("X-Forever-Icon", problems[0])
        self.assertIn("Addon.toc", problems[0])

    def test_the_value_must_be_a_client_icon(self):
        for value in (
            "Interface\\AddOns\\Addon\\media\\Icon",
            "INV_Misc_Map_01",
            "Interface\\Icons",
            "Interface\\Icons\\",
        ):
            with self.subTest(value=value):
                root = self.make({"Addon.toc": DEPENDS + f"## X-Forever-Icon: {value}\nCore.lua\n", "Core.lua": ""})
                problems = identity.check(root)
                self.assertEqual(len(problems), 1, problems)
                self.assertIn("Interface\\Icons\\<name>", problems[0])

    def test_the_value_must_be_in_the_pinned_build(self):
        root = self.make(
            {"Addon.toc": DEPENDS + "## X-Forever-Icon: Interface\\Icons\\NoSuchIcon\nCore.lua\n", "Core.lua": ""}
        )
        problems = identity.check(root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("NoSuchIcon", problems[0])
        self.assertIn("listfile", problems[0])

    def test_shipped_lua_must_not_repeat_the_path(self):
        root = self.make(
            {
                "Addon.toc": DEPENDS + f"## X-Forever-Icon: {ICON}\nCore.lua\n",
                "Core.lua": '\n\nlocal ICON = "interface\\\\icons\\\\inv_misc_map_01"\n',
            }
        )
        problems = identity.check(root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("Core.lua:3:", problems[0])
        self.assertIn("read it from the TOC", problems[0])

    def test_constant_concatenation_cannot_hide_the_path(self):
        root = self.make(
            {
                "Addon.toc": DEPENDS + f"## X-Forever-Icon: {ICON}\nCore.lua\n",
                "Core.lua": 'local ICON = "Interface\\\\Icons\\\\" .. "INV_Misc_Map_01"\n',
            }
        )
        self.assertEqual(len(identity.check(root)), 1)

    def test_a_comment_is_not_a_repeat(self):
        root = self.make(
            {
                "Addon.toc": DEPENDS + f"## X-Forever-Icon: {ICON}\nCore.lua\n",
                "Core.lua": f"-- {ICON} is read from the TOC\n",
            }
        )
        self.assertEqual(identity.check(root), [])

    def test_forevercore_does_not_declare_an_identity_icon(self):
        root = self.make({"ForeverCore.toc": "Core.lua\n", "Core.lua": ""})
        self.assertEqual(identity.check(root), [])

    def test_a_library_that_does_not_require_forevercore_has_no_identity(self):
        root = self.make(
            {
                "Addon.toc": DEPENDS + f"## X-Forever-Icon: {ICON}\nCore.lua\n",
                "Core.lua": "",
                "LibThing/LibThing.toc": "## Title: Library\nLib.lua\n",
                "LibThing/Lib.lua": "",
            }
        )
        self.assertEqual(identity.check(root), [])

    def test_every_child_addon_toc_is_checked(self):
        root = self.make(
            {
                "Addon.toc": DEPENDS + f"## X-Forever-Icon: {ICON}\nCore.lua\n",
                "Core.lua": "",
                "Child/Child.toc": "## RequiredDeps: ForeverCore\nChild.lua\n",
                "Child/Child.lua": "",
            }
        )
        problems = identity.check(root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("Child/Child.toc", problems[0])

    def test_lua_the_toc_does_not_load_is_not_shipped(self):
        root = self.make(
            {
                "Addon.toc": DEPENDS + f"## X-Forever-Icon: {ICON}\nCore.lua\n",
                "Core.lua": "",
                "tests/fixture.lua": f'local ICON = "{ICON}"\n',
            }
        )
        self.assertEqual(identity.check(root), [])

    def test_run_prints_each_problem(self):
        root = self.make({"Addon.toc": DEPENDS + "Core.lua\n", "Core.lua": ""})
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(identity.run(root), 1)
        self.assertIn("X-Forever-Icon", output.getvalue())

    def test_the_assets_check_runs_it(self):
        root = self.make({"Addon.toc": DEPENDS + f"## X-Forever-Icon: {ICON}\nCore.lua\n", "Core.lua": ""})
        with (
            mock.patch.object(assets, "run", return_value=0),
            mock.patch.object(identity, "run", return_value=1) as run,
            mock.patch("sys.argv", ["assets"]),
            mock.patch("pathlib.Path.cwd", return_value=root),
        ):
            self.assertEqual(assets.main(), 1)
        run.assert_called_once_with(root.resolve())


if __name__ == "__main__":
    unittest.main()
