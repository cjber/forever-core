#!/usr/bin/env python3
"""Render Forever Core's Thanks window from UI/Credits.lua and the credits it lists.

    python3 tools/screenshots.py
    python3 tools/screenshots.py --preview ~/.cache/agent-scratch/thanks \
        --source "SkillUp Forever=/path/to/skillup-forever/THIRD_PARTY.md" \
        --source "Legacy Forever=/path/to/legacy-forever/THIRD_PARTY.md"

The first form writes docs/screenshots/thanks.png, with one compact row hovered (the top-ranked player, by number of
contributions): the row wears the client's quest-log list highlight and the tooltip touches the window's right edge
at that row's top. Everything in it comes from this repository: the window's size, gaps and anchors from
UI/Credits.lua, its phrases from Locales/enUS.lua, the addon title the credits are registered under from
Expose.lua, and the players and projects from THIRD_PARTY.md through forever_tools.credits.parse.

--preview writes three images into DIR from the given THIRD_PARTY.md files, each parsed and registered
under the TITLE on its --source, in the order given: thanks-all.png (All addons, scrolled to the top-ranked
player so their tooltip shows), thanks-filtered.png (filtered to the first source's title,
the dropdown closed) and thanks-menu.png (the filter menu open). Nothing written by --preview is committed;
with no --source it previews this repository's own data.

The portrait frame, inset, scroll bar, dropdown, tooltip and metal edges are the shared wowmock renderer's
(FOREVER_CORE, default this checkout). Needs Pillow 12; the pinned client's art is fetched from wago.tools
once and cached under ~/.cache/wowmock/<build>/.
"""

import argparse
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = Path(os.environ.get("FOREVER_CORE", ROOT)).expanduser()
WOWMOCK = CORE / "tools" / "wowmock"
if not (WOWMOCK / "wowmock.py").is_file():
    sys.exit(f"wowmock.py not found in {WOWMOCK}; set FOREVER_CORE to the forever-core checkout")
sys.path.insert(0, str(WOWMOCK))
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "wow-forever-addon" / "tooling"))
import wowmock  # noqa: E402
from forever_tools import credits  # noqa: E402

UI_ART_BUILD = "1.60.1.70124"
SOURCE = (ROOT / "UI" / "Credits.lua").read_text(encoding="utf-8")
LOCALE = (ROOT / "Locales" / "enUS.lua").read_text(encoding="utf-8")


NUMERIC_CONSTANT = re.compile(r"^local ([A-Z][A-Z0-9_]*) = ([0-9A-Z_ +\-]+)$", re.MULTILINE)


def evaluate(expression, known):
    """A UI/Credits.lua constant's + and - arithmetic over the numbers set before it."""
    total, sign = 0, 1
    for token in re.findall(r"[A-Z][A-Z0-9_]*|\d+|[+-]", expression):
        if token == "+":
            sign = 1
        elif token == "-":
            sign = -1
        elif token.isdigit():
            total += sign * int(token)
        else:
            if token not in known:
                raise SystemExit(f"UI/Credits.lua's {token} is used before it is set")
            total += sign * known[token]
    return total


LAYOUT = {}
for name, expression in NUMERIC_CONSTANT.findall(SOURCE):
    LAYOUT[name] = evaluate(expression, LAYOUT)


def constant(name):
    """One `local NAME = <number>` from UI/Credits.lua, so a layout change moves the mock with it."""
    if name not in LAYOUT:
        raise SystemExit(f"UI/Credits.lua no longer defines {name} the Thanks mock reads")
    return LAYOUT[name]


def phrase(key):
    """One `L["..."] = "..."` from core's enUS, the words the window draws."""
    match = re.search(rf'^L\["{re.escape(key)}"\] = "([^"\\\\]*)"$', LOCALE, re.MULTILINE)
    if not match:
        raise SystemExit(f"Locales/enUS.lua no longer has {key!r} the Thanks mock draws")
    return match[1]


