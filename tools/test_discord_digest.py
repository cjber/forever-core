"""Tests for tools/discord_digest.py: pure payload building, no network."""

import contextlib
import io
import itertools
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import discord_digest as digest

NOW = datetime(2026, 11, 7, 18, tzinfo=timezone.utc)
SINCE = NOW - timedelta(hours=24)


def dataset(releases, changelog=None, store=None, addon=None):
    addon = addon or digest.ADDONS[0]
    classified = digest.classify_releases(releases)
    return digest.AddonData(addon, tuple(classified), changelog or {}, store or {})


def release(version, published):
    return digest.Release(version, published)


def addon(repo):
    return next(item for item in digest.ADDONS if item.repo == repo)


class FamilySyncTest(unittest.TestCase):
    def test_every_list_names_the_same_addons_in_the_same_order(self):
        family_names = [name for name, _slug, _line in digest.family.ADDONS]
        family_slugs = [slug for _name, slug, _line in digest.family.ADDONS]
        self.assertEqual([item.name for item in digest.ADDONS], family_names)
        self.assertEqual([item.repo for item in digest.ADDONS], family_slugs)
        self.assertEqual(set(digest.ACCENTS), set(family_slugs))
        for item in digest.ADDONS:
            self.assertEqual(item.accent, digest.ACCENTS[item.repo])


class ChangelogTest(unittest.TestCase):
    def test_player_bullets_and_subsections(self):
        text = """# Changelog

## [Unreleased]

- **Not shipped.**

## [1.1.6] - 2026-11-06

<!-- discord-image: docs/screenshots/new.png -->

- **The first headline.** Spoken as prose.
- **The second headline.**
- not bold, so not a player line
### For addon authors

- **An API note, not a player line.**

## [1.1.5] - 2026-11-05

- **An older headline.**
"""
        entries = digest.parse_changelog(text)
        self.assertNotIn("Unreleased", entries)
        self.assertEqual(entries["1.1.6"].headlines, ("The first headline.", "The second headline."))
        self.assertEqual(entries["1.1.6"].image, "docs/screenshots/new.png")
        self.assertEqual(entries["1.1.5"].headlines, ("An older headline.",))

    def test_player_bullets_under_changelog_sections(self):
        text = """# Changelog

## [1.14.0] - 2026-11-18

<!-- discord-image: docs/screenshots/route.png -->

### Changed

- **A changed headline.**

### Fixed

- **A fixed headline.**

### For addon authors

- **An API note, not a player line.**

### Tooling

- **A tooling note, not a player line.**
"""
        entries = digest.parse_changelog(text)
        self.assertEqual(entries["1.14.0"].headlines, ("A changed headline.", "A fixed headline."))
        self.assertEqual(entries["1.14.0"].image, "docs/screenshots/route.png")

    def test_player_bullets_with_any_list_marker(self):
        text = """# Changelog

## [1.14.0] - 2026-11-18

### Fixed

* **A star headline.**
+ **A plus headline.**
"""
        entries = digest.parse_changelog(text)
        self.assertEqual(entries["1.14.0"].headlines, ("A star headline.", "A plus headline."))


class ClassificationTest(unittest.TestCase):
    def test_major_and_minor_rises_are_features(self):
        versions = ("1.0.0", "1.0.1", "1.1.0", "1.1.1", "2.0.0", "2.0.1")
        releases = [release(version, NOW + timedelta(minutes=index)) for index, version in enumerate(versions)]
        classified = digest.classify_releases(releases)
        self.assertEqual([item.feature for item in classified], [True, False, True, False, True, False])

    def test_oldest_release_is_a_patch_when_it_starts_mid_line(self):
        releases = [
            release("0.5.0", NOW),
            release("0.5.1", NOW + timedelta(minutes=1)),
            release("0.6.0", NOW + timedelta(minutes=2)),
        ]
        classified = digest.classify_releases(releases)
        self.assertEqual([item.feature for item in classified], [True, False, True])

    def test_oldest_release_is_a_patch_without_a_patch_zero(self):
        releases = [release("0.5.1", NOW), release("0.6.0", NOW + timedelta(minutes=1))]
        classified = digest.classify_releases(releases)
        self.assertEqual([item.feature for item in classified], [False, True])


