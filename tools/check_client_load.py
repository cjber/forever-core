"""Refuse what the Forever client cannot load: a font object it never defines, and a TOC that lists Bindings.xml.

Fonts. `CreateFontString(name, layer, font)`, `SetFontObject(font)` (and its Normal, Highlight and Disabled forms),
XML `inherits=` on a FontString, Font or ButtonText, `font=` and a NormalFont, HighlightFont or DisabledFont `style=`
must name a font object the client defines or the addon defines itself. The client has no `GameFontLarge`, so
`CreateFontString(nil, "ARTWORK", "GameFontLarge")` errors on every login ("Couldn't find inherited node").
The client's fonts are listed in tools/blizzard_fonts.txt, generated from a pinned Blizzard UI source (see
`--blizzard-ui`). The addon's own are its XML `<Font>`, `<FontFamily>` and virtual `<FontString>` names, and its Lua
`CreateFont("Name")` and `CreateFontFamily("Name", ...)` calls. A string literal in the font argument is checked,
including each side of `a and "X" or "Y"`, and so is a bare capitalised global (`SetFontObject(GameFontNormal)`).
A local or a field is not followed.

Bindings. The client loads an addon's Bindings.xml by itself; listed in a TOC it loads again as a UI file and logs an
`Unrecognized XML` warning per binding on every login.

Every addon Lua, XML and TOC file is read, outside tests/, tools/, types/, docs/, Libs/ and dot folders.

    python3 tools/check_client_load.py                      this repository
    python3 tools/check_client_load.py FILE...              only these files
    python3 tools/check_client_load.py --blizzard-ui DIR    rewrite tools/blizzard_fonts.txt from a Blizzard UI tree
"""

import argparse
import re
import sys
from pathlib import Path

SKIPPED_DIRS = frozenset({"tests", "tools", "types", "docs", "Libs", "libs", "node_modules"})
FONTS_FILE = Path(__file__).resolve().with_name("blizzard_fonts.txt")
# The Lua calls whose argument (0-based) names a font object.
FONT_CALLS = {
    "CreateFontString": 2,
    "SetFontObject": 0,
    "SetNormalFontObject": 0,
    "SetHighlightFontObject": 0,
    "SetDisabledFontObject": 0,
}
DEFINE_CALLS = frozenset({"CreateFont", "CreateFontFamily"})
# SimpleHTML:SetFontObject(textType, font) takes the font second.
HTML_TEXT_TYPES = frozenset({"h1", "h2", "h3", "p"})
INHERITING_TAGS = frozenset({"FontString", "Font", "ButtonText"})
STYLE_TAGS = frozenset({"NormalFont", "HighlightFont", "DisabledFont"})
DEFINING_TAGS = frozenset({"Font", "FontFamily"})
START_TAG = re.compile(r"<([A-Za-z][\w.-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>")
ATTRIBUTE = re.compile(r"([\w:.-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")
XML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
PATH_LIKE = re.compile(r"[\\/]|\.(?:ttf|otf)$", re.IGNORECASE)
OPENERS = {"(": ")", "{": "}", "[": "]"}


def _tokenize(source):
    """forever_tools.lua's lexer: tools/forever_tools in a consumer, the skill pack's tooling in forever-core."""
    tools = Path(__file__).resolve().parent
    for base in (tools, tools.parent / ".agents/skills/wow-forever-addon/tooling"):
        if (base / "forever_tools" / "lua.py").is_file():
            if str(base) not in sys.path:
                sys.path.insert(0, str(base))
            break
    from forever_tools.lua import tokenize

    return tokenize(source)[0]


def _symbol(token, text):
    return token.kind in ("symbol", "keyword") and token.text == text


def _string_value(token):
    """The text of a short string literal; None for a long string, whose contents never name a font."""
    text = token.text
    if text[:1] in ("'", '"'):
        return text[1:-1]
    return None


# XML


def _xml_tags(source):
    """(tag, attributes, line) for every start tag, comments skipped."""
    source = XML_COMMENT.sub(lambda match: "\n" * match[0].count("\n"), source)
    for match in START_TAG.finditer(source):
        attributes = {
            name: first if first is not None else second for name, first, second in ATTRIBUTE.findall(match[2])
        }
        yield match[1], attributes, source.count("\n", 0, match.start()) + 1


def xml_definitions(source):
    names = set()
    for tag, attributes, _ in _xml_tags(source):
        name = attributes.get("name", "")
        if not name or "$" in name:
            continue
        if tag in DEFINING_TAGS or (tag == "FontString" and attributes.get("virtual") == "true"):
            names.add(name)
    return names


