import unittest

from forever_tools import multivalue, taint
from forever_tools.lua import LuaSyntaxError, tokenize


def messages(found):
    return [message for _, message in found]


class LexerTest(unittest.TestCase):
    def test_token_kinds_and_comments(self):
        tokens, comments = tokenize('local x = "a" -- note\nreturn 1..2')
        self.assertEqual([t.kind for t in tokens][:4], ["keyword", "name", "symbol", "string"])
        self.assertEqual(comments[1].strip(), "note")
        self.assertIn("..", [t.text for t in tokens])

    def test_crlf_inside_a_string_is_rejected_or_kept_consistent(self):
        tokens, _ = tokenize('local s = "a"\r\nlocal t = "b"\r\n')
        self.assertEqual(sum(t.kind == "string" for t in tokens), 2)

    def test_unexpected_character_raises(self):
        with self.assertRaises(LuaSyntaxError):
            tokenize("local x = $")


class MultivalueTest(unittest.TestCase):
    def test_select_expansion_is_flagged_and_allowed_by_comment(self):
        self.assertTrue(multivalue.check("local x = select(2, ...)\nprint(x, select(2, ...))\n"))
        self.assertEqual(multivalue.check("print((select(2, ...)))\n"), [])
        allowed = "local a, b = select(2, ...) -- multi-value: both are wanted\n"
        self.assertEqual(multivalue.check(allowed), [])

    def test_project_multi_return_is_flagged_only_under_that_rule(self):
        rules = multivalue.Rules(multi_return=frozenset({"GetThing"}))
        self.assertTrue(multivalue.check("print(GetThing())\n", rules))
        self.assertEqual(multivalue.check("print(GetThing())\n"), [])
        self.assertEqual(multivalue.check("print((GetThing()))\n", rules), [])


class TaintTest(unittest.TestCase):
    def test_unsafe_map_openers_are_flagged_and_the_safe_contract_is_not(self):
        for call in ("OpenWorldMap()", "OpenQuestLog()", "ToggleWorldMap()", "QuestMapFrame_ShowQuestDetails(1)"):
            with self.subTest(call=call):
                self.assertTrue(taint.check(f"{call}\n"), call)
                self.assertTrue(taint.check(f"_G.{call}\n"), call)
        self.assertEqual(taint.check("C_Map.OpenWorldMap(1)\n"), [])
        self.assertEqual(taint.check('hooksecurefunc("QuestMapFrame_ShowQuestDetails", f)\n'), [])

    def test_escape_comment_clears_a_call(self):
        self.assertEqual(taint.check("OpenWorldMap() -- taint-ok: protected path\n"), [])

    def test_set_map_id_depends_on_the_receiver(self):
        flagged = (
            "WorldMapFrame:SetMapID(1)\n",
            "local map = WorldMapFrame:GetMap()\nmap:SetMapID(1)\n",
            "WorldMapFrame:GetMap():SetMapID(1)\n",
        )
        for source in flagged:
            with self.subTest(source=source):
                self.assertTrue(taint.check(source))
        for source in ("scrollBox:SetMapID(1)\n", "probe:SetMapID(1)\n"):
            with self.subTest(source=source):
                self.assertEqual(taint.check(source), [])


if __name__ == "__main__":
    unittest.main()
