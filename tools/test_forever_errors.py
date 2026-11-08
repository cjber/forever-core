"""Tests for tools/forever_errors.py: the Lua reader, the readers, grouping and the filer."""

import contextlib
import io
import json
import os
import tempfile
import unittest
import unittest.mock
from datetime import datetime
from pathlib import Path

import forever_errors as errors

REFERENCE = datetime(2026, 11, 8, 12, 0)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def entry(folder="AdventureGuideForever", signature="sig-a", count=1, last_seen=100, message="bad thing"):
    return errors.Entry(
        source="journal",
        folder=folder,
        repo=errors.FOLDERS[folder],
        signature=signature,
        kind="error",
        message=message,
        stack=f"Interface/AddOns/{folder}/A.lua:10",
        count=count,
        first_seen=last_seen,
        last_seen=last_seen,
        version="v1.0.0",
        build="1.60.1.70124",
        locale="enUS",
    )


def group(folder="AdventureGuideForever", signature="sig-a", count=1, last_seen=100, message="bad thing"):
    return errors.group_entries([entry(folder, signature, count, last_seen, message)])[0]


class FakeRunner:
    """A gh runner: records every call and answers issue, label and comment reads from dictionaries."""

    def __init__(self):
        self.calls = []
        self.issues = {}
        self.comments = {}
        self.labels = {}

    def __call__(self, args, stdin_text=None):
        self.calls.append((list(args), stdin_text))
        if args[:2] == ["issue", "list"]:
            repo = args[args.index("-R") + 1]
            return 0, json.dumps(self.issues.get(repo, [])), ""
        if args[:2] == ["issue", "view"]:
            repo = args[args.index("-R") + 1]
            number = int(args[2])
            bodies = self.comments.get((repo, number), [])
            return 0, json.dumps({"comments": [{"body": body} for body in bodies]}), ""
        if args[:2] == ["label", "list"]:
            repo = args[args.index("-R") + 1]
            return 0, json.dumps([{"name": name} for name in self.labels.get(repo, [])]), ""
        return 0, "", ""

    def mutation(self, command):
        return [call for call in self.calls if call[0][:2] == command]


class LuaReaderTest(unittest.TestCase):
    def test_string_escapes(self):
        source = r"""X = { ["s"] = "a\nb\"c\\d\065\t", }"""
        self.assertEqual(errors.parse_lua(source)["X"]["s"], 'a\nb"c\\dA\t')

    def test_nesting_numeric_keys_and_positional_values(self):
        source = """
T = {
  [1] = "one",
  ["two"] = 2,
  [3] = { 4, 5, },
  nested = true,
  nothing = nil,
  negative = -7,
  fraction = 1.5,
  hex = 0x10,
}
"""
        table = errors.parse_lua(source)["T"]
        self.assertEqual(table[1], "one")
        self.assertEqual(table["two"], 2)
        self.assertEqual(table[3][1], 4)
        self.assertEqual(table[3][2], 5)
        self.assertIs(table["nested"], True)
        self.assertIsNone(table["nothing"])
        self.assertEqual(table["negative"], -7)
        self.assertEqual(table["fraction"], 1.5)
        self.assertEqual(table["hex"], 16)

    def test_comments_and_long_strings(self):
        source = """
-- a whole-line comment
A = "value" -- a trailing comment
B = [[long
string]]
"""
        values = errors.parse_lua(source)
        self.assertEqual(values["A"], "value")
        self.assertEqual(values["B"], "long\nstring")

    def test_negative_table_keys(self):
        self.assertEqual(errors.parse_lua("T = { [-157] = 1, }")["T"][-157], 1)

    def test_bad_input_raises(self):
        with self.assertRaises(errors.LuaSyntaxError):
            errors.parse_lua("X = { [1] = }")


