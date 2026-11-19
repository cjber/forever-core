"""Tests for tools/checklist: round composition, answers, the server, the BugGrabber reader and the release gate."""

import contextlib
import io
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "checklist"))

import checklist as cl  # noqa: E402

ROUND = """
round: 2026-11-19-2
title: Test round 2
builds:
  - addon: forever-core
    sha: b2ba8950aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    prs: [876]
  - addon: kiln-forever
    sha: 1234567
    regression: false
checks:
  - id: menus
    addon: forever-core
    pr: 876
    title: Menus match
    steps: [Right-click a step.]
    pass: They match.
  - id: opt
    addon: forever-core
    optional: true
    title: Optional one
    pass: It works.
"""

BUGS = r"""
BugGrabberDB = {
["lastSanitation"] = 3,
["errors"] = {
{
["message"] = "old \"quoted\" error\nline two",
["time"] = 100,
["counter"] = 1,
},
{
["message"] = "Interface/AddOns/X/a.lua:1: new \\ error \226\128\148",
["time"] = 2000,
["stack"] = [[stack
here]],
["counter"] = 3,
}, -- trailing comment
},
["session"] = 4515,
}
"""


class ChecklistTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        (self.home / "rounds").mkdir()
        (self.home / "rounds" / "2026-11-19-2.yaml").write_text(ROUND)
        patch = mock.patch.object(cl, "HANDOFF", self.home)
        patch.start()
        self.addCleanup(patch.stop)

    def test_compose_adds_regression_for_shipping_addons(self):
        r = cl.compose("2026-11-19-2")
        ids = [c["id"] for c in r["checks"]]
        self.assertEqual(ids[:2], ["menus", "opt"])
        self.assertIn("reg:forever-core:reload-clean", ids)
        self.assertFalse([i for i in ids if i.startswith("reg:kiln-forever")])
        self.assertTrue(all(c["sha"].startswith("b2ba895") for c in r["checks"] if c["addon"] == "forever-core"))
        self.assertEqual([g["addon"] for g in r["groups"]], ["forever-core"])

    def test_gate_needs_every_check_of_the_build(self):
        sha = "b2ba895"
        self.assertFalse(cl.gate("forever-core", sha)[0])
        for c in cl.compose("2026-11-19-2")["checks"]:
            if c["addon"] == "forever-core":
                cl.record_answer("2026-11-19-2", c["id"], "pass", None)
        self.assertTrue(cl.gate("forever-core", sha)[0])
        cl.record_answer("2026-11-19-2", "opt", "skip", "no Questie")
        self.assertTrue(cl.gate("forever-core", sha)[0])
        cl.record_answer("2026-11-19-2", "menus", "skip", None)
        self.assertFalse(cl.gate("forever-core", sha)[0])
        ok, rows, _ = cl.gate("forever-core", "deadbee")
        self.assertEqual((ok, rows), (False, []))
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stdout(io.StringIO()):
            cl.main(["status", "--addon", "forever-core", "--sha", sha])
        self.assertEqual(e.exception.code, 1)

    def test_an_answer_counts_only_for_the_build_it_was_given_against(self):
        for c in cl.compose("2026-11-19-2")["checks"]:
            if c["addon"] == "forever-core":
                cl.record_answer("2026-11-19-2", c["id"], "pass", None)
        with contextlib.redirect_stdout(io.StringIO()):
            cl.main(["build", "--addon", "forever-core", "--sha", "c0ffee1200000000000000000000000000000000"])
        self.assertFalse(cl.gate("forever-core", "c0ffee1200000000000000000000000000000000")[0])
        self.assertFalse(cl.gate("forever-core", "b2ba895")[0])
        cl.record_answer("2026-11-19-2", "menus", None, "a note after the new build")
        _, rows = cl.status_rows("2026-11-19-2")
        menus = next(r for r in rows if r["id"] == "menus")
        self.assertEqual((menus["status"], menus["note"]), (None, "a note after the new build"))
        self.assertNotIn('"status": "pass"', cl.render("2026-11-19-2", served=True))

    def test_a_new_runtime_digest_reopens_the_build(self):
        for c in cl.compose("2026-11-19-2")["checks"]:
            if c["addon"] == "forever-core":
                cl.record_answer("2026-11-19-2", c["id"], "pass", None)
        self.assertTrue(cl.gate("forever-core", "b2ba895")[0])
        with contextlib.redirect_stdout(io.StringIO()):
            cl.main(["build", "--addon", "forever-core", "--digest", "relinked"])
        self.assertFalse(cl.gate("forever-core", "b2ba895")[0])
        with self.assertRaises(SystemExit), mock.patch.object(cl.subprocess, "run", side_effect=OSError):
            cl.full_sha("forever-core", "b2ba895")

    def test_answers_reject_unknown_checks_and_statuses(self):
        with self.assertRaises(ValueError):
            cl.record_answer("2026-11-19-2", "nope", "pass", None)
        with self.assertRaises(ValueError):
            cl.record_answer("2026-11-19-2", "menus", "maybe", None)
        cl.record_answer("2026-11-19-2", "menus", "fail", "clipped")
        cl.record_answer("2026-11-19-2", "menus", None, "clipped radios")
        a = cl.load_results("2026-11-19-2")["answers"]["menus"]
        self.assertEqual((a["status"], a["note"], a["sha"][:7]), ("fail", "clipped radios", "b2ba895"))

    def test_a_page_rendered_for_another_build_cannot_pass_this_one(self):
        shown = {"sha": "b2ba8950aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "digest": ""}
        old = dict(shown, sha="0" * 40)
        png = "data:image/png;base64,iVBORw0KGgo="
        with self.assertRaisesRegex(ValueError, "reload the page"):
            cl.record_answer("2026-11-19-2", "menus", "pass", None, old)
        with self.assertRaisesRegex(ValueError, "reload the page"):
            cl.record_image("2026-11-19-2", "menus", png, old)
        with self.assertRaisesRegex(ValueError, "reload the page"):
            cl.record_answer("2026-11-19-2", "menus", "", None, old)
        cl.record_answer("2026-11-19-2", "menus", None, "a note is kept", old)
        first = cl.record_image("2026-11-19-2", "menus", png, shown)
        cl.record_answer("2026-11-19-2", "menus", "pass", None, shown)
        answer = cl.load_results("2026-11-19-2")["answers"]["menus"]
        self.assertEqual((answer["status"], answer["images"]), ("pass", [first]), "a screenshot pasted first is kept")
        # The same commit and digest tested in another client build reopens the check and drops its screenshot.
        with contextlib.redirect_stdout(io.StringIO()):
            cl.main(["build", "--addon", "forever-core", "--client-build", "1.60.2.71000"])
        _, rows = cl.status_rows("2026-11-19-2")
        menus = next(r for r in rows if r["id"] == "menus")
        self.assertEqual((menus["status"], menus["images"], menus["note"]), (None, [], "a note is kept"))
        with self.assertRaisesRegex(ValueError, "reload the page"):
            cl.record_answer("2026-11-19-2", "menus", "pass", None, shown)
        self.assertNotEqual(cl.record_image("2026-11-19-2", "menus", png, None), first)

    def test_buggrabber_reader_keeps_errors_since_the_round_started(self):
        path = self.home / "bugs.lua"
        path.write_bytes(BUGS.encode())
        db = cl.LuaReader(BUGS).assignments()["BugGrabberDB"]
        self.assertEqual(db["errors"][0]["message"], 'old "quoted" error\nline two')
        self.assertEqual(db["session"], 4515)
        errors = cl.bug_errors(1000, path)
        self.assertEqual(len(errors), 1)
        self.assertIn("new \\ error —", errors[0]["message"])
        self.assertEqual(errors[0]["stack"], "stack\nhere")

    def test_add_and_build_cli(self):
        with contextlib.redirect_stdout(io.StringIO()):
            cl.main(
                [
                    "build",
                    "--addon",
                    "shortest-path-forever",
                    "--sha",
                    "abcdef1000000000000000000000000000000000",
                    "--pr",
                    "1066",
                ]
            )
            cl.main(
                ["add", "--addon", "shortest-path-forever", "--title", "Menus match", "--pass", "ok", "--step", "a"]
            )
        data = cl.load_round("2026-11-19-2")
        self.assertEqual(
            data["builds"][-1],
            {"addon": "shortest-path-forever", "sha": "abcdef1000000000000000000000000000000000", "prs": ["1066"]},
        )
        self.assertEqual(data["checks"][-1]["id"], "menus-match")
        artifact = self.home / "core-1/ForeverCore"
        artifact.mkdir(parents=True)
        (artifact / "ForeverCore.toc").write_text("## Interface: 16001\n")
        with contextlib.redirect_stdout(io.StringIO()):
            cl.main(["build", "--addon", "forever-core", "--artifact", str(artifact.parent), "--digest", "d1"])
            cl.main(["build", "--addon", "forever-core", "--client-build", "1.60.1.70959"])

        def status():
            out = io.StringIO()
            with self.assertRaises(SystemExit), contextlib.redirect_stdout(out):
                cl.main(["status", "--addon", "forever-core", "--sha", "b2ba895", "--json"])
            return json.loads(out.getvalue())["build"]

        build = status()
        self.assertEqual((build["artifact"], build["digest"]), (str(artifact.parent), "d1"))
        self.assertEqual(build["client_build"], "1.60.1.70959")
        self.assertEqual(len(build["artifact_sha256"]), 64)
        self.assertEqual(build["artifact_sha256_now"], build["artifact_sha256"])
        (artifact / "Core.lua").write_text("-- rebuilt\n")
        self.assertNotEqual(status()["artifact_sha256_now"], build["artifact_sha256"])
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            cl.main(["build", "--addon", "forever-core", "--artifact", "test-artifacts/missing"])
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            cl.main(["add", "--addon", "forever-core", "--id", "menus", "--title", "Again", "--pass", "ok"])

    def test_server_saves_answers_and_refuses_cross_origin(self):
        server = cl.make_server(0)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{port}"

        def post(path, body, origin=None):
            req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
            if origin:
                req.add_header("Origin", origin)
            with urllib.request.urlopen(req) as r:
                return json.load(r)

        page = urllib.request.urlopen(base + "/round/2026-11-19-2").read().decode()
        self.assertIn("Menus match", page)
        self.assertIn("started", cl.load_results("2026-11-19-2"))
        shown = {
            "sha": "b2ba8950aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "digest": "",
            "artifact_sha256": "",
            "client_build": "",
        }
        with self.assertRaises(urllib.error.HTTPError) as e:
            post("/api/answer/2026-11-19-2", {"check": "menus", "status": "pass"}, origin=base)
        self.assertEqual(e.exception.code, 400)
        e.exception.close()
        post("/api/answer/2026-11-19-2", {"check": "menus", "status": "pass", **shown}, origin=base)
        png = "data:image/png;base64,iVBORw0KGgo="
        fname = post("/api/image/2026-11-19-2", {"check": "menus", "data": png, **shown})["file"]
        self.assertRegex(fname, r"^menus-1-[0-9a-f]{8}\.png$")
        self.assertTrue((self.home / "results" / "2026-11-19-2" / fname).exists())
        self.assertEqual(cl.load_results("2026-11-19-2")["answers"]["menus"]["images"], [fname])
        with mock.patch.object(cl, "BUGGRABBER", self.home / "missing.lua"):
            self.assertEqual(post("/api/submit/2026-11-19-2", {})["bugs"], 0)
        with self.assertRaises(urllib.error.HTTPError) as e:
            post("/api/answer/2026-11-19-2", {"check": "menus", "status": "fail"}, origin="https://example.com")
        self.assertEqual(e.exception.code, 403)
        e.exception.close()
        self.assertEqual(cl.load_results("2026-11-19-2")["answers"]["menus"]["status"], "pass")
        with self.assertRaises(urllib.error.HTTPError) as e:
            post("/api/image/2026-11-19-2", {"check": "nope", "data": png})
        self.assertEqual(e.exception.code, 400)
        e.exception.close()
        for bad in ("/shots/../rounds/2026-11-19-2.yaml", "/round/..", "/round/2026-01-01-1", "/api/results/x"):
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + bad)
            self.assertEqual(e.exception.code, 404, bad)
            e.exception.close()
        self.assertFalse((self.home / "results" / "2026-01-01-1.json").exists())
        with self.assertRaises(urllib.error.HTTPError) as e:
            post("/api/answer/2026-11-19-2", {"check": "menus", "status": "fail"}, origin="http://localhost:3000")
        self.assertEqual(e.exception.code, 403)
        e.exception.close()
        rebound = urllib.request.Request(base + "/api/results/2026-11-19-2", headers={"Host": "evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(rebound)
        self.assertEqual(e.exception.code, 403)
        e.exception.close()

    def test_copy_has_no_long_dashes(self):
        files = [cl.PAGE_TEMPLATE, cl.HERE / "README.md", *cl.REGRESSION_DIR.glob("*.yaml")]
        for f in files:
            self.assertNotRegex(f.read_text(), "[–—]", f.name)
        self.assertNotRegex(cl.render("2026-11-19-2", served=True), "[–—]")

    def test_regression_files_are_well_formed(self):
        for f in cl.REGRESSION_DIR.glob("*.yaml"):
            data = cl.load_yaml(f)
            self.assertTrue(data.get("name"), f.name)
            ids = [c["id"] for c in data["checks"]]
            self.assertEqual(len(ids), len(set(ids)), f.name)
            for c in data["checks"]:
                self.assertTrue(c["title"] and c["pass"], f"{f.name}: {c['id']}")


if __name__ == "__main__":
    unittest.main()
