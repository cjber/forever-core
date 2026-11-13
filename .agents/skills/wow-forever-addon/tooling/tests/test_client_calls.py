import tempfile
import unittest
from pathlib import Path

from forever_tools import client_calls

ENVIRONMENT = client_calls.Environment(
    api=frozenset({"C_Map.GetBestMapForUnit", "C_Item.GetItemIconByID", "GetTime"}),
    globals=frozenset({"print", "pairs", "_G", "Enum", "os"}),
    defined=frozenset({"MyAddon", "MyFrame"}),
)


def codes(source, environment=ENVIRONMENT):
    return [message.split(":", 1)[0] for _, message in client_calls.check(source, environment)]


class ClientCallsTest(unittest.TestCase):
    def test_a_documented_c_namespace_read_passes(self):
        for source in (
            "local map = C_Map.GetBestMapForUnit('player')\n",
            "local f = C_Map.GetBestMapForUnit\n",
            "local f = C_Map['GetBestMapForUnit']\n",
            "if not C_Map.GetBestMapForUnit then return end\n",
        ):
            with self.subTest(source=source):
                self.assertEqual(codes(source), [])

    def test_a_missing_c_namespace_read_fails(self):
        for source in (
            "C_Retail.Only()\n",
            "local f = C_Retail.Only\n",
            "local f = C_Retail['Only']\n",
            "if C_Retail.Only then return end\n",
        ):
            with self.subTest(source=source):
                self.assertEqual(codes(source), ["client-missing"])

    def test_a_call_of_a_known_global_passes(self):
        for source in (
            "print(GetTime())\n",
            "MyAddon()\n",
            "local value = Enum.Foo.Bar\n",
        ):
            with self.subTest(source=source):
                self.assertEqual(codes(source), [])

    def test_a_call_of_an_undefined_global_fails(self):
        for source in (
            "SomeRetailOnly()\n",
            "SomeRetailOnly(1, 2)\n",
            "SomeRetailOnly { key = 1 }\n",
            'SomeRetailOnly "text"\n',
            "DefinedHere = 1\nSomeRetailOnly(DefinedHere)\n",
            "local value = SomeRetailOnly(1)\n",
        ):
            with self.subTest(source=source):
                self.assertEqual(codes(source), ["client-missing"])

    def test_a_plain_read_of_a_global_is_not_a_call(self):
        for source in (
            "local value = SomeRetailOnly\n",
            "local faction = LE_PARTY_CATEGORY_HOME\n",
            "if SomeTable then return end\n",
            "local width = SomeTable.Width\n",
            "SomeTable.Field = 1\n",
            "local why = { name = 'SomeTable' }\n",
        ):
            with self.subTest(source=source):
                self.assertEqual(codes(source), [])

    def test_a_method_call_reads_a_table_not_the_global_function(self):
        for source in (
            "SomeTable:Method()\n",
            "UIParent:GetWidth()\n",
            "if SomeTable then SomeTable:Open() end\n",
        ):
            with self.subTest(source=source):
                self.assertEqual(codes(source), [])

    def test_a_local_is_not_a_global_read(self):
        for source in (
            "local x = 1\nprint(x)\n",
            "local x, y = 1, 2\nprint(x, y)\n",
            "for i = 1, 3 do print(i) end\n",
            "for k, v in pairs({}) do print(k, v) end\n",
            "local function helper() return helper end\n",
            "local _, ns = ...\nfunction ns:Method() return self.value end\n",
        ):
            with self.subTest(source=source):
                self.assertEqual(codes(source), [])

    def test_a_waiver_excuses_one_line_and_must_excuse_something(self):
        self.assertEqual(codes("SomeRetailOnly() -- client-ok: retail feature check\n"), [])
        self.assertEqual(codes("-- client-ok: retail feature check\nSomeRetailOnly()\n"), [])
        self.assertEqual(codes("local x = 1 -- client-ok: nothing here\n"), ["client-waiver-unused"])
        self.assertEqual(codes("SomeRetailOnly() -- client-ok:\n"), ["client-missing", "client-waiver-unused"])

    def test_malformed_lua_raises(self):
        with self.assertRaises(client_calls.LuaSyntaxError):
            client_calls.check("if x then\n", ENVIRONMENT)


