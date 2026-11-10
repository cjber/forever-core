"""Render docs/discord-button.png, the Discord button on every store page beside the Sponsors and Ko-fi buttons.

It matches docs/github-sponsors-button.png: a 223x30 pill, the mark in a white rounded square with a dark border, and
the label in Adwaita Sans Regular at 14 px. The pill is Discord's blurple lightened to the Ko-fi button's luminance,
so the dark label reads the same on all three. The mark is Discord's logo from Simple Icons (CC0), drawn from its SVG
path with rsvg-convert.

    python3 tools/render_discord_button.py [--font PATH]
"""

import argparse
import io
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/discord-button.png"
FONT = Path("/usr/share/fonts/Adwaita/AdwaitaSans-Regular.ttf")

SIZE = (223, 30)
SCALE = 4  # drawn at 4x and downsampled, for the same anti-aliasing as the hand-drawn buttons
PILL = (138, 148, 247, 255)
INK = (25, 21, 23, 255)
BLURPLE = "#5865F2"
LABEL = "Join me on Discord"
# Simple Icons "discord" path, viewBox 0 0 24 24.
MARK = (
    "M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495"
    "-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0"
    " 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528"
    " 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0"
    " 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914"
    "a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728"
    ".2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628"
    " 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177"
    "-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332"
    ".9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0"
    "c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419"
    " 0 1.3332-.946 2.4189-2.1568 2.4189Z"
)
# The icon square and label position, measured from docs/github-sponsors-button.png.
BOX = (9, 4, 34, 25)
LABEL_X = 55


def mark(size):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="{BLURPLE}" d="{MARK}"/></svg>'
    png = subprocess.run(
        ["rsvg-convert", "-w", str(size), "-h", str(size)], input=svg.encode(), capture_output=True, check=True
    ).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")


def render(font_path):
    w, h = SIZE[0] * SCALE, SIZE[1] * SCALE
    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=PILL)
    box = tuple(v * SCALE for v in BOX)
    draw.rounded_rectangle(box, radius=5 * SCALE, fill=(255, 255, 255, 255), outline=INK, width=SCALE + SCALE // 2)
    side = (box[3] - box[1]) * 7 // 10
    logo = mark(side)
    image.alpha_composite(logo, ((box[0] + box[2] - side) // 2, (box[1] + box[3] - side) // 2))
    font = ImageFont.truetype(str(font_path), 14 * SCALE)
    draw.text((LABEL_X * SCALE, h // 2), LABEL, font=font, fill=INK, anchor="lm")
    return image.resize(SIZE, Image.LANCZOS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--font", type=Path, default=FONT, help="Adwaita Sans Regular")
    arguments = parser.parse_args(argv)
    render(arguments.font).save(OUT, optimize=True)
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
