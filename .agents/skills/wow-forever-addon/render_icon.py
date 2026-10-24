#!/usr/bin/env python3
"""Render an addon's media/icon.svg to media/icon-400.png and the 64 px media/Icon.tga (WFA-8).

Run from the addon repository root. Needs `rsvg-convert` (librsvg) and Pillow. Output is
deterministic, so rerunning on an unchanged SVG leaves the files byte-identical.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

SVG = Path("media/icon.svg")
PNG = Path("media/icon-400.png")
TGA = Path("media/Icon.tga")


def render(size: int) -> Image.Image:
    png = subprocess.run(
        ["rsvg-convert", "--width", str(size), "--height", str(size), str(SVG)],
        check=True,
        capture_output=True,
    ).stdout
    return Image.open(BytesIO(png)).convert("RGBA")


def main() -> int:
    if not SVG.is_file():
        print(f"{SVG} not found; run from the addon repository root", file=sys.stderr)
        return 2
    if shutil.which("rsvg-convert") is None:
        print("rsvg-convert not found; install librsvg", file=sys.stderr)
        return 2
    render(400).save(PNG, optimize=True)
    # Top-left origin, uncompressed: the format the family's existing Icon.tga files use.
    render(64).save(TGA, rle=False, orientation=1)
    print(f"wrote {PNG} and {TGA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
