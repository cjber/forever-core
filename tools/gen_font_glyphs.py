"""Generate offline font coverage from pinned Fonts XML and cached client TTFs.

Requires fontTools only when regenerating. No font binaries are committed. Pass a
JSON mapping of client font paths to FileDataIDs from the build's wago listfile.
TOCs select in-game XML using forever_sim.loader rules. Inheritance is resolved
after collecting all definitions.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/wow-forever-addon/tooling"))
from forever_sim.fetch import BUILD as FONT_BUILD  # noqa: E402
from forever_sim.fetch import UI_REVISION


def ranges(points):
    result = []
    for point in sorted(points):
        if result and point == result[-1][1] + 1:
            result[-1][1] = point
        else:
            result.append([point, point])
    return result


def allowed(conditions):
    """Mirror forever_sim.loader.allowed for the Camelot/Mainline game."""
    game_types = {"camelot", "mainline"}
    for kind, value in re.findall(r"\[([A-Za-z]+)\s+([^\]]*)\]", conditions):
        tokens = set(re.split(r"[,\s]+", value.lower()))
        if kind == "AllowLoadGameType" and not tokens & game_types:
            return False
        if kind == "ExcludeLoadGameType" and tokens & game_types:
            return False
        if kind == "AllowLoad" and value.lower() == "glue":
            return False
    return True


def xml_paths(ui):
    """Follow eligible TOCs and XML Includes, shared fonts first, dependencies first."""
    base = ui / "Interface/AddOns"
    addons = {}
    for directory in sorted(base.glob("Blizzard_*")):
        candidates = [
            directory / f"{directory.name}{suffix}.toc" for suffix in ("_Camelot", "_Mainline", "_Vanilla", "")
        ]
        toc = next((p for p in candidates if p.is_file()), None)
        if toc is None:
            toc = next(iter(sorted(directory.glob("*.toc"))), None)
        if toc is None:
            continue
        metadata, files = {}, []
        for raw in toc.read_text().splitlines():
            line = raw.strip()
            if line.startswith("##") and ":" in line:
                key, value = line[2:].split(":", 1)
                condition = re.search(r"\s*\[.*\]\s*$", value)
                if condition and not allowed(condition[0]):
                    continue
                value = value[: condition.start()] if condition else value
                key = key.strip()
                metadata[key] = metadata.get(key, "") + ", " + value.strip()
            elif line and not line.startswith("#"):
                file, *conditions = line.split(maxsplit=1)
                if allowed(" ".join(conditions)):
                    files.append(file.replace("[Family]", "Mainline").replace("[Game]", "Camelot").replace("\\", "/"))
        conditions = "".join(
            f"[{key} {metadata[key].strip(', ')}]"
            for key in ("AllowLoad", "AllowLoadGameType", "ExcludeLoadGameType")
            if key in metadata
        )
        if allowed(conditions):
            deps = [
                dep
                for key, value in metadata.items()
                if key.lower().startswith("dep") or key.lower() in {"requireddeps", "requireddep"}
                for dep in re.split(r"[,\s]+", value)
                if dep
            ]
            addons[directory.name] = (directory, files, deps)
    paths, seen, loaded = [], set(), set()

    def include(path):
        path = path.resolve()
        if path in seen:
            return
        seen.add(path)
        paths.append((path.relative_to(base.resolve()).as_posix(), path))
        root = ET.fromstring(path.read_bytes())
        for node in root:
            if node.tag.rsplit("}", 1)[-1] == "Include" and node.get("file"):
                include(path.parent / node.attrib["file"].replace("\\", "/"))

    def load(name):
        if name in loaded or name not in addons:
            return
        loaded.add(name)
        directory, files, deps = addons[name]
        for dep in deps:
            load(dep)
        for file in files:
            if file.lower().endswith(".xml"):
                include(directory / file)

    load("Blizzard_Fonts_Shared")
    for name in addons:
        load(name)
    return paths


def read_xml(paths):
    """Resolve explicit font-family members and style inheritance, in load order."""
    definitions, sources = {}, []
    digest = hashlib.sha256()
    origins = {}
    for name, path in paths:
        raw = path.read_bytes()
        sources.append(name)
        digest.update(name.encode("utf-8") + b"\0" + raw)
        root = ET.fromstring(raw)
        for node in root:
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "FontFamily" and node.get("name"):
                members = {}
                for member in node:
                    alphabet = member.get("alphabet")
                    font = next((c for c in member if c.get("font")), None)
                    if alphabet and font is not None:
                        members[alphabet] = font.attrib["font"].replace("\\", "/").lower()
                if members:
                    value = members
                elif node.get("inherits"):
                    value = node.attrib["inherits"]
                else:
                    continue
            elif tag == "Font" and node.get("name"):
                if node.get("font"):
                    value = {"*": node.attrib["font"].replace("\\", "/").lower()}
                elif node.get("inherits"):
                    value = node.attrib["inherits"]
                else:
                    continue
            else:
                continue
            font_name = node.attrib["name"]
            definitions.setdefault(font_name, []).append((name, value))
            origins.setdefault(font_name, name)
    resolved = {}

    def resolve(name, stack=()):
        if name in stack:
            raise ValueError(f"font inheritance cycle: {stack + (name,)}")
        members = None
        for source, value in definitions[name]:
            candidate = resolve(value, stack + (name,)) if isinstance(value, str) else value
            if members is not None and members != candidate:
                raise ValueError(f"conflicting font {name!r}: {origins[name]} and {source}")
            members = candidate
        return members

    for name in definitions:
        resolved[name] = resolve(name)
    return resolved, sources, digest.hexdigest()


def generate(ui, cache, file_ids):
    from fontTools.ttLib import TTFont

    revision = subprocess.check_output(["git", "-C", str(ui), "rev-parse", "HEAD"], text=True).strip()
    if revision != UI_REVISION:
        raise ValueError(f"UI revision {revision}, expected {UI_REVISION}")
    objects, sources, xml_sha256 = read_xml(xml_paths(ui))
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
        "xml_sources": sources,
        "xml_sha256": xml_sha256,
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
