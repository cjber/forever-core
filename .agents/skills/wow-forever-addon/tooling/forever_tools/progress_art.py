"""Check art at generic progress bar usage sites."""

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from xml.parsers import expat

from .client_calls import _arguments, _blocks, _declarations, _enclosing, _expression, _field, _header_dos
from .lua import LuaSyntaxError, Token, tokenize
from .luadata import LuaDataError, unescape

REGISTRY = Path(__file__).with_name("asset-registry.md")
SLOTS = {"fill", "background", "template"}


@dataclass(frozen=True)
class Usage:
    line: int
    widget: str
    slot: str
    value: str


def _rows(text: str, section: str, columns: int) -> list[list[str]]:
    start = f"<!-- progress-{section}:start -->"
    end = f"<!-- progress-{section}:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"missing or duplicate progress {section} in asset registry")
    body = text.split(start, 1)[1].split(end, 1)[0]
    rows = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in body.splitlines() if row.strip()]
    if len(rows) < 2 or any(len(row) != columns or not all(row) for row in rows):
        raise ValueError(f"invalid progress {section} table in asset registry")
    return rows[2:]


def load_registry(path: Path = REGISTRY) -> tuple[dict[str, set[str]], set[tuple[str, ...]]]:
    text = path.read_text(encoding="utf-8")
    approved = defaultdict(set)
    for slot, value in _rows(text, "approvals", 2):
        approved[slot].add(value)
    if approved.keys() != SLOTS:
        raise ValueError("asset registry must approve fill, background and template slots")
    exceptions = set()
    for addon, file, widget, slot, value, source in _rows(text, "exceptions", 6):
        if (
            slot not in SLOTS
            or "*" in (addon, file, widget, value)
            or not re.fullmatch(
                r"https://github.com/Gethe/wow-ui-source/blob/[a-f0-9]{40}/[^\s#]+#L\d+(?:-L\d+)?", source
            )
        ):
            raise ValueError(f"invalid native progress exception for {addon}/{file} {widget}")
        exceptions.add((addon, file, widget, slot, value))
    return dict(approved), exceptions


def _path(tokens: list[Token]) -> str | None:
    if tokens and all(token.kind == "name" if i % 2 == 0 else token.text == "." for i, token in enumerate(tokens)):
        return "".join(token.text for token in tokens)
    return None


def _receiver(tokens: list[Token], end: int) -> str:
    start = end - 1
    while start >= 2 and tokens[start - 1].text == "." and tokens[start - 2].kind == "name":
        start -= 2
    return _path(tokens[start:end]) or "?"


def _literal(tokens: list[Token]) -> str | None:
    if tokens and all(token.kind == "string" if i % 2 == 0 else token.text == ".." for i, token in enumerate(tokens)):
        try:
            return "".join(unescape(token.text) for token in tokens[::2])
        except LuaDataError:
            return None
    if len(tokens) == 1 and tokens[0].kind == "number":
        return tokens[0].text
    return None