class DefinitionsTest(unittest.TestCase):
    def test_global_assignments_and_named_frames_are_definitions(self):
        source = """
function PlainFunction() end
function Table.Field() end
Value = 1
_G.Bracketed = 2
_G["Quoted"] = 3
CreateFrame("Frame", "NamedFrame", nil)
local LocalValue = 1
local function LocalFunction() end
Holder.Field = 4
local t = { Key = 5 }
"""
        self.assertEqual(
            client_calls.definitions(source),
            frozenset({"PlainFunction", "Value", "Bracketed", "Quoted", "NamedFrame"}),
        )

    def test_a_multi_assignment_defines_every_target(self):
        self.assertEqual(client_calls.definitions("First, Second = 1, 2\n"), frozenset({"First", "Second"}))

    def test_the_generator_reads_the_function_definitions(self):
        found = client_calls.analysis(
            "function PlainFunction() end\nValue = function() end\nTable = {}\nCreateFrame('Frame', 'Named')\n"
        )
        self.assertEqual(found.functions, frozenset({"PlainFunction", "Value"}))

    def test_a_forevercore_helper_names_the_frame_it_builds(self):
        for source, name in (
            ('ForeverCore.TrackerSection.Create("MySection", nil, {})\n', "MySection"),
            ('ForeverCore.QuestLogTabs.Register("mine", { name = "MyTab", panel = panel })\n', "MyTab"),
            ('ForeverCore.MinimapButton.Create({ name = "MyButton" })\n', "MyButton"),
        ):
            with self.subTest(source=source):
                self.assertEqual(client_calls.definitions(source), frozenset({name}))

    def test_another_function_naming_a_frame_is_not_a_definition(self):
        for source in (
            'OtherAddon.Create("MyFrame")\n',
            'ForeverCore.ReportFor("MyFrame", {})\n',
            'SomeCall({ name = "MyFrame" })\n',
            'ForeverCore.TrackerSection.Create(nil, "MyFrame")\n',
            "local spec = { name = 'MyFrame' }\nForeverCore.MinimapButton.Create(spec)\n",
        ):
            with self.subTest(source=source):
                self.assertEqual(client_calls.definitions(source), frozenset())

    def test_xml_names_skip_virtual_frames_but_keep_virtual_fonts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Ui.xml"
            path.write_text(
                '<Ui><Frame name="Named"/><Frame name="Template" virtual="true"/>'
                '<Font name="GameFontNormal" virtual="true"/><Frame name="$parentChild"/></Ui>'
            )
            self.assertEqual(client_calls.xml_definitions([path]), frozenset({"Named", "GameFontNormal"}))

    def test_saved_variables_are_definitions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Addon.toc"
            path.write_text("## Interface: 16001\n## SavedVariables: One, Two\n## SavedVariablesPerCharacter: Three\n")
            self.assertEqual(client_calls.saved_variables([path]), frozenset({"One", "Two", "Three"}))


