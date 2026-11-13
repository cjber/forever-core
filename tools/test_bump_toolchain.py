"""Tests for tools/bump_toolchain.py, against recorded upstream JSON and no network."""

import base64
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import bump_toolchain

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
OLD = "2026-11-01T00:00:00Z"
YESTERDAY = "2026-11-12T00:00:00Z"
HOURS_AGO = "2026-11-13T09:00:00Z"

MANIFEST = {
    "schema": 1,
    "runtimes": {
        "python": {
            "version": "3.14",
            "upstream": {"kind": "github-release", "repo": "python/cpython", "strip": "minor", "tag": "v{version}"},
        },
        "node": {
            "version": "22",
            "upstream": {"kind": "github-release", "repo": "nodejs/node", "strip": "major", "tag": "v{version}"},
        },
        "bun": {"version": "1.4.2", "upstream": {"kind": "npm", "package": "bun"}},
    },
    "tools": {
        "lua51": {
            "version": "5.1.5",
            "url": "https://www.lua.org/ftp/lua-{version}.tar.gz",
            "sha256": "0" * 64,
            "upstream": {"kind": "github-tag", "repo": "lua/lua", "series": "^5\\.1\\.", "tag": "v{version}"},
        },
        "luajit": {
            "commit": "c525bcb9024510cad9e170e12b6209aedb330f83",
            "upstream": {"kind": "github-branch", "repo": "LuaJIT/LuaJIT", "branch": "v2.1"},
        },
        "luacheck": {
            "version": "1.1.2",
            "commit": "418f48976c73be697fe64b0eba9ea9821ac9bca8",
            "upstream": {"kind": "github-tag", "repo": "lunarmodules/luacheck", "tag": "v{version}"},
        },
        "luals": {
            "version": "3.19.1",
            "url": "https://github.com/LuaLS/lua-language-server/releases/download/{version}/lua-language-server-{version}-linux-x64.tar.gz",
            "sha256": "e" * 64,
            "upstream": {"kind": "github-release", "repo": "LuaLS/lua-language-server", "tag": "{version}"},
        },
        "annotations": {
            "commit": "d0b5b51fac4c52c493371b9b18e66ce604ea4326",
            "upstream": {"kind": "github-branch", "repo": "Ketho/vscode-wow-api", "branch": "master"},
        },
        "speedpatrol": {"version": "0.2.0", "upstream": {"kind": "npm", "package": "speedpatrol"}},
    },
}

NEW_LUACHECK = "0123456789abcdef0123456789abcdef01234567"
NEW_LUAJIT = "fedcba9876543210fedcba9876543210fedcba98"
NEW_ANNOTATIONS = "1111111111111111111111111111111111111111"


def routes(extra=None):
    """Every upstream read the fixture manifest makes, as the fake network answers them."""
    table = {
        "repos/python/cpython/releases?per_page=100": [
            {"tag_name": "v3.15.0", "published_at": OLD, "prerelease": False, "draft": False},
            {"tag_name": "v3.15.0rc1", "published_at": OLD, "prerelease": True, "draft": False},
            {"tag_name": "v3.14.10", "published_at": OLD, "prerelease": False, "draft": False},
        ],
        "repos/nodejs/node/releases?per_page=100": [
            {"tag_name": "v24.1.0", "published_at": OLD, "prerelease": False, "draft": False},
            {"tag_name": "v22.20.0", "published_at": OLD, "prerelease": False, "draft": False},
        ],
        "repos/lua/lua/tags?per_page=100": [
            {"name": "v5.5.1", "commit": {"sha": "a" * 40}},
            {"name": "v5.1.5", "commit": {"sha": "b" * 40}},
        ],
        "repos/LuaJIT/LuaJIT/commits/v2.1": {
            "sha": NEW_LUAJIT,
            "commit": {"committer": {"date": OLD}},
        },
        "repos/lunarmodules/luacheck/tags?per_page=100": [
            {"name": "v1.2.0", "commit": {"sha": NEW_LUACHECK}},
            {"name": "v1.1.2", "commit": {"sha": "418f48976c73be697fe64b0eba9ea9821ac9bca8"}},
            {"name": "v1", "commit": {"sha": "c" * 40}},
        ],
        f"repos/lunarmodules/luacheck/commits/{NEW_LUACHECK}": {"commit": {"committer": {"date": OLD}}},
        "repos/LuaLS/lua-language-server/releases?per_page=100": [
            {"tag_name": "3.20.0", "published_at": OLD, "prerelease": False, "draft": False},
            {"tag_name": "3.19.1", "published_at": OLD, "prerelease": False, "draft": False},
        ],
        "repos/Ketho/vscode-wow-api/commits/master": {
            "sha": NEW_ANNOTATIONS,
            "commit": {"committer": {"date": OLD}},
        },
    }
    table.update(extra or {})
    table.update(DOWNLOADS)
    return table


