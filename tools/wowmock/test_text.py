"""Canvas text layout regressions, using Pillow's bundled bitmap font."""

import unittest
from types import SimpleNamespace

from PIL import ImageFont
from wowmock import Canvas


class FakeUi:
    scale = 1

    @staticmethod
    def font(_font):
        return ImageFont.load_default(size=16)


class TextLayoutTest(unittest.TestCase):
    def test_text_width_uses_the_widest_line(self):
        canvas = Canvas(FakeUi(), 120, 40)
        font = SimpleNamespace(height=16, color=(1, 1, 1), shadow=None, outline=False)
        self.assertEqual(canvas.text_width("x\nwide line", font), canvas.text_width("wide line", font))

    def test_multiline_center_and_right_justify_each_line(self):
        canvas = Canvas(FakeUi(), 120, 40)
        font = SimpleNamespace(height=16, color=(1, 1, 1), shadow=None, outline=False)
        canvas.text(0, 0, "wide line\nx", font, justify="CENTER", width=120)
        alpha = canvas.image.getchannel("A")
        rows = [alpha.crop((0, top, 120, top + 16)).getbbox() for top in (0, 16)]
        self.assertIsNotNone(rows[0])
        self.assertIsNotNone(rows[1])
        self.assertAlmostEqual((rows[0][0] + rows[0][2]) / 2, 60, delta=2)
        self.assertAlmostEqual((rows[1][0] + rows[1][2]) / 2, 60, delta=2)

        canvas = Canvas(FakeUi(), 120, 40)
        canvas.text(0, 0, "wide line\nx", font, justify="RIGHT", width=120)
        alpha = canvas.image.getchannel("A")
        rows = [alpha.crop((0, top, 120, top + 16)).getbbox() for top in (0, 16)]
        self.assertGreater(rows[1][0], rows[0][0])
        self.assertAlmostEqual(rows[0][2], 120, delta=2)
        self.assertAlmostEqual(rows[1][2], 120, delta=2)


if __name__ == "__main__":
    unittest.main()