class OptionalDeclarationTest(unittest.TestCase):
    def findings(self, root, optional_deps, declarations=None, runtime=""):
        toc = "## Interface: 16001\n## Dependencies: ForeverCore\n"
        if optional_deps is not None:
            toc += f"## OptionalDeps: {optional_deps}\n"
        (root / "Addon.toc").write_text(toc + "Core.lua\n")
        (root / "Core.lua").write_text(runtime)
        if declarations is not None:
            (root / "tools").mkdir(exist_ok=True)
            (root / "tools" / "client_optional.txt").write_text(declarations)
        (root / "client_names.txt").write_text("# generated\nC_Map.GetBestMapForUnit\n")
        paths, environment = client_calls.environment(
            root, annotations=root / "annotations", api=root / "client_names.txt"
        )
        return [(path.name, line, message) for path, line, message in client_calls.findings(root, paths, environment)]

    def test_a_declared_optional_global_may_be_called(self):
        with tempfile.TemporaryDirectory() as directory:
            found = self.findings(
                Path(directory),
                optional_deps="Questie, RXPGuides",
                declarations="LibStub  RXPGuides\n",
                runtime='local pins = LibStub("HereBeDragons-Pins-2.0", true)\n',
            )
            self.assertEqual(found, [])

    def test_a_folder_the_toc_does_not_list_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            found = self.findings(
                Path(directory),
                optional_deps="Questie",
                declarations="LibStub  RXPGuides\n",
                runtime='LibStub("HereBeDragons-Pins-2.0", true)\n',
            )
            self.assertEqual([message.split(":", 1)[0] for _, _, message in found], ["client-optional-folder"])

    def test_a_declared_name_the_addon_never_calls_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            found = self.findings(Path(directory), optional_deps="Questie", declarations="Questie  Questie\n")
            self.assertEqual([message.split(":", 1)[0] for _, _, message in found], ["client-optional-unused"])

    def test_a_malformed_declaration_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            found = self.findings(Path(directory), optional_deps="Questie", declarations="Questie\n")
            self.assertEqual([message.split(":", 1)[0] for _, _, message in found], ["client-optional-format"])

    def test_a_comment_and_a_blank_line_are_not_declarations(self):
        with tempfile.TemporaryDirectory() as directory:
            found = self.findings(
                Path(directory),
                optional_deps="Questie",
                declarations="# optional globals\n\nQuestie  Questie",
                runtime="Questie()\n",
            )
            self.assertEqual(found, [])

    def test_without_the_file_nothing_is_declared(self):
        with tempfile.TemporaryDirectory() as directory:
            found = self.findings(Path(directory), optional_deps=None, runtime='LibStub("x")\n')
            self.assertEqual([message.split(":", 1)[0] for _, _, message in found], ["client-missing"])


class EnvironmentTest(unittest.TestCase):
    def test_a_toc_load_graph_supplies_the_runtime_files_and_definitions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Addon.toc").write_text("## SavedVariables: AddonDB\nCore.lua\nUi.xml\n")
            (root / "Core.lua").write_text("AddonGlobal = {}\nlocal localOnly = 1\n")
            (root / "Ui.xml").write_text('<Ui><Script file="Quests.lua"/><Frame name="AddonFrame"/></Ui>')
            (root / "Quests.lua").write_text("function AddonGlobal:Open() end\n")
            annotations = root / "annotations"
            (annotations / "Annotations" / "Core" / "Lua").mkdir(parents=True)
            (annotations / "Annotations" / "Core" / "Data").mkdir(parents=True)
            (annotations / "Annotations" / "Core" / "Lua" / "compat.lua").write_text("wipe = table.wipe\n")
            (annotations / "Annotations" / "Core" / "Data" / "Enum.lua").write_text("Enum = {}\nConstants = {}\n")
            api = root / "client_names.txt"
            api.write_text("# generated\nC_Map.GetBestMapForUnit\n")
            (root / "tools").mkdir()
            (root / "tools" / "client_optional.txt").write_text("LibStub  LibStub\n")
            paths, environment = client_calls.environment(root, annotations=annotations, api=api)
            self.assertEqual([path.name for path in paths], ["Core.lua", "Quests.lua"])
            self.assertEqual(environment.api, frozenset({"C_Map.GetBestMapForUnit"}))
            self.assertEqual(environment.defined, frozenset({"AddonGlobal", "AddonDB", "AddonFrame"}))
            self.assertEqual(environment.optional, frozenset({"LibStub"}))
            self.assertTrue({"wipe", "Enum", "Constants", "os", "coroutine", "debug"} <= environment.globals)


if __name__ == "__main__":
    unittest.main()
