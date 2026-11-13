"""Tests for tools/gen_forever_api.py over a small fixture tree, with no network.

The committed `client_names.txt` is compared with a fresh generation when the pinned Blizzard UI source is checked out
(`tools/typecheck.sh` fetches it to `.types/blizzard-ui`), the way test_gen_widget_methods.py checks its own data.
"""

import tempfile
import unittest
from pathlib import Path

import gen_forever_api
from forever_sim.fetch import BUILD, UI_REVISION

ROOT = Path(__file__).resolve().parent.parent
COMMITTED = ROOT / ".agents" / "skills" / "wow-forever-addon" / "tooling" / "forever_tools" / "client_names.txt"
COMMITTED_PROBE = ROOT / "tools" / "forever_probe_api.lua"
COMMITTED_BUILD = "1.60.1.70938"
UI_CHECKOUTS = (
    ROOT / ".types" / "blizzard-ui" / "wow-ui-source",
    ROOT / "tools" / ".cache" / "forever_sim" / "wow-ui-source",
)
UI = next((path for path in UI_CHECKOUTS if (path / gen_forever_api.DOCUMENTATION).is_dir()), None)

DOCUMENTATION = """local Test =
{
\tName = "Test",
\tType = "System",
\tNamespace = "C_Test",
\tFunctions =
\t{
\t\t{ Name = "Works", Type = "Function" },
\t},
};
APIDocumentation:AddDocumentationTable(Test);

local GlobalTest =
{
\tName = "GlobalTest",
\tType = "System",
\tFunctions =
\t{
\t\t{ Name = "GlobalWorks", Type = "Function" },
\t},
};
APIDocumentation:AddDocumentationTable(GlobalTest);
"""
TOC = "TestDocumentation.lua\n"
LUA = """
function TestHelper() end
GlobalTable = {}
CreateFrame("Frame", "NamedByLua")
CalledGlobal(1)
local best = C_Test.FromUi()
local localOnly = 1
local width = SomeClientConstant
"""
XML = '<Ui><Frame name="NamedByXml"/><Frame name="Template" virtual="true"/></Ui>'
PROBE = """ForeverProbeDB =
{
\t["api"] =
\t{
\t\t["build"] = "9.9.9.99999",
\t\t["globals"] =
\t\t{
\t\t\t"ProbeGlobal",
\t\t},
\t\t["namespaces"] =
\t\t{
\t\t\t["C_Probe"] =
\t\t\t{
\t\t\t\t"Thing",
\t\t\t},
\t\t},
\t},
}
"""


class GeneratorTest(unittest.TestCase):
    def fixture(self, root):
        ui = root / "ui"
        documents = ui / "Interface" / "AddOns" / "Blizzard_APIDocumentationGenerated"
        documents.mkdir(parents=True)
        (documents / "Blizzard_APIDocumentationGenerated.toc").write_text(TOC)
        (documents / "TestDocumentation.lua").write_text(DOCUMENTATION)
        framexml = ui / "Interface" / "AddOns" / "Blizzard_FrameXML"
        framexml.mkdir(parents=True)
        (framexml / "Test.lua").write_text(LUA)
        (framexml / "Test.xml").write_text(XML)
        return ui

    def generate(self, root, *extra):
        ui = self.fixture(root)
        out = root / "client_names.txt"
        code = gen_forever_api.main(["--ui", str(ui), "--offline", "--out", str(out), *extra])
        self.assertEqual(code, 0)
        return ui, out

    def names(self, text):
        return [line for line in text.splitlines() if line and not line.startswith("#")]

    def test_every_callable_source_is_written_sorted_with_the_pinned_header(self):
        with tempfile.TemporaryDirectory() as directory:
            _, out = self.generate(Path(directory))
            text = out.read_text()
        self.assertIn(UI_REVISION, text)
        self.assertIn(BUILD, text)
        names = self.names(text)
        self.assertEqual(names, sorted(names))
        for name in (
            "C_Test.Works",
            "GlobalWorks",
            "TestHelper",
            "CalledGlobal",
            "C_Test.FromUi",
        ):
            with self.subTest(name=name):
                self.assertIn(name, names)
        for name in ("GlobalTable", "NamedByLua", "NamedByXml", "SomeClientConstant", "Template", "localOnly"):
            with self.subTest(name=name):
                self.assertNotIn(name, names)

    def test_the_committed_probe_table_is_merged_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            _, out = self.generate(Path(directory))
            text = out.read_text()
        self.assertEqual(gen_forever_api.PROBE, COMMITTED_PROBE)
        self.assertIn(f"Merged with a ForeverProbe dump from build {COMMITTED_BUILD}", text)
        names = self.names(text)
        self.assertIn("C_ItemInteraction.ClearPendingItem", names)

    def test_a_probe_dump_merges_its_build_and_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            probe = root / "ForeverProbe.lua"
            probe.write_text(PROBE)
            _, out = self.generate(root, "--probe", str(probe))
            text = out.read_text()
        self.assertIn("9.9.9.99999", text)
        self.assertNotIn(COMMITTED_BUILD, text)
        self.assertIn("ProbeGlobal", self.names(text))
        self.assertIn("C_Probe.Thing", self.names(text))

    def test_check_passes_on_a_fresh_file_and_fails_on_an_edited_one(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ui, out = self.generate(root)
            self.assertEqual(gen_forever_api.main(["--ui", str(ui), "--offline", "--out", str(out), "--check"]), 0)
            edited = out.read_text().replace("TestHelper", "HandEdited")
            out.write_text(edited)
            self.assertEqual(gen_forever_api.main(["--ui", str(ui), "--offline", "--out", str(out), "--check"]), 1)
            self.assertEqual(out.read_text(), edited)


@unittest.skipUnless(UI is not None, "the pinned Blizzard UI source is not checked out")
class CommittedDataTest(unittest.TestCase):
    def test_the_committed_file_is_a_fresh_generation(self):
        self.assertEqual(
            gen_forever_api.main(["--ui", str(UI), "--offline", "--out", str(COMMITTED), "--check"]),
            0,
            "client_names.txt is stale; run: python3 tools/gen_forever_api.py",
        )


if __name__ == "__main__":
    unittest.main()
