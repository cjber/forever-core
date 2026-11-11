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


def comment(comment_id, text, username="user", display="User", parent=None, replies=None, posted=None):
    row = {
        "id": comment_id,
        "text": text,
        "datePosted": posted if posted is not None else 1_000 + comment_id,
        "author": {"username": username, "displayName": display},
    }
    if parent is not None:
        row["parentId"] = parent
    if replies is not None:
        row["replies"] = replies
    return row


def owner_reply(comment_id, parent, posted=None):
    # The live API names the owner "barryguns" and displays "cjber".
    return comment(comment_id, "owner answer", username="barryguns", display="cjber", parent=parent, posted=posted)


def fake_fetch(rows):
    def fetch(url):
        page = int(re.search(r"page=(\d+)", url).group(1))
        return {"data": rows if page == 0 else [], "pagination": {"totalCount": len(rows)}}

    return fetch


def run(argv, fetch, state=None, links=None):
    output = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        with (
            unittest.mock.patch.object(cfwatch, "projects", lambda root=None, remote=None: {"test-mod": 1}),
            unittest.mock.patch.object(cfwatch, "linked_issues", lambda search=None: links or {}),
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


class ProjectsTest(unittest.TestCase):
    def tree(self, root, ids, missing=()):
        """A fake suite checkout per watched slug: one root TOC, with the project line when `ids` names one."""
        for slug in cfwatch.slug_list():
            if slug in missing:
                continue
            folder = Path(root) / slug
            folder.mkdir(parents=True)
            line = f"## X-Curse-Project-ID: {ids[slug]}\n" if slug in ids else ""
            (folder / "Example.toc").write_text("## Interface: 16001\n" + line)

    def test_every_addon_and_forevercore_is_watched_from_its_own_root_toc(self):
        ids = {slug: 1000 + index for index, slug in enumerate(cfwatch.slug_list())}
        with tempfile.TemporaryDirectory() as tmp:
            self.tree(tmp, ids)
            found = cfwatch.projects(tmp)
        self.assertEqual(list(found), cfwatch.slug_list())
        self.assertEqual(len(found), 9)
        self.assertEqual(found, ids)
        self.assertIn("forever-core", found)
        self.assertEqual(found["commissions-forever"], ids["commissions-forever"])

    def test_a_root_toc_without_the_project_line_fails_loudly(self):
        ids = {slug: 1000 for slug in cfwatch.slug_list() if slug != "forever-core"}
        with tempfile.TemporaryDirectory() as tmp:
            self.tree(tmp, ids)
            with self.assertRaisesRegex(SystemExit, "forever-core has no ## X-Curse-Project-ID"):
                cfwatch.projects(tmp)

    def test_a_missing_checkout_reads_the_toc_through_github(self):
        ids = {slug: 1000 + index for index, slug in enumerate(cfwatch.slug_list())}
        requested = []

        def remote(slug):
            requested.append(slug)
            return f"## Interface: 16001\n## X-Curse-Project-ID: {ids[slug]}\n"

        with tempfile.TemporaryDirectory() as tmp:
            self.tree(
                tmp,
                {slug: ids[slug] for slug in cfwatch.slug_list() if slug != "tweaks-forever"},
                missing=["tweaks-forever"],
            )
            found = cfwatch.projects(tmp, remote)
        self.assertEqual(requested, ["tweaks-forever"])
        self.assertEqual(found, ids)


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
                "owner answered the reporter's own follow-up",
                replies=[comment(50, "player reply", parent=5, replies=[owner_reply(51, 50)])],
            ),
            comment(
                6,
                "reporter followed up after the owner's answer",
                replies=[owner_reply(60, 6), comment(61, "it is 4 percent per point", parent=6)],
            ),
        ]

    def test_lists_threads_whose_latest_post_is_not_the_owners(self):
        output = run(["--unanswered"], fake_fetch(self.rows()))
        heads = [int(match) for match in re.findall(r"(?m)^=== \[test-mod\] thread #(\d+),", output)]
        self.assertEqual(heads, [1, 4, 6])
        self.assertIn("3 unanswered", output)

    def test_prints_the_whole_thread_so_a_follow_up_reads_in_context(self):
        output = run(["--unanswered"], fake_fetch(self.rows()))
        thread = output[output.index("thread #6,") :]
        self.assertRegex(thread, r"(?m)^\[test-mod\] #6 ")
        self.assertRegex(thread, r"(?m)^\[test-mod\] #60 .*cjber \(reply to #6\)")
        self.assertRegex(thread, r"(?m)^\[test-mod\] #61 .*\n  it is 4 percent per point$")

    def test_a_reply_listed_at_the_top_level_joins_its_thread(self):
        groups = {top["id"]: [row["id"] for row in rows] for top, rows in cfwatch.threads(self.rows())}
        self.assertEqual(groups[3], [3, 30])
        self.assertNotIn(30, groups)
        self.assertEqual(groups[5], [5, 50, 51])


