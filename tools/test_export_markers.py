"""Tests for tools/export_markers.py: the step markers it writes and the --check mode the gate runs."""

import contextlib
import io
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import export_markers  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


class MarkersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = export_markers.renders()

    def test_every_committed_file_matches_the_sources(self):
        stale = [path.name for path, data in self.files.items() if path.read_bytes() != data]
        self.assertEqual(stale, [], "run python3 tools/export_markers.py")

    def test_the_set_is_twenty_five_numbers_ring_and_diamond(self):
        names = sorted(path.name for path in self.files)
        expected = sorted([f"{number}.tga" for number in range(1, 26)] + ["Ring.tga", "Diamond.tga"])
        self.assertEqual(names, expected)

    def test_every_marker_is_a_64_pixel_square_tga(self):
        for path, data in self.files.items():
            with self.subTest(marker=path.name):
                width, height = data[12] | data[13] << 8, data[14] | data[15] << 8
                self.assertEqual((width, height), (64, 64), "a 64 by 64 TGA header")
                self.assertEqual(data[16], 32, "32 bits per pixel")
                with Image.open(io.BytesIO(data)) as image:
                    image.load()
                    self.assertEqual(image.size, (64, 64))

    def test_the_diamond_sits_in_the_ring_and_leaves_the_rim_alone(self):
        ring = export_markers.art(export_markers.SOURCE / export_markers.RING_SOURCE)
        pin = export_markers.art(export_markers.SOURCE / export_markers.PIN_SOURCE, export_markers.PIN_SIZE)
        diamond = export_markers.with_diamond(ring, pin)
        middle = sum(ring.getpixel((32, 32))[:3])
        self.assertLess(middle, 150, "the empty ring's middle is the dark hole")
        self.assertGreater(sum(diamond.getpixel((32, 32))[:3]), middle, "the diamond is gold in that middle")
        rim = [
            (x, y)
            for x in range(64)
            for y in range(64)
            if ring.getpixel((x, y))[3] > 200 and not 16 <= x <= 47 and not 16 <= y <= 47
        ]
        self.assertTrue(rim, "the ring draws a rim round its opening")
        changed = [point for point in rim if diamond.getpixel(point) != ring.getpixel(point)]
        self.assertEqual(changed, [], "the diamond is pasted inside the ring's opening only")

    def test_the_transformed_face_centre_is_exact(self):
        ring = export_markers.art(export_markers.SOURCE / export_markers.RING_SOURCE)
        pin = export_markers.art(export_markers.SOURCE / export_markers.PIN_SOURCE, export_markers.PIN_SIZE)
        cut, centre = export_markers.diamond_cut(pin)
        self.assertEqual(centre, (Fraction(33, 2), Fraction(33, 2)))
        original_overlay = export_markers.diamond_overlay

        def check_overlay(ring, scaled, face):
            expected = tuple(
                point * Fraction(new, old) for point, new, old in zip(centre, scaled.size, cut.size, strict=True)
            )
            self.assertEqual(face, expected)
            origin = export_markers.diamond_origin(ring, face)
            self.assertEqual(tuple(a + b for a, b in zip(origin, face, strict=True)), (Fraction(32), Fraction(32)))
            return original_overlay(ring, scaled, face)

        with mock.patch.object(export_markers, "diamond_overlay", side_effect=check_overlay):
            export_markers.with_diamond(ring, pin)

    def test_rendered_face_extent_is_symmetric(self):
        # Isolate the measured face silhouette from its differently shaded facets
        # and shadow. Keep the real pin's alpha so the production crop is unchanged.
        pin = export_markers.art(export_markers.SOURCE / export_markers.PIN_SOURCE, export_markers.PIN_SIZE)
        face = Image.new("RGBA", pin.size, (0, 0, 0, 255))
        ImageDraw.Draw(face).polygon([(63, 35), (77, 49), (63, 63), (49, 49)], fill="white")
        face.putalpha(pin.getchannel("A"))
        ring = Image.new("RGBA", (64, 64), (0, 0, 0, 255))
        rendered = export_markers.with_diamond(ring, face)
        # Half coverage is the geometric edge of the white silhouette, independent
        # of the source's gold RGB values. Pixel edges, rather than indices, bound it.
        bounds = rendered.convert("L").point(lambda coverage: 255 if coverage >= 128 else 0).getbbox()
        self.assertIsNotNone(bounds)
        for axis in (0, 1):
            self.assertAlmostEqual(
                (bounds[axis] + bounds[axis + 2]) / 2,
                ring.size[axis] / 2,
                delta=1 / export_markers.COMPOSITE_SUPERSAMPLE,
            )

    def test_check_passes_on_the_repository(self):
        self.assertEqual(export_markers.main(["--check"]), 0)

    def test_check_fails_on_a_stale_marker(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch)
            for path, data in self.files.items():
                (target / path.name).write_bytes(data)
            (target / "3.tga").write_bytes(b"stale")
            with mock.patch.object(export_markers, "TARGET", target), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(export_markers.main(["--check"]), 1)

    def test_check_fails_on_a_missing_marker(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch)
            for path, data in self.files.items():
                if path.name != "Diamond.tga":
                    (target / path.name).write_bytes(data)
            with mock.patch.object(export_markers, "TARGET", target), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(export_markers.main(["--check"]), 1)


if __name__ == "__main__":
    unittest.main()
