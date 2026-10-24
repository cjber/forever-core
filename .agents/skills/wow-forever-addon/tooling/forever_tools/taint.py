"""Reject addon code that writes into or hooks Blizzard's objects, or runs Blizzard code whose state it would taint.

Forever runs Blizzard's UI through secure delegates. A method an addon hooked or replaced on a Blizzard object,
a field it wrote there, or a lazy cache Blizzard first built from addon code, then fails or is blocked inside
Blizzard's own calls, blamed on this addon. An exception needs a `-- taint-ok: <reason>` comment on its line that
names an addon-owned object or a verified safe contract.
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .lua import LuaSyntaxError, Token, tokenize

__all__ = ["DEFAULT_POLICY", "Policy", "check", "run"]

# Globals the family's addons own. Every other global root is Blizzard's (or another addon's).
OWN = re.compile(
    r"(?:Tweaks|SkillUp|Legacy|ShortestPath|AdventureGuide|WorkOrders)Forever\w*|WOF_\w+|SLASH_\w+|SlashCmdList"
)

# Blizzard functions that must only run from Blizzard's code: layout that writes its frames' state, lazy caches
# built on first call, and links other Blizzard code reads.
CALLS = {
    "SetModuleContainer": "registering addon modules taints Blizzard tracker layout",
    "UpdateFrameSize": "bag layout writes the bag's state",
    "UpdateItemLayout": "bag layout builds the bag's item cache",
    "UpdateContainerFrameAnchors": "bag anchoring builds the shown-bags cache",
    "UpdateUIPanelPositions": "panel layout writes the panel manager's state",
    "GetBagsShown": "lazy cache of shown bags",
    "EnumerateValidItems": "lazy cache of a bag's items",
    "GetBagSize": "lazy cache of a bag's size",
    "GetRows": "reads the lazy bag size cache",
    "ContainerFrameUtil_EnumerateContainerFrames": "lazy cache of bag frames",
    "SetParentInitializer": "the settings search reads this link",
    "AddMaskableTexture": "writes into the map canvas's texture list",
    "UpdateAnchors": "nameplate layout writes the plate's state",
}

# Blizzard globals that open the world map or turn it. Run from addon code they taint the map's fields until a
# reload, so its pins are blocked in combat. C_Map.OpenWorldMap asks the game to open it from its own code.
MAP_OPENERS = {
    "OpenWorldMap": "sets the map's mapID as the addon; C_Map.OpenWorldMap has Blizzard's code do it",
    "OpenQuestLog": "runs the world map's layout as the addon; open it with C_Map.OpenWorldMap",
    "ToggleWorldMap": "runs the world map's layout as the addon; open it with C_Map.OpenWorldMap",
    "QuestMapFrame_ShowQuestDetails": "writes the quest details frame's questID, which the map's quest pins read",
}
MAP_REASON = "sets the map's mapID as the addon; C_Map.OpenWorldMap has Blizzard's code do it"
# Blizzard's map canvases, and the call that returns one from a pin or provider. SetMapID on these is the
# retarget C_Map.OpenWorldMap replaces; the same method on a canvas the addon created is its own.
MAP_FRAMES = frozenset({"WorldMapFrame", "BattlefieldMapFrame", "FlightMapFrame"})
MAP_GETTERS = frozenset({"GetMap"})


@dataclass(frozen=True)
class Policy:
    own: re.Pattern[str] = OWN
    calls: dict[str, str] = field(default_factory=lambda: dict(CALLS))
    map_openers: dict[str, str] = field(default_factory=lambda: dict(MAP_OPENERS))
    map_frames: frozenset[str] = MAP_FRAMES
    map_getters: frozenset[str] = MAP_GETTERS


DEFAULT_POLICY = Policy()


def flagged(comments: dict[int, str], line: int) -> bool:
    return not re.fullmatch(r"taint-ok:\s*\S.*", comments.get(line, ""))


def chain_names(tokens: list[Token], index: int) -> list[str]:
    """Names in the call chain starting at the name at `index`: `a.b:c(x).d` gives a, b, c, d."""
    names = [tokens[index].text]
    cursor = index + 1
    while True:
        if tokens[cursor].text in {".", ":"} and tokens[cursor + 1].kind == "name":
            names.append(tokens[cursor + 1].text)
            cursor += 2
        elif tokens[cursor].text == "(":
            depth = 0
            while True:
                depth += tokens[cursor].text == "("
                depth -= tokens[cursor].text == ")"
                cursor += 1
                if depth == 0:
                    break
        else:
            return names


def locals_of(tokens: list[Token], policy: Policy) -> tuple[set[str], set[str], set[str]]:
    """Names bound by local, for or function parameters anywhere in the file, those bound to a new table, and
    those bound to one of Blizzard's map canvases."""
    names: set[str] = {"ns", "self", "_G"}
    tables: set[str] = {"ns"}
    maps: set[str] = set()
    for index, token in enumerate(tokens):
        if token.text == "local" and tokens[index + 1].text == "function":
            names.add(tokens[index + 2].text)
        elif token.text in {"local", "for"}:
            cursor = index + 1
            bound = []
            while tokens[cursor].kind == "name":
                bound.append(tokens[cursor].text)
                if tokens[cursor + 1].text != ",":
                    break
                cursor += 2
            names.update(bound)
            if token.text == "local" and len(bound) == 1 and tokens[cursor + 1].text == "=":
                if tokens[cursor + 2].text == "{":
                    tables.add(bound[0])
                elif tokens[cursor + 2].kind == "name":
                    chain = chain_names(tokens, cursor + 2)
                    if chain[0] in policy.map_frames or policy.map_getters.intersection(chain):
                        maps.add(bound[0])
        elif token.text == "function":
            cursor = index + 1
            while tokens[cursor].text != "(":
                cursor += 1
            cursor += 1
            while tokens[cursor].text != ")":
                if tokens[cursor].kind == "name":
                    names.add(tokens[cursor].text)
                cursor += 1
    return names, tables, maps