LUALS_ASSET = "lua-language-server-3.20.0-linux-x64.tar.gz"
DOWNLOADS = {
    "https://www.lua.org/ftp/lua-5.1.5.tar.gz": b"lua 5.1.5",
    f"https://github.com/LuaLS/lua-language-server/releases/download/3.20.0/{LUALS_ASSET}": b"luals",
}


class FakeNet:
    """One recorded table for both reads: a GitHub path or URL maps to its JSON, a download URL to its bytes."""

    def __init__(self, table):
        self.table = table
        self.calls = []

    def github(self, path):
        self.calls.append(path)
        return self.table[path]

    def get(self, url):
        self.calls.append(url)
        return self.table[url]


def npm(package, version, published=OLD):
    return json.dumps({"dist-tags": {"latest": version}, "time": {version: published}})


def current_routes():
    """Every upstream read answered with the manifest's own pin, so nothing should move."""
    table = routes()
    table["repos/LuaLS/lua-language-server/releases?per_page=100"] = [
        {"tag_name": "3.19.1", "published_at": OLD, "prerelease": False, "draft": False}
    ]
    table["repos/lunarmodules/luacheck/tags?per_page=100"] = [
        {"name": "v1.1.2", "commit": {"sha": "418f48976c73be697fe64b0eba9ea9821ac9bca8"}}
    ]
    table["repos/LuaJIT/LuaJIT/commits/v2.1"] = {
        "sha": MANIFEST["tools"]["luajit"]["commit"],
        "commit": {"committer": {"date": OLD}},
    }
    table["repos/Ketho/vscode-wow-api/commits/master"] = {
        "sha": MANIFEST["tools"]["annotations"]["commit"],
        "commit": {"committer": {"date": OLD}},
    }
    table["repos/python/cpython/releases?per_page=100"] = [
        {"tag_name": "v3.14.10", "published_at": OLD, "prerelease": False, "draft": False}
    ]
    table["repos/nodejs/node/releases?per_page=100"] = [
        {"tag_name": "v22.20.0", "published_at": OLD, "prerelease": False, "draft": False}
    ]
    table["https://registry.npmjs.org/bun"] = npm("bun", "1.4.2")
    table["https://registry.npmjs.org/speedpatrol"] = npm("speedpatrol", "0.2.0")
    return table


