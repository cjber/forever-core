import tempfile
import unittest
from pathlib import Path

from forever_tools import locales

TEMPLATE = """\
-- Template.
local _, ns = ...
if GetLocale() ~= "deDE" then
\treturn
end
local L = ns.L
L["%d left"] = "%d left"
L["%s is at %s"] = "%s is at %s"
L["|cffffd100Gold|r line"] = "|cffffd100Gold|r line"
L["Two\\nlines"] = "Two\\nlines"
L["CARD_TITLE"] =
\t"Next " .. "stop"
L["Done 100%"] = "Done 100%"
L["%d%% done"] = "%d%% done"
"""


def translation(locale, lines):
    body = "\n".join(lines)
    return f"""-- Machine translated (2026-10-16); corrections welcome.
local _, ns = ...
if GetLocale() ~= "{locale}" then
\treturn
end
local L = ns.L
{body}
"""


class LocalesTest(unittest.TestCase):
    def make(self, files, toc_locales=("deDE",)):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        toc = "## Interface: 11508\nLocales\\enUS.lua\n" + "".join(f"Locales\\{code}.lua\n" for code in toc_locales)
        files = {"Addon.toc": toc, "Locales/enUS.lua": "local _, ns = ...\n", "Locales/phrases.txt": TEMPLATE, **files}
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text, encoding="utf-8")
        return root

    def check(self, lines, locale="deDE", **options):
        return locales.check(self.make({f"Locales/{locale}.lua": translation(locale, lines)}, **options))

    def test_a_good_translation_passes_and_reports_coverage(self):
        problems, coverage = self.check(
            [
                'L["%d left"] = "%d übrig"',
                'L["%s is at %s"] = "%2$s: %1$s"',
                'L["|cffffd100Gold|r line"] = "|cffffd100Gold|r-Zeile"',
                'L["Two\\nlines"] = "Zwei\\nZeilen"',
                'L["CARD_TITLE"] = "Nächster " .. "Halt"',
                'L["Done 100%"] = "Fertig 100 %"',
                'L["%d%% done"] = "%d %% fertig"',
            ]
        )
        self.assertEqual(problems, [])
        self.assertEqual(coverage[0], "deDE: 7 of 7 lines (100%)")
        self.assertIn("frFR: no file, so English", coverage)
        self.assertEqual(len(coverage), len(locales.LOCALES))

    def test_gaps_fall_back_to_english_and_only_lower_coverage(self):
        problems, coverage = self.check(['L["%d left"] = "%d übrig"'])
        self.assertEqual(problems, [])
        self.assertEqual(coverage[0], "deDE: 1 of 7 lines (14%)")
        root = self.make({"Locales/deDE.lua": translation("deDE", ['L["%d left"] = "%d übrig"'])})
        problems, _ = locales.check(root, release=True)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("6 line(s) untranslated", problems[0])

    def test_placeholder_mismatches_are_named(self):
        problems, _ = self.check(
            [
                'L["%d left"] = "%s übrig"',
                'L["%s is at %s"] = "%s"',
                'L["Done 100%"] = "Fertig %d"',
                'L["%d%% done"] = "%d % fertig"',
            ]
        )
        self.assertEqual(len(problems), 4, problems)
        joined = "\n".join(problems)
        self.assertIn("'%d left': placeholders ['d'] in English but ['s'] here", joined)
        self.assertIn("'%s is at %s': placeholders ['s', 's'] in English but ['s'] here", joined)
        self.assertIn("'Done 100%': placeholders ['d'] here but none in English", joined)
        self.assertIn("'%d%% done': string.format would reject %", joined)

    def test_a_rejected_format_is_named(self):
        problems, _ = self.check(['L["%d left"] = "%123d übrig"'])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("string.format would reject %123d", problems[0])

    def test_positions_must_run_without_gaps(self):
        problems, _ = self.check(['L["%s is at %s"] = "%3$s: %1$s"'])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("positions must run 1..n", problems[0])

    def test_escape_counts_must_match(self):
        problems, _ = self.check(['L["|cffffd100Gold|r line"] = "Gold"', 'L["Two\\nlines"] = "Zwei Zeilen"'])
        joined = "\n".join(problems)
        self.assertIn("1 '|cffffd100' in English but 0 here", joined)
        self.assertIn("1 '|r' in English but 0 here", joined)
        self.assertIn("1 newline in English but 0 here", joined)

    def test_unknown_keys_duplicates_and_bad_statements_fail(self):
        problems, _ = self.check(['L["Gone"] = "Weg"'])
        self.assertIn("'Gone' is not in phrases.txt", problems[0])
        problems, _ = self.check(['L["%d left"] = "%d übrig"', 'L["%d left"] = "%d noch"'])
        self.assertIn("assigned twice", problems[0])
        problems, _ = self.check(['L["%d left"] = format("%d")'])
        self.assertIn("must be assigned a string", problems[0])
        problems, _ = self.check(['print("hi")'])
        self.assertIn('expected L["key"] = "text"', problems[0])

    def test_a_file_the_toc_does_not_load_or_that_guards_another_locale_fails(self):
        problems, _ = self.check(['L["%d left"] = "%d übrig"'], toc_locales=())
        self.assertEqual(problems, ["Locales/deDE.lua: not loaded by Addon.toc; list it after Locales/enUS.lua"])
        root = self.make({"Locales/frFR.lua": translation("deDE", [])}, toc_locales=("frFR",))
        problems, _ = locales.check(root)
        self.assertEqual(problems, ["Locales/frFR.lua: its GetLocale guard names 'deDE', not 'frFR'"])

    def test_the_toc_must_load_a_translation_after_english(self):
        root = self.make({"Locales/deDE.lua": translation("deDE", [])}, toc_locales=("deDE",))
        (root / "Addon.toc").write_text("## Interface: 11508\nLocales\\deDE.lua\nLocales\\enUS.lua\n")
        problems, _ = locales.check(root)
        self.assertEqual(problems, ["Locales/deDE.lua: Addon.toc loads it before Locales/enUS.lua; move it after"])

    def test_the_layout_and_its_order_are_fixed(self):
        good = translation("deDE", ['L.CARD_TITLE = "Nächster Halt";', 'L["%d left"] = "%d übrig"'])
        self.assertEqual(locales.check(self.make({"Locales/deDE.lua": good}))[0], [])
        early = 'local _, ns = ...\nlocal L = ns.L\nL["%d left"] = "%d"\nif GetLocale() ~= "deDE" then\n\treturn\nend\n'
        problems, _ = locales.check(self.make({"Locales/deDE.lua": early}))
        self.assertTrue(any("must come once, in the order" in problem for problem in problems), problems)
        twice = translation("deDE", ['if GetLocale() ~= "frFR" then return end'])
        problems, _ = locales.check(self.make({"Locales/deDE.lua": twice}))
        self.assertTrue(any("must come once" in problem for problem in problems), problems)
        bare = 'L["%d left"] = "%d"\n'
        problems, _ = locales.check(self.make({"Locales/deDE.lua": bare}))
        self.assertTrue(any("before `local L = ns.L`" in problem for problem in problems), problems)

    def test_decimal_escapes_are_utf8_bytes(self):
        problems, coverage = self.check(['L["%d left"] = "%d \\195\\188brig"'])
        self.assertEqual(problems, [])
        self.assertEqual(locales.parse(translation("deDE", ['L["k"] = "\\195\\188"']))[1]["k"].text, "ü")

    def test_escape_payloads_and_order_must_survive(self):
        problems, _ = self.check(['L["|cffffd100Gold|r line"] = "|cffff0000Gold|r-Zeile"'])
        self.assertTrue(any("'|cffffd100' in English but 0 here" in problem for problem in problems), problems)
        problems, _ = self.check(['L["|cffffd100Gold|r line"] = "|rGold|cffffd100 Zeile"'])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("a |r closes a colour before a |c opens it", problems[0])

    def test_a_literal_percent_with_a_space_is_text(self):
        self.assertEqual(locales.placeholders("0% shows none, after the 5% cut"), ([], ["%"]))
        problems, _ = self.check(['L["Done 100%"] = "Bei 0 % wird nichts gezeigt"'])
        self.assertEqual(problems, [])

    def test_only_client_languages_are_accepted(self):
        root = self.make({"Locales/enGB.lua": translation("enGB", [])}, toc_locales=("enGB",))
        problems, _ = locales.check(root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("enGB is not a client language", problems[0])

    def test_luajit_parses_each_file(self):
        root = self.make({"Locales/deDE.lua": translation("deDE", ['L["%d left"] = "%d übrig"']) + "if then\n"})
        problems, _ = locales.check(root)
        self.assertTrue(any("deDE.lua" in problem and "near" in problem for problem in problems), problems)

    def test_placeholders_and_escapes_helpers(self):
        self.assertEqual(locales.placeholders("%2$s and %1$.1f, %i%%"), ([(2, "s"), (1, "f"), (None, "d")], []))
        self.assertEqual(locales.placeholders("%123d %y")[1], ["%123d", "%y"])
        counts, order = locales.escapes("|cff00ff00x|r ||c |TInterface\\x:0|t\n")
        self.assertEqual((counts["|cff00ff00"], counts["|TInterface\\x:0|t"], counts["newline"]), (1, 1, 1))
        self.assertEqual(order, ["|cff00ff00", "|r", "|TInterface\\x:0|t"])


if __name__ == "__main__":
    unittest.main()