def xml_uses(source):
    """(line, font name) for every font object an XML file inherits or names."""
    uses = []
    for tag, attributes, line in _xml_tags(source):
        if tag in INHERITING_TAGS and attributes.get("inherits"):
            uses += [(line, name.strip()) for name in attributes["inherits"].split(",") if name.strip()]
        font = attributes.get("font", "")
        if font and not PATH_LIKE.search(font):
            uses.append((line, font))
        if tag in STYLE_TAGS and attributes.get("style"):
            uses.append((line, attributes["style"]))
    return uses


# Lua


def _arguments(tokens, opening):
    """The argument token lists of the call whose `(` is at `opening`, and the index past its `)`."""
    arguments, current, depth, at = [], [], 0, opening + 1
    while at < len(tokens) and tokens[at].kind != "eof":
        token = tokens[at]
        if token.kind == "symbol" and token.text in OPENERS:
            depth += 1
        elif token.kind == "symbol" and token.text in OPENERS.values():
            if depth == 0:
                if current:
                    arguments.append(current)
                return arguments, at + 1
            depth -= 1
        elif depth == 0 and _symbol(token, ","):
            arguments.append(current)
            current = []
            at += 1
            continue
        current.append((token, depth))
        at += 1
    return arguments, at


def _locals(tokens):
    """Every name the file binds as a local or a parameter, so a bare argument of that name is not read as a global."""
    names = set()
    for at, token in enumerate(tokens):
        if _symbol(token, "local"):
            step = at + 1
            if _symbol(tokens[step], "function"):
                names.add(tokens[step + 1].text)
                continue
            while tokens[step].kind == "name":
                names.add(tokens[step].text)
                if not _symbol(tokens[step + 1], ","):
                    break
                step += 2
        elif _symbol(token, "function"):
            step = at + 1
            while step < len(tokens) and not _symbol(tokens[step], "("):
                step += 1
            for inner in tokens[step + 1 :]:
                if _symbol(inner, ")"):
                    break
                if inner.kind == "name":
                    names.add(inner.text)
        elif _symbol(token, "for"):
            step = at + 1
            while tokens[step].kind == "name" or _symbol(tokens[step], ","):
                if tokens[step].kind == "name":
                    names.add(tokens[step].text)
                step += 1
    return names


def _font_names(argument, local_names):
    """(line, name) for each font object an argument can evaluate to."""
    if len(argument) == 1 and argument[0][0].kind == "name":
        token = argument[0][0]
        if token.text[:1].isupper() and token.text not in local_names:
            return [(token.line, token.text)]
        return []
    names = []
    for index, (token, depth) in enumerate(argument):
        if token.kind != "string" or depth:
            continue
        neighbours = [argument[at][0] for at in (index - 1, index + 1) if 0 <= at < len(argument)]
        if any(_symbol(other, op) for other in neighbours for op in ("==", "~=", "..")):
            continue
        value = _string_value(token)
        if value:
            names.append((token.line, value))
    return names


def lua_definitions(tokens):
    names = set()
    for at, token in enumerate(tokens):
        if token.kind == "name" and token.text in DEFINE_CALLS and _symbol(tokens[at + 1], "("):
            if tokens[at + 2].kind == "string" and _string_value(tokens[at + 2]):
                names.add(_string_value(tokens[at + 2]))
    return names


def lua_uses(tokens):
    uses, local_names = [], None
    for at, token in enumerate(tokens):
        if token.kind != "name" or token.text not in FONT_CALLS or not _symbol(tokens[at + 1], "("):
            continue
        if local_names is None:
            local_names = _locals(tokens)
        arguments, _ = _arguments(tokens, at + 1)
        position = FONT_CALLS[token.text]
        if token.text == "SetFontObject" and len(arguments) == 2:
            first = arguments[0]
            if len(first) == 1 and first[0][0].kind == "string" and _string_value(first[0][0]) in HTML_TEXT_TYPES:
                position = 1
        if position < len(arguments):
            uses += _font_names(arguments[position], local_names)
    return uses


# TOC


def toc_findings(source):
    findings = []
    for line, text in enumerate(source.splitlines(), 1):
        entry = text.split("#", 1)[0].strip() if not text.lstrip().startswith("#") else ""
        entry = re.sub(r"\s*\[.*$", "", entry).replace("\\", "/")
        if entry.rsplit("/", 1)[-1].lower() == "bindings.xml":
            findings.append(
                (
                    line,
                    "client-load: the client loads Bindings.xml by itself; listed in a TOC it loads again as a UI "
                    "file and logs an Unrecognized XML warning per binding on every login, so remove this line",
                )
            )
    return findings


# Files


