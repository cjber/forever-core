"""Button state selection follows the native SharedButton template."""

import unittest
from unittest.mock import patch

from PIL import Image
from wowmock import DISABLED, FONTS, Atlas, Canvas, Ui, ui_panel_button


class ButtonStatesTest(unittest.TestCase):
    def test_native_atlas_and_text_states(self):
        for state, suffix in (("normal", ""), ("hover", ""), ("pressed", "-Pressed"), ("disabled", "-Disabled")):
            with self.subTest(state=state):
                ui = Ui(scale=1)
                canvas = ui.canvas(200, 40)
                atlas = Atlas("button", Image.new("RGBA", (12, 24)), 12, 24, False, False)
                with patch.object(ui, "atlas", return_value=atlas) as lookup, patch.object(Canvas, "text") as text:
                    ui_panel_button(canvas, 10, 8, 150, 24, "Continue", state=state)
                names = [call.args[0] for call in lookup.call_args_list]
                self.assertEqual(
                    names[:3],
                    [f"128-RedButton-Left{suffix}", f"128-RedButton-Right{suffix}", f"_128-RedButton-Center{suffix}"],
                )
                self.assertEqual(len(names), 4 if state == "hover" else 3)
                if state == "hover":
                    self.assertEqual(names[-1], "128-RedButton-Highlight")
                self.assertEqual(text.call_args.args[:2], (8, 7) if state == "pressed" else (10, 8))
                self.assertEqual(
                    text.call_args.args[3], FONTS["GameFontHighlight" if state == "hover" else "GameFontNormal"]
                )
                self.assertEqual(text.call_args.args[4], DISABLED if state == "disabled" else None)


if __name__ == "__main__":
    unittest.main()