class DigestTest(unittest.TestCase):
    def digest(self, datasets, since=SINCE, now=NOW, backfill=False):
        payload = digest.build_digest(datasets, since, now, backfill=backfill)
        self.assertIsNotNone(payload)
        return payload

    def test_retired_wago_metadata_does_not_make_a_link(self):
        self.assertEqual(
            digest.parse_store_links("## X-Wago-ID: old\n## X-Curse-Project-ID: 1\n"),
            {"curseforge": "https://www.curseforge.com/projects/1"},
        )
        self.assertNotIn("Wago", digest.links_line({"wago": "https://addons.wago.io/addons/old"}, "https://notes.test"))

    def test_range_order_and_feature_fold(self):
        data = dataset(
            [
                release("1.0.0", SINCE - timedelta(hours=1)),
                release("1.0.1", SINCE + timedelta(hours=1)),
                release("1.1.0", SINCE + timedelta(hours=2)),
            ],
            {
                "1.0.1": digest.ChangelogEntry(("The patch fix.", "Another patch fix.")),
                "1.1.0": digest.ChangelogEntry(("The big feature.",)),
            },
            {"curseforge": "https://www.curseforge.com/projects/1", "wago": "https://addons.wago.io/addons/x"},
        )
        payload = self.digest([data])
        self.assertEqual(
            payload["content"],
            "**Today's updates · Saturday 7 November**\n"
            "2 releases across 1 addon. Update in your addon manager, then `/reload`.",
        )
        embed = payload["embeds"][0]
        self.assertEqual(embed["title"], "v1.0.0 → v1.1.0")
        self.assertEqual(embed["url"], "https://github.com/cjber/shortest-path-forever/releases/tag/v1.1.0")
        lines = embed["description"].splitlines()
        self.assertEqual(lines[0], "• New in 1.1: see the post above")
        self.assertEqual(lines[1], "• The patch fix.")
        self.assertEqual(lines[2], "• Another patch fix.")
        self.assertNotIn("The big feature.", embed["description"])
        self.assertNotIn("Wago", embed["description"])
        self.assertIn("[Full notes](https://github.com/cjber/shortest-path-forever/releases/tag/v1.1.0)", lines[-1])

    def test_an_addon_without_player_lines_is_left_out(self):
        with_lines = dataset([release("1.0.1", NOW - timedelta(hours=1))], {"1.0.1": digest.ChangelogEntry(("Fix.",))})
        without_lines = dataset(
            [release("0.1.0", NOW - timedelta(hours=1))],
            {},
            addon=digest.ADDONS[1],
        )
        payload = self.digest([with_lines, without_lines])
        self.assertEqual(len(payload["embeds"]), 1)
        self.assertIn("1 release across 1 addon.", payload["content"])

    def test_truncation_counts_hidden_lines(self):
        headlines = tuple(f"Headline {number}." for number in range(1, 7))
        data = dataset(
            [release("1.0.0", SINCE - timedelta(hours=1)), release("1.0.1", NOW - timedelta(hours=1))],
            {"1.0.1": digest.ChangelogEntry(headlines)},
        )
        embed = self.digest([data])["embeds"][0]
        lines = embed["description"].splitlines()
        self.assertEqual(lines[:4], [f"• Headline {number}." for number in range(1, 5)])
        self.assertEqual(lines[4], "+2 more")

    def test_backfill_heading_uses_the_since_date(self):
        data = dataset([release("1.0.1", NOW - timedelta(hours=1))], {"1.0.1": digest.ChangelogEntry(("Fix.",))})
        payload = self.digest([data], since=datetime(2026, 11, 5, 9, tzinfo=timezone.utc), backfill=True)
        self.assertTrue(payload["content"].startswith("**Updates since Thursday 5 November**"))

    def test_backfill_lists_feature_headlines_where_the_digest_folds_them(self):
        data = dataset(
            [release("1.0.0", SINCE - timedelta(hours=1)), release("1.1.0", NOW - timedelta(hours=1))],
            {"1.1.0": digest.ChangelogEntry(("The big feature.",))},
        )
        daily = self.digest([data])["embeds"][0]["description"]
        self.assertIn("• New in 1.1: see the post above", daily)
        self.assertNotIn("The big feature.", daily)

        backfill = self.digest([data], backfill=True)["embeds"][0]["description"]
        self.assertIn("• The big feature.", backfill)
        self.assertNotIn("see the post above", backfill)

    def test_count_nouns_are_pluralised(self):
        single = dataset(
            [release("1.0.0", SINCE - timedelta(hours=1)), release("1.0.1", NOW - timedelta(hours=1))],
            {"1.0.1": digest.ChangelogEntry(("A fix.",))},
        )
        self.assertIn("1 release across 1 addon.", self.digest([single])["content"])

        first = dataset(
            [
                release("1.0.0", SINCE - timedelta(hours=1)),
                release("1.0.1", NOW - timedelta(hours=2)),
                release("1.0.2", NOW - timedelta(hours=1)),
            ],
            {"1.0.1": digest.ChangelogEntry(("A fix.",)), "1.0.2": digest.ChangelogEntry(("Another fix.",))},
        )
        second = dataset(
            [release("2.0.0", SINCE - timedelta(hours=1)), release("2.0.1", NOW - timedelta(hours=1))],
            {"2.0.1": digest.ChangelogEntry(("A fix.",))},
            addon=digest.ADDONS[1],
        )
        self.assertIn("3 releases across 2 addons.", self.digest([first, second])["content"])

    def test_empty_digest_posts_nothing(self):
        data = dataset([release("1.0.1", NOW - timedelta(hours=1))], {})
        self.assertIsNone(digest.build_digest([data], SINCE, NOW))

    def test_digest_description_limit_keeps_the_links(self):
        headlines = tuple("A very long headline. " + "x" * 2000 for _ in range(4))
        data = dataset(
            [release("1.0.0", SINCE - timedelta(hours=1)), release("1.0.1", NOW - timedelta(hours=1))],
            {"1.0.1": digest.ChangelogEntry(headlines)},
        )
        embed = self.digest([data])["embeds"][0]
        self.assertLessEqual(len(embed["description"]), digest.MAX_DESCRIPTION)
        self.assertIn("[Full notes](", embed["description"])

    def test_total_embed_text_limit_trims_headlines_not_links(self):
        headlines = tuple("Another long headline. " + "y" * 900 for _ in range(4))
        first = dataset(
            [release("1.0.0", SINCE - timedelta(hours=1)), release("1.0.1", NOW - timedelta(hours=1))],
            {"1.0.1": digest.ChangelogEntry(headlines)},
        )
        second = dataset(
            [release("2.0.0", SINCE - timedelta(hours=1)), release("2.0.1", NOW - timedelta(hours=1))],
            {"2.0.1": digest.ChangelogEntry(headlines)},
            addon=digest.ADDONS[1],
        )
        payload = self.digest([first, second])
        self.assertLessEqual(sum(digest.embed_text_length(embed) for embed in payload["embeds"]), digest.MAX_EMBED_TEXT)
        for embed in payload["embeds"]:
            self.assertIn("[Full notes](", embed["description"])


