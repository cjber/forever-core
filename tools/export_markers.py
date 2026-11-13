"""Export the suite's step markers from their generated sources in tools/marker_source.

The sources are AI-assisted originals on a flat magenta (#FF00FF) background, made for these addons with no Blizzard
art. This keys the magenta to alpha, crops to the art, centres it at its native aspect on a 64 by 64 canvas and
writes media/Numbers/1.tga to media/Numbers/25.tga, the gold numbered markers, Ring.tga, the empty ring a place
visited twice stacks behind, and Diamond.tga, the ring with the goal pin's diamond in it: the polygon 17 pixels out
from (64, 50) on the 128 by 128 pin, scaled to 27 pixels with one factor for both axes and centred over the ring. The
numbered markers and the ring are byte for byte the files Adventure Guide Forever and Shortest Path Forever already
ship for the same numbers, so an addon reads its markers from core instead of carrying a second copy.

    python3 tools/export_markers.py            # rewrite media/Numbers from tools/marker_source
    python3 tools/export_markers.py --check    # fail when the committed files differ from what this writes
"""

import argparse
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools" / "marker_source"
TARGET = ROOT / "media" / "Numbers"

# A marker's canvas: square, since the client draws it in a square slot.
SIZE = 64
MAX_NUMBER = 25
NUMBERS = range(1, MAX_NUMBER + 1)
RING_SOURCE = "ring.png"
# The goal pin, keyed to 128 by 128 exactly as Shortest Path Forever's media/Pin.tga is, for the diamond to cut.
PIN_SOURCE = "pin-gold.png"
PIN_SIZE = 128
# The pin's diamond sits in the dark circle: a polygon this far from this centre, one factor for both axes.
DIAMOND_CENTRE = (64, 50)
DIAMOND_RADIUS = 17
# The diamond fills this share of a marker's width, so it sits inside the ring's opening.
DIAMOND_SHARE = 0.42
# The polygon is drawn this many times too large and scaled down, so its edge is smooth and not stepped.
SUPERSAMPLE = 4


def key_magenta(image: Image.Image) -> Image.Image:
    """Magenta to alpha, with a soft edge and the magenta spill pulled out of the rim."""
    image = image.convert("RGBA")
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, _ = pixels[x, y]
            distance = max(abs(r - 255), g, abs(b - 255))
            if distance < 60:
                pixels[x, y] = (r, g, b, 0)
            elif distance < 120:
                pixels[x, y] = (min(r, g + 40), g, min(b, g + 40), int(255 * (distance - 60) / 60))
    return image


def art(source: Path, size: int = SIZE) -> Image.Image:
    """`source` keyed, cropped to the art and centred at its native aspect on a `size` square canvas."""
    with Image.open(source) as opened:
        marker = key_magenta(opened)
    marker = marker.crop(marker.getbbox())
    scale = size / max(marker.size)  # one factor for both axes: the art keeps its shape
    marker = marker.resize((round(marker.width * scale), round(marker.height * scale)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size))
    canvas.paste(marker, ((size - marker.width) // 2, (size - marker.height) // 2))
    return canvas


def diamond_mask() -> Image.Image:
    """The pin's diamond as a mask on a 128 by 128 pin: `DIAMOND_RADIUS` out from `DIAMOND_CENTRE`, smooth edged."""
    large = PIN_SIZE * SUPERSAMPLE
    mask = Image.new("L", (large, large), 0)
    x, y = DIAMOND_CENTRE
    radius = DIAMOND_RADIUS
    ImageDraw.Draw(mask).polygon(
        [
            (x * SUPERSAMPLE, (y - radius) * SUPERSAMPLE),
            ((x + radius) * SUPERSAMPLE, y * SUPERSAMPLE),
            (x * SUPERSAMPLE, (y + radius) * SUPERSAMPLE),
            ((x - radius) * SUPERSAMPLE, y * SUPERSAMPLE),
        ],
        fill=255,
    )
    return mask.resize((PIN_SIZE, PIN_SIZE), Image.Resampling.LANCZOS)


def diamond_cut(pin: Image.Image) -> Image.Image:
    """The goal pin's diamond, cut out by `diamond_mask` and cropped to what is left of the art."""
    cut = pin.copy()
    cut.putalpha(Image.composite(pin.getchannel("A"), Image.new("L", pin.size, 0), diamond_mask()))
    return cut.crop(cut.getchannel("A").point(lambda value: 255 if value > 8 else 0).getbbox())


def with_diamond(ring: Image.Image, pin: Image.Image) -> Image.Image:
    """`ring` with the pin's diamond drawn at `DIAMOND_SHARE` of its width, centred over the ring."""
    cut = diamond_cut(pin)
    size = round(ring.width * DIAMOND_SHARE)
    scale = size / max(cut.size)  # one factor for both axes: the diamond keeps its shape
    cut = cut.resize((round(cut.width * scale), round(cut.height * scale)), Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", ring.size, (0, 0, 0, 0))
    layer.paste(cut, ((ring.width - cut.width) // 2, (ring.height - cut.height) // 2))
    return Image.alpha_composite(ring, layer)


def encode(image: Image.Image) -> bytes:
    """`image` as the uncompressed 32-bit TGA the client reads."""
    buffer = io.BytesIO()
    image.save(buffer, format="TGA", compression=None)
    return buffer.getvalue()


def renders() -> dict[Path, bytes]:
    """Every marker file this tool writes, keyed by its path under the repository root."""
    files = {}
    for number in NUMBERS:
        files[TARGET / f"{number}.tga"] = encode(art(SOURCE / f"{number}.png"))
    ring = art(SOURCE / RING_SOURCE)
    files[TARGET / "Ring.tga"] = encode(ring)
    pin = art(SOURCE / PIN_SOURCE, PIN_SIZE)
    files[TARGET / "Diamond.tga"] = encode(with_diamond(ring, pin))
    return files


def shown(path: Path) -> str:
    """`path` under the repository as a repository path, or as it stands when it is not."""
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--check", action="store_true", help="fail when a committed marker differs from what this tool writes"
    )
    args = parser.parse_args(argv)
    files = renders()
    if args.check:
        stale = [path for path, data in files.items() if not path.is_file() or path.read_bytes() != data]
        for path in stale:
            print(f"{shown(path)}: differs from what tools/export_markers.py writes")
        if stale:
            return 1
        print(f"Step markers: {len(files)} committed files match tools/marker_source")
        return 0
    for path, data in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(f"Step markers: wrote {len(files)} files to {shown(TARGET)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
