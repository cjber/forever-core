#!/usr/bin/env python3
"""Fail when a rendered scene's widgets leave the window frame or overlap each other.

`tools/mockups.py` writes `docs/screenshots/layout.json` beside the images: the window frame and every widget it drew,
in the same units the addon anchors them in. This reads that manifest and the PNGs together and holds them to the
rules a player would notice, so a layout bug cannot reach a README, a store listing or a merge:

- every widget sits inside the window frame, and the whole drawing sits on the canvas;
- interactive widgets (buttons, tabs, inputs) never overlap, and side-by-side buttons keep at least `MIN_GAP` units
  between them and `MIN_INSET` from their container's edge;
- in the rendered pixels, the button art is where the manifest says it is, inside the frame - the manifest is only
  trustworthy while the renderer still matches it.

    python3 tools/visual_audit.py             # audit docs/screenshots
    python3 tools/visual_audit.py --dir DIR   # audit another render directory

Exit 0 when every scene passes, 1 with one line per finding otherwise. Development only; nothing here ships.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MIN_GAP = 8.0
MIN_INSET = 8.0
INTERACTIVE = {"button", "tabs", "input"}
# A pixel belongs to the UI when it is brighter than the mock backdrop's brightest wash (inner 0.13 of white).
UI_LUMA = 62.0
# Tolerance in device pixels for art that is drawn a pixel or two proud of its logical rect (button caps, glow).
ART_SLOP = 6


def luma(pixel: tuple[int, int, int]) -> float:
    red, green, blue = pixel
    return 0.299 * red + 0.587 * green + 0.114 * blue


def is_button_red(pixel: tuple[int, int, int]) -> bool:
    """The 128-RedButton art: a saturated dark red, unlike the gold text and brass chrome around it."""
    red, green, blue = pixel
    return red > 90 and red > green * 1.6 and red > blue * 1.6 and green < 90


def load_png(path: Path) -> Any:
    try:
        from PIL import Image  # ty: ignore[unresolved-import]  # Pillow is local only, like wowmock
    except ImportError:
        sys.exit("visual_audit: Pillow is required (uv add pillow)")
    return Image.open(path).convert("RGB")


def frame_box(image: Any) -> tuple[int, int, int, int]:
    """The window's outer chrome, read off the top edge: the title bar band carries nothing but the frame."""
    width, height = image.size
    pixels = image.load()
    bright = [(x, y) for y in range(0, height, 2) for x in range(0, width, 2) if luma(pixels[x, y]) > UI_LUMA]
    if not bright:
        raise ValueError("nothing drawn above the backdrop")
    top = min(y for _, y in bright)
    band = [x for x, y in bright if y <= top + 40]
    left, right = min(band), max(band)
    rows = [y for x, y in bright if left <= x <= right]
    return left, top, right, max(rows)


def red_extent(image: Any, top: int, bottom: int) -> tuple[int, int, list[int]]:
    """Horizontal extent of button art in a row band, plus the x of every red column (to find the gap)."""
    width, _ = image.size
    pixels = image.load()
    columns = [
        x
        for x in range(width)
        if any(is_button_red(pixels[x, y]) for y in range(max(0, top), min(image.size[1], bottom), 2))
    ]
    if not columns:
        return 0, 0, []
    return min(columns), max(columns), columns