class JournalTest(unittest.TestCase):
    def test_reads_our_journals_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            saved = root / "WTF" / "Account" / "1" / "SavedVariables"
            write(
                saved / "AdventureGuideForever.lua",
                """
AdventureGuideForeverDB = {
["errors"] = {
["sig-a"] = {
["signature"] = "sig-a",
["kind"] = "error",
["message"] = "bad 12 thing",
["stack"] = "Interface/AddOns/AdventureGuideForever/A.lua:10",
["count"] = 2,
["firstSeen"] = 100,
["lastSeen"] = 200,
["version"] = "v0.11.1",
["build"] = "1.60.1.70124",
["locale"] = "enUS",
["addons"] = { "Foo", "Bar", },
},
},
["log"] = { "line one", "line two", },
}
""",
            )
            write(saved / "Other.lua", 'OtherDB = { ["errors"] = { ["sig"] = { ["message"] = "no" } } }')
            write(saved / "NoJournal.lua", 'NoJournalDB = { ["setting"] = true }')
            loaded = errors.load_sources(root / "WTF", root / "Logs", REFERENCE)
            self.assertEqual(loaded.warnings, ())
            self.assertEqual(len(loaded.entries), 1)
            entry = loaded.entries[0]
            self.assertEqual(entry.source, "journal")
            self.assertEqual(entry.folder, "AdventureGuideForever")
            self.assertEqual(entry.repo, "cjber/adventure-guide-forever")
            self.assertEqual(entry.signature, "sig-a")
            self.assertEqual(entry.count, 2)
            self.assertEqual(entry.first_seen, 100.0)
            self.assertEqual(entry.last_seen, 200.0)
            self.assertEqual(entry.addons, ("Foo", "Bar"))
            self.assertEqual([line.raw for line in loaded.log_lines], ["line one", "line two"])


class BugGrabberTest(unittest.TestCase):
    def test_keeps_only_entries_naming_one_of_our_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            saved = root / "WTF" / "Account" / "1" / "SavedVariables"
            write(
                saved / "!BugGrabber.lua",
                """
BugGrabberDB = {
["errors"] = {
{
["message"] = "bad thing",
["stack"] = "Interface/AddOns/AdventureGuideForever/A.lua:10",
["locals"] = "",
["session"] = 1,
["time"] = 300,
["counter"] = 4,
},
{
["message"] = "not ours",
["stack"] = "Interface/AddOns/AtlasLootClassic/X.lua:10",
["locals"] = "",
["session"] = 1,
["time"] = 300,
["counter"] = 1,
},
},
}
""",
            )
            loaded = errors.load_sources(root / "WTF", root / "Logs", REFERENCE)
            ours = [entry for entry in loaded.entries if entry.source == "buggrabber"]
            self.assertEqual(len(ours), 1)
            self.assertEqual(ours[0].folder, "AdventureGuideForever")
            self.assertEqual(ours[0].repo, "cjber/adventure-guide-forever")
            self.assertEqual(ours[0].count, 4)
            self.assertEqual(ours[0].last_seen, 300.0)


class TaintLogTest(unittest.TestCase):
    def test_reads_lines_naming_our_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(
                root / "Logs" / "taint.log",
                "11/8 11:07:44.832  Tainted value written by AdventureGuideForever "
                "- Interface/AddOns/AdventureGuideForever/A.lua:4\n"
                "11/8 11:07:45.000  Tainted value written by another addon "
                "- Interface/AddOns/AtlasLootClassic/X.lua:4\n",
            )
            loaded = errors.load_sources(root / "WTF", root / "Logs", REFERENCE)
            self.assertEqual(len(loaded.log_lines), 2)
            ours = [entry for entry in loaded.entries if entry.source == "taint"]
            self.assertEqual(len(ours), 1)
            self.assertEqual(ours[0].repo, "cjber/adventure-guide-forever")
            self.assertEqual(ours[0].last_seen, datetime(2026, 11, 8, 11, 7, 44, 832000).timestamp())


class GroupingTest(unittest.TestCase):
    def test_one_group_per_repo_and_signature(self):
        base = dict(
            source="journal",
            kind="error",
            message="bad thing",
            stack="frame",
            version="v1.0.0",
            build="build",
            locale="enUS",
        )
        entries = [
            errors.Entry(
                folder="AdventureGuideForever",
                repo="cjber/adventure-guide-forever",
                signature="a",
                count=1,
                first_seen=100,
                last_seen=200,
                **base,
            ),
            errors.Entry(
                folder="AdventureGuideForever",
                repo="cjber/adventure-guide-forever",
                signature="a",
                count=2,
                first_seen=50,
                last_seen=300,
                **base,
            ),
            errors.Entry(
                folder="SkillUpForever",
                repo="cjber/skillup-forever",
                signature="a",
                count=1,
                first_seen=100,
                last_seen=100,
                **base,
            ),
        ]
        groups = errors.group_entries(entries)
        self.assertEqual(len(groups), 2)
        guide = next(item for item in groups if item.repo == "cjber/adventure-guide-forever")
        self.assertEqual(guide.count, 3)
        self.assertEqual(guide.first_seen, 50)
        self.assertEqual(guide.last_seen, 300)
        self.assertEqual(guide.hash, errors.signature_hash("a"))


