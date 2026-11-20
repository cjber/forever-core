import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from forever_tools import embed

CORE = Path(__file__).resolve().parents[5]


class EmbedTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "DemoForever"
        (self.root / "UI").mkdir(parents=True)
        (self.root / "tools").mkdir()
        (self.root / "tools" / "forever-core.txt").write_text("v1.14.5\n")
        self.toc()
        (self.root / "Main.lua").write_text("local addon, ns = ...\nns.main = addon\n")
        (self.root / "UI" / "UI.xml").write_text(
            '<Ui xmlns="http://www.blizzard.com/wow/ui/">\n  <Script file="Window.lua"/>\n</Ui>\n'
        )
        (self.root / "UI" / "Window.lua").write_bytes(b"\xef\xbb\xbflocal _, ns = ...\nns.window = true\n")

    def toc(
        self, fields="## OptionalDeps: ForeverCore\n## X-Forever-Core-Embed: 1\n## SavedVariables: DemoForeverDB\n"
    ):
        (self.root / "DemoForever.toc").write_text(f"## Interface: 16001\n{fields}\nMain.lua\nUI\\UI.xml\n")

    def run_embed(self):
        return embed.transform(self.root, CORE, "1.14.5")

    def test_the_toc_loads_core_then_the_host_then_the_addon(self):
        result = self.run_embed()
        self.assertEqual(result["wrapped"], 2)
        loads = [line for line in (self.root / "DemoForever.toc").read_text().splitlines() if line and line[0] != "#"]
        self.assertEqual(loads[0], "Libs\\ForeverCore\\Core\\Loader.lua")
        host = loads.index(embed.HOST_BEGIN)
        self.assertTrue(all(line.startswith("Libs\\ForeverCore\\") for line in loads[:host]))
        self.assertEqual(loads[host + 1 :], ["Main.lua", "UI\\UI.xml", embed.HOST_RUN, embed.READY])
        manifest = json.loads((self.root / "Libs/ForeverCore/bundle.json").read_text())
        self.assertEqual(manifest["wrapped"], ["Main.lua", "UI/Window.lua"])

    def test_wrapping_keeps_line_one_and_the_byte_order_mark(self):
        self.run_embed()
        main = (self.root / "Main.lua").read_bytes()
        self.assertTrue(main.startswith(embed.HEADER + b"local addon, ns = ...\n"))
        window = (self.root / "UI" / "Window.lua").read_bytes()
        self.assertTrue(window.startswith(embed.BOM + embed.HEADER + b"local _, ns = ...\n"))

    @unittest.skipUnless(shutil.which("luajit"), "luajit not on PATH")
    def test_a_wrapped_file_without_the_host_runs_at_once(self):
        self.run_embed()
        script = (
            f"local chunk = assert(loadfile({str(self.root / 'Main.lua')!r})) "
            'local ns = {} chunk("DemoForever", ns) '
            'assert(ns.main == "DemoForever", "ran at once") '
            'local hosted = { ForeverCoreHostChunks = {} } chunk("DemoForever", hosted) '
            'assert(hosted.main == nil and #hosted.ForeverCoreHostChunks == 1, "deferred under the host")'
        )
        subprocess.run(["luajit", "-e", script], check=True)

    @unittest.skipUnless(shutil.which("luajit"), "luajit not on PATH")
    def test_the_addon_files_run_even_when_core_did_not_start(self):
        self.run_embed()
        run = self.root / embed.HOST_RUN
        script = (
            "local ready = {} "
            "ForeverCoreLoader = { OnReady = function(callback) ready[#ready + 1] = callback end } "
            "local ran = 0 "
            "local host = { ForeverCoreHostChunks = { function() ran = ran + 1 end } } "
            f"assert(loadfile({str(run)!r}))('DemoForever', host) "
            "ready[1](nil, nil) "
            "assert(ran == 1, 'the files run, so the addon require gate can answer with the fix') "
        )
        subprocess.run(["luajit", "-e", script], check=True)

    @unittest.skipUnless(shutil.which("luajit"), "luajit not on PATH")
    def test_the_addon_files_get_the_loading_events_they_missed(self):
        self.run_embed()
        run = self.root / embed.HOST_RUN
        harness = Path(__file__).with_name("run_replay_harness.lua")
        subprocess.run(["luajit", str(harness), str(run)], check=True)

    @unittest.skipUnless(shutil.which("git"), "git not on PATH")
    def test_in_a_git_checkout_the_new_files_are_tracked_for_the_packager(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        self.run_embed()
        others = subprocess.run(
            ["git", "-C", str(self.root), "ls-files", "--others", "--directory"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.assertEqual(others, "")
        tracked = subprocess.run(
            ["git", "-C", str(self.root), "ls-files"], capture_output=True, text=True, check=True
        ).stdout.split()
        self.assertIn("Libs/ForeverCore/Core/Loader.lua", tracked)
        self.assertIn(embed.HOST_RUN, tracked)

    def test_a_required_core_is_refused(self):
        self.toc("## Dependencies: ForeverCore\n## X-Forever-Core-Embed: 1\n## SavedVariables: DemoForeverDB\n")
        with self.assertRaisesRegex(embed.EmbedError, "OptionalDeps"):
            self.run_embed()

    def test_an_addon_without_saved_variables_is_refused(self):
        self.toc("## OptionalDeps: ForeverCore\n## X-Forever-Core-Embed: 1\n")
        with self.assertRaisesRegex(embed.EmbedError, "SavedVariables"):
            self.run_embed()

    def test_an_addon_with_only_per_character_saved_variables_is_refused(self):
        self.toc(
            "## OptionalDeps: ForeverCore\n## X-Forever-Core-Embed: 1\n## SavedVariablesPerCharacter: DemoCharDB\n"
        )
        with self.assertRaisesRegex(embed.EmbedError, "per character"):
            self.run_embed()
        self.assertFalse((self.root / "Libs").exists())

    def test_an_addon_with_several_account_saved_variables_is_refused(self):
        self.toc("## OptionalDeps: ForeverCore\n## X-Forever-Core-Embed: 1\n## SavedVariables: DemoDB, DemoOtherDB\n")
        with self.assertRaisesRegex(embed.EmbedError, "exactly one"):
            self.run_embed()
        self.assertFalse((self.root / "Libs").exists())

    def test_one_account_global_beside_a_per_character_one_embeds(self):
        self.toc(
            "## OptionalDeps: ForeverCore\n## X-Forever-Core-Embed: 1\n## SavedVariables: DemoForeverDB\n"
            "## SavedVariablesPerCharacter: DemoCharDB\n"
        )
        self.assertEqual(self.run_embed()["wrapped"], 2)

    def test_the_last_opt_in_line_decides(self):
        for fields in (
            "## X-Forever-Core-Embed: 0\n## X-Forever-Core-Embed: 1\n",
            "##X-Forever-Core-Embed: 1\n",
            "  ## X-Forever-Core-Embed: 1\n",
        ):
            with self.subTest(fields=fields):
                self.toc("## OptionalDeps: ForeverCore\n## SavedVariables: DemoForeverDB\n" + fields)
                self.assertIs(embed.enabled(self.root), True)

    def test_an_opt_in_value_other_than_1_is_refused(self):
        for fields in (
            "## X-Forever-Core-Embed: 1\n## X-Forever-Core-Embed: 0\n",
            "## X-Forever-Core-Embed: 1, 1\n",
            "## X-Forever-Core-Embed: true\n",
            "## X-Forever-Core-Embed: 1 # note\n",
        ):
            with self.subTest(fields=fields):
                self.toc("## OptionalDeps: ForeverCore\n## SavedVariables: DemoForeverDB\n" + fields)
                with self.assertRaisesRegex(embed.EmbedError, "exactly 1"):
                    embed.enabled(self.root)

    def test_the_toc_is_the_one_package_as_names(self):
        (self.root / ".pkgmeta").write_text("package-as: DemoForever\n")
        (self.root / "Demo.toc").write_text("## Interface: 16001\n")
        self.assertTrue(embed.enabled(self.root))
        with self.assertRaisesRegex(embed.EmbedError, "also has Demo.toc"):
            self.run_embed()

    def test_a_second_package_as_is_refused(self):
        (self.root / ".pkgmeta").write_text("package-as: Wrong\npackage-as: DemoForever\n")
        with self.assertRaisesRegex(embed.EmbedError, "set 2 times"):
            embed.enabled(self.root)

    def test_a_flavor_toc_beside_the_root_toc_is_refused(self):
        (self.root / "DemoForever_Mainline.toc").write_text("## Interface: 110000\n")
        with self.assertRaisesRegex(embed.EmbedError, "DemoForever_Mainline.toc"):
            self.run_embed()

    def test_a_second_run_is_refused(self):
        self.run_embed()
        with self.assertRaisesRegex(embed.EmbedError, "already"):
            self.run_embed()

    def test_without_the_field_the_cli_changes_nothing(self):
        self.toc("## OptionalDeps: ForeverCore\n## SavedVariables: DemoForeverDB\n")
        before = (self.root / "DemoForever.toc").read_text()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(embed.main(["--core", str(CORE), str(self.root)]), 0)
        self.assertEqual((self.root / "DemoForever.toc").read_text(), before)
        self.assertFalse((self.root / "Libs").exists())


if __name__ == "__main__":
    unittest.main()
