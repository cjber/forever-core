"""Dropdown art follows WowStyle1DropdownTemplate's own anchors."""

import unittest
from unittest.mock import patch

from PIL import Image
from wowmock import FONTS, Atlas, Canvas, Ui, dropdown


class DropdownAnchorsTest(unittest.TestCase):
    def test_background_and_arrow_anchors(self):
        ui = Ui(scale=1)
        canvas = ui.canvas(240, 80)
        background = Atlas("common-dropdown-textholder", Image.new("RGBA", (120, 25)), 120, 25, False, False)
        arrow = Atlas("common-dropdown-a-button", Image.new("RGBA", (18, 26)), 18, 26, False, False)
        art = {"common-dropdown-textholder": background, "common-dropdown-a-button": arrow}
        with (
            patch.object(ui, "atlas", side_effect=art.__getitem__),
            patch.object(Canvas, "draw") as draw,
            patch.object(Canvas, "text") as text,
            patch.object(Canvas, "text_width", side_effect=lambda value, font: len(value) * 6),
        ):
            rect = dropdown(canvas, 40, 20, 120, "Legacy")
        self.assertEqual(rect, (40, 20, 120, 25))
        # Background: TOPLEFT (-8, 7) to BOTTOMRIGHT (8, -9) is w+16 by h+16 around the button.
        self.assertEqual(draw.call_args_list[0].args, (background, 32, 13, 136, 41))
        # Arrow: RIGHT (1, -3) puts its right edge 1 past the button and its centre 3 below the middle, so a
        # centred arrow (19.5 here) fails.
        self.assertEqual(draw.call_args_list[1].args, (arrow, 143, 22.5))
        self.assertEqual(text.call_args.args[:2], (48, 28))
        self.assertEqual(text.call_args.args[2], "Legacy")
        self.assertEqual(text.call_args.args[3], FONTS["GameFontHighlight"])
        self.assertEqual(text.call_args.kwargs, {"box_height": 10})

    def test_text_is_cut_short_of_the_arrow(self):
        ui = Ui(scale=1)
        canvas = ui.canvas(240, 80)
        art = {
            name: Atlas(name, Image.new("RGBA", (1, 1)), 18, 26, False, False)
            for name in ("common-dropdown-textholder", "common-dropdown-a-button")
        }
        with (
            patch.object(ui, "atlas", side_effect=art.__getitem__),
            patch.object(Canvas, "draw"),
            patch.object(Canvas, "text") as text,
            patch.object(Canvas, "text_width", side_effect=lambda value, font: len(value) * 6),
        ):
            dropdown(canvas, 40, 20, 120, "Legacy of the Forever")
        # 95 units of room before the arrow's left edge, at 6 units a glyph: 12 characters and '...'.
        self.assertEqual(text.call_args.args[2], "Legacy of th...")


if __name__ == "__main__":
    unittest.main()