class VersionTest(unittest.TestCase):
    def test_a_tag_names_the_version_the_entry_tracks(self):
        cases = [
            ("v2.5.2", {"tag": "v{version}"}, "2.5.2"),
            ("1.7.12.25", {"tag": "{version}"}, "1.7.12.25"),
            ("v1_9_0", {"tag": "v{version}"}, "1.9.0"),
            ("2.5.2", {"tag": "v{version}"}, None),
            ("v3.15.0", {"tag": "v{version}", "strip": "minor"}, "3.15"),
            ("v22.20.0", {"tag": "v{version}", "strip": "major", "series": "^22$"}, "22"),
            ("v5.5.1", {"tag": "v{version}", "series": "^5\\.1\\."}, None),
            ("v5.1.5", {"tag": "v{version}", "series": "^5\\.1\\."}, "5.1.5"),
            ("v5.5-beta", {"tag": "v{version}"}, None),
            ("release-1.0", {"tag": "v{version}"}, None),
            ("v23.0.0", {"tag": "v{version}", "strip": "major", "series": "^22$"}, None),
        ]
        for tag, upstream, expected in cases:
            with self.subTest(tag=tag, upstream=upstream):
                self.assertEqual(bump_toolchain.version_from_tag(tag, upstream), expected)


class PlanTest(unittest.TestCase):
    def test_every_kind_of_pin_is_read_from_its_upstream(self):
        table = routes()
        table["https://registry.npmjs.org/bun"] = npm("bun", "1.4.4")
        table["https://registry.npmjs.org/speedpatrol"] = npm("speedpatrol", "0.3.0")
        net = FakeNet(table)
        updates = bump_toolchain.plan(MANIFEST, net, NOW)
        self.assertEqual(
            [(update.group, update.name) for update in updates],
            [
                ("runtimes", "python"),
                ("runtimes", "node"),
                ("runtimes", "bun"),
                ("tools", "luajit"),
                ("tools", "luacheck"),
                ("tools", "luals"),
                ("tools", "annotations"),
                ("tools", "speedpatrol"),
            ],
        )
        self.assertEqual(updates[0].fields, {"version": "3.15"})
        self.assertEqual(updates[1].fields, {"version": "24"})
        self.assertEqual(updates[2].fields, {"version": "1.4.4"})
        self.assertEqual(updates[3].fields, {"commit": NEW_LUAJIT})
        self.assertEqual(updates[4].fields, {"version": "1.2.0", "commit": NEW_LUACHECK})
        self.assertEqual(
            updates[5].fields,
            {
                "version": "3.20.0",
                "sha256": hashlib.sha256(b"luals").hexdigest(),
            },
        )
        self.assertEqual(updates[6].fields, {"commit": NEW_ANNOTATIONS})
        self.assertEqual(updates[7].fields, {"version": "0.3.0"})

    def test_a_pin_at_its_pinned_version_does_not_move(self):
        self.assertEqual(bump_toolchain.plan(MANIFEST, FakeNet(current_routes()), NOW), [])

    def test_an_older_upstream_never_downgrades_a_pin(self):
        table = current_routes()
        table["repos/LuaLS/lua-language-server/releases?per_page=100"] = [
            {"tag_name": "3.18.9", "published_at": OLD, "prerelease": False, "draft": False}
        ]
        table["https://registry.npmjs.org/bun"] = npm("bun", "1.4.1")
        names = [update.name for update in bump_toolchain.plan(MANIFEST, FakeNet(table), NOW)]
        self.assertNotIn("luals", names)
        self.assertNotIn("bun", names)

    def test_a_release_younger_than_the_cooldown_is_skipped(self):
        table = routes()
        table["https://registry.npmjs.org/bun"] = npm("bun", "1.4.4", HOURS_AGO)
        table["https://registry.npmjs.org/speedpatrol"] = npm("speedpatrol", "0.3.0", YESTERDAY)
        table["repos/LuaLS/lua-language-server/releases?per_page=100"] = [
            {"tag_name": "3.20.0", "published_at": HOURS_AGO, "prerelease": False, "draft": False},
            {"tag_name": "3.19.1", "published_at": OLD, "prerelease": False, "draft": False},
        ]
        updates = bump_toolchain.plan(MANIFEST, FakeNet(table), NOW)
        names = [update.name for update in updates]
        self.assertNotIn("bun", names)
        self.assertNotIn("luals", names)
        self.assertIn("speedpatrol", names)

    def test_a_dry_run_prints_the_plan_and_writes_nothing(self):
        table = routes()
        table["https://registry.npmjs.org/bun"] = npm("bun", "1.4.2")
        table["https://registry.npmjs.org/speedpatrol"] = npm("speedpatrol", "0.2.0")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "toolchain.json"
            path.write_text(json.dumps(MANIFEST, indent=2) + "\n")
            out = io.StringIO()
            with redirect_stdout(out):
                code = bump_toolchain.main(["--manifest", str(path), "--dry-run"], FakeNet(table), NOW)
            self.assertEqual(code, 0)
            self.assertIn("tools.luals: version 3.19.1 -> 3.20.0", out.getvalue())
            self.assertEqual(path.read_text(), json.dumps(MANIFEST, indent=2) + "\n")

    def test_a_run_rewrites_the_manifest_in_place(self):
        table = routes()
        table["https://registry.npmjs.org/bun"] = npm("bun", "1.4.2")
        table["https://registry.npmjs.org/speedpatrol"] = npm("speedpatrol", "0.2.0")
        manifest = json.loads(json.dumps(MANIFEST))
        updates = bump_toolchain.plan(manifest, FakeNet(table), NOW)
        bump_toolchain.apply(manifest, updates)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "toolchain.json"
            bump_toolchain.write(path, manifest)
            written = json.loads(path.read_text())
            self.assertEqual(list(written), ["schema", "runtimes", "tools"])
            self.assertEqual(written["tools"]["luals"]["version"], "3.20.0")
            self.assertEqual(written["tools"]["luals"]["sha256"], hashlib.sha256(b"luals").hexdigest())
            self.assertTrue(path.read_text().endswith("}\n"))


