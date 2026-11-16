"""Generate offline font coverage from pinned Fonts XML and cached client TTFs.

Requires fontTools only when regenerating. No font binaries are committed. Pass a
JSON mapping of client font paths to FileDataIDs from the build's wago listfile.
The XML order is the game-loaded order in Blizzard_Fonts_Shared.toc (Mainline).
"""

import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/wow-forever-addon/tooling"))
from forever_sim.fetch import BUILD as FONT_BUILD  # noqa: E402
from forever_sim.fetch import UI_REVISION

XML_FILES = (
    "Mainline/Fonts.xml",
    "Shared/Fonts.xml",
    "Shared/GameFonts.xml",
    "Mainline/GameFonts.xml",
    "Shared/FontStyles.xml",
    "Mainline/FontStyles.xml",
    "Mainline/GameFontStyles.xml",
    "Shared/GameFontStyles.xml",
)


def ranges(points):
    result = []
    for point in sorted(points):
        if result and point == result[-1][1] + 1:
            result[-1][1] = point
        else:
            result.append([point, point])
    return result


def read_xml(paths):
    """Resolve explicit font-family members and style inheritance, in load order."""
    definitions, sources = {}, {}
    for name, path in paths:
        raw = path.read_bytes()
        sources[name] = hashlib.sha256(raw).hexdigest()
        root = ET.fromstring(raw)
        for node in root:
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "FontFamily":
                members = {}
                for member in node:
                    alphabet = member.get("alphabet")
                    font = next((c for c in member if c.get("font")), None)
                    if alphabet and font is not None:
                        members[alphabet] = font.attrib["font"].replace("\\", "/").lower()
                if members:
                    definitions[node.attrib["name"]] = members
            elif tag == "Font" and node.get("name"):
                if node.get("font"):
                    definitions[node.attrib["name"]] = {"*": node.attrib["font"].replace("\\", "/").lower()}
                elif node.get("inherits"):
                    definitions[node.attrib["name"]] = node.attrib["inherits"]
    resolved = {}

    def resolve(name, stack=()):
        if name in stack:
            raise ValueError(f"font inheritance cycle: {stack + (name,)}")
        value = definitions[name]
        return resolve(value, stack + (name,)) if isinstance(value, str) else value

    for name in definitions:
        resolved[name] = resolve(name)
    return resolved, sources


def generate(ui, cache, file_ids):
    from fontTools.ttLib import TTFont

    revision = subprocess.check_output(["git", "-C", str(ui), "rev-parse", "HEAD"], text=True).strip()
    if revision != UI_REVISION:
        raise ValueError(f"UI revision {revision}, expected {UI_REVISION}")
    base = ui / "Interface/AddOns/Blizzard_Fonts_Shared"
    objects, sources = read_xml([(name, base / name) for name in XML_FILES])
    fonts = {}
    for name in sorted({font for members in objects.values() for font in members.values()}):
        file_id = file_ids[name]
        path = cache / str(file_id)
        with TTFont(path) as font:
            # Unicode cmap entries pointing to glyph zero are missing glyphs.
            points = {
                p
                for table in font["cmap"].tables
                if table.isUnicode()
                for p, glyph in table.cmap.items()
                if font.getGlyphID(glyph) != 0
            }
        fonts[name] = {
            "file_id": file_id,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "url": f"https://wago.tools/api/casc/{file_id}?download&build={FONT_BUILD}",
            "ranges": ranges(points),
        }
    return {
        "font_build": FONT_BUILD,
        "ui_revision": revision,
        "ui_repository": "https://github.com/Gethe/wow-ui-source",
        "xml_sha256": sources,
        "objects": objects,
        "fonts": fonts,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ui", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--file-ids", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = generate(args.ui, args.cache, json.loads(args.file_ids.read_text()))
    args.output.write_text(json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