class FeatureTest(unittest.TestCase):
    def test_feature_post_carries_every_headline_and_the_image(self):
        data = dataset(
            [release("1.0.0", NOW - timedelta(days=2)), release("1.1.0", NOW - timedelta(minutes=30))],
            {
                "1.1.0": digest.ChangelogEntry(
                    ("The first feature.", "The second feature."),
                    "docs/screenshots/feature.png",
                )
            },
            addon=addon("tweaks-forever"),
        )
        payloads = digest.build_features([data], NOW - timedelta(hours=1), NOW)
        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self.assertEqual(payload["content"], "**New in Tweaks Forever 1.1**")
        embed = payload["embeds"][0]
        self.assertEqual(embed["title"], "v1.1.0 · What's new")
        self.assertEqual(embed["author"]["icon_url"], digest.emblem_url(addon("tweaks-forever")))
        self.assertEqual(embed["thumbnail"]["url"], digest.icon_url(addon("tweaks-forever")))
        self.assertEqual(
            embed["image"]["url"],
            "https://raw.githubusercontent.com/cjber/tweaks-forever/v1.1.0/docs/screenshots/feature.png",
        )
        self.assertIn("• The first feature.", embed["description"])
        self.assertIn("• The second feature.", embed["description"])
        self.assertIn("[Full notes](", embed["description"])

    def test_feature_release_without_headlines_posts_nothing(self):
        data = dataset(
            [release("1.0.0", NOW - timedelta(days=2)), release("1.1.0", NOW - timedelta(minutes=30))],
            {"1.1.0": digest.ChangelogEntry((), "docs/screenshots/feature.png")},
        )
        self.assertEqual(digest.build_features([data], NOW - timedelta(hours=1), NOW), [])

    def test_only_feature_releases_inside_the_hour_are_posted(self):
        data = dataset(
            [
                release("1.0.0", NOW - timedelta(days=2)),
                release("1.0.1", NOW - timedelta(minutes=30)),
                release("1.1.0", NOW - timedelta(hours=2)),
            ],
            {
                "1.0.1": digest.ChangelogEntry(("A patch.",)),
                "1.1.0": digest.ChangelogEntry(("An older feature.",)),
            },
        )
        self.assertEqual(digest.build_features([data], NOW - timedelta(hours=1), NOW), [])


