"""Tests for docs/handoff/cfwatch.py: its state path, output IDs and unanswered comments."""

import contextlib
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("cfwatch", ROOT / "docs" / "handoff" / "cfwatch.py")
cfwatch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cfwatch)


def comment(comment_id, text, username="user", display="User", parent=None, replies=None):
    row = {
        "id": comment_id,
        "text": text,
        "datePosted": 1_000 + comment_id,
        "author": {"username": username, "displayName": display},
    }
    if parent is not None:
        row["parentId"] = parent
    if replies is not None:
        row["replies"] = replies
    return row


def owner_reply(comment_id, parent):
    # The live API names the owner "barryguns" and displays "cjber".
    return comment(comment_id, "owner answer", username="barryguns", display="cjber", parent=parent)


def fake_fetch(rows):
    def fetch(url):
        page = int(re.search(r"page=(\d+)", url).group(1))
        return {"data": rows if page == 0 else [], "pagination": {"totalCount": len(rows)}}

    return fetch


def run(argv, fetch, state=None):
    output = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        with (
            unittest.mock.patch.object(cfwatch, "MODS", {"test-mod": 1}),
            unittest.mock.patch.dict(os.environ, {"XDG_STATE_HOME": state or tmp}),
            contextlib.redirect_stdout(output),
        ):
            cfwatch.main(argv, fetch)
    return output.getvalue()


class StatePathTest(unittest.TestCase):
    def test_state_lives_under_xdg_state_home(self):
        with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch.dict(os.environ, {"XDG_STATE_HOME": tmp}):
            self.assertEqual(Path(cfwatch.state_path()), Path(tmp) / "forever-core" / "cfwatch-seen.json")

    def test_state_falls_back_to_local_state(self):
        with unittest.mock.patch.dict(os.environ, {"XDG_STATE_HOME": ""}):
            self.assertEqual(
                Path(cfwatch.state_path()),
                Path.home() / ".local" / "state" / "forever-core" / "cfwatch-seen.json",
            )


class ModsTest(unittest.TestCase):
    def test_field_guide_is_watched(self):
        self.assertEqual(cfwatch.MODS["field-guide-forever"], 1786835)


class OutputTest(unittest.TestCase):
    def test_every_comment_prints_its_own_id(self):
        rows = [
            comment(1, "top level", replies=[comment(2, "a reply", parent=1)]),
            comment(3, "another top level"),
        ]
        output = run([], fake_fetch(rows))
        self.assertRegex(output, r"(?m)^\[test-mod\] #1 .*\n  top level$")
        self.assertRegex(output, r"(?m)^\[test-mod\] #2 .* \(reply to #1\):\n  a reply$")
        self.assertRegex(output, r"(?m)^\[test-mod\] #3 ")

    def test_mark_writes_seen_state_outside_the_checkout(self):
        rows = [comment(1, "top level")]
        with tempfile.TemporaryDirectory() as tmp:
            run(["--mark"], fake_fetch(rows), state=tmp)
            path = Path(tmp) / "forever-core" / "cfwatch-seen.json"
            seen = json.loads(path.read_text())
            self.assertEqual(seen["1"]["slug"], "test-mod")
            self.assertEqual(seen["1"]["who"], "User")
            second = run([], fake_fetch(rows), state=tmp)
            self.assertNotRegex(second, r"(?m)^\[test-mod\] #1 ")
            self.assertIn("0 unseen", second)


class UnansweredTest(unittest.TestCase):
    def rows(self):
        return [
            comment(1, "needs an answer"),
            comment(2, "answered directly", replies=[owner_reply(20, 2)]),
            comment(3, "owner reply arrived separately"),
            owner_reply(30, 3),
            comment(4, "only another player answered", replies=[comment(40, "player reply", parent=4)]),
            comment(
                5,
                "owner answered a reply, not the top level",
                replies=[comment(50, "player reply", parent=5, replies=[owner_reply(51, 50)])],
            ),
        ]

    def test_lists_top_level_comments_without_an_owner_reply(self):
        output = run(["--unanswered"], fake_fetch(self.rows()))
        ids = [int(match) for match in re.findall(r"(?m)^\[test-mod\] #(\d+) ", output)]
        self.assertEqual(ids, [1, 4, 5])
        self.assertIn("3 unanswered", output)

    def test_matches_owner_replies_by_parent_id_across_the_flattened_list(self):
        flat = cfwatch.flatten(self.rows())
        self.assertIn(30, [row["id"] for row in flat])
        self.assertEqual([row["id"] for row in cfwatch.unanswered(flat)], [1, 4, 5])


if __name__ == "__main__":
    unittest.main()
