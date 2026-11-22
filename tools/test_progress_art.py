"""The registry applies only where the source establishes a progress role."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/wow-forever-addon/tooling"))
from forever_tools import progress_art  # noqa: E402


class ProgressArtTest(unittest.TestCase):
    def check(self, source, suffix=".lua", addon="Fixture", file="UI/Example.lua"):
        return [message for _, message in progress_art.check(source, suffix, addon, file, progress_art.load_registry())]

    def test_native_bar_and_content_icon(self):
        self.assertEqual(
            self.check("""
local bar = CreateFrame("StatusBar", nil, parent)
local bg = bar:CreateTexture(nil, "BACKGROUND")
bg:SetAtlas("common-stat-bar-BG")
local fill = bar:CreateTexture()
fill:SetAtlas("common-stat-bar-white")
bar:SetStatusBarTexture(fill)
icon:SetTexture("Interface/Icons/INV_Misc_Book_09")
line:SetColorTexture(1, 1, 1, 1)
local alternate = CreateFrame("Frame", nil, parent, "ColoredProgressBarTemplate")
"""),
            [],
        )

    def test_custom_fill_and_background(self):
        found = self.check("""
Style.BAR_TEXTURE = "Interface/Buttons/" .. "WHITE8X8"
local bar = CreateFrame("StatusBar", nil, parent)
bar:SetStatusBarTexture(Style.BAR_TEXTURE)
local bg = bar:CreateTexture(nil, "BACKGROUND")
bg:SetColorTexture(0, 0, 0, 1)
bar:SetBackdrop({ bgFile = "Interface/Buttons/WHITE8X8" })
""")
        self.assertEqual(len(found), 3)
        self.assertIn("WHITE8X8", found[0])
        self.assertIn("background", found[1])
        self.assertIn("WHITE8X8", found[2])

    def test_xml_role_and_native_exception(self):
        found = self.check(
            """
<Ui>
  <StatusBar name="Meter" inherits="OtherTemplate"><BarTexture file="custom.blp"/></StatusBar>
  <Texture file="Interface/Icons/INV_Misc_Book_09"/>
</Ui>
""",
            ".xml",
        )
        self.assertEqual(len(found), 2)
        source = """
local bar = CreateFrame("Frame", nil, parent, "ColoredProgressBarTemplate")
bar.Fill:SetAtlas("common-stat-bar-green")
"""
        self.assertEqual(self.check(source, addon="AdventureGuideForever", file="UI/Overview.lua"), [])
        self.assertEqual(len(self.check(source, addon="AdventureGuideForever", file="UI/Other.lua")), 1)

    def test_lua_widget_scope_and_valid_nonasset_escape(self):
        self.assertEqual(
            self.check(r"""
local text = "\x41"
local function one()
    local bar = CreateFrame("StatusBar", nil, parent)
    bar:SetStatusBarTexture("common-stat-bar-white")
end
local function two()
    local bar = CreateFrame("Frame", nil, parent)
    bar:SetBackdrop({ bgFile = "custom.blp" })
end
"""),
            [],
        )

    def test_template_mixins_and_numeric_fill(self):
        findings = self.check("""
local bar = CreateFrame("Frame", nil, parent, "ColoredProgressBarTemplate, BackdropTemplate")
bar:SetBackdrop({ bgFile = "custom.blp" })
local status = CreateFrame("StatusBar", nil, parent)
status:SetStatusBarTexture(123456)
""")
        self.assertEqual(len(findings), 2)
        self.assertIn("background", findings[0])
        self.assertIn("123456", findings[1])

    def test_xml_solid_background(self):
        findings = self.check(
            """
<Ui>
  <StatusBar name="Meter">
    <Layers><Layer level="BACKGROUND"><Texture><Color r="0" g="0" b="0"/></Texture></Layer></Layers>
    <BarTexture atlas="common-stat-bar-white"/>
  </StatusBar>
</Ui>
""",
            ".xml",
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("Meter background", findings[0])


if __name__ == "__main__":
    unittest.main()
