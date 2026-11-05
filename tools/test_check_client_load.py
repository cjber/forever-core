"""Tests for tools/check_client_load.py."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import check_client_load as gate

KNOWN = {"GameFontNormal", "GameFontNormalLarge", "GameFontHighlightHuge", "ChatFontNormal"}


def lua(source):
    return [name for _, name in gate.lua_uses(gate._tokenize(source))]


class LuaUsesTest(unittest.TestCase):
    def test_create_font_string_third_argument(self):
        self.assertEqual(lua('local t = f:CreateFontString(nil, "ARTWORK", "GameFontLarge")'), ["GameFontLarge"])

    def test_set_font_object_forms(self):
        source = (
            'b:SetNormalFontObject("A") b:SetHighlightFontObject("B") b:SetDisabledFontObject("C") e:SetFontObject("D")'
        )
        self.assertEqual(sorted(lua(source)), ["A", "B", "C", "D"])

    def test_each_branch_of_a_conditional(self):
        source = 'b:SetFontObject(entry.kind == "title" and "Yes" or "No")'
        self.assertEqual(sorted(lua(source)), ["No", "Yes"])

    def test_bare_global_but_not_a_local_or_parameter(self):
        source = """
local Font = "x"
local function f(titleFont, Param)
	a:SetFontObject(GameFontHighlight)
	a:CreateFontString(nil, "OVERLAY", titleFont)
	a:SetFontObject(Font)
	a:SetFontObject(Param)
	a:SetFontObject(ns.Font)
end
"""
        self.assertEqual(lua(source), ["GameFontHighlight"])

    def test_nested_and_concatenated_strings_are_not_fonts(self):
        self.assertEqual(lua('a:SetFontObject(Pick("x")) a:SetFontObject("Game" .. size)'), [])

    def test_simple_html_takes_the_font_second(self):
        self.assertEqual(lua('html:SetFontObject("h1", "Header")'), ["Header"])

    def test_definitions(self):
        tokens = gate._tokenize('CreateFont("MyFont") CreateFontFamily("MyFamily", {})')
        self.assertEqual(gate.lua_definitions(tokens), {"MyFont", "MyFamily"})


class XmlTest(unittest.TestCase):
    SOURCE = """<Ui>
	<Font name="MyFont" inherits="GameFontNormal" virtual="true"/>
	<FontString name="MyText" inherits="MissingA" virtual="true"/>
	<!-- <FontString inherits="Commented"/> -->
	<Frame name="X" inherits="BackdropTemplate">
		<Layers><Layer><FontString inherits="MissingB, GameFontNormal"/></Layer></Layers>
		<Frames><EditBox font="MissingC"/><Button><NormalFont style="MissingD"/></Button></Frames>
	</Frame>
	<Font name="Path" font="Fonts\\FRIZQT__.TTF"/>
</Ui>
"""

    def test_uses(self):
        self.assertEqual(
            gate.xml_uses(self.SOURCE),
            [
                (2, "GameFontNormal"),
                (3, "MissingA"),
                (6, "MissingB"),
                (6, "GameFontNormal"),
                (7, "MissingC"),
                (7, "MissingD"),
            ],
        )

    def test_definitions(self):
        self.assertEqual(gate.xml_definitions(self.SOURCE), {"MyFont", "MyText", "Path"})


class TocTest(unittest.TestCase):
    def test_bindings_listed(self):
        source = "## Interface: 16001\nCore.lua\nBindings.xml\n# Bindings.xml\nUI\\bindings.XML [AllowLoad Game]\n"
        self.assertEqual([line for line, _ in gate.toc_findings(source)], [3, 5])


class RunTest(unittest.TestCase):
    def run_in(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, text in files.items():
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(text, encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                failed = gate.check(gate.addon_files(root), KNOWN, root)
            return failed, out.getvalue()

    def test_the_settings_page_bug(self):
        failed, out = self.run_in({"UI/SettingsPage.lua": 'p:CreateFontString(nil, "ARTWORK", "GameFontLarge")\n'})
        self.assertTrue(failed)
        self.assertIn('UI/SettingsPage.lua:1: client-load: font object "GameFontLarge"', out)

    def test_client_and_addon_fonts_pass(self):
        failed, out = self.run_in(
            {
                "Core.lua": 'CreateFont("AddonFont")\n',
                "Fonts.xml": '<Ui><Font name="XmlFont" virtual="true"/></Ui>\n',
                "Libs/Lib/Lib.xml": '<Ui><Font name="LibFont" virtual="true"/></Ui>\n',
                "UI.lua": 'a:SetFontObject("AddonFont") a:SetFontObject("XmlFont") a:SetFontObject("LibFont")\n'
                'a:CreateFontString(nil, "ARTWORK", "GameFontHighlightHuge")\n',
                "Addon.toc": "Core.lua\nFonts.xml\nUI.lua\n",
            }
        )
        self.assertFalse(failed, out)

    def test_skipped_folders_and_bindings(self):
        failed, out = self.run_in(
            {
                "tests/spec.lua": 'a:SetFontObject("Nope")\n',
                ".hidden/x.lua": 'a:SetFontObject("Nope")\n',
                "Addon.toc": "Core.lua\nBindings.xml\n",
            }
        )
        self.assertTrue(failed)
        self.assertEqual(out.count("client-load"), 1)
        self.assertIn("Addon.toc:2: client-load: the client loads Bindings.xml by itself", out)

    def test_the_shipped_font_list_is_the_clients(self):
        fonts = gate.blizzard_fonts()
        self.assertIn("GameFontNormalLarge", fonts)
        self.assertIn("GameFontHighlightHuge", fonts)
        self.assertNotIn("GameFontLarge", fonts)


if __name__ == "__main__":
    unittest.main()
