"""Tests for the restriction pin generator in the skill pack's forever_sim/fetch.py."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "forever_fetch", ROOT / ".agents" / "skills" / "wow-forever-addon" / "tooling" / "forever_sim" / "fetch.py"
)
fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch)


class RestrictionClassTest(unittest.TestCase):
    def test_only_protected_refuses_addon_code_at_any_time(self):
        self.assertEqual(fetch.restriction_class("protected", "API:X"), "always")
        self.assertEqual(fetch.restriction_class("nocombat", "API:X"), "nocombat")
        self.assertEqual(fetch.restriction_class("hwevent", "API:X"), "hwevent")

    def test_a_tag_the_simulator_cannot_model_stays_untagged(self):
        # noscript blocks /run and loadstring, not the addon file code the sim runs; secureframe and restrictedframe
        # block a kind of frame the sim does not track.
        self.assertEqual(fetch.restriction_class("noscript", "API:X"), "untagged")
        self.assertEqual(fetch.restriction_class("secureframe", "API:X"), "untagged")
        self.assertEqual(fetch.restriction_class("restrictedframe", "API:X"), "untagged")

    def test_a_combined_tag_takes_the_strongest_modelled_class(self):
        # The unmodelled part of a combined tag does not turn a hardware-event call into an unconditional refusal.
        self.assertEqual(fetch.restriction_class("hwevent,noscript", "API:X"), "hwevent")
        self.assertEqual(fetch.restriction_class("hwevent,restrictedframe", "API:X"), "hwevent")
        self.assertEqual(fetch.restriction_class("hwevent,nofreetrial", "API:X"), "hwevent")
        self.assertEqual(fetch.restriction_class("protected,hwevent", "API:X"), "always")

    def test_a_state_tag_stays_untagged(self):
        self.assertEqual(fetch.restriction_class("noinstance", "API:X"), "untagged")
        self.assertEqual(fetch.restriction_class("grouponly", "API:X"), "untagged")

    def test_an_unknown_tag_fails_loudly(self):
        with self.assertRaisesRegex(SystemExit, "unknown restrictedapi class mystery"):
            fetch.restriction_class("mystery", "API:X")

    def test_wiki_titles_for_a_function_and_a_widget_method(self):
        self.assertEqual(fetch.wiki_title("F", "C_Map.OpenWorldMap"), "API_C_Map.OpenWorldMap")
        self.assertEqual(fetch.wiki_title("F", "SetBindingSpell"), "API_SetBindingSpell")
        self.assertEqual(
            fetch.wiki_title("W", "SimpleScriptRegionAPI_SetPassThroughButtons"),
            "API_ScriptRegion_SetPassThroughButtons",
        )

    def test_the_committed_pin_covers_a_function_and_a_method(self):
        pin = fetch.RESTRICTIONS.read_text(encoding="utf-8").splitlines()
        rows = {line.split()[0]: line.split()[1] for line in pin if line and not line.startswith("#")}
        self.assertEqual(rows["C_Map.OpenWorldMap"], "nocombat")
        self.assertEqual(rows["SimpleScriptRegionAPI_SetPassThroughButtons"], "nocombat")
        self.assertEqual(rows["CopyToClipboard"], "always")
        self.assertIn("untagged", set(rows.values()))

    def test_a_noscript_name_is_not_refused_to_addon_file_code(self):
        pin = fetch.RESTRICTIONS.read_text(encoding="utf-8").splitlines()
        rows = {line.split()[0]: line.split()[1] for line in pin if line and not line.startswith("#")}
        self.assertEqual(rows["C_FriendList.AddFriend"], "untagged")
        self.assertEqual(rows["DeleteCursorItem"], "hwevent")
        self.assertEqual(rows["C_AuctionHouse.PostItem"], "hwevent")


if __name__ == "__main__":
    unittest.main()
