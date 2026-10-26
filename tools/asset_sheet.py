"""Render contact sheets of client atlas art so a human can judge what to keep and what to ban.

    python3 tools/asset_sheet.py --out docs/asset-audit

Each group is a list of prefix filters over UiTextureAtlasElement names. One sheet per group, cells sized to the
art's native pixels (the c60/retail art is authored at 2x), labelled with the element name as SetAtlas takes it.
"""
import argparse
import collections
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WOWMOCK = Path(__file__).resolve().parent / "wowmock"
if not WOWMOCK.exists():  # locally: the mock tooling lives in bestiary-forever/tools
    WOWMOCK = Path(__file__).resolve().parents[2] / "bestiary-forever" / "tools" / "wowmock"
sys.path.insert(0, str(WOWMOCK))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import wowmock  # noqa: E402

BG = (26, 26, 30)
PANEL = (38, 38, 44)
INK = (232, 232, 236)
DIM = (150, 150, 158)
ACCENT = (255, 209, 0)

GROUPS = collections.OrderedDict([
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
])

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


def sheet(ui, group, prefixes, out, per_sheet=21):
    elements = ui.table("UiTextureAtlasElement", key="Name")
    picked = {}
    atlases = ui.table("UiTextureAtlas")
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
    font = ImageFont.truetype(str(Path.home() / ".cache/wowmock/1.60.1.70124/files/615960"), 11)
    title_font = ImageFont.truetype(str(Path.home() / ".cache/wowmock/1.60.1.70124/files/615960"), 20)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/asset-audit")
    ap.add_argument("--only", action="append")
    args = ap.parse_args()
    out = Path(args.out)
    ui = wowmock.Ui(scale=2)
    for group, prefixes in GROUPS.items():
        if args.only and group not in args.only:
            continue
        sheet(ui, group, prefixes, out / f"{group}.png")


if __name__ == "__main__":
    main()