def check_manifest(layout: dict[str, Any]) -> list[str]:
    """Bounds, overlap and margin rules, in the addon's own units."""
    findings: list[str] = []
    frame = layout["frame"]
    canvas = layout["canvas"]
    widgets = layout["widgets"]
    right, bottom = frame["x"] + frame["w"], frame["y"] + frame["h"]
    for widget in widgets:
        x0, y0 = widget["x"], widget["y"]
        x1, y1 = x0 + widget["w"], y0 + widget["h"]
        if x0 < -MIN_INSET or y0 < -MIN_INSET or x1 > canvas["width"] + MIN_INSET or y1 > canvas["height"] + MIN_INSET:
            findings.append(f"{widget['name']}: {x1 - x0:g}x{y1 - y0:g} at ({x0:g}, {y0:g}) is off the canvas")
        if x0 < frame["x"] - 0.5 or y0 < frame["y"] - 0.5 or x1 > right + 0.5 or y1 > bottom + 0.5:
            overflow = max(
                frame["x"] - x0,
                frame["y"] - y0,
                x1 - right,
                y1 - bottom,
            )
            detail = (
                f"right edge {x1:g} past the frame's {right:g} by {overflow:g} units"
                if x1 > right
                else f"{x1 - x0:g}x{y1 - y0:g} at ({x0:g}, {y0:g}) leaves the frame"
            )
            findings.append(f"{widget['name']}: {detail}")
    containers = [w for w in widgets if w["role"] == "bar"]
    for widget in widgets:
        for bar in containers:
            if widget is bar:
                continue
            inside_y = bar["y"] <= widget["y"] and widget["y"] + widget["h"] <= bar["y"] + bar["h"]
            inside_x = bar["x"] <= widget["x"] and widget["x"] + widget["w"] <= bar["x"] + bar["w"]
            if not (inside_x and inside_y):
                continue
            inset = min(
                widget["x"] - bar["x"],
                bar["x"] + bar["w"] - (widget["x"] + widget["w"]),
                widget["y"] - bar["y"],
                bar["y"] + bar["h"] - (widget["y"] + widget["h"]),
            )
            if inset < MIN_INSET:
                findings.append(
                    f"{widget['name']}: {inset:g} units from the {bar['name']} edge (minimum {MIN_INSET:g})"
                )
    interactive = [w for w in widgets if w["role"] in INTERACTIVE]
    for index, first in enumerate(interactive):
        for second in interactive[index + 1 :]:
            dx = max(first["x"], second["x"]) - min(first["x"] + first["w"], second["x"] + second["w"])
            dy = max(first["y"], second["y"]) - min(first["y"] + first["h"], second["y"] + second["h"])
            if dx > MIN_GAP or dy > MIN_GAP:
                continue
            if dx > 0 and dy > 0:
                findings.append(
                    f"{first['name']} and {second['name']} are only {min(dx, dy):g} units apart (minimum {MIN_GAP:g})"
                )
            else:
                findings.append(f"{first['name']} and {second['name']} overlap")
    return findings


def check_image(path: Path, layout: dict[str, Any]) -> list[str]:
    """The pixels: button art inside the frame, in two pieces, where the manifest says it is."""
    findings: list[str] = []
    image = load_png(path)
    frame_left, frame_top, frame_right, _ = frame_box(image)
    scale = (frame_right - frame_left) / layout["frame"]["w"]
    offset_y = frame_top - layout["frame"]["y"] * scale
    buttons = [w for w in layout["widgets"] if w["role"] == "button"]
    if not buttons:
        return findings
    top = min(b["y"] for b in buttons)
    bottom = max(b["y"] + b["h"] for b in buttons)
    band_top = round(top * scale + offset_y) - ART_SLOP
    band_bottom = round(bottom * scale + offset_y) + ART_SLOP
    left, right, columns = red_extent(image, band_top, band_bottom)
    if not columns:
        return [f"{path.name}: no button art found in the bottom bar band"]
    if right > frame_right + 1:
        overshoot = (right - frame_right) / scale
        findings.append(
            f"{path.name}: button art reaches x={right}, {overshoot:.0f} units past the frame edge ({frame_right})"
        )
    if left < frame_left - 1:
        findings.append(f"{path.name}: button art starts at x={left}, left of the frame ({frame_left})")
    expected = max(round(b["w"] * scale) for b in buttons)
    widest = max(
        (max(run) - min(run) + 1 for run in _runs(columns) if run),
        default=0,
    )
    if widest and abs(widest - expected) > expected * 0.15:
        findings.append(f"{path.name}: widest button is {widest}px, the manifest's widest is {expected}px")
    runs = [run for run in _runs(columns) if len(run) > ART_SLOP]
    if len(buttons) > 1 and len(runs) < len(buttons):
        findings.append(f"{path.name}: {len(runs)} separate button(s) drawn, the manifest has {len(buttons)}")
    for first, second in zip(runs, runs[1:], strict=False):
        gap = min(second) - max(first) - 1
        if gap < MIN_GAP * scale:
            findings.append(f"{path.name}: {gap}px between buttons (minimum {MIN_GAP * scale:.0f}px)")
    return findings


def _runs(columns: list[int]) -> list[list[int]]:
    """Group the red columns into contiguous runs; a gap between buttons splits them."""
    runs: list[list[int]] = []
    for column in columns:
        if runs and column - runs[-1][-1] <= 2:
            runs[-1].append(column)
        else:
            runs.append([column])
    return runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--dir", type=Path, default=ROOT / "docs" / "screenshots")
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args(argv)
    manifest = args.manifest or args.dir / "layout.json"
    if not manifest.is_file():
        sys.exit(f"visual_audit: {manifest} is missing; run `python3 tools/mockups.py` first")
    layout: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
    findings = check_manifest(layout)
    scenes = layout.get("scenes") or [path.name for path in sorted(args.dir.glob("*.png"))]
    images = [args.dir / name for name in scenes if (args.dir / name).is_file()]
    for path in images:
        findings.extend(check_image(path, layout))
    for finding in findings:
        print(f"visual_audit: {finding}")
    print(
        f"visual_audit: {len(layout['widgets'])} widgets, {len(images)} images, "
        f"{len(findings)} finding{'s' if len(findings) != 1 else ''}"
    )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