class MajorTest(unittest.TestCase):
    def test_a_new_major_is_proposed_like_any_other_update(self):
        update = bump_toolchain.plan_entry(
            "runtimes", "node", MANIFEST["runtimes"]["node"], FakeNet(routes()), NOW, bump_toolchain.COOLDOWN_DAYS
        )
        self.assertEqual(update.fields, {"version": "24"})

    def test_only_a_version_pin_can_cross_a_major(self):
        after = json.loads(json.dumps(MANIFEST))
        after["runtimes"]["python"]["version"] = "3.16"
        after["runtimes"]["node"]["version"] = "24"
        after["runtimes"]["bun"]["version"] = "2.0.0"
        after["tools"]["luacheck"]["version"] = "1.2.0"
        after["tools"]["luajit"]["commit"] = NEW_LUAJIT
        after["tools"]["luals"]["version"] = "4.0.0"
        self.assertEqual(
            bump_toolchain.changes(MANIFEST, after)[1],
            ["runtimes.node", "runtimes.bun", "tools.luals"],
        )

    def test_lua51_keeps_its_series_and_says_why(self):
        manifest = json.loads(bump_toolchain.MANIFEST.read_text(encoding="utf-8"))
        lua51 = manifest["tools"]["lua51"]
        self.assertEqual(lua51["upstream"]["series"], "^5\\.1\\.")
        self.assertIn("Lua 5.1", lua51["note"])
        self.assertNotIn("series", manifest["runtimes"]["node"]["upstream"])


class StagedChangesTest(unittest.TestCase):
    def test_additions_and_deletions_carry_the_file_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def run(*args):
                subprocess.run(args, cwd=root, check=True, capture_output=True)

            run("git", "init", "--quiet")
            run("git", "config", "user.email", "test@example.com")
            run("git", "config", "user.name", "Test")
            (root / "toolchain.json").write_text("{}\n")
            (root / "gone.txt").write_text("bye\n")
            run("git", "add", "-A")
            run("git", "commit", "--quiet", "-m", "base")
            (root / "toolchain.json").write_text('{"schema": 2}\n')
            (root / "gone.txt").unlink()
            here = Path.cwd()
            try:
                os.chdir(root)
                additions, deletions = bump_toolchain.staged_changes()
            finally:
                os.chdir(here)
            self.assertEqual(deletions, [{"path": "gone.txt"}])
            self.assertEqual([entry["path"] for entry in additions], ["toolchain.json"])
            self.assertEqual(
                base64.b64decode(additions[0]["contents"]).decode(),
                '{"schema": 2}\n',
            )


