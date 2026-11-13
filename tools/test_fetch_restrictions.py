"""Tests for the restriction pin generator in the skill pack's forever_sim/fetch.py."""

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "forever_fetch", ROOT / ".agents" / "skills" / "wow-forever-addon" / "tooling" / "forever_sim" / "fetch.py"
)
fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch)


class RestrictionClassesTest(unittest.TestCase):
    def test_only_protected_refuses_addon_code_at_any_time(self):
        self.assertEqual(fetch.restriction_classes("protected", "API:X"), ["always"])
        self.assertEqual(fetch.restriction_classes("nocombat", "API:X"), ["nocombat"])
        self.assertEqual(fetch.restriction_classes("hwevent", "API:X"), ["hwevent"])

    def test_a_tag_the_simulator_cannot_model_stays_untagged(self):
        # noscript blocks /run and loadstring, not the addon file code the sim runs; secureframe and restrictedframe
        # block a kind of frame the sim does not track.
        self.assertEqual(fetch.restriction_classes("noscript", "API:X"), ["untagged"])
        self.assertEqual(fetch.restriction_classes("secureframe", "API:X"), ["untagged"])
        self.assertEqual(fetch.restriction_classes("restrictedframe", "API:X"), ["untagged"])

    def test_a_combined_tag_keeps_every_class_it_can_model(self):
        # Any one of a name's classes refuses the call, so both survive a tag that names both.
        self.assertEqual(fetch.restriction_classes("nocombat,hwevent", "API:X"), ["nocombat", "hwevent"])
        self.assertEqual(fetch.restriction_classes("protected,hwevent", "API:X"), ["always", "hwevent"])
        # The unmodelled part of a combined tag does not turn a hardware-event call into an unconditional refusal.
        self.assertEqual(fetch.restriction_classes("hwevent,noscript", "API:X"), ["hwevent"])
        self.assertEqual(fetch.restriction_classes("hwevent,restrictedframe", "API:X"), ["hwevent"])
        self.assertEqual(fetch.restriction_classes("hwevent,nofreetrial", "API:X"), ["hwevent"])

    def test_a_state_tag_stays_untagged(self):
        self.assertEqual(fetch.restriction_classes("noinstance", "API:X"), ["untagged"])
        self.assertEqual(fetch.restriction_classes("grouponly", "API:X"), ["untagged"])

    def test_an_unknown_tag_fails_loudly(self):
        with self.assertRaisesRegex(SystemExit, "unknown restrictedapi class mystery"):
            fetch.restriction_classes("mystery", "API:X")

    def test_wiki_titles_for_a_function_and_a_widget_method(self):
        self.assertEqual(fetch.wiki_title("F", "C_Map.OpenWorldMap"), "API_C_Map.OpenWorldMap")
        self.assertEqual(fetch.wiki_title("F", "SetBindingSpell"), "API_SetBindingSpell")
        self.assertEqual(
            fetch.wiki_title("W", "SimpleScriptRegionAPI_SetPassThroughButtons"),
            "API_ScriptRegion_SetPassThroughButtons",
        )

    def test_the_committed_pin_covers_a_function_and_a_method(self):
        rows = self.rows()
        self.assertEqual(rows["C_Map.OpenWorldMap"], ["nocombat"])
        self.assertEqual(rows["SimpleScriptRegionAPI_SetPassThroughButtons"], ["nocombat"])
        self.assertEqual(rows["CopyToClipboard"], ["always"])
        self.assertIn(["untagged"], rows.values())

    def test_a_noscript_name_is_not_refused_to_addon_file_code(self):
        rows = self.rows()
        self.assertEqual(rows["C_FriendList.AddFriend"], ["untagged"])
        self.assertEqual(rows["DeleteCursorItem"], ["hwevent"])
        self.assertEqual(rows["C_AuctionHouse.PostItem"], ["hwevent"])

    def rows(self):
        pin = fetch.RESTRICTIONS.read_text(encoding="utf-8").splitlines()
        return {line.split()[0]: line.split()[1].split(",") for line in pin if line and not line.startswith("#")}


