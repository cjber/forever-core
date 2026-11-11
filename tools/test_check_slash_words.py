"""Tests for tools/check_slash_words.py."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import check_slash_words as gate

MAIN_ASSIST = {"/ma": ("SLASH_MAINASSISTON1", "SLASH_MAINASSISTON3")}


class CheckTest(unittest.TestCase):
    def check(self, source, owned=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Addon.lua"
            path.write_text(source)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                failed = gate.check([path], MAIN_ASSIST if owned is None else owned, Path(tmp))
        return failed, output.getvalue()

    def test_an_addon_word_the_client_owns_fails_with_the_client_key(self):
        failed, output = self.check('SLASH_MACROASSIST1 = "/ma"\n')
        self.assertTrue(failed)
        self.assertIn("Addon.lua:1:", output)
        self.assertIn("/ma", output)
        self.assertIn("SLASH_MAINASSISTON1", output)

    def test_a_free_word_passes(self):
        failed, output = self.check('SLASH_MACROASSIST1 = "/macroassist"\n')
        self.assertFalse(failed)
        self.assertEqual(output, "")

    def test_a_conditional_assignment_still_counts(self):
        failed, _ = self.check('if enabled then\n\tSLASH_MACROASSIST1 = "/ma"\nend\n')
        self.assertTrue(failed)

    def test_a_word_differing_only_in_case_still_collides(self):
        failed, _ = self.check('SLASH_MACROASSIST1 = "/MA"\n')
        self.assertTrue(failed)

    def test_a_commented_assignment_does_not_count(self):
        failed, _ = self.check('-- SLASH_MACROASSIST1 = "/ma"\n')
        self.assertFalse(failed)

    def test_a_concatenated_word_is_not_read_as_the_client_word(self):
        failed, _ = self.check('SLASH_MACROASSIST1 = "/ma" .. suffix\n')
        self.assertFalse(failed)

    def test_the_pin_lists_the_client_main_assist_command(self):
        words = gate.client_words()
        self.assertIn("/ma", words)
        self.assertIn("SLASH_MAINASSISTON1", words["/ma"])


if __name__ == "__main__":
    unittest.main()