class CollectTest(unittest.TestCase):
    def test_one_repos_failure_does_not_drop_the_rest(self):
        def load(addon, token=None):
            if addon.repo == "skillup-forever":
                raise OSError("connection reset")
            return dataset([release("1.0.0", NOW)], addon=addon)

        errors = io.StringIO()
        with (
            mock.patch.object(digest, "load_addon", side_effect=load),
            contextlib.redirect_stderr(errors),
        ):
            datasets = digest.collect_datasets()
        self.assertEqual(
            [data.addon.repo for data in datasets],
            [
                "shortest-path-forever",
                "adventure-guide-forever",
                "legacy-forever",
                "tweaks-forever",
                "field-guide-forever",
                "commissions-forever",
                "macro-assist-forever",
            ],
        )
        self.assertIn("skipping skillup-forever: connection reset", errors.getvalue())


def at(day, hour, minute=0, second=0):
    return datetime(2026, 11, day, hour, minute, second, tzinfo=timezone.utc)


class ScheduledWindowsTest(unittest.TestCase):
    def test_a_delayed_run_still_posts_the_digest(self):
        windows = digest.scheduled_windows(at(16, 17, 10), at(16, 18, 50))
        self.assertEqual(windows.features, (at(16, 17, 10), at(16, 18, 50)))
        self.assertEqual(windows.digest, (at(15, 18), at(16, 18)))

    def test_only_the_first_run_past_the_hour_posts_the_digest(self):
        self.assertIsNone(digest.scheduled_windows(at(16, 18, 50), at(16, 19, 5)).digest)

    def test_a_dropped_hour_widens_the_feature_window(self):
        windows = digest.scheduled_windows(at(17, 1, 50), at(17, 10, 20))
        self.assertEqual(windows.features, (at(17, 1, 50), at(17, 10, 20)))
        self.assertIsNone(windows.digest)

    def test_a_day_without_an_hour_18_run_posts_on_the_next_run(self):
        # The 17 November runs: 01:50, 10:20, then 19:39, none in hour 18.
        windows = digest.scheduled_windows(at(17, 10, 20), at(17, 19, 39))
        self.assertEqual(windows.digest, (at(16, 18), at(17, 18)))

    def test_days_without_runs_fold_into_one_digest(self):
        windows = digest.scheduled_windows(at(14, 12), at(17, 2))
        self.assertEqual(windows.digest, (at(13, 18), at(16, 18)))

    def test_consecutive_windows_meet(self):
        starts = [at(16, 17, 10), at(16, 18, 50), at(17, 1, 50), at(17, 10, 20), at(17, 19, 39), at(18, 18, 0)]
        digests = []
        for previous, current in itertools.pairwise(starts):
            windows = digest.scheduled_windows(previous, current)
            self.assertEqual(windows.features[0], previous)
            if windows.digest:
                digests.append(windows.digest)
        self.assertEqual(digests, [(at(15, 18), at(16, 18)), (at(16, 18), at(17, 18)), (at(17, 18), at(18, 18))])

    def test_the_first_run_looks_back_one_hour(self):
        windows = digest.scheduled_windows(None, at(17, 10, 20))
        self.assertEqual(windows.features, (at(17, 9, 20), at(17, 10, 20)))
        self.assertIsNone(windows.digest)

    def test_a_digest_over_several_days_names_its_start(self):
        data = dataset([release("1.0.1", at(15, 9))], {"1.0.1": digest.ChangelogEntry(("Fix.",))})
        payload = digest.build_digest([data], at(13, 18), at(16, 18))
        self.assertTrue(payload["content"].startswith("**Updates since Friday 13 November**"))