class GateTest(unittest.TestCase):
    def run_main(self, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = errors.main(list(arguments))
        return status, stdout.getvalue()

    def fixture(self, root):
        saved = root / "WTF" / "Account" / "1" / "SavedVariables"
        write(
            saved / "AdventureGuideForever.lua",
            'AdventureGuideForeverDB = { ["errors"] = { ["a"] = { ["message"] = "old", ["lastSeen"] = 100 } } }',
        )
        write(
            saved / "SkillUpForever.lua",
            'SkillUpForeverDB = { ["errors"] = { ["b"] = { ["message"] = "new", ["lastSeen"] = 300 } } }',
        )
        return root / "WTF", root / "Logs"

    def test_since_keeps_the_newer_entry_and_the_gate_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            wtf, logs = self.fixture(Path(directory))
            status, output = self.run_main("--wtf", str(wtf), "--logs", str(logs), "--since", "200", "--json")
            self.assertEqual(status, 1)
            groups = json.loads(output)
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["repo"], "cjber/skillup-forever")
            self.assertEqual(groups[0]["message"], "new")

    def test_no_remaining_entry_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            wtf, logs = self.fixture(Path(directory))
            status, output = self.run_main("--wtf", str(wtf), "--logs", str(logs), "--since", "400", "--json")
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output), [])

    def test_addon_narrows_the_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            wtf, logs = self.fixture(Path(directory))
            status, _ = self.run_main("--wtf", str(wtf), "--logs", str(logs), "--addon", "FieldGuideForever")
            self.assertEqual(status, 0)
            status, _ = self.run_main("--wtf", str(wtf), "--logs", str(logs), "--addon", "NoSuchAddon")
            self.assertEqual(status, 2)

    def test_addon_accepts_a_repository_name(self):
        with tempfile.TemporaryDirectory() as directory:
            wtf, logs = self.fixture(Path(directory))
            status, output = self.run_main(
                "--wtf", str(wtf), "--logs", str(logs), "--addon", "adventure-guide-forever", "--json"
            )
            self.assertEqual(status, 1)
            self.assertEqual([item["repo"] for item in json.loads(output)], ["cjber/adventure-guide-forever"])

    def test_file_dry_run_from_the_command_line(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as directory:
            wtf, logs = self.fixture(Path(directory))
            real_gh = errors.Gh
            with unittest.mock.patch.object(errors, "Gh", lambda: real_gh(runner)):
                status, output = self.run_main("--wtf", str(wtf), "--logs", str(logs), "--file", "--dry-run")
        self.assertEqual(status, 1)
        self.assertIn("would create cjber/skillup-forever: ", output)
        self.assertEqual(runner.mutation(["issue", "create"]), [])


class StaleTest(unittest.TestCase):
    """A sighting before the installed TOC's mtime cannot describe the code installed now."""

    def run_main(self, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = errors.main(list(arguments))
        return status, stdout.getvalue()

    def journal(self, root, *last_seen, signature="sig-a"):
        entries = "".join(
            f'["{signature}-{index}"] = {{ ["signature"] = "{signature}", '
            f'["message"] = "bad thing", ["lastSeen"] = {when} }},'
            for index, when in enumerate(last_seen)
        )
        saved = root / "WTF" / "Account" / "1" / "SavedVariables"
        write(saved / "AdventureGuideForever.lua", f'AdventureGuideForeverDB = {{ ["errors"] = {{ {entries} }} }}')
        return root / "WTF"

    def install(self, root, mtime, folder="AdventureGuideForever"):
        toc = root / "Interface" / "AddOns" / folder / f"{folder}.toc"
        write(toc, "## Interface: 16001\n")
        os.utime(toc, (mtime, mtime))
        return toc

    def test_a_sighting_before_the_installed_build_is_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wtf = self.journal(root, 100)
            toc = self.install(root, 500)
            self.assertEqual(errors.install_times(wtf)["AdventureGuideForever"], toc.stat().st_mtime)
            status, output = self.run_main("--wtf", str(wtf), "--logs", str(root / "Logs"), "--json")
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output), [])

    def test_include_stale_marks_the_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wtf = self.journal(root, 100)
            self.install(root, 500)
            status, output = self.run_main("--wtf", str(wtf), "--logs", str(root / "Logs"), "--include-stale", "--json")
            self.assertEqual(status, 0)
            groups = json.loads(output)
            self.assertEqual(len(groups), 1)
            self.assertTrue(groups[0]["stale"])
            self.assertEqual(groups[0]["liveCount"], 0)
            self.assertEqual(groups[0]["staleCount"], 1)

    def test_a_sighting_after_the_installed_build_is_live(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wtf = self.journal(root, 600)
            self.install(root, 500)
            status, output = self.run_main("--wtf", str(wtf), "--logs", str(root / "Logs"), "--json")
            self.assertEqual(status, 1)
            groups = json.loads(output)
            self.assertEqual(len(groups), 1)
            self.assertFalse(groups[0]["stale"])
            self.assertEqual(groups[0]["liveCount"], 1)
            self.assertEqual(groups[0]["staleCount"], 0)

    def test_a_mixed_group_reports_live_and_stale_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wtf = self.journal(root, 100, 600)
            self.install(root, 500)
            status, output = self.run_main("--wtf", str(wtf), "--logs", str(root / "Logs"))
            self.assertEqual(status, 1)
            self.assertIn("1 live, 1 stale", output)
            status, output = self.run_main("--wtf", str(wtf), "--logs", str(root / "Logs"), "--json")
            groups = json.loads(output)
            self.assertEqual(len(groups), 1)
            self.assertFalse(groups[0]["stale"])
            self.assertEqual((groups[0]["liveCount"], groups[0]["staleCount"]), (1, 1))

    def test_a_missing_toc_leaves_the_group_live(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wtf = self.journal(root, 100)
            status, output = self.run_main("--wtf", str(wtf), "--logs", str(root / "Logs"), "--json")
            self.assertEqual(status, 1)
            self.assertFalse(json.loads(output)[0]["stale"])

    def test_install_time_follows_a_symlinked_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "test-artifacts" / "adventure-guide-forever-dev"
            toc = target / "AdventureGuideForever.toc"
            write(toc, "## Interface: 16001\n")
            os.utime(toc, (500, 500))
            link = root / "Interface" / "AddOns" / "AdventureGuideForever"
            link.parent.mkdir(parents=True)
            link.symlink_to(target, target_is_directory=True)
            self.assertEqual(errors.install_times(root / "WTF")["AdventureGuideForever"], 500)

    def test_file_skips_a_stale_group(self):
        item = errors.group_entries([entry(last_seen=100)], {"AdventureGuideForever": 500})[0]
        self.assertTrue(item.stale)
        runner = FakeRunner()
        output = []
        decisions = errors.file_groups([item], errors.Gh(runner), out=output.append)
        self.assertEqual([decision.action for decision in decisions], ["skip"])
        self.assertIn("skipped (stale: seen before the installed build)", output[0])
        self.assertEqual(runner.calls, [])

    def test_include_stale_files_the_group(self):
        item = errors.group_entries([entry(last_seen=100)], {"AdventureGuideForever": 500})[0]
        runner = FakeRunner()
        output = []
        decisions = errors.file_groups([item], errors.Gh(runner), dry_run=True, include_stale=True, out=output.append)
        self.assertEqual([decision.action for decision in decisions], ["create"])
        self.assertTrue(output[0].startswith("would create cjber/adventure-guide-forever: "))


class FilingTest(unittest.TestCase):
    def test_no_issue_creates_one_and_the_label(self):
        runner = FakeRunner()
        output = []
        decisions = errors.file_groups([group(count=2)], errors.Gh(runner), out=output.append)
        self.assertEqual([decision.action for decision in decisions], ["create"])
        self.assertEqual(output, ["created cjber/adventure-guide-forever#?: Lua error: bad thing"])
        creates = runner.mutation(["issue", "create"])
        self.assertEqual(len(creates), 1)
        args, body = creates[0]
        self.assertIn("--label", args)
        self.assertEqual(args[args.index("--label") + 1], "error-report")
        self.assertIn(errors.signature_hash("sig-a"), body)
        self.assertIn("count=2", body)
        self.assertEqual(len(runner.mutation(["label", "create"])), 1)

    def test_same_hash_and_same_count_is_skipped(self):
        runner = FakeRunner()
        signature = errors.signature_hash("sig-a")
        runner.issues["cjber/adventure-guide-forever"] = [
            {"number": 7, "body": f"<!-- forever-errors: signature={signature} count=3 -->"}
        ]
        output = []
        decisions = errors.file_groups([group(count=3)], errors.Gh(runner), out=output.append)
        self.assertEqual([decision.action for decision in decisions], ["skip"])
        self.assertEqual(runner.mutation(["issue", "create"]), [])
        self.assertEqual(runner.mutation(["issue", "comment"]), [])

    def test_a_risen_count_comments_once(self):
        runner = FakeRunner()
        signature = errors.signature_hash("sig-a")
        runner.issues["cjber/adventure-guide-forever"] = [
            {"number": 7, "body": f"<!-- forever-errors: signature={signature} count=3 -->"}
        ]
        runner.comments[("cjber/adventure-guide-forever", 7)] = ["<!-- forever-errors: count=3 -->"]
        output = []
        decisions = errors.file_groups([group(count=5)], errors.Gh(runner), out=output.append)
        self.assertEqual([decision.action for decision in decisions], ["comment"])
        comments = runner.mutation(["issue", "comment"])
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0][0][2], "7")
        self.assertIn("count=5", comments[0][1])
        self.assertEqual(runner.mutation(["issue", "create"]), [])

    def test_the_last_comment_sets_the_baseline(self):
        runner = FakeRunner()
        signature = errors.signature_hash("sig-a")
        runner.issues["cjber/adventure-guide-forever"] = [
            {"number": 7, "body": f"<!-- forever-errors: signature={signature} count=3 -->"}
        ]
        runner.comments[("cjber/adventure-guide-forever", 7)] = ["<!-- forever-errors: count=5 -->"]
        decisions = errors.file_groups([group(count=4)], errors.Gh(runner), out=lambda line: None)
        self.assertEqual([decision.action for decision in decisions], ["skip"])

    def test_an_issue_without_the_hash_does_not_count(self):
        runner = FakeRunner()
        runner.issues["cjber/adventure-guide-forever"] = [
            {"number": 7, "body": "<!-- forever-errors: signature=000000000000 count=9 -->"}
        ]
        decisions = errors.file_groups([group(count=1)], errors.Gh(runner), out=lambda line: None)
        self.assertEqual([decision.action for decision in decisions], ["create"])

    def test_dry_run_writes_nothing(self):
        runner = FakeRunner()
        output = []
        decisions = errors.file_groups([group(count=2)], errors.Gh(runner), dry_run=True, out=output.append)
        self.assertEqual([decision.action for decision in decisions], ["create"])
        self.assertEqual(output, ["would create cjber/adventure-guide-forever: Lua error: bad thing"])
        self.assertEqual(runner.mutation(["issue", "create"]), [])
        self.assertEqual(runner.mutation(["label", "create"]), [])
        self.assertEqual(runner.mutation(["issue", "comment"]), [])

    def test_every_read_gets_stdin_from_devnull(self):
        runner = FakeRunner()
        errors.file_groups([group()], errors.Gh(runner), out=lambda line: None)
        reads = [call for call in runner.calls if call[0][:2] in (["issue", "list"], ["label", "list"])]
        self.assertTrue(reads)
        for args, stdin_text in reads:
            self.assertIsNone(stdin_text)
            self.assertNotIn("--body", args)

    def test_the_issue_list_is_read_once_per_repo(self):
        runner = FakeRunner()
        first = group(signature="sig-a")
        second = group(signature="sig-b")
        errors.file_groups([first, second], errors.Gh(runner), out=lambda line: None)
        self.assertEqual(len(runner.mutation(["issue", "list"])), 1)

    def test_title_is_cut_to_eighty_characters(self):
        item = group(message="x" * 120)
        self.assertEqual(errors.issue_title(item), "Lua error: " + "x" * 80)

    def test_log_context_ends_at_the_last_sighting(self):
        lines = [
            errors.LogLine(datetime(2026, 11, 8, 10, 0, second), f"line {second}", f"line {second}")
            for second in range(30)
        ]
        context = errors.log_context(lines, datetime(2026, 11, 8, 10, 0, 20).timestamp(), "AdventureGuideForever")
        self.assertEqual(len(context), 20)
        self.assertEqual(context[-1], "line 20")


if __name__ == "__main__":
    unittest.main()
