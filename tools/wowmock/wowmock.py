"""wowmock: faithful WoW UI mock screenshots from the client's own art, without running the game.

Everything is fetched from wago.tools for one client build and cached under ~/.cache/wowmock/<build>/.
Coordinates are UI units with a top-left origin and y growing downwards (WoW anchor offsets have y
growing upwards, so negate them when copying from XML/Lua). A Canvas renders at `ui.scale` pixels
per UI unit.

    ui = Ui(scale=2)                       # build defaults to the WoW: Forever client
    ui.atlas("Tooltip-NineSlice-Center")   # element name as the UI code uses it -> Atlas
    ui.texture("interface/common/whiteiconframe.blp") or ui.texture(651080)
    ui.item(4818)                          # Item: name, quality, icon, stats, ...
    FONTS["GameTooltipText"]               # Font objects as Blizzard_Fonts defines them

    tip = tooltip(ui, item_tooltip_lines(ui, ui.item(4818)) + [TooltipLine("|cffffd100Extra|r")])
    bag, slots = container_frame(ui, "Backpack", 133633, [(4818, None), ...], money=12345)
    menu, rows = context_menu(ui, [MenuTitle("Title"), MenuCheckbox("A", True), MenuDivider(), ...])
    scene(ui, [(bag, 0, 0), (tip, x, y)]).save(path)   # layers bottom to top, framed over a backdrop

    art = map_art(ui, 1440)                  # a UiMap's base art; map_overlays + draw_overlay reveal areas
    terrain = minimap_art(ui, 1, 6341.38, 557.68, 233.333)  # world map, north x, west y, radius in yards
    frame, r = world_map_frame(ui, art, ["World", "Kalimdor", "Ashenvale"], arrows=(1, 2))
    tracker, r = objective_tracker(ui, [TrackerModule("Legacy", [TrackerBlock("Novice Mage", ["..."])])])
    atlas_markup("common-dropdown-icon-checkmark-yellow", 14, 14)  # inline atlas texture in Canvas text
    tooltip_backdrop(canvas, x, y, w, h)    # legacy BackdropTemplate's tooltip textures, not NineSlice
    dialog_border(canvas, x, y, w, h); panel_tabs(canvas, x, y, ["HUD", "Windows"], selected=1)
    minimal_slider(canvas, x, y, 180, 32, 100, 50, 150); ui_panel_button(canvas, x, y, w, h, "Okay")
    basic_panel(ui, "Nearby services", 380, 400)  # canvas and frame origin (x, y)
    edit_mode_checkbox(canvas, x, y, "Label", True); edit_mode_selection(canvas, x, y, w, h, "Name")

Widgets return (Canvas, rects) where rects locate interesting parts in UI units, so a scene can place a
tooltip beside a slot or draw an addon's own textures into a slot (see item_button's `artwork` hook).
"""

import csv
import io
import json
import math
import re
import struct
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

BUILD = "1.60.1.70124"
USER_AGENT = "wowmock/1.0"
# WoW: Forever draws its "c60" art (atlas set 1) wherever an atlas element has a member in that set.
FOREVER_ATLAS_SET = 1

FRIZQT = "fonts/frizqt__.ttf"
ARIALN = "fonts/arialn.ttf"


def rgb(hex_colour):
    """(r, g, b) in 0-1 from 'rrggbb'."""
    return tuple(int(hex_colour[i : i + 2], 16) / 255 for i in (0, 2, 4))


# ITEM_QUALITY_COLORS: the client's default C_ColorOverrides colours, used for item names.
QUALITY_TEXT = {
    0: rgb("9d9d9d"),
    1: rgb("ffffff"),
    2: rgb("1eff00"),
    3: rgb("0070dd"),
    4: rgb("a335ee"),
    5: rgb("ff8000"),
}
NORMAL = rgb("ffd200")  # NORMAL_FONT_COLOR, GlobalColor -11776
WHITE = (1.0, 1.0, 1.0)
DISABLED = rgb("808080")


@dataclass(frozen=True)
class Font:
    """A Blizzard font object: file, height in UI units, colour, shadow offset (WoW sign) and outline."""

    path: str
    height: int
    color: tuple = WHITE
    shadow: tuple | None = None
    outline: bool = False


FONTS = {
    "GameFontNormal": Font(FRIZQT, 12, NORMAL, (1, -1)),
    "GameFontHighlight": Font(FRIZQT, 12, WHITE, (1, -1)),
    "GameFontNormalSmall": Font(FRIZQT, 10, NORMAL, (1, -1)),
    "GameFontHighlightSmall": Font(FRIZQT, 10, WHITE, (1, -1)),
    "GameFontDisableSmall": Font(FRIZQT, 10, DISABLED, (1, -1)),
    "GameFontHighlightMedium": Font(FRIZQT, 14, WHITE, (1, -1)),
    "GameFontNormalLarge": Font(FRIZQT, 16, NORMAL, (1, -1)),
    "GameFontHighlightLarge": Font(FRIZQT, 16, WHITE, (1, -1)),
    "GameTooltipHeaderText": Font(FRIZQT, 14, WHITE),
    "GameTooltipText": Font(FRIZQT, 12, WHITE),
    "NumberFontNormal": Font(ARIALN, 14, WHITE, None, True),
}


class Wago:
    """Cached access to wago.tools for one build."""

    def __init__(self, build=BUILD, cache=None):
        self.build = build
        self.cache = Path(cache or Path.home() / ".cache" / "wowmock" / build)
        (self.cache / "files").mkdir(parents=True, exist_ok=True)
        self.paths_file = self.cache / "paths.json"
        self.paths = json.loads(self.paths_file.read_text()) if self.paths_file.exists() else {}

    def fetch(self, url, timeout=180):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    def cached(self, path, url):
        if not path.exists():
            data = self.fetch(url)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_bytes(data)
            temporary.replace(path)
        return path.read_bytes()

    def file(self, fdid):
        # Without &build= the endpoint serves the file from current retail, which differs for UI art.
        url = f"https://wago.tools/api/casc/{fdid}?download&build={self.build}"
        return self.cached(self.cache / "files" / str(fdid), url)

    def db2(self, table):
        url = f"https://wago.tools/db2/{table}/csv?build={self.build}"
        text = self.cached(self.cache / f"{table}.csv", url).decode("utf-8")
        return list(csv.DictReader(io.StringIO(text)))

    def fdid(self, path):
        """File data ID for a client path such as 'interface/icons/inv_misc_bag_08.blp'."""
        path = path.lower().replace("\\", "/")
        if path not in self.paths:
            self.resolve([path])
        return self.paths[path]

    def resolve(self, paths):
        """Look several paths up at once; the search endpoint takes ~30 s per call, so run them in parallel."""
        missing = [p.lower().replace("\\", "/") for p in paths if p.lower().replace("\\", "/") not in self.paths]

        def search(path):
            found = json.loads(self.fetch(f"https://wago.tools/api/files?search={path}"))
            # No match comes back as an empty JSON list rather than an empty object.
            return path, {v: int(k) for k, v in (found or {}).items()}

        with ThreadPoolExecutor(8) as pool:
            for path, found in pool.map(search, missing):
                if path not in found:
                    raise KeyError(f"no file {path!r} in the listfile")
                self.paths.update(found)
        self.paths_file.write_text(json.dumps(self.paths, indent=1, sort_keys=True))


@dataclass
class Atlas:
    """A cropped atlas member: `image` in source pixels, `width`/`height` in UI units, tiling flags."""

    name: str
    image: Image.Image
    width: float
    height: float
    tile_h: bool
    tile_v: bool
    # UiTextureAtlasElementSliceData margins (left, top, right, bottom) in UI units: the atlas stretches as
    # a nine-slice, keeping its corners at native size, as SetAtlas does with TextureSliceMode Stretched.
    slice: tuple | None = None


@dataclass
class Item:
    id: int
    name: str
    quality: int
    icon: int
    item_level: int
    required_level: int
    inventory_type: int
    class_id: int
    subclass_id: int
    bonding: int
    max_count: int
    sell_price: int
    stats: list = field(default_factory=list)  # [(stat type, allocation /10000)]


class Ui:
    """Data + asset access for one build, rendering at `scale` pixels per UI unit."""

    def __init__(self, build=BUILD, scale=2, atlas_set=FOREVER_ATLAS_SET, cache=None):
        self.wago = Wago(build, cache)
        self.scale = scale
        self.atlas_set = atlas_set
        self._tables = {}
        self._textures = {}
        self._fonts = {}

    def table(self, name, key="ID"):
        if name not in self._tables:
            self._tables[name] = {row[key]: row for row in self.wago.db2(name)}
        return self._tables[name]

    def texture(self, ref):
        """RGBA image of a texture by file data ID or client path."""
        fdid = ref if isinstance(ref, int) else self.wago.fdid(ref)
        if fdid not in self._textures:
            self._textures[fdid] = decode_texture(self.wago.file(fdid))
        return self._textures[fdid]

    def font(self, font):
        size = round(font.height * self.scale)
        key = (font.path, size)
        if key not in self._fonts:
            # BASIC layout keeps FreeType's hinted, whole-pixel advances, which is how the client spaces text;
            # RAQM's fractional advances set a row of Friz 12 ~6% narrower than a real capture.
            self._fonts[key] = ImageFont.truetype(
                io.BytesIO(self.wago.file(self.wago.fdid(font.path))), size, layout_engine=ImageFont.Layout.BASIC
            )
        return self._fonts[key]

    def atlas(self, name):
        """Resolve an atlas element name the way SetAtlas does, preferring this client's atlas set."""
        elements = self.table("UiTextureAtlasElement", key="Name")
        element = next((row for n, row in elements.items() if n.lower() == name.lower()), None)
        if element is None:
            raise KeyError(f"no atlas element {name!r}")
        atlases = self.table("UiTextureAtlas")
        canvases = self.table("UiCanvas")
        members = [
            m for m in self.table("UiTextureAtlasMember").values() if m["UiTextureAtlasElementID"] == element["ID"]
        ]

        def logical_size(member):
            # Override size wins; else pixels scaled by the canvas (member's, else the atlas's): canvas 2
            # is 2048 wide, i.e. art authored at 2x.
            canvas = (
                member["UiCanvasID"]
                if member["UiCanvasID"] != "0"
                else atlases[member["UiTextureAtlasID"]]["UiCanvasID"]
            )
            factor = int(canvases[canvas]["Width"]) / 1024 if canvas in canvases else 1
            return (
                int(member["OverrideWidth"]) or int(member["Width"]) / factor,
                int(member["OverrideHeight"]) or int(member["Height"]) / factor,
            )

        def rank(member):
            # The client's own set wins. Outside it, a "-c60" member sits in the default set too but is
            # not what this client draws (its grey tooltip centre proves it), so take the plain one.
            in_set = atlases[member["UiTextureAtlasID"]]["UiTextureAtlasSetID"] == str(self.atlas_set)
            density = int(member["Width"]) / logical_size(member)[0]
            return (in_set, "-c60" not in member["CommittedName"], -abs(density - self.scale), int(member["ID"]))

        member = max(members, key=rank)
        atlas = atlases[member["UiTextureAtlasID"]]
        sheet = self.texture(int(atlas["FileDataID"]))
        # BLP size can differ from the committed atlas size (a mip dropped); scale committed coordinates.
        sx, sy = sheet.width / int(atlas["AtlasWidth"]), sheet.height / int(atlas["AtlasHeight"])
        box = [int(member[k]) for k in ("CommittedLeft", "CommittedTop", "CommittedRight", "CommittedBottom")]
        image = sheet.crop((round(box[0] * sx), round(box[1] * sy), round(box[2] * sx), round(box[3] * sy)))
        width, height = logical_size(member)
        flags = int(member["CommittedFlags"])
        slices = self.table("UiTextureAtlasElementSliceData", key="UiTextureAtlasElementID").get(element["ID"])
        margins = tuple(int(slices[k]) for k in ("Left", "Top", "Right", "Bottom")) if slices else None
        return Atlas(member["CommittedName"], image, width, height, bool(flags & 4), bool(flags & 2), margins)

    def global_color(self, name):
        """(r, g, b, a) of a GlobalColor constant such as UNCOMMON_GREEN_COLOR."""
        for row in self.wago.db2("GlobalColor"):
            if row["LuaConstantName"] == name:
                value = int(row["Color"]) & 0xFFFFFFFF
                return tuple(((value >> shift) & 255) / 255 for shift in (16, 8, 0, 24))
        raise KeyError(name)

    def item(self, item_id):
        sparse = self.table("ItemSparse").get(str(item_id))
        base = self.table("Item").get(str(item_id))
        if sparse is None or base is None:
            raise KeyError(f"item {item_id} is not in this build's Item/ItemSparse")
        icon = int(base["IconFileDataID"]) or self.appearance_icon(item_id)
        stats = [
            (int(sparse[f"StatModifier_bonusStat_{i}"]), int(sparse[f"StatPercentEditor_{i}"]) / 10000)
            for i in range(10)
            if sparse[f"StatPercentEditor_{i}"] != "0"
        ]
        return Item(
            item_id,
            sparse["Display_lang"],
            int(sparse["OverallQualityID"]),
            icon,
            int(sparse["ItemLevel"]),
            int(sparse["RequiredLevel"]),
            int(sparse["InventoryType"]),
            int(base["ClassID"]),
            int(base["SubclassID"]),
            int(sparse["Bonding"]),
            int(sparse["MaxCount"]),
            int(sparse["SellPrice"]),
            stats,
        )

    def appearance_icon(self, item_id):
        """Items with IconFileDataID 0 take their icon from their default appearance."""
        modified = [r for r in self.table("ItemModifiedAppearance").values() if r["ItemID"] == str(item_id)]
        if not modified:
            raise KeyError(f"item {item_id} has no icon and no appearance")
        default = min(modified, key=lambda r: int(r["OrderIndex"]))
        return int(self.table("ItemAppearance")[default["ItemAppearanceID"]]["DefaultIconFileDataID"])

    def stat_value(self, item, allocation):
        """Mainline stat budget: RandPropPoints[ilvl] column for the quality and slot, times the allocation."""
        column = {2: "Good", 3: "Superior", 4: "Epic"}[item.quality]
        slot = SLOT_BUDGET_INDEX[item.inventory_type]
        points = int(self.table("RandPropPoints")[str(item.item_level)][f"{column}_{slot}"])
        return math.floor(points * allocation + 0.5)

    def canvas(self, width, height):
        return Canvas(self, width, height)


