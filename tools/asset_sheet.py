"""Render contact sheets of client atlas art so a human can judge what to keep and what to ban.

    python3 tools/asset_sheet.py --out docs/asset-audit

Each group is a list of prefix filters over UiTextureAtlasElement names. One sheet per group, cells sized to the
art's native pixels (the c60/retail art is authored at 2x), labelled with the element name as SetAtlas takes it.
"""

import argparse
import collections
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "wowmock"))

import wowmock  # noqa: E402

BG = (26, 26, 30)
PANEL = (38, 38, 44)
INK = (232, 232, 236)
DIM = (150, 150, 158)
ACCENT = (255, 209, 0)

GROUPS = collections.OrderedDict(
    [
        ("native-retail", ["common-", "ui-frame-", "!ui-frame-", "minimal-", "tooltip-", "!tooltip-", "128-redbutton"]),
        ("garrison-classhall", ["garr", "classhall", "orderhall"]),
        ("covenant-soulbinds", ["covenant", "soulbind"]),
        ("warfronts", ["warfront"]),
        ("housing", ["housing"]),
        ("pvp-queue", ["pvpqueue", "pvptalents"]),
        ("shop-store", ["shop"]),
        ("dragonriding-plunderstorm", ["dragonriding", "plunderstorm"]),
        ("legacy-old-style", ["legacy"]),
        ("questlog", ["questlog"]),
    ]
)

CELL_W, CELL_H, COLS, PAD, LABEL_H, HEADER = 200, 150, 7, 8, 26, 46


def wrap(text, font, width, draw):
    words, lines, line = text.split("-"), [], ""
    for word in words:
        trial = word if not line else line + "-" + word
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines[:3]


def sheet(ui, group, prefixes, out, font, title_font, per_sheet=21):
    elements = ui.table("UiTextureAtlasElement", key="Name")
    picked = {}
    members_by_element = collections.defaultdict(list)
    for m in ui.table("UiTextureAtlasMember").values():
        members_by_element[m["UiTextureAtlasElementID"]].append(m)

    for name, row in elements.items():
        low = name.lower().lstrip("!")
        if not any(low.startswith(p) for p in prefixes):
            continue
        # Rank by the largest crop, so the sheet shows real controls rather than 4px specks.
        area = max((int(m["Width"]) * int(m["Height"]) for m in members_by_element.get(row["ID"], [])), default=0)
        if area < 256:
            continue
        picked[name] = area
    if not picked:
        print(f"  {group}: nothing matched")
        return None
    names = [n for n, _ in sorted(picked.items(), key=lambda kv: -kv[1])][:per_sheet]

    rows = (len(names) + COLS - 1) // COLS
    width = COLS * CELL_W + PAD * (COLS + 1)
    height = HEADER + rows * (CELL_H + LABEL_H) + PAD
    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((PAD, 12), f"{group}: {len(picked)} matching elements, {len(names)} shown", font=title_font, fill=ACCENT)

    for i, name in enumerate(names):
        cx = PAD + (i % COLS) * (CELL_W + PAD)
        cy = HEADER + (i // COLS) * (CELL_H + LABEL_H)
        draw.rectangle([cx, cy, cx + CELL_W, cy + CELL_H], fill=PANEL)
        try:
            atlas = ui.atlas(name)
        except Exception as exc:  # noqa: BLE001 - one bad element must not lose the sheet
            draw.text((cx + 6, cy + 6), f"{type(exc).__name__}", font=font, fill=(255, 120, 120))
            continue
        img = atlas.image
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img = img.crop(img.getbbox() or (0, 0, 1, 1)) if img.getbbox() else img
        if img.width > CELL_W - 12 or img.height > CELL_H - 12:
            factor = min((CELL_W - 12) / img.width, (CELL_H - 12) / img.height)
            img = img.resize((max(1, int(img.width * factor)), max(1, int(img.height * factor))), Image.LANCZOS)
        canvas.paste(img, (cx + (CELL_W - img.width) // 2, cy + (CELL_H - img.height) // 2), img)
        for li, line in enumerate(wrap(name, font, CELL_W - 8, draw)):
            draw.text((cx + 4, cy + CELL_H + 2 + li * 11), line, font=font, fill=INK)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(f"  {group}: {len(picked)} match, wrote {out.name} ({width}x{height})")
    return out


def own_art_sheet(out, font, title_font):
    """Render the raster addon assets that remain after the texture cleanup."""
    files = []
    for repo in (
        "adventure-guide-forever",
        "atlas-forever",
        "field-guide-forever",
        "hoard-forever",
        "legacy-forever",
        "shortest-path-forever",
        "skillup-forever",
        "tweaks-forever",
    ):
        media = ROOT.parent / repo / "media"
        if media.is_dir():
            files.extend(p for p in media.iterdir() if p.suffix.lower() in {".png", ".tga", ".blp"})
    files.sort(key=lambda p: (p.parent.parent.name, p.name.lower()))
    cell_w, cell_h, columns, pad, title_h = 208, 170, 5, 10, 42
    rows = (len(files) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * cell_w + (columns + 1) * pad, title_h + rows * (cell_h + pad) + pad), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((pad, 10), f"Our shipped raster art: {len(files)} files", font=title_font, fill=ACCENT)
    for index, path in enumerate(files):
        x = pad + index % columns * (cell_w + pad)
        y = title_h + index // columns * (cell_h + pad)
        draw.rectangle((x, y, x + cell_w, y + cell_h), fill=PANEL)
        try:
            art = Image.open(path).convert("RGBA")
            art.thumbnail((cell_w - 20, cell_h - 42), Image.Resampling.LANCZOS)
            canvas.paste(art, (x + (cell_w - art.width) // 2, y + (cell_h - 32 - art.height) // 2), art)
        except Exception as exc:  # noqa: BLE001 - keep the audit sheet complete if one format is unsupported
            draw.text((x + 8, y + 8), f"{type(exc).__name__}", font=font, fill=(255, 120, 120))
        label = f"{path.parent.parent.name}/{path.name}"
        draw.text((x + 5, y + cell_h - 24), label[:32], font=font, fill=INK)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(f"  our-own-art: {len(files)} files, wrote {out.name} ({canvas.width}x{canvas.height})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/asset-audit")
    ap.add_argument("--only", action="append")
    args = ap.parse_args()
    out = Path(args.out)
    ui = wowmock.Ui(scale=2)
    font = ui.font(wowmock.Font(wowmock.FRIZQT, 11))
    title_font = ui.font(wowmock.Font(wowmock.FRIZQT, 20))
    for group, prefixes in GROUPS.items():
        if args.only and group not in args.only:
            continue
        sheet(ui, group, prefixes, out / f"{group}.png", font, title_font)
    if not args.only or "our-own-art" in args.only:
        own_art_sheet(out / "our-own-art.png", font, title_font)


if __name__ == "__main__":
    main()
