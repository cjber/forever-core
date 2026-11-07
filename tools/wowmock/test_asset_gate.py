"""A render fails when it touches art the suite's asset blacklist forbids."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import wowmock
from forever_tools import legacy_chrome
from PIL import Image
from wowmock import BUILD, Atlas, BannedAsset, Ui

ATLAS_TABLES = {
    "UiTextureAtlasElement": {"common-dropdown-bg": {"ID": "1", "Name": "common-dropdown-bg"}},
    "UiTextureAtlas": {
        "1": {
            "UiTextureAtlasSetID": "0",
            "UiCanvasID": "0",
            "FileDataID": "2",
            "AtlasWidth": "64",
            "AtlasHeight": "64",
        }
    },
    "UiCanvas": {},
    "UiTextureAtlasMember": {
        "1": {
            "ID": "1",
            "UiTextureAtlasElementID": "1",
            "UiTextureAtlasID": "1",
            "UiCanvasID": "0",
            "OverrideWidth": "0",
            "OverrideHeight": "0",
            "Width": "64",
            "Height": "64",
            "CommittedName": "common-dropdown-bg",
            "CommittedLeft": "0",
            "CommittedTop": "0",
            "CommittedRight": "64",
            "CommittedBottom": "64",
            "CommittedFlags": "0",
        }
    },
    "UiTextureAtlasElementSliceData": {},
}


def ui_in(directory):
    return Ui(scale=1, cache=Path(directory))


class BannedTextureTest(unittest.TestCase):
    def test_a_banned_texture_path_raises(self):
        path = "interface/minimap/tracking/repair.blp"
        with tempfile.TemporaryDirectory() as directory:
            ui = ui_in(directory)
            with self.assertRaises(BannedAsset) as caught:
                ui.texture(path)
        self.assertEqual(caught.exception.asset, path)
        self.assertIn(path, str(caught.exception))
        self.assertIn("Repair atlas of the same name", str(caught.exception))
        self.assertIsInstance(caught.exception, ValueError)

    def test_an_f_string_built_banned_path_raises(self):
        name = "banker"
        path = f"interface/minimap/tracking/{name}.blp"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(BannedAsset) as caught:
                ui_in(directory).texture(path)
        self.assertEqual(caught.exception.asset, path)
        self.assertIn("Banker atlas", caught.exception.reason)

    def test_a_banned_numeric_texture_uses_paths_json(self):
        path = "interface/minimap/tracking/repair.blp"
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            (cache / "paths.json").write_text(json.dumps({path: 136465}))
            with self.assertRaises(BannedAsset) as caught:
                ui_in(directory).texture(136465)
        self.assertEqual(caught.exception.asset, path)

    def test_a_banned_numeric_texture_uses_the_cached_listfile(self):
        path = "interface/minimap/tracking/repair.blp"
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            (cache / f"listfile-{BUILD}.json").write_text(
                json.dumps({"136465": "interface\\minimap\\tracking\\repair.blp"})
            )
            with self.assertRaises(BannedAsset) as caught:
                ui_in(directory).texture(136465)
        self.assertEqual(caught.exception.asset, path)

    def test_allowlisted_pieces_pass_the_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            ui = ui_in(directory)
            for path in legacy_chrome.ALLOWLIST:
                with self.subTest(path=path):
                    self.assertIsNone(ui.check_asset(path))

    def test_an_allowlisted_texture_still_renders(self):
        path = "interface/buttons/buttonhilight-square.blp"
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            (cache / "paths.json").write_text(json.dumps({path: 130718}))
            ui = ui_in(directory)
            with (
                patch.object(ui.wago, "file", return_value=b""),
                patch.object(wowmock, "decode_texture", return_value=Image.new("RGBA", (1, 1))),
            ):
                self.assertIsInstance(ui.texture(path), Image.Image)


class BannedAtlasTest(unittest.TestCase):
    def test_a_banned_atlas_raises(self):
        name = "GarrMission_MissionParchment"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(BannedAsset) as caught:
                ui_in(directory).atlas(name)
        self.assertEqual(caught.exception.asset, name)
        self.assertIn("expansion chrome", caught.exception.reason)

    def test_a_normal_atlas_resolves(self):
        with tempfile.TemporaryDirectory() as directory:
            ui = ui_in(directory)
            with (
                patch.object(ui, "table", side_effect=lambda name, key="ID": ATLAS_TABLES[name]),
                patch.object(ui, "_image", return_value=Image.new("RGBA", (64, 64))),
            ):
                atlas = ui.atlas("common-dropdown-bg")
        self.assertIsInstance(atlas, Atlas)
        self.assertEqual(atlas.name, "common-dropdown-bg")

    def test_an_atlas_sheet_is_not_rechecked_as_loose_art(self):
        tables = copy.deepcopy(ATLAS_TABLES)
        tables["UiTextureAtlas"]["1"]["FileDataID"] = "137056"
        with tempfile.TemporaryDirectory() as directory:
            ui = ui_in(directory)
            with (
                patch.object(ui, "table", side_effect=lambda name, key="ID": tables[name]),
                patch.object(ui.wago, "file", return_value=b""),
                patch.object(wowmock, "decode_texture", return_value=Image.new("RGBA", (64, 64))),
            ):
                atlas = ui.atlas("common-dropdown-bg")
        self.assertIsInstance(atlas, Atlas)


if __name__ == "__main__":
    unittest.main()