def lua_usages(source: str, templates: set[str]) -> list[Usage]:
    tokens, _ = tokenize(source)
    ends = _blocks(tokens, _header_dos(tokens))
    scopes, declared = _declarations(tokens, ends, _enclosing(tokens, ends))

    def binding(path: str, index: int) -> tuple[str, int]:
        base = path.split(".", 1)[0]
        return path, max((start for start, end in scopes.get(base, ()) if start <= index <= end), default=-1)

    def asset(argument: list[Token], index: int) -> str | None:
        return _literal(argument) or constants.get(binding(_path(argument) or "", index))

    constants: dict[tuple[str, int], str] = {}
    bars: set[tuple[str, int]] = set()
    textures: dict[tuple[str, int], tuple[tuple[str, int], str]] = {}
    paints: dict[tuple[str, int], Usage] = {}
    fills: dict[tuple[str, int], str] = {}
    usages = []
    assignment: tuple[tuple[str, int], int] | None = None

    for index, token in enumerate(tokens[:-1]):
        word = token.text
        if word == "=" and index and tokens[index - 1].kind == "name":
            end = _expression(tokens, index + 1, ends)
            path = _receiver(tokens, index)
            target = binding(path, end if index - 1 in declared else index)
            value = asset(tokens[index + 1 : end], index)
            bars.discard(target)
            textures.pop(target, None)
            paints.pop(target, None)
            fills.pop(target, None)
            constants.pop(target, None)
            if value:
                constants[target] = value
            assignment = (target, index + 1)

        if (
            word
            not in {
                "CreateFrame",
                "CreateTexture",
                "SetStatusBarTexture",
                "SetAtlas",
                "SetTexture",
                "SetColorTexture",
                "SetBackdrop",
            }
            or tokens[index + 1].text != "("
        ):
            continue
        args = _arguments(tokens, index + 1)
        first = asset(args[0], index)
        receiver = _receiver(tokens, index - 1) if index and tokens[index - 1].text == ":" else "?"
        widget = binding(receiver, index)
        if word == "CreateFrame" and assignment and assignment[1] == index:
            target = assignment[0]
            template = asset(args[3], index) if len(args) >= 4 else None
            inherited = {name.strip() for name in (template or "").split(",")} - {"", "BackdropTemplate"}
            if first == "StatusBar" or inherited & templates:
                bars.add(target)
                usages.extend(Usage(token.line, target[0], "template", name) for name in inherited)
        elif word == "CreateTexture" and receiver != "?" and assignment and len(args) >= 2:
            start = index - 2
            while start >= 2 and tokens[start - 1].text == ".":
                start -= 2
            if assignment[1] == start:
                textures[assignment[0]] = (widget, asset(args[1], index) or "")
        elif word == "SetStatusBarTexture":
            if first:
                usages.append(Usage(token.line, receiver, "fill", first))
            elif path := _path(args[0]):
                target = binding(path, index)
                fills[target] = receiver
                if paint := paints.get(target):
                    usages.append(Usage(paint.line, receiver, "fill", paint.value))
        elif word == "SetBackdrop" and widget in bars and args[0] and args[0][0].text != "nil":
            backdrop = [value for name in ("bgFile", "edgeFile") if (value := _field(args[0], name))]
            usages.extend(
                Usage(token.line, receiver, "background", value) for value in backdrop or [first or "SetBackdrop"]
            )
        elif word in {"SetAtlas", "SetTexture", "SetColorTexture"}:
            value = "SetColorTexture" if word == "SetColorTexture" else first
            if value:
                paints[widget] = Usage(token.line, receiver, "fill", value)
                if widget in fills:
                    usages.append(Usage(token.line, fills[widget], "fill", value))
                elif receiver.endswith(".Fill") and binding(receiver[:-5], index) in bars:
                    usages.append(Usage(token.line, receiver[:-5], "fill", value))
                elif widget in textures:
                    parent, layer = textures[widget]
                    if parent in bars and layer == "BACKGROUND":
                        usages.append(Usage(token.line, parent[0], "background", value))
    return usages


def xml_usages(source: str, templates: set[str]) -> list[Usage]:
    parser = expat.ParserCreate(namespace_separator=" ")
    stack: list[tuple[str, str | None]] = []
    usages = []

    def start(tag: str, attrs: dict[str, str]) -> None:
        tag = tag.rsplit(" ", 1)[-1]
        line = parser.CurrentLineNumber
        parent, widget = stack[-1] if stack else ("", None)
        inherited = {name.strip() for name in attrs.get("inherits", "").split(",")} - {"", "BackdropTemplate"}
        if tag in {"Frame", "StatusBar", "Button"}:
            widget = None
            if tag == "StatusBar" or inherited & templates:
                widget = attrs.get("name") or attrs.get("parentKey") or tag
                for name in sorted(inherited):
                    usages.append(Usage(line, widget, "template", name))
        if widget:
            if tag in {"BarTexture", "Texture"}:
                if tag == "BarTexture" or attrs.get("parentKey") == "Fill":
                    slot = "fill"
                elif parent == "BACKGROUND":
                    slot = "background"
                else:
                    slot = None
                if slot and (value := attrs.get("atlas") or attrs.get("file") or attrs.get("color")):
                    usages.append(Usage(line, widget, slot, value))
            elif tag == "Color" and parent == "Texture" and len(stack) >= 2 and stack[-2][0] == "BACKGROUND":
                usages.append(Usage(line, widget, "background", "Color"))
            elif tag == "Backdrop":
                backdrop = [attrs[name] for name in ("bgFile", "edgeFile") if name in attrs]
                usages.extend(Usage(line, widget, "background", value) for value in backdrop or ["Backdrop"])
        stack.append((attrs.get("level", tag) if tag == "Layer" else tag, widget))

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda _: stack.pop()
    parser.Parse(source, True)
    return usages


def check(source: str, suffix: str, addon: str, file: str, registry: tuple) -> list[tuple[int, str]]:
    approved, exceptions = registry
    try:
        if suffix == ".lua":
            usages = lua_usages(source, approved["template"])
        elif suffix == ".xml":
            usages = xml_usages(source, approved["template"])
        else:
            return []
    except (LuaSyntaxError, expat.ExpatError) as error:
        return [(1, f"progress-art: could not inspect source: {error}")]
    return sorted(
        {
            (
                use.line,
                f"progress-art: {use.widget} {use.slot} {use.value!r}; use {', '.join(sorted(approved[use.slot]))}",
            )
            for use in usages
            if use.value not in approved[use.slot] and (addon, file, use.widget, use.slot, use.value) not in exceptions
        }
    )