# RandPropPoints budget column per inventory type.
SLOT_BUDGET_INDEX = {
    **dict.fromkeys((1, 5, 7, 17, 20), 0),
    **dict.fromkeys((3, 6, 8, 10, 12), 1),
    **dict.fromkeys((2, 9, 11, 14, 16, 22, 23), 2),
    **dict.fromkeys((13, 21), 3),
    **dict.fromkeys((15, 25, 26), 4),
}
INVENTORY_TYPE_NAMES = {
    1: "Head",
    2: "Neck",
    3: "Shoulder",
    4: "Shirt",
    5: "Chest",
    6: "Waist",
    7: "Legs",
    8: "Feet",
    9: "Wrist",
    10: "Hands",
    11: "Finger",
    12: "Trinket",
    13: "One-Hand",
    14: "Off Hand",
    15: "Ranged",
    16: "Back",
    17: "Two-Hand",
    19: "Tabard",
    20: "Chest",
    21: "Main Hand",
    22: "Off Hand",
    23: "Held In Off-hand",
}
STAT_NAMES = {3: "Agility", 4: "Strength", 5: "Intellect", 6: "Spirit", 7: "Stamina"}
# The tooltip lists primary stats before Stamina whatever order the item stores them in.
STAT_ORDER = (4, 3, 5, 7, 6)
BINDING_TEXT = {1: "Binds when picked up", 2: "Binds when equipped", 3: "Binds when used", 4: "Quest Item"}