def registered_title():
    """The addon title core hands its own credits to, as Expose.lua writes it."""
    match = re.search(r'CreditsPage\.Register\("([^"]+)"', (ROOT / "Expose.lua").read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("Expose.lua no longer registers core's credits; the Thanks mock cannot name the addon")
    return match[1]


# UI/Credits.lua's Build: WINDOW_WIDTH by WINDOW_HEIGHT, a header holding the title, the subtitle and the
# filter's own row, and a 14-unit bottom edge around the InsetFrameTemplate, with the page inset 8 from its
# top and left and 28 from its right.
WINDOW_WIDTH = constant("WINDOW_WIDTH")
WINDOW_HEIGHT = constant("WINDOW_HEIGHT")
HEADER_HEIGHT = constant("HEADER_HEIGHT")
BOTTOM = constant("BOTTOM")
CONTENT_WIDTH = constant("CONTENT_WIDTH")
SECTION_HEIGHT = constant("SECTION_HEIGHT")
SECTION_GAP = constant("SECTION_GAP")
ROW_HEIGHT = constant("ROW_HEIGHT")
NAME_COUNT_GAP = constant("NAME_COUNT_GAP")
NAME_DETAIL_GAP = constant("NAME_DETAIL_GAP")
DROPDOWN_WIDTH = constant("DROPDOWN_WIDTH")
DROPDOWN_HEIGHT = constant("DROPDOWN_HEIGHT")
DROPDOWN_RIGHT = constant("DROPDOWN_RIGHT")
DROPDOWN_TOP = constant("DROPDOWN_TOP")
ICON_MATCH = re.search(r'^local ICON = "Interface\\\\Icons\\\\([^"\\\\]+)"$', SOURCE, re.MULTILINE)
if not ICON_MATCH:
    raise SystemExit("UI/Credits.lua no longer sets the portrait's icon")
ICON = f"interface/icons/{ICON_MATCH[1].lower()}.blp"

SUBTITLE_TOPLEFT = (62, 54)  # subtitle:SetPoint("TOPLEFT", 62, -54)
INSET_MARGIN = constant("INSET_MARGIN")  # the inset's margin from the window's left and right edges
SCROLL_INSET = (8, 8)  # scroll:SetPoint("TOPLEFT", 8, -8); BOTTOMRIGHT, -28, 8
SCROLL_RIGHT = 28
# Mainline ScrollDefine.lua: SCROLL_FRAME_SCROLL_BAR_OFFSET_LEFT/TOP/BOTTOM, the bar's offsets from the
# ScrollFrameTemplate's right edge (MinimalScrollBar is 8 wide).
SCROLLBAR_OFFSET = (6, 2, 5)
TOOLTIP_WRAP = 260  # GameTooltip:AddLine(..., true) wraps within roughly this width
HIGHLIGHT = "interface/questframe/ui-questtitlehighlight.blp"  # the quest log row highlight other lists wear

GOLD = wowmock.NORMAL  # NORMAL_FONT_COLOR, the section headers and the tooltip's addon names
GREY = wowmock.rgb("808080")  # GRAY_FONT_COLOR, each row's addon list
WHITE = wowmock.WHITE
SUBTITLE_FONT = wowmock.FONTS["GameFontHighlightSmall"]
SECTION_FONT = wowmock.FONTS["GameFontNormalSmall"]
NAME_FONT = wowmock.FONTS["GameFontHighlight"]
DETAIL_FONT = wowmock.FONTS["GameFontHighlightSmall"]
PAGE_KINDS = {
    "header": (SECTION_FONT, GOLD, "LEFT"),
    "empty": (NAME_FONT, None, "CENTER"),
}


def name_order(row):
    """Alphabetical, case-insensitively, as Inspired by is listed."""
    return (row["name"].lower(), row["name"])


def player_order(row):
    """UI/Credits.lua's SortPlayers: most contributions first, then name, case-insensitively."""
    return (-row["count"], row["name"].lower(), row["name"])


def merge(entries, rank=False):
    """UI/Credits.lua's Merge: one row per exact name, every contribution kept in registration order, with its count."""
    rows, index = [], {}
    for title, entry in entries:
        row = index.get(entry["name"])
        if row is None:
            row = {"name": entry["name"], "helped": [], "count": 0}
            index[entry["name"]] = row
            rows.append(row)
        row["helped"].append({"addon": title, "what": entry["what"]})
        row["count"] += 1
    rows.sort(key=player_order if rank else name_order)
    return rows


def detail(row, filter_title=None):
    """UI/Credits.lua's Detail: the addon list once each, or the filtered addon's distinct what lines."""
    if filter_title:
        seen, what = set(), []
        for item in row["helped"]:
            if item["what"] and item["what"] not in seen:
                seen.add(item["what"])
                what.append(item["what"])
        return phrase(", ").join(what)
    return phrase(", ").join(dict.fromkeys(item["addon"] for item in row["helped"]))


def view(rows, filter_title):
    """UI/Credits.lua's View: only the rows crediting the filtered addon, each with just its lines."""
    if not filter_title:
        return rows
    kept = []
    for row in rows:
        helped = [item for item in row["helped"] if item["addon"] == filter_title]
        if helped:
            kept.append({"name": row["name"], "helped": helped, "count": len(helped)})
    return kept


def page_sections(sources, filter_title=None):
    """UI/Credits.lua's Render order: Players first, then Inspired by, each only when it has rows."""
    sections = []
    for key, header in (("players", "Players"), ("inspired", "Inspired by")):
        entries = ((title, entry) for title, data in sources for entry in data.get(key, []))
        rows = merge(entries, rank=key == "players")
        rows = view(rows, filter_title)
        if key == "players":
            rows.sort(key=player_order)
        if rows:
            sections.append((phrase(header), rows))
    return sections


def page(measure, sections, filter_title=None):
    """UI/Credits.lua's Render walk: (item, top, kind) per header and compact row, and the content height.

    A row is one fixed ROW_HEIGHT line, then the next; a section is its header's SECTION_HEIGHT, its rows,
    and SECTION_GAP when another follows. The empty page is its one centred line.
    """
    if not sections:
        empty = wowmock.wrap_text(measure, phrase("No one is listed yet."), NAME_FONT, CONTENT_WIDTH)
        return [(empty, 24, "empty")], 50
    items, top = [], 0
    for position, (header, rows) in enumerate(sections):
        items.append((wowmock.wrap_text(measure, header, SECTION_FONT, CONTENT_WIDTH), top, "header"))
        top += SECTION_HEIGHT
        for row in rows:
            items.append((row, top, "row"))
            top += ROW_HEIGHT
        if position < len(sections) - 1:
            top += SECTION_GAP
    return items, top


def pick_hover(sections):
    """The top-ranked player, the first Players row, the one every Thanks image tooltips."""
    for header, rows in sections:
        if phrase("Players") in header:
            return rows[0] if rows else None
    return None


def tooltip_lines(row):
    """UI/Credits.lua's GroupedLines: contributions grouped by the exact words they gave, each addon once, in order."""
    groups, index, seen = [], {}, set()
    for helped in row["helped"]:
        group = index.get(helped["what"])
        if group is None:
            group = {"what": helped["what"], "addons": []}
            index[helped["what"]] = group
            groups.append(group)
        key = (helped["what"], helped["addon"])
        if key not in seen:
            seen.add(key)
            group["addons"].append(helped["addon"])
    return groups


def wrap_colored(measure, runs, font, width):
    """The client's greedy word wrap over [(text, colour)] runs, keeping each word's colour on its line."""
    tokens = []
    for text, color in runs:
        for position, word in enumerate(text.split(" ")):
            if position:
                tokens.append((" ", color))
            if word:
                tokens.append((word, color))
    lines, current = [[]], 0.0
    for token, color in tokens:
        token_width = measure.text_width(token, font)
        if token == " ":
            if not lines[-1]:
                continue
            lines[-1].append((token, color))
            current += token_width
            continue
        if lines[-1] and current + token_width > width:
            if lines[-1][-1][0] == " ":
                current -= measure.text_width(" ", font)
                lines[-1].pop()
            lines.append([])
            current = 0.0
        lines[-1].append((token, color))
        current += token_width
    return ["".join(wowmock.colored(text, color) if color else text for text, color in line) for line in lines]


def row_tooltip(ui, row):
    """GameTooltip: the name as the title, then one wrapped line per distinct what, its addons gold and its
    words white. One sentence is one line however many addons gave it."""
    measure = ui.canvas(1, 1)
    header_font = wowmock.FONTS["GameTooltipHeaderText"]
    text_font = wowmock.FONTS["GameTooltipText"]
    title = row["name"]
    if row.get("count", len(row["helped"])) > 1:
        title = phrase("%s (%s)") % (title, phrase("%d contributions") % row["count"])
    lines = [(title, header_font)]
    for group in tooltip_lines(row):
        runs = [(phrase(", ").join(group["addons"]), GOLD)]
        if group["what"]:
            runs.append((": " + group["what"], None))
        lines.extend((line, text_font) for line in wrap_colored(measure, runs, text_font, TOOLTIP_WRAP))
    widths = [measure.text_width(line, font) for line, font in lines]
    width = math.ceil(max(widths, default=0)) + 2 * wowmock.TOOLTIP_PADDING
    height = (
        sum(font.height for _, font in lines)
        + wowmock.TOOLTIP_LINE_GAP * (len(lines) - 1)
        + 2 * wowmock.TOOLTIP_PADDING
    )
    canvas = ui.canvas(width, height)
    background = ui.global_color("TOOLTIP_DEFAULT_BACKGROUND_COLOR")
    canvas.nine_slice(wowmock.TOOLTIP_LAYOUT, 0, 0, width, height, center_color=(*background[:3], 1))
    y = wowmock.TOOLTIP_PADDING
    for line, font in lines:
        canvas.text(wowmock.TOOLTIP_PADDING, y, line, font)
        y += font.height + wowmock.TOOLTIP_LINE_GAP
    return canvas


def menu_entries(sources, filter_title):
    """The filter menu: All addons, then each source's title, one radio each because the page shows one."""
    entries = [wowmock.MenuRadio(phrase("All addons"), filter_title is None)]
    for title, _data in sources:
        entries.append(wowmock.MenuRadio(title, filter_title == title))
    return entries


def draw_row(canvas, measure, row, top, filter_title):
    """One compact row: the name, its contribution count when above one, then the addons (or the filtered
    addon's what) in grey on the same line."""
    name_width = measure.text_width(row["name"], NAME_FONT)
    canvas.text(0, top, row["name"], NAME_FONT, box_height=ROW_HEIGHT)
    text_x = name_width + NAME_DETAIL_GAP
    count = row.get("count", len(row["helped"]))
    if count > 1:
        count_text = f"x{count}"
        canvas.text(name_width + NAME_COUNT_GAP, top, count_text, DETAIL_FONT, GREY, box_height=ROW_HEIGHT)
        text_x = name_width + NAME_COUNT_GAP + measure.text_width(count_text, DETAIL_FONT) + NAME_DETAIL_GAP
    text = detail(row, filter_title)
    room = CONTENT_WIDTH - text_x
    if text and room > 0:
        line = wowmock.wrap_text(measure, text, DETAIL_FONT, room, max_lines=1)[0]
        canvas.text(text_x, top, line, DETAIL_FONT, GREY, box_height=ROW_HEIGHT)


def thanks(ui, sources, filter_title=None, hover=None, menu=False):
    """The Thanks window at its real size, compact rows, with an optional row tooltip and filter menu."""
    margin = 24
    measure = ui.canvas(1, 1)
    sections = page_sections(sources, filter_title)
    items, content_height = page(measure, sections, filter_title)
    view_h = WINDOW_HEIGHT - HEADER_HEIGHT - BOTTOM - 2 * SCROLL_INSET[1]

    tooltip = None
    hover_item = None
    hover_top = None
    scroll = 0
    if hover is not None:
        for item, top, kind in items:
            if kind == "row" and item is hover:
                hover_item, hover_top = item, top
                break
        if hover_item is None:
            # The caller may have picked its row from its own merge; match it by name.
            for item, top, kind in items:
                if kind == "row" and item["name"] == hover["name"]:
                    hover_item, hover_top = item, top
                    break
        tooltip = row_tooltip(ui, hover)
        if hover_top is not None and hover_top + ROW_HEIGHT > view_h:
            # Scroll the tooltipped row into the view (near its middle when the list allows) so the tooltip
            # belongs to a row the reader can see, rather than to one past the bottom of the page.
            offset = hover_top - (view_h - ROW_HEIGHT) / 2
            scroll = min(max(offset, 0), max(content_height - view_h, 0))

    menu_canvas = None
    menu_rect = None
    if menu:
        menu_canvas, geometry = wowmock.context_menu(ui, menu_entries(sources, filter_title))
        menu_rect = geometry["menu"]

    # ANCHOR_RIGHT: the tooltip sits beside the window, touching its right edge at the hovered row's top.
    tip_width = tooltip.width if tooltip else 0
    tip_height = tooltip.height if tooltip else 0
    tip_x = margin + WINDOW_WIDTH
    tip_y = margin + HEADER_HEIGHT + SCROLL_INSET[1] + (hover_top - scroll if hover_item else 0)
    menu_bottom = 0
    if menu_canvas is not None and menu_rect is not None:
        menu_bottom = margin + DROPDOWN_TOP + DROPDOWN_HEIGHT + 2 - menu_rect[1] + menu_canvas.height
    width = WINDOW_WIDTH + 2 * margin + tip_width
    height = max(
        WINDOW_HEIGHT + 2 * margin,
        tip_y + tip_height + margin if hover_item else 0,
        menu_bottom + margin if menu_canvas else 0,
    )
    x = y = margin
    canvas = ui.canvas(width, height)

    # PortraitFrameTemplate and its Bg: PortraitFrameTextureBaseTemplate's tiled rock (TOPLEFT 2, -21 to
    # BOTTOMRIGHT -2, 2) and _UI-Frame-TopTileStreaks (6, -21) to (-2, -21).
    rock = ui.texture("interface/framegeneral/ui-background-rock.blp")
    wowmock.tiled(
        canvas,
        rock,
        x + 2,
        y + 21,
        WINDOW_WIDTH - 4,
        WINDOW_HEIGHT - 23,
        rock.width / ui.scale,
        rock.height / ui.scale,
    )
    streaks = ui.atlas("_UI-Frame-TopTileStreaks")
    canvas.draw(streaks, x + 6, y + 21, WINDOW_WIDTH - 8, streaks.height)

    # The sentence runs on one line to the inset's edge; the filter has its own row below it.
    subtitle_room = WINDOW_WIDTH - SUBTITLE_TOPLEFT[0] - INSET_MARGIN
    for index, line in enumerate(
        wowmock.wrap_text(measure, phrase("The players who helped each Forever addon."), SUBTITLE_FONT, subtitle_room)
    ):
        canvas.text(
            x + SUBTITLE_TOPLEFT[0],
            y + SUBTITLE_TOPLEFT[1] + index * SUBTITLE_FONT.height,
            line,
            SUBTITLE_FONT,
        )

    drop_x = x + WINDOW_WIDTH - DROPDOWN_RIGHT - DROPDOWN_WIDTH
    drop_y = y + DROPDOWN_TOP
    wowmock.dropdown(
        canvas,
        drop_x,
        drop_y,
        DROPDOWN_WIDTH,
        filter_title or phrase("All addons"),
        h=DROPDOWN_HEIGHT,
    )

    inset_x, inset_y = x + INSET_MARGIN, y + HEADER_HEIGHT
    inset_w, inset_h = WINDOW_WIDTH - 2 * INSET_MARGIN, WINDOW_HEIGHT - HEADER_HEIGHT - BOTTOM
    marble = ui.texture("interface/framegeneral/ui-background-marble.blp")
    wowmock.tiled(
        canvas,
        marble,
        inset_x,
        inset_y,
        inset_w,
        inset_h,
        marble.width / ui.scale,
        marble.height / ui.scale,
    )
    wowmock.draw_nine_slice(canvas, wowmock.INSET_FRAME_LAYOUT, inset_x, inset_y, inset_w, inset_h)

    scroll_x, scroll_y = inset_x + SCROLL_INSET[0], inset_y + SCROLL_INSET[1]
    view_w = inset_w - SCROLL_INSET[0] - SCROLL_RIGHT
    if view_w != CONTENT_WIDTH:
        raise SystemExit(f"the scroll view is {view_w} wide but UI/Credits.lua lays rows out at {CONTENT_WIDTH}")

    content = ui.canvas(CONTENT_WIDTH, max(content_height, 1))
    highlight = ui.texture(HIGHLIGHT)
    for item, top, kind in items:
        if kind == "row":
            if item is hover_item:
                # The Button's HighlightTexture, struck across the row and added to the page's marble.
                content.draw(highlight, 0, top, CONTENT_WIDTH, ROW_HEIGHT, blend="ADD")
            draw_row(content, measure, item, top, filter_title)
        else:
            font, color, justify = PAGE_KINDS[kind]
            for index, line in enumerate(item):
                content.text(0, top + index * font.height, line, font, color, justify=justify, width=CONTENT_WIDTH)
    # The ScrollFrame clips its child: draw exactly the window from `scroll` to `scroll + view_h`.
    clip_top = canvas.px(scroll_y)
    content_top = canvas.px(scroll)
    clip_height = max(0, min(canvas.px(scroll_y + view_h) - clip_top, content.image.height - content_top))
    canvas.composite(
        content.image.crop((0, content_top, content.image.width, content_top + clip_height)),
        canvas.px(scroll_x),
        clip_top,
    )

    offset_left, offset_top, offset_bottom = SCROLLBAR_OFFSET
    wowmock.minimal_scrollbar(
        canvas,
        scroll_x + view_w + offset_left,
        scroll_y - offset_top,
        view_h + offset_top + offset_bottom,
        visible=min(1, view_h / max(content_height, 1)),
        offset=scroll / max(content_height - view_h, 1),
    )

    # Portrait, metal NineSlice, title and close button over everything, as their frame levels draw them.
    wowmock.portrait_frame_art(canvas, x, y, WINDOW_WIDTH, WINDOW_HEIGHT, ui.texture(ICON), phrase("Thanks"))

    if tooltip is not None and hover_item is not None:
        canvas.paste(tooltip, tip_x, tip_y)

    if menu_canvas is not None and menu_rect is not None:
        # UI/ContextMenu.lua: SetPoint("TOPRIGHT", owner, "BOTTOMRIGHT", 0, -2), drawn over the page.
        menu_x, menu_y, menu_w, _menu_h = menu_rect
        owner_right = x + WINDOW_WIDTH - DROPDOWN_RIGHT
        owner_bottom = y + DROPDOWN_TOP + DROPDOWN_HEIGHT
        canvas.paste(menu_canvas, owner_right - menu_w - menu_x, owner_bottom + 2 - menu_y)

    return canvas


def parse_sources(values):
    """The `--source TITLE=PATH` pairs, parsed under their titles in the order given."""
    sources = []
    for value in values:
        title, separator, path = value.partition("=")
        title, path = title.strip(), path.strip()
        if not separator or not title or not path:
            raise SystemExit(f"--source wants TITLE=PATH, not {value!r}")
        source = Path(path).expanduser()
        if not source.is_file():
            raise SystemExit(f"--source {title}: {source} is not a file")
        sources.append((title, credits.parse(source.read_text(encoding="utf-8"))))
    return sources


def default_sources():
    """This repository's own THIRD_PARTY.md, registered under the title Expose.lua hands it in with."""
    return [(registered_title(), credits.parse((ROOT / "THIRD_PARTY.md").read_text(encoding="utf-8")))]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preview", type=Path, metavar="DIR", help="write the three preview images into DIR")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="TITLE=PATH",
        help="a THIRD_PARTY.md to preview under TITLE, in the order given (repeatable)",
    )
    arguments = parser.parse_args(argv)
    if arguments.source and not arguments.preview:
        parser.error("--source is only for --preview")

    ui = wowmock.Ui(build=UI_ART_BUILD, scale=2)
    sources = parse_sources(arguments.source) if arguments.preview else default_sources()
    if not sources:
        sources = default_sources()

    if arguments.preview:
        output = arguments.preview.expanduser()
        output.mkdir(parents=True, exist_ok=True)
        all_sections = page_sections(sources)
        written = [
            (output / "thanks-all.png", thanks(ui, sources, None, hover=pick_hover(all_sections))),
            (output / "thanks-filtered.png", thanks(ui, sources, sources[0][0])),
            (output / "thanks-menu.png", thanks(ui, sources, None, menu=True)),
        ]
        for path, canvas in written:
            wowmock.scene(ui, [(canvas, 0, 0)]).save(path)
            print(path)
        return

    output = ROOT / "docs" / "screenshots"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "thanks.png"
    sections = page_sections(sources)
    wowmock.scene(ui, [(thanks(ui, sources, None, hover=pick_hover(sections)), 0, 0)]).save(path)
    print(path)


if __name__ == "__main__":
    main()
