import json
import shutil
import tempfile
import unittest
from pathlib import Path

from forever_sim import fetch, sync

PACKAGE = Path(__file__).resolve().parent.parent / "forever_sim"


class SyncTest(unittest.TestCase):
    def test_manifest_covers_subfolders_and_matches(self):
        manifest = json.loads((PACKAGE / "MANIFEST.json").read_text())
        self.assertEqual(manifest["package"], "forever_sim")
        self.assertIn("stubs/Questie/Questie.lua", manifest["files"])
        self.assertIn("stubs/Questie/Questie.toc", manifest["files"])
        self.assertEqual(sync.problems(PACKAGE, manifest["files"]), [])

    def test_an_edited_file_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "forever_sim"
            shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
            expected = json.loads((copy / "MANIFEST.json").read_text())["files"]
            (copy / "stubs" / "TomTom" / "TomTom.lua").write_text("-- edited\n")
            self.assertEqual(
                sync.problems(copy, expected), ["stubs/TomTom/TomTom.lua: changed (edit the producer, then run update)"]
            )

    def test_no_file_name_reads_as_a_credential(self):
        for name in json.loads((PACKAGE / "MANIFEST.json").read_text())["files"]:
            self.assertIsNone(sync.SECRET_WORDS.search(name), name)


class FetchTest(unittest.TestCase):
    def test_lua_strings_escape_quotes_backslashes_and_newlines(self):
        self.assertEqual(fetch.lua_string('a "b"\\\n'), '"a \\"b\\"\\\\\\n"')

    def test_client_tables_become_lua_data_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db2 = root / "db2" / fetch.BUILD
            db2.mkdir(parents=True)
            (db2 / "GlobalStrings.csv").write_text("ID,BaseTag,TagText_lang,Flags\n1,CANCEL,Cancel,1\n2,1BAD,x,1\n")
            (db2 / "GlobalColor.csv").write_text("ID,LuaConstantName,Color\n1,NORMAL_FONT_COLOR,-11776\n")
            (db2 / "UiTextureAtlasMember.csv").write_text(
                "CommittedName,ID,Width,Height,OverrideWidth,OverrideHeight\nPin-Big,1,32,32,0,48\n"
            )
            fetch.build_data(root, ["enUS"], offline=True)
            out = root / "data" / fetch.BUILD
            strings = (out / "globalstrings-enUS.lua").read_text()
            self.assertIn('["CANCEL"]="Cancel",', strings)
            self.assertNotIn("1BAD", strings)
            self.assertIn('{"NORMAL_FONT_COLOR",1.0000,0.8235,0.0000,1.0000},', (out / "globalcolors.lua").read_text())
            self.assertIn('["pin-big"]={32,48},', (out / "atlas.lua").read_text())

    def test_offline_refuses_to_download(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(SystemExit):
            fetch.db2(Path(directory), "GlobalStrings", offline=True, locale="deDE")


if __name__ == "__main__":
    unittest.main()
