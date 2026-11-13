"""Tests for tools/export_markers.py: the step markers it writes and the --check mode the gate runs."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import export_markers  # noqa: E402
from PIL import Image  # noqa: E402


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
