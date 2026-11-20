"""Tests for the API documentation check: published names, the minor history and the missing-file pass."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents/skills/wow-forever-addon/tooling"))
from forever_tools import docs_contract  # noqa: E402

API = """\
local API = { version = 1, minor = 2 }

function API.CurrentStop()
	return nil
end

API.Stats = function()
	return {}
end

local function Leaderboard(limit)
	return limit
end
API.Leaderboard = Leaderboard
"""

DOCS = """\
# Addon API

`version = 1`. The history: minor 1 names `CurrentStop`, minor 2 names `Leaderboard` and `Stats`.

- `CurrentStop()` returns the stop.
- `Stats()` returns the rows.
- `Leaderboard(limit)` returns the board.
"""


class PublicationsTest(unittest.TestCase):
    def test_every_publication_form_is_found(self):
        self.assertEqual(docs_contract.published(API), ["CurrentStop", "Leaderboard", "Stats"])

    def test_an_assignment_from_a_table_member_is_published(self):
        source = (
            "local hub = ForeverCore.APIKit.Hub(name, channels)\n"
            "API.Subscribe = hub.Subscribe\n"
            "API.Handler = ns.Handler\n"
        )
        self.assertEqual(docs_contract.published(source), ["Handler", "Subscribe"])

    def test_the_value_fields_assigned_by_name_are_not_published(self):
        self.assertEqual(docs_contract.published("API.version = VERSION\nAPI.minor = MINOR\n"), [])

    def test_table_fields_are_not_published_names(self):
        self.assertEqual(docs_contract.published("local API = { version = 1, minor = 7 }\n"), [])

    def test_commented_out_functions_are_not_published(self):
        self.assertEqual(docs_contract.published("-- function API.Old() end\n"), [])

    def test_minor_is_read_from_the_api_table(self):
        self.assertEqual(docs_contract.minor_of(API), 2)
        self.assertIsNone(docs_contract.minor_of("local API = { version = 1 }\n"))

    def test_a_commented_minor_is_not_the_api_table_s(self):
        self.assertIsNone(docs_contract.minor_of("-- local API = { minor = 9 }\nlocal API = { version = 1 }\n"))


class CheckTest(unittest.TestCase):
    def run_check(self, api_text=None, docs_text=DOCS, argument=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            if api_text is not None:
                (root / "Core").mkdir()
                (root / "Core" / "API.lua").write_text(api_text, encoding="utf-8")
            if docs_text is not None:
                (root / "docs").mkdir()
                (root / "docs" / "api.md").write_text(docs_text, encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = docs_contract.main(root, [argument] if argument else [])
            return code, output.getvalue()

    def test_documented_names_and_minor_pass(self):
        code, output = self.run_check(API)
        self.assertEqual(code, 0)
        self.assertIn("3 published names and minor 2", output)

    def test_a_name_the_docs_does_not_mention_fails(self):
        docs = DOCS.replace("- `Stats()` returns the rows.\n", "")
        code, output = self.run_check(API, docs)
        self.assertEqual(code, 1)
        self.assertIn("docs/api.md does not mention Stats(", output)
        self.assertNotIn("CurrentStop(", output)

    def test_a_minor_the_history_does_not_mention_fails(self):
        docs = DOCS.replace("minor 2 names `Leaderboard`", "minor 1 names `Leaderboard`")
        code, output = self.run_check(API, docs)
        self.assertEqual(code, 1)
        self.assertIn("does not mention minor 2", output)

    def test_a_minor_number_far_from_the_word_does_not_count(self):
        code, output = self.run_check(API, "# API\n\nminor\n" + "x" * 300 + "\n\n2\n")
        self.assertEqual(code, 1)
        self.assertIn("does not mention minor 2", output)

    def test_a_missing_docs_file_fails_and_lists_every_name(self):
        code, output = self.run_check(API, docs_text=None)
        self.assertEqual(code, 1)
        self.assertIn("docs/api.md is missing", output)
        for name in ("CurrentStop", "Leaderboard", "Stats"):
            self.assertIn(f"does not mention {name}(", output)

    def test_no_api_file_passes_with_a_message(self):
        code, output = self.run_check(api_text=None)
        self.assertEqual(code, 0)
        self.assertIn("nothing to check", output)

    def test_the_api_path_can_be_given_as_an_argument(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            api = root / "Other" / "API.lua"
            api.parent.mkdir()
            api.write_text(API, encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "api.md").write_text(DOCS, encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = docs_contract.main(root, [str(api)])
        self.assertEqual(code, 0)
        self.assertIn("3 published names", output.getvalue())


class AnswerTest(unittest.TestCase):
    def test_a_hand_written_invalid_answer_fails(self):
        failures = docs_contract.answer_failures('function API.Stop(step)\n\treturn nil, "invalid"\nend\n')
        self.assertEqual(len(failures), 1)
        self.assertIn("line 2", failures[0])
        self.assertIn("APIKit.Invalid()", failures[0])

    def test_a_reason_outside_the_documented_set_fails(self):
        for source in ('return nil, "unsupported"', 'return APIKit.NotReady("busy")', "return nil, 'unavailable'"):
            self.assertEqual(len(docs_contract.answer_failures(source)), 1, source)

    def test_every_documented_reason_passes(self):
        for reason in ("loading", "disabled", "none", "combat", "unreachable"):
            self.assertEqual(docs_contract.answer_failures(f'return nil, "{reason}"'), [])
            self.assertEqual(docs_contract.answer_failures(f'return APIKit.NotReady("{reason}")'), [])

    def test_the_invalid_helper_and_comments_pass(self):
        self.assertEqual(docs_contract.answer_failures('return APIKit.Invalid() -- not return nil, "invalid"'), [])
        self.assertEqual(docs_contract.answer_failures('-- return nil, "busy"'), [])

    def test_check_reports_the_answers_with_the_file_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Core").mkdir()
            (root / "Core" / "API.lua").write_text('function API.Stop()\n\treturn nil, "invalid"\nend\n')
            (root / "docs").mkdir()
            (root / "docs" / "api.md").write_text("`Stop()`\n")
            output = io.StringIO()
            with redirect_stdout(output):
                code = docs_contract.check(root, root / "Core" / "API.lua")
        self.assertEqual(code, 1)
        self.assertIn("Core/API.lua: line 2", output.getvalue())


if __name__ == "__main__":
    unittest.main()
