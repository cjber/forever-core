"""Check reviewed text producers or locale values with an explicit font object.

A locale alone does not identify the font a widget uses. Automatic checks require
source-bound, reviewed widget mappings. Dynamic text and unlisted producers have
no coverage claim. Coverage comes from pinned XML mappings and Unicode cmaps.
"""

import argparse
import hashlib
import json
from pathlib import Path

from .locales import Entry, LocaleError, _string, parse
from .lua import LuaSyntaxError, tokenize

# WoW locale alphabets, as named by Fonts XML Member nodes. No character-based
# script detection: Latin text in ruRU still uses the russian member.
ALPHABETS = {
    "enUS": "roman",
    "enGB": "roman",
    "deDE": "roman",
    "esES": "roman",
    "esMX": "roman",
    "frFR": "roman",
    "itIT": "roman",
    "ptBR": "roman",
    "ruRU": "russian",
    "koKR": "korean",
    "zhCN": "simplifiedchinese",
    "zhTW": "traditionalchinese",
}


def font_path(data, locale, font_object):
    alphabet = ALPHABETS[locale]
    members = data["objects"][font_object]
    return members[alphabet] if alphabet in members else members["*"]


def visible_text(text):
    """Read WoW's explicit markup delimiters; retain link labels and escaped pipes.

    This removes only encoded presentation metadata, never character categories.
    Unknown or incomplete escapes stay literal so they cannot hide missing glyphs.
    """
    result, index = [], 0
    while index < len(text):
        if text.startswith("||", index):
            result.append("|")
            index += 2
            continue
        code = text[index : index + 2]
        if code in ("|r", "|h", "|n"):
            index += 2
            continue
        if code == "|c" and len(text[index + 2 : index + 10]) == 8:
            if all(c in "0123456789abcdefABCDEF" for c in text[index + 2 : index + 10]):
                index += 10
                continue
        if code in ("|T", "|A", "|H"):
            closing = {"|T": "|t", "|A": "|a", "|H": "|h"}[code]
            end = text.find(closing, index + 2)
            if end >= 0:
                index = end + 2
                continue
        result.append(text[index])
        index += 1
    return "".join(result)


def missing(data, locale, font_object, text):
    """Return absent rendered codepoints; newline/tab are layout instructions."""
    path = font_path(data, locale, font_object)
    spans = data["fonts"][path]["ranges"]
    return path, sorted(
        {
            ord(char)
            for char in visible_text(text)
            if char not in "\n\r\t" and not any(start <= ord(char) <= end for start, end in spans)
        }
    )


def read_entries(path):
    source = path.read_text(encoding="utf-8")
    if path.stem != "enUS":
        return parse(source)
    # English initializes ns.L before the phrase assignments. Locate the first
    # assignment through the lexer, then let the same strict locale parser read
    # the complete suffix. Unsupported statements in that suffix still fail.
    tokens, _ = tokenize(source)
    for index, token in enumerate(tokens[:-5]):
        if (
            token.text == "L"
            and tokens[index + 1].text == "["
            and tokens[index + 2].kind == "string"
            and tokens[index + 3].text == "]"
            and tokens[index + 4].text == "="
        ):
            lines = source.splitlines(keepends=True)
            prefix = 'local _, ns = ...\nif GetLocale() ~= "enUS" then return end\nlocal L = ns.L\n'
            _, entries = parse(prefix + "".join(lines[token.line - 1 :]))
            return "enUS", {key: Entry(entry.text, entry.line + token.line - 4) for key, entry in entries.items()}
    return "enUS", {}


def check(path, data, font_object, fallback=None):
    locale, entries = read_entries(path)
    if locale != path.stem:
        raise LocaleError(f"GetLocale guard {locale!r} does not match {path.stem}")
    sources = {key: (path, entry) for key, entry in entries.items()}
    if fallback is not None:
        english_path, english_entries = fallback
        for key, entry in english_entries.items():
            sources.setdefault(key, (english_path, entry))
    problems = []
    for key, (source_path, entry) in sources.items():
        font, absent = missing(data, locale, font_object, entry.text)
        for point in absent:
            problems.append(
                f"{source_path}:{entry.line}: {key!r}: U+{point:04X} absent in {font} ({font_object}, {locale})"
            )
    return problems


