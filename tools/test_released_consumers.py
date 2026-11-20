"""Tests for tools/released_consumers.py: asset choice, safe unpacking and the released consumer folders, no network."""

import contextlib
import io
import json
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock

import released_consumers as released


def archive(members: dict[str, bytes]) -> bytes:
    """A zip in memory from member name to contents."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        for name, data in members.items():
            package.writestr(name, data)
    return buffer.getvalue()


def release(tag: str, *names: str) -> dict:
    """A release JSON with one asset per name."""
    return {
        "tag_name": tag,
        "assets": [{"name": name, "browser_download_url": f"https://example.test/{name}"} for name in names],
    }


class AssetTest(unittest.TestCase):
    """Which asset of a release is the addon, and which never is."""

    def test_the_forever_zip_is_the_addon(self):
        chosen = released.addon_asset(
            release("v1.2.3", "release.json", "LegacyForever-v1.2.3-forever.zip", "notes.txt")
        )
        self.assertEqual(chosen["name"], "LegacyForever-v1.2.3-forever.zip")

    def test_a_plain_zip_is_the_next_choice(self):
        chosen = released.addon_asset(release("v1.2.3", "release.json", "LegacyForever.zip"))
        self.assertEqual(chosen["name"], "LegacyForever.zip")

    def test_release_json_is_never_the_addon(self):
        self.assertIsNone(released.addon_asset(release("v1.2.3", "release.json")))

    def test_a_release_with_no_assets_has_no_addon(self):
        self.assertIsNone(released.addon_asset({"tag_name": "v1.2.3"}))

    def test_the_cache_folder_name_is_safe(self):
        self.assertEqual(released.tag_label({"tag_name": "v1.2.3/build"}), "v1.2.3_build")
        self.assertEqual(released.tag_label({}), "latest")


class DownloadTest(unittest.TestCase):
    def test_download_rejects_oversized_response_without_writing_it(self):
        destination = Path(self.enterContext(tempfile.TemporaryDirectory())) / "addon.zip"
        asset = release("v1", "addon.zip")["assets"][0]
        with (
            mock.patch.object(released, "MAX_DOWNLOAD_BYTES", 3, create=True),
            mock.patch.object(released.urllib.request, "urlopen", return_value=io.BytesIO(b"1234")),
            self.assertRaisesRegex(released.ReleasedError, "download.*limit"),
        ):
            released.download(asset, destination)
        self.assertFalse(destination.exists())


class ExtractTest(unittest.TestCase):
    """The addon's own folder is what a release gives, and nothing escapes the cache folder."""

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())) / "unpacked"

    def unpack(self, members: dict[str, bytes]) -> None:
        package = self.root.parent / "addon.zip"
        package.write_bytes(archive(members))
        released.extract(package, self.root)

    def test_the_addons_own_folder_is_returned_and_core_and_libraries_are_dropped(self):
        self.unpack(
            {
                "LegacyForever/LegacyForever.toc": b"## Interface: 16001\n",
                "LegacyForever/UI/Map.lua": b"-- map\n",
                "ForeverCore/ForeverCore.toc": b"## Interface: 16001\n",
                "LibStub/LibStub.toc": b"## Interface: 16001\n",
            }
        )
        self.assertEqual([name for name, _folder in released.addon_folders(self.root)], ["LegacyForever"])
        self.assertTrue((self.root / "LegacyForever/UI/Map.lua").is_file())

    def test_extract_rejects_excessive_member_count(self):
        with (
            mock.patch.object(released, "MAX_ZIP_MEMBERS", 1, create=True),
            self.assertRaisesRegex(released.ReleasedError, "member count.*limit"),
        ):
            self.unpack({"Addon/": b"", "Addon/Addon.toc": b""})
        self.assertFalse(self.root.exists())

    def test_extract_rejects_excessive_cumulative_size(self):
        with (
            mock.patch.object(released, "MAX_EXTRACTED_BYTES", 3, create=True),
            self.assertRaisesRegex(released.ReleasedError, "extracted size.*limit"),
        ):
            self.unpack({"Addon/first": b"12", "Addon/second": b"34"})
        self.assertFalse(self.root.exists())

    def test_an_absolute_member_is_refused(self):
        with self.assertRaisesRegex(released.ReleasedError, "unsafe zip member"):
            self.unpack({"LegacyForever/LegacyForever.toc": b"", "/etc/passwd": b"root"})

    def test_a_parent_member_is_refused(self):
        with self.assertRaisesRegex(released.ReleasedError, "unsafe zip member"):
            self.unpack({"LegacyForever/LegacyForever.toc": b"", "../../evil.txt": b"x"})

    def test_a_windows_parent_member_is_refused(self):
        with self.assertRaisesRegex(released.ReleasedError, "unsafe zip member"):
            self.unpack({"LegacyForever/LegacyForever.toc": b"", "..\\evil.txt": b"x"})

    def test_a_drive_letter_member_is_refused(self):
        with self.assertRaisesRegex(released.ReleasedError, "unsafe zip member"):
            self.unpack({"C:/Windows/evil.txt": b"x"})

    def test_a_folder_without_its_toc_is_not_an_addon(self):
        self.unpack({"ForeverCore/ForeverCore.toc": b"", "LibStub/LibStub.toc": b"", "notes.txt": b"hi"})
        self.assertEqual(released.addon_folders(self.root), [])