def chain_end(tokens: list[Token], index: int) -> int:
    """Index just past `root(.name|[expr])*` starting at the root name at `index`."""
    cursor = index + 1
    while True:
        if tokens[cursor].text == "." and tokens[cursor + 1].kind == "name":
            cursor += 2
        elif tokens[cursor].text == "[":
            depth = 0
            while True:
                depth += tokens[cursor].text == "["
                depth -= tokens[cursor].text == "]"
                cursor += 1
                if depth == 0:
                    break
        else:
            return cursor


def receiver_root(tokens: list[Token], index: int, policy: Policy) -> tuple[str | None, bool]:
    """For a method name at `index` after `.` or `:`, the root name of its receiver, and whether the receiver is a
    call to a map getter (`pin:GetMap():SetMapID()`)."""
    cursor = index - 2
    if tokens[cursor].text == ")":
        depth = 0
        while cursor >= 0:
            depth += tokens[cursor].text == ")"
            depth -= tokens[cursor].text == "("
            if depth == 0:
                break
            cursor -= 1
        return None, cursor > 0 and tokens[cursor - 1].text in policy.map_getters
    while cursor >= 2 and tokens[cursor - 1].text in {".", ":"} and tokens[cursor - 2].kind == "name":
        cursor -= 2
    return (tokens[cursor].text if tokens[cursor].kind == "name" else None), False


def map_retarget(tokens: list[Token], index: int, maps: set[str], policy: Policy) -> bool:
    """Whether the `SetMapID` at `index` retargets one of Blizzard's map canvases."""
    if tokens[index - 1].text not in {".", ":"}:
        return False
    root, getter = receiver_root(tokens, index, policy)
    return getter or (root is not None and (root in policy.map_frames or root in maps))


def _check(source: str, policy: Policy) -> list[tuple[int, str]]:
    tokens, comments = tokenize(source)
    names, tables, maps = locals_of(tokens, policy)
    findings: list[tuple[int, str]] = []

    def report(line: int, message: str) -> None:
        if flagged(comments, line):
            findings.append((line, message))

    headers: set[int] = set()
    for index, token in enumerate(tokens):
        previous = tokens[index - 1].text if index else ""
        if token.text == "function" and tokens[index + 1].kind == "name":
            # A named definition: its name chain is not a call, and a Blizzard root is a replaced method.
            cursor = index + 1
            while tokens[cursor].text != "(":
                headers.add(cursor)
                cursor += 1
            root = tokens[index + 1]
            if cursor > index + 2 and root.text not in names and not policy.own.fullmatch(root.text):
                report(root.line, f"taint-blizzard-write: defines a method on Blizzard's {root.text}")
            continue
        if token.kind != "name" or index in headers:
            continue
        if token.text == "hooksecurefunc" and tokens[index + 1].text == "(":
            first = tokens[index + 2]
            if first.kind != "string" and not (first.text in tables and tokens[index + 3].text == ","):
                report(token.line, "taint-method-hook: hooksecurefunc on an object; hook a script or an event")
        elif token.text in policy.calls and tokens[index + 1].text == "(" and previous != "function":
            report(token.line, f"taint-blizzard-call: {token.text} ({policy.calls[token.text]})")
        elif (
            token.text in policy.map_openers
            and tokens[index + 1].text == "("
            and (previous not in {".", ":", "function"} or tokens[index - 2].text == "_G")
        ):
            report(token.line, f"taint-blizzard-call: {token.text} ({policy.map_openers[token.text]})")
        elif token.text == "SetMapID" and tokens[index + 1].text == "(" and map_retarget(tokens, index, maps, policy):
            report(token.line, f"taint-blizzard-call: SetMapID ({MAP_REASON})")
        elif previous not in {".", ":"} and token.text not in names and not policy.own.fullmatch(token.text):
            end = chain_end(tokens, index)
            if end > index + 1 and tokens[end].text == "=":
                report(token.line, f"taint-blizzard-write: writes a field of Blizzard's {token.text}")
    return findings


def check(source: str, policy: Policy = DEFAULT_POLICY) -> list[tuple[int, str]]:
    """`(line, message)` for each taint risk in `source`; malformed Lua raises LuaSyntaxError."""
    try:
        return _check(source, policy)
    except IndexError as error:
        raise LuaSyntaxError("unexpected end of file") from error


def run(paths: list[Path], policy: Policy = DEFAULT_POLICY) -> int:
    failed = False
    for path in paths:
        try:
            findings = check(path.read_text(encoding="utf-8"), policy)
        except (LuaSyntaxError, OSError, UnicodeDecodeError) as error:
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
            continue
        for line, message in findings:
            print(f"{path}:{line}: {message}")
            failed = True
    return int(failed)
