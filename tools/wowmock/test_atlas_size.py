"""atlas_size answers with the size atlas() picks, from the tables alone, and never fetches a sheet."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from wowmock import Ui

ATLAS_TABLES = {
    "UiTextureAtlasElement": {
        "demo": {"ID": "1", "Name": "demo"},
        "empty": {"ID": "2", "Name": "empty"},
    },
    "UiTextureAtlas": {
        "1": {
            "UiTextureAtlasSetID": "0",
            "UiCanvasID": "0",
            "FileDataID": "2",
            "AtlasWidth": "64",
            "AtlasHeight": "64",
        },
        "2": {
            "UiTextureAtlasSetID": "1",
            "UiCanvasID": "0",
            "FileDataID": "3",
            "AtlasWidth": "64",
            "AtlasHeight": "64",
        },
    },
    "UiCanvas": {},
    "UiTextureAtlasMember": {
        "10": {
            "ID": "10",
            "UiTextureAtlasElementID": "1",
            "UiTextureAtlasID": "1",
            "UiCanvasID": "0",
            "OverrideWidth": "0",
            "OverrideHeight": "0",
            "Width": "40",
            "Height": "20",
            "CommittedName": "demo-plain",
            "CommittedLeft": "0",
            "CommittedTop": "0",
            "CommittedRight": "40",
            "CommittedBottom": "20",
            "CommittedFlags": "0",
        },
        "11": {
            "ID": "11",
            "UiTextureAtlasElementID": "1",
            "UiTextureAtlasID": "2",
            "UiCanvasID": "0",
            "OverrideWidth": "0",
            "OverrideHeight": "0",
            "Width": "32",
            "Height": "16",
            "CommittedName": "demo-c60",
            "CommittedLeft": "0",
            "CommittedTop": "0",
            "CommittedRight": "32",
            "CommittedBottom": "16",
            "CommittedFlags": "0",
        },
    },
    "UiTextureAtlasElementSliceData": {},
}


def ui_in(directory):
    return Ui(scale=1, cache=Path(directory))


class AtlasSizeTest(unittest.TestCase):
    def test_matches_the_member_atlas_picks(self):
        with tempfile.TemporaryDirectory() as directory:
            ui = ui_in(directory)
            with (
                patch.object(ui, "table", side_effect=lambda name, key="ID": ATLAS_TABLES[name]),
                patch.object(ui, "_image", return_value=Image.new("RGBA", (64, 64))),
            ):
                atlas = ui.atlas("demo")
                size = ui.atlas_size("demo")
        self.assertEqual(size, (atlas.width, atlas.height))
        self.assertEqual(size, (32.0, 16.0))

    def test_an_unknown_name_is_none(self):
        with tempfile.TemporaryDirectory() as directory:
            ui = ui_in(directory)
            with patch.object(ui, "table", side_effect=lambda name, key="ID": ATLAS_TABLES[name]):
                self.assertIsNone(ui.atlas_size("no-such-element"))

    def test_an_element_with_no_member_is_none(self):
        with tempfile.TemporaryDirectory() as directory:
            ui = ui_in(directory)
            with patch.object(ui, "table", side_effect=lambda name, key="ID": ATLAS_TABLES[name]):
                self.assertIsNone(ui.atlas_size("empty"))

    def test_the_match_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as directory:
            ui = ui_in(directory)
            with patch.object(ui, "table", side_effect=lambda name, key="ID": ATLAS_TABLES[name]):
                self.assertEqual(ui.atlas_size("DeMo"), (32.0, 16.0))

    def test_no_texture_is_fetched_and_no_asset_gate_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            ui = ui_in(directory)
            with (
                patch.object(ui, "table", side_effect=lambda name, key="ID": ATLAS_TABLES[name]),
                patch.object(ui, "_image") as image,
                patch.object(ui, "check_asset") as check_asset,
                patch.object(ui.wago, "file") as file,
                patch.object(ui.wago, "fetch") as fetch,
            ):
                self.assertEqual(ui.atlas_size("demo"), (32.0, 16.0))
        image.assert_not_called()
        check_asset.assert_not_called()
        file.assert_not_called()
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
