"""Tests for docs/handoff/cfwatch.py: its state path, output IDs and unanswered comments."""

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
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


def run(argv, fetch, state=None, links=None, root=None):
    output = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        with (
            unittest.mock.patch.object(cfwatch, "projects", lambda root=None, remote=None: {"test-mod": 1}),
            unittest.mock.patch.object(cfwatch, "linked_issues", lambda search=None: links or {}),
            unittest.mock.patch.object(cfwatch, "suite_root", lambda: Path(root or tmp)),
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

        def released(repo, number, **kwargs):
            return cfwatch.Release("v1.5.1", "2026-11-11T00:00:00Z") if number == 7 else None

        with unittest.mock.patch.object(cfwatch, "released_in", released):
            output = run(["--due"], fake_fetch([]), links=links)
        self.assertIn("[skillup-forever] thread #11: cjber/skillup-forever#7 released in v1.5.1", output)
        self.assertNotIn("thread #12", output)
        self.assertIn("1 due, 0 answered, 1 still waiting", output)

    def test_a_thread_is_due_only_once_every_linked_issue_has_released(self):
        links = {"11": [self.link(number=7), self.link(number=8)]}

        def released(repo, number, **kwargs):
            return cfwatch.Release("v1.5.1", "2026-11-11T00:00:00Z") if number == 7 else None

        with unittest.mock.patch.object(cfwatch, "released_in", released):
            output = run(["--due"], fake_fetch([]), links=links)
        self.assertNotIn("thread #11:", output)
        self.assertIn("0 due, 0 answered, 1 still waiting", output)

    def test_an_owner_reply_after_the_release_has_answered_the_thread(self):
        links = {"11": [self.link(number=7)]}
        rows = [comment(11, "needs a fix"), owner_reply(10, 11, posted=1_800_000_000_000)]

        def released(repo, number, **kwargs):
            return cfwatch.Release("v1.5.1", "2026-11-11T00:00:00Z")

        with unittest.mock.patch.object(cfwatch, "released_in", released):
            output = run(["--due"], fake_fetch(rows), links=links)
        self.assertNotIn("thread #11:", output)
        self.assertIn("0 due, 1 answered, 0 still waiting", output)

    def test_an_owner_reply_before_the_release_leaves_the_thread_due(self):
        links = {"11": [self.link(number=7)]}
        rows = [comment(11, "needs a fix"), owner_reply(10, 11)]

        def released(repo, number, **kwargs):
            return cfwatch.Release("v1.5.1", "2026-11-11T00:00:00Z")

        with unittest.mock.patch.object(cfwatch, "released_in", released):
            output = run(["--due"], fake_fetch(rows), links=links)
        self.assertIn("[skillup-forever] thread #11: cjber/skillup-forever#7 released in v1.5.1", output)
        self.assertIn("1 due, 0 answered, 0 still waiting", output)

    def test_a_player_post_after_the_owners_reply_leaves_the_thread_answered(self):
        links = {"11": [self.link(number=7)]}
        rows = [
            comment(11, "needs a fix"),
            owner_reply(10, 11, posted=1_800_000_000_000),
            comment(12, "Works great! Cheers!", parent=11, posted=1_800_000_100_000),
        ]

        def released(repo, number, **kwargs):
            return cfwatch.Release("v1.5.1", "2026-11-11T00:00:00Z")

        with unittest.mock.patch.object(cfwatch, "released_in", released):
            due = run(["--due"], fake_fetch(rows), links=links)
            waiting = run(["--unanswered"], fake_fetch(rows))
        self.assertNotIn("thread #11:", due)
        self.assertIn("0 due, 1 answered, 0 still waiting", due)
        self.assertIn("=== [test-mod] thread #11, 3 posts", waiting)

    def test_a_nested_owner_reply_after_the_release_has_answered_the_thread(self):
        links = {"11": [self.link(number=7)]}
        rows = [
            comment(
                11,
                "needs a fix",
                replies=[
                    comment(
                        20,
                        "same here",
                        parent=11,
                        replies=[owner_reply(21, 20, posted=1_800_000_000_000)],
                    )
                ],
            )
        ]

        def released(repo, number, **kwargs):
            return cfwatch.Release("v1.5.1", "2026-11-11T00:00:00Z")

        with unittest.mock.patch.object(cfwatch, "released_in", released):
            output = run(["--due"], fake_fetch(rows), links=links)
        self.assertNotIn("thread #11:", output)
        self.assertIn("0 due, 1 answered, 0 still waiting", output)


class DueCallsTest(unittest.TestCase):
    """A due run answers from local tags and makes a bounded, cached number of REST calls."""

    def test_due_makes_no_compare_calls_and_caches_every_answer(self):
        tags = tuple(f"v1.0.{number}" for number in range(30))
        links = {
            str(number): [{"repo": "skillup-forever", "slug": "skillup-forever", "number": number, "state": "closed"}]
            for number in range(1, 6)
        }
        api_calls = []

        def api(*args):
            url = args[1]
            api_calls.append(url)
            if "/timeline" in url:
                return [{"event": "closed", "commit_id": "abc"}]
            if "/issues/" in url:
                return {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-11T02:16:31Z"}
            if "/releases" in url:
                return [
                    {"tag_name": tag, "published_at": f"2026-11-{index + 1:02d}", "draft": False}
                    for index, tag in enumerate(tags)
                ]
            raise AssertionError(url)

        def git(checkout, *args):
            stdout = "v1.0.29\n" if args[0] == "tag" else ""
            return subprocess.CompletedProcess(args, 0, stdout, "")

        with tempfile.TemporaryDirectory() as tmp:
            with (
                unittest.mock.patch.object(cfwatch, "gh_json", api),
                unittest.mock.patch.object(cfwatch, "checkout", lambda root, repo: Path("/checkout")),
                unittest.mock.patch.object(cfwatch, "git", git),
            ):
                first = run(["--due"], fake_fetch([]), state=tmp, links=links, root=tmp)
                self.assertIn("5 due", first)
                self.assertFalse([url for url in api_calls if "/compare/" in url])
                self.assertEqual(sum("/releases" in url for url in api_calls), 1)
                self.assertEqual(len(api_calls), 11)

                api_calls.clear()
                second = run(["--due"], fake_fetch([]), state=tmp, links=links, root=tmp)
                self.assertIn("5 due", second)
                self.assertEqual(len(api_calls), 5)
                self.assertFalse([url for url in api_calls if "/compare/" in url or "/timeline" in url])


class ReleasedInTest(unittest.TestCase):
    """The tag that first contains the fix, from local git tags and one cached release list."""

    def release(
        self,
        issue,
        events=None,
        tags=("v1.5.0", "v1.5.1"),
        contained=("v1.5.1",),
        contained_by_sha=None,
        sha="abc",
        fetch_ok=True,
        api_calls=None,
        git_calls=None,
    ):
        def api(*args):
            url = args[1]
            if api_calls is not None:
                api_calls.append(url)
            if "/timeline" in url:
                return events or []
            if "/issues/" in url:
                return issue
            if "/pulls/" in url:
                return {"merge_commit_sha": sha}
            if "/releases" in url:
                return [
                    {"tag_name": tag, "published_at": f"2026-11-{index + 1:02d}", "draft": False}
                    for index, tag in enumerate(tags)
                ]
            if "/compare/" in url:
                raise AssertionError("compare API used even though the local checkout has the tags")
            raise AssertionError(url)

        def git(checkout, *args):
            if git_calls is not None:
                git_calls.append(args)
            if args[0] == "fetch" and not fetch_ok:
                return subprocess.CompletedProcess(args, 128, "", "could not read from remote repository")
            if args[0] == "tag":
                tags = contained if contained_by_sha is None else contained_by_sha.get(args[2], ())
                stdout = "\n".join(tags) + ("\n" if tags else "")
                return subprocess.CompletedProcess(args, 0, stdout, "")
            return subprocess.CompletedProcess(args, 0, "", "")

        return unittest.mock.patch.multiple(
            cfwatch,
            gh_json=api,
            checkout=lambda root, repo: Path("/checkout"),
            git=git,
        )

    def released(self, *args, **kwargs):
        return cfwatch.released_in(*args, root=Path("/suite"), **kwargs)

    def merged(self, at="2026-11-11T02:16:29Z", number=583, repo="skillup-forever"):
        source = {"number": number, "pull_request": {"merged_at": at}, "repository": {"full_name": f"cjber/{repo}"}}
        return [{"event": "cross-referenced", "source": {"issue": source}}]

    def test_an_open_issue_is_not_due(self):
        with self.release({"state": "open"}):
            self.assertIsNone(self.released("skillup-forever", 9))

    def test_a_closed_not_planned_issue_is_never_due(self):
        with self.release({"state": "closed", "state_reason": "not_planned", "closed_at": "2026-11-11T02:16:31Z"}):
            self.assertIsNone(self.released("skillup-forever", 9))

    def test_a_closed_issue_names_the_release_that_first_contains_its_pr(self):
        issue = {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-11T02:16:31Z"}
        api_calls, git_calls = [], []
        with self.release(issue, self.merged(), api_calls=api_calls, git_calls=git_calls):
            self.assertEqual(self.released("skillup-forever", 9), cfwatch.Release("v1.5.1", "2026-11-02"))
        self.assertFalse([url for url in api_calls if "/compare/" in url])
        self.assertEqual(
            git_calls, [("fetch", "--tags", "--quiet"), ("tag", "--contains", "abc", "--sort=creatordate")]
        )

    def test_a_later_pr_in_another_repo_never_names_a_pr_here(self):
        issue = {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-18T00:00:00Z"}
        events = self.merged("2026-11-17T00:00:00Z") + self.merged("2026-11-17T12:00:00Z", 716, "forever-core")
        api_calls = []
        with self.release(issue, events, api_calls=api_calls):
            self.released("skillup-forever", 759)
        pulls = [url for url in api_calls if "/pulls/" in url]
        self.assertEqual(pulls, ["repos/cjber/skillup-forever/pulls/583"])

    def test_a_pr_only_in_another_repo_is_not_a_release_here(self):
        issue = {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-18T00:00:00Z"}
        api_calls = []
        with self.release(issue, self.merged(number=716, repo="forever-core"), api_calls=api_calls):
            self.assertIsNone(self.released("skillup-forever", 759))
        self.assertFalse([url for url in api_calls if "/pulls/" in url])

    def test_a_fix_on_main_but_not_in_a_release_is_not_due(self):
        issue = {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-11T02:16:31Z"}
        with self.release(issue, self.merged(), contained=()):
            self.assertIsNone(self.released("skillup-forever", 9))

    def test_a_pr_merged_after_the_issue_closed_does_not_close_it(self):
        issue = {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-11T02:16:31Z"}
        late = self.merged("2026-11-11T02:32:02Z")
        with self.release(issue, late, sha="late"):
            self.assertIsNone(self.released("skillup-forever", 9))

    def test_without_a_local_checkout_it_never_falls_back_to_compare_calls(self):
        issue = {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-11T02:16:31Z"}
        api_calls = []

        def api(*args):
            url = args[1]
            api_calls.append(url)
            if "/timeline" in url:
                return [{"event": "closed", "commit_id": "abc"}]
            if "/issues/9" in url:
                return issue
            raise AssertionError(url)

        with (
            unittest.mock.patch.object(cfwatch, "gh_json", api),
            unittest.mock.patch.object(cfwatch, "checkout", lambda root, repo: None),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertIsNone(self.released("skillup-forever", 9))
        self.assertFalse([url for url in api_calls if "/compare/" in url])

    def test_a_closed_issue_keeps_its_answer_for_later_runs(self):
        issue = {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-11T02:16:31Z"}
        cache, api_calls, git_calls = {}, [], []
        with self.release(issue, [{"event": "closed", "commit_id": "abc"}], api_calls=api_calls, git_calls=git_calls):
            first = self.released("skillup-forever", 9, cache=cache)
            second = self.released("skillup-forever", 9, cache=cache)
        self.assertEqual(first, second)
        self.assertEqual(
            cache["skillup-forever#9"],
            {"tag": "v1.5.1", "published": "2026-11-02", "closed_at": "2026-11-11T02:16:31Z"},
        )
        self.assertEqual(len(api_calls), 4)
        self.assertEqual(
            git_calls, [("fetch", "--tags", "--quiet"), ("tag", "--contains", "abc", "--sort=creatordate")]
        )

    def test_a_reopened_issue_drops_its_cached_release(self):
        closed = {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-11T02:16:31Z"}
        cache = {}
        with self.release(closed, [{"event": "closed", "commit_id": "abc"}]):
            self.assertEqual(self.released("skillup-forever", 9, cache=cache), cfwatch.Release("v1.5.1", "2026-11-02"))
        self.assertIn("skillup-forever#9", cache)

        with self.release({"state": "open"}):
            self.assertIsNone(self.released("skillup-forever", 9, cache=cache))
        self.assertNotIn("skillup-forever#9", cache)

    def test_a_reclosed_issue_with_a_new_fix_recomputes_its_release(self):
        first = {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-11T02:16:31Z"}
        cache, api_calls = {}, []
        with self.release(first, [{"event": "closed", "commit_id": "abc"}]):
            self.released("skillup-forever", 9, cache=cache)

        reclosed = {"state": "closed", "state_reason": "completed", "closed_at": "2026-12-01T00:00:00Z"}
        both_closes = [
            {"event": "closed", "commit_id": "abc", "created_at": "2026-11-11T02:16:31Z"},
            {"event": "reopened", "created_at": "2026-11-20T00:00:00Z"},
            {"event": "closed", "commit_id": "def", "created_at": "2026-12-01T00:00:00Z"},
        ]
        with self.release(
            reclosed,
            both_closes,
            tags=("v1.5.1", "v1.6.0"),
            contained=(),
            contained_by_sha={"abc": ("v1.5.1",), "def": ("v1.6.0",)},
            api_calls=api_calls,
        ):
            found = self.released("skillup-forever", 9, cache=cache)

        self.assertEqual(found, cfwatch.Release("v1.6.0", "2026-11-02"))
        self.assertIn("/timeline", "".join(api_calls))
        self.assertEqual(cache["skillup-forever#9"]["closed_at"], "2026-12-01T00:00:00Z")

    def test_a_new_manual_close_does_not_fall_back_to_the_old_commit(self):
        issue = {"state": "closed", "state_reason": "completed", "closed_at": "2026-12-01T00:00:00Z"}
        events = [
            {"event": "closed", "commit_id": "abc", "created_at": "2026-11-11T02:16:31Z"},
            {"event": "reopened", "created_at": "2026-11-20T00:00:00Z"},
            *self.merged("2026-11-25T00:00:00Z"),
            {"event": "closed", "created_at": "2026-12-01T00:00:00Z"},
        ]
        with self.release(
            issue,
            events,
            tags=("v1.5.1", "v1.6.0"),
            contained=(),
            contained_by_sha={"abc": ("v1.5.1",), "def": ("v1.6.0",)},
            sha="def",
        ):
            found = self.released("skillup-forever", 9)

        self.assertEqual(found, cfwatch.Release("v1.6.0", "2026-11-02"))

    def test_a_failed_tag_fetch_fails_closed_without_using_stale_tags(self):
        issue = {"state": "closed", "state_reason": "completed", "closed_at": "2026-11-11T02:16:31Z"}
        repositories, api_calls, git_calls = {}, [], []
        errors = io.StringIO()
        with (
            self.release(
                issue,
                [{"event": "closed", "commit_id": "abc"}],
                fetch_ok=False,
                api_calls=api_calls,
                git_calls=git_calls,
            ),
            contextlib.redirect_stderr(errors),
        ):
            self.assertIsNone(self.released("skillup-forever", 9, releases=repositories))
            self.assertIsNone(self.released("skillup-forever", 10, releases=repositories))

        self.assertEqual(git_calls, [("fetch", "--tags", "--quiet")])
        self.assertIn("git fetch --tags failed", errors.getvalue())
        self.assertFalse([url for url in api_calls if "/releases" in url or "/compare/" in url])


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
        with self.assertRaises(SystemExit) as missing, contextlib.redirect_stderr(io.StringIO()):
            run(["--settle", "1"], fake_fetch(self.rows()))
        self.assertEqual(missing.exception.code, 2)


class CliTest(unittest.TestCase):
    """The command line settles help and bad arguments before state, projects or the network."""

    def run_cli(self, argv):
        output, errors = io.StringIO(), io.StringIO()
        guard = unittest.mock.Mock(
            side_effect=AssertionError("the command line read state, projects or the network before it settled")
        )
        with (
            unittest.mock.patch.object(cfwatch, "projects", guard),
            unittest.mock.patch.object(cfwatch, "load", guard),
            unittest.mock.patch.object(cfwatch, "save", guard),
            unittest.mock.patch.object(cfwatch, "state_path", guard),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(errors),
        ):
            with self.assertRaises(SystemExit) as exit:
                cfwatch.main(argv, guard)
        return exit.exception.code, output.getvalue(), errors.getvalue()

    def test_help_prints_usage_and_exits_zero_before_any_side_effect(self):
        code, output, errors = self.run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("usage: cfwatch.py", output)
        self.assertIn("--settle THREAD REASON", output)
        self.assertEqual(errors, "")

    def test_unknown_or_malformed_arguments_exit_two_before_any_side_effect(self):
        cases = [
            ["--nope"],
            ["--unanswere"],
            ["--mark", "--unknown"],
            ["--settle", "1"],
            ["--settle", "not-a-number", "thanks only"],
            ["--settle", "1", "   "],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                code, output, errors = self.run_cli(argv)
                self.assertEqual(code, 2)
                self.assertIn("usage: cfwatch.py", errors)
                self.assertEqual(output, "")

    def test_every_current_mode_and_combination_still_runs(self):
        rows = [comment(1, "a question")]
        modes = [
            [],
            ["--mark"],
            ["--unanswered"],
            ["--due"],
            ["--mark", "--unanswered"],
            ["--settle", "#1", "thanks only"],
            ["--settle", "#1", "thanks only", "--settle", "1", "answered by another player"],
        ]
        for argv in modes:
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as tmp:
                output = run(argv, fake_fetch(rows), state=tmp)
                self.assertTrue(output)


if __name__ == "__main__":
    unittest.main()
