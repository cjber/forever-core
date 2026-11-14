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
            self.write_atlas_tables(
                db2,
                "CommittedName,ID,UiTextureAtlasID,Width,Height,UiTextureAtlasElementID,OverrideWidth,OverrideHeight,"
                "UiCanvasID\nPin-Big,1,1,32,32,9,0,48,0\n",
                "Name,ID\nPin-Big,9\n",
            )
            fetch.build_data(root, ["enUS"], offline=True)
            out = root / "data" / fetch.BUILD
            strings = (out / "globalstrings-enUS.lua").read_text()
            self.assertIn('["CANCEL"]="Cancel",', strings)
            self.assertNotIn("1BAD", strings)
            self.assertIn('{"NORMAL_FONT_COLOR",1.0000,0.8235,0.0000,1.0000},', (out / "globalcolors.lua").read_text())
            self.assertIn('["pin-big"]={32,48},', (out / "atlas.lua").read_text())

    @staticmethod
    def write_atlas_tables(db2: Path, members: str, elements: str) -> None:
        (db2 / "UiCanvas.csv").write_text("ID,Width,Height\n1,1024,768\n2,2048,1536\n")
        (db2 / "UiTextureAtlas.csv").write_text(
            "ID,FileDataID,UiTextureAtlasSetID,AtlasWidth,AtlasHeight,UiCanvasID\n"
            "3944,1,1,512,512,1\n3945,2,1,1024,1024,2\n"
        )
        (db2 / "UiTextureAtlasMember.csv").write_text(members)
        (db2 / "UiTextureAtlasElement.csv").write_text(elements)

    def test_atlas_element_names_take_the_native_member_not_the_2x_one(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db2 = root / "db2" / fetch.BUILD
            db2.mkdir(parents=True)
            (db2 / "GlobalStrings.csv").write_text("ID,BaseTag,TagText_lang,Flags\n1,CANCEL,Cancel,1\n")
            (db2 / "GlobalColor.csv").write_text("ID,LuaConstantName,Color\n1,NORMAL_FONT_COLOR,-11776\n")
            self.write_atlas_tables(
                db2,
                "CommittedName,ID,UiTextureAtlasID,Width,Height,UiTextureAtlasElementID,OverrideWidth,OverrideHeight,"
                "UiCanvasID\n"
                "UI-HUD-Minimap-Frame-Cycle-c60,2,3944,42,42,9,0,0,0\n"
                "UI-HUD-Minimap-Frame-Cycle-c60-2x,3,3945,84,84,9,0,0,0\n",
                "Name,ID\nUI-HUD-Minimap-Frame-Cycle,9\n",
            )
            fetch.build_data(root, ["enUS"], offline=True)
            atlas = (root / "data" / fetch.BUILD / "atlas.lua").read_text()
            self.assertIn('["ui-hud-minimap-frame-cycle"]={42,42},', atlas)
            self.assertIn('["ui-hud-minimap-frame-cycle-c60-2x"]={42,42},', atlas)

    def test_a_stale_atlas_cache_is_rebuilt_from_the_element_table(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db2 = root / "db2" / fetch.BUILD
            db2.mkdir(parents=True)
            (db2 / "GlobalStrings.csv").write_text("ID,BaseTag,TagText_lang,Flags\n1,CANCEL,Cancel,1\n")
            (db2 / "GlobalColor.csv").write_text("ID,LuaConstantName,Color\n1,NORMAL_FONT_COLOR,-11776\n")
            self.write_atlas_tables(
                db2,
                "CommittedName,ID,UiTextureAtlasID,Width,Height,UiTextureAtlasElementID,OverrideWidth,OverrideHeight,"
                "UiCanvasID\nPin-Big,1,1,32,32,9,0,48,0\n",
                "Name,ID\nPin-Big,9\n",
            )
            out = root / "data" / fetch.BUILD
            out.mkdir(parents=True)
            (out / "atlas.lua").write_text("return {\n}\n")
            fetch.build_data(root, ["enUS"], offline=True)
            atlas = (out / "atlas.lua").read_text()
            self.assertTrue(atlas.startswith(fetch.ATLAS_MARKER))
            self.assertIn('["pin-big"]={32,48},', atlas)

    def test_a_stale_atlas_cache_without_inputs_fails_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db2 = root / "db2" / fetch.BUILD
            db2.mkdir(parents=True)
            (db2 / "GlobalStrings.csv").write_text("ID,BaseTag,TagText_lang,Flags\n1,CANCEL,Cancel,1\n")
            (db2 / "GlobalColor.csv").write_text("ID,LuaConstantName,Color\n1,NORMAL_FONT_COLOR,-11776\n")
            out = root / "data" / fetch.BUILD
            out.mkdir(parents=True)
            (out / "atlas.lua").write_text("return {\n}\n")
            with self.assertRaises(SystemExit) as raised:
                fetch.build_data(root, ["enUS"], offline=True)
            self.assertIn("without --offline", str(raised.exception))

    def test_offline_refuses_to_download(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(SystemExit):
            fetch.db2(Path(directory), "GlobalStrings", offline=True, locale="deDE")


if __name__ == "__main__":
    unittest.main()