class LinkedTest(unittest.TestCase):
    def link(self, number=7, state="open", repo="skillup-forever", slug="skillup-forever"):
        return {"repo": repo, "slug": slug, "number": number, "state": state, "closed_at": ""}

    def test_only_the_exact_line_links_a_thread(self):
        def search():
            return [
                {
                    "repository": {"name": "skillup-forever"},
                    "number": 7,
                    "state": "open",
                    "body": "A player reported this.\nCurseForge thread 8684993 (skillup-forever)\n",
                },
                {
                    "repository": {"name": "forever-core"},
                    "number": 388,
                    "state": "open",
                    "body": "The line `CurseForge thread <id> (<addon>)` goes on every issue.\n",
                },
            ]

        linked = cfwatch.linked_issues(search)
        self.assertEqual(list(linked), ["8684993"])
        self.assertEqual(linked["8684993"][0]["number"], 7)
        self.assertEqual(linked["8684993"][0]["repo"], "skillup-forever")

    def test_an_unanswered_thread_with_an_issue_reads_as_waiting_not_unanswered(self):
        rows = [
            comment(1, "needs a fix"),
            owner_reply(10, 1),
            comment(11, "still broken", parent=1),
            comment(2, "no issue"),
        ]
        output = run(["--unanswered"], fake_fetch(rows), links={"1": [self.link()]})
        self.assertIn("waiting on cjber/skillup-forever#7 (open)", output)
        self.assertIn("thread #1, 3 posts", output)
        self.assertNotIn("[test-mod] #1 ", output)
        self.assertIn("thread #2,", output)
        self.assertIn("1 unanswered, 1 waiting on an issue, 0 settled", output)

    def test_due_lists_a_released_link_and_keeps_unreleased_ones_waiting(self):
        links = {
            "11": [self.link(number=7)],
            "12": [self.link(number=8, state="closed")],
        }

        def released(repo, number):
            return cfwatch.Release("v1.5.1", "2026-11-11T00:00:00Z") if number == 7 else None

        with unittest.mock.patch.object(cfwatch, "released_in", released):
            output = run(["--due"], fake_fetch([]), links=links)
        self.assertIn("[skillup-forever] thread #11: cjber/skillup-forever#7 released in v1.5.1", output)
        self.assertNotIn("thread #12", output)
        self.assertIn("1 due, 0 answered, 1 still waiting", output)

    def test_a_thread_is_due_only_once_every_linked_issue_has_released(self):
        links = {"11": [self.link(number=7), self.link(number=8)]}

        def released(repo, number):
            return cfwatch.Release("v1.5.1", "2026-11-11T00:00:00Z") if number == 7 else None

        with unittest.mock.patch.object(cfwatch, "released_in", released):
            output = run(["--due"], fake_fetch([]), links=links)
        self.assertNotIn("thread #11:", output)
        self.assertIn("0 due, 0 answered, 1 still waiting", output)

    def test_an_owner_reply_after_the_release_has_answered_the_thread(self):
        links = {"11": [self.link(number=7)]}
        rows = [comment(11, "needs a fix"), owner_reply(10, 11, posted=1_800_000_000_000)]

        def released(repo, number):
            return cfwatch.Release("v1.5.1", "2026-11-11T00:00:00Z")

        with unittest.mock.patch.object(cfwatch, "released_in", released):
            output = run(["--due"], fake_fetch(rows), links=links)
        self.assertNotIn("thread #11:", output)
        self.assertIn("0 due, 1 answered, 0 still waiting", output)

    def test_an_owner_reply_before_the_release_leaves_the_thread_due(self):
        links = {"11": [self.link(number=7)]}
        rows = [comment(11, "needs a fix"), owner_reply(10, 11)]

        def released(repo, number):
            return cfwatch.Release("v1.5.1", "2026-11-11T00:00:00Z")

        with unittest.mock.patch.object(cfwatch, "released_in", released):
            output = run(["--due"], fake_fetch(rows), links=links)
        self.assertIn("[skillup-forever] thread #11: cjber/skillup-forever#7 released in v1.5.1", output)
        self.assertIn("1 due, 0 answered, 0 still waiting", output)