class RunWindowsTest(unittest.TestCase):
    def test_previous_successful_scheduled_run_sets_the_windows(self):
        api = "https://api.github.com/repos/cjber/forever-core/actions"
        responses = {
            f"{api}/runs/3": {"id": 3, "workflow_id": 9, "run_started_at": "2026-11-17T19:39:37Z"},
            f"{api}/workflows/9/runs?event=schedule&status=success&per_page={digest.RUNS_PAGE}": {
                "workflow_runs": [
                    {"id": 4, "run_started_at": "2026-11-17T20:05:00Z"},
                    {"id": 2, "run_started_at": "2026-11-17T10:20:15Z"},
                    {"id": 1, "run_started_at": "2026-11-17T01:50:14Z"},
                ]
            },
        }
        with mock.patch.object(digest, "_get", side_effect=lambda url, token: json.dumps(responses[url])):
            windows = digest.fetch_run_windows("token", "cjber/forever-core", "3")
        self.assertEqual(windows.features, (at(17, 10, 20, 15), at(17, 19, 39, 37)))
        self.assertEqual(windows.digest, (at(16, 18), at(17, 18)))

    def test_schedule_mode_posts_features_before_the_digest(self):
        data = dataset(
            [release("1.0.0", at(15, 9)), release("1.1.0", at(17, 12))],
            {"1.1.0": digest.ChangelogEntry(("The big feature.",))},
        )
        windows = digest.Windows((at(17, 10, 20), at(17, 19, 39)), (at(16, 18), at(17, 18)))
        output = io.StringIO()
        with (
            mock.patch.object(digest, "fetch_run_windows", return_value=windows),
            mock.patch.object(digest, "collect_datasets", return_value=[data]),
            mock.patch.dict(
                os.environ,
                {"DISCORD_ANNOUNCE_WEBHOOK": "", "GITHUB_TOKEN": "", "GITHUB_REPOSITORY": "r", "GITHUB_RUN_ID": "1"},
            ),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(digest.main(["--mode", "schedule"]), 0)
        contents = [json.loads(line)["content"] for line in output.getvalue().splitlines()]
        self.assertEqual(len(contents), 2)
        self.assertTrue(contents[0].startswith("**New in Shortest Path Forever 1.1**"))
        self.assertTrue(contents[1].startswith("**Today's updates · Tuesday 17 November**"))


class MainTest(unittest.TestCase):
    def test_dry_run_prints_the_webhook_payload_without_posting(self):
        data = dataset(
            [release("1.0.0", SINCE - timedelta(hours=1)), release("1.0.1", NOW - timedelta(hours=1))],
            {"1.0.1": digest.ChangelogEntry(("A fix.",))},
        )
        output = io.StringIO()
        with (
            mock.patch.object(digest, "collect_datasets", return_value=[data]),
            mock.patch.object(digest, "post") as poster,
            mock.patch.dict(os.environ, {"DISCORD_ANNOUNCE_WEBHOOK": "", "GITHUB_TOKEN": ""}),
            contextlib.redirect_stdout(output),
        ):
            status = digest.main(["--mode", "digest", "--now", "2026-11-07T18:00:00Z", "--dry-run"])
        self.assertEqual(status, 0)
        poster.assert_not_called()
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["username"], "Forever Addons")
        self.assertEqual(payload["avatar_url"], digest.emblem_url(digest.ADDONS[0]))
        self.assertEqual(payload["allowed_mentions"], {"parse": []})
        self.assertIn("Today's updates", payload["content"])

    def test_missing_webhook_also_dry_runs(self):
        data = dataset(
            [release("1.0.0", SINCE - timedelta(hours=1)), release("1.0.1", NOW - timedelta(hours=1))],
            {"1.0.1": digest.ChangelogEntry(("A fix.",))},
        )
        output = io.StringIO()
        with (
            mock.patch.object(digest, "collect_datasets", return_value=[data]),
            mock.patch.object(digest, "post") as poster,
            mock.patch.dict(os.environ, {"DISCORD_ANNOUNCE_WEBHOOK": "", "GITHUB_TOKEN": ""}),
            contextlib.redirect_stdout(output),
        ):
            status = digest.main(["--mode", "digest", "--now", "2026-11-07T18:00:00Z"])
        self.assertEqual(status, 0)
        poster.assert_not_called()
        self.assertIn('"content"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
