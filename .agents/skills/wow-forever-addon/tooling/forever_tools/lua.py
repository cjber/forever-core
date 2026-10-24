"""Lua 5.1 lexer shared by the taint and multi-value lints."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    text: str
    line: int
    kind: str = "symbol"
    end_line: int = 0

    def __post_init__(self) -> None:
        if not self.end_line:
            object.__setattr__(self, "end_line", self.line)

    @property
    def value(self) -> str:
        return self.text


class LuaSyntaxError(ValueError):
    pass


LONG_OPEN = re.compile(r"\[(=*)\[")
NUMBER = re.compile(r"(?:0[xX][0-9a-fA-F]+|(?:\d+(?:\.(?!\.)\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
KEYWORDS = frozenset(
    "and break do else elseif end false for function if in local nil not or repeat return then true until while".split()
)
OPERATORS = ("...", "..", "==", "~=", "<=", ">=")
SINGLE = "+-*/%^#=<>;:,().{}[]"


def tokenize(source: str) -> tuple[list[Token], dict[int, str]]:
    """Tokens ending in `<eof>`, and each line comment's text by line (long comments are not recorded)."""
    tokens: list[Token] = []
    comments: dict[int, str] = {}
    pos, line = 0, 1
    while pos < len(source):
        start, first_line = pos, line
        char = source[pos]
        if char.isspace():
            line += char == "\n"
            pos += 1
            continue
        comment = source.startswith("--", pos)
        long = LONG_OPEN.match(source, pos + 2 if comment else pos)
        if long:
            closing = "]" + long[1] + "]"
            end = source.find(closing, long.end())
            if end < 0:
                raise LuaSyntaxError(f"{line}: unterminated long string/comment")
            pos = end + len(closing)
            kind = "string"
        elif comment:
            end = source.find("\n", pos)
            pos = len(source) if end < 0 else end
            comments[line] = source[start + 2 : pos].strip()
            continue
        elif char in "\"'":
            pos += 1
            while pos < len(source) and source[pos] != char:
                if source[pos] == "\n":
                    raise LuaSyntaxError(f"{line}: newline in quoted string")
                if source[pos] == "\\":
                    pos += 1
                    if source[pos : pos + 2] == "\r\n":
                        pos += 1
                pos += 1
            if pos >= len(source):
                raise LuaSyntaxError(f"{line}: unterminated quoted string")
            pos += 1
            kind = "string"
        elif number := NUMBER.match(source, pos):
            pos = number.end()
            kind = "number"
        elif name := NAME.match(source, pos):
            pos = name.end()
            kind = "keyword" if name[0] in KEYWORDS else "name"
        else:
            symbol = next((s for s in OPERATORS if source.startswith(s, pos)), char)
            if symbol == char and char not in SINGLE:
                raise LuaSyntaxError(f"{line}: unexpected character {char!r}")
            pos += len(symbol)
            kind = "symbol"
        line += source.count("\n", start, pos)
        if not comment:
            tokens.append(Token(source[start:pos], first_line, kind, line))
    tokens.append(Token("<eof>", line))
    return tokens, comments
