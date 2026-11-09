import tempfile
import unittest
from pathlib import Path

from forever_tools import multivalue
from forever_tools.lua import LuaSyntaxError, tokenize


class ScanRootsTest(unittest.TestCase):
    def test_absolute_cache_parent_does_not_exclude_the_requested_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / ".cache" / "checkout"
            root.mkdir(parents=True)
            source = root / "Core.lua"
            source.write_text("return select(2, ...)\n")
            nested = root / ".cache" / "ignored.lua"
            nested.parent.mkdir()
            nested.write_text("return select(2, ...)\n")
            self.assertEqual(multivalue.lua_files([root]), [source])
            self.assertEqual(multivalue.lua_files([source]), [source])


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


if __name__ == "__main__":
    unittest.main()
