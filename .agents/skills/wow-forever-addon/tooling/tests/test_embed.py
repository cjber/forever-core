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

    def test_a_required_core_is_refused(self):
        self.toc("## Dependencies: ForeverCore\n## X-Forever-Core-Embed: 1\n## SavedVariables: DemoForeverDB\n")
        with self.assertRaisesRegex(embed.EmbedError, "OptionalDeps"):
            self.run_embed()

    def test_an_addon_without_saved_variables_is_refused(self):
        self.toc("## OptionalDeps: ForeverCore\n## X-Forever-Core-Embed: 1\n")
        with self.assertRaisesRegex(embed.EmbedError, "SavedVariables"):
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
