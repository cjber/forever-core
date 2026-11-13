"""Tests for tools/dependabot_merge.py, against recorded REST JSON and a fake `gh`."""

import io
import unittest
from contextlib import redirect_stdout

import dependabot_merge

PATCH = """Bump actions/checkout from 4.1.0 to 4.2.0

Bumps [actions/checkout](https://github.com/actions/checkout) from 4.1.0 to 4.2.0.

---
updated-dependencies:
- dependency-name: actions/checkout
  dependency-type: direct:production
  update-type: version-update:semver-patch
...
"""

MINOR = PATCH.replace("semver-patch", "semver-minor")
MAJOR = PATCH.replace("semver-patch", "semver-major")

GROUPED_MINOR = """Bump the actions group with 2 updates

Bumps the actions group with 2 updates: [actions/checkout](https://github.com/actions/checkout) and
[actions/setup-python](https://github.com/actions/setup-python).

---
updated-dependencies:
- dependency-name: actions/checkout
  dependency-type: direct:production
  update-type: version-update:semver-minor
- dependency-name: actions/setup-python
  dependency-type: direct:production
  update-type: version-update:semver-patch
...
"""

GROUPED_ONE_MAJOR = GROUPED_MINOR.replace("semver-minor", "semver-major")


class FakeGh:
    """The recorded REST answers, with every write recorded instead of made."""

    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def json(self, path):
        self.calls.append(("json", path))
        return self.payloads[path]

    def enable_auto_merge(self, repo, number):
        self.calls.append(("merge", repo, number))

    def disable_auto_merge(self, repo, number):
        self.calls.append(("disable", repo, number))

    def label(self, repo, number, name):
        self.calls.append(("label", repo, number, name))


def pull(number, sha, login="dependabot[bot]"):
    return {"number": number, "user": {"login": login}, "head": {"sha": sha}}


def payloads(repo, pulls, messages):
    table = {f"repos/cjber/{repo}/pulls?state=open&per_page=100&page=1": pulls}
    for index, message in messages.items():
        table[f"repos/cjber/{repo}/commits/{pulls[index]['head']['sha']}"] = {"commit": {"message": message}}
    return table


class DecideTest(unittest.TestCase):
    def test_a_single_patch_or_minor_update_merges(self):
        for message in (PATCH, MINOR):
            with self.subTest(message=message.splitlines()[0]):
                decision = dependabot_merge.decide(message)
                self.assertEqual(decision.action, "merge")
                self.assertEqual([dependency.name for dependency in decision.dependencies], ["actions/checkout"])

    def test_a_major_update_waits_for_review(self):
        decision = dependabot_merge.decide(MAJOR)
        self.assertEqual(decision.action, "major")
        self.assertEqual(decision.dependencies[0].update, "major")

    def test_a_grouped_update_merges_only_when_every_dependency_is_patch_or_minor(self):
        self.assertEqual(dependabot_merge.decide(GROUPED_MINOR).action, "merge")
        minor = dependabot_merge.decide(GROUPED_MINOR)
        self.assertEqual(
            [(dependency.name, dependency.update) for dependency in minor.dependencies],
            [("actions/checkout", "minor"), ("actions/setup-python", "patch")],
        )
        grouped = dependabot_merge.decide(GROUPED_ONE_MAJOR)
        self.assertEqual(grouped.action, "major")
        self.assertEqual([dependency.update for dependency in grouped.dependencies], ["major", "patch"])

    def test_a_message_without_a_trailer_is_left_for_review(self):
        decision = dependabot_merge.decide("Bump something\n\nNo trailers here.\n")
        self.assertEqual(decision.action, "review")
        self.assertEqual(decision.dependencies, [])

    def test_an_unknown_update_type_is_left_for_review(self):
        message = PATCH.replace("version-update:semver-patch", "version-update:semver-0")
        self.assertEqual(dependabot_merge.decide(message).action, "review")


class MainTest(unittest.TestCase):
    def run_main(self, argv, gh, repos):
        out = io.StringIO()
        with redirect_stdout(out):
            code = dependabot_merge.main(argv, gh=gh, repos=repos)
        return code, out.getvalue()

    def test_a_dry_run_reads_and_changes_nothing(self):
        pulls = [pull(1, "a" * 40), pull(2, "b" * 40), pull(3, "c" * 40, login="cjber")]
        gh = FakeGh(payloads("tweaks-forever", pulls, {0: PATCH, 1: GROUPED_ONE_MAJOR}))
        code, out = self.run_main(["--dry-run"], gh, ["tweaks-forever"])
        self.assertEqual(code, 0)
        self.assertIn("auto-merge", out)
        self.assertIn("left for review, labelled major", out)
        self.assertEqual([call for call in gh.calls if call[0] != "json"], [])
        self.assertNotIn("repos/cjber/tweaks-forever/commits/" + "c" * 40, [call[1] for call in gh.calls])

    def test_a_live_run_arms_auto_merge_and_labels_a_major(self):
        pulls = [pull(1, "a" * 40), pull(2, "b" * 40), pull(3, "c" * 40)]
        gh = FakeGh(payloads("field-guide-forever", pulls, {0: PATCH, 1: MAJOR, 2: GROUPED_MINOR}))
        code, out = self.run_main([], gh, ["field-guide-forever"])
        self.assertEqual(code, 0, out)
        writes = [call for call in gh.calls if call[0] != "json"]
        self.assertEqual(
            writes,
            [
                ("merge", "field-guide-forever", 1),
                ("disable", "field-guide-forever", 2),
                ("label", "field-guide-forever", 2, "major"),
                ("merge", "field-guide-forever", 3),
            ],
        )

    def test_a_message_that_cannot_be_read_is_not_auto_merged(self):
        pulls = [pull(1, "a" * 40)]
        gh = FakeGh(payloads("legacy-forever", pulls, {0: "Bump something\n\nNo trailers here.\n"}))
        code, out = self.run_main([], gh, ["legacy-forever"])
        self.assertEqual(code, 0, out)
        self.assertEqual([call for call in gh.calls if call[0] != "json"], [("disable", "legacy-forever", 1)])

    def test_a_repository_that_cannot_be_read_is_reported(self):
        gh = FakeGh({})
        code, out = self.run_main([], gh, ["legacy-forever"])
        self.assertEqual(code, 1)
        self.assertIn("could not list Dependabot pull requests", out)
        self.assertIn("legacy-forever", out)

    def test_a_repository_with_no_open_pull_request_reads_one_page(self):
        gh = FakeGh({"repos/cjber/forever-core/pulls?state=open&per_page=100&page=1": []})
        code, out = self.run_main([], gh, ["forever-core"])
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.calls, [("json", "repos/cjber/forever-core/pulls?state=open&per_page=100&page=1")])


if __name__ == "__main__":
    unittest.main()