@unittest.skipUnless(shutil.which("luajit"), "needs luajit to read the SavedVariables chunk")
class ProbeTest(unittest.TestCase):
    """The blocks ForeverProbe recorded on the live client, read from its SavedVariables and merged into the pin."""

    def write_probe(self, directory: Path, hits: str) -> Path:
        path = directory / "ForeverProbe.lua"
        path.write_text("ForeverProbeBlockedDB = {\n\thits = {\n" + hits + "\n\t},\n}\n", encoding="utf-8")
        return path

    def test_a_blocked_call_is_named_the_way_the_sim_keys_it(self):
        # The event names a call as the client's own message does; a method's frame name is not its pin key.
        self.assertEqual(fetch.probe_name("C_UI.Reload()"), "C_UI.Reload")
        self.assertEqual(fetch.probe_name("OpenWorldMap()"), "OpenWorldMap")
        self.assertEqual(fetch.probe_name("SkillUpFrame:SetEnabled()"), "SetEnabled")
        self.assertIsNone(fetch.probe_name("()"))

    def test_the_class_comes_from_the_event_and_the_combat_state(self):
        self.assertEqual(fetch.probe_classes("ADDON_ACTION_BLOCKED", False), ["always"])
        self.assertEqual(fetch.probe_classes("ADDON_ACTION_BLOCKED", True), ["nocombat"])
        self.assertEqual(fetch.probe_classes("ADDON_ACTION_FORBIDDEN", False), ["hwevent"])
        self.assertEqual(fetch.probe_classes("MACRO_ACTION_FORBIDDEN", True), ["hwevent"])
        # DisplayInterfaceActionBlockedMessage is recorded with no arguments, so it names no call.
        self.assertIsNone(fetch.probe_classes("message", False))

    def test_an_always_block_outweighs_a_wiki_class(self):
        self.assertEqual(fetch.merge_classes(["untagged"], ["nocombat"]), ["nocombat"])
        self.assertEqual(fetch.merge_classes(["nocombat"], ["always"]), ["always"])
        self.assertEqual(fetch.merge_classes(["always"], ["nocombat"]), ["always"])
        self.assertEqual(fetch.merge_classes(["hwevent"], ["nocombat"]), ["nocombat", "hwevent"])
        self.assertEqual(fetch.merge_classes([], []), ["untagged"])

    def test_every_recorded_block_is_read_from_the_saved_variables(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_probe(
                Path(directory),
                "\t\t{ kind = 'ADDON_ACTION_BLOCKED', combat = false, args = { 'SkillUpForever', "
                "'SkillUpFrame:SetEnabled()' }, stack = '' },\n"
                "\t\t{ kind = 'ADDON_ACTION_BLOCKED', combat = true, args = { 'TweaksForever', 'C_UI.Reload()' } },\n"
                "\t\t{ kind = 'ADDON_ACTION_FORBIDDEN', combat = false, args = { 'CommoditiesForever', "
                "'C_TradeSkillUI.OpenTradeSkill()' } },\n"
                "\t\t{ kind = 'MACRO_ACTION_BLOCKED', combat = false, args = { 'UseAction()' } },\n"
                "\t\t{ kind = 'message', combat = false, args = {} },",
            )
            blocks = fetch.probe_blocks(path)
        self.assertEqual(
            blocks,
            {
                "SetEnabled": ["always"],
                "C_UI.Reload": ["nocombat"],
                "C_TradeSkillUI.OpenTradeSkill": ["hwevent"],
                "UseAction": ["always"],
            },
        )

    def test_the_merge_keeps_the_wikis_classes_and_adds_the_clients(self):
        merged = fetch.merge_probe(
            {"C_Map.OpenWorldMap": ["nocombat"], "CopyToClipboard": ["always"]},
            {"C_Map.OpenWorldMap": ["always"], "SetEnabled": ["always"]},
        )
        self.assertEqual(merged["C_Map.OpenWorldMap"], ["always"])
        self.assertEqual(merged["CopyToClipboard"], ["always"])
        self.assertEqual(merged["SetEnabled"], ["always"])

    def test_a_probe_names_the_file_it_could_not_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Broken.lua"
            path.write_text("this is not Lua", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "could not read the probe"):
                fetch.probe_blocks(path)


if __name__ == "__main__":
    unittest.main()
