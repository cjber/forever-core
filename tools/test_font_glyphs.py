"""Offline regressions using the actual pinned font coverage, not fitted glyph fixtures."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLING = Path(__file__).resolve().parents[1] / ".agents/skills/wow-forever-addon/tooling"
sys.path.insert(0, str(TOOLING))
from forever_tools.font_glyphs import check, font_path, main, missing, read_entries  # noqa: E402
from gen_font_glyphs import ranges, read_xml  # noqa: E402

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
        self.assertEqual(len(DATA["xml_sha256"]), 8)
        for font in DATA["fonts"].values():
            self.assertEqual(len(font["sha256"]), 64)
            self.assertIn(DATA["font_build"], font["url"])

    def test_xml_order_inheritance_and_case(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder) / "a.xml", Path(folder) / "b.xml"
            first.write_text(
                '<Ui><FontFamily name="Base"><Member alphabet="russian">'
                '<Font font="Fonts\\FIRST.TTF"/></Member></FontFamily>'
                '<Font name="Style" inherits="Base"/></Ui>'
            )
            second.write_text(
                '<Ui><FontFamily name="Base"><Member alphabet="russian">'
                '<Font font="Fonts\\LAST.TTF"/></Member></FontFamily></Ui>'
            )
            objects, hashes = read_xml([("a", first), ("b", second)])
            self.assertEqual(objects["Style"], {"russian": "fonts/last.ttf"})
            self.assertEqual(len(hashes), 2)

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