class Canvas:
    """An RGBA surface addressed in UI units."""

    def __init__(self, ui, width, height):
        self.ui = ui
        self.width, self.height = width, height
        self.image = Image.new("RGBA", (self.px(width), self.px(height)), (0, 0, 0, 0))

    def px(self, value):
        return round(value * self.ui.scale)

    def draw(self, src, x, y, w=None, h=None, color=(1, 1, 1, 1), blend="BLEND", flip_h=False, flip_v=False):
        """Draw a texture or Atlas into a UI rect: stretched, tiled for tiling atlases, or nine-sliced for
        atlases with slice margins."""
        if isinstance(src, Atlas):
            w = src.width if w is None else w
            h = src.height if h is None else h
        width, height = self.px(x + w) - self.px(x), self.px(y + h) - self.px(y)
        if width <= 0 or height <= 0:
            return
        if not isinstance(src, Atlas):
            piece = src.resize((width, height), Image.LANCZOS)
        elif src.slice:
            piece = self.sliced(src, width, height)
        elif src.tile_h or src.tile_v:
            tile = src.image.resize((max(1, self.px(src.width)), max(1, self.px(src.height))), Image.LANCZOS)
            tile = tile.resize(
                (tile.width if src.tile_h else width, tile.height if src.tile_v else height), Image.LANCZOS
            )
            piece = Image.new("RGBA", (width, height))
            for tx in range(0, width, tile.width):
                for ty in range(0, height, tile.height):
                    piece.paste(tile, (tx, ty))
        else:
            piece = src.image.resize((width, height), Image.LANCZOS)
        if flip_h:
            piece = piece.transpose(Image.FLIP_LEFT_RIGHT)
        if flip_v:
            piece = piece.transpose(Image.FLIP_TOP_BOTTOM)
        self.composite(tint(piece, color), self.px(x), self.px(y), blend)

    def sliced(self, atlas, width, height):
        image = atlas.image
        density = image.width / atlas.width
        left, top, right, bottom = atlas.slice
        src_x = [0, round(left * density), image.width - round(right * density), image.width]
        src_y = [0, round(top * density), image.height - round(bottom * density), image.height]
        dst_x = [0, self.px(left), width - self.px(right), width]
        dst_y = [0, self.px(top), height - self.px(bottom), height]
        piece = Image.new("RGBA", (width, height))
        for i in range(3):
            for j in range(3):
                size = (dst_x[i + 1] - dst_x[i], dst_y[j + 1] - dst_y[j])
                if size[0] > 0 and size[1] > 0:
                    cell = image.crop((src_x[i], src_y[j], src_x[i + 1], src_y[j + 1]))
                    piece.paste(cell.resize(size, Image.LANCZOS), (dst_x[i], dst_y[j]))
        return piece

    def composite(self, piece, left, top, blend="BLEND"):
        layer = Image.new("RGBA", self.image.size)
        layer.paste(piece, (left, top))
        if blend == "ADD":
            alpha = layer.getchannel("A")
            added = Image.composite(layer, Image.new("RGBA", layer.size), alpha).convert("RGB")
            merged = ImageChops.add(self.image.convert("RGB"), added)
            merged.putalpha(ImageChops.lighter(self.image.getchannel("A"), alpha))
            self.image = merged
        else:
            self.image = Image.alpha_composite(self.image, layer)

    def fill(self, x, y, w, h, color):
        piece = Image.new("RGBA", (self.px(x + w) - self.px(x), self.px(y + h) - self.px(y)), rgba255(color))
        self.composite(piece, self.px(x), self.px(y))

    def paste(self, other, x, y):
        self.composite(other.image, self.px(x), self.px(y))

    def mask(self, mask_image, x, y, w, h):
        """Multiply everything already inside the rect by a mask texture's alpha (MaskTexture)."""
        alpha = mask_image.getchannel("A").resize((self.px(w), self.px(h)), Image.LANCZOS)
        full = Image.new("L", self.image.size, 0)
        full.paste(alpha, (self.px(x), self.px(y)))
        self.image.putalpha(ImageChops.multiply(self.image.getchannel("A"), full))

    def text_width(self, text, font):
        face = self.ui.font(font)
        return sum(
            face.getlength(run) / self.ui.scale if isinstance(run, str) else inline_texture_size(self.ui, run, font)[0]
            for run, _ in text_runs(text, font.color)
        )

    def text(self, x, y, text, font, color=None, box_height=None, justify="LEFT", width=None):
        """Draw a FontString: `text` may carry |cffRRGGBB...|r colour escapes and |A...|a / |T...|t inline
        textures (centred on the glyphs). The line box is `font.height` tall, vertically centred in
        `box_height` if given; x is the left edge (or the box of `width` for CENTER/RIGHT). Returns the
        text width."""
        runs = text_runs(text, color or font.color)
        face = self.ui.font(font)
        total = self.text_width(text, font)
        if justify == "CENTER":
            x += (width - total) / 2
        elif justify == "RIGHT":
            x += width - total
        top = y + ((box_height - font.height) / 2 if box_height else 0)
        layer = Image.new("RGBA", self.image.size)
        draw = ImageDraw.Draw(layer)
        stroke = max(1, round(self.ui.scale)) if font.outline else 0
        cursor = x
        icons = []
        # The client centres an inline texture on the glyphs, not on the line box: Friz's ascent puts the
        # digits' ink ~1.5 units below the box centre, and a real capture's coins sit level with the digits.
        _, ink_top, _, ink_bottom = face.getbbox("0")
        ink_centre = (ink_top + ink_bottom) / 2 / self.ui.scale
        for run, run_color in runs:
            if not isinstance(run, str):
                w, h = inline_texture_size(self.ui, run, font)
                icons.append((run, cursor + run.offset[0], top + ink_centre - h / 2 - run.offset[1], w, h))
                cursor += w
                continue
            position = (self.px(cursor), self.px(top))
            if font.shadow:
                offset = (self.px(font.shadow[0]), -self.px(font.shadow[1]))
                draw.text((position[0] + offset[0], position[1] + offset[1]), run, font=face, fill=(0, 0, 0, 255))
            draw.text(
                position, run, font=face, fill=rgba255(run_color), stroke_width=stroke, stroke_fill=(0, 0, 0, 255)
            )
            cursor += face.getlength(run) / self.ui.scale
        self.image = Image.alpha_composite(self.image, layer)
        for run, left, icon_top, w, h in icons:
            self.draw(inline_texture_image(self.ui, run), left, icon_top, w, h)
        return total

    def nine_slice(self, layout, x, y, w, h, center_color=(1, 1, 1, 1), border_color=(1, 1, 1, 1)):
        """NineSliceUtil.ApplyLayout for a frame at (x, y, w, h); layout mirrors NineSliceLayouts.lua."""
        mirror = layout.get("mirrorLayout", False)
        pieces = {}
        for name in ("TopLeftCorner", "TopRightCorner", "BottomLeftCorner", "BottomRightCorner"):
            spec = layout[name]
            atlas = self.ui.atlas(spec["atlas"])
            ox, oy = spec.get("x", 0), -spec.get("y", 0)
            left = x + ox if "Left" in name else x + w + ox - atlas.width
            top = y + oy if "Top" in name else y + h + oy - atlas.height
            pieces[name] = (atlas, left, top)

        def rect(name):
            atlas, left, top = pieces[name]
            return left, top, left + atlas.width, top + atlas.height

        tl, tr, bl, br = (rect(n) for n in ("TopLeftCorner", "TopRightCorner", "BottomLeftCorner", "BottomRightCorner"))
        edges = {}

        def offsets(spec):
            return spec.get("x", 0), -spec.get("y", 0), spec.get("x1", 0), -spec.get("y1", 0)

        for name, place in (
            ("TopEdge", lambda a, o: (tl[2] + o[0], tl[1] + o[1], tr[0] + o[2] - tl[2] - o[0], a.height)),
            ("BottomEdge", lambda a, o: (bl[2] + o[0], bl[3] + o[1] - a.height, br[0] + o[2] - bl[2] - o[0], a.height)),
            ("LeftEdge", lambda a, o: (tl[0] + o[0], tl[3] + o[1], a.width, bl[1] + o[3] - tl[3] - o[1])),
            ("RightEdge", lambda a, o: (tr[2] + o[0] - a.width, tr[3] + o[1], a.width, br[1] + o[3] - tr[3] - o[1])),
        ):
            if name in layout:
                atlas = self.ui.atlas(layout[name]["atlas"])
                edges[name] = (atlas, place(atlas, offsets(layout[name])))
        if "Center" in layout:
            o = offsets(layout["Center"])
            atlas = self.ui.atlas(layout["Center"]["atlas"])
            self.draw(
                atlas,
                tl[2] + o[0],
                tl[3] + o[1],
                br[0] + o[2] - tl[2] - o[0],
                br[1] + o[3] - tl[3] - o[1],
                center_color,
            )
        flips = {
            "TopRightCorner": (True, False),
            "BottomLeftCorner": (False, True),
            "BottomRightCorner": (True, True),
            "BottomEdge": (False, True),
            "RightEdge": (True, False),
        }
        # A piece's own mirrorLayout overrides the layout's (NineSlice.lua SetupTextureCoordinates).
        for name, (atlas, box) in edges.items():
            fh, fv = flips.get(name, (False, False)) if layout[name].get("mirrorLayout", mirror) else (False, False)
            self.draw(atlas, *box, border_color, flip_h=fh, flip_v=fv)
        for name, (atlas, left, top) in pieces.items():
            fh, fv = flips.get(name, (False, False)) if layout[name].get("mirrorLayout", mirror) else (False, False)
            self.draw(atlas, left, top, color=border_color, flip_h=fh, flip_v=fv)

    def save(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.image.save(path, optimize=True)


def decode_texture(data):
    """Decode a BLP/PNG/etc. to RGBA. Pillow reads BLP2 palette and DXT encodings but not encoding 3,
    uncompressed BGRA, which much newer UI art uses; that one is read here from the first mip."""
    if data[:4] == b"BLP2" and data[4 + 4] == 3:
        width, height = struct.unpack_from("<II", data, 12)
        offset, size = struct.unpack_from("<I", data, 20)[0], struct.unpack_from("<I", data, 84)[0]
        return Image.frombytes("RGBA", (width, height), data[offset : offset + size], "raw", "BGRA")
    return Image.open(io.BytesIO(data)).convert("RGBA")


def rgba255(color):
    r, g, b, *a = color
    return tuple(round(c * 255) for c in (r, g, b, a[0] if a else 1))


def tint(image, color):
    """Vertex colour: multiply channels by (r, g, b[, a])."""
    if tuple(color) in ((1, 1, 1), (1, 1, 1, 1)):
        return image
    r, g, b, *a = color
    bands = [
        band.point(lambda v, f=f: round(v * f))
        for band, f in zip(image.split(), (r, g, b, a[0] if a else 1), strict=True)
    ]
    return Image.merge("RGBA", bands)


COLOUR_ESCAPE = re.compile(r"\|c([0-9a-fA-F]{8})|\|r")


def parse_colours(text, default):
    """Split '|cffRRGGBBtext|r' markup into [(text, (r, g, b, a))]."""
    runs, color, position = [], default, 0
    for match in COLOUR_ESCAPE.finditer(text):
        if match.start() > position:
            runs.append((text[position : match.start()], color))
        code = match.group(1)
        color = (*rgb(code[2:]), int(code[:2], 16) / 255) if code else default
        position = match.end()
    if position < len(text):
        runs.append((text[position:], color))
    return runs


def colored(text, color):
    """WoW colour escape, as addons build it with string.format('|cff%02x%02x%02x', floor(c * 255))."""
    return "|cff{:02x}{:02x}{:02x}{}|r".format(*(math.floor(c * 255) for c in color[:3]), text)


@dataclass(frozen=True)
class InlineTexture:
    """An |A (atlas) or |T (file) escape: height/width 0 mean the font height / the texture's aspect;
    `crop` is (texW, texH, left, right, top, bottom) texel coordinates from a |T escape; `offset` is its
    (offsetX, offsetY), which moves the drawn icon (y up) without changing the space it takes in the line."""

    atlas: str | None
    file: str | None
    height: int
    width: int
    crop: tuple | None = None
    offset: tuple = (0, 0)


INLINE_TEXTURE = re.compile(r"\|A:([^:|]+):(-?\d+):(-?\d+)[^|]*\|a|\|T([^:|]+)((?::-?\d+)*)\|t")


def atlas_markup(atlas, width, height):
    """CreateAtlasMarkup(atlas, width, height): note the escape stores height first."""
    return f"|A:{atlas}:{height}:{width}|a"


def text_runs(text, default):
    """parse_colours, with inline textures split out as InlineTexture runs."""
    runs = []
    for run, color in parse_colours(text, default):
        position = 0
        for match in INLINE_TEXTURE.finditer(run):
            if match.start() > position:
                runs.append((run[position : match.start()], color))
            if match.group(1):
                runs.append((InlineTexture(match.group(1), None, int(match.group(2)), int(match.group(3))), color))
            else:
                numbers = [int(n) for n in match.group(5).split(":")[1:]]
                height, width = (numbers + [0, 0])[:2]
                crop = tuple(numbers[4:10]) if len(numbers) >= 10 else None
                offset = tuple((numbers + [0, 0, 0, 0])[2:4])
                runs.append((InlineTexture(None, match.group(4), height, width or height, crop, offset), color))
            position = match.end()
        if position < len(run):
            runs.append((run[position:], color))
    return runs


def inline_texture_image(ui, run):
    if run.atlas:
        return ui.atlas(run.atlas)
    image = ui.texture(run.file.lower().replace("\\", "/") + ("" if "." in run.file[-5:] else ".blp"))
    if run.crop:
        tw, th, left, right, top, bottom = run.crop
        sx, sy = image.width / tw, image.height / th
        image = image.crop((round(left * sx), round(top * sy), round(right * sx), round(bottom * sy)))
    return image


def inline_texture_size(ui, run, font):
    height = run.height or font.height
    if run.width:
        return run.width, height
    image = inline_texture_image(ui, run)  # an Atlas (UI units) or an Image (texels): both have the aspect
    return height * image.width / image.height, height


# ---------------------------------------------------------------------------------------------- backdrop


def backdrop(ui, width, height, inner=(0.13, 0.14, 0.16), outer=(0.04, 0.045, 0.05)):
    """A dim, soft radial gradient to sit UI on, standing in for a blurred game world."""
    small = Image.new("RGB", (64, 64))
    for py in range(64):
        for px in range(64):
            d = min(1, math.hypot((px - 32) / 32, (py - 36) / 40))
            small.putpixel(
                (px, py), tuple(round(255 * (i + (o - i) * d**1.4)) for i, o in zip(inner, outer, strict=True))
            )
    canvas = ui.canvas(width, height)
    canvas.image = small.resize(canvas.image.size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(4)).convert("RGBA")
    return canvas


def scene(ui, layers, margin=24):
    """Compose [(canvas, x, y)] bottom to top over a backdrop cropped to what they draw, plus `margin`.
    Positions are free: widgets can be placed relative to each other and the scene is framed after."""
    boxes = []
    for canvas, x, y in layers:
        left, top, right, bottom = canvas.image.getbbox()
        boxes.append((x + left / ui.scale, y + top / ui.scale, x + right / ui.scale, y + bottom / ui.scale))
    left, top = min(b[0] for b in boxes) - margin, min(b[1] for b in boxes) - margin
    right, bottom = max(b[2] for b in boxes) + margin, max(b[3] for b in boxes) + margin
    result = backdrop(ui, right - left, bottom - top)
    for canvas, x, y in layers:
        result.paste(canvas, x - left, y - top)
    return result


# ------------------------------------------------------------------------------------------------ tooltip

TOOLTIP_LAYOUT = {  # NineSliceLayouts.TooltipDefaultLayout
    "TopLeftCorner": {"atlas": "Tooltip-NineSlice-CornerTopLeft"},
    "TopRightCorner": {"atlas": "Tooltip-NineSlice-CornerTopRight"},
    "BottomLeftCorner": {"atlas": "Tooltip-NineSlice-CornerBottomLeft"},
    "BottomRightCorner": {"atlas": "Tooltip-NineSlice-CornerBottomRight"},
    "TopEdge": {"atlas": "_Tooltip-NineSlice-EdgeTop"},
    "BottomEdge": {"atlas": "_Tooltip-NineSlice-EdgeBottom"},
    "LeftEdge": {"atlas": "!Tooltip-NineSlice-EdgeLeft"},
    "RightEdge": {"atlas": "!Tooltip-NineSlice-EdgeRight"},
    "Center": {"atlas": "Tooltip-NineSlice-Center", "x": -4, "y": 4, "x1": 4, "y1": -4},
}
TOOLTIP_PADDING = 10
TOOLTIP_LINE_GAP = 2
# Measured on a real SkillUp capture once text used the client's whole-pixel advances: a double line's
# left and right texts sit 40 units apart when that line sets the tooltip's width.
TOOLTIP_COLUMN_GAP = 40


@dataclass
class TooltipLine:
    """One GameTooltip line; `money` (copper) renders SetTooltipMoney's coin frame after `left`."""

    left: str
    color: tuple = WHITE
    right: str | None = None
    right_color: tuple = WHITE
    money: int | None = None


def coin_parts(copper):
    gold, silver, copper = copper // 10000, copper // 100 % 100, copper % 100
    return [
        (value, atlas)
        for value, atlas in ((gold, "coin-gold"), (silver, "coin-silver"), (copper, "coin-copper"))
        if value
    ]


def money_width(canvas, copper):
    # SmallMoneyFrame: each coin button is its digits plus a 13-unit icon, 4 units apart.
    parts = coin_parts(copper)
    digits = FONTS["NumberFontNormal"]
    return sum(canvas.text_width(str(value), digits) + 13 for value, _ in parts) + 4 * (len(parts) - 1)


def draw_money(canvas, x, y, copper, height=13):
    digits = FONTS["NumberFontNormal"]
    for value, atlas in coin_parts(copper):
        x += canvas.text(x, y, str(value), digits, box_height=height)
        canvas.draw(canvas.ui.atlas(atlas), x, y, 13, 13)
        x += 13 + 4


def tooltip(ui, lines):
    """A GameTooltip: first line in GameTooltipHeaderText, the rest GameTooltipText."""
    measure = ui.canvas(1, 1)
    fonts = [FONTS["GameTooltipHeaderText"]] + [FONTS["GameTooltipText"]] * (len(lines) - 1)
    widths = []
    for line, font in zip(lines, fonts, strict=True):
        width = measure.text_width(line.left, font)
        if line.money is not None:
            width += 4 + money_width(measure, line.money)
        if line.right:
            width += TOOLTIP_COLUMN_GAP + measure.text_width(line.right, font)
        widths.append(width)
    inner_height = sum(font.height for font in fonts) + TOOLTIP_LINE_GAP * (len(lines) - 1)
    width = math.ceil(max(widths)) + 2 * TOOLTIP_PADDING
    height = inner_height + 2 * TOOLTIP_PADDING
    canvas = ui.canvas(width, height)
    background = ui.global_color("TOOLTIP_DEFAULT_BACKGROUND_COLOR")
    canvas.nine_slice(TOOLTIP_LAYOUT, 0, 0, width, height, center_color=(*background[:3], 1))
    y = TOOLTIP_PADDING
    for line, font in zip(lines, fonts, strict=True):
        drawn = canvas.text(TOOLTIP_PADDING, y, line.left, font, line.color)
        if line.money is not None:
            draw_money(canvas, TOOLTIP_PADDING + drawn + 4, y - 0.5, line.money)
        if line.right:
            canvas.text(
                TOOLTIP_PADDING,
                y,
                line.right,
                font,
                line.right_color,
                justify="RIGHT",
                width=width - 2 * TOOLTIP_PADDING,
            )
        y += font.height + TOOLTIP_LINE_GAP
    return canvas


def item_tooltip_lines(ui, item, player_level=60):
    """Lines of a Mainline item tooltip from the item's data: name, item level, binding, uniqueness, slot and
    armour type, primary stats and requirement, and sell price. Armour, weapon damage, durability and
    spell effects are not derived; add them by hand if the item has them."""
    lines = [TooltipLine(item.name, QUALITY_TEXT[item.quality]), TooltipLine(f"Item Level {item.item_level}", NORMAL)]
    if item.bonding:
        lines.append(TooltipLine(BINDING_TEXT[item.bonding]))
    if item.max_count == 1:
        lines.append(TooltipLine("Unique"))
    if item.inventory_type:
        subclass = ""
        if item.class_id in (2, 4) and item.subclass_id:
            subclasses = [r for r in ui.table("ItemSubClass").values() if r["ClassID"] == str(item.class_id)]
            subclass = next(r["DisplayName_lang"] for r in subclasses if r["SubClassID"] == str(item.subclass_id))
        lines.append(TooltipLine(INVENTORY_TYPE_NAMES[item.inventory_type], right=subclass or None))
    known = sorted((s for s in item.stats if s[0] in STAT_NAMES), key=lambda s: STAT_ORDER.index(s[0]))
    unknown = [s for s in item.stats if s[0] not in STAT_NAMES]
    if unknown:
        raise ValueError(f"item {item.id} has stats wowmock cannot name: {unknown}")
    for stat, allocation in known:
        lines.append(TooltipLine(f"+{ui.stat_value(item, allocation)} {STAT_NAMES[stat]}"))
    if item.required_level > 1:
        met = player_level >= item.required_level
        lines.append(TooltipLine(f"Requires Level {item.required_level}", WHITE if met else rgb("ff2020")))
    if item.sell_price:
        lines.append(TooltipLine("Sell Price:", money=item.sell_price))
    return lines


# ------------------------------------------------------------------------------------------ item buttons

ITEM_BUTTON = 37
BAG_QUALITY_COLORS = {1: "COMMON_GRAY_COLOR", 2: "UNCOMMON_GREEN_COLOR", 3: "RARE_BLUE_COLOR", 4: "EPIC_PURPLE_COLOR"}


def item_button(canvas, x, y, item=None, count=None, hover=False, artwork=None, junk=False):
    """ContainerFrameItemButtonTemplate at (x, y). `artwork(canvas, x, y)` draws in the ARTWORK layer, above
    the icon and normal texture and below the quality border, where an addon's CreateTexture(nil, "ARTWORK")
    lands. `junk` shows the JunkIcon coin (OVERLAY 5, above the quality border)."""
    ui = canvas.ui
    if item is None:
        canvas.draw(ui.atlas("bags-item-slot64"), x, y, ITEM_BUTTON, ITEM_BUTTON)
    else:
        canvas.draw(ui.texture(item.icon), x, y, ITEM_BUTTON, ITEM_BUTTON)
    canvas.draw(
        ui.texture("interface/buttons/ui-quickslot2.blp"),
        x + (ITEM_BUTTON - 64) / 2,
        y + (ITEM_BUTTON - 64) / 2 + 1,
        64,
        64,
    )
    if artwork:
        artwork(canvas, x, y)
    if count and count > 1:
        # NumberFontNormal anchored BOTTOMRIGHT -5, 2.
        canvas.text(
            x, y + ITEM_BUTTON - 2 - 14, str(count), FONTS["NumberFontNormal"], justify="RIGHT", width=ITEM_BUTTON - 5
        )
    if item is not None and item.quality in BAG_QUALITY_COLORS:
        border = ui.global_color(BAG_QUALITY_COLORS[item.quality])
        canvas.draw(ui.texture("interface/common/whiteiconframe.blp"), x, y, ITEM_BUTTON, ITEM_BUTTON, border)
    if junk:
        # ContainerFrame.xml: bags-junkcoin at its atlas size, TOPLEFT (1, 0).
        canvas.draw(ui.atlas("bags-junkcoin"), x + 1, y)
    if hover:
        canvas.draw(
            ui.texture("interface/buttons/buttonhilight-square.blp"), x, y, ITEM_BUTTON, ITEM_BUTTON, blend="ADD"
        )


# ---------------------------------------------------------------------------------------- container frame

HELD_BAG_LAYOUT = {  # NineSliceLayouts.HeldBagLayout
    "TopLeftCorner": {"atlas": "ui-frame-portraitmetal-cornertopleftsmall", "x": -13, "y": 16},
    "TopRightCorner": {"atlas": "UI-Frame-Metal-CornerTopRight", "x": 4, "y": 16},
    "BottomLeftCorner": {"atlas": "UI-Frame-Metal-CornerBottomLeft", "x": -13, "y": -3},
    "BottomRightCorner": {"atlas": "UI-Frame-Metal-CornerBottomRight", "x": 4, "y": -3},
    "TopEdge": {"atlas": "_UI-Frame-Metal-EdgeTop"},
    "BottomEdge": {"atlas": "_UI-Frame-Metal-EdgeBottom"},
    "LeftEdge": {"atlas": "!UI-Frame-Metal-EdgeLeft"},
    "RightEdge": {"atlas": "!UI-Frame-Metal-EdgeRight"},
}
CONTAINER_WIDTH = 178
ITEM_SPACING = 5
# How far the frame's art reaches past its rect (the metal corners), so the canvas holds all of it.
CONTAINER_MARGIN = 24


def container_frame(ui, title, portrait, slots, money, columns=4, hover=None, artwork=None, junk=()):
    """The Mainline backpack (ContainerFrameBackpackTemplate). `slots` is [(item_id | None, count | None)] in
    slot order; `hover` is the index of a slot under the cursor; `artwork(canvas, x, y, index)` draws into
    a slot's ARTWORK layer; `junk` holds the indices whose junk coin shows. Returns the frame and slot rectangles
    in canvas units."""
    rows = math.ceil(len(slots) / columns)
    items_height = rows * ITEM_BUTTON + (rows - 1) * ITEM_SPACING
    money_height = 13
    height = items_height + (9 + 48 + 30) + money_height
    width = CONTAINER_WIDTH
    m = CONTAINER_MARGIN
    canvas = ui.canvas(width + 2 * m, height + 2 * m)

    background = ui.global_color("PANEL_BACKGROUND_COLOR")
    bg_left, bg_top, bg_right, bg_bottom = m + 2, m + 20, m + width - 2, m + height - 3
    corner_left, corner_right = (
        ui.atlas("uiframebackground-nineslice-cornerbottomleft"),
        ui.atlas("uiframebackground-nineslice-cornerbottomright"),
    )
    canvas.fill(bg_left, bg_top, bg_right - bg_left, bg_bottom - corner_left.height - bg_top, background)
    canvas.fill(
        bg_left + corner_left.width,
        bg_bottom - corner_left.height,
        bg_right - bg_left - corner_left.width - corner_right.width,
        corner_left.height,
        background,
    )
    canvas.draw(corner_left, bg_left, bg_bottom - corner_left.height, color=background)
    canvas.draw(corner_right, bg_right - corner_right.width, bg_bottom - corner_right.height, color=background)

    # SetPortraitTextureSizeAndOffset(36, -4, 1), masked by CircleMask inset (2, 0, -2, 4).
    portrait_layer = ui.canvas(width + 2 * m, height + 2 * m)
    portrait_layer.draw(ui.texture(portrait), m - 4, m - 1, 36, 36)
    portrait_layer.mask(ui.texture("interface/characterframe/tempportraitalphamask.blp"), m - 4 + 2, m - 1, 32, 32)
    canvas.nine_slice(HELD_BAG_LAYOUT, m, m, width, height)
    canvas.paste(portrait_layer, 0, 0)

    canvas.text(m + 35, m + 1 + 5, title, FONTS["GameFontNormal"], justify="CENTER", width=width - 35 - 24)
    canvas.draw(ui.atlas("RedButton-Exit"), m + width + 1 - 24, m, 24, 24)

    search_x, search_y = m + 42, m + 37
    canvas.draw(ui.atlas("common-search-border-left"), search_x - 5, search_y - 1, 8, 20)
    canvas.draw(ui.atlas("common-search-border-middle"), search_x + 3, search_y - 1, 96 - 8 - 3, 20)
    canvas.draw(ui.atlas("common-search-border-right"), search_x + 96 - 8, search_y - 1, 8, 20)
    canvas.draw(ui.atlas("common-search-magnifyingglass"), search_x + 1, search_y + 5, 10, 10)
    canvas.text(search_x + 16, search_y, "Search", FONTS["GameFontDisableSmall"], box_height=18)
    canvas.draw(ui.atlas("bags-button-autosort-up"), m + width - 9 - 28, m + 34, 28, 26)

    money_left, money_right, money_top = m + 8, m + width - 8, m + height - 8 - money_height
    coinbox_top = money_top + (money_height - 17) / 2
    canvas.draw(ui.atlas("common-coinbox-left"), money_left, coinbox_top, 8, 17)
    canvas.draw(ui.atlas("_common-coinbox-center"), money_left + 8, coinbox_top, money_right - money_left - 16, 17)
    canvas.draw(ui.atlas("common-coinbox-right"), money_right - 8, coinbox_top, 8, 17)
    draw_money(canvas, money_right - 13 - money_width(canvas, money), money_top, money)

    rects = []
    items_right, items_bottom = m + width - 8, money_top - 4
    for index, (item_id, count) in enumerate(slots):
        # Laid out BottomRightToTopLeft in reverse slot order, so slot 1 lands top-left.
        from_end = len(slots) - 1 - index
        x = items_right - ITEM_BUTTON - (from_end % columns) * (ITEM_BUTTON + ITEM_SPACING)
        y = items_bottom - ITEM_BUTTON - (from_end // columns) * (ITEM_BUTTON + ITEM_SPACING)
        item = ui.item(item_id) if item_id else None
        hook = (lambda c, bx, by, i=index: artwork(c, bx, by, i)) if artwork and item else None
        item_button(canvas, x, y, item, count, hover == index, hook, index in junk and item is not None)
        rects.append((x, y, ITEM_BUTTON, ITEM_BUTTON))
    return canvas, {"frame": (m, m, width, height), "slots": rects}


# -------------------------------------------------------------------------------------------- context menu


@dataclass
class MenuTitle:
    text: str


@dataclass
class MenuButton:
    text: str
    submenu: bool = False
    hover: bool = False


@dataclass
class MenuCheckbox:
    text: str
    checked: bool
    hover: bool = False


@dataclass
class MenuDivider:
    pass


MENU_INSET = (8, 8, 8, 15)  # MenuStyle1Mixin:GetInset left, top, right, bottom
MENU_CHILD_PADDING = 20  # MenuStyle1Mixin:GetChildExtentPadding width
MENU_ROW = 20  # MenuVariants.CreateFontString height
MENU_DIVIDER = 13


def context_menu(ui, entries):
    """A Blizzard_Menu context menu in MenuStyle1. Returns (canvas, {"menu": rect, "rows": [rect]})."""
    measure = ui.canvas(1, 1)
    text_font = FONTS["GameFontHighlight"]
    tick = ui.atlas("common-dropdown-ticksquare")

    def extent(entry):
        if isinstance(entry, MenuDivider):
            return 0, MENU_DIVIDER
        width = measure.text_width(entry.text, text_font)
        if isinstance(entry, MenuCheckbox):
            width += tick.width + 7
        if isinstance(entry, MenuButton) and entry.submenu:
            width += 16
        return width, MENU_ROW

    extents = [extent(e) for e in entries]
    child_width = round(max(w for w, _ in extents)) + MENU_CHILD_PADDING
    left, top, right, bottom = MENU_INSET
    width = left + child_width + right
    height = top + sum(h for _, h in extents) + bottom
    margin = 12
    canvas = ui.canvas(width + 2 * margin, height + 2 * margin)
    # MenuStyle1Mixin:Generate: common-dropdown-bg from (-10, 3) to (10, -3) at alpha .925.
    canvas.draw(ui.atlas("common-dropdown-bg"), margin - 10, margin - 3, width + 20, height + 6, (1, 1, 1, 0.925))
    y = margin + top
    rows = []
    for entry, (_, row_height) in zip(entries, extents, strict=True):
        x = margin + left
        if isinstance(entry, MenuDivider):
            canvas.draw(
                ui.texture("interface/common/ui-tooltipdivider-transparent.blp"), x, y, child_width, MENU_DIVIDER
            )
        else:
            if getattr(entry, "hover", False):
                canvas.draw(
                    ui.texture("interface/questframe/ui-questtitlehighlight.blp"),
                    x,
                    y,
                    child_width,
                    row_height,
                    blend="ADD",
                )
            if isinstance(entry, MenuTitle):
                canvas.text(x, y, entry.text, text_font, NORMAL, box_height=MENU_ROW)
            elif isinstance(entry, MenuCheckbox):
                tick_top = y + (MENU_ROW - tick.height) / 2
                canvas.draw(tick, x, tick_top)
                if entry.checked:
                    check = ui.atlas("common-dropdown-icon-checkmark-yellow")
                    canvas.draw(
                        check, x + (tick.width - check.width) / 2 + 2, tick_top + (tick.height - check.height) / 2 - 1
                    )
                canvas.text(x + tick.width + 7, y - 1, entry.text, text_font, box_height=MENU_ROW)
            else:
                canvas.text(x, y, entry.text, text_font, box_height=MENU_ROW)
                if entry.submenu:
                    canvas.draw(
                        ui.texture("interface/chatframe/chatframeexpandarrow.blp"), x + child_width - 16, y + 2, 16, 16
                    )
        rows.append((x, y, child_width, row_height))
        y += row_height
    return canvas, {"menu": (margin, margin, width, height), "rows": rows}


# ------------------------------------------------------------------------------------------------ text wrap


def wrap_text(canvas, text, font, width, max_lines=0):
    """Word-wrap a FontString to `width` UI units the way the client does (greedy, at spaces); with
    `max_lines` (SetMaxLines), the last kept line is cut with '...'. Returns the lines."""
    lines, line = [], ""
    for word in text.split(" "):
        candidate = f"{line} {word}" if line else word
        if not line or canvas.text_width(candidate, font) <= width:
            line = candidate
        else:
            lines.append(line)
            line = word
    lines.append(line)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and canvas.text_width(last + "...", font) > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "..."
    return lines


# ------------------------------------------------------------------------------------------------ world map


def power_of_two(pixels):
    size = 16
    while size < pixels:
        size *= 2
    return size


def minimap_art(ui, map_id, x, y, radius):
    """Stitch pinned WDT MAID minimap tiles around north-growing x / west-growing y.

    The eighth FileDataID is minimapTexture; the seventh is the terrain normal map.
    Radius is in world yards. The returned square is north-up, before the UI mask.
    """
    world = ui.table("Map")[str(map_id)]
    wdt = ui.wago.file(int(world["WdtFileDataID"]))
    position, maid = 0, None
    while position + 8 <= len(wdt):
        magic, size = struct.unpack_from("<4sI", wdt, position)
        if magic in (b"DIAM", b"MAID"):
            maid = wdt[position + 8 : position + 8 + size]
        position += size + 8
    assert maid and len(maid) == 64 * 64 * 32, "expected WDT MAID with minimapTexture entries"
    unit = 1600 / 3
    left, top = 32 - (y + radius) / unit, 32 - (x + radius) / unit
    right, bottom = left + radius * 2 / unit, top + radius * 2 / unit
    x0, y0 = math.floor(left), math.floor(top)
    image = Image.new("RGBA", ((math.ceil(right) - x0) * 256, (math.ceil(bottom) - y0) * 256))
    for y in range(y0, math.ceil(bottom)):
        for x in range(x0, math.ceil(right)):
            fdid = struct.unpack_from("<8I", maid, (y * 64 + x) * 32)[7]
            assert fdid, f"no minimap texture at {x},{y}"
            image.paste(ui.texture(fdid).resize((256, 256), Image.Resampling.LANCZOS), ((x - x0) * 256, (y - y0) * 256))
    return image.crop(tuple(round(v * 256) for v in (left - x0, top - y0, right - x0, bottom - y0)))


def map_art_id(ui, ui_map_id):
    """The UiMapArt a uiMap shows with no phase."""
    rows = [r for r in ui.table("UiMapXMapArt").values() if r["UiMapID"] == str(ui_map_id) and r["PhaseID"] == "0"]
    if not rows:
        raise KeyError(f"uiMap {ui_map_id} has no map art")
    return min(rows, key=lambda r: int(r["ID"]))["UiMapArtID"]


def map_art(ui, ui_map_id):
    """A uiMap's base art (layer 0) as one RGBA image in canvas pixels (1002x668 for a zone): its
    UiMapArtTile files laid out on the UiMapArtStyleLayer grid, the last row/column cropped."""
    art = map_art_id(ui, ui_map_id)
    style = ui.table("UiMapArt")[art]["UiMapArtStyleID"]
    layer = next(
        r for r in ui.table("UiMapArtStyleLayer").values() if r["UiMapArtStyleID"] == style and r["LayerIndex"] == "0"
    )
    width, height = int(layer["LayerWidth"]), int(layer["LayerHeight"])
    tile_w, tile_h = int(layer["TileWidth"]), int(layer["TileHeight"])
    image = Image.new("RGBA", (width, height))
    for tile in ui.table("UiMapArtTile").values():
        if tile["UiMapArtID"] == art and tile["LayerIndex"] == "0":
            texture = ui.texture(int(tile["FileDataID"])).resize((tile_w, tile_h), Image.LANCZOS)
            image.paste(texture, (int(tile["ColIndex"]) * tile_w, int(tile["RowIndex"]) * tile_h))
    return image


@dataclass
class MapOverlay:
    """A WorldMapOverlay: the art the map reveals over an explored area, in canvas pixels."""

    id: int
    offset_x: int
    offset_y: int
    width: int
    height: int
    hit: tuple  # left, top, right, bottom
    tiles: list  # FileDataIDs, row-major

    @property
    def key(self):
        """offsetX:offsetY:width:height, as C_MapExplorationInfo textures identify an overlay."""
        return f"{self.offset_x}:{self.offset_y}:{self.width}:{self.height}"


def map_overlays(ui, ui_map_id):
    """Every exploration overlay of a uiMap's art, ordered by ID."""
    art = map_art_id(ui, ui_map_id)
    tiles = {}
    for tile in ui.table("WorldMapOverlayTile").values():
        if tile["LayerIndex"] == "0":
            tiles.setdefault(tile["WorldMapOverlayID"], []).append(tile)
    overlays = []
    for row in ui.table("WorldMapOverlay").values():
        if row["UiMapArtID"] != art:
            continue
        ordered = sorted(tiles.get(row["ID"], []), key=lambda t: (int(t["RowIndex"]), int(t["ColIndex"])))
        overlays.append(
            MapOverlay(
                int(row["ID"]),
                int(row["OffsetX"]),
                int(row["OffsetY"]),
                int(row["TextureWidth"]),
                int(row["TextureHeight"]),
                tuple(int(row[k]) for k in ("HitRectLeft", "HitRectTop", "HitRectRight", "HitRectBottom")),
                [int(t["FileDataID"]) for t in ordered],
            )
        )
    return sorted(overlays, key=lambda o: o.id)


def draw_overlay(ui, image, offset_x, offset_y, width, height, tiles, color=(1, 1, 1, 1), tile_size=256):
    """Composite an overlay's tiles onto map art in place, as MapExplorationPinMixin:RefreshOverlays lays
    them out: row-major tiles of `tile_size`, the last in a row/column drawn at its remaining pixels from
    the top-left of its power-of-two file. `color` is the textures' vertex colour."""
    wide, tall = math.ceil(width / tile_size), math.ceil(height / tile_size)
    for row in range(tall):
        tile_h = height - row * tile_size if row == tall - 1 else tile_size
        for col in range(wide):
            tile_w = width - col * tile_size if col == wide - 1 else tile_size
            texture = ui.texture(tiles[row * wide + col])
            file_w, file_h = (power_of_two(tile_w), power_of_two(tile_h))
            sx, sy = texture.width / file_w, texture.height / file_h
            piece = texture.crop((0, 0, round(tile_w * sx), round(tile_h * sy))).resize((tile_w, tile_h), Image.LANCZOS)
            layer = Image.new("RGBA", image.size)
            layer.paste(tint(piece, color), (offset_x + col * tile_size, offset_y + row * tile_size))
            image.alpha_composite(layer)
    return image


WORLD_MAP_WIDTH, WORLD_MAP_HEIGHT = 702, 534  # WorldMapFrame minimizedWidth/Height
WORLD_MAP_SPACER = 67  # TITLE_CANVAS_SPACER_FRAME_HEIGHT
WORLD_MAP_NAVBAR_X_OFFSET = -50  # Camelot WorldMapConstants.NAVBAR_X_OFFSET
PORTRAIT_FRAME_LAYOUT = {  # NineSliceLayouts.PortraitFrameTemplateMinimizable
    "TopLeftCorner": {"atlas": "UI-Frame-PortraitMetal-CornerTopLeft", "x": -13, "y": 16},
    "TopRightCorner": {"atlas": "UI-Frame-Metal-CornerTopRightDouble", "x": 4, "y": 16},
    "BottomLeftCorner": {"atlas": "UI-Frame-Metal-CornerBottomLeft", "x": -13, "y": -3},
    "BottomRightCorner": {"atlas": "UI-Frame-Metal-CornerBottomRight", "x": 4, "y": -3},
    "TopEdge": {"atlas": "_UI-Frame-Metal-EdgeTop"},
    "BottomEdge": {"atlas": "_UI-Frame-Metal-EdgeBottom"},
    "LeftEdge": {"atlas": "!UI-Frame-Metal-EdgeLeft"},
    "RightEdge": {"atlas": "!UI-Frame-Metal-EdgeRight"},
}
WORLD_MAP_MARGIN = 16  # the metal corners overhang the frame by up to 16


def tiled(canvas, texture, x, y, w, h, tile_w, tile_h, coords=(0, 1, 0, 1)):
    """A horizTile/vertTile texture region: `coords` (left, right, top, bottom) of the file, repeated every
    tile_w x tile_h UI units and clipped to the rect."""
    left, right, top, bottom = coords
    piece = texture.crop(
        (
            round(left * texture.width),
            round(top * texture.height),
            round(right * texture.width),
            round(bottom * texture.height),
        )
    )
    tile = piece.resize((max(1, canvas.px(tile_w)), max(1, canvas.px(tile_h))), Image.LANCZOS)
    width, height = canvas.px(x + w) - canvas.px(x), canvas.px(y + h) - canvas.px(y)
    area = Image.new("RGBA", (width, height))
    for tx in range(0, width, tile.width):
        for ty in range(0, height, tile.height):
            area.paste(tile, (tx, ty))
    canvas.composite(area, canvas.px(x), canvas.px(y))


def crop_coords(texture, left, right, top, bottom):
    """SetTexCoord: the file region, flipped when right < left or bottom < top."""
    box = [
        round(left * texture.width),
        round(top * texture.height),
        round(right * texture.width),
        round(bottom * texture.height),
    ]
    piece = texture.crop((min(box[0], box[2]), min(box[1], box[3]), max(box[0], box[2]), max(box[1], box[3])))
    if right < left:
        piece = piece.transpose(Image.FLIP_LEFT_RIGHT)
    if bottom < top:
        piece = piece.transpose(Image.FLIP_TOP_BOTTOM)
    return piece


def nav_bar(canvas, x, y, w, h, names, arrows=()):
    """NavBarTemplate as the world map uses it: the home button (names[0]) then one NavButtonTemplate per
    map, the last selected. `arrows` holds the names whose button has a dropdown arrow (listFunc)."""
    ui = canvas.ui
    tile = ui.texture("interface/helpframe/cs_helptextures_tile.blp")
    sheet = ui.texture("interface/helpframe/cs_helptextures.blp")
    tiled(canvas, tile, x, y, w, h, 128, h, (0, 1, 0.1875, 0.25390625))
    # WorldMapNavBarTemplate's inset border, below and beside the bar.
    canvas.draw(ui.atlas("!UI-Frame-InnerLeftTile"), x - 3, y, 3, h)
    canvas.draw(ui.atlas("!UI-Frame-InnerRightTile"), x + w, y, 3, h)
    canvas.draw(ui.atlas("UI-Frame-InnerBotLeftCorner"), x - 3, y + h - 3)
    canvas.draw(ui.atlas("UI-Frame-InnerBotRight"), x + w - 3, y + h - 3)
    canvas.draw(ui.atlas("_UI-Frame-InnerBotTile"), x + 3, y + h, w - 6, 3)
    font = FONTS["GameFontNormal"]
    button_h = 30
    top = y + (h - button_h) / 2
    # Home: its width (and texcoords) come from the "Home" text it loads with, before SetText.
    home_w = min(128, canvas.text_width("Home", font) + 50)
    buttons, cursor = [], x + home_w - 15  # home.xoffset: the next button starts under its tip
    for index, name in enumerate(names[1:], start=1):
        width = canvas.text_width(name, font) + (53 if name in arrows else 30)
        buttons.append((name, cursor, width, index == len(names) - 1))
        cursor += width
    # NavBar_CheckLength raises each button above the one to its right, so draw right to left: each
    # button's arrow (and the home button's tip) overlaps its right-hand neighbour.
    for name, left, width, last in reversed(buttons):
        tiled(canvas, tile, left, top, width, button_h, 128, button_h, (0, 1, 0.0625, 0.12109375))
        if last:
            canvas.draw(crop_coords(sheet, 0.00195313, 0.25195313, 0.375, 0.640625), left, top, width, button_h)
        canvas.draw(crop_coords(sheet, 0.88867188, 0.9296875, 0.296875, 0.53125), left + width, top, 21, 30)
        canvas.text(left + 20, top, name, font, box_height=button_h)
        if name in arrows:
            arrow = crop_coords(
                ui.texture("interface/buttons/squarebuttontextures.blp"), 0.453125, 0.640625, 0.203125, 0.015625
            )
            # MenuArrowButton 27x31, RIGHT at the button's TOPRIGHT (-2, -15); the art 12x12 at CENTER (0, -1).
            canvas.draw(arrow, left + width - 2 - 27 / 2 - 6, top + 15 - 6 + 1, 12, 12)
    tex_left = 0.703125 - home_w / 128 * 0.25
    canvas.draw(crop_coords(sheet, tex_left, 0.703125, 0.0078125, 0.2421875), x, top, home_w, button_h)
    canvas.draw(ui.texture("interface/common/shadowoverlay-left.blp"), x, top, 30, 30)
    canvas.text(x + 10, top, names[0], font, box_height=button_h)
    tiled(canvas, tile, x, y, w, h, 128, h, (0, 1, 0.2578125, 0.32421875))


def world_map_frame(
    ui, map_image, nav, arrows=(), title="Map & Quest Log", portrait="interface/questframe/ui-questlog-bookicon.blp"
):
    """WorldMapFrame minimized with the quest log hidden, as the Camelot (Forever) UI lays it out: metal
    portrait frame, rock background, NavBar (`nav` = home label then map names), the tracking options
    dropdown beside it, and `map_image` (canvas pixels, e.g. map_art) fitted to the scroll container.

    Returns (canvas, rects), rects in canvas UI units: "frame" (x, y, w, h), "container" (the canvas
    clip rect) and "map" (x, y, w, h where the map image landed, so a normalised position (nx, ny) is at
    (x + nx * w, y + ny * h)), plus "scale" (UI units per canvas pixel)."""
    m = WORLD_MAP_MARGIN
    w, h = WORLD_MAP_WIDTH, WORLD_MAP_HEIGHT
    canvas = ui.canvas(w + 2 * m, h + 2 * m)
    # Bg is reparented to the map, under the canvas; tiled at its file's pixel size on screen.
    rock = ui.texture("interface/framegeneral/ui-background-rock.blp")
    tiled(canvas, rock, m + 2, m + 21, w - 4, h - 23, rock.width / ui.scale, rock.height / ui.scale)
    container = (m + 2, m + WORLD_MAP_SPACER, w - 5, h - 2 - WORLD_MAP_SPACER)
    cx, cy, cw, ch = container
    scale = min(cw / map_image.width, ch / map_image.height)
    mw, mh = map_image.width * scale, map_image.height * scale
    mx, my = cx + (cw - mw) / 2, cy + (ch - mh) / 2
    canvas.draw(map_image, mx, my, mw, mh)
    # InsetBorderTop along the spacer's bottom.
    canvas.draw(ui.atlas("_UI-Frame-InnerTopTile"), m + 2, m + 63, cw, 3)
    nav_x, nav_y = m + 2 + 64, m + 25
    nav_w, nav_h = (m + w - 3 + WORLD_MAP_NAVBAR_X_OFFSET) - nav_x, (m + WORLD_MAP_SPACER - 9) - nav_y
    nav_bar(canvas, nav_x, nav_y, nav_w, nav_h, nav, arrows)
    # WorldMapTrackingOptionsButton: LEFT to the NavBar's RIGHT (10, -2), its icon at (4, -6) of 32x32.
    options_x, options_y = nav_x + nav_w + 10, nav_y + nav_h / 2 - 16 + 2
    canvas.draw(ui.atlas("common-dropdown-a-button"), options_x + 4, options_y + 6)
    # Side panel toggle (quest log hidden): 32x32 at the container's BOTTOMRIGHT (-2, 1).
    toggle_x, toggle_y = cx + cw - 2 - 32, cy + ch - 1 - 32
    corner = ui.atlas("MapCornerShadow-Right")
    canvas.draw(corner, toggle_x + 32 + 2 - corner.width, toggle_y + 32 + 1 - corner.height)
    canvas.draw(ui.atlas("QuestCollapse-Show-Up"), toggle_x, toggle_y, 32, 32)
    canvas.nine_slice(camelot_layout(PORTRAIT_FRAME_LAYOUT), m, m, w, h)
    # Portrait (level 400, over the border), masked to a circle.
    portrait_layer = ui.canvas(w + 2 * m, h + 2 * m)
    portrait_layer.draw(ui.texture(portrait), m - 5, m - 7, 62, 62)
    portrait_layer.mask(ui.texture("interface/characterframe/tempportraitalphamask.blp"), m - 3, m - 7, 58, 58)
    canvas.paste(portrait_layer, 0, 0)
    canvas.text(m + 58, m + 1 + 5, title, FONTS["GameFontNormal"], justify="CENTER", width=w - 58 - 24)
    close_x = m + w + 1 - 24
    canvas.draw(ui.atlas("RedButton-Exit"), close_x, m, 24, 24)
    canvas.draw(ui.atlas("RedButton-Expand"), close_x - 1 - 24, m, 24, 24)
    rects = {"frame": (m, m, w, h), "container": container, "map": (mx, my, mw, mh), "scale": scale}
    return canvas, rects


# --------------------------------------------------------------------------------------- objective tracker

TRACKER_WIDTH = 260
TRACKER_TOP_PADDING = 38  # BASE_TOP_PADDING
TRACKER_MODULE_SPACING = 10
TRACKER_HEADER_HEIGHT = 25  # module headerHeight: what the layout counts (the header frame is 26)
TRACKER_FROM_HEADER = 10
TRACKER_BLOCK_X = 20
TRACKER_FROM_BLOCK = 10
TRACKER_LINE_SPACING = 4
TRACKER_LINE = rgb("cccccc")  # OBJECTIVE_TRACKER_COLOR.Normal
FONTS.setdefault("ObjectiveTrackerHeaderFont", Font(FRIZQT, 14, NORMAL, (1, -1)))
FONTS.setdefault("ObjectiveTrackerLineFont", Font(FRIZQT, 12, WHITE, (1, -1)))
FONTS.setdefault("GameFontNormalLarge", Font(FRIZQT, 16, NORMAL, (1, -1)))  # SystemFont_Shadow_Large


@dataclass
class TrackerBlock:
    """One block: a header (may carry markup) and objective lines; dash=False is OBJECTIVE_DASH_STYLE_HIDE."""

    header: str
    lines: list = field(default_factory=list)  # [str] or [(str, dash)]


@dataclass
class TrackerModule:
    header: str
    blocks: list = field(default_factory=list)


def objective_tracker(ui, modules, title="All Objectives", container=True):
    """ObjectiveTrackerFrame: the container header, then each module's header and blocks, laid out as
    ObjectiveTrackerModuleMixin/BlockMixin do (block headers and lines wrap to two lines). The background
    nine-slice sits at alpha 0 by default, so nothing is drawn behind the text.

    Set container=False for a crop beginning at the first module header.
    Returns (canvas, rects): "modules" lists each module's header rect (x, y, w, h), for an addon's own
    header decorations; "blocks" lists each block's (x, y, w, h)."""
    measure = ui.canvas(1, 1)
    line_font = FONTS["ObjectiveTrackerLineFont"]
    header_font = FONTS["ObjectiveTrackerHeaderFont"]
    block_w = TRACKER_WIDTH - TRACKER_BLOCK_X
    dash_w = measure.text_width("- ", line_font)
    header_color = ui.global_color("OBJECTIVE_TRACKER_BLOCK_HEADER_COLOR")[:3]
    layout, y = [], TRACKER_TOP_PADDING if container else 0
    for module in modules:
        blocks, block_y, contents = [], y + 26 + TRACKER_FROM_HEADER, TRACKER_HEADER_HEIGHT
        for block in module.blocks:
            header_lines = wrap_text(measure, block.header, line_font, block_w, 2)
            height = len(header_lines) * line_font.height
            lines = []
            for line in block.lines:
                text, dash = line if isinstance(line, tuple) else (line, True)
                wrapped = wrap_text(measure, text, line_font, block_w - dash_w, 2)
                lines.append((wrapped, dash, block_y + height + TRACKER_LINE_SPACING))
                height += len(wrapped) * line_font.height + TRACKER_LINE_SPACING
            blocks.append((header_lines, lines, block_y, height))
            contents += height + (TRACKER_FROM_BLOCK if len(blocks) > 1 else TRACKER_FROM_HEADER)
            block_y += height + TRACKER_FROM_BLOCK
        layout.append((module, y, blocks))
        y += contents + TRACKER_MODULE_SPACING
    margin = 8
    canvas = ui.canvas(TRACKER_WIDTH + 2 * margin, y + 2 * margin)
    ox, oy = margin, margin
    if container:
        header = ui.atlas("ui-questtracker-primary-objective-header")
        canvas.draw(header, ox + (TRACKER_WIDTH - header.width) / 2, oy + (32 - header.height) / 2)
        canvas.text(ox + 7, oy, title, header_font, box_height=32)
        button = ui.atlas("ui-questtrackerbutton-collapse-all")
        canvas.draw(button, ox + TRACKER_WIDTH - 1 - button.width, oy + (32 - button.height) / 2)
    rects = {"modules": [], "blocks": []}
    for module, top, blocks in layout:
        background = ui.atlas("UI-QuestTracker-Secondary-Objective-Header")
        canvas.draw(background, ox + (TRACKER_WIDTH - background.width) / 2, oy + top + (26 - background.height) / 2)
        # ObjectiveTrackerModuleHeaderTemplate caps its single line at 200 and scales down to 12.
        module_font = header_font
        while module_font.height > 12 and measure.text_width(module.header, module_font) > 200:
            module_font = Font(module_font.path, module_font.height - 1, module_font.color, module_font.shadow)
        canvas.text(ox + 7, oy + top, module.header, module_font, box_height=26)
        minimize = ui.atlas("ui-questtrackerbutton-secondary-collapse")
        canvas.draw(minimize, ox + TRACKER_WIDTH + 1 - minimize.width, oy + top + (26 - minimize.height) / 2)
        rects["modules"].append((ox, oy + top, TRACKER_WIDTH, 26))
        for header_lines, lines, block_top, height in blocks:
            bx = ox + TRACKER_BLOCK_X
            for index, text in enumerate(header_lines):
                canvas.text(bx, oy + block_top + index * line_font.height, text, line_font, header_color)
            for wrapped, dash, line_top in lines:
                if dash:
                    canvas.text(bx, oy + line_top - 1, "- ", line_font, TRACKER_LINE)
                for index, text in enumerate(wrapped):
                    canvas.text(bx + dash_w, oy + line_top + index * line_font.height, text, line_font, TRACKER_LINE)
            rects["blocks"].append((bx, oy + block_top, TRACKER_WIDTH - TRACKER_BLOCK_X, height))
    return canvas, rects


# ----------------------------------------------------------------------------- Camelot panels and widgets

# Blizzard_SharedXML/Camelot/NineSliceLayoutOverrides.lua: Forever's metal corners are cut differently from
# Mainline's, so every layout that uses them is shifted at load. (piece, atlas, x adjustment, y override)
CAMELOT_NINE_SLICE_OFFSETS = (
    ("TopRightCorner", "UI-Frame-Metal-CornerTopRight", -2, None),
    ("TopRightCorner", "UI-Frame-Metal-CornerTopRightDouble", -2, None),
    ("BottomLeftCorner", "UI-Frame-Metal-CornerBottomLeft", None, -8),
    ("BottomRightCorner", "UI-Frame-Metal-CornerBottomRight", -2, -8),
)


def camelot_layout(layout):
    """A NineSliceLayouts entry as the Forever client ends up with it after its offset overrides."""
    result = {name: dict(piece) if isinstance(piece, dict) else piece for name, piece in layout.items()}
    for name, atlas, x_adjustment, y_override in CAMELOT_NINE_SLICE_OFFSETS:
        piece = result.get(name)
        if piece and piece["atlas"] == atlas:
            if x_adjustment is not None:
                piece["x"] = piece.get("x", 0) + x_adjustment
            if y_override is not None:
                piece["y"] = y_override
    return result


PORTRAIT_FRAME_TEMPLATE_LAYOUT = camelot_layout(
    {  # NineSliceLayouts.PortraitFrameTemplate
        "TopLeftCorner": {"atlas": "UI-Frame-PortraitMetal-CornerTopLeft", "x": -13, "y": 16},
        "TopRightCorner": {"atlas": "UI-Frame-Metal-CornerTopRight", "x": 4, "y": 16},
        "BottomLeftCorner": {"atlas": "UI-Frame-Metal-CornerBottomLeft", "x": -13, "y": -3},
        "BottomRightCorner": {"atlas": "UI-Frame-Metal-CornerBottomRight", "x": 4, "y": -3},
        "TopEdge": {"atlas": "_UI-Frame-Metal-EdgeTop"},
        "BottomEdge": {"atlas": "_UI-Frame-Metal-EdgeBottom"},
        "LeftEdge": {"atlas": "!UI-Frame-Metal-EdgeLeft"},
        "RightEdge": {"atlas": "!UI-Frame-Metal-EdgeRight"},
    }
)
INSET_FRAME_LAYOUT = {  # NineSliceLayouts.InsetFrameTemplate
    "TopLeftCorner": {"atlas": "UI-Frame-InnerTopLeft"},
    "TopRightCorner": {"atlas": "UI-Frame-InnerTopRight"},
    "BottomLeftCorner": {"atlas": "UI-Frame-InnerBotLeftCorner", "y": -1},
    "BottomRightCorner": {"atlas": "UI-Frame-InnerBotRight", "y": -1},
    "TopEdge": {"atlas": "_UI-Frame-InnerTopTile"},
    "BottomEdge": {"atlas": "_UI-Frame-InnerBotTile"},
    "LeftEdge": {"atlas": "!UI-Frame-InnerLeftTile"},
    "RightEdge": {"atlas": "!UI-Frame-InnerRightTile"},
}


def portrait_frame_art(canvas, x, y, w, h, portrait, title, layout=PORTRAIT_FRAME_TEMPLATE_LAYOUT):
    """The top levels of a PortraitFrameTemplate at (x, y, w, h): the portrait (level 400, 62x62 at (-5, 7),
    masked to a circle), the metal NineSlice over it (500), then the title and close button (510). Draw the
    frame's Bg and contents first. `portrait` is a texture path/fdid or an already loaded Image."""
    ui = canvas.ui
    layer = ui.canvas(canvas.width, canvas.height)
    image = portrait if isinstance(portrait, Image.Image) else ui.texture(portrait)
    layer.draw(image, x - 5, y - 7, 62, 62)
    layer.mask(ui.texture("interface/characterframe/tempportraitalphamask.blp"), x - 3, y - 7, 58, 58)
    canvas.paste(layer, 0, 0)
    canvas.nine_slice(layout, x, y, w, h)
    # TitleContainer (58, -1) to (-24, -1), 20 high; GameFontNormal at its TOP (0, -5).
    canvas.text(x + 58, y + 1 + 5, title, FONTS["GameFontNormal"], justify="CENTER", width=w - 58 - 24)
    # UIPanelCloseButtonDefaultAnchors, Camelot: TOPRIGHT (-2, 1).
    canvas.draw(ui.atlas("RedButton-Exit"), x + w - 2 - 24, y - 1, 24, 24)


def coin_texture_string(copper, height=14):
    """C_CurrencyInfo.GetCoinTextureString: '<n>|T<coin>:h:h:2:0|t' per non-zero denomination, joined with
    spaces (the offset nudges each coin 2 units right of its slot)."""
    gold, silver, rest = copper // 10000, copper // 100 % 100, copper % 100
    parts = [
        f"{value}|TInterface\\MoneyFrame\\UI-{name}Icon:{height}:{height}:2:0|t"
        for value, name in ((gold, "Gold"), (silver, "Silver"), (rest, "Copper"))
        if value
    ]
    return " ".join(parts) or f"0|TInterface\\MoneyFrame\\UI-CopperIcon:{height}:{height}:2:0|t"


def three_slice_button(canvas, x, y, w, h, text, font=None, atlas="128-RedButton"):
    """ThreeSliceButtonTemplate (BigRedThreeSlice: SharedButton*Template): Left/Right caps scaled to the
    button height, trimmed evenly when they don't fit, the tiling centre between; text centred."""
    ui = canvas.ui
    left, right, centre = ui.atlas(f"{atlas}-Left"), ui.atlas(f"{atlas}-Right"), ui.atlas(f"_{atlas}-Center")
    scale = h / left.height
    lw, rw = left.width * scale, right.width * scale
    if lw + rw > w:
        # ThreeSliceButtonMixin:UpdateScale's trimming, for the common case of caps of unequal width.
        extra = lw + rw - w
        if lw - extra > rw:
            nl, nr = lw - extra, rw
        elif rw - extra > lw:
            nl, nr = lw, rw - extra
        else:
            extra -= abs(lw - rw)
            nl = nr = min(lw, rw) - extra / 2
        left_img = left.image.crop((0, 0, round(left.image.width * nl / lw), left.image.height))
        right_img = right.image.crop(
            (round(right.image.width * (1 - nr / rw)), 0, right.image.width, right.image.height)
        )
        lw, rw = nl, nr
    else:
        left_img, right_img = left.image, right.image
    canvas.draw(left_img, x, y, lw, h)
    canvas.draw(right_img, x + w - rw, y, rw, h)
    if w - lw - rw > 0:
        canvas.draw(Atlas(centre.name, centre.image, centre.width * scale, h, True, False), x + lw, y, w - lw - rw, h)
    font = font or FONTS["GameFontNormal"]
    canvas.text(x, y, text, font, justify="CENTER", width=w, box_height=h)


def search_box(canvas, x, y, w, h=20, instructions="Search"):
    """SearchBoxTemplate: the common-search-border three-slice (Left 8 wide at LEFT -5), magnifier 10x10 at
    LEFT (1, -1), and the grey instructions from x + 16."""
    ui = canvas.ui
    canvas.draw(ui.atlas("common-search-border-left"), x - 5, y, 8, h)
    canvas.draw(ui.atlas("common-search-border-middle"), x + 3, y, w - 8 - 3, h)
    canvas.draw(ui.atlas("common-search-border-right"), x + w - 8, y, 8, h)
    canvas.draw(ui.atlas("common-search-magnifyingglass"), x + 1, y + (h - 10) / 2 + 1, 10, 10)
    font = FONTS["GameFontDisableSmall"]
    canvas.text(x + 16, y, instructions, font, (0.35, 0.35, 0.35), box_height=h)


def filter_dropdown(canvas, right, top, text="Filter"):
    """WowStyle1FilterDropdownTemplate placed by its TOPRIGHT: 18 high, text width + 60 wide, the
    common-dropdown-b-button art 4 units outside it. Returns its rect."""
    ui = canvas.ui
    font = FONTS["GameFontNormal"]
    w, h = canvas.text_width(text, font) + 60, 18
    x = right - w
    canvas.draw(ui.atlas("common-dropdown-b-button"), x - 4, top - 4, w + 8, h + 8)
    canvas.text(x, top, text, font, justify="CENTER", width=w, box_height=20)
    return x, top, w, h


def minimal_scrollbar(canvas, x, y, h, visible=1.0, offset=0.0):
    """MinimalScrollBar: the 8-wide track (19 in from each end) and both steppers. With `visible` < 1 (the
    shown fraction of the content) it draws the small thumb, `minThumbExtent` 23, `offset` along the track."""
    ui = canvas.ui
    top, bottom = ui.atlas("minimal-scrollbar-track-top"), ui.atlas("minimal-scrollbar-track-bottom")
    track_top, track_bottom = y + 19, y + h - 19
    canvas.draw(top, x, track_top)
    canvas.draw(bottom, x, track_bottom - bottom.height)
    canvas.draw(
        ui.atlas("!minimal-scrollbar-track-middle"),
        x,
        track_top + top.height,
        8,
        track_bottom - bottom.height - track_top - top.height,
    )
    if visible < 1:
        track = track_bottom - track_top
        extent = max(23, track * visible)
        thumb_top = track_top + (track - extent) * offset
        begin, end = ui.atlas("minimal-scrollbar-small-thumb-top"), ui.atlas("minimal-scrollbar-small-thumb-bottom")
        canvas.draw(begin, x, thumb_top)
        canvas.draw(end, x, thumb_top + extent - end.height)
        middle = ui.atlas("minimal-scrollbar-small-thumb-middle")
        canvas.draw(middle, x, thumb_top + begin.height, 8, extent - begin.height - end.height)
    back, forward = ui.atlas("minimal-scrollbar-arrow-top"), ui.atlas("minimal-scrollbar-arrow-bottom")
    canvas.draw(back, x + 4 - back.width / 2, y)
    canvas.draw(forward, x + 4 - forward.width / 2, y + h - forward.height)


def minimal_checkbox(canvas, x, y, label, size=26, checked=False, font=None, color=None):
    """CheckboxWithLabelTemplate (MinimalCheckboxArtTemplate) at (x, y), its label 3 units to the right."""
    ui = canvas.ui
    canvas.draw(ui.atlas("checkbox-minimal"), x, y, size, size)
    if checked:
        canvas.draw(ui.atlas("checkmark-minimal"), x, y, size, size)
    font = font or FONTS["GameFontNormalSmall"]
    canvas.text(x + size + 3, y, label, font, color, box_height=size)


def side_tab(canvas, x, y, icon, selected=False):
    """LargeSideTabButtonTemplate at its TOPLEFT (a profession or panel tab on a frame's right edge), in the
    Camelot art: 55x55, the icon 50x50 at CENTER (-4, 0) masked by common-sidetab-mask. Returns its height."""
    ui = canvas.ui
    back = ui.atlas("common-sidetab")
    w, h = back.width, back.height - 5
    cx, cy = x + w / 2, y + h / 2
    canvas.draw(back, cx - back.width / 2, cy - back.height / 2)
    layer = ui.canvas(canvas.width, canvas.height)
    image = icon if isinstance(icon, Image.Image) else ui.texture(icon)
    image = image.crop(
        (
            round(image.width * 0.03125),
            round(image.height * 0.03125),
            round(image.width * 0.96875),
            round(image.height * 0.96875),
        )
    )
    layer.draw(image, cx - 4 - 25, cy - 25, 50, 50)
    mask = ui.atlas("common-sidetab-mask")
    layer.mask(mask.image, cx - mask.width / 2, cy - mask.height / 2, mask.width, mask.height)
    canvas.paste(layer, 0, 0)
    if selected:
        chosen = ui.atlas("common-sidetab-selected")
        canvas.draw(chosen, cx - chosen.width / 2, cy - chosen.height / 2)
    return h


def tooltip_backdrop(canvas, x, y, w, h, background=(0, 0, 0, 1), border=(1, 1, 1, 1), edge=12):
    """BackdropTemplate's UI-Tooltip-Background/Border at edgeSize=12, insets=3, tileSize=16.

    Backdrop.lua uses eight strips in a legacy border file, with 1/128 horizontal and 1/16 vertical
    texel insets. This is different art from GameTooltip's modern atlas NineSlice.
    """
    ui = canvas.ui
    # ManifestInterfaceData IDs avoid a slow path lookup and still select the pinned build's bytes.
    # Tint the background separately, so an alpha multiplier doesn't affect pre-existing scene art.
    bg = ui.canvas(w - 6, h - 6)
    tiled(bg, ui.texture(137056), 0, 0, w - 6, h - 6, 16, 16)
    bg.image = tint(bg.image, background)
    canvas.paste(bg, x + 3, y + 3)
    texture = ui.texture(137057)
    for index, (left, top) in enumerate(
        ((x, y), (x + w - edge, y), (x, y + h - edge), (x + w - edge, y + h - edge)), 4
    ):
        piece = crop_coords(texture, index / 8 + 1 / 128, (index + 1) / 8 - 1 / 128, 1 / 16, 15 / 16)
        canvas.draw(piece, left, top, edge, edge, border)
    for index, (left, top, length, horizontal) in enumerate(
        (
            (x, y + edge, h - 2 * edge, False),
            (x + w - edge, y + edge, h - 2 * edge, False),
            (x + edge, y, w - 2 * edge, True),
            (x + edge, y + h - edge, w - 2 * edge, True),
        )
    ):
        piece = crop_coords(texture, index / 8 + 1 / 128, (index + 1) / 8 - 1 / 128, 0, 1)
        if horizontal:
            # Backdrop.lua maps the strip's left edge to the top, with V decreasing rightward.
            piece = piece.transpose(Image.Transpose.ROTATE_270)
        layer = ui.canvas(length if horizontal else edge, edge if horizontal else length)
        tiled(layer, tint(piece, border), 0, 0, layer.width, layer.height, edge, edge)
        canvas.paste(layer, left, top)


# ------------------------------------------------------------------------------------------------ dialogs

DIALOG_LAYOUT = {  # NineSliceLayouts.Dialog (Camelot leaves it alone)
    "TopLeftCorner": {"atlas": "UI-Frame-DiamondMetal-CornerTopLeft"},
    "TopRightCorner": {"atlas": "UI-Frame-DiamondMetal-CornerTopRight"},
    "BottomLeftCorner": {"atlas": "UI-Frame-DiamondMetal-CornerBottomLeft"},
    "BottomRightCorner": {"atlas": "UI-Frame-DiamondMetal-CornerBottomRight"},
    "TopEdge": {"atlas": "_UI-Frame-DiamondMetal-EdgeTop"},
    "BottomEdge": {"atlas": "_UI-Frame-DiamondMetal-EdgeBottom"},
    "LeftEdge": {"atlas": "!UI-Frame-DiamondMetal-EdgeLeft"},
    "RightEdge": {"atlas": "!UI-Frame-DiamondMetal-EdgeRight"},
}


def unique_corners_layout(kit):
    """NineSliceLayouts.UniqueCornersLayout for a texture kit, without the Center when the kit has none
    (OptionsFrame has none: SetAtlas on a missing element leaves the centre empty)."""
    return {
        name: {"atlas": atlas % kit}
        for name, atlas in (
            ("TopLeftCorner", "%s-NineSlice-CornerTopLeft"),
            ("TopRightCorner", "%s-NineSlice-CornerTopRight"),
            ("BottomLeftCorner", "%s-NineSlice-CornerBottomLeft"),
            ("BottomRightCorner", "%s-NineSlice-CornerBottomRight"),
            ("TopEdge", "_%s-NineSlice-EdgeTop"),
            ("BottomEdge", "_%s-NineSlice-EdgeBottom"),
            ("LeftEdge", "!%s-NineSlice-EdgeLeft"),
            ("RightEdge", "!%s-NineSlice-EdgeRight"),
            ("Center", "%s-NineSlice-Center"),
        )
    }


def draw_nine_slice(canvas, layout, x, y, w, h):
    """Canvas.nine_slice, dropping pieces whose atlas this build lacks, as SetAtlas silently does."""
    present = {}
    for name, piece in layout.items():
        if not isinstance(piece, dict):
            present[name] = piece
            continue
        try:
            canvas.ui.atlas(piece["atlas"])
        except KeyError:
            continue
        present[name] = piece
    canvas.nine_slice(present, x, y, w, h)


def dialog_border(canvas, x, y, w, h, background=(0, 0, 0, 0.8)):
    """DialogBorderTranslucentTemplate (the default `background`) or any DialogBorder*Template given its Bg
    colour: the Bg 7 units inside the frame, then the DiamondMetal Dialog NineSlice."""
    canvas.fill(x + 7, y + 7, w - 14, h - 14, background)
    canvas.nine_slice(DIALOG_LAYOUT, x, y, w, h)


def ui_panel_button(canvas, x, y, w, h, text, font=None):
    """UIPanelButtonTemplate: UI-Panel-Button-Up's left cap, stretched middle and right cap (12 wide each
    side, texcoords from SecureUIPanelTemplates.xml) with GameFontNormal centred."""
    texture = canvas.ui.texture("interface/buttons/ui-panel-button-up.blp")
    canvas.draw(crop_coords(texture, 0, 0.09375, 0, 0.6875), x, y, 12, h)
    canvas.draw(crop_coords(texture, 0.09375, 0.53125, 0, 0.6875), x + 12, y, w - 24, h)
    canvas.draw(crop_coords(texture, 0.53125, 0.625, 0, 0.6875), x + w - 12, y, 12, h)
    canvas.text(x, y, text, font or FONTS["GameFontNormal"], justify="CENTER", width=w, box_height=h)


def close_button(canvas, right, top):
    """UIPanelCloseButton (24x24 RedButton-Exit) placed by its TOPRIGHT."""
    canvas.draw(canvas.ui.atlas("RedButton-Exit"), right - 24, top, 24, 24)


def panel_tabs(canvas, x, y, names, selected=0):
    """PanelTabButtonTemplate tabs from the first tab's TOPLEFT, each 3 units after the last: width is the
    text (GameFontNormalSmall) plus 20, at least the side caps' width. The selected tab takes the taller
    activetab art and white text 3 below centre; the others gold text 2 above. Returns the tab rects."""
    ui = canvas.ui
    rects = []
    for index, name in enumerate(names):
        active = index == selected
        prefix = "uiframe-activetab" if active else "uiframe-tab"
        left, right, middle = ui.atlas(f"{prefix}-left"), ui.atlas(f"{prefix}-right"), ui.atlas(f"_{prefix}-center")
        font = FONTS["GameFontHighlightSmall" if active else "GameFontNormalSmall"]
        caps = ui.atlas("uiframe-tab-left").width + ui.atlas("uiframe-tab-right").width
        w = max(canvas.text_width(name, font) + 20, caps)
        left_x = x + (-1 if active else -3)
        right_x = x + w + (8 if active else 7) - right.width
        canvas.draw(left, left_x, y)
        canvas.draw(right, right_x, y)
        canvas.draw(middle, left_x + left.width, y, right_x - left_x - left.width, middle.height)
        # ButtonText is 10 high at CENTER (0, 2), which PanelTemplates_(De)SelectTab moves to (0, -3)/(0, 2).
        canvas.text(x, y + 16 - 5 + (3 if active else -2), name, font, justify="CENTER", width=w, box_height=10)
        rects.append((x, y, w, 32))
        x += w + 3
    return rects


def minimal_slider(canvas, x, y, w, h, value, lo, hi):
    """MinimalSliderWithSteppersTemplate at (x, y, w, h): the bar 19 in from each side, the Back/Forward
    steppers 4 outside it and the thumb at `value` in [lo, hi], all centred vertically."""
    ui = canvas.ui
    bar_x, bar_w, cy = x + 19, w - 38, y + h / 2
    left, right, middle = (
        ui.atlas("Minimal_SliderBar_Left"),
        ui.atlas("Minimal_SliderBar_Right"),
        ui.atlas("_Minimal_SliderBar_Middle"),
    )
    canvas.draw(left, bar_x, cy - left.height / 2)
    canvas.draw(right, bar_x + bar_w - right.width, cy - right.height / 2)
    canvas.draw(middle, bar_x + left.width, cy - middle.height / 2, bar_w - left.width - right.width, middle.height)
    thumb = ui.atlas("Minimal_SliderBar_Button")
    canvas.draw(thumb, bar_x + (bar_w - thumb.width) * (value - lo) / (hi - lo), cy - thumb.height / 2)
    back, forward = ui.atlas("Minimal_SliderBar_Button_Left"), ui.atlas("Minimal_SliderBar_Button_Right")
    canvas.draw(back, bar_x - 4 - 11, cy - 19 / 2, 11, 19)
    canvas.draw(forward, bar_x + bar_w + 4, cy - 18 / 2, 9, 18)


def edit_mode_checkbox(canvas, x, y, label, checked=False):
    """EditModeCheckButtonTemplate: the classic 32x32 UI-CheckBox file textures and a GameFontHighlightMedium
    label 5 units to the right, both centred on a 32-high row."""
    ui = canvas.ui
    canvas.draw(ui.texture("interface/buttons/ui-checkbox-up.blp"), x, y, 32, 32)
    if checked:
        canvas.draw(ui.texture("interface/buttons/ui-checkbox-check.blp"), x, y, 32, 32)
    canvas.text(x + 37, y, label, FONTS["GameFontHighlightMedium"], box_height=32)


def edit_mode_selection_layout(kit):
    """EditModeSystemTemplates.lua's EditModeSystemSelectionLayout for a texture kit: one mirrored corner
    8 units outside each corner of the system, the centre spread over the same outset."""
    corner = f"{kit}-NineSlice-Corner"
    return {
        "TopLeftCorner": {"atlas": corner, "mirrorLayout": True, "x": -8, "y": 8},
        "TopRightCorner": {"atlas": corner, "mirrorLayout": True, "x": 8, "y": 8},
        "BottomLeftCorner": {"atlas": corner, "mirrorLayout": True, "x": -8, "y": -8},
        "BottomRightCorner": {"atlas": corner, "mirrorLayout": True, "x": 8, "y": -8},
        "TopEdge": {"atlas": f"_{kit}-NineSlice-EdgeTop"},
        "BottomEdge": {"atlas": f"_{kit}-NineSlice-EdgeBottom"},
        "LeftEdge": {"atlas": f"!{kit}-NineSlice-EdgeLeft"},
        "RightEdge": {"atlas": f"!{kit}-NineSlice-EdgeRight"},
        "Center": {"atlas": f"{kit}-NineSlice-Center", "x": -8, "y": 8, "x1": 8, "y1": -8},
    }


def edit_mode_selection(canvas, x, y, w, h, label=None, selected=True):
    """EditModeSystemSelectionTemplate over a system at (x, y, w, h): the blue highlight, or the yellow
    selected kit with the system's name centred in GameFontHighlightLarge."""
    kit = "editmode-actionbar-selected" if selected else "editmode-actionbar-highlight"
    canvas.nine_slice(edit_mode_selection_layout(kit), x, y, w, h)
    if selected and label:
        font = FONTS["GameFontHighlightLarge"]
        canvas.text(x, y, label, font, justify="CENTER", width=w, box_height=h)


def basic_panel(ui, title, w, h):
    # BasicFrameTemplateWithInset: Blizzard_UIPanelTemplates/Mainline/UIPanelTemplates.xml:558–704.
    canvas = ui.canvas(w + 12, h + 8)
    x, y = 6, 1
    rock = ui.texture("interface/framegeneral/ui-background-rock.blp")
    marble = ui.texture("interface/framegeneral/ui-background-marble.blp")
    tiled(canvas, rock, x + 2, y + 21, w - 4, h - 23, rock.width / ui.scale, rock.height / ui.scale)
    canvas.draw(ui.atlas("_UI-Frame-TopTileStreaks"), x, y + 21, w - 2, 43)
    tiled(canvas, marble, x + 4, y + 24, w - 10, h - 28, marble.width / ui.scale, marble.height / ui.scale)
    draw_nine_slice(canvas, INSET_FRAME_LAYOUT, x + 4, y + 24, w - 10, h - 28)
    layout = {
        "TopLeftCorner": {"atlas": "UI-Frame-TopLeftCorner", "x": -6, "y": 1},
        "TopRightCorner": {"atlas": "UI-Frame-TopCornerRight", "y": 1},
        "BottomLeftCorner": {"atlas": "UI-Frame-BotCornerLeft", "x": -6, "y": -5},
        "BottomRightCorner": {"atlas": "UI-Frame-BotCornerRight", "y": -5},
        "TopEdge": {"atlas": "_UI-Frame-TitleTile"},
        "BottomEdge": {"atlas": "_UI-Frame-Bot"},
        "LeftEdge": {"atlas": "!UI-Frame-LeftTile"},
        "RightEdge": {"atlas": "!UI-Frame-RightTile", "x": 1},
    }
    canvas.draw(ui.atlas("_UI-Frame-TitleTileBg"), x + 2, y + 1, w - 27, 18)
    draw_nine_slice(canvas, layout, x, y, w, h)
    close_button(canvas, x + w - 2, y - 1)
    canvas.text(x - 6, y + 4, title, FONTS["GameFontNormal"], NORMAL, justify="CENTER", width=w)
    return canvas, x, y
