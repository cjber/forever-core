"""Backpack slots draw their item, not the empty-slot art, over filled slots."""

import unittest
from types import SimpleNamespace

import wowmock
from PIL import Image


class ItemUi:
    scale = 1

    def texture(self, ref):
        return Image.new("RGBA", (wowmock.ITEM_BUTTON, wowmock.ITEM_BUTTON), (255, 0, 0, 255))

    def atlas(self, name):
        if name != "bags-item-slot64":
            raise AssertionError(name)
        return wowmock.Atlas(name, Image.new("RGBA", (64, 64), (0, 255, 0, 255)), 64, 64, False, False)

    def global_color(self, name):
        return (1, 1, 1, 1)


class RecordingCanvas:
    def __init__(self, ui):
        self.ui = ui
        self.draws = []

    def draw(self, src, x, y, w=None, h=None, **kwargs):
        self.draws.append((src, x, y, w, h))

    def text(self, *args, **kwargs):
        pass


class BackpackSlotTest(unittest.TestCase):
    def test_a_filled_slot_shows_the_item_icon(self):
        ui = ItemUi()
        canvas = wowmock.Canvas(ui, wowmock.ITEM_BUTTON, wowmock.ITEM_BUTTON)
        wowmock.item_button(canvas, 0, 0, SimpleNamespace(icon=123, quality=0))
        middle = canvas.image.getpixel((wowmock.ITEM_BUTTON // 2, wowmock.ITEM_BUTTON // 2))
        self.assertEqual(middle[:3], (255, 0, 0))

    def test_an_empty_slot_draws_its_art_once_inside_the_button(self):
        ui = ItemUi()
        canvas = RecordingCanvas(ui)
        wowmock.item_button(canvas, 10, 20)
        slots = [draw for draw in canvas.draws if draw[0] is not None and draw[0].name == "bags-item-slot64"]
        self.assertEqual(len(slots), 1)
        _, x, y, w, h = slots[0]
        self.assertEqual((x, y, w, h), (10, 20, wowmock.ITEM_BUTTON, wowmock.ITEM_BUTTON))
        for _, x, y, w, h in canvas.draws:
            self.assertGreaterEqual(x, 10)
            self.assertGreaterEqual(y, 20)
            self.assertLessEqual(x + w, 10 + wowmock.ITEM_BUTTON)
            self.assertLessEqual(y + h, 20 + wowmock.ITEM_BUTTON)


if __name__ == "__main__":
    unittest.main()
