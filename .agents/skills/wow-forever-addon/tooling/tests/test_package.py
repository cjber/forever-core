import shutil
import tempfile
import unittest
from pathlib import Path

from forever_tools import package

POLICY = package.Policy(addons=("Addon", "Lib"))


class PackageTest(unittest.TestCase):
    def make(self, files):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text)
        return root

    def good(self):
        return {
            "Addon/Addon.toc": (
                "## Title: A\n## IconTexture: Interface\\AddOns\\Addon\\media\\Icon\nCore.lua\nUI\\ui.xml\n"
            ),
            "Addon/Core.lua": (
                'local DOT = "Interface\\\\AddOns\\\\Addon\\\\media\\\\Dot"\n'
                'local other = "Interface\\\\AddOns\\\\X\\\\y"\n'
            ),
            "Addon/UI/ui.xml": (
                '<Ui><Script file="ui.lua"/><Texture file="Interface\\AddOns\\Addon\\media\\Shade"/></Ui>'
            ),
            "Addon/UI/ui.lua": "",
            "Addon/media/Icon.tga": "",
            "Addon/media/dot.tga": "",
            "Addon/media/Shade.blp": "",
            "Addon/LICENSE": "MIT",
            "Addon/README.md": "# A\n\n## Credits\n\nThanks.\n",
            "Addon/THIRD_PARTY.md": "# Inputs\n\n## Ideas and contributors\n\nNone.\n",
            "Lib/LICENSE.txt": "MIT",
            "Lib/Lib.toc": "## IconTexture: Interface\\AddOns\\Addon\\media\\Icon\nLib.lua\n",
            "Lib/Lib.lua": "",
        }

    def test_a_complete_package_passes(self):
        self.assertEqual(package.check(self.make(self.good()), POLICY), [])

    def test_each_problem_is_reported_once(self):
        files = self.good()
        del files["Addon/UI/ui.lua"], files["Addon/media/Shade.blp"], files["Addon/LICENSE"], files["Lib/Lib.toc"]
        files["Addon/tests/x_spec.lua"] = ""
        files["Addon/tools/gen.py"] = ""
        problems = package.check(self.make(files), POLICY)
        self.assertEqual(len(problems), 6, problems)
        joined = "\n".join(problems)
        for expected in (
            "Addon/UI/ui.lua: missing (loaded by Addon/UI/ui.xml)",
            "Addon/UI/ui.xml: names Interface\\AddOns\\Addon\\media\\Shade",
            "Addon/tests: shipped",
            "Addon/tools: shipped",
            "Addon/LICENSE: missing",
            "Lib/Lib.toc: missing",
        ):
            self.assertIn(expected, joined)

    def test_credits_and_every_folders_licence_must_ship(self):
        files = self.good()
        del files["Lib/LICENSE.txt"]
        files["Addon/README.md"] = "# A\n\nCredits are thin here. ## Credits\nThanks.\n"
        files["Addon/THIRD_PARTY.md"] = "# Inputs\n\n### Ideas and contributors\n\nNone.\n"
        problems = package.check(self.make(files), POLICY)
        self.assertEqual(
            problems,
            [
                "Lib/LICENSE: missing; every packaged folder ships its licence",
                "Addon/README.md: no `## Credits` section with text; credit what the addon uses",
                "Addon/THIRD_PARTY.md: no `## Ideas and contributors` section with text; credit what the addon uses",
            ],
        )
        del files["Addon/THIRD_PARTY.md"]
        problems = package.check(self.make(files), POLICY)
        self.assertIn("Addon/THIRD_PARTY.md: missing; it must ship", problems)
        del files["Addon/README.md"]
        problems = package.check(self.make(files), POLICY)
        self.assertIn("Addon/README.md: missing; it must ship", problems)
        self.assertEqual(sum("THIRD_PARTY.md" in problem for problem in problems), 1, problems)

    def test_the_main_folder_takes_any_licence_name(self):
        files = self.good()
        del files["Addon/LICENSE"]
        files["Addon/COPYING.md"] = "GPL"
        self.assertEqual(package.check(self.make(files), POLICY), [])
        del files["Addon/COPYING.md"]
        self.assertEqual(
            package.check(self.make(files), POLICY), ["Addon/LICENSE: missing; every packaged folder ships its licence"]
        )

    def test_licence_names_are_exact(self):
        for name in ("LICENSE", "license", "LICENCE.md", "UNLICENSE", "COPYING.txt", "License.TXT"):
            self.assertTrue(package.licence_file(name), name)
        for name in ("README.md", "LicenseCheck.lua", "Licenses.xml", "license_spec.lua", "MIT-LICENSE.txt"):
            self.assertFalse(package.licence_file(name), name)

    def test_sections_take_markdown_leeway_and_need_text(self):
        for text in (
            "## Credits\n\nThanks.\n",
            "   ## credits ##\nThanks.\n",
            "## Credits  \n\n- a\n",
            "## Credits\n### People\nThanks.\n",
            "## Credits\n\n## Other\nx\n## Credits\nThanks.\n",
            "## Credits\r\n\r\nThanks.\r\n",
            "## Credits\n~~~\ncode\n~~~\n",
        ):
            self.assertTrue(package.has_section(text, "## Credits"), text)
        for text in (
            "## Credits\n\n## Licence\nGPL\n",
            "## Credits\n",
            "    ## Credits\nThanks.\n",
            "### Credits\nThanks.\n",
            "```\n## Credits\nThanks.\n```\n",
            "## Credits and more\nThanks.\n",
            "Text ## Credits\nThanks.\n",
            "## Credits\n\n<!-- TODO: credit libraries -->\n",
            "<!--\n## Credits\nThanks\n-->\n",
            "```\n``` example\n## Credits\nfoo\n```\n",
            "## Credits\n\n---\n",
        ):
            self.assertFalse(package.has_section(text, "## Credits"), text)

    def test_a_licence_in_required_takes_any_licence_name(self):
        files = self.good()
        del files["Addon/LICENSE"]
        files["Addon/LICENCE.txt"] = "MIT"
        policy = package.Policy(addons=("Addon", "Lib"), required=("LICENSE", "THIRD_PARTY.md"))
        self.assertEqual(package.check(self.make(files), policy), [])

    def test_a_policy_heading_that_is_not_markdown_is_named(self):
        policy = package.Policy(addons=("Addon", "Lib"), credits=(("README.md", "Credits:"),))
        self.assertEqual(
            package.check(self.make(self.good()), policy),
            ["Addon/README.md: not an ATX Markdown heading: 'Credits:'; fix the policy's credits heading"],
        )

    def test_a_non_utf8_credits_file_is_named(self):
        root = self.make(self.good())
        (root / "Addon/THIRD_PARTY.md").write_bytes(b"## Ideas and contributors\nRen\xe9e\n")
        self.assertEqual(package.check(root, POLICY), ["Addon/THIRD_PARTY.md: not UTF-8"])

    def test_a_missing_addon_folder_and_a_lua_path_are_named(self):
        files = self.good()
        del files["Addon/media/dot.tga"]
        root = self.make({k: v for k, v in files.items() if not k.startswith("Lib/")})
        problems = package.check(root, POLICY)
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("Addon/Core.lua:1: names Interface\\AddOns\\Addon\\media\\Dot", problems[0] + problems[1])
        self.assertIn("Lib: not in", problems[0] + problems[1])

    def test_the_client_rules_for_case_prefixes_absolute_includes_and_flavours(self):
        files = self.good()
        files["Addon/Addon.toc"] = files["Addon/Addon.toc"].replace("Core.lua", "core.lua")
        files["Addon/Core.lua"] += 'local P = "Interface\\\\AddOns\\\\Addon\\\\media\\\\class_" .. class\n'
        files["Addon/UI/ui.xml"] = '<Ui><Script file="Interface\\AddOns\\Addon\\UI\\ui.lua"/></Ui>'
        files["Addon/Addon_Vanilla.toc"] = "Gone.lua\n"
        files["Addon/Tests/x.lua"] = ""
        problems = package.check(self.make(files), POLICY)
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("Addon/Tests: shipped", problems[0])
        self.assertIn("Addon/Gone.lua: missing (loaded by Addon/Addon_Vanilla.toc)", problems[1])

    def test_missing_support_is_a_problem_not_a_crash(self):
        root = self.make({})
        release = self.make({"Addon/Addon.toc": ""})
        policy = package.Policy(addons=("Addon",), specs=("tests/a_spec.lua",))
        self.assertIn("tests: not in the checkout", package.run_specs(root, release, policy)[0])

    @unittest.skipUnless(shutil.which("luajit"), "needs luajit")
    def test_specs_run_on_the_package_with_the_support_laid_over(self):
        root = self.make({"tests/a_spec.lua": 'assert(loadfile("Core.lua"))()\n', "Core.lua": ""})
        release = self.make({"Addon/Core.lua": "", "Addon/Addon.toc": "Core.lua\n"})
        policy = package.Policy(addons=("Addon",), specs=("tests/a_spec.lua",))
        self.assertEqual(package.run_specs(root, release, policy), [])
        (release / "Addon/Core.lua").unlink()
        problems = package.run_specs(root, release, policy)
        self.assertEqual(len(problems), 1)
        self.assertIn("fails on the packaged files", problems[0])

    def test_shipped_support_is_refused(self):
        root = self.make({"tests/a_spec.lua": ""})
        release = self.make({"Addon/tests/a_spec.lua": ""})
        policy = package.Policy(addons=("Addon",), specs=("tests/a_spec.lua",))
        self.assertIn("shipped in the package", package.run_specs(root, release, policy)[0])


if __name__ == "__main__":
    unittest.main()