def addon_files(root, suffixes=(".lua", ".xml", ".toc")):
    """Every Lua, XML and TOC file the addon could ship: outside tests, tools, types, docs, Libs and dot folders."""
    files = []
    for path in sorted(root.rglob("*")):
        parts = path.relative_to(root).parts
        if path.suffix.lower() not in suffixes or not path.is_file():
            continue
        if parts[0] in SKIPPED_DIRS or any(part.startswith(".") for part in parts):
            continue
        files.append(path)
    return files


def library_files(root):
    """Lua and XML under Libs/: they never fail this check, but a font a library defines is the addon's to use."""
    return [
        path
        for folder in ("Libs", "libs")
        if (root / folder).is_dir()
        for path in sorted((root / folder).rglob("*"))
        if path.suffix.lower() in (".lua", ".xml") and path.is_file()
    ]


def blizzard_fonts(path=FONTS_FILE):
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.add(line)
    return names


def _definitions(path, source):
    if path.suffix.lower() == ".xml":
        return xml_definitions(source)
    if path.suffix.lower() == ".lua" and "CreateFont" in source:
        return lua_definitions(_tokenize(source))
    return set()


def check(files, known, root):
    """Print every finding as `file:line: message`; return whether any was found."""
    sources, failed = {}, False
    for path in files:
        try:
            sources[path] = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as error:
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
    # Every font the addon defines counts, wherever it is defined, even when only some files are checked.
    defined = set(known)
    for path in dict.fromkeys([*sources, *addon_files(root, (".lua", ".xml")), *library_files(root)]):
        try:
            source = sources[path] if path in sources else path.read_text(encoding="utf-8-sig")
            defined |= _definitions(path, source)
        except (OSError, UnicodeDecodeError, ValueError) as error:  # ValueError: forever_tools.lua.LuaSyntaxError
            print(f"{path}: {error}", file=sys.stderr)
            failed = True

    for path, source in sources.items():
        suffix = path.suffix.lower()
        if suffix == ".toc":
            findings = toc_findings(source)
        else:
            if suffix == ".xml":
                uses = xml_uses(source)
            elif "Font" in source:
                try:
                    uses = lua_uses(_tokenize(source))
                except ValueError:
                    continue  # reported above
            else:
                uses = []
            findings = [
                (
                    line,
                    f'client-load: font object "{name}" is not defined by the client\'s UI '
                    "(tools/blizzard_fonts.txt) or by this addon, so the client errors when it is used",
                )
                for line, name in uses
                if name not in defined
            ]
        shown = path.resolve().relative_to(root.resolve()) if path.resolve().is_relative_to(root.resolve()) else path
        for line, message in sorted(set(findings)):
            print(f"{shown}:{line}: {message}")
        failed |= bool(findings)
    return failed


# Generating tools/blizzard_fonts.txt


def _load_on_demand(addon):
    for toc in addon.glob("*.toc"):
        for line in toc.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if re.match(r"##\s*LoadOnDemand\s*:\s*1", line):
                return True
    return False


def generate(ui_root):
    """The font objects a Blizzard UI tree defines in game: XML in addons loaded at login, glue screens left out."""
    addons = ui_root / "Interface" / "AddOns"
    if not addons.is_dir():
        raise SystemExit(f"{addons} is not a directory")
    names = set()
    for addon in sorted(path for path in addons.iterdir() if path.is_dir()):
        if _load_on_demand(addon):
            continue
        for path in sorted(addon.rglob("*.xml")):
            if not path.name.startswith("Glue"):
                names |= xml_definitions(path.read_text(encoding="utf-8-sig", errors="replace"))
    version = ui_root / "version.txt"
    build = version.read_text(encoding="utf-8").strip() if version.is_file() else "unknown"
    header = [
        f"# Font objects the Forever client's UI defines in game, build {build}.",
        "# Generated by tools/check_client_load.py --blizzard-ui <tree> from the pinned Blizzard UI source",
        "# (wow-handoff/blizzard-ui): Font, FontFamily and virtual FontString names in the XML of every addon loaded",
        "# at login, glue-screen files left out. Vendored from cjber/forever-core; regenerate it there.",
    ]
    FONTS_FILE.write_text("\n".join(header + sorted(names)) + "\n", encoding="utf-8")
    print(f"{FONTS_FILE.name}: {len(names)} font objects from build {build}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--blizzard-ui", type=Path, help="regenerate tools/blizzard_fonts.txt from this UI tree")
    arguments = parser.parse_args(argv)
    if arguments.blizzard_ui:
        generate(arguments.blizzard_ui)
        return 0
    root = Path(__file__).resolve().parent.parent
    files = arguments.files or addon_files(root)
    if check(files, blizzard_fonts(), root):
        return 1
    print(f"Client load check: {len(files)} Lua, XML and TOC files checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
