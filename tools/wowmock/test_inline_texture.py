"""A |T escape may name its texture by FileDataID, as the client allows, as well as by path."""

import unittest

import wowmock
from PIL import Image


class TextureUi:
    def __init__(self):
        self.refs = []

    def texture(self, ref):
        self.refs.append(ref)
        return Image.new("RGBA", (64, 64), (255, 0, 0, 255))


class InlineTextureTest(unittest.TestCase):
    def run_of(self, markup):
        ((run, _color),) = wowmock.text_runs(markup, (1, 1, 1))
        return run

    def test_file_data_id_is_looked_up_by_id(self):
        ui = TextureUi()
        wowmock.inline_texture_image(ui, self.run_of("|T132892:14:14|t"))
        self.assertEqual(ui.refs, [132892])

    def test_path_is_still_looked_up_by_path(self):
        ui = TextureUi()
        wowmock.inline_texture_image(ui, self.run_of("|TInterface\\Icons\\INV_Misc_QuestionMark:14|t"))
        self.assertEqual(ui.refs, ["interface/icons/inv_misc_questionmark.blp"])

    def test_file_data_id_keeps_its_crop(self):
        image = wowmock.inline_texture_image(TextureUi(), self.run_of("|T132892:14:14:0:0:64:64:5:59:5:59|t"))
        self.assertEqual(image.size, (54, 54))


if __name__ == "__main__":
    unittest.main()
