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
        self.assertIn("SetBackdrop", found[2])

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
