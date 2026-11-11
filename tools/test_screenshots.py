"""Check tools/screenshots.py's credit rows against the addon's own data, without Pillow or wowmock."""

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents/skills/wow-forever-addon/tooling"))
from forever_tools import credits  # noqa: E402
from forever_tools.luadata import parse_tables  # noqa: E402

SCENES = Path(__file__).with_name("screenshots.py")
TITLE = re.search(r'CreditsPage\.Register\("([^"]+)"', (ROOT / "Expose.lua").read_text(encoding="utf-8"))[1]
LOCALE = (ROOT / "Locales" / "enUS.lua").read_text(encoding="utf-8")


def phrase(key):
    """One phrase from core's enUS, read the way the Lua file writes it."""
    return re.search(rf'^L\["{re.escape(key)}"\] = "([^"\\\\]*)"$', LOCALE, re.MULTILINE)[1]


def port(name, scope=None):
    """Compile one screenshots.py function with the names it reads from the module."""
    tree = ast.parse(SCENES.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    scope = dict(scope or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SCENES), "exec"), scope)
    return scope[name]


class CreditRowTests(unittest.TestCase):
    def setUp(self):
        self.name_order = port("name_order")
        self.player_order = port("player_order")
        self.merge = port("merge", {"name_order": self.name_order, "player_order": self.player_order})
        self.detail = port("detail", {"phrase": phrase})
        self.view = port("view")
        self.tooltip_lines = port("tooltip_lines")
        self.sections = port(
            "page_sections",
            {
                "merge": self.merge,
                "view": self.view,
                "phrase": phrase,
                "player_order": self.player_order,
            },
        )
        self.data = credits.parse((ROOT / "THIRD_PARTY.md").read_text(encoding="utf-8"))

    def test_the_mock_reads_the_credits_the_addon_ships(self):
        table = parse_tables((ROOT / "Data" / "Credits.lua").read_text(encoding="utf-8"))[0]["ns.Credits"]
        shipped = {key: [dict(row.keyed) for row in table.keyed[key].array] for key in ("players", "inspired")}
        self.assertEqual(shipped, self.data)

    def test_the_page_is_players_ranked_then_inspired_alphabetical(self):
        sections = self.sections([(TITLE, self.data)])
        self.assertEqual(["Players", "Inspired by"], [header for header, _ in sections])
        for header, rows in sections:
            order = self.player_order if header == "Players" else self.name_order
            self.assertEqual(sorted(rows, key=order), rows)
            for row in rows:
                self.assertEqual([TITLE], [item["addon"] for item in row["helped"]])

    def test_a_row_reads_the_addons_that_credit_it(self):
        for _header, rows in self.sections([(TITLE, self.data)]):
            for row in rows:
                self.assertEqual(TITLE, self.detail(row))

    def test_a_filtered_row_reads_that_addon_s_what(self):
        for _header, rows in self.sections([(TITLE, self.data)], TITLE):
            for row in rows:
                self.assertEqual(row["helped"][0]["what"], self.detail(row, TITLE))

    def test_the_filtered_inspired_group_keeps_only_that_addon(self):
        data = {
            "players": [],
            "inspired": [
                {"name": "Questie", "what": "The tracker layout"},
                {"name": "Atlas", "what": "The map notes"},
            ],
        }
        other = {
            "players": [],
            "inspired": [{"name": "Questie", "what": "The quest list"}],
        }
        sections = self.sections([("One", data), ("Two", other)], "One")
        self.assertEqual(["Inspired by"], [header for header, _ in sections])
        rows = sections[0][1]
        self.assertEqual(["Atlas", "Questie"], [row["name"] for row in rows])
        self.assertEqual("The tracker layout", rows[1]["helped"][0]["what"])

    def test_a_name_credited_four_times_keeps_all_four_contributions(self):
        rows = self.merge(
            [
                ("First", {"name": "Ada", "what": ""}),
                ("Second", {"name": "Ada", "what": "Reported a bug"}),
                ("First", {"name": "Ada", "what": "A tracker section"}),
                ("Second", {"name": "Ada", "what": "Something else"}),
            ],
            rank=True,
        )
        self.assertEqual(
            [
                {
                    "name": "Ada",
                    "helped": [
                        {"addon": "First", "what": ""},
                        {"addon": "Second", "what": "Reported a bug"},
                        {"addon": "First", "what": "A tracker section"},
                        {"addon": "Second", "what": "Something else"},
                    ],
                    "count": 4,
                }
            ],
            rows,
        )

    def test_players_rank_by_contribution_count_then_name(self):
        rows = self.merge(
            [
                ("First", {"name": "bob", "what": "One"}),
                ("First", {"name": "Ada", "what": "One"}),
                ("First", {"name": "Ada", "what": "Two"}),
                ("First", {"name": "Cid", "what": "One"}),
            ],
            rank=True,
        )
        self.assertEqual(["Ada", "bob", "Cid"], [row["name"] for row in rows])
        self.assertEqual([2, 1, 1], [row["count"] for row in rows])

    def test_a_row_without_a_what_or_an_addon_still_reads(self):
        self.assertEqual(TITLE, self.detail({"name": "Ada", "helped": [{"addon": TITLE, "what": ""}]}))
        self.assertEqual("", self.detail({"name": "Ada", "helped": []}))

    def test_addons_with_the_same_what_share_one_tooltip_line(self):
        row = {
            "name": "Ada",
            "count": 6,
            "helped": [
                {"addon": "First", "what": "Same words"},
                {"addon": "Second", "what": "Other words"},
                {"addon": "Third", "what": "Same words"},
                {"addon": "First", "what": "Same words"},
                {"addon": "Fourth", "what": ""},
                {"addon": "Fifth", "what": ""},
            ],
        }
        self.assertEqual(
            [
                {"what": "Same words", "addons": ["First", "Third"]},
                {"what": "Other words", "addons": ["Second"]},
                {"what": "", "addons": ["Fourth", "Fifth"]},
            ],
            self.tooltip_lines(row),
        )


if __name__ == "__main__":
    unittest.main()