class ReleasedInTest(unittest.TestCase):
    """The tag that first contains the fix, from the issue's own state and timeline."""

    def release(self, issue, events=None, tags=("v1.5.0", "v1.5.1"), contained=("v1.5.1",), sha="abc"):
        def api(*args):
            url = args[1]
            if url.endswith("/issues/9"):
                return issue
            if "/timeline" in url:
                return events or []
            if "/pulls/" in url:
                return {"merge_commit_sha": sha}
            if "/releases" in url:
                return [
                    {"tag_name": tag, "published_at": f"2026-11-{index + 1:02d}", "draft": False}
                    for index, tag in enumerate(tags)
                ]
            if "/compare/" in url:
                return {"status": "ahead" if url.rsplit("...", 1)[1] in contained else "behind"}
            raise AssertionError(url)

        return unittest.mock.patch.object(cfwatch, "gh_json", api)

    def merged(self, at="2026-11-11T02:16:29Z"):
        return [{"event": "cross-referenced", "source": {"issue": {"number": 583, "pull_request": {"merged_at": at}}}}]

    def test_an_open_issue_is_not_due(self):
        with self.release({"state": "open"}):
            self.assertIsNone(cfwatch.released_in("skillup-forever", 9))

    def test_a_closed_not_planned_issue_is_never_due(self):
        with self.release({"state": "closed", "state_reason": "not_planned", "closed_at": "2026-11-11T02:16:31Z"}):
            self.assertIsNone(cfwatch.released_in("skillup-forever", 9))

    def test_a_closed_issue_names_the_release_that_first_contains_its_pr(self):
        issue = {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-11T02:16:31Z"}
        with self.release(issue, self.merged()):
            self.assertEqual(cfwatch.released_in("skillup-forever", 9), cfwatch.Release("v1.5.1", "2026-11-02"))

    def test_a_fix_on_main_but_not_in_a_release_is_not_due(self):
        issue = {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-11T02:16:31Z"}
        with self.release(issue, self.merged(), contained=()):
            self.assertIsNone(cfwatch.released_in("skillup-forever", 9))

    def test_a_pr_merged_after_the_issue_closed_does_not_close_it(self):
        issue = {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-11T02:16:31Z"}
        late = self.merged("2026-11-11T02:32:02Z")
        with self.release(issue, late, sha="late"):
            self.assertIsNone(cfwatch.released_in("skillup-forever", 9))


class SettleTest(unittest.TestCase):
    def rows(self, follow_up=False):
        replies = [owner_reply(10, 1), comment(11, "thanks, works now", parent=1)]
        if follow_up:
            replies.append(comment(12, "it broke again", parent=1))
        return [comment(1, "a question", replies=replies), comment(2, "still waiting")]

    def heads(self, output):
        return [int(match) for match in re.findall(r"(?m)^=== \[test-mod\] thread #(\d+),", output)]

    def test_a_settled_thread_leaves_the_unanswered_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = run(["--settle", "1", "thanks only"], fake_fetch(self.rows()), state=tmp)
            self.assertIn("settled [test-mod] thread #1: thanks only", output)
            saved = json.loads((Path(tmp) / "forever-core" / "cfwatch-settled.json").read_text())
            self.assertEqual(saved["1"]["latest"], 11)
            self.assertEqual(saved["1"]["reason"], "thanks only")
            output = run(["--unanswered"], fake_fetch(self.rows()), state=tmp)
            self.assertEqual(self.heads(output), [2])
            self.assertIn("1 unanswered, 0 waiting on an issue, 1 settled", output)

    def test_a_new_post_brings_a_settled_thread_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            run(["--settle", "#1", "thanks only"], fake_fetch(self.rows()), state=tmp)
            output = run(["--unanswered"], fake_fetch(self.rows(follow_up=True)), state=tmp)
            self.assertEqual(sorted(self.heads(output)), [1, 2])
            self.assertIn("2 unanswered, 0 waiting on an issue, 0 settled", output)

    def test_an_unknown_thread_or_missing_reason_is_refused(self):
        with self.assertRaises(SystemExit):
            run(["--settle", "99", "thanks only"], fake_fetch(self.rows()))
        with self.assertRaises(SystemExit):
            run(["--settle", "1"], fake_fetch(self.rows()))


if __name__ == "__main__":
    unittest.main()
