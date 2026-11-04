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

    def test_indirect_legacy_chrome_references(self):
        self.assertTrue(assets.check('CreateFrame("Frame", nil, p, "DialogBorderTemplate")'))
        self.assertTrue(assets.check("f:SetBackdrop(BACKDROP_DIALOG_32_32)"))
        for name in assets.LEGACY_CHROME_TEMPLATES:
            with self.subTest(template=name):
                self.assertTrue(assets.check(f'CreateFrame("Frame", nil, p, "{name}")'))
                self.assertTrue(assets.check(f'<Frame inherits="OtherTemplate, {name}"/>', ".xml"))
        for name in assets.LEGACY_BACKDROPS:
            with self.subTest(backdrop=name):
                self.assertTrue(assets.check(f"f:SetBackdrop({name})"))
                self.assertTrue(assets.check(f"local backdrop = _G.{name}"))
                self.assertTrue(assets.check(f'<KeyValue key="backdropInfo" value="{name}" type="global"/>', ".xml"))
                self.assertTrue(assets.check(f"backdrop = {name}", ".py"))
                self.assertEqual(assets.check(f"-- {name}"), [])
                self.assertEqual(assets.check(f"# {name}", ".py"), [])
        self.assertEqual(assets.check('CreateFrame("Frame", nil, p, "BackdropTemplate")'), [])
        self.assertEqual(assets.check("f:SetBackdrop(customBackdrop)"), [])
        self.assertEqual(assets.check('CreateFrame("Frame", nil, p, "DialogBorderOpaqueTemplate")'), [])

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

    def test_xml_backdrop_file_attributes_are_checked(self):
        source = (
            '<Backdrop bgFile="Interface\\DialogFrame\\UI-DialogBox-Background" '
            'edgeFile="Interface\\DialogFrame\\UI-DialogBox-Border"/>'
        )
        self.assertEqual(
            assets.references(source, ".xml"),
            [
                (1, "Interface\\DialogFrame\\UI-DialogBox-Background"),
                (1, "Interface\\DialogFrame\\UI-DialogBox-Border"),
            ],
        )
        self.assertEqual(len(assets.check(source, ".xml")), 2)

    def test_xml_script_bodies_and_multiline_attributes_are_checked(self):
        source = (
            '<Frame inherits="OtherTemplate,\n UIPanelButtonTemplate">\n'
            '  <OnLoad>self:SetNormalTexture("Interface\\Buttons\\UI-Panel-Button-Up")</OnLoad>\n'
            "</Frame>"
        )
        findings = assets.check(source, ".xml")
        self.assertEqual(len(findings), 2)
        self.assertTrue(any(line == 1 and "UIPanelButtonTemplate" in message for line, message in findings))
        self.assertTrue(any(line == 3 and "UI-Panel-Button-Up" in message for line, message in findings))

    def test_xml_text_atlas_markup_is_checked(self):
        source = '<Button text="|TInterface/Buttons/UI-Panel-Button-Up:16|t"/>'
        self.assertEqual(len(assets.check(source, ".xml")), 1)

    def test_xml_cdata_and_entities_are_checked(self):
        source = (
            '<OnLoad><![CDATA[self:SetNormalTexture("Interface\\Buttons\\UI-Panel-Button-Up")]]></OnLoad>\n'
            "<OnShow>self:SetNormalTexture(&quot;Interface\\Buttons\\UI-Panel-Button-Down&quot;)</OnShow>"
        )
        findings = assets.check(source, ".xml")
        self.assertEqual(len(findings), 2)

    def test_xml_cdata_keeps_literal_entities_and_comments(self):
        source = (
            '<OnLoad><![CDATA[local text = "&quot; <!-- literal -->"\n'
            'self:SetTexture("Interface\\Buttons\\UI-Panel-Button-Up")]]></OnLoad>'
        )
        findings = assets.check(source, ".xml")
        self.assertEqual(len(findings), 1)

    def test_xml_cdata_after_whitespace_is_checked(self):
        source = (
            '<OnLoad>\n<![CDATA[local value = "&quot;"\n'
            'self:SetTexture("Interface\\Buttons\\UI-Panel-Button-Up")]]>\n</OnLoad>'
        )
        self.assertEqual(len(assets.check(source, ".xml")), 1)

    def test_xml_attributes_inside_cdata_cannot_hide_real_attributes(self):
        source = (
            '<OnLoad><![CDATA[local value = "file=" ]]></OnLoad>\n'
            '<Texture file="Interface\\Buttons\\UI-Panel-Button-Up"/>'
        )
        self.assertEqual(len(assets.check(source, ".xml")), 1)

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

    def test_inline_atlas_and_inherited_templates(self):
        self.assertTrue(assets.check('label:SetText("|A:GarrMission_TopBar:16:16|a")'))
        self.assertTrue(assets.check('label:SetText("|A:128-GoldRedButton-Left:16:16|a")'))
        for template in ("MagicButtonTemplate", "LFGListMagicButtonTemplate", "UIPanelLargeSilverButton"):
            self.assertIsNotNone(assets.problem(template))
        self.assertIsNotNone(assets.problem("Interface/Buttons/UI-SilverButtonLG-Left-Up"))

    def test_active_renderer_modules_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / "tools"
            tools.mkdir()
            for name in ("micro_menu_render.py", "rarity.py"):
                (tools / name).write_text('button = "UIPanelButtonTemplate"\n')
            files = assets.renderer_files(root)
            self.assertEqual({path.name for path in files}, {"micro_menu_render.py", "rarity.py"})
            self.assertEqual(assets.run(files), 1)


if __name__ == "__main__":
    unittest.main()
