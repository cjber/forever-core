import hashlib
import json
import tempfile
import unittest
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import audit_store_core as audit


class StoreAuditTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.cache = Path(temp.name)
        self.now = datetime(2026, 11, 20, tzinfo=timezone.utc)
        self.github = {"name": "FieldGuideForever-v0.8.15-forever.zip"}
        self.curseforge = self.github.copy()
        self.assets = [self.github]
        self.consumer_published = self.now - timedelta(hours=48)

    def release(self, repo):
        if repo == "forever-core":
            return {"tag_name": "v1.15.3", "published_at": self.now.isoformat()}
        return {"tag_name": "v0.8.15", "assets": self.assets, "published_at": self.consumer_published.isoformat()}

    def run_audit(self, hours=0):
        return audit.audit(
            self.cache,
            now=self.now + timedelta(hours=hours),
            repos=lambda: ["field-guide-forever"],
            release=self.release,
            fetch_asset=self.fetch,
            cf_asset=lambda project: self.curseforge,
            lookup_project=lambda repo: 1,
        )

    def fetch(self, asset, destination, **kwargs):
        curse = asset is self.curseforge
        if curse:
            self.assertIs(kwargs["request"], urllib.request.Request)
        if asset.get("unavailable"):
            raise OSError("read unavailable")
        with zipfile.ZipFile(destination, "w") as archive:
            addon = "FieldGuideForever"
            toc = "## X-Curse-Project-ID: 1\n"
            if "embed" in asset:
                major, minor, patch = map(int, asset["embed"].split("."))
                build = major * 1000000 + minor * 1000 + patch
                digest = "a" * 64
                stamp = f'host.ForeverCoreCopy = ForeverCoreLoader.Begin(addon, {build}, "{digest}")'.encode()
                prefix = "Libs/ForeverCore/"
                manifest = {
                    "schema": 1,
                    "standalone": False,
                    "version": asset["embed"],
                    "build": build,
                    "source_digest": digest,
                    "files": {prefix + "Begin.lua": hashlib.sha256(stamp).hexdigest()},
                }
                archive.writestr(f"{addon}/{prefix}Begin.lua", stamp)
                archive.writestr(f"{addon}/{prefix}bundle.json", json.dumps(manifest))
                toc += "## X-Forever-Core-Embed: 1\n"
            archive.writestr(f"{addon}/{addon}.toc", toc)
            if "bridge" in asset:
                archive.writestr("ForeverCore/ForeverCore.toc", f"## Version: {asset['bridge']}\n")
        return destination

    def test_field_guide_legacy_file_is_flagged_on_both_stores_during_grace(self):
        self.github["bridge"] = self.curseforge["bridge"] = "v1.14.5"
        reports, failures = self.run_audit()
        self.assertEqual(len(reports), 2)
        self.assertTrue(all("v0.8.15" in row and "bridge v1.14.5" in row for row in reports))
        self.assertEqual(sum("below the minimum v1.15.0" in row for row in failures), 2)
        self.assertEqual(sum("older than latest v1.15.3" in row for row in failures), 2)

    def test_bridge_above_floor_still_fails_during_grace(self):
        self.github["bridge"] = self.curseforge["bridge"] = "v1.15.2"
        _, failures = self.run_audit()
        self.assertEqual(len(failures), 2)
        self.assertTrue(all("older than latest" in row for row in failures))

    def test_embed_grace_expires_at_24_hours_and_never_excuses_floor(self):
        self.github["embed"] = self.curseforge["embed"] = "1.15.2"
        self.assertEqual(self.run_audit(hours=23)[1], [])
        self.assertEqual(len(self.run_audit(hours=24)[1]), 2)
        self.curseforge["embed"] = "1.14.5"
        self.assertIn("CurseForge", self.run_audit()[1][0])
        self.assertIn("below the minimum", self.run_audit()[1][0])

    def test_reports_fresh_github_and_stale_curseforge_independently(self):
        self.github["embed"] = self.curseforge["embed"] = "1.15.3"
        self.assertEqual(self.run_audit(hours=25)[1], [])
        self.curseforge.update(name="FieldGuideForever-v0.8.14-forever.zip", embed="1.15.1")
        _, failures = self.run_audit(hours=25)
        self.assertEqual(len(failures), 2)
        self.assertTrue(all("CurseForge" in row for row in failures))
        self.assertTrue(any("file-name parity" in row and "GitHub v0.8.15" in row for row in failures))

    def test_all_forever_assets_are_inspected_and_can_match_curseforge(self):
        self.github["embed"] = "1.15.3"
        second = {"name": "Other-v0.8.15-forever.zip", "bridge": "v1.14.5"}
        self.assets.append(second)
        self.curseforge.update(name=second["name"], embed="1.15.3")
        reports, failures = self.run_audit(hours=25)
        self.assertEqual(len(reports), 3)
        self.assertTrue(any(second["name"] in row and "below the minimum" in row for row in failures))
        self.assertFalse(any("file-name parity" in row for row in failures))

    def test_fresh_clean_github_release_allows_previous_curseforge_file(self):
        self.github["embed"] = "1.15.3"
        self.consumer_published = self.now + timedelta(hours=25)
        self.curseforge["name"] = "FieldGuideForever-v0.8.14-forever.zip"
        for layout, version in (("bridge", "v1.14.5"), ("embed", "1.14.5")):
            with self.subTest(layout=layout):
                self.curseforge[layout] = version
                self.assertEqual(self.run_audit(hours=48)[1], [])
                failures = self.run_audit(hours=49)[1]
                self.assertTrue(any("below the minimum" in row for row in failures))
                self.assertTrue(any("file-name parity" in row for row in failures))
                del self.curseforge[layout]

    def test_fresh_unclean_github_does_not_excuse_curseforge(self):
        self.consumer_published = self.now
        self.github["embed"] = "1.14.5"
        self.curseforge.update(name="FieldGuideForever-v0.8.14-forever.zip", bridge="v1.14.5")
        _, failures = self.run_audit()
        self.assertTrue(any("CurseForge" in row and "file-name parity" in row for row in failures))
        self.assertTrue(any("CurseForge" in row and "below the minimum" in row for row in failures))

    def test_read_failure_and_missing_core_fail_the_audit(self):
        self.curseforge["unavailable"] = True
        _, failures = self.run_audit()
        self.assertEqual(len(failures), 2)
        self.assertIn("package carries no ForeverCore", failures[0])
        self.assertIn("CurseForge project 1: read unavailable", failures[1])

    def test_a_consumer_with_no_release_is_reported_not_failed(self):
        self.release = lambda repo: (
            None if repo != "forever-core" else {"tag_name": "v1.15.3", "published_at": self.now.isoformat()}
        )
        reports, failures = self.run_audit()
        self.assertEqual(failures, [])
        self.assertEqual(reports, ["field-guide-forever: no published release"])

    def test_github_read_failure_still_audits_curseforge(self):
        self.github["unavailable"] = True
        self.curseforge["bridge"] = "v1.14.5"
        reports, failures = self.run_audit()
        self.assertEqual(len(reports), 1)
        self.assertIn("CurseForge", reports[0])
        self.assertIn("GitHub v0.8.15 (FieldGuideForever-v0.8.15-forever.zip): read unavailable", failures[0])
        self.assertIn("below the minimum", failures[1])

    def test_workflow_uses_the_repository_token_for_github_reads(self):
        workflow = Path(audit.__file__).resolve().parents[1] / ".github/workflows/store-core-audit.yml"
        self.assertIn("GH_TOKEN: ${{ github.token }}", workflow.read_text())

    def test_curseforge_selects_approved_stable_forever_and_uses_public_cdn(self):
        def fetch(url):
            self.assertIn("releaseType=1", url)
            return {
                "data": [
                    {"releaseType": 2},
                    {"releaseType": 1, "status": 4, "gameVersionTypeIds": [1]},
                    {
                        "releaseType": 1,
                        "status": 4,
                        "gameVersionTypeIds": [88568],
                        "id": 9705567,
                        "fileName": "File Name.zip",
                    },
                ]
            }

        result = audit.curseforge_asset(123, fetch=fetch)
        self.assertEqual(result["browser_download_url"], "https://edge.forgecdn.net/files/9705/567/File%20Name.zip")

    def test_curseforge_paginates_and_supports_an_authenticated_download_url(self):
        calls = []

        def fetch(url, *, headers=None):
            calls.append((url, headers))
            if "pageIndex=0" in url:
                return {"data": [{"releaseType": 2}], "pagination": {"totalCount": 2}}
            if "pageIndex=1" in url:
                return {
                    "data": [
                        {
                            "releaseType": 1,
                            "status": 4,
                            "gameVersionTypeIds": [88568],
                            "id": 12,
                            "fileName": "Addon.zip",
                        }
                    ]
                }
            return {"data": "https://example.test/Addon.zip"}

        result = audit.curseforge_asset(123, fetch=fetch, key="test-key")
        self.assertEqual(result["browser_download_url"], "https://example.test/Addon.zip")
        self.assertEqual(calls[-1][1], {"x-api-key": "test-key"})
        self.assertTrue(all(headers is None for _url, headers in calls[:-1]))

    def test_matching_issue_is_updated_instead_of_duplicated(self):
        calls = []

        def api(*args):
            calls.append(args)
            return [{"title": audit.ISSUE_TITLE, "number": 42, "body": "previous"}]

        audit.update_issue(["bad file"], api=api)
        self.assertEqual(calls[-1][0:2], ("issues/42", "PATCH"))
        self.assertIn("bad file", calls[-1][2]["body"])
        calls.clear()

        def empty(*args):
            calls.append(args)
            return []

        audit.update_issue(["bad file"], api=empty)
        self.assertEqual(calls[-1][0:2], ("issues", "POST"))
        self.assertEqual(calls[-1][2]["title"], audit.ISSUE_TITLE)


if __name__ == "__main__":
    unittest.main()
