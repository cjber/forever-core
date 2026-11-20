import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from forever_sim import fetch, gen_client_surface, gen_undocumented_returns, sync

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
            self.write_flyout_and_item_tables(db2)
            fetch.build_data(root, ["enUS"], offline=True)
            out = root / "data" / fetch.BUILD
            strings = (out / "globalstrings-enUS.lua").read_text()
            self.assertIn('["CANCEL"]="Cancel",', strings)
            self.assertNotIn("1BAD", strings)
            self.assertIn('{"NORMAL_FONT_COLOR",1.0000,0.8235,0.0000,1.0000},', (out / "globalcolors.lua").read_text())
            self.assertIn('["pin-big"]={32,48},', (out / "atlas.lua").read_text())
            self.assertEqual(
                (out / "items-enUS.lua").read_text(),
                'return {\nitems = {\n[25]={"Worn \\"Short\\" Sword",1,7,2,1,2,7,21,135274,1,0,0,0,""},\n},\n'
                'classes = {\n[2]={name="Weapon",subs={[0]="Axe",[7]="Sword"}},\n},\n}\n',
            )
            self.assertEqual(
                (out / "flyouts.lua").read_text(),
                'return {\n[7]={name="Stances",description="Choose a stance",slots={2457,71}},\n'
                '[8]={name="Empty",description="No spells",slots={}},\n}\n',
            )

    @staticmethod
    def write_flyout_and_item_tables(db2: Path) -> None:
        (db2 / "Item.csv").write_text(
            "ID,ClassID,SubclassID,InventoryType,IconFileDataID\n25,2,7,21,135274\n26,2,7,21,1\n"
        )
        # Item 26 has no name in ItemSparse, so the client shows nothing for it.
        (db2 / "ItemSparse.csv").write_text(
            "ID,Display_lang,OverallQualityID,SellPrice,ItemLevel,Stackable,RequiredLevel,Bonding,ExpansionID,ItemSet,"
            'Description_lang\n25,"Worn ""Short"" Sword",1,7,2,1,1,0,0,0,\n26,,1,1,1,1,1,0,0,0,\n'
        )
        (db2 / "ItemClass.csv").write_text("ID,ClassName_lang,ClassID\n3,Weapon,2\n")
        (db2 / "ItemSubClass.csv").write_text("DisplayName_lang,ClassID,SubClassID\nSword,2,7\nAxe,2,0\n")
        (db2 / "SpellFlyout.csv").write_text(
            "ID,Name_lang,Description_lang\n7,Stances,Choose a stance\n8,Empty,No spells\n"
        )
        # The DB2 row order is not the slot order.
        (db2 / "SpellFlyoutItem.csv").write_text("ID,SpellID,Slot,SpellFlyoutID\n1,71,1,7\n2,2457,0,7\n")

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
            self.write_flyout_and_item_tables(db2)
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
            self.write_flyout_and_item_tables(db2)
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


class ClientSurfaceTest(unittest.TestCase):
    DUMP = """ForeverProbeDB = { clientSurface = { build = 16001,
  cvars = { userFontScale = { default = "1" }, odd = { default = 'a"b\\\\c\\nd' },
    tab = { default = "p\\vq\\194\\133r" }, hidden = { default = "<secret>" },
    valueOnly = { value = "7" } },
  scripts = { FontString = { "OnEnter", "OnLeave" }, Frame = { "OnEvent" } },
  undefinedCvars = { "gone" },
  failedWidgets = { ModelSceneActor = "no actor", Foo = "bad \\"Interface\\\\Foo\\"" } } }
"""

    def test_a_dump_becomes_lua_the_simulator_reads_back_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "ForeverProbe.lua"
            dump.write_text(self.DUMP)
            out = Path(directory) / "client_surface.lua"
            out.write_text(gen_client_surface.render(*gen_client_surface.read(dump)))
            check = (
                f'local t = dofile("{out}"); assert(t.interface == 16001); '
                'assert(t.cvars.userFontScale == "1"); assert(t.cvars.odd == "a\\"b\\\\c\\nd"); '
                'assert(t.cvars.hidden == nil, "a secret default is left out"); assert(t.undefined[1] == "gone"); '
                'assert(t.cvars.valueOnly == "7", "no default: the reported value"); '
                'assert(t.scripts.FontString[1] == "OnEnter"); assert(t.unmade.ModelSceneActor == "no actor"); '
                'assert(t.cvars.tab == "p\\vq\\194\\133r", "control and non-ASCII bytes survive"); '
                'assert(t.unmade.Foo == "bad \\"Interface\\\\Foo\\"", "an error with a backslash survives")'
            )
            subprocess.run(["luajit", "-e", check], check=True)

    def test_a_dump_without_the_record_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "ForeverProbe.lua"
            dump.write_text("ForeverProbeDB = {}\n")
            with self.assertRaises(SystemExit):
                gen_client_surface.read(dump)

    def test_a_dump_with_a_failed_half_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / "ForeverProbe.lua"
            dump.write_text(self.DUMP.replace("build = 16001,", 'build = 16001, errors = { cvars = "boom" },'))
            with self.assertRaises(SystemExit):
                gen_client_surface.read(dump)


class UndocumentedReturnsTest(unittest.TestCase):
    def test_only_called_undocumented_functions_take_the_annotated_returns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            addons = root / "ui" / "Interface" / "AddOns"
            (addons / "Blizzard_APIDocumentationGenerated").mkdir(parents=True)
            (addons / "Blizzard_APIDocumentationGenerated" / "PetDocumentation.lua").write_text(
                'local P = { Namespace = "C_PetJournal", Functions = {\n'
                '{\n\tName = "GetNumPetTypes",\n\tType = "Function",\n} } }\n'
            )
            (addons / "Blizzard_Collections").mkdir()
            (addons / "Blizzard_Collections" / "Pets.lua").write_text(
                "local a, b = C_PetJournal.GetNumPets()\nC_PetJournal.GetNumPetTypes()\nC_Foo.Missing()\n"
            )
            (root / "ann" / "Annotations").mkdir(parents=True)
            (root / "ann" / "Annotations" / "Wiki.lua").write_text(
                "---@return number numPets\n---@return number numOwned\nfunction C_PetJournal.GetNumPets() end\n"
                "---@return number n\nfunction C_PetJournal.GetNumPetTypes() end\n"
                "---@return string? name\n---@return Enum.ItemQuality q\n---@return Foo[] list\n"
                "function C_PetJournal.Unused() end\n"
            )
            returns = gen_undocumented_returns.read(root / "ann", root / "ui")
            self.assertEqual(returns, {"C_PetJournal.GetNumPets": [("number", False), ("number", False)]})
            self.assertEqual(gen_undocumented_returns.doc_type("string?"), ("string", True))
            self.assertEqual(gen_undocumented_returns.doc_type("Enum.ItemQuality"), ("ItemQuality", False))
            self.assertEqual(gen_undocumented_returns.doc_type("Foo[]"), ("table", False))
            out = root / "returns.lua"
            out.write_text(gen_undocumented_returns.render(returns))
            check = f'local t = dofile("{out}"); assert(#t["C_PetJournal.GetNumPets"] == 2)'
            subprocess.run(["luajit", "-e", check], check=True)


if __name__ == "__main__":
    unittest.main()
