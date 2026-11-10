"""Tests for the shared asset blacklist's FileDataID age rule."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents/skills/wow-forever-addon/tooling"))
import gen_legacy_chrome  # noqa: E402
from forever_tools import assets, legacy_chrome  # noqa: E402


class LegacyChromeAgeTest(unittest.TestCase):
    def messages(self, value):
        return [message for _, message in assets.check(f'local texture = "{value}"')]

    def test_a_banned_legacy_path_fails(self):
        messages = self.messages("Interface\\TargetingFrame\\UI-StatusBar")
        self.assertIn(
            "asset-blacklist: interface/targetingframe/ui-statusbar: "
            "pre-Legion UI chrome (FileDataID < 1000000); use an atlas",
            messages,
        )

    def test_a_named_family_path_gets_the_age_message_too(self):
        messages = self.messages("Interface\\Buttons\\UI-Panel-Button-Up")
        self.assertIn(
            "asset-blacklist: interface/buttons/ui-panel-button-up: "
            "pre-Legion UI chrome (FileDataID < 1000000); use an atlas",
            messages,
        )

    def test_a_banned_path_is_case_and_slash_insensitive(self):
        messages = self.messages("INTERFACE/TARGETINGFRAME/UI-STATUSBAR.TGA")
        self.assertTrue(any("pre-Legion UI chrome" in message for message in messages))

    def test_an_exempt_content_icon_passes(self):
        self.assertEqual(self.messages("Interface\\Icons\\INV_Misc_QuestionMark"), [])

    def test_a_modern_client_texture_passes(self):
        self.assertEqual(self.messages("Interface\\Minimap\\UI-BonusObjectiveBlob-Outside"), [])

    def test_minimap_tracking_icons_fail_with_their_atlas(self):
        messages = self.messages("Interface\\Minimap\\Tracking\\Repair")
        self.assertEqual(
            messages,
            [
                "asset-blacklist: interface/minimap/tracking/repair: "
                "pre-Legion UI chrome (FileDataID < 1000000); use the Repair atlas of the same name instead"
            ],
        )
        self.assertIn("use the Banker atlas of the same name", self.messages("Interface/Minimap/Tracking/Banker")[0])
        self.assertIn("use the BattleMaster atlas", self.messages("Interface/Minimap/Tracking/BattleMaster")[0])

    def test_map_content_and_client_slot_art_stay_exempt(self):
        for value in (
            "Interface\\Minimap\\UI-QuestBlobMinimap-Inside",
            "Interface\\Minimap\\ObjectIcons",
            "Interface\\Minimap\\POIIcons",
            "Interface\\Minimap\\Ping\\Ping2",
            "Interface\\Minimap\\UI-Minimap-Ping-Expand",
            "Interface\\PaperDoll\\UI-PaperDoll-Slot-Head",
            "Interface\\Minimap\\Minimap_Chest_Elite",
        ):
            with self.subTest(value=value):
                self.assertEqual(self.messages(value), [])

    def test_minimap_chrome_stays_under_the_age_rule(self):
        messages = self.messages("Interface\\Minimap\\UI-Minimap-Border")
        self.assertTrue(any("pre-Legion UI chrome" in message for message in messages))

    def test_libdbicon_minimap_pieces_are_allowlisted_but_tracking_still_fails(self):
        for value in (
            "Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight",
            "Interface\\Minimap\\Minimap-TrackingBorder",
            "Interface\\Minimap\\UI-Minimap-Background",
        ):
            with self.subTest(value=value):
                self.assertEqual(self.messages(value), [])
        messages = self.messages("Interface\\Minimap\\Tracking\\Repair")
        self.assertTrue(any("use the Repair atlas of the same name instead" in message for message in messages))

    def test_an_allowlisted_raid_target_icon_passes(self):
        for name in ("UI-RaidTargetingIcon_1", "UI-RaidTargetingIcons"):
            with self.subTest(name=name):
                self.assertEqual(self.messages(f"Interface\\TargetingFrame\\{name}"), [])

    def test_an_atlas_name_passes(self):
        self.assertEqual(assets.check('texture:SetAtlas("common-dropdown-bg")'), [])

    def test_an_unresolvable_interface_path_fails(self):
        messages = self.messages("Interface\\Buttons\\NoSuchTexture")
        self.assertTrue(any("unverifiable client path" in message for message in messages))

    def test_inline_markup_reports_the_path_not_the_markup(self):
        messages = self.messages("|TInterface/TargetingFrame/UI-StatusBar:16|t")
        self.assertEqual(
            messages,
            [
                "asset-blacklist: interface/targetingframe/ui-statusbar: "
                "pre-Legion UI chrome (FileDataID < 1000000); use an atlas"
            ],
        )

    def test_an_addons_own_media_path_is_not_a_client_path(self):
        self.assertEqual(self.messages("Interface\\AddOns\\SomeAddon\\media\\Icon"), [])

    def test_a_constant_prefix_of_a_known_path_is_not_called_a_typo(self):
        self.assertEqual(self.messages("Interface\\WorldMap\\ShadowfangKeep\\ShadowfangKeep1"), [])

    def test_a_backdrop_global_gets_the_age_rule_for_the_files_it_draws(self):
        messages = [message for _, message in assets.check("f:SetBackdrop(BACKDROP_TOAST_12_12)")]
        self.assertEqual(
            messages,
            [
                "asset-blacklist: interface/friendsframe/ui-toast-background: "
                "pre-Legion UI chrome (FileDataID < 1000000); use an atlas",
                "asset-blacklist: interface/friendsframe/ui-toast-border: "
                "pre-Legion UI chrome (FileDataID < 1000000); use an atlas",
            ],
        )

    def test_a_backdrop_global_is_expanded_in_every_source_kind(self):
        for source, suffix in (
            ("backdrop = BACKDROP_TOAST_12_12", ".py"),
            ('<KeyValue key="backdropInfo" value="BACKDROP_TOAST_12_12" type="global"/>', ".xml"),
            ('local backdrop = _G["BACKDROP_TOAST_12_12"]', ".lua"),
        ):
            with self.subTest(suffix=suffix):
                messages = [message for _, message in assets.check(source, suffix)]
                self.assertTrue(any("interface/friendsframe/ui-toast-border" in message for message in messages))

    def test_a_backdrop_global_with_current_files_passes(self):
        self.assertEqual(assets.check("f:SetBackdrop(BACKDROP_WATERMARK_DIALOG_0_16)"), [])

    def test_generated_backdrop_data_names_the_toast_files(self):
        self.assertEqual(
            legacy_chrome.backdrop_paths("BACKDROP_TOAST_12_12"),
            ("interface/friendsframe/ui-toast-background", "interface/friendsframe/ui-toast-border"),
        )


class BackdropSourceTest(unittest.TestCase):
    def test_backdrop_globals_are_read_from_their_definitions(self):
        source = (
            "BACKDROP_OLD_1_1 = {\n"
            '\tbgFile = "Interface\\\\Old\\\\Background",\n'
            '\tedgeFile = "Interface\\\\Old\\\\Border",\n'
            "\tinsets = { left = 1 },\n"
            "};\n"
            'NOT_A_BACKDROP = { name = "Interface\\\\Old\\\\Art" };\n'
            'OUTER = { inner = { bgFile = "Interface\\\\Old\\\\Nested" } };\n'
        )
        self.assertEqual(
            gen_legacy_chrome.parse_backdrops(source),
            {"BACKDROP_OLD_1_1": ["interface/old/background", "interface/old/border"]},
        )


if __name__ == "__main__":
    unittest.main()
