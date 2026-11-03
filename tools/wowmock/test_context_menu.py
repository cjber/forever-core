"""Menu compositing regressions, using synthetic art without client downloads."""

import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from wowmock import Atlas, Canvas, MenuTitle, Ui, context_menu


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


if __name__ == "__main__":
    unittest.main()
