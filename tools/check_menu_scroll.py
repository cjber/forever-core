"""Refuse a menu built from a list that can outgrow the screen without scrolling.

Blizzard's Menu API never clamps a submenu to the screen, and a dropdown's root only flips sideways, so a menu whose
entries come from a list runs off the bottom once the list is long (Shortest Path Forever's vendors by specialty,
cjber/shortest-path-forever#359). `description:SetScrollMode(extent)` makes a root or submenu description scroll
past `extent` pixels (Blizzard_Menu/Menu.lua, "Scrolling Menus" in 11_0_0_MenuImplementationGuide.lua).

In every addon Lua file (outside tests/, tools/, types/, docs/, Libs/ and dot folders):

- A description that gets an entry (`CreateButton`, `CreateCheckbox`, `CreateRadio`, `CreateTitle`, `CreateDivider`
  or another Menu inserter) inside a loop, or is passed to a call inside a loop, needs `SetScrollMode(...)` on that
  same description in the same function. A loop counts only when the description was bound before it: a submenu
  made inside the loop body gets each pass's entries once. A numeric `for` with literal bounds and a `for` over an
  inline table constructor have a fixed length and never count.
- `UIDropDownMenu_AddButton` inside a loop is refused: the old dropdown cannot scroll, so build the list with the
  Menu API and SetScrollMode.

A loop known to stay short says why on its `for`, `while` or `repeat` line, or the line above:
`-- menu-scroll-ok: <reason of three words or more>`. A marker with no reason, or one that excuses nothing, fails.

    python3 tools/check_menu_scroll.py            every addon Lua file in this repository
    python3 tools/check_menu_scroll.py FILE...    only these files
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The Menu API's inserters (Blizzard_Menu/MenuUtil.lua, MenuUtilPrivate.Inserters) but CreateFrame, a name too
# common outside menus to read as one here.
INSERTERS = frozenset(
    (
        "CreateButton",
        "CreateCheckbox",
        "CreateRadio",
        "CreateTitle",
        "CreateDivider",
        "CreateSpacer",
        "CreateTemplate",
        "CreateHighlightButton",
        "CreateHighlightRadio",
        "CreateColorSwatch",
        "CreateSearchEntry",
    )
)
# Calls whose function argument builds a menu: its second parameter is the root description.
GENERATOR_CALLS = frozenset({"CreateContextMenu", "SetupMenu", "ModifyMenu"})
LEGACY_ADD = "UIDropDownMenu_AddButton"
SCROLL = "SetScrollMode"
SKIPPED_DIRS = frozenset({"tests", "tools", "types", "docs", "Libs", "libs", "node_modules"})
MARKER = re.compile(r"menu-scroll-ok\b:?\s*(.*)")
MIN_REASON_WORDS = 3
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

    return tokenize(source)


@dataclass
class Loop:
    index: int
    line: int
    fixed: bool = False
    awaiting_do: bool = False


@dataclass
class Block:
    kind: str  # "function", "loop" or "block"
    index: int
    loop: Loop | None = None
    scope: dict[str, int] = field(default_factory=dict)


@dataclass
class Function:
    descriptions: set[str] = field(default_factory=set)
    scrolled: set[str] = field(default_factory=set)
    # (description, binding token index, line, enclosing loops in this function, how it got entries)
    uses: list[tuple[str, int, int, list[Loop], str]] = field(default_factory=list)
    # Bare names passed to a call inside a loop: (name, binding index, line, loops).
    passes: list[tuple[str, int, int, list[Loop]]] = field(default_factory=list)


def _skip_group(tokens, index):
    """The index just past the bracket group opening at `index`."""
    closing, depth = OPENERS[tokens[index].text], 0
    for at in range(index, len(tokens)):
        text = tokens[at].text if tokens[at].kind == "symbol" else ""
        if text == tokens[index].text:
            depth += 1
        elif text == closing:
            depth -= 1
            if depth == 0:
                return at + 1
    return len(tokens)


def _is(token, text):
    return token.kind in ("symbol", "keyword") and token.text == text


def _call_end(tokens, at):
    """The index past the arguments that start at `at`, and past any `:Method(...)` chained onto the result."""
    while True:
        if _is(tokens[at], "(") or _is(tokens[at], "{"):
            at = _skip_group(tokens, at)
        elif tokens[at].kind == "string":
            at += 1
        else:
            return at
        if not (_is(tokens[at], ":") and tokens[at + 1].kind == "name"):
            return at
        at += 2


def _leaves(tokens, at):
    """Whether the statement ending before `at` is followed by `return` or `break`, so its loop runs it once."""
    while _is(tokens[at], ";"):
        at += 1
    return _is(tokens[at], "return") or _is(tokens[at], "break")


def _fixed_header(header):
    """Whether a `for` header (the tokens between `for` and `do`) has a fixed, literal length."""
    numbers = [token for token in header[2:] if not _is(token, ",") and not _is(token, "-")]
    if len(header) > 1 and _is(header[1], "="):
        return all(token.kind == "number" for token in numbers)
    if any(_is(token, "in") for token in header):
        after = header[[_is(token, "in") for token in header].index(True) + 1 :]
        return (
            len(after) >= 4
            and after[0].text in ("ipairs", "pairs")
            and _is(after[1], "(")
            and _is(after[2], "{")
            and _skip_group(after, 2) == len(after) - 1
            and _is(after[-1], ")")
        )
    return False


def _receiver(tokens, colon):
    """The description before `:Method` as a dotted name chain (None for any other expression), and where it starts."""
    at = colon - 1
    if tokens[at].kind != "name":
        return None, at
    while at >= 2 and _is(tokens[at - 1], ".") and tokens[at - 2].kind == "name":
        at -= 2
    return "".join(token.text for token in tokens[at:colon]), at


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.blocks: list[Block] = []
        self.functions: list[Function] = []
        self.legacy: list[tuple[int, list[Loop]]] = []

    # Scopes ------------------------------------------------------------------------------------------------------

    def bind(self, name, index):
        if self.blocks:
            self.blocks[-1].scope[name] = index

    def binding(self, name):
        """The token index `name` was bound at in this function, or -1 when it comes from outside it."""
        for block in reversed(self.blocks):
            if name in block.scope:
                return block.scope[name]
            if block.kind == "function":
                break
        return -1

    def open_loops(self):
        """The loops around this point, inside the innermost function."""
        loops = []
        for block in reversed(self.blocks):
            if block.kind == "function":
                break
            if block.loop and not block.loop.awaiting_do:
                loops.append(block.loop)
        return loops

    def function(self):
        for block in reversed(self.blocks):
            if block.kind == "function":
                return self.functions[block.index]
        return None

    # Walk --------------------------------------------------------------------------------------------------------

    def run(self):
        tokens = self.tokens
        self.functions.append(Function())
        self.blocks.append(Block("function", 0))
        generator_at: set[int] = set()
        at = 0
        while at < len(tokens):
            token = tokens[at]
            text = token.text if token.kind in ("keyword", "symbol") else None
            if text == "function":
                self.open_function(at, at in generator_at)
            elif text in ("for", "while"):
                loop = Loop(at, token.line, awaiting_do=True)
                if text == "for":
                    end = next(i for i in range(at, len(tokens)) if _is(tokens[i], "do") or i == len(tokens) - 1)
                    loop.fixed = _fixed_header(tokens[at + 1 : end])
                self.blocks.append(Block("loop", at, loop))
                if text == "for":
                    names = at + 1
                    while tokens[names].kind == "name":
                        self.bind(tokens[names].text, at)
                        if not _is(tokens[names + 1], ","):
                            break
                        names += 2
            elif text == "do":
                top = self.blocks[-1] if self.blocks else None
                if top and top.loop and top.loop.awaiting_do:
                    top.loop.awaiting_do = False
                else:
                    self.blocks.append(Block("block", at))
            elif text == "repeat":
                loop = Loop(at, token.line)
                self.blocks.append(Block("loop", at, loop))
            elif text == "if":
                self.blocks.append(Block("block", at))
            elif text in ("elseif", "else") and self.blocks:
                self.blocks[-1].scope.clear()
            elif text in ("end", "until") and len(self.blocks) > 1:
                self.blocks.pop()
            elif text == "local":
                self.declare(at)
            elif text == ":" and tokens[at + 1].kind == "name":
                self.method(at)
            elif token.kind == "name":
                if token.text == LEGACY_ADD and _is(tokens[at + 1], "("):
                    self.legacy.append((token.line, self.open_loops()))
                elif token.text in GENERATOR_CALLS and _is(tokens[at + 1], "("):
                    generator_at |= self.generator_functions(at + 1)
                self.argument(at)
            at += 1
        return self

    def open_function(self, at, generator):
        tokens = self.tokens
        self.functions.append(Function())
        block = Block("function", len(self.functions) - 1)
        paren = next(i for i in range(at, len(tokens)) if _is(tokens[i], "("))
        is_method = any(_is(tokens[i], ":") for i in range(at, paren))
        self.blocks.append(block)
        params = [tokens[i].text for i in range(paren + 1, _skip_group(tokens, paren) - 1) if tokens[i].kind == "name"]
        if is_method:
            params.insert(0, "self")
        for name in params:
            self.bind(name, at)
        if generator and len(params) > 1:
            self.functions[-1].descriptions.add(params[1])

    def generator_functions(self, paren):
        """Token indices of `function` literals passed straight to a menu generator call."""
        end, depth, found = _skip_group(self.tokens, paren), 0, set()
        for at in range(paren, end):
            token = self.tokens[at]
            if token.kind == "symbol" and token.text in OPENERS:
                depth += 1
            elif token.kind == "symbol" and token.text in OPENERS.values():
                depth -= 1
            elif _is(token, "function") and depth == 1:
                found.add(at)
        return found

    def declare(self, at):
        tokens = self.tokens
        if _is(tokens[at + 1], "function"):
            self.bind(tokens[at + 2].text, at)
            return
        names, cursor = [], at + 1
        while tokens[cursor].kind == "name":
            names.append(tokens[cursor].text)
            if not _is(tokens[cursor + 1], ","):
                break
            cursor += 2
        cursor += 1
        # `local x = y:CreateButton(...)` makes x a description.
        if len(names) == 1 and _is(tokens[cursor], "="):
            end = cursor + 1
            while end < len(tokens) and (tokens[end].kind == "name" or _is(tokens[end], ".")):
                end += 1
            if _is(tokens[end], ":") and tokens[end + 1].text in INSERTERS:
                function = self.function()
                if function:
                    function.descriptions.add(names[0])
        for name in names:
            self.bind(name, at)

    def method(self, colon):
        tokens = self.tokens
        name = tokens[colon + 1].text
        if name not in INSERTERS and name != SCROLL:
            return
        key, start = _receiver(tokens, colon)
        # A call result is a fresh description each time; `function Description:CreateButton` is a definition.
        if key is None or (start > 0 and _is(tokens[start - 1], "function")):
            return
        function = self.function()
        if function is None:
            return
        if name == SCROLL:
            function.scrolled.add(key)
            return
        function.descriptions.add(key)
        if _leaves(tokens, _call_end(tokens, colon + 2)):
            return
        bound = self.binding(key.split(".", 1)[0])
        function.uses.append((key, bound, tokens[colon].line, self.open_loops(), name))

    def argument(self, at):
        """A bare name passed to a call: `Fill(menu, ...)`."""
        tokens = self.tokens
        before, after = tokens[at - 1] if at else None, tokens[at + 1]
        if not (before and (_is(before, "(") or _is(before, ",")) and (_is(after, ",") or _is(after, ")"))):
            return
        loops = self.open_loops()
        function = self.function()
        if not loops or not function:
            return
        opening, depth = at - 1, 0
        while opening > 0 and not (depth == 0 and _is(tokens[opening], "(")):
            if tokens[opening].kind == "symbol" and tokens[opening].text in OPENERS.values():
                depth += 1
            elif tokens[opening].kind == "symbol" and tokens[opening].text in OPENERS:
                depth -= 1
            opening -= 1
        if not _leaves(tokens, _call_end(tokens, opening)):
            function.passes.append((tokens[at].text, self.binding(tokens[at].text), tokens[at].line, loops))


def check(source):
    """Each finding as (line, message)."""
    tokens, comments = _tokenize(source)
    parser = _Parser(tokens).run()
    markers = {}
    for line, text in comments.items():
        if match := MARKER.match(text):
            markers[line] = match[1].strip()

    def marker_for(loop):
        for line in (loop.line, loop.line - 1):
            if line in markers:
                return line
        return None

    findings, used = [], set()

    def counted(loops, bound):
        """The loops that repeat this entry: variable length and bound before the description."""
        result = []
        for loop in loops:
            if loop.fixed or bound >= loop.index:
                continue
            marker = marker_for(loop)
            if marker is not None and len(markers[marker].split()) >= MIN_REASON_WORDS:
                used.add(marker)
                continue
            result.append(loop)
        return result

    for function in parser.functions:
        reported = set()
        events = [(key, bound, line, loops, f":{how}(...)") for key, bound, line, loops, how in function.uses]
        events += [
            (name, bound, line, loops, f"a call that receives {name}")
            for name, bound, line, loops in function.passes
            if name in function.descriptions
        ]
        for key, bound, line, loops, how in sorted(events, key=lambda event: event[2]):
            repeating = counted(loops, bound)
            if not repeating or key in function.scrolled or key in reported:
                continue
            reported.add(key)
            findings.append(
                (
                    line,
                    f"menu-scroll: {key} gets entries through {how} in the loop at line {repeating[0].line} with no "
                    f"{key}:SetScrollMode(extent) in this function, so a long list runs off the screen; scroll it, "
                    "or mark the loop -- menu-scroll-ok: <why it stays short>",
                )
            )

    for line, loops in parser.legacy:
        if counted(loops, -1):
            findings.append(
                (
                    line,
                    f"menu-scroll: {LEGACY_ADD} in a loop builds a dropdown that cannot scroll; use the Menu API "
                    "(dropdown:SetupMenu) with SetScrollMode, or mark the loop -- menu-scroll-ok: <why it stays short>",
                )
            )

    for line, reason in markers.items():
        if len(reason.split()) < MIN_REASON_WORDS:
            findings.append(
                (line, f"menu-scroll-unused: this menu-scroll-ok names no reason of {MIN_REASON_WORDS} words")
            )
        elif line not in used:
            findings.append((line, "menu-scroll-unused: this menu-scroll-ok excuses no menu loop"))
    return sorted(set(findings))


def addon_files(root):
    """Every Lua file the addon could ship: outside tests, tools, types, docs, third-party Libs and dot folders."""
    files = []
    for path in sorted(root.rglob("*.lua")):
        parts = path.relative_to(root).parts
        if parts[0] in SKIPPED_DIRS or any(part.startswith(".") for part in parts):
            continue
        files.append(path)
    return files


def run(root, files):
    failed, checked = False, 0
    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
            continue
        checked += 1
        if ":Create" not in source and LEGACY_ADD not in source and "menu-scroll-ok" not in source:
            continue
        try:
            hits = check(source)
        except ValueError as error:  # forever_tools.lua.LuaSyntaxError
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
            continue
        shown = path.resolve().relative_to(root.resolve()) if path.resolve().is_relative_to(root.resolve()) else path
        for line, message in hits:
            print(f"{shown}:{line}: {message}")
        failed |= bool(hits)
    if not failed:
        print(f"Menu scroll check: {checked} Lua files checked")
    return int(failed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", type=Path)
    root = Path(__file__).resolve().parent.parent
    files = parser.parse_args(argv).files or addon_files(root)
    return run(root, files)


if __name__ == "__main__":
    sys.exit(main())
