"""Check art at generic progress bar usage sites."""

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from xml.parsers import expat

from .client_calls import _arguments
from .lua import Token, tokenize
from .luadata import unescape

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


def _asset(tokens: list[Token], constants: dict[str, str]) -> str | None:
    if tokens and all(token.kind == "string" if i % 2 == 0 else token.text == ".." for i, token in enumerate(tokens)):
        return "".join(unescape(token.text) for token in tokens[::2])
    return constants.get(_path(tokens) or "")


def lua_usages(source: str, templates: set[str]) -> list[Usage]:
    tokens, _ = tokenize(source)
    constants: dict[str, str] = {}
    bars: set[str] = set()
    textures: dict[str, tuple[str, str]] = {}
    paints: dict[str, Usage] = {}
    fills: dict[str, str] = {}
    usages = []

    for index, token in enumerate(tokens[:-1]):
        word = token.text
        if word == "=" and tokens[index - 1].kind == "name":
            end = index + 1
            while tokens[end].kind == "string" or tokens[end].text == "..":
                end += 1
            target = _receiver(tokens, index)
            if value := _asset(tokens[index + 1 : end], constants):
                constants[target] = value
            else:
                constants.pop(target, None)

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
        first = _asset(args[0], constants)
        receiver = _receiver(tokens, index - 1) if index and tokens[index - 1].text == ":" else "?"
        if word == "CreateFrame" and index and tokens[index - 1].text == "=":
            target = _receiver(tokens, index - 1)
            template = _asset(args[3], constants) if len(args) >= 4 else None
            if first == "StatusBar" or template in templates:
                bars.add(target)
                if template:
                    for name in template.split(","):
                        name = name.strip()
                        if name != "BackdropTemplate":
                            usages.append(Usage(token.line, target, "template", name))
        elif word == "CreateTexture" and index >= 3 and tokens[index - 1].text == ":":
            start = index - 2
            while start >= 2 and tokens[start - 1].text == ".":
                start -= 2
            if tokens[start - 1].text == "=" and len(args) >= 2:
                target = _receiver(tokens, start - 1)
                layer = _asset(args[1], constants) or ""
                textures[target] = (receiver, layer)
        elif word == "SetStatusBarTexture":
            if first:
                usages.append(Usage(token.line, receiver, "fill", first))
            elif target := _path(args[0]):
                fills[target] = receiver
        elif word == "SetBackdrop" and receiver in bars and args[0] and args[0][0].text != "nil":
            usages.append(Usage(token.line, receiver, "background", first or "SetBackdrop"))
        elif word in {"SetAtlas", "SetTexture", "SetColorTexture"}:
            value = first or ("SetColorTexture" if word == "SetColorTexture" else None)
            if value:
                paints[receiver] = Usage(token.line, receiver, "fill", value)
                if receiver in fills:
                    usages.append(Usage(token.line, fills[receiver], "fill", value))
                elif receiver.endswith(".Fill") and receiver[:-5] in bars:
                    usages.append(Usage(token.line, receiver[:-5], "fill", value))
                elif receiver in textures:
                    parent, layer = textures[receiver]
                    if parent in bars and layer == "BACKGROUND":
                        usages.append(Usage(token.line, parent, "background", value))
            continue

        if word == "SetStatusBarTexture" and not first and (target := _path(args[0])) in paints:
            paint = paints[target]
            usages.append(Usage(paint.line, receiver, "fill", paint.value))
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
            elif tag == "Backdrop":
                usages.append(Usage(line, widget, "background", attrs.get("bgFile", "Backdrop")))
        stack.append((attrs.get("level", tag) if tag == "Layer" else tag, widget))

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda _: stack.pop()
    parser.Parse(source, True)
    return usages


def check(source: str, suffix: str, addon: str, file: str, registry: tuple) -> list[tuple[int, str]]:
    approved, exceptions = registry
    if suffix == ".lua":
        usages = lua_usages(source, approved["template"])
    elif suffix == ".xml":
        usages = xml_usages(source, approved["template"])
    else:
        return []
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