def check_bindings(root, data, manifest):
    """Check reviewed text-to-widget bindings, invalidating them on source change.

    These are explicit producer contracts, not inferred font choices. A source
    digest covers aliases, callbacks and later SetFont calls, which a nearby
    CreateFontString match alone cannot rule out. Review callers before updating
    a digest. English uses an explicit enUS entry when present, otherwise the
    phrase key, which must occur as an exact decoded Lua string in the producer.
    Dynamic text and unlisted producers have no coverage claim.
    """
    problems = []
    locales = {}
    for path in sorted((root / "Locales").glob("*.lua")):
        locale, entries = read_entries(path)
        if locale != path.stem:
            raise LocaleError(f"{path}: GetLocale guard does not match filename")
        locales[locale] = (path, entries)
    if "enUS" not in locales:
        raise LocaleError("bindings require Locales/enUS.lua for fallback")
    english_path, english = locales["enUS"]
    count = 0
    for producer in manifest["producers"]:
        path = root / producer["source"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != producer["sha256"]:
            problems.append(f"{path}: font binding source changed; review widget and callers before refreshing digest")
            continue
        tokens, _ = tokenize(path.read_text(encoding="utf-8"))
        literals = {_string(token): token.line for token in tokens if token.kind == "string"}
        for binding in producer["bindings"]:
            if ("phrase" in binding) == ("literal" in binding):
                raise ValueError("binding must name exactly one phrase or runtime literal")
            count += 1
            for locale, (locale_path, entries) in locales.items():
                if "phrase" in binding:
                    key = binding["phrase"]
                    if key not in english and key not in literals:
                        raise LocaleError(
                            f"{path}: binding names unknown English phrase {key!r}: "
                            "absent from enUS entries and producer string literals"
                        )
                    fallback = english[key] if key in english else Entry(key, literals[key])
                    entry = entries.get(key, fallback)
                    origin = locale_path if key in entries else english_path if key in english else path
                    location = f"{origin}:{entry.line}"
                    text = entry.text
                else:
                    key, text = "runtime literal", binding["literal"]
                    location = str(path)
                font, absent = missing(data, locale, binding["font"], text)
                for point in absent:
                    problems.append(
                        f"{location}: {key!r}: U+{point:04X} absent in {font} "
                        f"({binding['font']}, {locale}; {binding['widget']})"
                    )
    if not count:
        problems.append("no reviewed font bindings checked")
    return problems


def main(root, argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--font", help="actual font object used by every checked phrase")
    selection.add_argument(
        "--bindings", type=Path, help="reviewed producer manifest, defaults to tools/font_bindings.json"
    )
    parser.add_argument("--data", type=Path, default=Path(__file__).with_name("font_glyphs.json"))
    parser.add_argument("files", nargs="*", type=Path, help="locale files, defaults to all files in Locales")
    args = parser.parse_args(argv)
    data = json.loads(args.data.read_text())
    paths = args.files or sorted((root / "Locales").glob("*.lua"))
    if not args.font:
        if args.files:
            parser.error("locale file arguments require --font")
        manifest_path = args.bindings or root / "tools/font_bindings.json"
        try:
            problems = check_bindings(root, data, json.loads(manifest_path.read_text()))
        except (OSError, ValueError, KeyError, LuaSyntaxError) as error:
            problems = [f"{manifest_path}: cannot establish font coverage: {error}"]
        for problem in problems:
            print(problem)
        return int(bool(problems))
    english = root / "Locales/enUS.lua"
    try:
        fallback = (english, read_entries(english)[1]) if english.is_file() else None
    except (LocaleError, LuaSyntaxError, UnicodeError) as error:
        print(f"{english}: cannot read English fallback: {error}")
        return 1
    problems = []
    if not paths:
        problems.append(f"{root / 'Locales'}: no locale files found")
    for path in paths:
        try:
            problems.extend(check(path, data, args.font, fallback))
        except (LocaleError, LuaSyntaxError, KeyError, UnicodeError) as error:
            problems.append(f"{path}: cannot establish font coverage: {error}")
    for problem in problems:
        print(problem)
    return int(bool(problems))