FAKE_GH = """#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\\n")
if args[:1] == ["api"]:
    path = args[1]
    if path == "graphql":
        print(json.dumps({"data": {"createCommitOnBranch": {"commit": {"oid": "c" * 40}}}}))
    elif "/pulls?" in path:
        print("[]")
    elif path.endswith("/pulls"):
        print(json.dumps({"number": 7, "html_url": "https://example.invalid/7"}))
    else:
        print("{}")
"""


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log = self.root / "gh.log"
        self.log.write_text("")
        binaries = self.root / "bin"
        binaries.mkdir()
        gh = binaries / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.path = f"{binaries}{os.pathsep}{os.environ['PATH']}"
        self.run_git("git", "init", "--quiet")
        self.run_git("git", "config", "user.email", "test@example.com")
        self.run_git("git", "config", "user.name", "Test")
        self.write_manifest("3.19.1")
        self.run_git("git", "add", "-A")
        self.run_git("git", "commit", "--quiet", "-m", "base")
        self.cwd = Path.cwd()

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def run_git(self, *args):
        subprocess.run(args, cwd=self.root, check=True, capture_output=True)

    def write_manifest(self, version):
        manifest = {"schema": 1, "runtimes": {}, "tools": {"luals": {"version": version}}}
        (self.root / "toolchain.json").write_text(json.dumps(manifest, indent=2) + "\n")

    def publish(self):
        previous = {name: os.environ.get(name) for name in ("PATH", "FAKE_GH_LOG", "GITHUB_REPOSITORY")}
        os.environ.update({"PATH": self.path, "FAKE_GH_LOG": str(self.log), "GITHUB_REPOSITORY": "cjber/forever-core"})
        out = io.StringIO()
        try:
            os.chdir(self.root)
            with redirect_stdout(out):
                code = bump_toolchain.open_pr()
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return code, out.getvalue(), calls

    def test_publishing_a_clean_tree_touches_nothing(self):
        code, out, calls = self.publish()
        self.assertEqual(code, 0)
        self.assertIn("Nothing to publish", out)
        self.assertEqual(calls, [])

    def test_a_minor_update_arms_auto_merge_and_drops_an_old_major_label(self):
        self.write_manifest("3.20.0")
        code, out, calls = self.publish()
        self.assertEqual(code, 0, out)
        self.assertTrue([call for call in calls if call[:2] == ["pr", "merge"]])
        self.assertFalse([call for call in calls if "labels[]=major" in call])
        bodies = [arg for call in calls for arg in call if arg.startswith("body=")]
        self.assertIn("tools.luals: version 3.19.1 -> 3.20.0", bodies[0])
        self.assertTrue(
            [call for call in calls if "DELETE" in call and any(arg.endswith("/labels/major") for arg in call)]
        )

    def test_a_major_update_waits_for_review_and_is_labelled(self):
        self.write_manifest("4.0.0")
        code, out, calls = self.publish()
        self.assertEqual(code, 0, out)
        self.assertIn("waits for review", out)
        self.assertFalse([call for call in calls if call[:3] == ["pr", "merge", "--auto"]])
        self.assertTrue([call for call in calls if call[:3] == ["pr", "merge", "--disable-auto"]])
        self.assertEqual(
            [call for call in calls if "labels[]=major" in call],
            [["api", "repos/cjber/forever-core/issues/7/labels", "--method", "POST", "-f", "labels[]=major"]],
        )


if __name__ == "__main__":
    unittest.main()
