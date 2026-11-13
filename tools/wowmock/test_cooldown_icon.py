"""A Cooldown Manager icon is masked by the client's mask and wears its overlay at the documented outset."""

import unittest

import wowmock
from PIL import Image


class CooldownUi:
    scale = 1

    def __init__(self):
        self.atlases = []

    def texture(self, ref):
        return Image.new("RGBA", (50, 50), (255, 0, 0, 255))

    def atlas(self, name):
        self.atlases.append(name)
        if name == "UI-HUD-CoolDownManager-Mask":
            return wowmock.Atlas(name, Image.new("RGBA", (50, 50), (255, 255, 255, 128)), 50, 50, False, False)
        if name == "UI-HUD-CoolDownManager-IconOverlay":
            return wowmock.Atlas(name, Image.new("RGBA", (16, 16), (0, 255, 0, 255)), 16, 16, False, False)
        raise AssertionError(name)


class RecordingCanvas:
    def __init__(self, ui):
        self.ui = ui
        self.draws = []
        self.composites = []

    def px(self, value):
        return value

    def composite(self, piece, left, top, blend="BLEND"):
        self.composites.append((piece, left, top))

    def draw(self, src, x, y, w=None, h=None, **kwargs):
        self.draws.append((src, x, y, w, h))


class CooldownIconTest(unittest.TestCase):
    def test_the_icon_is_masked_and_the_overlay_lands_at_the_outset(self):
        ui = CooldownUi()
        canvas = RecordingCanvas(ui)
        wowmock.cooldown_icon(canvas, 10, 20, 50, 134400)
        self.assertEqual(ui.atlases, ["UI-HUD-CoolDownManager-Mask", "UI-HUD-CoolDownManager-IconOverlay"])
        piece, left, top = canvas.composites[0]
        self.assertEqual((left, top), (10, 20))
        self.assertEqual(piece.size, (50, 50))
        self.assertEqual(piece.getpixel((25, 25))[3], 128)
        src, x, y, w, h = canvas.draws[0]
        self.assertEqual(src.name, "UI-HUD-CoolDownManager-IconOverlay")
        self.assertEqual((x, y, w, h), (1, 12, 68, 66))


if __name__ == "__main__":
    unittest.main()
