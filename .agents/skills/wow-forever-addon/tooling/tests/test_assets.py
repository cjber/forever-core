import tempfile
import unittest
from pathlib import Path

from forever_tools import art, assets


class AssetsTest(unittest.TestCase):
    def test_legacy_family_and_templates(self):
        for value in (
            "Interface\\Buttons\\UI-Panel-Button-Up",
            "interface/buttons/ui-panel-button-disabled.blp",
            "Interface/Buttons/UI-DialogBox-GoldButton-Up-Left",
            "Interface/DialogFrame/UI-DialogBox-Border",
            "Interface/Tooltips/UI-Tooltip-Background",
            "UIPanelButtonTemplate",
            "SomethingElse, UIPanelButtonNoTooltipTemplate",
            *assets.LEGACY_BUTTON_TEMPLATES,
            "128-GoldRedButton-Left",
            "SharedGoldRedButtonSmallTemplate",
        ):
            with self.subTest(value=value):
                self.assertIsNotNone(assets.problem(value))

    def test_current_set_and_content_icons(self):
        for value in (*assets.APPROVED_BUTTON_TEMPLATES, "128-RedButton-Left", "Interface/Icons/INV_Misc_Book_09"):
            self.assertIsNone(assets.problem(value))

    def test_lua_xml_and_renderer(self):
        self.assertTrue(assets.check('local TEMPLATE = "UIPanelButtonTemplate"'))
        self.assertTrue(assets.check('<Button inherits="UIPanelButtonTemplate"/>', ".xml"))
        self.assertTrue(assets.check('<KeyValue key="atlasName" value="128-GoldRedButton"/>', ".xml"))
        self.assertTrue(assets.check('ui.texture("interface/buttons/ui-panel-button-down.blp")', ".py"))
        self.assertEqual(assets.check('-- "UIPanelButtonTemplate" is forbidden'), [])
        self.assertEqual(assets.check('<!-- <Button inherits="UIPanelButtonTemplate"/> -->', ".xml"), [])

    def test_art_helper_and_shape_waiver_cannot_bypass_blacklist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = root / "Art.lua"
            helper.write_text('t:SetAtlas("GarrMission_EncounterAbilityBorder") -- art-ok: square\n')
            self.assertEqual(art.run(root, [helper], frozenset({"Art.lua"})), 1)
            self.assertEqual(art.run(root, [helper], frozenset()), 1)

    def test_long_strings_and_constant_concatenation(self):
        self.assertTrue(assets.check("t:SetTexture([=[Interface/Buttons/UI-Panel-Button-Up]=])"))
        self.assertTrue(assets.check('local template = "UIPanel" .. "ButtonTemplate"'))
        self.assertTrue(assets.check('local path = "Interface/Buttons/UI-" .. "Panel-Button-Up"'))
        self.assertEqual(assets.check('--[=[ "UIPanelButtonTemplate" ]=]'), [])
        self.assertTrue(assets.check('label:SetText("Old |TInterface/Buttons/UI-Panel-Button-Up:16|t")'))
        self.assertTrue(assets.check('template = "UIPanel" + "ButtonTemplate"', ".py"))


if __name__ == "__main__":
    unittest.main()
