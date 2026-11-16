"""Offline regressions using the actual pinned font coverage, not fitted glyph fixtures."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLING = Path(__file__).resolve().parents[1] / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))
from forever_tools.font_glyphs import check, font_path, main, missing, read_entries  # noqa: E402
from gen_font_glyphs import ranges, read_xml, xml_paths  # noqa: E402

DATA = json.loads((TOOLING / "forever_tools/font_glyphs.json").read_text())


class FontGlyphTests(unittest.TestCase):
    def test_reported_russian_middle_dot(self):
        path, absent = missing(DATA, "ruRU", "GameFontNormal", "А · Б")
        self.assertEqual(path, "fonts/frizqt___cyr.ttf")
        self.assertEqual(absent, [0xB7])

    def test_roman_middle_dot_is_present(self):
        self.assertEqual(missing(DATA, "enUS", "GameFontNormal", "A · B")[1], [])

    def test_no_script_detection_from_text(self):
        self.assertEqual(missing(DATA, "ruRU", "GameFontNormal", "Latin ·")[1], [0xB7])

    def test_skurri_verified_controls(self):
        russian = next(
            name for name, members in DATA["objects"].items() if members.get("russian") == "fonts/skurri_cyr.ttf"
        )
        self.assertEqual(missing(DATA, "ruRU", russian, "А · Б")[1], [])
        roman = next(name for name, members in DATA["objects"].items() if members.get("roman") == "fonts/skurri.ttf")
        self.assertEqual(missing(DATA, "enUS", roman, "•")[1], [0x2022])

    def test_cjk_and_korean_members(self):
        for locale, path, text in (
            ("koKR", "fonts/2002.ttf", "한글"),
            ("zhCN", "fonts/arkai_t.ttf", "中文"),
            ("zhTW", "fonts/blei00d.ttf", "中文"),
        ):
            with self.subTest(locale=locale):
                self.assertEqual(font_path(DATA, locale, "GameFontNormal"), path)
                self.assertEqual(missing(DATA, locale, "GameFontNormal", text)[1], [])

    def test_inherited_styles_resolve(self):
        for locale in ("enUS", "ruRU", "koKR", "zhCN", "zhTW"):
            self.assertEqual(font_path(DATA, locale, "GameFontHighlight"), font_path(DATA, locale, "GameFontNormal"))

    def test_unknown_font_and_locale_fail_closed(self):
        for locale, font in (("xxXX", "GameFontNormal"), ("ruRU", "InventedFont")):
            with self.assertRaises(KeyError):
                missing(DATA, locale, font, "a")

    def test_translation_parser_values_only_and_escaped_utf8(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ruRU.lua"
            path.write_text(
                'local _, ns = ...\nif GetLocale() ~= "ruRU" then return end\nlocal L = ns.L\n'
                '-- · is a comment\nL["· is a key"] = "А"\n'
                'L["bad"] = "\\194\\183" .. " ok"\n'
            )
            problems = check(path, DATA, "GameFontNormal")
            self.assertEqual(len(problems), 1)
            self.assertIn(":6: 'bad': U+00B7", problems[0])

    def test_wrong_guard_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ruRU.lua"
            path.write_text('local _, ns = ...\nif GetLocale() ~= "deDE" then return end\nlocal L = ns.L\n')
            with self.assertRaisesRegex(ValueError, "does not match"):
                check(path, DATA, "GameFontNormal")

    def test_missing_binding_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(main(Path(folder), []), 1)

    def test_layout_controls_are_not_glyphs(self):
        self.assertEqual(missing(DATA, "ruRU", "GameFontNormal", "А\n\t\rБ")[1], [])

    def test_every_font_has_provenance(self):
        self.assertEqual(len(DATA["ui_revision"]), 40)
        self.assertEqual(len(DATA["xml_sources"]), 907)
        self.assertIsInstance(DATA["xml_sha256"], str)
        self.assertEqual(len(bytes.fromhex(DATA["xml_sha256"])), 32)
        for font in DATA["fonts"].values():
            self.assertEqual(len(font["sha256"]), 64)
            self.assertIn(DATA["font_build"], font["url"])

    def test_cross_addon_inheritance(self):
        with tempfile.TemporaryDirectory() as folder:
            ui = Path(folder)
            shared = ui / "Interface/AddOns/Blizzard_Fonts_Shared"
            shared.mkdir(parents=True)
            (shared / "Blizzard_Fonts_Shared.toc").write_text(
                "## AllowLoad: Both\nFonts.xml\nGlue.xml [AllowLoad Glue]\n"
            )
            (shared / "Glue.xml").write_text('<Ui><Font name="GlueOnly" inherits="Missing"/></Ui>')
            (shared / "Fonts.xml").write_text(
                '<Ui><FontFamily name="Base"><Member alphabet="russian">'
                '<Font font="Fonts\\FIRST.TTF"/></Member></FontFamily></Ui>'
            )
            other = ui / "Interface/AddOns/Blizzard_Other/Nested/Fonts.xml"
            other.parent.mkdir(parents=True)
            (other.parent.parent / "Blizzard_Other.toc").write_text("Root.xml\n")
            (other.parent.parent / "Root.xml").write_text('<Ui><Include file="Nested/Fonts.xml"/></Ui>')
            other.write_text('<Ui><Font name="Style" inherits="Base"/></Ui>')
            paths = xml_paths(ui)
            objects, sources, digest = read_xml(paths)
            self.assertEqual(objects["Style"], {"russian": "fonts/first.ttf"})
            self.assertEqual(sources, [name for name, _ in paths])
            self.assertEqual(len(sources), 3)
            expected = b"".join(name.encode() + b"\0" + path.read_bytes() for name, path in paths)
            self.assertEqual(digest, hashlib.sha256(expected).hexdigest())
            self.assertNotEqual(digest, read_xml(list(reversed(paths)))[2])
            renamed = [("renamed.xml", paths[0][1]), *paths[1:]]
            self.assertNotEqual(digest, read_xml(renamed)[2])
            other.write_bytes(other.read_bytes() + b"\n")
            self.assertNotEqual(digest, read_xml(paths)[2])
            self.assertNotIn("GlueOnly", objects)

    def test_toc_variants_and_game_conditions(self):
        with tempfile.TemporaryDirectory() as folder:
            ui = Path(folder)
            addon = ui / "Interface/AddOns/Blizzard_Test"
            addon.mkdir(parents=True)
            for suffix in ("", "_Vanilla", "_Mainline", "_Camelot"):
                (addon / f"Blizzard_Test{suffix}.toc").write_text(f"{suffix or 'Default'}.xml\n")
            (addon / "Blizzard_Test_Camelot.toc").write_text(
                "[Family]/Fonts.xml [AllowLoadGameType mainline]\n"
                "Missing.xml [AllowLoadGameType classic]\n"
                "Missing.xml [ExcludeLoadGameType camelot]\n"
            )
            (addon / "Mainline").mkdir()
            (addon / "Mainline/Fonts.xml").write_text('<Ui><Font name="Selected" font="Fonts/A.ttf"/></Ui>')
            glue = addon.parent / "Blizzard_Glue"
            glue.mkdir()
            (glue / "Blizzard_Glue.toc").write_text("## AllowLoad: Glue\nMissing.xml\n")
            objects, _, _ = read_xml(xml_paths(ui))
            self.assertEqual(objects, {"Selected": {"*": "fonts/a.ttf"}})

    def test_xml_cycle(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fonts.xml"
            path.write_text('<Ui><Font name="A" inherits="B"/><Font name="B" inherits="A"/></Ui>')
            with self.assertRaisesRegex(ValueError, "inheritance cycle"):
                read_xml([("fonts.xml", path)])

    def test_conflicting_redefinition_names_both_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder) / "a.xml", Path(folder) / "b.xml"
            first.write_text('<Ui><Font name="Base" font="Fonts/first.ttf"/></Ui>')
            second.write_text('<Ui><Font name="Base" font="Fonts/last.ttf"/></Ui>')
            with self.assertRaisesRegex(ValueError, "conflicting font 'Base': a.xml and b.xml"):
                read_xml([("a.xml", first), ("b.xml", second)])
            second.write_text('<Ui><Font name="Base" font="Fonts/FIRST.TTF"/></Ui>')
            self.assertEqual(read_xml([("a.xml", first), ("b.xml", second)])[0]["Base"], {"*": "fonts/first.ttf"})

    def test_markup_metadata_is_not_displayed(self):
        text = "|cffffffffА|r|T·:16|t|A·:16:16|a|Hitem:·|hБ|h"
        self.assertEqual(missing(DATA, "ruRU", "GameFontNormal", text)[1], [])
        self.assertEqual(missing(DATA, "ruRU", "GameFontNormal", "|Hitem:1|h·|h")[1], [0xB7])
        self.assertEqual(missing(DATA, "ruRU", "GameFontNormal", "||T·:16|t")[1], [0xB7])
        self.assertEqual(missing(DATA, "ruRU", "GameFontNormal", "|T·")[1], [0xB7])

    def test_english_preamble_and_line_numbers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "enUS.lua"
            path.write_text('local _, ns = ...\nlocal L = {}\nns.L = L\nL["x"] = "•"\n')
            skurri = next(
                name for name, members in DATA["objects"].items() if members.get("roman") == "fonts/skurri.ttf"
            )
            problems = check(path, DATA, skurri)
            self.assertEqual(len(problems), 1)
            self.assertIn(":4: 'x': U+2022", problems[0])

    def test_english_assignment_forms(self):
        source = (
            "local _, ns = ...\n"
            "ns.L = {\n"
            '\tGO = "Go",\n'
            '\tLONG = "a" .. "b";\n'
            '\t["Key"] = "Text",\n'
            '\tRACES = ITEM_RACES_ALLOWED or "Races: %s",\n'
            '\tCALL = format("%d", 1),\n'
            "}\n"
            'ns.L["Later"] = "Later"\n'
            'local L = ns.L\nL.NAME = "Name"\n'
            '_G.BINDING_HEADER_X = "Ignored"\n'
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "enUS.lua"
            path.write_text(source)
            locale, entries = read_entries(path)
        self.assertEqual(locale, "enUS")
        self.assertEqual(
            {key: (entry.text, entry.line) for key, entry in entries.items()},
            {"GO": ("Go", 3), "LONG": ("ab", 4), "Key": ("Text", 5), "Later": ("Later", 9), "NAME": ("Name", 11)},
        )

    def test_english_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "enUS.lua"
            path.write_text('local _, ns = ...\nns.L = { A = "a" }\nns.L.A = "b"\n')
            with self.assertRaisesRegex(ValueError, "assigned twice"):
                read_entries(path)

    def test_english_fallback_uses_target_locale_font(self):
        with tempfile.TemporaryDirectory() as folder:
            english, russian = Path(folder) / "enUS.lua", Path(folder) / "ruRU.lua"
            english.write_text('local L = {}\nL["fallback"] = "·"\n')
            russian.write_text('local _, ns = ...\nif GetLocale() ~= "ruRU" then return end\nlocal L = ns.L\n')
            problems = check(russian, DATA, "GameFontNormal", (english, read_entries(english)[1]))
            self.assertEqual(len(problems), 1)
            self.assertIn("enUS.lua:2: 'fallback': U+00B7", problems[0])
            self.assertIn("ruRU", problems[0])

    def test_ranges_are_lossless(self):
        points = {0, 1, 3, 0x10000, 0x10001}
        self.assertEqual({p for lo, hi in ranges(points) for p in range(lo, hi + 1)}, points)


if __name__ == "__main__":
    unittest.main()