class ReleasedFoldersTest(unittest.TestCase):
    """Every consumer's latest release is unpacked once, and a failure is an error."""

    def setUp(self):
        self.cache = Path(self.enterContext(tempfile.TemporaryDirectory())) / "released"

    def run_release(self, releases: dict, packages: dict, repos=("legacy-forever", "skillup-forever")):
        def download(asset, destination):
            destination.write_bytes(packages[asset["name"]])
            return destination

        with (
            mock.patch.object(released, "discover_tooling_repos", return_value=set()),
            mock.patch.object(released, "consumer_repos", return_value=list(repos)),
            mock.patch.object(released, "latest_release", side_effect=lambda repo: releases.get(repo)),
            mock.patch.object(released, "download", side_effect=download),
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            folders = released.released_folders(self.cache)
        return folders, out.getvalue()

    def test_each_consumers_release_is_unpacked_and_its_own_folder_returned(self):
        folders, printed = self.run_release(
            {
                "legacy-forever": release("v2.4.1", "release.json", "LegacyForever-v2.4.1-forever.zip"),
                "skillup-forever": release("v1.0.0", "SkillUpForever-v1.0.0-forever.zip"),
            },
            {
                "LegacyForever-v2.4.1-forever.zip": archive(
                    {
                        "LegacyForever/LegacyForever.toc": b"",
                        "ForeverCore/ForeverCore.toc": b"",
                    }
                ),
                "SkillUpForever-v1.0.0-forever.zip": archive({"SkillUpForever/SkillUpForever.toc": b""}),
            },
        )
        self.assertEqual([name for name, _path in folders], ["LegacyForever", "SkillUpForever"])
        self.assertTrue((self.cache / "legacy-forever-v2.4.1/LegacyForever/LegacyForever.toc").is_file())
        self.assertIn("legacy-forever: v2.4.1 LegacyForever", printed)

    def test_a_consumer_with_no_release_is_skipped_with_a_note(self):
        folders, printed = self.run_release(
            {"legacy-forever": release("v2.4.1", "LegacyForever-v2.4.1-forever.zip")},
            {"LegacyForever-v2.4.1-forever.zip": archive({"LegacyForever/LegacyForever.toc": b""})},
        )
        self.assertEqual([name for name, _path in folders], ["LegacyForever"])
        self.assertIn("skillup-forever: no release; skipped", printed)

    def test_a_release_with_no_addon_zip_is_skipped_with_a_note(self):
        folders, printed = self.run_release(
            {
                "legacy-forever": release("v2.4.1", "release.json"),
                "skillup-forever": release("v1.0.0", "SkillUpForever-v1.0.0-forever.zip"),
            },
            {"SkillUpForever-v1.0.0-forever.zip": archive({"SkillUpForever/SkillUpForever.toc": b""})},
        )
        self.assertEqual([name for name, _path in folders], ["SkillUpForever"])
        self.assertIn("legacy-forever: release v2.4.1 ships no addon zip; skipped", printed)

    def test_no_released_consumer_folder_at_all_is_an_error(self):
        with self.assertRaisesRegex(
            released.ReleasedError, "no released consumer found: the gate cannot check anything"
        ):
            self.run_release(
                {"legacy-forever": release("v2.4.1", "release.json")},
                {},
                repos=("legacy-forever",),
            )

    def test_no_consumer_with_a_release_is_the_same_error(self):
        with self.assertRaisesRegex(released.ReleasedError, "no released consumer found"):
            self.run_release({}, {})

    def test_an_unpacked_release_with_no_addon_folder_is_an_error(self):
        with self.assertRaisesRegex(released.ReleasedError, "holds no addon folder"):
            self.run_release(
                {"legacy-forever": release("v2.4.1", "LegacyForever-v2.4.1-forever.zip")},
                {"LegacyForever-v2.4.1-forever.zip": archive({"ForeverCore/ForeverCore.toc": b""})},
                repos=("legacy-forever",),
            )

    def test_a_download_that_fails_is_an_error(self):
        with (
            mock.patch.object(released, "discover_tooling_repos", return_value=set()),
            mock.patch.object(released, "consumer_repos", return_value=["legacy-forever"]),
            mock.patch.object(released, "latest_release", return_value=release("v1", "LegacyForever-v1.zip")),
            mock.patch.object(
                released,
                "download",
                side_effect=released.ReleasedError("could not download LegacyForever-v1.zip: no route"),
            ),
            self.assertRaisesRegex(released.ReleasedError, "could not download"),
        ):
            released.released_folders(self.cache)

    def test_a_command_that_cannot_unpack_exits_nonzero(self):
        with (
            mock.patch.object(released, "released_folders", side_effect=released.ReleasedError("no network")),
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            code = released.main([])
        self.assertEqual(code, 1)
        self.assertIn("no network", err.getvalue())

    def test_the_command_lists_every_returned_folder(self):
        folders = [("LegacyForever", Path("/cache/LegacyForever"))]
        with (
            mock.patch.object(released, "released_folders", return_value=folders),
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            self.assertEqual(released.main([]), 0)
        self.assertIn("LegacyForever: /cache/LegacyForever", out.getvalue())


class ReleaseReadTest(unittest.TestCase):
    """A missing release is a skip, an unreadable API is an error."""

    def test_a_missing_release_is_none(self):
        error = urllib.error.HTTPError("https://api.github.test", 404, "Not Found", {}, None)
        with mock.patch.object(released, "remote_json", side_effect=error):
            self.assertIsNone(released.latest_release("kiln-forever"))

    def test_another_read_failure_is_an_error(self):
        with mock.patch.object(released, "remote_json", side_effect=json.JSONDecodeError("bad", "", 0)):
            with self.assertRaisesRegex(released.ReleasedError, "could not read"):
                released.latest_release("legacy-forever")


if __name__ == "__main__":
    unittest.main()
