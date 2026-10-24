import tempfile
import unittest
from pathlib import Path

from forever_tools import art


class ArtTest(unittest.TestCase):
    def test_raw_art_is_flagged(self):
        cases = [
            'icon:SetAtlas("QuestNormal")\nicon:SetSize(14, 20)',
            "icon:SetTexture(file)",
            'button:SetNormalAtlas("RedButton-Expand")',
            'button:SetHighlightTexture("Interface\\\\Buttons\\\\UI-Common-MouseHilight")',
            'local mark = CreateAtlasMarkup("QuestNormal", 12, 20)',
            'local MARK = "|A:QuestNormal:12:20|a "',
            'return ("|T%d:14:20|t"):format(texture)',
        ]
        for source in cases:
            with self.subTest(source=source):
                found = art.check(source)
                self.assertEqual(len(found), 1, found)
                self.assertTrue(found[0][1].startswith("art-raw:"), found)

    def test_helpers_native_size_and_waivers_are_clean(self):
        cases = [
            'Art.Fit(icon, "QuestNormal", 14, 14)',
            'icon:SetAtlas("questlog-icon-setting", true)',
            "fill:SetColorTexture(0, 0, 0, 1)",
            "art:SetAtlas(CARD_ART) -- art-ok: nine-slice, margins set below",
            "-- art-ok: a square map tile, sized square below\ntexture:SetTexture(tile)",
            '-- icon:SetAtlas("QuestNormal") was here',
            'local text = "A|cffffffffB|r"',
        ]
        for source in cases:
            with self.subTest(source=source):
                self.assertEqual(art.check(source), [])

    def test_a_waiver_must_earn_its_place(self):
        self.assertTrue(art.check("local x = 1 -- art-ok: nothing here")[0][1].startswith("art-unused:"))
        found = art.check('icon:SetAtlas("QuestNormal") -- art-ok:')
        self.assertEqual([message.split(":")[0] for _, message in found], ["art-raw", "art-unused"])

    def test_xml(self):
        flagged = '<Texture parentKey="Icon" atlas="QuestNormal" setAllPoints="true"/>'
        self.assertEqual(len(art.check(flagged, xml=True)), 1)
        self.assertEqual(art.check('<Texture atlas="QuestNormal" useAtlasSize="true"/>', xml=True), [])
        self.assertEqual(art.check("<!-- art-ok: a square atlas on a square pin -->\n" + flagged, xml=True), [])
        self.assertEqual(art.check('<Texture parentKey="Fill"><Color r="0" g="0" b="0"/></Texture>', xml=True), [])

    def test_run_exempts_only_a_real_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Art.lua").write_text('t:SetAtlas("a")\n', encoding="utf-8")
            (root / "Panel.lua").write_text('Art.Fit(t, "a", 1, 1)\n', encoding="utf-8")
            files = [root / "Art.lua", root / "Panel.lua"]
            self.assertEqual(art.run(root, files, frozenset({"Art.lua"})), 0)
            self.assertEqual(art.run(root, files, frozenset()), 1)
            self.assertEqual(art.run(root, files, frozenset({"Art.lua", "Gone.lua"})), 1)


if __name__ == "__main__":
    unittest.main()
