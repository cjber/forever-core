"""Menu compositing regressions, using synthetic art without client downloads."""

import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from wowmock import Atlas, Canvas, MenuRadio, MenuTitle, Ui, context_menu


class MenuTransparencyTest(unittest.TestCase):
    def test_rounded_menu_preserves_scene_at_transparent_corners(self):
        image = Image.new("RGBA", (68, 68))
        ImageDraw.Draw(image).rounded_rectangle((0, 0, 67, 67), radius=12, fill=(0, 0, 0, 242))
        atlas = Atlas("common-dropdown-bg", image, 68, 68, False, False, (16, 13, 16, 19))
        ui = Ui(scale=1)
        with (
            patch.object(ui, "atlas", return_value=atlas),
            patch.object(Canvas, "text_width", return_value=80),
            patch.object(Canvas, "text"),
        ):
            menu, _ = context_menu(ui, [MenuTitle("Ashenvale")])
        scene = Image.new("RGBA", menu.image.size, (90, 120, 50, 255))
        composed = Image.alpha_composite(scene, menu.image)
        self.assertEqual(composed.getpixel((2, 9)), scene.getpixel((2, 9)))
        centre = (menu.image.width // 2, menu.image.height // 2)
        self.assertNotEqual(composed.getpixel(centre), scene.getpixel(centre))


class MenuRadioTest(unittest.TestCase):
    def test_a_radio_uses_the_radial_art_and_its_label_clears_it_by_one_unit(self):
        ui = Ui(scale=1)
        art = {}
        for name, size in (
            ("common-dropdown-bg", (68, 68)),
            ("common-dropdown-ticksquare", (12, 12)),
            ("common-dropdown-tickradial", (18, 18)),
            ("common-dropdown-icon-radialtick-yellow", (14, 14)),
        ):
            art[name] = Atlas(name, Image.new("RGBA", size), *size, False, False)
        with (
            patch.object(ui, "atlas", side_effect=art.__getitem__),
            patch.object(Canvas, "text_width", return_value=60),
            patch.object(Canvas, "draw") as draw,
            patch.object(Canvas, "text") as text,
        ):
            context_menu(ui, [MenuRadio("All addons", True)])
        # Menu inset (8) and margin (12) put the row at x=20, y=20; an 18-high radial tick centres at y=21.
        self.assertEqual(draw.call_args_list[1].args, (art["common-dropdown-tickradial"], 20, 21))
        self.assertEqual(draw.call_args_list[2].args[0], art["common-dropdown-icon-radialtick-yellow"])
        # The label clears the 18-wide indicator by one unit and sits level with the row.
        self.assertEqual(text.call_args.args[:3], (39, 20, "All addons"))


if __name__ == "__main__":
    unittest.main()
